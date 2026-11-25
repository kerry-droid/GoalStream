import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BarChart3, Maximize2, Minimize2, ShieldCheck, Timer } from 'lucide-react';
import { api } from '../api.js';
import HlsPlayer from './HlsPlayer.jsx';
import MatchoraEmbed from './MatchoraEmbed.jsx';
import MatchoraChannelPicker, { bestMatchoraChannel } from './MatchoraChannelPicker.jsx';

const sample = { league: 'Premier League · Matchweek 28', home: 'Liverpool', away: 'Manchester City', homeScore: 2, awayScore: 1, minute: 67, events: [{ min: "67'", name: 'Mohamed Salah', type: 'Goal', team: 'Liverpool' }, { min: "52'", name: 'Phil Foden', type: 'Goal', team: 'Manchester City' }, { min: "31'", name: 'Darwin Núñez', type: 'Goal', team: 'Liverpool' }], stats: [['Possession', 54, 46], ['Shots', 12, 9], ['Corners', 6, 4]] };
export default function MatchDetails({ matchId: passedId, onBack }) {
  const params = useParams(); const location = useLocation(); const navigate = useNavigate(); const matchId = passedId || params.matchId; const fixture = location.state?.fixture;
  const [data, setData] = useState(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [tab, setTab] = useState('Timeline'); const [matchoraSelection, setMatchoraSelection] = useState(undefined); const [matchoraPlaying, setMatchoraPlaying] = useState(false); const [fullscreen, setFullscreen] = useState(false); const [controlsVisible, setControlsVisible] = useState(true); const [liveTimeline, setLiveTimeline] = useState([]); const matchoraPlayerRef = useRef(null); const lastScoreRef = useRef(null); const hideControlsTimer = useRef(null);
  useEffect(() => { let active = true; setLoading(true); setError(''); setMatchoraSelection(undefined); setMatchoraPlaying(false); setFullscreen(false); setLiveTimeline([]); lastScoreRef.current = null; if (String(matchId).startsWith('demo-')) { setData(null); setLoading(false); return () => { active = false; }; } api(`/matches/${matchId}`).then(result => { if (!active) return; const match = result.response?.[0]; if (!match) setError('This match is not available from the selected football provider.'); setData(match || null); }).catch(e => { if (active) setError(e.message || 'Match details could not be loaded.'); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [matchId]);
  useEffect(() => {
    if (data?.provider !== 'matchora') return undefined;
    const goals = data.goals || {};
    lastScoreRef.current = { matchId: String(matchId), home: Number(goals.home) || 0, away: Number(goals.away) || 0 };
    const timer = window.setInterval(async () => {
      try {
        const result = await api(`/matches/${matchId}`);
        const latest = result.response?.[0];
        if (!latest || String(latest.fixture?.id) !== String(matchId)) return;
        const previous = lastScoreRef.current;
        const current = { matchId: String(matchId), home: Number(latest.goals?.home) || 0, away: Number(latest.goals?.away) || 0 };
        if (previous?.matchId === current.matchId) {
          const minute = latest.fixture?.status?.elapsed ? `${latest.fixture.status.elapsed}'` : 'LIVE';
          const updates = [];
          for (let goal = previous.home; goal < current.home; goal += 1) updates.push({ id: `${matchId}-h-${goal + 1}-${Date.now()}-${goal}`, minute, type: 'Goal', team: latest.teams?.home?.name || 'Home team', text: 'Goal reported by Matchora' });
          for (let goal = previous.away; goal < current.away; goal += 1) updates.push({ id: `${matchId}-a-${goal + 1}-${Date.now()}-${goal}`, minute, type: 'Goal', team: latest.teams?.away?.name || 'Away team', text: 'Goal reported by Matchora' });
          if (updates.length) setLiveTimeline(items => [...updates, ...items]);
        }
        lastScoreRef.current = current;
        setData(currentData => currentData ? { ...currentData, ...latest, streams: currentData.streams || latest.streams || [], statistics: currentData.statistics || latest.statistics || [] } : currentData);
      } catch { /* Keep the last good live score if a refresh is temporarily unavailable. */ }
    }, 30000);
    return () => window.clearInterval(timer);
  }, [matchId, data?.provider]);
  useEffect(() => {
    const syncFullscreen = () => {
      const active = document.fullscreenElement === matchoraPlayerRef.current;
      setFullscreen(active);
      setControlsVisible(true);
      window.clearTimeout(hideControlsTimer.current);
      if (active) hideControlsTimer.current = window.setTimeout(() => setControlsVisible(false), 3200);
    };
    document.addEventListener('fullscreenchange', syncFullscreen);
    return () => { document.removeEventListener('fullscreenchange', syncFullscreen); window.clearTimeout(hideControlsTimer.current); };
  }, []);
  const goBack = () => onBack ? onBack() : navigate('/');
  const playMatchora = () => { setMatchoraSelection(current => current === undefined ? { channelId: bestMatchoraChannel(data?.channels)?.id ?? null, quality: 'AUTO' } : current); setMatchoraPlaying(true); };
  const toggleMatchoraFullscreen = async () => {
    const target = matchoraPlayerRef.current;
    if (!target) return;
    try {
      if (document.fullscreenElement === target) await document.exitFullscreen();
      else if (target.requestFullscreen) await target.requestFullscreen();
      else if (target.webkitRequestFullscreen) target.webkitRequestFullscreen();
    } catch { setError('Fullscreen is unavailable in this browser. The match is still playing in the player.'); }
  };
  const revealPlayerControls = () => {
    if (!document.fullscreenElement) return;
    setControlsVisible(true);
    window.clearTimeout(hideControlsTimer.current);
    hideControlsTimer.current = window.setTimeout(() => setControlsVisible(false), 3200);
  };
  if (loading) return <div className="goal-match-page"><button className="goal-back" onClick={goBack}><ArrowLeft size={18}/>All matches</button><div className="goal-player-loading">Loading match details…</div></div>;
  if (error) return <div className="goal-match-page"><button className="goal-back" onClick={goBack}><ArrowLeft size={18}/>All matches</button><div className="goal-match-error"><ShieldCheck size={22}/><b>Match details unavailable</b><span>{error}</span><button className="goal-button-lime" onClick={() => navigate(0)}>Try again</button></div></div>;
  const real = data && !String(matchId).startsWith('demo-');
  const demoLive = String(matchId) === 'demo-live'; const isDemoLive = demoLive || fixture?.live;
  const home = real ? data.teams?.home?.name : fixture?.home || sample.home; const away = real ? data.teams?.away?.name : fixture?.away || sample.away;
  const demoScore = typeof fixture?.score === 'string' ? fixture.score.split(':').map(value => value.trim()) : null;
  const homeScore = real ? (data.goals?.home ?? '–') : isDemoLive ? demoScore?.[0] ?? fixture?.goals?.home ?? sample.homeScore : '–'; const awayScore = real ? (data.goals?.away ?? '–') : isDemoLive ? demoScore?.[1] ?? fixture?.goals?.away ?? sample.awayScore : '–';
  const streams = data?.streams || []; const embed = data?.provider === 'matchora' && data?.hasMatchEmbed; const hlsStream = streams.find(stream => stream.type === 'HLS');
  const statRows = real ? (data.statistics?.length ? ['Ball Possession', 'Total Shots', 'Corner Kicks'].map(label => { const h = data.statistics[0]?.statistics?.find(x => x.type === label)?.value; const a = data.statistics[1]?.statistics?.find(x => x.type === label)?.value; return [label, Number.parseInt(h, 10) || 0, Number.parseInt(a, 10) || 0]; }) : []) : demoLive ? sample.stats : [];
  return <div className="goal-match-page"><button className="goal-back" onClick={goBack}><ArrowLeft size={18}/>All matches</button>
    <div className="goal-match-page-heading"><div><p className="goal-eyebrow">{real ? data.league?.name : fixture?.league || sample.league}</p><h1>{home} <span>vs</span> {away}</h1></div>{(isDemoLive || (real && ['1H', '2H', 'HT', 'ET', 'BT', 'P'].includes(data.fixture?.status?.short))) && <span className="goal-live-pill"><i/> LIVE&nbsp; {real ? data.fixture?.status?.elapsed || '' : fixture?.minute || sample.minute}{(real ? data.fixture?.status?.elapsed : fixture?.minute || sample.minute) ? "'" : ''}</span>}</div>
    {embed ? <section className={`goal-player goal-player-embed${fullscreen ? ' is-fullscreen' : ''}`} ref={matchoraPlayerRef}>{matchoraPlaying && <MatchoraEmbed matchId={data.fixture.id} preferredChannelId={matchoraSelection?.channelId} embedUrl={data.embedUrl}/>}<MatchoraChannelPicker channels={data.channels || []} selectedChannelId={matchoraSelection?.channelId} playing={matchoraPlaying} onChoose={(channelId, quality) => setMatchoraSelection({ channelId, quality })} onPlay={playMatchora}/>{matchoraPlaying && <><div className={`goal-player-control-bar${fullscreen && !controlsVisible ? ' controls-hidden' : ''}`}><button className="goal-player-enlarge" aria-label={fullscreen ? 'Return to mini player' : 'Enter fullscreen'} title={fullscreen ? 'Return to mini player' : 'Enter fullscreen'} onClick={toggleMatchoraFullscreen}>{fullscreen ? <Minimize2 size={20}/> : <Maximize2 size={20}/>}</button></div>{fullscreen && <span className="goal-player-reveal-sensor" aria-hidden="true" onPointerMove={revealPlayerControls} onMouseMove={revealPlayerControls}/>}</>}</section> : hlsStream ? <section className="goal-player goal-player-hls"><HlsPlayer stream={hlsStream}/></section> : <section className="goal-player"><div className="goal-player-overlay"><span className="goal-player-placeholder-icon"><ShieldCheck size={27}/></span><b>{real ? 'No authorized stream is available for this match.' : isDemoLive ? 'Live stream preview' : 'Match stream unavailable'}</b><span>{real ? 'A licensed broadcaster will appear here when one is available.' : 'This match uses placeholder data and has no playable broadcast.'}</span></div></section>}
    <section className="goal-match-score"><span>{home}</span><strong>{homeScore} <i>:</i> {awayScore}</strong><span>{away}</span><small>{real ? data.league?.round || data.league?.name : fixture?.time ? `Kick-off · ${fixture.time}` : 'Anfield · Liverpool'}</small></section>
    {streams.filter(stream => stream.type !== 'HLS').map(stream => <section className="goal-real-stream" key={stream.id}><a href={stream.url} target="_blank" rel="noreferrer">Watch on {stream.provider}</a></section>)}
    <div className="goal-match-tabs" role="tablist" aria-label="Match information">{[['Timeline', Timer], ['Stats', BarChart3]].map(([name, Icon]) => <button role="tab" aria-selected={tab === name} className={tab === name ? 'active' : ''} key={name} onClick={() => setTab(name)}><Icon size={17}/>{name}</button>)}</div>
    {tab === 'Timeline' && <section className="goal-timeline">{liveTimeline.map(event => <article className="goal-event" key={event.id}><time>{event.minute}</time><span className="goal-event-mark">⚽</span><div><b>{event.type}</b><p>{event.text}</p><small>{event.team}</small></div></article>)}{(real || !demoLive ? [] : sample.events).map((event, index) => <article className="goal-event" key={`sample-${index}`}><time>{event.min}</time><span className="goal-event-mark">⚽</span><div><b>{event.type}</b><p>{event.name}</p><small>{event.team}</small></div></article>)}{!liveTimeline.length && (real || !demoLive) && <div className="goal-placeholder-note">{embed ? 'Matchora does not provide a full event timeline for this match. New goals reported while this page is open will appear here.' : 'Match events will appear here as the provider reports them.'}</div>}</section>}
    {tab === 'Stats' && <section className="goal-stats">{statRows.length ? statRows.map(([label, h, a]) => <article className="goal-stat" key={label}><div><strong>{h}{label.toLowerCase().includes('possession') ? '%' : ''}</strong><span>{label}</span><strong>{a}{label.toLowerCase().includes('possession') ? '%' : ''}</strong></div><div className="goal-stat-bars"><i style={{ width: `${Math.max(5, Number(h) / (Number(h) + Number(a) || 1) * 100)}%` }}/><i style={{ width: `${Math.max(5, Number(a) / (Number(h) + Number(a) || 1) * 100)}%` }}/></div></article>) : real && embed ? <><article className="goal-stat"><div><strong>{homeScore}</strong><span>Score</span><strong>{awayScore}</strong></div><div className="goal-stat-bars"><i style={{width:`${Number(homeScore)/(Number(homeScore)+Number(awayScore)||1)*100}%`}}/><i style={{width:`${Number(awayScore)/(Number(homeScore)+Number(awayScore)||1)*100}%`}}/></div></article><article className="goal-stat"><div><strong>{data.fixture?.status?.elapsed ? `${data.fixture.status.elapsed}'` : data.fixture?.status?.long || '—'}</strong><span>Match time</span><strong>{data.channels?.filter(channel => channel.playing && !channel.dead).length || 0}</strong></div><p className="goal-placeholder-note">Minute / status · active Matchora channels</p></article><div className="goal-placeholder-note">Matchora does not provide possession, shots or corners for this match.</div></> : <div className="goal-placeholder-note">Statistics are not available for this match yet.</div>}</section>}
  </div>;
}
