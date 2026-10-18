# FloodTrace — Phase 1: Incident Mode

Build a browser app, **FloodTrace — Flood Forensic Analysis**, modeled on the "FireTrace" wildfire tool whose
screenshots live in `reference/firetrace-frames/` (look at f_01, f_03, f_11, f_19 before starting — match their
layout, density and warm light UI). This phase builds **Incident mode only**. Drones and Resources tabs appear in the
top bar but are disabled placeholders.

## Stack
- Vite + React 18 + TypeScript (strict), in this folder (`/Users/olatunde/FloodTrace`) — scaffold in place, keep `reference/` and this SPEC.
- three + @react-three/fiber + @react-three/drei for the 3D view
- zustand for app state
- recharts for the bottom charts
- No backend. All data is synthetic and generated in `src/data/`.
- Plain CSS with CSS variables (no Tailwind). Font: Inter via Google Fonts.

## The incident (synthetic)
- Name: **Cedar Fork Flood**, ID `TN-CFR-2026-0042`, location "Cedar Fork Valley, TN".
- Time window: **Mar 3 2026 06:00 → Mar 7 2026 06:00** (96 h).
- Story: heavy rain Mar 3 → river rises → **levee breach Mar 4 03:40** on the east bank near "Millbrook" →
  peak crest Mar 4 21:00 → evacuation order Mar 4 04:15 → recession begins Mar 5 12:00 → water below flood stage Mar 6 18:00.

## Architecture (important — everything reads one clock)
- `src/state/store.ts` (zustand): `currentTime` (ms epoch), `playing`, `speed` (1×/4×/16×/60× sim-hours per real second scaled sensibly),
  `viewMode` ('2d' | '3d'), `layers` (record of id → { visible, opacity }), `selectedEventId`.
- `src/data/terrain.ts`: deterministic procedural heightmap (seeded noise, no Math.random) on a ~256×256 grid covering ~6×6 km,
  with a meandering river valley carved along a spline, a floodplain, hills on either side, a town ("Millbrook") on the
  east-bank floodplain, a levee ridge along the east bank. Export `heightAt(x, z)` and the grid.
- `src/data/hydrology.ts`: time series sampled every 15 min for: rainfall rate (mm/h), cumulative rainfall, river stage (m)
  at gauge "CF-01", discharge (m³/s), soil saturation (%). Flood stage = a constant. Export
  `waterSurfaceAt(x, z, t)` — a water surface elevation that follows the river stage, slopes down-valley along the spline,
  and after the breach time spills into the east floodplain (grow the breach-side inundation over a few hours from the breach point).
  Also export `inundatedAreaKm2(t)` (precomputed series) and `depthAt(x,z,t)`.
- `src/data/events.ts`: key events (Rain onset, Levee breach, Evacuation order, Peak crest, Recession begins, Below flood stage), each with time, type, icon, and a map position.
- All panels derive values from `currentTime` via selectors/interpolation — no panel keeps its own copy of time.

## Layout (match the reference proportions)
- **Top bar**: logo + "FloodTrace" + "Flood Forensic Analysis" | incident selector "Cedar Fork Flood ▾" | location | date range |
  mode tabs **Incident** (active) / **Drones** / **Resources** (disabled, with count badges) | View ▾ Analysis ▾ Share ▾ | settings.
- **Center map** (~70% width): 3D scene by default with 2D/3D toggle, zoom readout, fullscreen button, compass top-left, scale bar.
  - Terrain mesh: stylized, flat-shaded, earthy palette; instanced low-poly cone trees on hillsides (not on floodplain/river);
    simple box buildings for Millbrook; labeled place markers (Millbrook, gauge CF-01, a couple of named hills with elevations).
  - **Water mesh**: same grid as terrain; vertex height = max(terrain, waterSurfaceAt), alpha/colour from depth via
    `depthToColor` (see below). Hide where depth ≤ 0. Updates when `currentTime` changes (update the position/color
    attributes in place; don't rebuild geometry).
  - **Flood front path**: a line from the breach point through timestamped waypoints (like the fire path in the reference),
    with labeled pins "Breach Mar 4, 03:40", "Mar 4, 12:00", etc.
  - **Flow vectors** layer: animated streamlines following the river/flood direction (like the wind vectors in f_19).
  - 2D mode: top-down orthographic view of the same scene with a lat/long grid and labels (reference f_11).
  - OrbitControls; sensible initial camera framing the breach + town.
- **Right panel** (tabs Layers / Analysis / Evidence / Notes — only Layers functional):
  - Layers with checkbox + thumbnail swatch + opacity slider: Terrain (3D), Aerial Imagery, Max Flood Extent, Flood Depth (Modeled),
    Flood Susceptibility, Flow Vectors (off by default), Defenses (Levees & Sandbags), Structures, Roads, Administrative Boundaries.
    Wire at least: Max Flood Extent, Flood Depth, Flow Vectors, Defenses, Structures.
  - **Incident Overview** card (name, ID, location, start, end, peak inundation km², cause "Levee breach (prelim.)", status).
  - **Hydrology & Flood Behavior** card (live at currentTime): Rainfall rate, River stage vs flood stage, Discharge, Soil saturation,
    Max depth in town, Flow velocity. Red text when a value is in a dangerous range.
- **Bottom**: Timeline with play/pause/step, speed selector, scrubber with hover time tooltip, day/hour ticks, event markers on the track.
  Right of it, **Key Events** list (+ Add button inert) — clicking jumps `currentTime` and highlights the row.
- **Three charts** under the timeline, each with a vertical cursor at currentTime and the future portion faded/dashed
  (like the reference): **Inundated Area (km²)**, **River Stage (m)** with a dashed flood-stage line, **Rainfall (mm/h)** as bars.

## The user writes one function
Create `src/lib/floodColor.ts` exporting `depthToColor(depthM: number): { color: [number, number, number]; alpha: number }`
(RGB 0–1). Implement only a TEMPORARY placeholder body (constant blue, alpha 0.6) and mark it clearly with
`// TODO(user): ...` explaining it should map depth bands (e.g. ankle / vehicle / life-threatening) to colors.
Everything else must use this function for water coloring so the user's version takes effect everywhere.

## Quality bar
- `npm run build` and `npx tsc --noEmit` must pass with zero errors. Run them and fix until clean.
- 60fps-ish on a laptop: instancing for trees, no per-frame allocations in the water update.
- Keep components small: `src/components/{TopBar,MapView,LayersPanel,IncidentOverview,HydrologyCard,Timeline,KeyEvents,Charts}.tsx`,
  scene pieces under `src/scene/`.
- Add a short `README.md` (run instructions, architecture in 10 lines).
- Do NOT start a long-running dev server and leave it running. Do not commit.
- When finished, print a summary: files created, anything not done, known issues.
