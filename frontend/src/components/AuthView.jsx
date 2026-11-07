import { useState } from 'react';
import { api, setToken } from '../api.js';
import { Lens } from './Lens.jsx';

// Screen 1: log in or create an account. On success the JWT is saved by setToken().

export default function AuthView({ onAuth }) {
  const [mode, setMode] = useState('login');    
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = mode === 'login'
        ? { username, password }
        : { username, password, email, full_name: fullName };
      const { token, ...profile } = await api('/api/auth/' + mode, { method: 'POST', body });
      setToken(token);            // store the JWT (api.js sends it on every later request)
      onAuth(profile);            // the server also sends the profile: hand it to App
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <section className="center">
      <Lens size={190} />
      <h1>See inside any repository.</h1>
      <p>Log in to turn a GitHub repo into documentation you can read, download and ask questions of.</p>

      <form className="card" onSubmit={submit}>
        <div className="tabs">
          <button type="button" className={'tab' + (mode === 'login' ? ' on' : '')} onClick={() => setMode('login')}>Log in</button>
          <button type="button" className={'tab' + (mode === 'register' ? ' on' : '')} onClick={() => setMode('register')}>Create account</button>
        </div>
        {mode === 'register' && (
          <input
            placeholder="Full name (optional)" aria-label="Full name" autoComplete="name"
            maxLength={60} value={fullName} onChange={(e) => setFullName(e.target.value)}
          />
        )}
        <input
          placeholder="Username" aria-label="Username" autoComplete="username"
          required minLength={3} value={username} onChange={(e) => setUsername(e.target.value)}
        />
        {mode === 'register' && (
          <input
            type="email" placeholder="Email (e.g. you@gmail.com)" aria-label="Email" autoComplete="email"
            required value={email} onChange={(e) => setEmail(e.target.value)}
          />
        )}
        <input
          type="password" placeholder="Password (6+ characters)" aria-label="Password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)}
        />
        <button className="btn" disabled={busy}>{mode === 'login' ? 'Log in' : 'Create account'}</button>
        <p className="err" role="alert">{error}</p>
      </form>
    </section>
  );
}
