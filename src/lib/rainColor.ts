/** Rain-rate colour ramp (mm/h), light blue → deep blue → purple; transparent when effectively dry. */
export const RAIN_STOPS: { mmH: number; rgb: [number, number, number] }[] = [
  { mmH: 0.5, rgb: [191, 224, 245] },
  { mmH: 2, rgb: [120, 180, 228] },
  { mmH: 5, rgb: [61, 127, 196] },
  { mmH: 10, rgb: [39, 72, 163] },
  { mmH: 20, rgb: [122, 63, 176] },
];

export function rainColor(mmH: number | null): [number, number, number, number] {
  if (mmH === null || mmH < RAIN_STOPS[0].mmH) return [0, 0, 0, 0];
  let i = 0;
  while (i < RAIN_STOPS.length - 1 && mmH >= RAIN_STOPS[i + 1].mmH) i++;
  if (i === RAIN_STOPS.length - 1) return [...RAIN_STOPS[i].rgb, 235];
  const a = RAIN_STOPS[i];
  const b = RAIN_STOPS[i + 1];
  const f = (mmH - a.mmH) / (b.mmH - a.mmH);
  const mix = (k: number) => Math.round(a.rgb[k] + (b.rgb[k] - a.rgb[k]) * f);
  return [mix(0), mix(1), mix(2), Math.round(150 + 85 * Math.min(1, mmH / 10))];
}
