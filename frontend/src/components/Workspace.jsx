import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import DocPanel from './DocPanel.jsx';
import ChatPanel from './ChatPanel.jsx';

// Screen 4: documentation on the left, self-RAG chatbot on the right.
// v1.1: it now receives only `repoId` (from the URL #/repos/<repoId>) and loads the saved
// documentation from the backend itself, so opening or refreshing this URL always works,
// even days later or after a server restart.
export default function Workspace({ repoId }) {
  const [repo, setRepo] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let stopped = false;
    api(`/api/repos/${repoId}/doc`)
      .then((d) => { if (!stopped) setRepo({ id: repoId, ...d }); })
      .catch((e) => { if (!stopped) setError(e.message); });
    return () => { stopped = true; };
  }, [repoId]);

  if (error) {
    return (
      <section className="center">
        <h1 className="scan-title">Can’t open this repo</h1>
        <p className="err" role="alert">{error}</p>
        <p><a href="#/repos">Back to My repos</a></p>
      </section>
    );
  }
  if (!repo) return <section className="center"><p>Loading…</p></section>;

  return (
    <section className="work">
      <DocPanel repo={repo}>
        <button className="btn ghost" onClick={() => go('repos')}>All repos</button>
      </DocPanel>
      <ChatPanel repo={repo} />
    </section>
  );
}
