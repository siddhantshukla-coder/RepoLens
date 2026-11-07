import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { fmtDate, kb, repoLabel } from '../format.js';
import ConfirmButton from './ConfirmButton.jsx';

// NEW in v1.1  -  section "My repos".
// Shows (1) analyses that are still running or have failed, and (2) every repo this user
// has analysed. All of it comes from the backend database, so it is the same after a
// restart and on any device the user logs in from.
export default function ReposPage() {
  const [repos, setRepos] = useState(null);   // null = still loading
  const [jobs, setJobs] = useState([]);       // running + failed analyses
  const [error, setError] = useState('');

  async function load() {
    try {
      const [r, j] = await Promise.all([api('/api/repos'), api('/api/jobs')]);
      setRepos(r.repos);
      setJobs(j.jobs);
      setError('');
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  // While something is still analysing, refresh every 3 s so it moves into the repo list by itself.
  const running = jobs.some((j) => j.status === 'running');
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [running]);

  async function removeRepo(id) {
    try { await api('/api/repos/' + id, { method: 'DELETE' }); setRepos((r) => r.filter((x) => x.id !== id)); }
    catch (e) { setError(e.message); }
  }
  async function dismissJob(id) {
    try { await api('/api/jobs/' + id, { method: 'DELETE' }); setJobs((j) => j.filter((x) => x.id !== id)); }
    catch (e) { setError(e.message); }
  }
  async function retryJob(job) {
    try {
      await api('/api/jobs/' + job.id, { method: 'DELETE' });
      const { job_id } = await api('/api/repos/analyze', { method: 'POST', body: { repo_url: job.repo_url } });
      go('scan/' + job_id);
    } catch (e) { setError(e.message); }
  }

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1>My repos</h1>
          <p>Everything you have analysed. Open one to read its documentation and chat with it.</p>
        </div>
        <button className="btn" onClick={() => go('analyze')}>Analyze a new repo</button>
      </div>

      {error && <p className="err" role="alert">{error}</p>}

      {jobs.length > 0 && (
        <>
          <h2 className="section-title">In progress and failed</h2>
          <div className="grid">
            {jobs.map((j) => (
              <article key={j.id} className={'rcard ' + (j.status === 'running' ? 'running' : 'failed')}>
                <h3>{repoLabel(j.repo_url)}</h3>
                {j.status === 'running' ? (
                  <>
                    <div className="bar wide"><i style={{ width: j.percent + '%' }} /></div>
                    <p className="meta">{j.percent}% · {j.message}</p>
                    <div className="row"><button className="btn" onClick={() => go('scan/' + j.id)}>View progress</button></div>
                  </>
                ) : (
                  <>
                    <p className="meta bad-text">{j.message}</p>
                    <div className="row">
                      <button className="btn" onClick={() => retryJob(j)}>Try again</button>
                      <button className="btn ghost" onClick={() => dismissJob(j.id)}>Dismiss</button>
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
        </>
      )}

      <h2 className="section-title">Analysed repos{repos ? ` (${repos.length})` : ''}</h2>
      {repos === null && !error && <p className="muted">Loading…</p>}
      {repos && repos.length === 0 && (
        <div className="empty">
          <p>You haven’t analysed a repo yet.</p>
          <button className="btn" onClick={() => go('analyze')}>Analyze your first repo</button>
        </div>
      )}
      <div className="grid">
        {repos && repos.map((r) => (
          <article key={r.id} className="rcard">
            <h3>{r.name}</h3>
            <p className="meta">
              <a href={r.url} target="_blank" rel="noreferrer">{r.url.replace('https://', '')}</a>
              <br />Analysed {fmtDate(r.created_at)} · docs {kb(r.doc_chars)}
            </p>
            <div className="row">
              <button className="btn" onClick={() => go('repos/' + r.id)}>Open &amp; chat</button>
              <button className="btn ghost" onClick={() => go('docs/' + r.id)}>Documentation</button>
              <ConfirmButton onConfirm={() => removeRepo(r.id)} confirmText="Confirm delete">Delete</ConfirmButton>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
