import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import jwt
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request, send_from_directory
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

if __package__:
    from .extensions import db, limiter, migrate
    from .football_provider import football_request
    from .models import Competition, Favourite, Match, RefreshSession, Stream, Team, User, utcnow
else:
    from extensions import db, limiter, migrate
    from football_provider import football_request
    from models import Competition, Favourite, Match, RefreshSession, Stream, Team, User, utcnow

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


def create_app(test_config=None):
    app = Flask(__name__)
    app_env = os.getenv('APP_ENV', 'development')
    client_url = os.getenv('CLIENT_URL', '')
    if not client_url and app_env != 'production':
        client_url = 'http://localhost:5173'
    if not client_url:
        vercel_host = os.getenv('VERCEL_PROJECT_PRODUCTION_URL') if os.getenv('VERCEL_ENV') == 'production' else os.getenv('VERCEL_URL')
        client_url = f'https://{vercel_host}' if vercel_host else ''
    app.config.update(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY', 'development-secret-change-this-value'),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', ''),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        MAX_CONTENT_LENGTH=32 * 1024,
        JWT_ACCESS_SECRET=os.getenv('JWT_ACCESS_SECRET', 'development-access-secret-change-this'),
        JWT_REFRESH_DAYS=int(os.getenv('REFRESH_TOKEN_DAYS', '30')),
        ACCESS_TOKEN_MINUTES=int(os.getenv('ACCESS_TOKEN_MINUTES', '15')),
        CLIENT_URL=client_url,
        API_FOOTBALL_KEY=os.getenv('API_FOOTBALL_KEY', ''),
        API_FOOTBALL_BASE_URL=os.getenv('API_FOOTBALL_BASE_URL', 'https://v3.football.api-sports.io'),
        FOOTBALL_PROVIDER=os.getenv('FOOTBALL_PROVIDER', 'matchora').lower(),
        MATCHORA_BASE_URL=os.getenv('MATCHORA_BASE_URL', 'https://matchora.pro'),
        FOOTBALL_DATA_TOKEN=os.getenv('FOOTBALL_DATA_TOKEN', ''),
        FOOTBALL_DATA_BASE_URL=os.getenv('FOOTBALL_DATA_BASE_URL', 'https://api.football-data.org/v4'),
        FOOTBALL_PROVIDER_RPM=int(os.getenv('FOOTBALL_PROVIDER_RPM', '30')),
        FOOTBALL_PROVIDER_DAILY_LIMIT=int(os.getenv('FOOTBALL_PROVIDER_DAILY_LIMIT', '90')),
        COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
        APP_ENV=app_env,
        RATELIMIT_STORAGE_URI=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError(
            'DATABASE_URL is not set. Copy backend/.env.example to backend/.env '
            'and configure it with the PostgreSQL credentials for your machine.'
        )
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith(('postgres://', 'postgresql://')):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql+psycopg://', 1).replace('postgresql://', 'postgresql+psycopg://', 1)
    if app.config['APP_ENV'] == 'production':
        if not app.config['SQLALCHEMY_DATABASE_URI'] or len(app.config['JWT_ACCESS_SECRET']) < 32 or len(app.config['SECRET_KEY']) < 32:
            raise RuntimeError('Production requires DATABASE_URL, FLASK_SECRET_KEY, and JWT_ACCESS_SECRET (32+ characters).')
        client_origin = urlparse(app.config['CLIENT_URL']) if app.config['CLIENT_URL'] else None
        if client_origin and (client_origin.scheme != 'https' or not client_origin.netloc or client_origin.hostname in ('localhost', '127.0.0.1')):
            raise RuntimeError('Production requires CLIENT_URL to be the public HTTPS frontend origin.')
        if not app.config['COOKIE_SECURE']:
            raise RuntimeError('Production requires COOKIE_SECURE=true.')
    CORS(app, origins=[app.config['CLIENT_URL']] if app.config['CLIENT_URL'] else [], supports_credentials=True)
    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(__file__), 'migrations'))
    limiter.init_app(app)

    @app.get('/api/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'goalstream-python'})

    def error(message, status=400):
        return jsonify({'error': message}), status

    def same_origin_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            origin = request.headers.get('Origin')
            if origin:
                allowed = {app.config['CLIENT_URL'].rstrip('/')} if app.config['CLIENT_URL'] else set()
                vercel_hosts = (os.getenv('VERCEL_URL'), os.getenv('VERCEL_PROJECT_PRODUCTION_URL'))
                allowed.update(f'https://{host}' for host in vercel_hosts if host)
                request_scheme = 'https' if app.config['APP_ENV'] == 'production' else request.scheme
                allowed.add(f'{request_scheme}://{request.host}'.rstrip('/'))
                if origin.rstrip('/') not in allowed:
                    return error('Request origin is not allowed.', 403)
            return fn(*args, **kwargs)
        return wrapped

    @app.after_request
    def security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if app.config['APP_ENV'] == 'production':
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    def serialize_user(user):
        return {'id': user.id, 'email': user.email, 'username': user.username, 'displayName': user.display_name, 'role': user.role}

    def sign_access(user):
        now = datetime.now(timezone.utc)
        return jwt.encode({'sub': str(user.id), 'iat': now, 'exp': now + timedelta(minutes=app.config['ACCESS_TOKEN_MINUTES']), 'iss': 'universal-ai'}, app.config['JWT_ACCESS_SECRET'], algorithm='HS256')

    def issue_refresh(user, response):
        raw = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(days=app.config['JWT_REFRESH_DAYS'])
        db.session.add(RefreshSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user=user, expires_at=expires))
        db.session.commit()
        response.set_cookie('refreshToken', raw, httponly=True, secure=app.config['COOKIE_SECURE'], samesite='None' if app.config['COOKIE_SECURE'] else 'Lax', path='/api/auth', expires=expires)

    def establish(user, status=200):
        response = make_response(jsonify({'user': serialize_user(user), 'accessToken': sign_access(user)}), status)
        issue_refresh(user, response)
        return response

    def auth_required(admin=False):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
                if not token:
                    return error('Authentication required', 401)
                try:
                    claims = jwt.decode(token, app.config['JWT_ACCESS_SECRET'], algorithms=['HS256'], issuer='universal-ai')
                    user = db.session.get(User, int(claims['sub']))
                except (jwt.PyJWTError, ValueError, KeyError):
                    return error('Session expired', 401)
                if not user:
                    return error('Authentication required', 401)
                if admin and user.role != 'ADMIN':
                    return error('Administrator access required', 403)
                request.current_user = user
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    @app.post('/api/auth/register')
    @limiter.limit('8 per minute')
    @same_origin_required
    def register():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get('email', '')).strip().lower()
        username = str(payload.get('username', '')).strip().lower()
        display_name = str(payload.get('displayName', '')).strip()
        password = payload.get('password', '')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or len(email) > 254:
            return error('Enter a valid email address')
        if not re.fullmatch(r'[a-z0-9_]{3,24}', username):
            return error('Username must be 3–24 characters using letters, numbers, or underscores')
        if not isinstance(password, str) or len(password) < 8 or len(password) > 72:
            return error('Password must contain 8–72 characters')
        if not display_name or len(display_name) > 80:
            return error('Display name must contain 1–80 characters')
        if User.query.filter(or_(User.email == email, User.username == username)).first():
            return error('Email or username is already in use', 409)
        user = User(email=email, username=username, display_name=display_name, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        return establish(user, 201)

    @app.post('/api/auth/login')
    @limiter.limit('12 per minute')
    @same_origin_required
    def login():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get('email', '')).strip().lower()
        password = payload.get('password', '')
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password if isinstance(password, str) else ''):
            return error('Invalid email or password', 401)
        return establish(user)

    @app.post('/api/auth/google')
    def google_auth_unavailable():
        return error('Google sign-in is not configured for the Flask backend. Use email and password.', 503)

    @app.post('/api/auth/refresh')
    @same_origin_required
    def refresh():
        raw = request.cookies.get('refreshToken')
        if not raw:
            return error('Session expired', 401)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        session = RefreshSession.query.filter_by(token_hash=token_hash).first()
        expires_at = session.expires_at if session and session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc) if session else None
        if not session or expires_at <= datetime.now(timezone.utc):
            if session:
                db.session.delete(session)
                db.session.commit()
            response = make_response(jsonify({'error': 'Session expired'}), 401)
            response.delete_cookie('refreshToken', path='/api/auth')
            return response
        user = session.user
        db.session.delete(session)
        db.session.flush()
        return establish(user)

    @app.post('/api/auth/logout')
    @same_origin_required
    def logout():
        raw = request.cookies.get('refreshToken')
        if raw:
            token_hash = hashlib.sha256(raw.encode()).hexdigest()
            RefreshSession.query.filter_by(token_hash=token_hash).delete()
            db.session.commit()
        response = make_response('', 204)
        response.delete_cookie('refreshToken', path='/api/auth')
        return response

    @app.get('/api/auth/me')
    @app.get('/api/auth/profile')
    @auth_required()
    def profile():
        return jsonify({'user': serialize_user(request.current_user)})

    def stream_active_query(match_id=None):
        now = datetime.now(timezone.utc)
        query = Stream.query.filter(Stream.available.is_(True), or_(Stream.starts_at.is_(None), Stream.starts_at <= now), or_(Stream.ends_at.is_(None), Stream.ends_at > now))
        if match_id is not None:
            query = query.filter_by(match_external_id=match_id)
        return query

    def stream_json(stream, include_admin_fields=False):
        result = {'id': stream.id, 'matchId': stream.match_external_id, 'competition': stream.competition, 'url': stream.url, 'type': stream.stream_type, 'provider': stream.provider, 'geographicRestrictions': stream.geographic_restrictions or [], 'available': stream.available, 'startsAt': stream.starts_at.isoformat() if stream.starts_at else None, 'endsAt': stream.ends_at.isoformat() if stream.ends_at else None}
        if include_admin_fields:
            result['authorizationReference'] = stream.authorization_reference
        return result

    @app.get('/api/football/fixtures')
    @app.get('/api/matches')
    @limiter.limit('60 per minute')
    def matches():
        query = {key: request.args.get(key) for key in ('date', 'league', 'team', 'season') if request.args.get(key)}
        return jsonify(football_request('fixtures', query))

    @app.get('/api/matches/scores')
    @limiter.limit('60 per minute')
    def match_scores():
        if app.config['FOOTBALL_PROVIDER'] == 'matchora':
            return jsonify(football_request('scores'))
        data = football_request('fixtures', {'live': 'all'})
        rows = []
        for match in data.get('response', []):
            fixture = match.get('fixture', {})
            goals = match.get('goals') or {}
            home, away = goals.get('home'), goals.get('away')
            rows.append({
                'id': fixture.get('id'),
                'status': (fixture.get('status') or {}).get('short', 'NS'),
                'minute': (fixture.get('status') or {}).get('elapsed'),
                'score': f'{home}-{away}' if home is not None and away is not None else None,
                'live': True,
                'finished': False,
            })
        return jsonify({'response': rows})

    @app.get('/api/matches/live')
    @limiter.limit('60 per minute')
    def live_matches():
        return jsonify(football_request('fixtures', {'live': 'all'}))

    @app.get('/api/matches/upcoming')
    @limiter.limit('60 per minute')
    def upcoming_matches():
        limit = min(max(request.args.get('limit', 20, type=int), 1), 50)
        return jsonify(football_request('fixtures', {'next': limit}))

    @app.get('/api/matches/<match_id>')
    @limiter.limit('60 per minute')
    def match_details(match_id):
        match = football_request('fixtures', {'id': match_id})
        stats = football_request('statistics', {'fixture': match_id})
        payload = dict(match)
        # Flask captures this route parameter as text. Cast numeric provider IDs
        # before comparing against Stream.match_external_id (an integer column).
        local_match_id = int(match_id) if str(match_id).isdecimal() else None
        payload['streams'] = [stream_json(s) for s in stream_active_query(local_match_id).all()] if local_match_id is not None else []
        payload['statistics'] = stats.get('response', [])
        return jsonify(payload)

    @app.get('/api/football/fixtures/<match_id>')
    @limiter.limit('60 per minute')
    def football_match_details(match_id):
        return jsonify(football_request('fixtures', {'id': match_id}))

    @app.get('/api/football/competitions')
    @app.get('/api/competitions')
    @limiter.limit('60 per minute')
    def competitions():
        return jsonify(football_request('leagues'))

    @app.get('/api/channels')
    @limiter.limit('30 per minute')
    def channel_catalog():
        if app.config['FOOTBALL_PROVIDER'] != 'matchora':
            return jsonify({'count': 0, 'channels': []})
        return jsonify(football_request('channels'))

    @app.get('/api/replays')
    @limiter.limit('30 per minute')
    def replays():
        if app.config['FOOTBALL_PROVIDER'] != 'matchora':
            return jsonify({'count': 0, 'next': None, 'replays': []})
        query = {key: request.args.get(key) for key in ('date', 'q', 'before') if request.args.get(key)}
        return jsonify(football_request('replays', query))

    @app.get('/api/football/competitions/<int:competition_id>')
    @app.get('/api/competitions/<int:competition_id>')
    def competition_details(competition_id):
        return jsonify(football_request('leagues', {'id': competition_id}))

    @app.get('/api/football/teams')
    @app.get('/api/teams')
    def teams():
        query = {key: request.args.get(key) for key in ('league', 'season', 'search') if request.args.get(key)}
        return jsonify(football_request('teams', query))

    @app.get('/api/football/teams/<int:team_id>')
    @app.get('/api/teams/<int:team_id>')
    def team_details(team_id):
        return jsonify(football_request('teams', {'id': team_id}))

    @app.get('/api/football/standings')
    def standings():
        query = {key: request.args.get(key) for key in ('league', 'season') if request.args.get(key)}
        return jsonify(football_request('standings', query))

    @app.get('/api/streams')
    @limiter.limit('60 per minute')
    def streams():
        data = football_request('fixtures', {'live': 'all'})
        live_matches = data.get('response', [])
        live_ids = {row.get('fixture', {}).get('id') for row in live_matches}
        authorized = [stream_json(s) for s in stream_active_query().all() if s.match_external_id in live_ids]
        if app.config['FOOTBALL_PROVIDER'] == 'matchora':
            matchora = [{
                'id': f"matchora-{row['fixture']['id']}",
                'matchId': row['fixture']['id'],
                'competition': row['league']['name'],
                'provider': 'Matchora',
                'type': 'MATCHORA',
                'channelCount': row.get('channelCount', 0),
                'embedUrl': row.get('embedUrl'),
                'channels': row.get('channels') or [],
                'home': row['teams']['home']['name'],
                'away': row['teams']['away']['name'],
                'homeBadge': row['teams']['home'].get('logo'),
                'awayBadge': row['teams']['away'].get('logo'),
                'score': row.get('goals') or {},
                'minute': (row.get('fixture', {}).get('status') or {}).get('elapsed'),
            } for row in live_matches if row.get('hasMatchEmbed')]
            return jsonify(matchora + authorized)
        return jsonify(authorized)

    @app.get('/api/streams/<int:stream_id>')
    def stream_details(stream_id):
        stream = stream_active_query().filter_by(id=stream_id).first()
        return jsonify(stream_json(stream)) if stream else error('Authorized stream not found or unavailable', 404)

    @app.get('/api/matches/<int:match_id>/streams')
    def match_streams(match_id):
        return jsonify([stream_json(s) for s in stream_active_query(match_id).all()])

    @app.get('/api/favourites')
    @auth_required()
    def list_favourites():
        rows = Favourite.query.filter_by(user_id=request.current_user.id).order_by(Favourite.created_at.desc()).all()
        result = []
        for row in rows:
            team = row.team
            comp = row.competition
            result.append({'id': row.id, 'targetType': row.target_type, 'targetId': row.target_external_id,
                           'team': {'id': team.id, 'externalId': team.external_id, 'name': team.name, 'logoUrl': team.logo_url} if team else None,
                           'competition': {'id': comp.id, 'externalId': comp.external_id, 'name': comp.name, 'logoUrl': comp.logo_url} if comp else None})
        return jsonify(result)

    @app.post('/api/favourites')
    @auth_required()
    def create_favourite():
        payload = request.get_json(silent=True) or {}
        kind = payload.get('targetType')
        external_id = payload.get('targetId')
        if kind not in ('team', 'competition') or not isinstance(external_id, int) or external_id < 1:
            return error('targetType and positive integer targetId are required')
        user = request.current_user
        existing = Favourite.query.filter_by(user_id=user.id, target_type=kind, target_external_id=external_id).first()
        if existing:
            return jsonify({'id': existing.id, 'targetType': kind, 'targetId': external_id}), 200
        data = football_request('teams' if kind == 'team' else 'leagues', {'id': external_id})
        row = (data.get('response') or [None])[0]
        entity = row.get('team') if row and kind == 'team' else row.get('league') if row else None
        if not entity:
            return error(f'{kind.title()} was not found', 404)
        if kind == 'team':
            item = Team.query.filter_by(external_id=external_id).first()
            if not item:
                item = Team(external_id=external_id, name=entity['name'], country=entity.get('country'), logo_url=entity.get('logo'))
                db.session.add(item)
                db.session.flush()
            favourite = Favourite(user=user, target_type=kind, target_external_id=external_id, team=item)
        else:
            item = Competition.query.filter_by(external_id=external_id).first()
            if not item:
                country = (row.get('country') or {}).get('name')
                item = Competition(external_id=external_id, name=entity['name'], country=country, logo_url=entity.get('logo'))
                db.session.add(item)
                db.session.flush()
            favourite = Favourite(user=user, target_type=kind, target_external_id=external_id, competition=item)
        db.session.add(favourite)
        db.session.commit()
        return jsonify({'id': favourite.id, 'targetType': kind, 'targetId': external_id}), 201

    @app.delete('/api/favourites/<int:favourite_id>')
    @auth_required()
    def remove_favourite(favourite_id):
        favourite = Favourite.query.filter_by(id=favourite_id, user_id=request.current_user.id).first()
        if not favourite:
            return error('Favourite not found', 404)
        db.session.delete(favourite)
        db.session.commit()
        return '', 204

    def parse_datetime(value, field):
        if value in (None, ''):
            return None
        if not isinstance(value, str):
            raise ValueError(f'{field} must be an ISO date/time')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def admin_stream_payload(payload, partial=False):
        result = {}
        aliases = {'matchId': 'match_external_id', 'type': 'stream_type', 'authorizationReference': 'authorization_reference', 'geographicRestrictions': 'geographic_restrictions', 'startsAt': 'starts_at', 'endsAt': 'ends_at'}
        required = {'matchId', 'competition', 'url', 'type', 'provider', 'authorizationReference'}
        if not partial and not required.issubset(payload):
            raise ValueError('Match, competition, URL, type, provider, and authorization reference are required')
        allowed = required | {'geographicRestrictions', 'available', 'startsAt', 'endsAt'}
        for key, value in payload.items():
            if key not in allowed:
                raise ValueError(f'Unknown stream field: {key}')
            if key == 'matchId':
                if not isinstance(value, int) or value < 1: raise ValueError('matchId must be a positive integer')
            if key in ('competition', 'provider', 'authorizationReference') and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f'{key} must be a non-empty string')
            if key == 'url':
                parsed = urlparse(value) if isinstance(value, str) else None
                if not parsed or parsed.scheme != 'https' or not parsed.netloc: raise ValueError('Stream URL must use HTTPS')
            if key == 'type' and value not in ('HLS', 'LINK'): raise ValueError('type must be HLS or LINK')
            if key == 'available' and not isinstance(value, bool): raise ValueError('available must be boolean')
            if key == 'geographicRestrictions' and (not isinstance(value, list) or any(not isinstance(item, str) for item in value)):
                raise ValueError('geographicRestrictions must be a list of strings')
            result[aliases.get(key, key)] = parse_datetime(value, key) if key in ('startsAt', 'endsAt') else value
        if result.get('starts_at') and result.get('ends_at') and result['ends_at'] <= result['starts_at']:
            raise ValueError('endsAt must be after startsAt')
        return result

    @app.get('/api/admin/dashboard')
    @auth_required(admin=True)
    def admin_dashboard():
        now = datetime.now(timezone.utc)
        active = Stream.query.filter_by(available=True).filter(or_(Stream.starts_at.is_(None), Stream.starts_at <= now), or_(Stream.ends_at.is_(None), Stream.ends_at > now)).count()
        return jsonify({'users': User.query.count(), 'teams': Team.query.count(), 'competitions': Competition.query.count(), 'matches': Match.query.count(), 'streams': Stream.query.count(), 'activeStreams': active})

    @app.get('/api/admin/users')
    @auth_required(admin=True)
    def admin_users():
        users = User.query.order_by(User.created_at.desc()).limit(100).all()
        return jsonify([{'id': u.id, 'email': u.email, 'username': u.username, 'displayName': u.display_name, 'role': u.role, 'createdAt': u.created_at.isoformat()} for u in users])

    @app.put('/api/admin/users/<int:user_id>/role')
    @auth_required(admin=True)
    def admin_user_role(user_id):
        payload = request.get_json(silent=True) or {}
        role = payload.get('role')
        user = db.session.get(User, user_id)
        if not user: return error('User not found', 404)
        if role not in ('USER', 'ADMIN'): return error('Role must be USER or ADMIN')
        if user.role == 'ADMIN' and role == 'USER' and User.query.filter_by(role='ADMIN').count() <= 1:
            return error('At least one administrator must remain.', 409)
        user.role = role
        db.session.commit()
        return jsonify({'id': user.id, 'email': user.email, 'role': user.role})

    @app.get('/api/admin/streams')
    @auth_required(admin=True)
    def admin_streams():
        return jsonify([stream_json(s, include_admin_fields=True) for s in Stream.query.order_by(Stream.updated_at.desc()).limit(200).all()])

    @app.post('/api/admin/streams')
    @auth_required(admin=True)
    def create_stream():
        payload = request.get_json(silent=True) or {}
        try:
            values = admin_stream_payload(payload)
            fixture_data = football_request('fixtures', {'id': values['match_external_id']})
            fixture = (fixture_data.get('response') or [None])[0]
            if not fixture: return error('Match not found in the configured football data provider', 404)
            fixture_id = fixture.get('fixture', {}).get('id')
            if fixture_id != values['match_external_id']:
                return error('Match provider ID mismatch', 400)
            league, teams, goals = fixture.get('league', {}), fixture.get('teams', {}), fixture.get('goals', {})
            row = Match.query.filter_by(external_id=fixture_id).first()
            kickoff = parse_datetime(fixture.get('fixture', {}).get('date'), 'fixture date')
            if not row:
                row = Match(external_id=fixture_id, kickoff_at=kickoff)
                db.session.add(row)
            row.competition_id = league.get('id'); row.home_team_id = teams.get('home', {}).get('id'); row.away_team_id = teams.get('away', {}).get('id')
            row.kickoff_at = kickoff; row.status = fixture.get('fixture', {}).get('status', {}).get('short', 'NS')
            row.home_score = goals.get('home'); row.away_score = goals.get('away')
            stream = Stream(**values)
            db.session.add(stream)
            db.session.commit()
            return jsonify(stream_json(stream, include_admin_fields=True)), 201
        except ValueError as exc:
            db.session.rollback()
            return error(str(exc))

    @app.put('/api/admin/streams/<int:stream_id>')
    @auth_required(admin=True)
    def update_stream(stream_id):
        stream = db.session.get(Stream, stream_id)
        if not stream: return error('Stream not found', 404)
        try:
            values = admin_stream_payload(request.get_json(silent=True) or {}, partial=True)
            for key, value in values.items(): setattr(stream, key, value)
            db.session.commit()
            return jsonify(stream_json(stream, include_admin_fields=True))
        except ValueError as exc:
            db.session.rollback()
            return error(str(exc))

    @app.delete('/api/admin/streams/<int:stream_id>')
    @auth_required(admin=True)
    def delete_stream(stream_id):
        stream = db.session.get(Stream, stream_id)
        if not stream: return error('Stream not found', 404)
        db.session.delete(stream); db.session.commit()
        return '', 204

    def catalog_data(payload, partial=False):
        allowed = {'externalId', 'name', 'country', 'logoUrl'}
        if not partial and not {'externalId', 'name'}.issubset(payload): raise ValueError('externalId and name are required')
        values = {}
        for key, value in payload.items():
            if key not in allowed: raise ValueError(f'Unknown catalog field: {key}')
            if key == 'externalId':
                if not isinstance(value, int) or value < 1: raise ValueError('externalId must be a positive integer')
                values['external_id'] = value
            elif key == 'name':
                if not isinstance(value, str) or not value.strip() or len(value) > 120: raise ValueError('name must contain 1–120 characters')
                values['name'] = value.strip()
            elif key == 'country': values['country'] = value or None
            elif key == 'logoUrl': values['logo_url'] = value or None
        return values

    def admin_catalog(model, label):
        @app.get(f'/api/admin/{label}', endpoint=f'admin_{label}_list')
        @auth_required(admin=True)
        def list_catalog():
            rows = model.query.order_by(model.name.asc()).limit(500).all()
            return jsonify([{'id': row.id, 'externalId': row.external_id, 'name': row.name, 'country': row.country, 'logoUrl': row.logo_url} for row in rows])

        @app.post(f'/api/admin/{label}', endpoint=f'admin_{label}_add')
        @auth_required(admin=True)
        def add_catalog():
            try:
                row = model(**catalog_data(request.get_json(silent=True) or {}))
                db.session.add(row); db.session.commit()
                return jsonify({'id': row.id, 'externalId': row.external_id, 'name': row.name, 'country': row.country, 'logoUrl': row.logo_url}), 201
            except ValueError as exc:
                db.session.rollback(); return error(str(exc))

        @app.put(f'/api/admin/{label}/<int:row_id>', endpoint=f'admin_{label}_edit')
        @auth_required(admin=True)
        def edit_catalog(row_id):
            row = db.session.get(model, row_id)
            if not row: return error(f'{label.title()} entry not found', 404)
            try:
                for key, value in catalog_data(request.get_json(silent=True) or {}, partial=True).items(): setattr(row, key, value)
                db.session.commit()
                return jsonify({'id': row.id, 'externalId': row.external_id, 'name': row.name, 'country': row.country, 'logoUrl': row.logo_url})
            except ValueError as exc:
                db.session.rollback(); return error(str(exc))

        @app.delete(f'/api/admin/{label}/<int:row_id>', endpoint=f'admin_{label}_delete')
        @auth_required(admin=True)
        def delete_catalog(row_id):
            row = db.session.get(model, row_id)
            if not row: return error(f'{label.title()} entry not found', 404)
            db.session.delete(row); db.session.commit(); return '', 204
        return list_catalog, add_catalog, edit_catalog, delete_catalog

    admin_catalog(Competition, 'competitions')
    admin_catalog(Team, 'teams')

    # Serve the Vite build for browser routes so direct navigation and reloads
    # work when the app is hosted by Flask (for example, with `npm start`).
    frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'client', 'dist'))

    @app.get('/')
    def frontend_index():
        return send_from_directory(frontend_dist, 'index.html')

    @app.get('/<path:frontend_path>')
    def frontend_routes(frontend_path):
        if frontend_path.startswith('api/'):
            return error('Not found', 404)
        requested_file = os.path.join(frontend_dist, frontend_path)
        if os.path.isfile(requested_file):
            return send_from_directory(frontend_dist, frontend_path)
        return send_from_directory(frontend_dist, 'index.html')

    @app.errorhandler(404)
    def not_found(_exc):
        return error('Not found', 404)

    @app.errorhandler(429)
    def too_many(_exc):
        return error('Request limit reached. Try again shortly.', 429)

    @app.errorhandler(Exception)
    def internal_error(exc):
        if isinstance(exc, HTTPException):
            return error(exc.description, exc.code or 500)
        status = getattr(exc, 'status_code', 500)
        if status >= 500:
            app.logger.exception('Unhandled application error', exc_info=exc)
            return error('Something went wrong', 500)
        return error(str(exc), status)

    return app


app = create_app()
