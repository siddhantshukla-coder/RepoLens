import Markdown from './Markdown.jsx';
import { fmtDate } from '../format.js';

// Shows the generated documentation and lets the user download it as a .md file.
// v1.1: the extra buttons next to "Download .md" are now passed in as `children`
// (the workspace adds "All repos", the Documentation page adds "Chat" + "Delete"),
// so this one panel serves both screens.
export default function DocPanel({ repo, children }) {
  // The browser builds the file itself from text we already have: no extra request needed.
  function download() {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([repo.markdown], { type: 'text/markdown' }));
    a.download = repo.name.replace('/', '-') + '-docs.md';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <h2>{repo.name}</h2>
          <small>
            Generated documentation{repo.created_at ? ' · saved ' + fmtDate(repo.created_at) : ''}
            {repo.url && <> · <a className="subtle" href={repo.url} target="_blank" rel="noreferrer">GitHub</a></>}
          </small>
        </div>
        <div className="acts">
          <button className="btn" onClick={download}>Download .md</button>
          {children}
        </div>
      </div>
      <Markdown text={repo.markdown} className="doc" />
    </div>
  );
}
