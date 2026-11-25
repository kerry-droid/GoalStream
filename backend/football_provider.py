from datetime import datetime, timedelta, timezone
import re
from threading import Event, Lock
from time import monotonic
from urllib.parse import urlencode, urlparse

import requests
from flask import current_app

_cache = {}
_calls = []
_daily_calls = []
_inflight = {}
_lock = Lock()

def _failure(message, status=503):
    error = RuntimeError(message)
    error.status_code = status
    return error


def _consume_quota(enforce_daily=True):
    now = monotonic()
    with _lock:
        _calls[:] = [stamp for stamp in _calls if stamp > now - 60]
        _daily_calls[:] = [stamp for stamp in _daily_calls if stamp > now - 86_400]
        minute_count = len(_calls)
        if minute_count >= current_app.config['FOOTBALL_PROVIDER_RPM']:
            raise _failure('Football data provider request limit reached. Try again shortly.', 429)
        if enforce_daily and len(_daily_calls) >= current_app.config['FOOTBALL_PROVIDER_DAILY_LIMIT']:
            raise _failure('Football data provider daily quota reached. Try again after the quota resets.', 429)
        _calls.append(now)
        if enforce_daily:
            _daily_calls.append(now)


def _fetch(url, headers, cache_seconds=60, enforce_daily=True):
    with _lock:
        now = monotonic()
        cached = _cache.get(url)
        if cached and cached[0] > now:
            return cached[1]
        flight = _inflight.get(url)
        leader = flight is None
        if leader:
            flight = {'event': Event(), 'error': None}
            _inflight[url] = flight
        if len(_cache) > 1500:
            for key in [key for key, value in _cache.items() if value[0] <= now]:
                _cache.pop(key, None)
    if not leader:
        flight['event'].wait(timeout=13)
        with _lock:
            cached = _cache.get(url)
            if cached and cached[0] > monotonic():
                return cached[1]
            error = flight['error']
            # The first request failed or took too long. Let this caller retry
            # as the new leader rather than returning an unrelated empty result.
            if _inflight.get(url) is flight:
                _inflight.pop(url, None)
        if error:
            raise error
        return _fetch(url, headers, cache_seconds, enforce_daily)

    try:
        _consume_quota(enforce_daily=enforce_daily)
        try:
            response = requests.get(url, headers=headers, timeout=12)
        except requests.RequestException as exc:
            raise _failure('Football data provider is unavailable.', 502) from exc
        if not response.ok:
            status = 429 if response.status_code == 429 else 502
            raise _failure(f'Football data provider returned {response.status_code}.', status)
        payload = response.json()
        if current_app.config['FOOTBALL_PROVIDER'] == 'api-football' and payload.get('errors'):
            raise _failure('Football data provider rejected the request.', 502)
        with _lock:
            _cache[url] = (monotonic() + cache_seconds, payload)
        return payload
    except Exception as exc:
        with _lock:
            flight['error'] = exc
        raise
    finally:
        with _lock:
            if _inflight.get(url) is flight:
                _inflight.pop(url, None)
            flight['event'].set()


def _football_data_normalize(path, query, payload):
    if path == 'fixtures':
        matches = payload.get('matches') or ([payload] if payload.get('id') else [])
        rows = []
        status_map = {'SCHEDULED': ('NS', 'Not Started'), 'TIMED': ('TBD', 'Not Started'), 'IN_PLAY': ('1H', 'In Play'), 'PAUSED': ('HT', 'Halftime'), 'FINISHED': ('FT', 'Match Finished'), 'POSTPONED': ('PST', 'Postponed'), 'CANCELLED': ('CANC', 'Cancelled'), 'SUSPENDED': ('SUSP', 'Suspended'), 'AWARDED': ('AWD', 'Awarded')}
        for match in matches:
            short, long = status_map.get(match.get('status'), (match.get('status', 'NS'), match.get('status', 'Not Started')))
            running = match.get('status') in ('IN_PLAY', 'PAUSED')
            score = match.get('score') or {}
            full = score.get('fullTime') or score.get('regularTime') or {}
            rows.append({
                'fixture': {'id': match.get('id'), 'date': match.get('utcDate'), 'venue': {'name': match.get('venue')}, 'status': {'short': short, 'long': long, 'elapsed': match.get('minute') if running else None}},
                'league': {'id': (match.get('competition') or {}).get('id'), 'name': (match.get('competition') or {}).get('name'), 'country': (match.get('area') or {}).get('name'), 'logo': (match.get('competition') or {}).get('emblem')},
                'teams': {'home': {'id': (match.get('homeTeam') or {}).get('id'), 'name': (match.get('homeTeam') or {}).get('name'), 'logo': (match.get('homeTeam') or {}).get('crest')}, 'away': {'id': (match.get('awayTeam') or {}).get('id'), 'name': (match.get('awayTeam') or {}).get('name'), 'logo': (match.get('awayTeam') or {}).get('crest')}},
                'goals': {'home': full.get('home'), 'away': full.get('away')}, 'score': score,
            })
        return rows
    if path == 'leagues':
        comps = payload.get('competitions') or ([payload] if payload.get('id') else [])
        return [{'league': {'id': item.get('id'), 'name': item.get('name'), 'type': item.get('type'), 'logo': item.get('emblem')}, 'country': {'name': (item.get('area') or {}).get('name'), 'code': (item.get('area') or {}).get('code')}, 'seasons': []} for item in comps]
    if path == 'teams':
        teams = payload.get('teams') or ([payload] if payload.get('id') else [])
        return [{'team': {'id': item.get('id'), 'name': item.get('name'), 'country': (item.get('area') or {}).get('name'), 'logo': item.get('crest')}} for item in teams]
    if path == 'standings':
        return payload.get('standings') or []
    return []


def _matchora_event_normalize(event):
    event_id = str((event or {}).get('id', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]+', event_id):
        return None
    kickoff = event.get('kickoff')
    date = datetime.fromtimestamp(kickoff, timezone.utc).isoformat() if isinstance(kickoff, (int, float)) else None
    raw_status = str(event.get('status') or 'NS').upper()
    status_names = {'NS': 'Not Started', 'LIVE': 'In Play', '1H': 'First Half', '2H': 'Second Half', 'HT': 'Halftime', 'ET': 'Extra Time', 'PEN': 'Penalties', 'FT': 'Match Finished', 'AET': 'Match Finished', 'PST': 'Postponed', 'CANC': 'Cancelled'}
    status = 'FT' if event.get('finished') else ('1H' if raw_status == 'LIVE' else raw_status)
    score = event.get('score')
    goals = {'home': None, 'away': None}
    if isinstance(score, str) and '-' in score:
        home, away = score.split('-', 1)
        goals = {'home': int(home) if home.strip().isdigit() else None, 'away': int(away) if away.strip().isdigit() else None}
    elif isinstance(score, dict):
        goals = {'home': score.get('home'), 'away': score.get('away')}
    channels = []
    for channel in event.get('channels') or []:
        channel_id = str((channel or {}).get('id') or '')
        if re.fullmatch(r'[A-Za-z0-9_-]+', channel_id):
            channels.append({
                'id': channel_id,
                'name': channel.get('name') or channel.get('label') or 'Matchora channel',
                'language': channel.get('language') or channel.get('lang'),
                'country': channel.get('country'),
                'quality': channel.get('quality'),
                'playing': channel.get('playing'),
                'dead': channel.get('dead'),
                'watching': channel.get('watching'),
            })
    embed_url = str(event.get('embed_url') or '')
    parsed_embed = urlparse(embed_url)
    allowed_matchora_hosts = {'matchora.to', 'matchora.pro', 'es.matchora.pro'}
    safe_embed_url = embed_url if (
        parsed_embed.scheme == 'https'
        and parsed_embed.hostname in allowed_matchora_hosts
        and parsed_embed.path == f'/embed/match/{event_id}'
    ) else None
    return {
        'fixture': {'id': int(event_id) if event_id.isdigit() else event_id, 'date': date, 'venue': {'name': None}, 'status': {'short': status, 'long': status_names.get(status, raw_status), 'elapsed': event.get('minute')}},
        'league': {'id': None, 'name': event.get('league'), 'country': None, 'logo': event.get('league_badge')},
        'teams': {'home': {'id': None, 'name': event.get('home'), 'logo': event.get('home_badge')}, 'away': {'id': None, 'name': event.get('away'), 'logo': event.get('away_badge')}},
        'goals': goals,
        'score': score if isinstance(score, dict) else {},
        'provider': 'matchora',
        'hasMatchEmbed': bool(event.get('embed_url')),
        'embedUrl': safe_embed_url,
        'channelCount': event.get('channel_count', 0),
        'channels': channels,
    }


def _matchora_fixtures(query):
    base_url = current_app.config['MATCHORA_BASE_URL'].rstrip('/')
    if query.get('id'):
        event_id = str(query['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+', event_id):
            raise _failure('Invalid Matchora event ID.', 400)
        payload = _fetch(f'{base_url}/api/v1/events/{event_id}', {}, enforce_daily=False)
        events = [payload]
    elif query.get('live'):
        payload = _fetch(f'{base_url}/api/v1/live', {}, enforce_daily=False)
        events = payload.get('events', []) if isinstance(payload, dict) else payload
    elif query.get('next'):
        url = f'{base_url}/api/v1/schedule?{urlencode({"watchable": 1})}'
        payload = _fetch(url, {}, enforce_daily=False)
        events = payload.get('events', []) if isinstance(payload, dict) else payload
    else:
        match_date = query.get('date') or datetime.now(timezone.utc).date().isoformat()
        url = f'{base_url}/api/v1/schedule?{urlencode({"date": match_date, "watchable": 1})}'
        payload = _fetch(url, {}, enforce_daily=False)
        events = payload.get('events', []) if isinstance(payload, dict) else payload
    rows = [_matchora_event_normalize(event) for event in (events or [])]
    rows = [row for row in rows if row and row['league']['name'] and row['teams']['home']['name'] and row['teams']['away']['name']]
    if query.get('id'):
        rows = [row for row in rows if str(row['fixture']['id']) == str(query['id'])]
    else:
        # Matchora's schedule contains several sports; request/event metadata
        # carries the sport field, so retain only football events below.
        source_events = {str(event.get('id')): event for event in (events or []) if re.fullmatch(r'[A-Za-z0-9_-]+', str(event.get('id', '')))}
        rows = [row for row in rows if str(source_events.get(str(row['fixture']['id']), {}).get('sport', '')).lower() in ('soccer', 'football')]
        if query.get('next'):
            now = datetime.now(timezone.utc)
            rows = [row for row in rows if row['fixture'].get('date') and datetime.fromisoformat(row['fixture']['date']) >= now and row['fixture']['status']['short'] not in ('FT', 'AET', 'CANC')]
            rows.sort(key=lambda row: row['fixture']['date'])
            rows = rows[:min(max(int(query['next']), 1), 50)]
    if query.get('league'):
        rows = [row for row in rows if str(query['league']).lower() in (row['league'].get('name') or '').lower()]
    return {'get': 'fixtures', 'parameters': query, 'errors': {}, 'results': len(rows), 'paging': {'current': 1, 'total': 1}, 'response': rows}


def _matchora_scores():
    base_url = current_app.config['MATCHORA_BASE_URL'].rstrip('/')
    payload = _fetch(f'{base_url}/api/v1/scores', {}, cache_seconds=20, enforce_daily=False)
    events = payload.get('events', []) if isinstance(payload, dict) else []
    rows = [{
        'id': int(event['id']) if str(event['id']).isdigit() else str(event['id']),
        'status': str(event.get('status') or 'NS').upper(),
        'minute': event.get('minute'),
        'score': event.get('score'),
        'live': bool(event.get('live')),
        'finished': bool(event.get('finished')),
    } for event in events if re.fullmatch(r'[A-Za-z0-9_-]+', str(event.get('id', '')))]
    return {'response': rows}


def _matchora_channels():
    base_url = current_app.config['MATCHORA_BASE_URL'].rstrip('/')
    payload = _fetch(f'{base_url}/api/v1/channels', {}, cache_seconds=3600, enforce_daily=False)
    channels = payload.get('channels', []) if isinstance(payload, dict) else []
    result = []
    for channel in channels:
        feeds = []
        for feed in channel.get('feeds', []):
            path = urlparse(feed.get('embed_url') or '').path
            prefix = '/embed/channel/'
            feed_id = path[len(prefix):] if path.startswith(prefix) else ''
            if not feed_id.isdigit():
                continue
            feeds.append({
                'id': int(feed_id),
                'label': feed.get('label') or channel.get('name'),
                'language': feed.get('language') or feed.get('lang') or channel.get('language') or channel.get('lang'),
                'country': feed.get('country'),
                'quality': feed.get('quality') or channel.get('quality'),
            })
        if feeds:
            result.append({
                'name': channel.get('name') or feeds[0]['label'],
                'countries': channel.get('countries') or [],
                'quality': channel.get('quality') or '',
                'featured': bool(channel.get('featured')),
                'feeds': feeds,
            })
    return {'count': len(result), 'channels': result}


def _matchora_competitions():
    base_url = current_app.config['MATCHORA_BASE_URL'].rstrip('/')
    url = f'{base_url}/api/v1/schedule?{urlencode({"watchable": 1})}'
    payload = _fetch(url, {}, enforce_daily=False)
    events = payload.get('events', []) if isinstance(payload, dict) else []
    unique = {}
    for event in events:
        if str(event.get('sport', '')).lower() not in ('soccer', 'football'):
            continue
        name = str(event.get('league') or '').strip()
        if name and name.casefold() not in unique:
            unique[name.casefold()] = {
                'league': {'id': None, 'name': name, 'type': 'League', 'logo': event.get('league_badge')},
                'country': {'name': None, 'code': None},
                'seasons': [],
            }
    return {'response': sorted(unique.values(), key=lambda row: row['league']['name'].casefold())}


def _matchora_replays(query):
    base_url = current_app.config['MATCHORA_BASE_URL'].rstrip('/')
    params = {key: query[key] for key in ('date', 'q', 'before') if query.get(key)}
    url = f'{base_url}/api/v1/replays'
    if params:
        url = f'{url}?{urlencode(params)}'
    payload = _fetch(url, {}, enforce_daily=False)
    source = payload.get('replays', []) if isinstance(payload, dict) else []
    replays = []
    for item in source:
        if str(item.get('sport', '')).lower() not in ('soccer', 'football') or not str(item.get('id', '')).isdigit():
            continue
        replays.append({
            'id': int(item['id']),
            'home': item.get('home'),
            'away': item.get('away'),
            'league': item.get('league'),
            'kickoff': item.get('kickoff'),
            'duration': item.get('duration'),
            'recordings': item.get('recordings', 0),
            'homeBadge': item.get('home_badge'),
            'awayBadge': item.get('away_badge'),
            'leagueBadge': item.get('league_badge'),
        })
    return {'count': payload.get('count', len(replays)), 'next': payload.get('next'), 'replays': replays}


def football_request(path, query=None):
    query = {key: value for key, value in (query or {}).items() if value not in (None, '')}
    provider = current_app.config['FOOTBALL_PROVIDER']
    if provider == 'matchora':
        if path == 'scores':
            return _matchora_scores()
        if path == 'channels':
            return _matchora_channels()
        if path == 'replays':
            return _matchora_replays(query)
        if path == 'leagues':
            return _matchora_competitions()
        if path == 'fixtures':
            return _matchora_fixtures(query)
        if path == 'statistics':
            return {'response': []}
        if path in ('teams', 'standings'):
            return {'response': []}
        raise _failure('Unsupported football data route.', 400)
    if provider == 'api-football':
        token = current_app.config['API_FOOTBALL_KEY']
        if not token:
            raise _failure('Football data is not configured. Set API_FOOTBALL_KEY in the backend environment.')
        endpoint = 'fixtures/statistics' if path == 'statistics' else path
        url = f"{current_app.config['API_FOOTBALL_BASE_URL'].rstrip('/')}/{endpoint}"
        params = urlencode(query)
        if params:
            url = f'{url}?{params}'
        payload = _fetch(url, {'x-apisports-key': token})
        return payload

    token = current_app.config['FOOTBALL_DATA_TOKEN']
    if not token:
        raise _failure('Football data is not configured. Set FOOTBALL_DATA_TOKEN in the backend environment.')
    params = {}
    if path == 'fixtures':
        if query.get('id'):
            endpoint = f"/matches/{query['id']}"
        else:
            endpoint = '/matches'
            if query.get('live'):
                params['status'] = 'IN_PLAY,PAUSED'
            elif query.get('date'):
                params['date'] = query['date']
            elif query.get('next'):
                params['dateFrom'] = datetime.now(timezone.utc).date().isoformat()
                params['dateTo'] = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
            elif query.get('dateFrom'):
                params['dateFrom'], params['dateTo'] = query['dateFrom'], query.get('dateTo')
            if query.get('league'):
                params['competitions'] = query['league']
            if query.get('team'):
                params['team'] = query['team']
    elif path == 'leagues':
        endpoint = f"/competitions/{query['id']}" if query.get('id') else '/competitions'
    elif path == 'teams':
        if query.get('id'):
            endpoint = f"/teams/{query['id']}"
        elif query.get('league'):
            endpoint = f"/competitions/{query['league']}/teams"
        else:
            endpoint = '/teams'
        if query.get('season'):
            params['season'] = query['season']
    elif path == 'standings':
        endpoint = f"/competitions/{query.get('league') or query.get('id')}/standings"
        if query.get('season'):
            params['season'] = query['season']
    elif path == 'statistics':
        return {'response': []}
    else:
        raise _failure('Unsupported football data route.', 400)
    url = f"{current_app.config['FOOTBALL_DATA_BASE_URL'].rstrip('/')}{endpoint}"
    if params:
        url = f'{url}?{urlencode(params)}'
    payload = _fetch(url, {'X-Auth-Token': token})
    response = _football_data_normalize(path, query, payload)
    return {'get': path, 'parameters': query, 'errors': {}, 'results': len(response), 'paging': {'current': 1, 'total': 1}, 'response': response}
