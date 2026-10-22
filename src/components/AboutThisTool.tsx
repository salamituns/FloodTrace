import { useEffect } from 'react';
import { ABOUT_ISSUES_URL, ABOUT_PARAS } from '../lib/about';
import '../styles/places.css';

/** Header panel: what FloodTrace is, what it uses, how to report a mistake. */
export function AboutThisTool({ onClose }: { onClose: () => void }) {
	useEffect(() => {
		const onKey = (e: KeyboardEvent) => {
			if (e.key === 'Escape') onClose();
		};
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [onClose]);

	const last = ABOUT_PARAS[ABOUT_PARAS.length - 1];
	const rest = ABOUT_PARAS.slice(0, -1);

	return (
		<section className="howto howto--about" role="dialog" aria-label="About this tool">
			<header className="howto__head">
				<h2>About this tool</h2>
				<button type="button" className="howto__close" onClick={onClose} aria-label="Close">
					✕
				</button>
			</header>
			{rest.map((p) => (
				<p key={p}>{p}</p>
			))}
			<p>
				{last}{' '}
				<a className="link" href={ABOUT_ISSUES_URL} target="_blank" rel="noreferrer">
					{ABOUT_ISSUES_URL}
				</a>
			</p>
		</section>
	);
}
