/** Public-facing notice copy (Task 48). Keep it plain; no emergency numbers. */

export const OFFICIAL_NOTICE =
	'This is an independent tool, not a government warning. Follow NiMet and Lagos State (LASEMA) advice.';

export const ABOUT_ISSUES_URL = 'https://github.com/salamituns/FloodTrace/issues';

export const ABOUT_PARAS: string[] = [
	'FloodTrace is an independent project. It is not from NiMet, LASEMA, or any other government body.',
	'It uses news reports of floods in Lagos, satellite rain from NASA, weather forecasts from ECMWF and GloFAS via Open-Meteo, tide from EOT20, street maps from OpenStreetMap, and radar pictures from Copernicus Sentinel.',
	'How often the day-before forecast was right is on the Coming-up card, under “How much to trust this”. Open “How we know” for the numbers.',
	'Reported floods undercount real ones. A quiet map is not proof a street is safe.',
	'If you spot a mistake, report it on GitHub Issues.',
];

export const ABOUT_TEXT = ABOUT_PARAS.join(' ');

export function aboutWordCount(): number {
	return ABOUT_TEXT.split(/\s+/).filter(Boolean).length;
}
