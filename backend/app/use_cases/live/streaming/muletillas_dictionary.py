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
- Two unigram groups: "unambiguous" tokens always count as filler
  (interjections such as "eh", "mmm"), "ambiguous" tokens (e.g.
  "tipo", "este") need contextual disambiguation because they double
  as real Spanish words. The dictionary itself does not decide for
  ambiguous matches — it only flags them via `is_ambiguous` on the
  match record. The caller (today: the streaming supervisor) routes
  ambiguous matches through an LLM classifier before emitting a strike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Single tokens that are overwhelmingly used as fillers and have no
# common alternative meaning that would survive the tokenizer (these
# are mostly interjection-only forms). Match these directly without
# context.
SPANISH_FILLER_UNAMBIGUOUS_UNIGRAMS: frozenset[str] = frozenset(
    {
        "eh",
        "ehh",
        "ehhh",
        "mmm",
        "mm",
        "mmmm",
        "ah",
        "ahh",
        "ahhh",
        "viste",
        "digamos",
    }
)


# Tokens that double as both filler and real Spanish content words.
# Matches against these get tagged with `is_ambiguous=True` so the
# caller can route them through an LLM contextual classifier instead
# of trusting the dictionary alone. Examples:
# - "tipo" is a noun ("ningún tipo de") but also a filler ("y tipo,").
# - "este/esta/esto" are demonstratives ("este auto") but also fillers
#   ("este, lo que pasa..."). Same for "pues" (causal) vs filler.
SPANISH_FILLER_AMBIGUOUS_UNIGRAMS: frozenset[str] = frozenset(
    {
        "este",
        "esto",
        "esta",
        "tipo",
        "pues",
    }
)


# Union exposed for any caller that needs the full token set (e.g.,
# AssemblyAI keyterm boosting). Production code that classifies should
# use the split sets above.
SPANISH_FILLER_UNIGRAMS: frozenset[str] = (
    SPANISH_FILLER_UNAMBIGUOUS_UNIGRAMS | SPANISH_FILLER_AMBIGUOUS_UNIGRAMS
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
    `is_ambiguous` is True when the token doubles as a real Spanish
    content word; the caller should disambiguate via an LLM before
    treating the match as a real strike.
    """

    word: str
    start_char: int
    end_char: int
    context_snippet: str
    is_ambiguous: bool


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
                # All current bigrams ("o sea", "o sé") are unambiguous
                # fillers in Spanish so we tag them accordingly.
                matches.append(
                    MuletillaMatch(
                        word=canonical,
                        start_char=start_char,
                        end_char=next_end,
                        context_snippet=_context_snippet(
                            transcript, start_char, next_end
                        ),
                        is_ambiguous=False,
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
                    is_ambiguous=token in SPANISH_FILLER_AMBIGUOUS_UNIGRAMS,
                )
            )

    return matches
