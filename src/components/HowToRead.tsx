import { useEffect } from 'react';
import '../styles/places.css';

/** The front door's short guide (Task 33): what FloodTrace is, three steps, the colour key, one caveat.
 *  Dismissed with the close button or Esc; TopBar shows it automatically on a first visit only. */
export function HowToRead({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <section className="howto" role="dialog" aria-label="How to read this">
      <header className="howto__head">
        <h2>How to read this</h2>
        <button className="howto__close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </header>
      <p>FloodTrace tracks floods in Lagos: where the water went, what was blamed, and what was fixed.</p>
      <ol className="howto__steps">
        <li>Pick a place that floods.</li>
        <li>Read how often it floods, what was blamed, and whether the fix happened.</li>
        <li>Open a flood to replay it hour by hour.</li>
      </ol>
      <ul className="howto__key">
        <li>
          <span className="howto__dot howto__dot--red" aria-hidden="true" /> Red: flood reported.
        </li>
        <li>
          <span className="howto__dot howto__dot--amber" aria-hidden="true" /> Amber: promise not kept.
        </li>
        <li>
          <span className="howto__dot howto__dot--green" aria-hidden="true" /> Green: delivered or fixed.
        </li>
        <li>
          <span className="howto__dot howto__dot--blue" aria-hidden="true" /> Blue: water and rain.
        </li>
        <li>
          <span className="howto__dot howto__dot--grey" aria-hidden="true" /> Grey: unknown or not checked.
        </li>
      </ul>
      <p className="howto__caveat">We only know about floods that made the news.</p>
    </section>
  );
}
