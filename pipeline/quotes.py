"""Keep stored news quotes short (Task 48).

Quotes are fair-use excerpts, never article bodies. Rebuilds must not
bring a long quote back: clip_quote is applied when reports are written.
"""

from __future__ import annotations

MAX_QUOTE_WORDS = 25

# Shortest span that still holds the claim (place, cause, depth or date window).
# Each trim must be one unbroken run of the original words: a quote is never
# reworded or spliced. The assert below keeps it that way.
# Keys are the over-25-word strings found in the 2024 intake.
_TRIMS: dict[str, str] = {
    (
        "this is coupled with heavy rainfall which the state has been "
        "experiencing on a daily basis since last week, resulting in the "
        "level rise of the Lagos lagoon"
    ): (
        "heavy rainfall which the state has been experiencing on a daily "
        "basis since last week, resulting in the level rise of the Lagos lagoon"
    ),
    (
        "This is coupled with the heavy rainfall which the state has been "
        "experiencing daily since the previous week resulting in the rise in "
        "level of the Lagos lagoon"
    ): (
        "heavy rainfall which the state has been experiencing daily since the "
        "previous week resulting in the rise in level of the Lagos lagoon"
    ),
    (
        "the flooding in his Okota area was huge and caused by the total "
        "blockage of over one kilometre terminating at the communal effort "
        "bridge at Fasheun Drive"
    ): (
        "his Okota area was huge and caused by the total blockage of over one "
        "kilometre terminating at the communal effort bridge at Fasheun Drive"
    ),
    (
        "this happens when the magnitude of rain is so much on the Island "
        "which is discharged into the Lagoon, the water level of the Lagoon rises"
    ): (
        "the magnitude of rain is so much on the Island which is discharged "
        "into the Lagoon, the water level of the Lagoon rises"
    ),
}


for _full, _short in _TRIMS.items():
    assert _short in _full, f"trim is not a verbatim span of its quote: {_short!r}"


def clip_quote(text: str | None) -> str | None:
    """Trim a stored quote to ≤ 25 words, keeping a claim-bearing span when known."""
    if text is None:
        return None
    if not text:
        return text
    text = _TRIMS.get(text, text)
    words = text.split()
    if len(words) <= MAX_QUOTE_WORDS:
        return text
    return " ".join(words[:MAX_QUOTE_WORDS])
