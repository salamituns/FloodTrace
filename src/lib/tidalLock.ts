export type TidalLockLevel = 'none' | 'watch' | 'likely';

export interface TidalLockInput {
  /** Rainfall intensity now, mm/h (at the selected analysis point). */
  rainMmH: number;
  /** Rain accumulated over the previous 3 hours, mm. */
  rain3hMm: number;
  /** Modelled ocean tide height now, metres relative to mean sea level. */
  tideM: number;
  /** Tide change over the last hour, metres (+ rising, − falling). */
  tideTrendM: number;
}

/**
 * Is stormwater likely to be "locked in" because the lagoon/sea is too high for outfalls to discharge?
 * Drives the warning on the Conditions card and the shading on the tide chart.
 */
export function tidalLock(input: TidalLockInput): TidalLockLevel {
  // TODO(user): decide when rain + tide together count as a lock-up risk. Things to weigh:
  //   · the tide series is an *offshore* model — Lagos Lagoon lags it (likely 1–3 h) and is damped, so a
  //     rising offshore tide may matter more than its current height;
  //   · what rain rate overwhelms drains (flash-flood guidance often uses ~20–30 mm/h, but the reanalysis
  //     source here smooths bursts to a few mm/h, so thresholds tuned to it would be misleading for IMERG);
  //   · whether recent accumulation (rain3hMm) should count even when it's not raining right now.
  void input;
  return 'none';
}
