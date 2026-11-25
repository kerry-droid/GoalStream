import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Bell, CalendarDays, ChevronRight, Clock3, Goal, Home, Radio, Search, Shield, Star, Trophy, Users, X } from 'lucide-react';
import { api } from '../api.js';
import { reminderToggled, teamFollowed } from '../store.js';

const leagues = ['All matches', 'Premier League', 'Champions League', 'Europa League', 'La Liga', 'Serie A'];
const sampleFixtures = [
  { id: 'demo-1', league: 'Premier League', time: '19:30', home: 'Arsenal', away: 'Chelsea', homeBadge: 'ARS', awayBadge: 'CHE', offset: 7 * 60 + 37 },
  { id: 'demo-2', league: 'Champions League', time: '21:00', home: 'Real Madrid', away: 'Bayern Munich', homeBadge: 'RMA', awayBadge: 'BAY', offset: 9 * 60 + 7 },
  { id: 'demo-3', league: 'La Liga', time: '20:00', home: 'Barcelona', away: 'Atlético Madrid', homeBadge: 'BAR', awayBadge: 'ATM', offset: 8 * 60 + 7 },
];
const initials = name => String(name || 'FC').split(/\s+/).map(part => part[0]).join('').slice(0, 3).toUpperCase();
const isKenyaLeague = name => /(kenyan|kenya premier|fkf premier)/i.test(String(name || ''));
const kickoffAt = fixture => { const [hours, minutes] = fixture.time.split(':').map(Number); const date = new Date(); date.setHours(hours, minutes, 0, 0); if (date <= new Date()) date.setDate(date.getDate() + 1); return date; };

function Crest({ label }) { return <span className="gs-crest" aria-hidden="true">{label}</span>; }
function countdown(date, now) { const remaining = date - now; if (!Number.isFinite(remaining)) return 'Kick-off time unavailable'; if (remaining <= 0) return 'Kick-off passed'; const mins = Math.floor(remaining / 60000); return `Starts in ${Math.floor(mins / 60)}h ${mins % 60}m`; }

export default function Dashboard() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const reminders = useSelector(state => state.football.reminders);
  const [filter, setFilter] = useState('All matches');
  const [query, setQuery] = useState('');
  const [fixtures, setFixtures] = useState([]);
  const [liveMatches, setLiveMatches] = useState([]);
  const [liveLoading, setLiveLoading] = useState(true);
  const [now, setNow] = useState(Date.now());
  const [mobileSearch, setMobileSearch] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let active = true;
    api('/matches').then(data => { if (active && data.response?.length) setFixtures(data.response); }).catch(() => {});
    const refreshLive = () => api('/streams').then(streams => {
      if (!active) return;
      const playable = (streams || []).map(stream => ({
        stream,
        fixture: { id: stream.matchId, status: { elapsed: stream.minute } },
        league: { name: stream.competition || 'Live football' },
        teams: { home: { name: stream.home || 'Home' }, away: { name: stream.away || 'Away' } },
        goals: stream.score || {},
      }));
      setLiveMatches(playable);
      if (playable.length) api('/matches/live').then(data => {
        if (!active) return;
        const rows = data.response || [];
        setLiveMatches(current => current.map(match => {
          const source = rows.find(row => String(row.fixture?.id) === String(match.fixture?.id));
          return source ? { ...source, stream: match.stream, fixture: { ...source.fixture, status: { ...source.fixture?.status, elapsed: match.fixture?.status?.elapsed } } } : match;
        }));
      }).catch(() => {});
    }).catch(() => { if (active) setLiveMatches([]); }).finally(() => { if (active) setLiveLoading(false); });
    refreshLive(); const liveTimer = setInterval(refreshLive, 60000);
    const tick = setInterval(() => setNow(Date.now()), 30000);
    return () => { active = false; clearInterval(tick); clearInterval(liveTimer); };
  }, []);
  const shownFixtures = useMemo(() => {
    const source = fixtures.length ? fixtures.filter(m => !isKenyaLeague(m.league?.name)).map(m => ({ id: m.fixture?.id, league: m.league?.name || 'Football', time: new Date(m.fixture?.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }), home: m.teams?.home?.name, away: m.teams?.away?.name, homeBadge: initials(m.teams?.home?.name), awayBadge: initials(m.teams?.away?.name), status: m.fixture?.status?.short, hasMatchEmbed: m.hasMatchEmbed, score: m.goals, real: true })) : sampleFixtures;
    return source.filter(m => (filter === 'All matches' || m.league.toLowerCase().includes(filter.toLowerCase().replace('champions league', 'champions league').replace('europa league', 'europa league'))) && (!query || `${m.home} ${m.away} ${m.league}`.toLowerCase().includes(query.toLowerCase())));
  }, [fixtures, filter, query]);
  const openMatch = (id, fixture = null) => navigate(`/match/${id}`, { state: { fixture } });
  const navItems = [['Home', '/', Home], ['Live TV', '/live', Radio], ['Fixtures', '/fixtures', CalendarDays], ['Competitions', '/competitions', Trophy], ['My Teams', '/my-teams', Users]];
  const saveTeams = fixture => {
    const teams = [{ name: fixture.home, badge: fixture.homeBadge }, { name: fixture.away, badge: fixture.awayBadge }];
    teams.forEach(team => dispatch(teamFollowed(team)));
    setNotice('Teams added to My Teams.'); window.setTimeout(() => setNotice(''), 2200);
  };
  const toggleReminder = id => { dispatch(reminderToggled(id)); setNotice(reminders.includes(id) ? 'Reminder removed.' : 'Match reminder set.'); setTimeout(() => setNotice(''), 2200); };
  const featuredLive = liveMatches[0];
  const liveScore = match => match?.goals?.home != null && match?.goals?.away != null ? `${match.goals.home} : ${match.goals.away}` : '– : –';

  return <div className="goal-app">
    <header className="goal-topbar">
      <Link to="/" className="goal-wordmark" aria-label="GoalStream home"><Goal size={23}/><span>GOAL<span>STREAM</span></span></Link>
      <nav className="goal-desktop-nav" aria-label="Main navigation">{navItems.map(([name, href, Icon]) => <Link key={href} to={href} className={href === '/' ? 'active' : ''} aria-current={href === '/' ? 'page' : undefined}><Icon size={18}/>{name}{name === 'Live TV' && <span className="nav-live">{liveMatches.length > 0 && <i/>}{liveMatches.length} live</span>}</Link>)}</nav>
      <label className={`goal-search ${mobileSearch ? 'search-open' : ''}`}><span className="search-label">Search teams or leagues</span><Search size={18}/><input aria-label="Search teams or leagues" placeholder="Search teams or leagues" value={query} onChange={e => setQuery(e.target.value)}/></label>
      <button className="goal-search-mobile" aria-label="Search teams or leagues" onClick={() => setMobileSearch(v => !v)}>{mobileSearch ? <X/> : <Search/>}</button>
    </header>
    <main className="goal-content">
      <div className="goal-section-heading"><div><p className="goal-eyebrow">{new Date().toLocaleDateString([], { weekday: 'long' }).toUpperCase()} · MATCHDAY</p><h1>The game is on.</h1></div><div className="goal-date"><CalendarDays size={17}/>{new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}</div></div>
      <section className="goal-hero-row" aria-label="Featured live matches">
        <article className="goal-featured-live">
          {featuredLive ? <><div className="goal-feature-top"><span className="goal-live-pill"><i/> LIVE&nbsp; {featuredLive.fixture?.status?.elapsed ? `${featuredLive.fixture.status.elapsed}'` : ''}</span><span className="goal-league">{featuredLive.league?.name || 'Live football'}{featuredLive.league?.round ? ` · ${featuredLive.league.round}` : ''}</span><span className="goal-photo-slot" aria-label="Licensed team photography placeholder"><Shield size={19}/> Licensed photo</span></div><button className="goal-scoreboard" onClick={() => openMatch(featuredLive.fixture?.id, featuredLive)} aria-label={`Open live match ${featuredLive.teams?.home?.name} versus ${featuredLive.teams?.away?.name}`}><span className="goal-live-team"><Crest label={initials(featuredLive.teams?.home?.name)}/><b>{featuredLive.teams?.home?.name}</b></span><strong className="goal-score">{featuredLive.goals?.home ?? '–'} <i>:</i> {featuredLive.goals?.away ?? '–'}</strong><span className="goal-live-team"><Crest label={initials(featuredLive.teams?.away?.name)}/><b>{featuredLive.teams?.away?.name}</b></span></button><div className="goal-feature-actions"><button className="goal-button-lime" onClick={() => openMatch(featuredLive.fixture?.id, featuredLive)}><Radio size={17}/>Watch live</button><button className="goal-button-outline" onClick={() => openMatch(featuredLive.fixture?.id, featuredLive)}>Match centre <ChevronRight size={17}/></button><span className="goal-venue">{featuredLive.fixture?.venue?.name || featuredLive.league?.country || 'Live now'}</span></div></> : <div className="goal-no-live"><Radio size={28}/><h2>{liveLoading ? 'Checking live matches…' : 'No matches live right now'}</h2><p>{liveLoading ? 'Loading Matchora live events.' : 'Browse the schedule or catch up on a replay.'}</p><button className="goal-button-lime" onClick={() => navigate('/live')}>{liveLoading ? 'Open Live TV' : 'Open Live TV'}<ChevronRight size={17}/></button></div>}
        </article>
        <aside className="goal-live-panel"><div className="goal-panel-head"><div><p className="goal-eyebrow">HAPPENING NOW</p><h2>Live now</h2></div><span className="goal-live-count">{liveMatches.length} {liveMatches.length === 1 ? 'match' : 'matches'}</span></div>{liveMatches.slice(1).length ? liveMatches.slice(1).map(match => <button className="goal-live-row" key={match.fixture?.id} onClick={() => openMatch(match.fixture?.id, match)}><span className="goal-live-row-meta"><span>{match.league?.name || 'Live match'}</span><b>{match.fixture?.status?.elapsed ? `${match.fixture.status.elapsed}'` : 'LIVE'}</b></span><span className="goal-live-row-teams"><span><Crest label={initials(match.teams?.home?.name)}/>{match.teams?.home?.name}</span><strong>{liveScore(match)}</strong></span><span className="goal-live-row-teams"><span><Crest label={initials(match.teams?.away?.name)}/>{match.teams?.away?.name}</span><span className="goal-live-watch">Watch <ChevronRight size={15}/></span></span></button>) : <div className="goal-no-other-live">{liveMatches.length ? 'This is the only live match.' : liveLoading ? 'Checking Matchora…' : 'No other live matches.'}</div>}</aside>
      </section>
      <section className="goal-matches-section" id="today-matches">
        <div className="goal-match-title"><div><p className="goal-eyebrow">PLAN YOUR MATCHDAY</p><h2>Today's matches</h2></div><span>{new Date().toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}</span></div>
        <div className="goal-league-tabs" role="tablist" aria-label="Filter by league">{leagues.map(league => <button role="tab" aria-selected={filter === league} className={filter === league ? 'selected' : ''} key={league} onClick={() => setFilter(league)}>{league}</button>)}</div>
        <div className="goal-fixture-grid">{shownFixtures.map(fixture => {
          const time = fixture.real ? new Date(fixtures.find(m => String(m.fixture?.id) === String(fixture.id))?.fixture?.date) : kickoffAt(fixture);
          const finished = ['FT', 'AET', 'PEN'].includes(fixture.status);
          const replayAvailable = finished && fixture.hasMatchEmbed;
          const live = ['1H', '2H', 'HT', 'ET', 'BT', 'P'].includes(fixture.status);
          return <article className="goal-fixture-card" key={fixture.id}><div className="goal-fixture-league"><span>{fixture.league}</span>{replayAvailable && <span className="goal-replay-tag">REPLAY</span>}{live && <span className="goal-live-pill"><i/> LIVE</span>}<span className="goal-card-time"><Clock3 size={15}/>{fixture.time}</span></div><button className="goal-fixture-teams" onClick={() => openMatch(fixture.id, fixture)} aria-label={`Open ${fixture.home} versus ${fixture.away}`}><span className="goal-fixture-team"><Crest label={fixture.homeBadge}/><b>{fixture.home}</b></span><span className="goal-vs">{fixture.score?.home != null ? `${fixture.score.home} : ${fixture.score.away}` : 'VS'}</span><span className="goal-fixture-team"><Crest label={fixture.awayBadge}/><b>{fixture.away}</b></span></button><div className="goal-fixture-footer">{replayAvailable ? <button className="goal-button-lime goal-replay-button" onClick={() => openMatch(fixture.id, fixture)}><Radio size={16}/>Watch replay</button> : <><span>{live ? 'Match in progress' : finished ? 'Full time' : countdown(time, now)}</span><div className="goal-card-actions"><button className="goal-follow" aria-label={`Follow ${fixture.home} and ${fixture.away}`} title="Add both teams to My Teams" onClick={() => saveTeams(fixture)}><Star size={17}/></button>{!finished && <button className={reminders.includes(fixture.id) ? 'reminder-set' : ''} aria-label={`${reminders.includes(fixture.id) ? 'Remove' : 'Set'} reminder for ${fixture.home} versus ${fixture.away}`} title="Set reminder" onClick={() => toggleReminder(fixture.id)}><Bell size={18}/></button>}</div></>}</div></article>;
        })}</div>
        {!shownFixtures.length && <div className="goal-empty">No matches match this filter. Try another league or search.</div>}
      </section>
    </main>
    {notice && <div className="goal-toast" role="status">{notice}</div>}
    <nav className="goal-mobile-tabs" aria-label="Mobile navigation">{[['Home', '/', Home], ['Live', '/live', Radio], ['Fixtures', '/fixtures', CalendarDays], ['My Teams', '/my-teams', Star]].map(([name, href, Icon]) => <Link key={href} to={href} className={href === '/' ? 'active' : ''}><span className="mobile-tab-icon"><Icon size={20}/>{name === 'Live' && <i/>}</span>{name}</Link>)}</nav>
  </div>;
}
