// api.js - the ONLY place that talks to the backend and handles the JWT.

let token = localStorage.getItem('rl_token');   // survives page refreshes
let onUnauthorized = () => {};                   // App registers a logout function here

export const getToken = () => token;

export function setToken(t) {
  token = t;
  if (t) localStorage.setItem('rl_token', t);
  else localStorage.removeItem('rl_token');
}

export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

/**
 * api('/api/chat', { method: 'POST', body: {...} })
 *  - adds the "Authorization: Bearer <jwt>" header when we are logged in
 *  - returns the parsed JSON, or throws Error(message) so screens can show it
 *  - if the server says 401 (token expired / invalid) we log the user out
 */
export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = {};
  try { data = await res.json(); } catch { /* empty or non-JSON body */ }

  if (res.status === 401 && token) onUnauthorized();
  if (!res.ok) {
    // FastAPI sends {"detail": "..."} for errors we raise ourselves
    throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`);
  }
  return data;
}
