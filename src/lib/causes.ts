import type { CauseAttribution, CauseTag, CitywideCause, EvidenceItem } from '../events/types';

/** Display order runs from natural causes to human ones, so the split reads at a glance. */
export const CAUSES: { tag: CauseTag; label: string; human: boolean }[] = [
  { tag: 'heavy_rain', label: 'Heavy rain', human: false },
  { tag: 'lagoon_tide', label: 'Lagoon / tide', human: false },
  { tag: 'ocean_surge', label: 'Ocean surge', human: false },
  { tag: 'low_lying_terrain', label: 'Low-lying land', human: false },
  { tag: 'canal_overflow', label: 'Canal / river overflow', human: false },
  { tag: 'blocked_drainage', label: 'Blocked drains', human: true },
  { tag: 'drainage_capacity', label: 'Inadequate drains', human: true },
  { tag: 'setback_encroachment', label: 'Building on setbacks', human: true },
  { tag: 'construction', label: 'Construction / works', human: true },
  { tag: 'land_reclamation', label: 'Land reclamation', human: true },
  { tag: 'dam_release', label: 'Dam release', human: true },
];

const LABEL = Object.fromEntries(CAUSES.map((c) => [c.tag, c.label])) as Record<CauseTag, string>;
export const causeLabel = (tag: CauseTag) => LABEL[tag] ?? tag.replace(/_/g, ' ');

export interface CauseCount {
  tag: CauseTag;
  label: string;
  human: boolean;
  total: number;
  official: number;
}

/** Counts per cause across mapped reports and citywide statements; causes nobody named are dropped. */
export function countCauses(evidence: EvidenceItem[], citywide: CitywideCause[]): CauseCount[] {
  const claims: { causes: CauseTag[]; by: CauseAttribution | null | undefined }[] = [
    ...evidence.map((e) => ({ causes: e.props.causes ?? [], by: e.props.cause_attributed_by })),
    ...citywide.map((c) => ({ causes: c.causes, by: c.cause_attributed_by })),
  ];
  return CAUSES.map((c) => {
    const hits = claims.filter((x) => x.causes.includes(c.tag));
    return { ...c, total: hits.length, official: hits.filter((x) => x.by === 'official').length };
  }).filter((c) => c.total > 0);
}
