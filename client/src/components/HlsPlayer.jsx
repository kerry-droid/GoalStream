import { useEffect, useRef, useState } from 'react';
import { LoaderCircle } from 'lucide-react';

export default function HlsPlayer({stream}) {
 const videoRef=useRef(null); const hlsRef=useRef(null); const [error,setError]=useState(''); const [loading,setLoading]=useState(true); const [qualities,setQualities]=useState([]);const [quality,setQuality]=useState('-1');
 useEffect(()=>{
  const video=videoRef.current; if(!video||!stream)return; setError('');setLoading(true);setQualities([]);setQuality('-1');
  if(video.canPlayType('application/vnd.apple.mpegurl')){video.src=stream.url;video.oncanplay=()=>setLoading(false);video.onerror=()=>{setError('This authorized stream could not be loaded.');setLoading(false)};return()=>{video.pause();video.removeAttribute('src');video.load()}}
  let hls;let cancelled=false;
  import('hls.js').then(({default:Hls})=>{
   if(cancelled)return;
   if(!Hls.isSupported()){setError('HLS playback is not supported in this browser.');setLoading(false);return}
   hls=new Hls({enableWorker:true});hlsRef.current=hls;hls.loadSource(stream.url);hls.attachMedia(video);hls.on(Hls.Events.MANIFEST_PARSED,()=>{setLoading(false);setQualities(hls.levels.map((level,index)=>({index,label:level.height?`${level.height}p`:Math.round(level.bitrate/1000)+' kbps'})))});hls.on(Hls.Events.ERROR,(_event,data)=>{if(data.fatal){setError('This authorized stream could not be loaded.');setLoading(false);hls.destroy()}});
  }).catch(()=>{if(!cancelled){setError('The HLS playback module could not be loaded.');setLoading(false)}});
  return()=>{cancelled=true;hlsRef.current=null;hls?.destroy()};
 },[stream]);
 return <div className="video-wrap"><div className="video-frame">{loading&&<div className="video-loading"><LoaderCircle className="spin"/> Loading authorized stream…</div>}{error&&<div className="video-error">{error}</div>}<video ref={videoRef} controls playsInline autoPlay={false} aria-label="Authorized live football stream"/></div>{qualities.length>1&&<label className="quality-picker">Quality <select value={quality} onChange={e=>{setQuality(e.target.value);if(hlsRef.current)hlsRef.current.currentLevel=Number(e.target.value)}}><option value="-1">Auto</option>{qualities.map(level=><option key={level.index} value={level.index}>{level.label}</option>)}</select></label>}</div>
}
