import { store } from './store.js';
import { sessionReady, signedOut } from './store.js';

const configuredApi = (import.meta.env.VITE_API_URL || 'http://localhost:5000/api').replace(/\/+$/, '');
const API = configuredApi.endsWith('/api') ? configuredApi : `${configuredApi}/api`;
let refreshPromise;
export async function api(path, options = {}, retry = true) {
  const token = store.getState().auth.accessToken;
  const response = await fetch(`${API}${path}`, { ...options, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    refreshPromise ||= fetch(`${API}/auth/refresh`, { method: 'POST', credentials: 'include' }).then(async r => { if (!r.ok) throw new Error('Session expired'); const session = await r.json(); store.dispatch(sessionReady(session)); return session; }).catch(error => { store.dispatch(signedOut()); throw error; }).finally(() => { refreshPromise = null; });
    await refreshPromise;
    return api(path, options, false);
  }
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(payload.error || 'Request failed'); }
  return response.status === 204 ? null : response.json();
}
export { API };
