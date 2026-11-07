// format.js  -  NEW in v1.1. Small helpers shared by the pages.

// 1700000000 (unix seconds from the backend) -> "14 Nov 2023"
export const fmtDate = (ts) =>
  ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';

// "https://github.com/owner/repo" -> "owner/repo"
export const repoLabel = (url) => url.replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '');

// {full_name:'Siddhant Shukla'} -> "SS";  {username:'sid'} -> "S"
export const initials = (u) =>
  (u.full_name || u.username || '?').trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();

// number of characters -> "12 KB"
export const kb = (n) => (n / 1024).toFixed(n > 10240 ? 0 : 1) + ' KB';
