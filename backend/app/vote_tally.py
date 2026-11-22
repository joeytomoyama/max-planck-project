"""Vote tally: a pure function from Votes to the Result (rules per ADR 0001).

No I/O, no clock, no hidden state: the only source of arbitrariness is the
injectable `choose`, used solely to break a tie for the Decision Maker.

Labels are Player Label letters ("A", "B", "C"). Each ballot has a `kind`:
`vote` (counts for its `target`), `abstention` or `missing` (count for nobody).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

VOTE, ABSTENTION, MISSING = "vote", "abstention", "missing"


@dataclass(frozen=True)
class Ballot:
    round_number: int
    voter: str
    kind: str  # vote | abstention | missing
    target: str | None = None  # Player Label letter when kind == vote


@dataclass(frozen=True)
class Result:
    counts: dict[str, int]  # label -> Votes across all Rounds (every label present, 0 if none)
    decision_maker: str
    decided_by_tiebreak: bool  # True when several labels shared the top count


def count_votes(labels: Sequence[str], ballots: Iterable[Ballot]) -> dict[str, int]:
    """Votes per label. Abstentions, missing Votes and unknown targets count for nobody."""
    counts = {label: 0 for label in labels}
    for ballot in ballots:
        if ballot.kind == VOTE and ballot.target in counts:
            counts[ballot.target] += 1
    return counts


def round_summary(labels: Sequence[str], ballots: Iterable[Ballot]) -> dict:
    """One Round's stored `vote_results`: counts per label plus how many abstained / were missing."""
    ballots = list(ballots)
    return {
        "counts": count_votes(labels, ballots),
        "abstentions": sum(1 for b in ballots if b.kind == ABSTENTION),
        "missing": sum(1 for b in ballots if b.kind == MISSING),
    }


def tally(
    labels: Sequence[str],
    ballots: Iterable[Ballot],
    choose: Callable[[Sequence[str]], str] = random.choice,
) -> Result:
    """Combine every Round's Votes. The Decision Maker has the most Votes; a tie
    (including nobody voting at all) is broken by `choose` among the tied labels."""
    if not labels:
        raise ValueError("a Session has at least one Player Label")
    counts = count_votes(labels, ballots)
    top = max(counts.values())
    leaders = sorted(label for label, n in counts.items() if n == top)
    if len(leaders) == 1:
        return Result(counts, leaders[0], False)
    return Result(counts, choose(leaders), True)
