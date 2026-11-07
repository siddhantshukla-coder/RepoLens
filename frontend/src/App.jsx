import { useEffect, useState } from 'react';
import { api, getToken, setToken, setUnauthorizedHandler } from './api.js';
import { go, useRoute } from './router.js';
import { Sprite } from './components/Lens.jsx';
import TopNav from './components/TopNav.jsx';
import AuthView from './components/AuthView.jsx';
import RepoView from './components/RepoView.jsx';
import ScanView from './components/ScanView.jsx';
import ReposPage from './components/ReposPage.jsx';
import Workspace from './components/Workspace.jsx';
import DocsPage from './components/DocsPage.jsx';
import ProfilePage from './components/ProfilePage.jsx';

export default function App() {
  const [booting, setBooting] = useState(true);   // true while we check a saved login
  const [user, setUser] = useState(null);         // profile {username,email,full_name,created_at}; null = logged out
  const route = useRoute();

  // ---- session ----------------------------------------------------------
  // clearRoute=true  : the user clicked "Log out" -> forget where they were
  // clearRoute=false : the session just expired    -> keep the URL so they come back to it after logging in
  function endSession(clearRoute) {
    setToken(null);
    setUser(null);
    if (clearRoute) history.replaceState(null, '', location.pathname + location.search);
  }

  // After logging in with no page in the URL, return to the page this user was last on.
  function restoreLastPage(username) {
    if (!location.hash) go(localStorage.getItem('rl_last:' + username) || 'analyze', true);
  }

  function onAuth(profile) {
    setUser(profile);
    restoreLastPage(profile.username);
  }

  // On first load: if a token is saved, check it and restore the session.
  useEffect(() => {
    setUnauthorizedHandler(() => endSession(false));   // api.js calls this on every 401
    (async () => {
      if (getToken()) {
        try {
          const me = await api('/api/auth/me');
          setUser(me);
          restoreLastPage(me.username);
        } catch { /* token invalid or expired: fall through to the login screen */ }
      }
      setBooting(false);
    })();
  }, []);

  // Remember the last page per user (this is how "come back to what I was analysing" survives a new tab or a new day).
  useEffect(() => {
    if (user && location.hash) localStorage.setItem('rl_last:' + user.username, location.hash.replace(/^#\//, ''));
  }, [route, user]);

  // ---- render -----------------------------------------------------------
  if (booting) return <Sprite />;
  if (!user) return <><Sprite /><main><AuthView onAuth={onAuth} /></main></>;

  const { page, id } = route;
  let screen;
  if (page === 'scan') screen = <ScanView key={id} jobId={id} />;
  else if (page === 'repos') screen = id ? <Workspace key={id} repoId={id} /> : <ReposPage />;
  else if (page === 'docs') screen = <DocsPage selectedId={id} />;
  else if (page === 'profile') screen = <ProfilePage user={user} onUser={setUser} onLogout={() => endSession(true)} />;
  else screen = <RepoView />;

  return (
    <>
      <Sprite />
      <TopNav user={user} page={page} onLogout={() => endSession(true)} />
      <main className="with-bar">{screen}</main>
    </>
  );
}
