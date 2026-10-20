# Task 36: plain-language event text (UI/UX pass, part 4)

Read `docs/design/WORDS.md` first. The audience is residents and journalists.

## Why
The One flood view is now in plain words, but three kinds of text come straight from each `events/lagos-*/event.json` and still read like lab notes:
- `cause_prelim`, for example "Intense rain on saturated ground (IMERG core 19–31 mm/h over Apapa/Mile 2, 06:00–08:30); tidal lock unlikely for the morning…";
- `open_questions`;
- `key_events[].name`, for example "Sentinel-1A radar pass".

That technical text is the record and must stay. This task adds a plain version next to it.

## What to do
1. **Add plain fields** to each of the five `events/lagos-*/event.json` files (2011, 2021, 2022, 2024, 2025). Only add fields; change nothing that's already there.
   - **`cause_plain`:** 1–2 sentences, at most 45 words, for a resident. It covers what fell, when, on what kind of ground, and whether the tide likely made it worse.
   - **`open_questions_plain`:** one plain sentence per open question, in the same order and with the same count.
   - **`key_events[].name_plain`:** only where `name` has jargon. For example, "Sentinel-1A radar pass" becomes "Radar satellite passes over".
2. **Faithfulness rules.** These are strict, because this text is the evidence.
   - No new facts. Every claim in a plain sentence must be in the original.
   - Numbers: keep them exactly or leave them out. Never round in a way that changes the meaning. "19–31 mm/h" can become "up to about 30 mm an hour", but not "very heavy rain of 50 mm".
   - Keep uncertainty words ("likely", "possible", "unverified", "unknown").
   - Drop source and model names (IMERG, EOT20, AOI, S1A, ClimaMeter, NiMet). Keep "news reports said…" where the original credits a publication.
   - Use the WORDS.md wording: "high tide during heavy rain" for tidal lock or rain–tide compounding, and "radar satellite" for Sentinel-1.
3. **Loader and types.** `src/events/load.ts` and `src/events/types.ts` read the new fields as optional: `causePlain`, `openQuestionsPlain` and `KeyEvent.namePlain`. If a field is missing, fall back to the original.
4. **Display.**
   - `EventOverview.tsx` shows the plain cause and plain questions.
   - Under them, add a folded "Technical detail" toggle (`aria-expanded`) that shows the original `cause_prelim` and `open_questions` word for word.
   - `KeyEvents.tsx` shows `namePlain`, with the original `name` on hover.
   - The lead sentence logic in EventOverview may use `cause_plain` if that improves it. Say if you change it.

## Files you own
- the five `events/lagos-*/event.json` files (add fields only);
- `src/events/load.ts`, `src/events/types.ts`;
- `src/components/EventOverview.tsx`, `src/components/KeyEvents.tsx`, and `src/styles/flood.css`.

Droid is working in parallel on `SitePanel.tsx`, `SiteHistory.tsx`, `SiteTimeline.tsx` and `MapView.tsx`. Don't touch them.

If a schema or a pipeline script validates `event.json`, check it still passes:
- `grep -rn "event.json" pipeline/*.py | head`;
- run any validator that you find.

## Check
- `npx tsc --noEmit` and `npm run build` pass.
- `python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('events/lagos-*/event.json')]"` passes.
- `git diff events/` shows only added lines.
- **Report:** a table for every event. Each row gives the original text, then your plain version. I will review each one against the original.
- No browser tools.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
