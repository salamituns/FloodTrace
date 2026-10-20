import { useLayoutEffect, useRef, useState } from 'react';

/** Three-line clamp with a Read more control that works with a tap or the keyboard. */
export function ClampText({ text, className }: { text: string; className: string }) {
  const [expanded, setExpanded] = useState(false);
  const [needsToggle, setNeedsToggle] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || expanded) return;
    const measure = () => setNeedsToggle(el.scrollHeight > el.clientHeight + 1);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [expanded, text]);

  return (
    <>
      <p ref={ref} className={expanded ? className : `${className} clamp-3`}>
        {text}
      </p>
      {needsToggle && (
        <button type="button" className="read-more" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Read less' : 'Read more'}
        </button>
      )}
    </>
  );
}
