# Task 34b: fixes to the One flood view

I checked Task 34 in the browser at 1440×900; the direction is right. Fix the items below, keeping the same files, rules and checks as Task 34. Two rows in WORDS.md were updated, so re-read it.

1. **Wrong date in the lead sentence.** It says "Heavy rain on 2 Jul 2024", because `focus.start` is 18:00 on 2 Jul. The flood is known as 3 Jul 2024.
   - Use the event's main day: the date in its id or catalog entry, or the day of peak reports.
   - The main hours row stays as it is.
2. **"Likely cause" isn't clamped.** The full 9-line text shows, and there's no "Read more" link. Check the `causeLong` threshold; anything over about 120 characters should clamp to 3 lines.
3. **The bottom strip overlaps.** The "Charts ▾" toggle is drawn over the "Press play to replay the flood" hint (bottom left, under the timeline). Give each its own line, or put the hint inside the timeline header.
4. **"Rain at lekki" should read "Rain at Lekki".** Use the display name the Read-at select uses for each point.
5. **The rain grid still tints the whole map.** At 06:30 every ~10 km cell paints the city purple or blue, even at 0.3 opacity.
   - Leave cells under 2 mm/h transparent.
   - Cap the default opacity at 0.25.
   - The legend should say "Rain (mm/h), from 2 mm/h".
   - The map should read as a map, with rain showing only where it's heavy.
6. **Wrong label on the GHSL layer.** It must say "Land built over since 2000" with the GHSL note, per the updated WORDS.md. "Building close by" means something else.

**Check:** tsc and the build pass. Report what you changed for each numbered item. No browser tools. Don't commit.
