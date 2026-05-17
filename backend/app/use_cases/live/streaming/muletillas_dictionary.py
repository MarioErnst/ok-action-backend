"""Spanish filler-word dictionary and transcript matcher.

The live supervisor feeds final transcripts coming back from AssemblyAI
into `extract_muletillas`, which returns one match per filler-word
occurrence with enough context for the WS strike payload.

Why this lives here and not somewhere generic:

- The dictionary is product-specific (Spanish-LatAm filler vocabulary
  the team cares about pedagogically). It is not a general NLP table.
- It is the only place that needs to evolve as we collect false
  positives and false negatives in real sessions.
- Keeping it in the use_cases layer means the matcher can be tested
  without any AssemblyAI or genai SDK in the import graph.

Implementation notes:

- Matching is case-insensitive and punctuation-insensitive at the
  token level. We tokenize once per transcript.
- Unigrams cover the bulk of muletillas. Bigrams cover compound
  fillers ("o sea", "o sé").
- We do not try to disambiguate context-dependent words (e.g. "como"
  can be a filler or a normal preposition). Filtering by context
  produces brittle heuristics — for v1 we keep the conservative list
  below and accept the occasional false positive on commonly-ambiguous
  words. The list is easy to trim if a specific token shows up too
  often as noise in real sessions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Single tokens that count as muletilla on every occurrence. Lowercase.
# Kept narrow on purpose: include only tokens that are overwhelmingly
# used as fillers, even at the cost of missing the long tail.
SPANISH_FILLER_UNIGRAMS: frozenset[str] = frozenset(
    {
        "eh",
        "ehh",
        "ehhh",
        "este",
        "esto",
        "esta",
        "mmm",
        "mm",
        "mmmm",
        "ah",
        "ahh",
        "ahhh",
        "viste",
        "tipo",
        "pues",
        "digamos",
    }
)


# Compound fillers. Bigrams are matched by consecutive lowercase token
# pairs after tokenization.
SPANISH_FILLER_BIGRAMS: frozenset[tuple[str, str]] = frozenset(
    {
        ("o", "sea"),
        # AssemblyAI sometimes transcribes the unstressed "sea" as the
        # stressed "sé" form. Accept both so we do not miss occurrences.
        ("o", "sé"),
    }
)


@dataclass(frozen=True)
class MuletillaMatch:
    """One detected filler-word occurrence inside a transcript.

    `word` is the canonical lowercase form (unigram token or the
    space-joined bigram pair). `start_char`/`end_char` are byte
    positions inside the original transcript string so the UI can
    underline the exact segment. `context_snippet` is the surrounding
    sentence-ish fragment we send back to the client as evidence.
    """

    word: str
    start_char: int
    end_char: int
    context_snippet: str


# Tokenizer that yields (token_lower, start_char, end_char) tuples.
# Matches sequences of letters (including Spanish accents/ñ) so
# punctuation does not stick to tokens. The original substring is
# preserved by indexing back into the transcript with the char range.
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", re.UNICODE)


def _tokenize(transcript: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0).lower(), match.start(), match.end())
        for match in _WORD_RE.finditer(transcript)
    ]


def _context_snippet(transcript: str, start_char: int, end_char: int) -> str:
    """Return ~60 chars of surrounding context, trimmed at word edges."""

    window = 30
    lo = max(0, start_char - window)
    hi = min(len(transcript), end_char + window)
    # Trim ragged whitespace and leftover punctuation at the edges so
    # the snippet reads like a clean fragment in the UI.
    return transcript[lo:hi].strip(" \t\n\r,.;:!?¿¡-")


def extract_muletillas(transcript: str) -> list[MuletillaMatch]:
    """Return every muletilla occurrence in the order it appears.

    Empty or whitespace-only transcripts return an empty list. Bigrams
    are matched before unigrams when they overlap so that "o sea"
    counts once as a bigram instead of also counting "o" alone (which
    is not in the unigram list anyway, but the logic is robust against
    future additions).
    """

    if not transcript or not transcript.strip():
        return []

    tokens = _tokenize(transcript)
    matches: list[MuletillaMatch] = []

    consumed_until_index = -1  # last token index already consumed by a bigram

    for index, (token, start_char, end_char) in enumerate(tokens):
        if index <= consumed_until_index:
            continue

        # Bigram check: try this token + the next one as a pair.
        if index + 1 < len(tokens):
            next_token, _, next_end = tokens[index + 1]
            pair = (token, next_token)
            if pair in SPANISH_FILLER_BIGRAMS:
                canonical = f"{token} {next_token}"
                matches.append(
                    MuletillaMatch(
                        word=canonical,
                        start_char=start_char,
                        end_char=next_end,
                        context_snippet=_context_snippet(
                            transcript, start_char, next_end
                        ),
                    )
                )
                consumed_until_index = index + 1
                continue

        if token in SPANISH_FILLER_UNIGRAMS:
            matches.append(
                MuletillaMatch(
                    word=token,
                    start_char=start_char,
                    end_char=end_char,
                    context_snippet=_context_snippet(
                        transcript, start_char, end_char
                    ),
                )
            )

    return matches
