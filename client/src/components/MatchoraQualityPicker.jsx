import { useMemo } from 'react';
import { Play } from 'lucide-react';

function networkHint() {
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (!connection) return 'HD works best on a stable moderate or fast connection. SD is better when your connection is slow.';
  const type = connection.effectiveType;
  const downlink = Number(connection.downlink || 0);
  if (type === 'slow-2g' || type === '2g' || (downlink > 0 && downlink < 1.5)) return 'Slow connection detected. SD should use less data and play more smoothly.';
  if (type === '3g' || (downlink > 0 && downlink < 5)) return 'Moderate connection detected. HD may work; choose SD if playback buffers.';
  if (type === '4g' || downlink >= 5) return 'Your connection looks suitable for HD. Choose SD if playback buffers.';
  return 'HD works best on a stable moderate or fast connection. SD is better when your connection is slow.';
}

function qualityOf(channel) {
  const value = String(channel?.quality || '').toUpperCase();
  if (/SD|480|360|LOW/.test(value)) return 'SD';
  if (/HD|720|1080|FHD|UHD|4K/.test(value)) return 'HD';
  return 'AUTO';
}

export default function MatchoraQualityPicker({ channels = [], loading = false, error = '', selectedQuality, onChoose, onPlay }) {
  const options = useMemo(() => {
    const byQuality = { HD: [], SD: [] };
    channels.forEach(channel => {
      const quality = qualityOf(channel);
      if (quality !== 'AUTO') byQuality[quality].push(channel);
    });
    return byQuality;
  }, [channels]);
  const hint = useMemo(networkHint, []);
  const hdChannel = options.HD[0];
  const sdChannel = options.SD[0];

  return <section className="goal-quality-picker" aria-label="Choose stream quality">
    <p className="goal-quality-eyebrow">MATCHORA STREAM</p>
    <h2>Choose quality, then play</h2>
    <p className="goal-quality-hint">{hint}</p>
    {error && <p className="goal-quality-error" role="alert">{error}</p>}
    {loading ? <p className="goal-quality-loading" role="status">Loading SD and HD choices…</p> : <div className="goal-quality-options">
      <button type="button" aria-pressed={selectedQuality === 'HD'} className={`goal-quality-option ${selectedQuality === 'HD' ? 'selected' : ''}`} onClick={() => onChoose(hdChannel?.id || null, 'HD')}><strong>HD</strong><span>{hdChannel ? 'Sharper picture · stable moderate or fast network' : 'Matchora will choose the best available feed for HD'}</span></button>
      <button type="button" aria-pressed={selectedQuality === 'SD'} className={`goal-quality-option ${selectedQuality === 'SD' ? 'selected' : ''}`} onClick={() => onChoose(sdChannel?.id || null, 'SD')}><strong>SD</strong><span>{sdChannel ? 'Lower data use · slow or unstable network' : 'Matchora will choose an available feed'}</span></button>
    </div>}
    {onPlay && <button type="button" className="goal-button-lime goal-quality-play" onClick={onPlay} disabled={loading || selectedQuality === undefined} aria-label="Play match" title="Play match"><Play size={21} fill="currentColor"/></button>}
  </section>;
}
