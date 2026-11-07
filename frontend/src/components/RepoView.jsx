import { useState } from 'react';
import { api } from '../api.js';
import { go } from '../router.js';
import { Lens } from './Lens.jsx';

// Screen 2 ("Analyze"): paste a GitHub repo URL.
// v1.1: this component now starts the analysis itself (it used to get onAnalyze/error props
// from App). On success it jumps to #/scan/<jobId>. If the same repo is already being
// analysed, the backend returns that existing job, so the user simply re-attaches to it.
export default function RepoView() {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError('');
    try {
      const { job_id } = await api('/api/repos/analyze', { method: 'POST', body: { repo_url: url.trim() } });
      go('scan/' + job_id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <section className="center">
      <Lens size={130} />
      <h1>Which repository should we open?</h1>
      <p>RepoLens reads the code, writes the documentation, then answers your questions from it.</p>

      {/* the search bar is shaped like a lens barrel */}
      <form className="search" onSubmit={submit}>
        <input
          placeholder="https://github.com/owner/repo" aria-label="GitHub repository URL"
          required autoFocus value={url} onChange={(e) => setUrl(e.target.value)}
        />
        <button className="btn" disabled={busy}>Analyze repo</button>
      </form>
      <p className="err" role="alert">{error}</p>
      <p>
        Public GitHub repos. Up to 30 source files are documented, so big repos can take a few minutes.
        Repos you have already analysed are saved in <a href="#/repos">My repos</a>.
      </p>
    </section>
  );
}
