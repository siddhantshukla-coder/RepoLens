import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { repoLabel } from '../format.js';
import { Lens } from './Lens.jsx';

// Screen 3: live progress of ONE analysis job, taken from the URL (#/scan/<jobId>).
// v1.1 changes:
//  * the job id comes from the URL, so a refresh (or coming back later from "My repos")
//    re-attaches to the same job: it is saved in the backend database now
//  * when the job finishes we go straight to #/repos/<repoId> (replacing this history entry)
//  * a failed job shows its error here, with Retry / Dismiss, instead of bouncing to another screen
export default function ScanView({ jobId }) {
  const [job, setJob] = useState(null);      // latest job row from the backend
  const [problem, setProblem] = useState(''); // e.g. "Analysis not found"

  useEffect(() => {
    let stopped = false;   // set by the cleanup so a finished/unmounted screen stops polling
    let timer;

    async function tick() {
      try {
        const j = await api('/api/jobs/' + jobId);
        if (stopped) return;
        setJob(j);
        if (j.status === 'done') { go('repos/' + j.repo_id, true); return; }   // open the workspace
        if (j.status === 'error') return;                                      // stop polling, show the error
      } catch (err) {
        if (!stopped) setProblem(err.message);
        return;
      }
      timer = setTimeout(tick, 1500);   // still running: check again shortly
    }

    tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [jobId]);

  // Retry a failed analysis: remove the failed row, start a fresh job for the same repo.
  async function retry() {
    try {
      await api('/api/jobs/' + jobId, { method: 'DELETE' });
      const { job_id } = await api('/api/repos/analyze', { method: 'POST', body: { repo_url: job.repo_url } });
      go('scan/' + job_id, true);
    } catch (err) { setProblem(err.message); }
  }

  async function dismiss() {
    try { await api('/api/jobs/' + jobId, { method: 'DELETE' }); } catch { /* already gone */ }
    go('analyze');
  }

  if (problem) {
    return (
      <section className="center">
        <Lens size={110} />
        <h1 className="scan-title">Something went wrong</h1>
        <p className="err" role="alert">{problem}</p>
        <p><a href="#/repos">Go to My repos</a> or <a href="#/analyze">analyze another repo</a>.</p>
      </section>
    );
  }
  if (!job) return <section className="center"><p>Loading…</p></section>;

  if (job.status === 'error') {
    return (
      <section className="center">
        <Lens size={110} />
        <h1 className="scan-title">Analysis of {repoLabel(job.repo_url)} failed</h1>
        <p className="err" role="alert">{job.message}</p>
        <div className="row-btns">
          <button className="btn" onClick={retry}>Try again</button>
          <button className="btn ghost" onClick={dismiss}>Dismiss</button>
        </div>
      </section>
    );
  }

  return (
    <section className="center">
      <div className="scan">
        <Lens />
        <div className="sweep" />
        <div className="pct">{job.percent}%</div>
      </div>
      <h1 className="scan-title">Reading {repoLabel(job.repo_url)}</h1>
      <div className="bar"><i style={{ width: job.percent + '%' }} /></div>
      <p className="scan-msg" aria-live="polite">{job.message}</p>
      <p>You can leave this page: the analysis keeps running and is listed in <a href="#/repos">My repos</a>.</p>
    </section>
  );
}
