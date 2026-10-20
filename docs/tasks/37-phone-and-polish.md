# Task 37: phone layout, keyboard and contrast (UI/UX pass, part 5)

Read `docs/design/WORDS.md` first. Tasks 33–36 have landed, so read the current files before changing anything.

## Why
At 390 × 844, a phone-sized screen, the app is broken:
- **The page is about 1,000 px wide**, so it scrolls sideways.
- **The map is squeezed** into a 280 px strip on the left, with the places list beside it.
- **The map attribution** wraps into a tall white box covering half the map.
- **The bottom strip's header** wraps one word per line.

Residents and journalists will mostly open shared links on phones, so this matters as much as the desktop work.

## Files you own
Every component and stylesheet in `src/` that the layout needs. Droid is idle, so nothing runs in parallel. Don't change the following:
- data files;
- the rules in `watchList.ts`;
- any wording that already follows WORDS.md, unless a phone layout truly needs a shorter form. List any such change.

## A. Phone layout (width ≤ 720 px)
Stack the screen in a single column with **no horizontal scroll anywhere**:
1. **Top bar**, compact.
   - Show the logo, then the two mode buttons as a segmented control, then a "⋯" or icon buttons for Copy link and How to read this.
   - In One flood mode, put the event switcher on a second row.
2. **Map**, full width.
   - Height about 40 vh for Places and a place page, about 45 vh for One flood.
   - Collapse the attribution to the (i) button.
   - Keep the zoom controls, 2D/3D and Key reachable, without overlapping each other.
3. **Panel content**, full width, below the map.
   - Places: the list.
   - A place: the page.
   - One flood: What happened, Right now, News reports, Map layers.
4. **Bottom strip:**
   - **One flood.** Put the timeline's play control and scrubber directly under the map, kept visible with `position: sticky` while the panel scrolls, so the replay can still be driven. Put the charts and Key Events below the panel, both folded by default.
   - **Places / a place.** Fold the years timeline into a "Timeline ▾" section at the end, or let it scroll horizontally inside its own box with the row labels sticky. Pick one and say why.
5. **Tap targets** are at least 40 × 40 px. Hover notes (`title=`) aren't available on touch, so any hover note that carries meaning must also be reachable by tap: an (i) toggle or the existing expanders. Cover the watch-list column headers, the priority badge and the layer notes.
6. **Selecting a place on the map** (phone) scrolls the page to the place's panel.

## B. Mid widths (721–1100 px)
- The side panel keeps a usable width of at least 320 px.
- The map shrinks, not the panel.
- Nothing overlaps at 1024 × 768.

## C. Keyboard and screen readers (all widths)
- **Tab order** follows reading order: top bar → panel → map controls → timeline.
- **Focus.** Every interactive element has a visible `:focus-visible` ring.
- **Places list rows** open with Enter or Space, and the reasons expander is a separate tab stop.
- **Esc** closes How to read this, the Key, and any open "change" date picker.
- **Landmarks.** The map gets an `aria-label` describing what it shows ("Map of Lagos places that flood"). The list and the place page use headings in order, with no skipped levels.

## D. Contrast and colour
- Check every text/background pair you touch, and the existing small grey hint text (`.card__hint`, the timeline years). Each needs at least 4.5:1; large text needs 3:1.
- The ✓ / ✗ signs and the priority badges must not rely on colour alone. They already use shape and text; keep it that way.

## E. Small leftovers from my review
- **Overlapping street labels.** On a place page at street zoom, the basemap's street and area labels (e.g. "AGUNGI") can sit under our place label. If the basemap style lets you, hide basemap labels within about 60 px of the selected place's label. Otherwise leave it and say so.
- **Reading time.** `Our reading` and `Likely cause` clamp to 3 lines. Check that "Read more" works on touch and by keyboard.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- **No horizontal overflow.** In your report, state for each of these that `document.documentElement.scrollWidth <= window.innerWidth`:
  - widths: 390, 768, 1024, 1440;
  - screens: Places, a place page (`#site=agungi-collector`), One flood (`?event=lagos-2024-07-03`).
- **How to check.** Compute it from the CSS by reasoning, or with a throwaway headless script that you delete afterwards. You may use Playwright through the project's own `npx` **only if** it is already installed. Don't install anything, and if it isn't there, say so.
- **Report** the layout decisions you made and any wording you shortened.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
