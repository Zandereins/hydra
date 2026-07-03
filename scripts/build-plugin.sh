#!/usr/bin/env bash
set -euo pipefail

# scripts/build-plugin.sh — assemble a clean Claude Code plugin from the skill surface.
# Ships HEAD (committed content), never the working tree. Offline; no billed calls.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# D2 — single-source allowlist: 7 exact tracked paths, no globs.
SURFACE=(
  SKILL.md
  references/advisors.md
  references/chairman-protocol.md
  references/report-template.md
  references/review-protocol.md
  README.md
  LICENSE
)

# D4 — refuse if any surface file differs from HEAD (git archive ships HEAD regardless).
if [ -n "$(git status --porcelain -- "${SURFACE[@]}")" ]; then
  echo "ERROR: surface files differ from HEAD — commit first; the build ships HEAD, your uncommitted edits would NOT be included." >&2
  git status --short -- "${SURFACE[@]}" >&2
  exit 1
fi

# D6.2 — references completeness: SURFACE's references/ must equal HEAD's references/.
surface_refs="$(printf '%s\n' "${SURFACE[@]}" | grep '^references/' | sort)"
head_refs="$(git ls-tree HEAD --name-only references/ | sort)"
if [ "$surface_refs" != "$head_refs" ]; then
  echo "ERROR: SURFACE references/ list drifted from HEAD references/. Update SURFACE." >&2
  diff <(echo "$surface_refs") <(echo "$head_refs") >&2 || true
  exit 1
fi

# Stage in a temp dir; publish at the end.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/skills/hydra" "$STAGE/.claude-plugin"

# D1 — assemble from the committed tree (untracked cruft physically cannot ship).
git archive HEAD -- "${SURFACE[@]}" | tar -x -C "$STAGE/skills/hydra"

# D5 — plugin.json: hardcoded description; no author.email; SHA-stamped version read from HEAD.
PYVER="$(git show HEAD:pyproject.toml | sed -n 's/^version = "\(.*\)"$/\1/p')"
if [ "$PYVER" != "2.0.0a0" ]; then
  echo "ERROR: pyproject version drifted ($PYVER) — update the PEP440->SemVer translation in this script." >&2
  exit 1
fi
SHA="$(git rev-parse --short HEAD)"
cat > "$STAGE/.claude-plugin/plugin.json" <<JSON
{
  "name": "hydra",
  "description": "Multi-perspective code review council: advisors analyze, reviewers cross-examine, chairman synthesizes verdict.",
  "version": "2.0.0-alpha.0+g${SHA}",
  "author": { "name": "Zandereins" },
  "license": "MIT"
}
JSON
python3 -m json.tool "$STAGE/.claude-plugin/plugin.json" >/dev/null  # JSON syntax gate

# D6.1 — exact inventory: exactly the 8 expected files, nothing more.
expected="$(printf '%s\n' \
  ".claude-plugin/plugin.json" \
  "skills/hydra/SKILL.md" \
  "skills/hydra/references/advisors.md" \
  "skills/hydra/references/chairman-protocol.md" \
  "skills/hydra/references/report-template.md" \
  "skills/hydra/references/review-protocol.md" \
  "skills/hydra/README.md" \
  "skills/hydra/LICENSE" | sort)"
actual="$(cd "$STAGE" && find . -type f | sed 's|^\./||' | sort)"
if [ "$expected" != "$actual" ]; then
  echo "ERROR: staged inventory does not match the expected 8 files." >&2
  diff <(echo "$expected") <(echo "$actual") >&2 || true
  exit 1
fi

# D7 — hygiene gate: PR-#24 regression class only (abs-path / OS-username / personal mail).
# Idiom pinned: MUST be `if grep ...; then exit 1; fi` — a bare grep under set -e exits 1 on a CLEAN surface.
if grep -RInE "(/Users/[A-Za-z]|/home/[a-z]|\b$(id -un)\b|[A-Za-z0-9._%+-]+@(gmail|gmx|web|outlook|proton|yahoo)\.[a-z]+)" "$STAGE"; then
  echo "HYGIENE GATE FAILED — offenders above (abs-path / OS-username / personal e-mail must not ship)." >&2
  exit 1
fi

# D8 — publish (two-step; local git-ignored dir) + print the optional BILLED test (no code path runs it).
rm -rf dist/hydra-plugin
mkdir -p dist
mv "$STAGE" dist/hydra-plugin
trap - EXIT
echo "OK: built dist/hydra-plugin ($(find dist/hydra-plugin -type f | wc -l | tr -d ' ') files), version 2.0.0-alpha.0+g${SHA}"
echo "Validate offline (unbilled):     claude plugin validate dist/hydra-plugin"
echo "Optional (BILLED, run manually): claude --plugin-dir dist/hydra-plugin   # live trigger-firing only"
