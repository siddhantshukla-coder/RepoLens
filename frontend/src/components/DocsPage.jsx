import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { fmtDate, kb } from '../format.js';
import DocPanel from './DocPanel.jsx';
import ConfirmButton from './ConfirmButton.jsx';

// NEW in v1.1  -  section "Documentation": the library of saved, generated documentation.
// List on the left (#/docs), the selected document on the right (#/docs/<repoId>).
// The documentation itself is stored in the backend database, so it is always available
// to read or download again without re-running the analysis.
export default function DocsPage({ selectedId }) {
  const [repos, setRepos] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/repos').then((r) => setRepos(r.repos)).catch((e) => setError(e.message));
  }, []);

  // Nothing selected yet? Open the newest document automatically.
  useEffect(() => {
    if (!selectedId && repos && repos.length) go('docs/' + repos[0].id, true);
  }, [selectedId, repos]);

  if (error) return <section className="center"><p className="err" role="alert">{error}</p></section>;
  if (repos === null) return <section className="center"><p>Loading…</p></section>;
  if (repos.length === 0) {
    return (
      <section className="center">
        <h1 className="scan-title">No documentation yet</h1>
        <p>Documentation appears here after you analyse a repo.</p>
        <button className="btn" onClick={() => go('analyze')}>Analyze a repo</button>
      </section>
    );
  }

  return (
    <section className="docs">
      <aside className="doclist" aria-label="Saved documentation">
        {repos.map((r) => (
          <a key={r.id} href={'#/docs/' + r.id} className={'docitem' + (r.id === selectedId ? ' on' : '')}>
            <b>{r.name}</b>
            <small>{fmtDate(r.created_at)} · {kb(r.doc_chars)}</small>
          </a>
        ))}
      </aside>
      {selectedId && (
        <DocViewer
          key={selectedId} repoId={selectedId}
          onDeleted={(id) => { setRepos((rs) => rs.filter((x) => x.id !== id)); go('docs', true); }}
        />
      )}
    </section>
  );
}

// Loads and shows ONE saved document.
function DocViewer({ repoId, onDeleted }) {
  const [repo, setRepo] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let stopped = false;
    api(`/api/repos/${repoId}/doc`)
      .then((d) => { if (!stopped) setRepo({ id: repoId, ...d }); })
      .catch((e) => { if (!stopped) setError(e.message); });
    return () => { stopped = true; };
  }, [repoId]);

  async function remove() {
    try { await api('/api/repos/' + repoId, { method: 'DELETE' }); onDeleted(repoId); }
    catch (e) { setError(e.message); }
  }

  if (error) return <div className="panel"><p className="err pad" role="alert">{error}</p></div>;
  if (!repo) return <div className="panel"><p className="muted pad">Loading…</p></div>;

  return (
    <DocPanel repo={repo}>
      <button className="btn ghost" onClick={() => go('repos/' + repoId)}>Chat with this repo</button>
      <ConfirmButton onConfirm={remove} confirmText="Confirm delete">Delete</ConfirmButton>
    </DocPanel>
  );
}
