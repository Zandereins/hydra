# Hydra Plugin Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one offline build script that assembles a clean, marketplace-capable Claude Code plugin (`dist/hydra-plugin/`) from only the 7-file skill surface, leaving the dev repo and live skill byte-unchanged.

**Architecture:** A single `scripts/build-plugin.sh` (bash). It stages content from the committed tree via `git archive HEAD` against a single-source allowlist, generates `plugin.json`, runs structural + hygiene gates, then publishes to the git-ignored `dist/`. No billed model call. Built incrementally: the publish line exists from Task 1; Tasks 2–3 insert the manifest and the safety gates *before* it.

**Tech Stack:** bash (`set -euo pipefail`), `git archive`, `tar`, `grep`, `python3 -m json.tool`, `claude plugin validate` (offline, unbilled).

## Global Constraints

Copied verbatim from the spec — every task inherits these:

- **Zero disruption:** root `SKILL.md` + `references/` are READ ONLY; never move or edit them. The live skill loads from `~/.claude/skills/hydra/SKILL.md`.
- **Tracked additions total: exactly 2 files** — `scripts/build-plugin.sh` + the spec (already committed). No `.gitignore` edit (`dist/` already ignored at `.gitignore:5`). No test file is committed — the script's own gates + the acceptance commands are the tests.
- **Offline, deterministic, reproducible:** same HEAD → byte-identical `dist/`. No timestamps, `$HOME`, or hostname in emitted files. **No billed model call anywhere in the script.**
- **Surface (7 files, exact, no globs):** `SKILL.md`, `references/{advisors,chairman-protocol,report-template,review-protocol}.md`, `README.md`, `LICENSE`.
- **Version:** `2.0.0-alpha.0+g<short-sha>`; assert `pyproject` HEAD version == `2.0.0a0`, read from HEAD not the working tree.
- **plugin.json fields:** `name`=`hydra`, `description`=hardcoded, `author`=`{"name":"Zandereins"}` (no `author.email`), `license`=`MIT`.
- **Shell:** `#!/usr/bin/env bash` + `set -euo pipefail` (arrays/pipefail are not POSIX sh).
- **Work location:** worktree branch `feat/plugin-packaging-buildstep` (off `main` @ `2d1feb5`). Never commit to main. Never touch the live `SKILL.md`.

---

### Task 1: Assembly core (D1–D4, D6.2)

Skeleton + single-source `SURFACE` allowlist + dirty-surface refusal + references-completeness assert + `git archive` assembly. A temporary publish line makes the partial script runnable; Tasks 2–3 insert steps before it.

**Files:**
- Create: `scripts/build-plugin.sh`

**Interfaces:**
- Produces: `dist/hydra-plugin/skills/hydra/` containing exactly the 7 surface files, byte-identical to HEAD. A `SURFACE` bash array and a `$STAGE` temp dir that Tasks 2–3 extend.

- [ ] **Step 1: Write the initial script**

Create `scripts/build-plugin.sh`:

```bash
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

# --- TEMPORARY publish (Tasks 2-3 insert manifest + gates ABOVE this line) ---
rm -rf dist/hydra-plugin
mkdir -p dist
mv "$STAGE" dist/hydra-plugin
trap - EXIT
echo "OK (partial): staged $(find dist/hydra-plugin -type f | wc -l | tr -d ' ') files"
```

- [ ] **Step 2: Make it executable and run it (green path)**

Run:
```bash
chmod +x scripts/build-plugin.sh
bash scripts/build-plugin.sh
find dist/hydra-plugin -type f | sed 's|dist/hydra-plugin/||' | sort
```
Expected: `OK (partial): staged 7 files`, and the list is exactly the 7 surface paths under `skills/hydra/`.

- [ ] **Step 3: Verify byte-identity**

Run:
```bash
cmp SKILL.md dist/hydra-plugin/skills/hydra/SKILL.md && cmp references/advisors.md dist/hydra-plugin/skills/hydra/references/advisors.md && echo IDENTICAL
```
Expected: `IDENTICAL` (no `cmp` output).

- [ ] **Step 4: Red test — bogus pathspec fails the allowlist**

Run (temporary edit: add a nonexistent path to `SURFACE`, e.g. insert `nonexistent-xyz.md` into the array), then:
```bash
bash scripts/build-plugin.sh; echo "exit=$?"
```
Expected: `git archive` errors, `exit=128`. Then **revert** the temporary `SURFACE` edit.

- [ ] **Step 5: Red test — dirty surface is refused**

Run:
```bash
printf '\n<!-- scratch -->\n' >> SKILL.md
bash scripts/build-plugin.sh; echo "exit=$?"
git checkout -- SKILL.md
```
Expected: the "surface files differ from HEAD — commit first" error and `exit=1`; then `git checkout` restores SKILL.md clean.

- [ ] **Step 6: Commit**

```bash
git add scripts/build-plugin.sh
git commit -m "feat: plugin build-step — git-archive assembly + dirty/refs guards"
```

---

### Task 2: Manifest generation (D5)

Insert `plugin.json` generation (hardcoded description, no `author.email`, SHA-stamped version read from HEAD, JSON syntax gate) before the publish line, then validate offline.

**Files:**
- Modify: `scripts/build-plugin.sh` (insert a block after the `git archive` line, before the `--- TEMPORARY publish ---` marker)

**Interfaces:**
- Consumes: `$STAGE` and the `git archive` output from Task 1.
- Produces: `$STAGE/.claude-plugin/plugin.json` — a valid manifest with `version` = `2.0.0-alpha.0+g<sha>`.

- [ ] **Step 1: Insert the manifest block**

In `scripts/build-plugin.sh`, immediately after the `git archive HEAD ... | tar -x ...` line and before the `# --- TEMPORARY publish` comment, insert:

```bash
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
```

- [ ] **Step 2: Run the build (green path)**

Run:
```bash
bash scripts/build-plugin.sh
cat dist/hydra-plugin/.claude-plugin/plugin.json
```
Expected: build succeeds; `plugin.json` prints with `"version": "2.0.0-alpha.0+g<sha>"`, `"author": { "name": "Zandereins" }`, and **no** `email` field.

- [ ] **Step 3: Validate offline (unbilled)**

Run:
```bash
claude plugin validate dist/hydra-plugin; echo "exit=$?"
```
Expected: `✔ Validation passed`, `exit=0`. (Note: `validate` checks manifest structure, not the version string — our version is valid SemVer 2.0 by construction.)

- [ ] **Step 4: Red test — version drift fails loud**

Run (temporary: simulate drift by asserting against a wrong value — edit the `if [ "$PYVER" != "2.0.0a0" ]` line to `!= "9.9.9"` so the current `2.0.0a0` triggers the branch):
```bash
bash scripts/build-plugin.sh; echo "exit=$?"
```
Expected: `ERROR: pyproject version drifted (2.0.0a0) …` and `exit=1`. Then **revert** the temporary edit back to `!= "2.0.0a0"`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build-plugin.sh
git commit -m "feat: plugin build-step — generate + offline-validate plugin.json"
```

---

### Task 3: Safety gates + publish (D6.1, D7, D8)

Insert the exact-inventory assert and the surface-hygiene gate before the publish line; finalize the publish + billing-print. This is the reviewer gate for "do the safety guards actually fire."

**Files:**
- Modify: `scripts/build-plugin.sh` (insert two gate blocks before the publish; replace the temporary publish/echo with the final version)

**Interfaces:**
- Consumes: `$STAGE` with the 7 files + `plugin.json` from Tasks 1–2, and `$SHA` from Task 2.
- Produces: `dist/hydra-plugin/` (8 files) — the shippable plugin.

- [ ] **Step 1: Insert the inventory + hygiene gates**

In `scripts/build-plugin.sh`, after the manifest block (Task 2) and before the `# --- TEMPORARY publish` marker, insert:

```bash
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
```

- [ ] **Step 2: Replace the temporary publish with the final version**

Replace the `# --- TEMPORARY publish ...` block (from Task 1) with:

```bash
# D8 — publish (two-step; local git-ignored dir) + print the optional BILLED test (no code path runs it).
rm -rf dist/hydra-plugin
mkdir -p dist
mv "$STAGE" dist/hydra-plugin
trap - EXIT
echo "OK: built dist/hydra-plugin ($(find dist/hydra-plugin -type f | wc -l | tr -d ' ') files), version 2.0.0-alpha.0+g${SHA}"
echo "Validate offline (unbilled):     claude plugin validate dist/hydra-plugin"
echo "Optional (BILLED, run manually): claude --plugin-dir dist/hydra-plugin   # live trigger-firing only"
```

- [ ] **Step 3: Run the full build (green path)**

Run:
```bash
bash scripts/build-plugin.sh
find dist/hydra-plugin -type f | wc -l
claude plugin validate dist/hydra-plugin; echo "exit=$?"
```
Expected: `OK: built dist/hydra-plugin (8 files) …`; file count `8`; `✔ Validation passed`, `exit=0`.

- [ ] **Step 4: Red test — hygiene gate fires on a planted leak**

Run:
```bash
STAGE_TEST="$(mktemp -d)"; echo "path /Users/$(id -un)/secret" > "$STAGE_TEST/x"
grep -RInE "(/Users/[A-Za-z]|/home/[a-z]|\b$(id -un)\b|[A-Za-z0-9._%+-]+@(gmail|gmx|web|outlook|proton|yahoo)\.[a-z]+)" "$STAGE_TEST"; echo "grep-exit=$?"; rm -rf "$STAGE_TEST"
```
Expected: the planted line is printed and `grep-exit=0` (a match → the gate's `if` would `exit 1`). Confirms red-capability of the exact regex used in the script.

- [ ] **Step 5: Reproducibility check**

Run:
```bash
bash scripts/build-plugin.sh && cp -r dist/hydra-plugin /tmp/hydra-plugin-a && bash scripts/build-plugin.sh && diff -r /tmp/hydra-plugin-a dist/hydra-plugin && echo REPRODUCIBLE; rm -rf /tmp/hydra-plugin-a
```
Expected: `REPRODUCIBLE` (empty `diff -r` — same HEAD → byte-identical build).

- [ ] **Step 6: Confirm zero disruption**

Run:
```bash
git status --porcelain
```
Expected: only `scripts/build-plugin.sh` (and the committed docs) appear as intended; `dist/` does NOT appear (git-ignored); root `SKILL.md`/`references/` are unmodified.

- [ ] **Step 7: Commit**

```bash
git add scripts/build-plugin.sh
git commit -m "feat: plugin build-step — inventory + hygiene gates, publish"
```

---

## Notes for the implementer

- **`claude plugin validate` is unbilled** (offline manifest check) — safe to run freely. `claude --plugin-dir` IS billed — never run it from the script or a test; it is a manual, separate decision (live trigger-firing only).
- If the `pyproject` version legitimately moves off `2.0.0a0`, the version assert (Task 2) will fail loudly — that is intended; update the translation deliberately.
- Do not add an `--allow-dirty` flag: `git archive` ships HEAD regardless, so it would silently ship stale content.
- The final tracked diff must be exactly `scripts/build-plugin.sh` + the two `docs/` files (spec + this plan). If anything else is tracked, stop and reconcile.
