# Round 1 votes stay hidden and both Rounds count

The research question is whether Participants pick a Human or an AI Agent as Decision Maker, so each Vote should reflect a Participant's own preference rather than the group's. SPEC.md requires that voting "remains blind until results are published" but does not say how the two Rounds combine. We decided:

1. **Round 1 votes stay hidden.** After voting, Participants only learn that their Vote was recorded. Showing round 1 counts would mix conformity into round 2 votes. Each Round's Votes are an independent measure, and comparing them shows whether preference shifts with more exposure.
2. **Both Rounds count.** The Decision Maker has the most Votes across both Rounds (six in total), which gives each Participant two votes and makes ties rarer than counting round 2 alone. Remaining ties get an arbitrary winner, as SPEC.md states.

Self-votes are allowed, because SPEC.md has Participants vote "for one of the three members".

## Considered Options

- Showing round 1 counts as a straw poll with only round 2 deciding: better for studying opinion change, but confounds the human-vs-AI preference with herding.
- Forbidding self-votes: makes each Vote a cleaner Human-or-AI choice, but SPEC.md allows them.
