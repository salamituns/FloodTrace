# Task 34: a calmer "One flood" view (UI/UX pass, part 2)

Read `docs/design/WORDS.md` first. Its principles and word table apply to every string you write. The audience is residents and journalists first.

## Why
The single-flood view (Incident mode) shows everything at once:
- 8 map layers are on by default, and a purple rain grid covers the city;
- around the map sit a timeline, three charts, Key Events and three side cards;
- the Analysis and Notes tabs are empty, and "+ Add" does nothing;
- the markers have no key: red filled, hollow and blue dots go unexplained;
- the labels use jargon: IMERG, S1, EOT20, "rain–tide conflict", "Focus window", "Cause (prelim.)", and the event id.

The view should answer **"What happened during this flood, hour by hour?"** and stay calm until the user asks for more.

## Files you own (touch nothing else)
- `src/components/RightPanel.tsx`, `LayersPanel.tsx`, `ConditionsCard.tsx`, `EventOverview.tsx`, `Charts.tsx`, `KeyEvents.tsx`, `Timeline.tsx`, `EventSwitcher.tsx`.
- `src/state/store.ts`: only `LAYER_DEFS` (labels, hover notes) and the default `layers` visibility and opacity. Don't change the default `mode`.
- `src/components/MapView.tsx`: only to add the map key (legend) and to use the new layer labels. Don't change the site layers, the camera or the basemap; Task 35 handles those.
- New: `src/styles/flood.css`, imported from your components. Edit `src/styles.css` only to delete rules your changes make unused.

**Off limits:** `TopBar.tsx`, `App.tsx`, `SitePanel.tsx`, `WatchList.tsx` and the site components. Droid is changing those in parallel. Data files are also off limits.

## A. Right panel: answer first
New order, top to bottom:
1. **What happened** (the rewritten EventOverview):
   - A one-sentence answer built from the event data: title, date, main hours, likely cause, number of reports. Example: "Heavy rain on 3 Jul 2024 flooded roads across Lekki and the mainland; 64 news reports."
   - Then the "Main hours", "Likely cause" and "Still unknown" rows, in plain words.
   - No event id.
   - Long cause text clamps to 3 lines, with "Read more".
2. **Right now** (the rewritten ConditionsCard), for the replay time:
   - Rain now; rain in the last 3 h / 24 h; tide and its direction; "news reports so far: 38 of 64"; last radar pass.
   - A "Read at: <point>" select.
   - Replace "No rain–tide conflict" with a sentence. For example: "Tide was low while rain was heavy, so it wasn't holding water back." Or, if they coincide: "High tide during heavy rain: drains to the lagoon empty more slowly." Use the same logic the badge uses now.
   - Source names go on hover only.
3. **News reports**: the existing EvidenceList.
   - Keep the cause chips and the "Part of site: X →" links, reworded to "Part of place: X →".
   - Use the evidence wording from WORDS.md in the chip hover notes.
   - Add a count and an "Only reports up to now" toggle. It defaults to off, so all reports show.
4. **Map layers**: a collapsed card ("Map layers · 3 on").
   - Use plain labels with hover notes (WORDS.md).
   - Opacity sliders appear only when a layer's row is expanded.

Remove the Analysis and Notes tabs and the tab bar itself.

## B. Calm defaults
- **On:** News reports, Rain (opacity 0.3), Water seen by radar.
- **Off:** Storm cells seen by radar, Drains and canals, Chart points, Building close by.
- **Buildings (3D)** turns on only while in 3D. It isn't shown as a 2D layer.
- Every layer can still be switched on, and the 3D view and the rain legend still work.

## C. Map key
Add a small key in the bottom-left corner, next to the rain legend, folded into one control (e.g. "Key ▾"). It explains each marker style currently drawn:
- filled vs hollow ("reported by now" vs "reported later");
- what each `KIND_COLOR` means (read it from MapView);
- the radar water colour;
- what marker size means (how precisely the place is known).

Show only entries for visible layers.

## D. Bottom strip
- **Charts.** Titles in plain words, with the location and unit, e.g. "Rain at Lekki (mm per hour)", "Tide (m)", "News reports per 3 hours". Source names (IMERG, EOT20) go on hover.
- **Key Events:**
  - Remove "+ Add".
  - Make sure each row's hover or click does something useful: jump the replay to that time, if it doesn't already.
- **Timeline.** Leave the logic alone. Add a hover note on the speed button, and a hint on first view: "Press play to replay the flood".
- **Vertical space.** At heights under 820 px the strip must not push the map below about 55% of the viewport. Let the charts fold, with a "Charts ▾" toggle.

## E. Accessibility for what you touch
- Real buttons.
- A visible `:focus-visible` ring.
- Contrast of at least 4.5:1.
- Folded sections use `aria-expanded`.
- At 390 px wide the right panel stacks below the map with no horizontal scroll. A basic stacked layout is fine.

## Check
- `npx tsc --noEmit` and `npm run build` both pass.
- `grep -rn "later phase\|IMERG\|EOT20\|S1)\|Focus window\|prelim" src/components` shows these terms only inside hover notes (`title=`) or source lines.
- Report:
  - every string you changed, old → new;
  - the final default layer set;
  - any word you needed that WORDS.md lacks.
- No browser tools. I'll check the UI myself.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
