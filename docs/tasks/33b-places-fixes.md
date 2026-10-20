# Task 33b: fixes to the places list and How to read this

I checked Task 33 in the browser at 1440×900. The direction is right; fix these. Same files, rules and checks as Task 33. WORDS.md has two updated rows; re-read it.

1. **Priority sort is wrong.** With "Priority" selected, the order is Lekki–Epe (Medium), Olopo Meji (High), Alapere–Ogudu (Medium), Agungi (High), Oko-Oba (Low)… It must be tier descending, then the watch-list tie-breaks, exactly as `buildWatchList` returns it. Check that "Most flood days" and "A–Z" also sort correctly.
2. **Column headers are misaligned.**
   - "Floods often" and "Drains blamed" sit over the first two tick columns.
   - "Not fixed" wraps onto its own line at the left of the card.
   - Use one grid (or `grid-template-columns`) shared by the header row and every place row, so each header sits exactly over its column at every panel width.
3. **Badge and name run together** ("HighAgungi – Collector"). Add a gap between them.
4. **Names are truncated** ("Lekki–Epe Exp…", "Alpha Beach –…").
   - Let names wrap to two lines rather than cut off.
   - Keep each row compact: put the second line ("6 flood days reported · last 3 Jul 2024 · promise Overdue") on one line where it fits, and let it wrap naturally otherwise.
   - Don't put "promise" on a line by itself.
5. **"Sort: Priority | Most flood days | A–Z" wraps awkwardly** ("Most flood / days", "A– / Z").
   - Fit it on one line, or move it under the answer line as a compact segmented control.
   - Keep the "Places that flood · 13 places" title on one line.
6. **How to read this overflows sideways.** Its content measures 562 px inside a 328 px panel, so every line is cut off on the right. It must wrap, with no horizontal overflow at any width.
7. **Default as-of becomes today.**
   - This list is now the main list of places, but the 1 March default leaves out the whole 2026 season. Olopo Meji shows "5 flood days reported" here and 7 on its own page.
   - Default the ranking to today's date. The line then reads "Ranked as of today · change".
   - "change" keeps the date input and adds one quick option, "1 March (pre-season)", which uses the old rule.
   - Keep the rules in `watchList.ts` as they are.

Check: tsc, build and `check-watchlist.ts` pass. Report what you changed for each numbered item. No browser tools. Don't commit.
