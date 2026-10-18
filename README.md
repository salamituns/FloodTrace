# FloodTrace — Flood Forensic Analysis

A browser tool for reconstructing a flood event over time, modeled on the "FireTrace" wildfire concept
(reference frames in `reference/firetrace-frames/`). Phase 1 implements **Incident mode** for a synthetic
incident: the **Cedar Fork Flood** (levee breach Mar 4 2026 03:40, Millbrook, TN).

## Run

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # typecheck + production bundle
```

## Architecture

- **One clock.** `src/state/store.ts` holds `currentTime`; `App.tsx` advances it while playing. Every panel derives
  from it — the water mesh and buildings subscribe directly (no React re-render), UI panels use `useQuantTime()` (15-min grid).
- **Synthetic data** in `src/data/`: seeded procedural terrain (`terrain.ts`), rainfall → stage → behind-levee level
  (`hydrology.ts`), and the flood model (`flood.ts`) — a bathtub surface that follows river stage on the open bank and
  fills the levee-protected floodplain through the breach behind an advancing front. Inundated area and max extent are precomputed hourly.
- **Scene** in `src/scene/` (react-three-fiber): every grid-aligned mesh (terrain, water, overlays) shares one index buffer;
  the water updates its position/color attributes in place. Trees and buildings are instanced.
- **Water colour** comes from `depthToColor()` in `src/lib/floodColor.ts`, sampled into a lookup table at startup.
- Drones and Resources modes are placeholders for later phases.
