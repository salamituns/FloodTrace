import { useEffect, useState } from 'react';

/** A tap/keyboard stand-in for hover notes (`title=`), which phones cannot open. */
export function InfoTip({ label, children }: { label: string; children: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <span className="info-tip">
      <button
        type="button"
        className="info-tip__btn"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        i
      </button>
      {open && (
        <span className="info-tip__pop" role="note">
          {children}
        </span>
      )}
    </span>
  );
}
