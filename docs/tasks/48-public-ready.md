# Task 48: ready for the public

Read `docs/design/WORDS.md` first: plain words, short sentences, no jargon.

## Why
FloodTrace is going public, for people in Lagos. The repo will become open source, and the site will be on Cloudflare Pages. People may act on what it says, so it must be:
- clear about what it is and isn't;
- legally clean;
- easy to understand on a phone.

## Do
1. **"Not an official warning" notice.**
   - **Where:**
     - one short line on the Coming-up card, near the forecast level;
     - a fuller paragraph in an "About this tool" panel or page, reachable from the header.
   - **The short line says:** this is an independent tool, not a government warning; follow NiMet and Lagos State (LASEMA) advice.
   - **No phone numbers.** None could be confirmed on an official page.
   - **The About text covers:**
     - who made it, as an independent project;
     - what data it uses;
     - how often the forecast was right, linking to the existing trust sentence and its "How we know" details;
     - that reported floods undercount real ones;
     - how to report a mistake: a link to GitHub issues at `https://github.com/salamituns/FloodTrace/issues`.

     Keep it under 200 words.
2. **README for the public repo.** Rewrite `README.md` for two readers:
   - a Lagos resident who lands there: what the site does, with a link placeholder `https://floodtrace.pages.dev` (TODO until it's live);
   - a developer: how to run the app, how the pipeline works (point to `docs/FORECAST.md` and `docs/MODEL_COMPARE.md`), and the data sources with their licences.

   Keep it short.
3. **Licences.**
   - Add `LICENSE`: MIT for the code.
   - Add `DATA_LICENSE.md`:
     - FloodTrace's own derived data is CC BY 4.0;
     - list each upstream source with its licence and the attribution it requires: ECMWF and GloFAS via Open-Meteo (CC BY 4.0), NASA IMERG, EOT20, OpenStreetMap (ODbL), Copernicus Sentinel, and anything else you find in `meta` blocks and `docs/`.
   - OSM is ODbL: say plainly which files contain OSM-derived data.
4. **News quotes audit.** Search every committed file that stores text from news articles: media evidence, flood spots, event files, and whatever else `git grep` finds.
   - **Report:** the number of stored quotes, the longest in words, and how many are over 25 words.
   - Any quote over 25 words: trim it to the shortest span that still supports the claim it backs (the depth, the place, the date). Keep the source link.
   - **Never store full article bodies.** If any file holds article text beyond short quotes, report it and remove the body, keeping the URL, publisher, date and title.
   - Make the trims in the pipeline builders too, so a rebuild doesn't bring the long text back. Rerun the affected builders.
5. **Phone check (code-level).**
   - Look at the main screens at 360 px in the CSS.
   - Make sure the notice, the About panel and the Coming-up card don't overflow.
   - Make sure tap targets are at least 40 px.

   I'll check it in a browser afterwards.

## Check
- `npx tsc --noEmit`, `npm run build`, `npx tsx scripts/check-watchlist.ts` and `npx tsx scripts/check-forecast.ts` all pass.
- `git grep -n "767\|112"` in `src/` shows no emergency numbers.
- **Report:**
  - the exact notice text and the About text;
  - the quote-audit numbers, before and after;
  - the files changed.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit or push.
- Don't read `.env`.
- Don't start a dev server or open a browser.
- Droid is working on Task 47 in `pipeline/imerg*.py`, `pipeline/forecast.py`, `pipeline/run_daily.py`, `pipeline/tide_*.py`, `.github/` and `docs/FORECAST.md`. Don't touch those.
