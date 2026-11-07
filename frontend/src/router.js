// router.js  -  NEW in v1.1. A tiny "hash router" (no extra library needed).
//
// The page lives in the URL after the "#", so a refresh or a bookmark brings the user
// back to exactly where they were:
//     http://localhost:5173/#/repos/ab12cd   ->  { page: 'repos', id: 'ab12cd' }
//     http://localhost:5173/#/profile        ->  { page: 'profile', id: '' }
//     (no hash at all)                       ->  { page: 'analyze', id: '' }
//
// Pages: analyze | scan/<jobId> | repos | repos/<repoId> | docs | docs/<repoId> | profile
import { useEffect, useState } from 'react';

function parse() {
  const [page = '', id = ''] = location.hash.replace(/^#\/?/, '').split('/');
  return { page: page || 'analyze', id };
}

// React hook: returns the current route and re-renders whenever the URL hash changes.
export function useRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

// go('repos/abc')        -> navigate (adds a history entry, so Back works)
// go('repos/abc', true)  -> replace the current entry (so Back skips e.g. the scan screen)
export function go(path, replace = false) {
  const url = '#/' + path;
  if (replace) location.replace(url);
  else location.hash = url;
}
