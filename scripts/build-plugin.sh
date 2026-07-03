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

# --- TEMPORARY publish (Tasks 2-3 insert manifest + gates ABOVE this line) ---
rm -rf dist/hydra-plugin
mkdir -p dist
mv "$STAGE" dist/hydra-plugin
trap - EXIT
echo "OK (partial): staged $(find dist/hydra-plugin -type f | wc -l | tr -d ' ') files"
