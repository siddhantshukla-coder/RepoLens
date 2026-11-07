import { Mark } from './Lens.jsx';
import { initials } from '../format.js';

// NEW in v1.1. The top bar with the four sections: Analyze / My repos / Documentation / Profile.
// The links are plain <a href="#/..."> links: the hash router (router.js) does the rest.
const LINKS = [
  ['analyze', 'Analyze'],
  ['repos', 'My repos'],
  ['docs', 'Documentation'],
  ['profile', 'Profile'],
];

export default function TopNav({ user, page, onLogout }) {
  const active = page === 'scan' ? 'analyze' : page;   // the scan screen belongs to "Analyze"
  return (
    <header className="topbar">
      <a className="brand" href="#/analyze"><Mark />RepoLens</a>

      <nav className="nav" aria-label="Sections">
        {LINKS.map(([key, text]) => (
          <a
            key={key} href={'#/' + key}
            className={'navlink' + (active === key ? ' on' : '')}
            aria-current={active === key ? 'page' : undefined}
          >
            {text}
          </a>
        ))}
      </nav>

      <div className="who">
        <a className="whoami" href="#/profile" title="Your profile">
          <span className="avatar">{initials(user)}</span>
          <span>{user.full_name || user.username}</span>
        </a>
        <button className="btn ghost" onClick={onLogout}>Log out</button>
      </div>
    </header>
  );
}
