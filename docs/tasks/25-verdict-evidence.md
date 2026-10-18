# Task 25 — evidence for reviewer verdicts at Agungi and the Agric/AFA bridge

Context: `docs/SITES_PLAN.md` (read "Status (2026-10-17)" first). Each site page ends in a reviewer verdict on whether the
human cause that people named is supported. Alpha Beach and Oko-Oba have verdicts. Agungi (`agungi-collector`) and Agric/AFA
bridge (`agric-bridge`) are next. Your job is the research. I write the verdicts, so **don't edit `events/sites.json`,
`events/promises.json` or any dossier**.

## The claims to test (from `events/sites.json`)
- **agungi-collector:** Wahab (Jun–Jul 2024) said the Agungi Road collector is too small and that development outgrew the drainage.
  Questions:
  1. When was the existing collector built, and to what size?
  2. Has a new or larger collector been started or finished since 27 Jun 2024? Give dates, contractor and where.
  3. What did the Jun 2026 demolitions on Agungi/Ajiran actually remove, and was the Ajiran outfall reopened?
  4. Did Agungi flood again in 2025 or 2026? Give dates, depth notes and sources.
- **agric-bridge:** a resident (OSU, 29 Sep 2025) blamed the AFA bridge construction on Agric–Isawo Road for worsening the
  Aug 2025 flood.
  Questions:
  1. When did construction start?
  2. Did the works narrow, dam or divert the Afa river/channel? Look for coffer dams, temporary crossings, or spoil in the channel.
  3. Did residents or officials report flooding at the site in 2024, 2025 or 2026, before and after the inbound opening
     (8 Sep 2026)?
  4. Did anyone official answer the obstruction claim?

## Sources
- **Allowed:** official sources (MoE, Drainage Services, Ministry of Works, the Governor, commissioners' X posts) and news.
- **Reading pages:** Task 03 rules. Each quote is ≤ 25 words, verbatim, with its read status. Use Wayback for dead links.
- **Photos and video:** describe what they show. Don't download them.
- **Imagery:** list any Esri Wayback releases newer than the latest acquisition already in
  `events/drainage_sites/<site>/` (Agungi 2024-11-30, Agric 2025-04-30). Give the release ID and acquisition date, using the
  method in `pipeline/site_imagery.py`. Don't fetch the chips; Droid does that later.

## Output
`events/verdict_evidence.json`, with:
- `meta`: method, `searched_until`, and the sources list with read status.
- `sites.<site_id>.findings[]`: for each one give `question`, `answer`, `confidence` (`high`, `medium` or `low`) and
  `sources[]` (`url`, `publisher`, `date`, `quote`).
- `new_wayback[]`.
- `draft_verdict`: two or three sentences, which I will rewrite. It should say what the evidence supports and what it can't show.

Say "not found" rather than guessing. Don't touch other files. No background processes. Don't commit.
Finish with a short table: one row per question, with answer, confidence and number of sources.
