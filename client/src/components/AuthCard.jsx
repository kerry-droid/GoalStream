import { useState } from 'react';
import { useDispatch } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Goal, LockKeyhole, LoaderCircle } from 'lucide-react';
import { api } from '../api.js';
import { sessionReady } from '../store.js';

export default function AuthCard() {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ email: '', password: '', username: '', displayName: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const dispatch = useDispatch(); const navigate = useNavigate();
  const submit = async e => {
    e.preventDefault(); setError(''); setBusy(true);
    try {
      const result = await api(`/auth/${mode}`, { method: 'POST', body: JSON.stringify(form) }, false);
      dispatch(sessionReady(result)); navigate('/home');
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  return <div className="auth-card">
    <div className="card-mark"><Goal size={18}/></div>
    <p className="eyebrow">YOUR MATCHDAY STARTS HERE</p>
    <h1>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
    <p className="card-copy">Follow the fixtures, scores, and competitions you care about.</p>
    <form onSubmit={submit}>
      {mode === 'register' && <><label>Display name<input autoComplete="name" placeholder="Your name" value={form.displayName} onChange={e=>setForm({...form,displayName:e.target.value})} required/></label><label>Username<input autoComplete="username" placeholder="Choose a username" value={form.username} onChange={e=>setForm({...form,username:e.target.value})} required minLength="3"/></label></>}
      <label>Email address<input type="email" autoComplete="email" placeholder="you@example.com" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} required/></label>
      <label>Password<input type="password" autoComplete={mode==='login'?'current-password':'new-password'} placeholder="At least 8 characters" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} required minLength="8"/></label>
      {error && <p className="error-message" role="alert">{error}</p>}
      <button className="primary-button" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18}/> : <>{mode==='login'?'Sign in':'Create account'}<ArrowRight size={17}/></>}</button>
    </form>
    <p className="switch-mode">{mode==='login'?'New to GoalStream?':'Already have an account?'} <button onClick={()=>{setMode(mode==='login'?'register':'login');setError('');}}>{mode==='login'?'Create an account':'Sign in'}</button></p>
    <p className="legal"><LockKeyhole size={12}/> Your account is protected with secure sign-in.</p>
  </div>;
}
