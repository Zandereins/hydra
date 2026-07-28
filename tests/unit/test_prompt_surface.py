"""Regression guard: README.md must not drift from SKILL.md on cost + agent counts.

SKILL.md is the artifact the agent executes; README.md only documents it. When the
peer-review phase (Step 4) moved into standard mode by default (PR #27, `4d19ce0`,
2026-06-29), the README kept advertising the old 5-agent / ~$0.35-0.65 default and so
understated the default mode's cost by ~2x. That survived 22 days and 12 merged PRs --
including the 13-fix council round (#37) -- until a human doc-sync pass caught it
(PR #39, `b9a85ae`). Both files are part of the shipped plugin surface
(`scripts/build-plugin.sh` SURFACE), so the wrong numbers reached every built plugin too.

Nothing tested this: the unit suite covers the bench, and no test reads SKILL.md at all.

The guard compares SETS over the whole file rather than parsing the Modes tables, so it
covers the table, the modifier prose and the FAQ alike and survives reformatting. A bisect
over all 48 surface-touching commits shows these two assertions fire on exactly the
`4d19ce0`..`dcdf6c5` window and nowhere else -- zero false positives across the history.

Known and accepted blind spot: a pure SWAP of values between two modes keeps the sets
equal and would pass. That has never occurred in the repo's history.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "SKILL.md"
README = REPO / "README.md"

# Mode cost ranges ("$0.70-1.20") plus the deep --no-review point estimate ("$1.00").
COST = re.compile(r"\$\d+\.\d{2}(?:-\d+\.\d{2})?")
# Every agent count either document states: "8 agents", "5 agents", "10 to 7 agents".
AGENTS = re.compile(r"\b(\d+)\s+agents?\b")

# Vacuum guard: below this the pattern has stopped matching the document rather than
# found agreement. An empty set equals an empty set, so a silent format change would
# otherwise pass and leave a green guard that no longer guards anything.
MIN_MATCHES = 3

_FIX = (
    "SKILL.md is the source of truth (it is what the agent executes) -- update README.md "
    "to match. If you changed SKILL.md deliberately, pull README.md along; do not weaken "
    "this test."
)


def _assert_parity(pattern: re.Pattern[str], what: str) -> None:
    skill: set[str] = set(pattern.findall(SKILL.read_text()))
    readme: set[str] = set(pattern.findall(README.read_text()))
    for name, found in (("SKILL.md", skill), ("README.md", readme)):
        assert len(found) >= MIN_MATCHES, (
            f"{what}: only {len(found)} distinct match(es) in {name} -- the document "
            "format changed and this guard no longer reads it. Fix the pattern; do not "
            "delete the test."
        )
    assert skill == readme, (
        f"{what} drifted -- only in SKILL.md: {sorted(skill - readme)}; "
        f"only in README.md: {sorted(readme - skill)}. {_FIX}"
    )


def test_cost_strings_match_between_skill_and_readme() -> None:
    _assert_parity(COST, "cost strings")


def test_agent_counts_match_between_skill_and_readme() -> None:
    _assert_parity(AGENTS, "agent counts")
