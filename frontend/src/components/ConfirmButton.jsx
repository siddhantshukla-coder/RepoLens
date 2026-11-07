import { useEffect, useState } from 'react';

// NEW in v1.1. A two-step button for destructive actions: the first click "arms" it
// (the label changes), a second click within 4 seconds really does it. No pop-up needed.
export default function ConfirmButton({
  children, onConfirm, confirmText = 'Click again to confirm', className = 'btn ghost', disabled = false,
}) {
  const [armed, setArmed] = useState(false);

  // disarm automatically so a forgotten first click can't turn into an accidental delete later
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);

  return (
    <button
      type="button" disabled={disabled}
      className={className + (armed ? ' danger' : '')}
      onClick={() => { if (armed) { setArmed(false); onConfirm(); } else setArmed(true); }}
    >
      {armed ? confirmText : children}
    </button>
  );
}
