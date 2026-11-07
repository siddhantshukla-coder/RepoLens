import { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

// Renders Markdown text as HTML.
// DOMPurify is essential: the documentation is written by an LLM from somebody
// else's code, so it must never be injected into the page as raw, trusted HTML.
export default function Markdown({ text, className = '' }) {
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(text || '')), [text]);
  return <div className={'md ' + className} dangerouslySetInnerHTML={{ __html: html }} />;
}
