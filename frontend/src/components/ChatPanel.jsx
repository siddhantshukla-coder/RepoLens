import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import Markdown from './Markdown.jsx';

const SUGGESTIONS = ['What does this project do?', 'How do I run it?', 'Walk me through the main flow'];

// The chatbot. Each question goes to POST /api/chat, which runs your self-RAG
// graph over THIS repo's documentation. The graph can take a while (several LLM
// judge calls), so we show a "Checking the docs" bubble meanwhile.
export default function ChatPanel({ repo }) {
  // Each message: { role: 'user' | 'bot', text, wait?: true, bad?: true }
  const [messages, setMessages] = useState([{
    role: 'bot',
    text: `I’ve read **${repo.name}**. Ask me how a function works, where data flows, or how to run it.`,
  }]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const logRef = useRef(null);
  const inputRef = useRef(null);

  // keep the newest message in view
  useEffect(() => {
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  // give focus back to the box once an answer arrives
  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  async function ask(question) {
    const q = question.trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);
    // add the user's bubble plus a placeholder bubble for the answer
    setMessages((m) => [...m, { role: 'user', text: q }, { role: 'bot', wait: true }]);
    try {
      const r = await api('/api/chat', { method: 'POST', body: { repo_id: repo.id, question: q } });
      setMessages((m) => [...m.slice(0, -1), { role: 'bot', text: r.answer }]);   // replace placeholder
    } catch (err) {
      setMessages((m) => [...m.slice(0, -1), { role: 'bot', text: err.message, bad: true }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <h2>Ask the repo</h2>
          <small>Answers come only from the documentation</small>
        </div>
      </div>

      <div className="log" ref={logRef} aria-live="polite">
        {messages.map((m, i) => {
          if (m.role === 'user') return <div key={i} className="msg user">{m.text}</div>;
          if (m.wait) {
            return (
              <div key={i} className="msg bot">
                <span className="dots"><i /><i /><i /></span>Checking the docs
              </div>
            );
          }
          if (m.bad) return <div key={i} className="msg bot bad">{m.text}</div>;
          return <Markdown key={i} text={m.text} className="msg bot" />;
        })}
      </div>

      <div className="chips">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" disabled={busy} onClick={() => ask(s)}>{s}</button>
        ))}
      </div>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
        <input
          ref={inputRef} value={input} disabled={busy} autoComplete="off"
          placeholder="Ask about a file, function or flow" aria-label="Your question"
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="btn" disabled={busy}>Ask</button>
      </form>
    </div>
  );
}
