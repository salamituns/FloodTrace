# Task 33: front door, navigation and the places list (UI/UX pass, part 1)

Read `docs/design/WORDS.md` first. Its principles and word table apply to every string you write. Audience: residents and journalists first.

## Why
A first-time visitor lands on a dense map of one 2024 flood and gets no explanation.
- **Dead controls.** Imagery, Response, View, Analysis, Share and Settings either do nothing or are disabled.
- **Duplicated lists.** The same 13 places appear twice in the Sites view, in two different orders: the watch list and the site list.
- **Unclear watch list.** Its ticks have no column labels, and nothing says whether "Tier 3" is good or bad.

## Files you own (touch nothing else)
- `src/components/TopBar.tsx`, `src/App.tsx`
- `src/components/WatchList.tsx`
- `src/components/SitePanel.tsx`: only `SiteList`, the `SitePanel` container, and the no-site-selected branch. Leave `SiteDetail`, `BeforeAfter` and `Sparkline` alone; Task 35 rewrites them.
- `src/lib/watchList.ts`: reason **strings** only. The rules block and the logic stay exactly as they are.
- `scripts/check-watchlist.ts`: update its regexes to the new reason strings.
- New: `src/components/HowToRead.tsx`, `src/styles/places.css`
  - Import the CSS from your components.
  - Edit `src/styles.css` only to delete rules your changes made unused.
- `src/components/Icons.tsx` (add icons only).

**Off limits:**
- `store.ts`, `MapView.tsx` and every component of the One flood view. Cursor is changing those in parallel.
- `sites.json`, `promises.json` and every other data file.

## A. Front door
1. **Landing view.** With no `?event=` in the URL and no hash, open on **Places that flood** (`setMode('sites')` from `App.tsx`; leave the store's default alone).
   - `?event=…` still opens **One flood**.
   - `#site=…` still opens that place.
2. **Top bar:**
   - Brand: "FloodTrace" plus a short subtitle: "Lagos: where it floods, why, and what was fixed".
   - Mode switch: two buttons, **Places that flood** and **One flood**, with hover notes from WORDS.md.
   - Remove the Imagery and Response buttons and the View, Analysis, Share and Settings menus.
   - Add **Copy link**, which copies `location.href` and shows "Link copied" for 2 s. Ask nothing of the user.
   - Add **How to read this** (a `?` icon plus text), which opens HowToRead.
   - In One flood mode, keep the event switcher and the date as they are now.
3. **HowToRead:**
   - A short, dismissible panel over the side panel, shown automatically on the first visit only.
     - Remember the dismissal in `localStorage`, wrapped in try/catch.
     - If storage fails, show the panel and allow dismissal for this session only.
   - Content, at most about 90 words:
     - What FloodTrace is, in one sentence.
     - Three numbered steps: pick a place, read how often it floods / what was blamed / whether the fix happened, open a flood to replay it hour by hour.
     - The colour key from WORDS.md principle 7.
     - One caveat line: we only know about floods that made the news.
   - Esc and a close button dismiss it.
   - The **How to read this** button reopens it.

## B. One list of places (no place selected)
Replace the watch-list card plus the Sites card with **one card**, titled **Places that flood**.
1. **Answer line at the top**, computed. For example: "2 places show all three warning signs: Olopo Meji and Agungi."
2. **Column header row** with the three signs: **Floods often · Drains blamed · Not fixed**.
   - Each column header gets a hover note from WORDS.md.
   - Each cell shows ✓ or ✗ with an accessible label, e.g. "Floods often: yes".
3. **Each row:**
   - A priority badge (High, Medium, Low or Lowest, from the tier, per WORDS.md), with shape and colour both carrying the meaning.
   - The place name.
   - A second line: "N flood days reported · last Mon YYYY · promise <status>". Leave out any part that has no data.
   - Clicking the row opens the place.
   - **why?** becomes a chevron that expands the three reasons in plain words. It must not open the place.
4. **Order:** priority, then the watch list's tie-breaks.
   - Add a small "Sort: Priority | Most flood days | A–Z" control. "Most flood days" must reproduce the old site list order.
5. **As-of date:** a small line under the answer, "Ranked as of 1 Mar 2026 · change". "change" reveals the date input. Keep the current default rule.
6. **Footer:** "Ranks places by what's on record, not by forecast. A place with no reports can still flood."
7. **Reason strings in `watchList.ts`:** reword to WORDS.md. For example:
   - "7 flood days reported; last 28 Jun 2026";
   - "The Environment Commissioner blamed blocked drains, and imagery agrees";
   - "No promise on record".
   - Update `check-watchlist.ts` to match. All its checks must still pass.

## C. Accessibility basics for what you touch
- Real `<button>`s.
- A visible `:focus-visible` ring.
- Text contrast of at least 4.5:1.
- At phone width (390 px), the card and the top bar fit with no horizontal scroll. The top bar may collapse its subtitle.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- `grep -rn "Tier \|strong pluvial\|Imagery</\|Response</" src/components src/lib` finds nothing on screen.
- Report:
  - every string you changed, old → new;
  - any word you needed that WORDS.md lacks.
- No browser tools; I'll check the UI myself.

## Rules
- Foreground only. No `rm -rf`. Don't commit.
