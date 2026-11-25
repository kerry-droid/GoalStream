import { useEffect, useState } from 'react';

const hosts = ['https://matchora.pro', 'https://matchora.to', 'https://es.matchora.pro'];

const validProviderEmbed = (url, kind, id) => {
  if (!url || kind !== 'match') return '';
  try {
    const parsed = new URL(url);
    const hosts = ['matchora.pro', 'matchora.to', 'es.matchora.pro'];
    if (parsed.protocol !== 'https:' || !hosts.includes(parsed.hostname) || parsed.pathname !== `/embed/match/${encodeURIComponent(id)}`) return '';
    return parsed.origin + parsed.pathname;
  } catch { return ''; }
};

export default function MatchoraEmbed({ matchId, channelId, replayId, preferredChannelId, embedUrl }) {
  const [host, setHost] = useState('');
  const embedKind = replayId != null ? 'replay' : channelId != null ? 'channel' : 'match';
  const embedId = replayId != null ? replayId : channelId != null ? channelId : matchId;
  const providerEmbedUrl = validProviderEmbed(embedUrl, embedKind, embedId);

  useEffect(() => {
    let active = true;
    let done = false;
    const checks = new Array(hosts.length - 1);
    const timers = [];
    setHost('');

    if (providerEmbedUrl) {
      setHost(new URL(providerEmbedUrl).origin);
      return () => { active = false; };
    }

    const chooseHost = () => {
      if (!active || done) return;
      for (let index = 0; index < checks.length; index += 1) {
        if (checks[index] === true) {
          done = true;
          setHost(hosts[index]);
          return;
        }
        if (checks[index] === undefined) return;
      }
      done = true;
      setHost(hosts[hosts.length - 1]);
    };

    const markHost = (index, healthy) => {
      if (checks[index] !== undefined || !active || done) return;
      checks[index] = healthy;
      chooseHost();
    };

    hosts.slice(0, -1).forEach((candidate, index) => {
      timers[index] = window.setTimeout(() => markHost(index, false), 4000);
      fetch(`${candidate}/front-health`, { mode: 'no-cors', cache: 'no-store' }).then(
        () => {
          window.clearTimeout(timers[index]);
          markHost(index, true);
        },
        () => {
          window.clearTimeout(timers[index]);
          markHost(index, false);
        },
      );
    });

    return () => {
      active = false;
      timers.forEach(window.clearTimeout);
    };
  }, [embedKind, embedId, providerEmbedUrl]);

  if (!host) return <div className="matchora-player-loading" role="status">Loading {embedKind} player…</div>;

  const channelQuery = embedKind === 'match' && preferredChannelId != null ? `${providerEmbedUrl?.includes('?') ? '&' : '?'}ch=${encodeURIComponent(preferredChannelId)}` : '';
  const source = providerEmbedUrl || `${host}/embed/${embedKind}/${encodeURIComponent(embedId)}`;

  return <div className="matchora-player">
    <iframe
      src={`${source}${channelQuery}`}
      title={`Matchora ${embedKind} player`}
      width="100%"
      height="480"
      frameBorder="0"
      allow="autoplay; fullscreen"
      allowFullScreen
    />
  </div>;
}
