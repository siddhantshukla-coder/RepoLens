import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import './pages.css';   // v1.1: styles for the nav bar and the new sections (loaded after styles.css)

// Mount the app into <div id="root"> from index.html.
// (React.StrictMode is left out on purpose: in dev it runs effects twice,
// which would start the repo-analysis polling twice.)
createRoot(document.getElementById('root')).render(<App />);
