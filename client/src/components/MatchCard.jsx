import { Star, ChevronRight, MapPin } from 'lucide-react';

export default function MatchCard({match, onFollow, onView}) {
  const status = match.fixture?.status;
  const live = ['1H','2H','HT','ET','BT','P'].includes(status?.short);
  const time = status?.elapsed ? `${status.elapsed}'` : new Date(match.fixture.date).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  return <article className="match-card"><div className="match-meta"><span>{match.league?.name}</span><span className={live?'live-label':''}>{live && <i/>}{live?`LIVE · ${time}`:status?.long==='Match Finished'?'FULL TIME':time}</span></div><div className="match-teams"><div className="team"><img src={match.teams?.home?.logo} alt=""/><span>{match.teams?.home?.name}</span></div><div className="score">{match.goals?.home ?? '–'} <small>:</small> {match.goals?.away ?? '–'}</div><div className="team team-away"><img src={match.teams?.away?.logo} alt=""/><span>{match.teams?.away?.name}</span></div></div><div className="match-bottom"><span><MapPin size={12}/>{match.fixture?.venue?.name || match.league?.country}</span><span className="match-actions"><button onClick={()=>onFollow?.(match)} aria-label="Follow both teams" title="Follow both teams"><Star size={14}/></button><button onClick={()=>onView?.(match.fixture.id)} aria-label="Match details" title="Match details"><ChevronRight size={15}/></button></span></div></article>
}
