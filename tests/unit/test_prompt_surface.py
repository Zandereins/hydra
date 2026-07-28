"""Regression guards for the shipped prompt surface (SKILL.md, README.md, references/).

Three defects, each measured before the guard was written. The unit suite otherwise covers
the bench, not the product: these are the only tests that read a shipped file.

1. README drifting from SKILL.md (PR #39). When the peer-review phase moved into standard
   mode by default (PR #27, `4d19ce0`, 2026-06-29) the README kept advertising the old
   5-agent / 0.35-0.65 default, understating the default mode's cost by ~2x. It survived
   22 days and 12 merged PRs -- including the 13-fix council round (#37) -- until a human
   doc-sync pass caught it (`b9a85ae`). Bisected over all 48 surface-touching commits, the
   two set-parity assertions below fire on exactly that window and nowhere else.

2. `$` before a digit is destroyed at load time (verified 2026-07-28). The skill loader
   expands `$0`, `$1`, ... in SKILL.md as positional arguments of the invocation, so
   `~$0.70-1.20` reached the model as `~<first argument>.70-1.20`. Confirmed by a
   falsifiable prediction: loading with arguments `ZZPROBE QQMARK` rendered `~ZZPROBE.70-1.20`
   and `~QQMARK.50-2.50` at all 10 sites, including the Step 0.9 cost-confirmation banner --
   the one place a wrong figure must never appear. `${...}` forms are left intact, so shell
   positionals stay available as `${1}`. Costs are therefore written `USD 0.70-1.20`.

3. The Common Preamble could not satisfy the rule it ships under. SKILL.md's Prompt Assembly
   Rule requires the resolved instruction portion to contain ZERO `{{...}}` placeholders, but
   the CHAIN format line carried literal `{{file}}` / `{{line_range}}` / ... into every advisor
   prompt, so a faithful orchestrator could never clear the check. Now written `<file>` etc.

Covered: the value SETS of cost strings and agent counts, compared between exactly SKILL.md
and README.md; the absence of `$`-before-digit in both; the absence of unresolved placeholders
in the Common Preamble.

NOT covered, deliberately and with the measurement behind each choice:
  - A pure value SWAP between two modes keeps both sets equal and passes. Zero occurrences in
    48 commits; dict-equality would trade a disclosed gap for format-coupled mode-label parsing.
  - Semantic drift (e.g. a reference file citing the wrong Step number) is not mechanically
    reachable and stays the council's job.
  - The compared pair is CHOSEN, not derived from `scripts/build-plugin.sh` SURFACE. Deriving
    it would trip the vacuum guard on every reference file that legitimately contains no cost
    strings and would need an exemption list. Revisit if a third `.md` enters SURFACE carrying
    cost or agent-count figures.

If a legitimate asymmetry ever makes this red -- e.g. README is trimmed on purpose -- narrow the
pattern deliberately or fix the documents. Do not delete the guard: the drift it catches once
survived 22 days and a full council round unnoticed.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "SKILL.md"
README = REPO / "README.md"
ADVISORS = REPO / "references" / "advisors.md"

# Mode cost figures ("USD 0.70-1.20") plus the deep --no-review point estimate ("USD 1.00").
COST = re.compile(r"USD \d+\.\d{2}(?:-\d+\.\d{2})?")
# Every agent count either document states: "8 agents", "5 agents", "10 to 7 agents".
AGENTS = re.compile(r"\b(\d+)\s+agents?\b")
# The sequence the skill loader expands as a positional argument.
DOLLAR_DIGIT = re.compile(r"\$\d")

# Placeholders the orchestrator resolves per advisor before dispatch (SKILL.md Step 3).
ORCHESTRATOR_RESOLVED = ("{{BOUNDARY}}", "{{YOUR_INITIAL}}")
PREAMBLE_START = "## Common Preamble"
PREAMBLE_END = "## Opus Advisor 1"

# Vacuum guard: below this the pattern has stopped matching the document rather than found
# agreement. An empty set equals an empty set, so a silent format change would otherwise pass
# and leave a green guard that no longer guards anything.
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


def test_cost_and_agent_count_value_sets_match() -> None:
    """Set equality only -- a value swap between two modes keeps both sets equal and passes."""
    _assert_parity(COST, "cost figures")
    _assert_parity(AGENTS, "agent counts")


def test_no_dollar_before_digit_in_shipped_documents() -> None:
    for path in (SKILL, README):
        hits = [
            f"{path.name}:{n}: {line.strip()}"
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if DOLLAR_DIGIT.search(line)
        ]
        assert not hits, (
            "`$` immediately followed by a digit is expanded by the skill loader as a "
            "positional argument and corrupts the text (verified 2026-07-28). Write costs "
            "as `USD 0.70-1.20`; for shell positionals use the brace form `${1}`, which the "
            "loader leaves intact. Offending lines:\n" + "\n".join(hits)
        )


def test_common_preamble_has_no_unresolved_placeholders() -> None:
    text = ADVISORS.read_text()
    for marker in (PREAMBLE_START, PREAMBLE_END):
        assert marker in text, (
            f"advisors.md no longer contains {marker!r}, so this guard can no longer locate "
            "the Common Preamble. Fix the marker; do not delete the test."
        )
    block = text[text.index(PREAMBLE_START) : text.index(PREAMBLE_END)]
    for placeholder in ORCHESTRATOR_RESOLVED:
        block = block.replace(placeholder, "resolved")
    leftover = sorted(set(re.findall(r"\{\{[^{}]*\}\}", block)))
    assert not leftover, (
        "SKILL.md's Prompt Assembly Rule requires the resolved instruction portion to contain "
        "ZERO `{{...}}` placeholders, but the Common Preamble still carries "
        f"{leftover} after resolving {list(ORCHESTRATOR_RESOLVED)}. Either write them as "
        "`<angle brackets>` if they are illustrative, or add them to ORCHESTRATOR_RESOLVED "
        "if the orchestrator is expected to substitute them."
    )
