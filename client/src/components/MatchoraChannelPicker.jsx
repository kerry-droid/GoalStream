import { useState } from 'react';
import { ChevronDown, ListVideo, Play } from 'lucide-react';

const unavailable = channel => channel.dead === true || channel.dead === 1 || channel.dead === 'true';
const qualityRank = channel => {
  const value = String(channel.quality || '').toUpperCase();
  if (/4K|UHD/.test(value)) return 5;
  if (/FHD|1080/.test(value)) return 4;
  if (/HD|720/.test(value)) return 3;
  if (/SD|480|360/.test(value)) return 2;
  return 1;
};
export const bestMatchoraChannel = channels => {
  const available = (channels || []).filter(channel => !unavailable(channel));
  const english = available.filter(channel => /\b(english|eng|en)\b/i.test([channel.language, channel.name, channel.label].filter(Boolean).join(' ')));
  return [...(english.length ? english : available)].sort((a, b) => qualityRank(b) - qualityRank(a))[0] || null;
};

export default function MatchoraChannelPicker({ channels = [], loading = false, selectedChannelId, onChoose, onPlay, playing = false }) {
  const [open, setOpen] = useState(false);
  const selected = channels.find(channel => String(channel.id) === String(selectedChannelId));
  const select = channel => {
    onChoose(channel?.id ?? null, channel?.quality || 'AUTO');
    setOpen(false);
  };

  return <div className={`goal-matchora-channel-picker${playing ? ' is-playing' : ' is-ready'}`}>
    <button type="button" className="goal-matchora-channels-trigger" aria-label="Choose channel" aria-expanded={open} onClick={() => setOpen(value => !value)}>
      <ListVideo size={18}/><span>Channels</span><ChevronDown size={15}/>
    </button>
    {open && <section className="goal-matchora-channel-popover" aria-label="Matchora channels">
      <h3>Choose a channel</h3>
      <button type="button" className={!selectedChannelId ? 'selected' : ''} onClick={() => select(null)}>
        <span><b>Auto · English where available</b><small>Matchora chooses a working feed</small></span><i>Auto</i>
      </button>
      {loading && <p role="status">Loading Matchora channels…</p>}
      {channels.map(channel => <button type="button" key={channel.id} disabled={unavailable(channel)} className={String(selectedChannelId) === String(channel.id) ? 'selected' : ''} onClick={() => select(channel)}>
        <span><b>{channel.name || channel.label || `Channel ${channel.id}`}</b><small>{[channel.language, channel.country, channel.quality].filter(Boolean).join(' · ') || 'Matchora broadcast'}{unavailable(channel) ? ' · Unavailable' : ''}</small></span><i>{channel.quality || 'Feed'}</i>
      </button>)}
      {!loading && channels.length === 0 && <p>Matchora will select a working channel automatically.</p>}
    </section>}
    {!playing && onPlay && <button type="button" className="goal-quality-play" onClick={() => { setOpen(false); onPlay(); }} disabled={loading} aria-label="Play match" title={loading ? 'Loading Matchora channels' : 'Play match'}><Play size={21} fill="currentColor"/></button>}
    {playing && selected && <span className="goal-matchora-selected-channel" aria-live="polite">{selected.name || selected.label}</span>}
  </div>;
}
