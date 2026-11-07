import { useEffect, useState } from 'react';
import { api, setToken } from '../api.js';
import { fmtDate, initials } from '../format.js';
import ConfirmButton from './ConfirmButton.jsx';

// small helper: shows a green "saved" or red error line under a form
function Note({ msg }) {
  return msg ? <p className={msg.ok ? 'ok' : 'err'} role="status">{msg.text}</p> : null;
}

// NEW in v1.1  -  section "Profile": account details, edit profile, change password, delete account.
// `user` is the profile held by App; `onUser` updates it after an edit; `onLogout` ends the session.
export default function ProfilePage({ user, onUser, onLogout }) {
  const [stats, setStats] = useState(null);   // { repo_count, active_jobs }
  const [form, setForm] = useState({
    full_name: user.full_name || '', username: user.username, email: user.email || '',
  });
  const [profileMsg, setProfileMsg] = useState(null);
  const [pw, setPw] = useState({ current: '', next: '', again: '' });
  const [pwMsg, setPwMsg] = useState(null);
  const [delPw, setDelPw] = useState('');
  const [delMsg, setDelMsg] = useState(null);

  useEffect(() => { api('/api/profile').then(setStats).catch(() => {}); }, [user.username]);

  const field = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // ---- edit profile -----------------------------------------------------
  async function saveProfile(e) {
    e.preventDefault();
    setProfileMsg(null);
    try {
      // The JWT contains the username, so the server sends a NEW token (needed after a rename).
      const { token, ...profile } = await api('/api/profile', { method: 'PUT', body: form });
      setToken(token);
      onUser(profile);
      setForm({ full_name: profile.full_name || '', username: profile.username, email: profile.email || '' });
      setProfileMsg({ ok: true, text: 'Profile saved.' });
    } catch (err) { setProfileMsg({ ok: false, text: err.message }); }
  }

  // ---- change password --------------------------------------------------
  async function changePassword(e) {
    e.preventDefault();
    setPwMsg(null);
    if (pw.next !== pw.again) return setPwMsg({ ok: false, text: 'The new passwords don’t match.' });
    try {
      await api('/api/profile/password', {
        method: 'POST', body: { current_password: pw.current, new_password: pw.next },
      });
      setPw({ current: '', next: '', again: '' });
      setPwMsg({ ok: true, text: 'Password changed.' });
    } catch (err) { setPwMsg({ ok: false, text: err.message }); }
  }

  // ---- delete account ---------------------------------------------------
  async function deleteAccount() {
    setDelMsg(null);
    try {
      await api('/api/profile', { method: 'DELETE', body: { password: delPw } });
      localStorage.removeItem('rl_last:' + user.username);
      onLogout();
    } catch (err) { setDelMsg({ ok: false, text: err.message }); }
  }

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1>Your profile</h1>
          <p>Account details and settings.</p>
        </div>
      </div>

      <div className="profile">
        {/* ---- identity card ---- */}
        <aside className="pcard identity">
          <div className="bigavatar">{initials(user)}</div>
          <h2>{user.full_name || user.username}</h2>
          <p className="muted">@{user.username}</p>
          <p className="muted">{user.email || 'No email yet. Add one on the right.'}</p>
          <p className="muted">Member since {fmtDate(user.created_at)}</p>
          <div className="stats">
            <div className="stat"><b>{stats ? stats.repo_count : '–'}</b><span>repos analysed</span></div>
            <div className="stat"><b>{stats ? stats.active_jobs : '–'}</b><span>running now</span></div>
          </div>
        </aside>

        <div className="stack-col">
          {/* ---- edit profile ---- */}
          <form className="pcard stack" onSubmit={saveProfile}>
            <h2>Edit profile</h2>
            <label className="field">Full name
              <input value={form.full_name} onChange={field('full_name')} maxLength={60} autoComplete="name" />
            </label>
            <label className="field">Username
              <input value={form.username} onChange={field('username')} required minLength={3} maxLength={30} autoComplete="username" />
            </label>
            <label className="field">Email
              <input type="email" value={form.email} onChange={field('email')} required autoComplete="email" />
            </label>
            <div><button className="btn">Save changes</button></div>
            <Note msg={profileMsg} />
          </form>

          {/* ---- change password ---- */}
          <form className="pcard stack" onSubmit={changePassword}>
            <h2>Change password</h2>
            <label className="field">Current password
              <input type="password" value={pw.current} autoComplete="current-password" required
                onChange={(e) => setPw((p) => ({ ...p, current: e.target.value }))} />
            </label>
            <label className="field">New password
              <input type="password" value={pw.next} autoComplete="new-password" required minLength={6}
                onChange={(e) => setPw((p) => ({ ...p, next: e.target.value }))} />
            </label>
            <label className="field">Repeat new password
              <input type="password" value={pw.again} autoComplete="new-password" required minLength={6}
                onChange={(e) => setPw((p) => ({ ...p, again: e.target.value }))} />
            </label>
            <div><button className="btn">Update password</button></div>
            <Note msg={pwMsg} />
          </form>

          {/* ---- delete account ---- */}
          <div className="pcard stack danger-zone">
            <h2>Delete account</h2>
            <p className="muted">
              Permanently deletes your account, every analysed repo, all saved documentation and chat
              indexes. This can’t be undone.
            </p>
            <label className="field">Enter your password to confirm
              <input type="password" value={delPw} autoComplete="current-password"
                onChange={(e) => setDelPw(e.target.value)} />
            </label>
            <div>
              <ConfirmButton
                className="btn ghost" disabled={!delPw} onConfirm={deleteAccount}
                confirmText="Yes, delete everything"
              >
                Delete my account
              </ConfirmButton>
            </div>
            <Note msg={delMsg} />
          </div>
        </div>
      </div>
    </section>
  );
}
