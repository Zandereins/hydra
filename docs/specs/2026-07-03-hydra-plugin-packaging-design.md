# Hydra Plugin Packaging — Design Spec (Approach A: build-step assembly)

- **Date:** 2026-07-03
- **Status:** Approved (design), iterated via 4-lens fable adversarial review, **all load-bearing claims independently re-verified by the orchestrator** at HEAD `2d1feb5` (probe 2026-07-03). One fable claim was **refuted** and corrected: `claude plugin validate` *does* exist (see Context / D5 / OQ1).
- **Branch:** `feat/plugin-packaging-buildstep` (off `main` @ `2d1feb5`)
- **Distribution target:** shareable via git, marketplace-**capable** but **not** published.

## Goal

Make Hydra installable as a Claude Code plugin. A single build script assembles a clean plugin tree `dist/hydra-plugin/` from ONLY the verified 7-file skill surface and emits `.claude-plugin/plugin.json`. The dev repo and the live skill (`~/.claude/skills/hydra/SKILL.md`) stay byte-unchanged.

## Context

- The repo root **is** the live skill directory; root `SKILL.md` + `references/` are READ ONLY.
- **Verified surface** (7 tracked files at HEAD, zero runtime dependency on `hydra/` or `bench/`): `SKILL.md`, `references/{advisors,chairman-protocol,report-template,review-protocol}.md`, `README.md`, `LICENSE`.
- **Security history (the one real threat model):** PR #24 scrubbed an absolute path (OS username) and a personal email from the tree. Naive copying could reintroduce this class — surface hygiene matters.
- **Independently re-verified repo facts this spec relies on (probe 2026-07-03, HEAD 2d1feb5):**
  - `dist/` is ALREADY gitignored (`.gitignore:5` = `dist/`).
  - `pyproject.toml` at HEAD line 7 = `version = "2.0.0a0"`.
  - `git archive HEAD -- <7 pathspecs> | tar -x` extracts exactly the 7 files, `cmp` byte-identical to HEAD; a bogus pathspec fails **exit 128**.
  - The hygiene regex (below) is **GREEN on the clean surface** and **RED on a planted `/Users/<user>/` leak**.
  - **`claude plugin validate <path>` EXISTS** (offline, unbilled) — *corrects* the fable spec's "no validate subcommand" claim and the stale roadmap note (2026-06-03). **Caveat:** `validate` checks manifest structure but **not** the version-string format — a garbage `version` still passes (`exit 0`), so `validate` confirms *manifest acceptance*, not marketplace SemVer conformance.

## Requirements

1. **Tracked additions: exactly 2 files** — `scripts/build-plugin.sh` + this spec. **No `.gitignore` edit** (verified no-op; `dist/` already covered at line 5).
2. **Output layout (8 files):** `dist/hydra-plugin/.claude-plugin/plugin.json` + `dist/hydra-plugin/skills/hydra/{SKILL.md, references/*.md (4), README.md, LICENSE}`.
3. **Offline, deterministic, reproducible:** same HEAD → byte-identical `dist/`. No timestamps, `$HOME`, or hostname in any emitted file. **No billed model call anywhere in the script.**
4. **Version:** `2.0.0-alpha.0+g<short-sha>` in `plugin.json` — valid SemVer 2.0 build metadata, **not** a bump; `pyproject.toml` alpha hold `2.0.0a0` untouched and read from HEAD (not the working tree).

## Decisions (defaults set 2026-07-03 — pending Franz's confirmation)

- **README:** ship the existing 319-line dev README as-is (YAGNI; a trimmed user-facing README is a trivial future add if/when actually published).
- **`author.name`:** `Zandereins` (GH handle) — privacy-preserving, consistent with the noreply-alias / PR-#24 posture.
- **LICENSE copyright:** keep `Franz Paul` (real name in an MIT copyright is standard and already public in the repo; changing it would touch the root LICENSE, violating zero-disruption). **Flagged:** this ships Franz's real name in the plugin; the hygiene gate does NOT catch it (name ≠ OS-username). Override → change the root LICENSE separately.
- **Plugin dir name:** `hydra-plugin` (wrapper) — the skill itself is `skills/hydra`.
- **Cut (override to re-add):** CI reproducibility check, `marketplace.json` stub (deferred until publishing is a real decision).

## Technical Decisions

### D1 — Assembly via `git archive HEAD`, not `cp`
```bash
git archive HEAD -- "${SURFACE[@]}" | tar -x -C "$STAGE/skills/hydra"   # mkdir -p "$STAGE/skills/hydra" first
```
Content comes from the committed tree, never the filesystem, so untracked cruft (the PR-#24 leak class: logs, `eval-suite.json`, stray drafts) **physically cannot ship**. Simpler *and* safer than `cp`. Verified: exactly 7 files, byte-identical; bogus pathspec → exit 128 (the allowlist is load-bearing, not decorative).

### D2 — Single-source `SURFACE` allowlist, per-file, no globs
One bash array of the 7 exact paths drives ALL of: archive pathspecs, dirty check, inventory assert. **Not** even `references/*.md` — a future stray draft in `references/` cannot auto-ship. Prevent- and detect-layers stay in sync by construction.

### D3 — Shell dialect: bash, not POSIX sh
`#!/usr/bin/env bash` + `set -euo pipefail`. `pipefail` and arrays are not POSIX sh; pinned so nobody "fixes" the shebang later.

### D4 — Dirty-surface refusal, NO override flag
`git status --porcelain -- "${SURFACE[@]}"` non-empty → fail: *"surface files differ from HEAD — commit first; the build ships HEAD, your uncommitted edits would NOT be included."* An `--allow-dirty` flag is a semantic trap: `git archive` ships HEAD regardless, so the flag would silently ship stale content while the user believes their edits are in. Commit-first costs one command.

### D5 — plugin.json: hardcoded description, handle-only author, fail-loud version, offline validate
- **Description hardcoded** in the heredoc. Do NOT extract from the `SKILL.md` frontmatter: it is a multi-line folded YAML block containing double quotes — naive extraction emits invalid JSON. Accept the drift explicitly; it is one string.
- **Concrete fields:** `name` = `hydra`, `author` = `{ "name": "Zandereins" }` (GH handle, privacy-preserving — see Decisions), `license` = `MIT`. **No `author.email`** — naive generators pull `git config user.email`; this repo's history already had a PII-email scrub.
- **Version:** `PYVER=$(git show HEAD:pyproject.toml | sed -n 's/^version = "\(.*\)"$/\1/p')`; assert `PYVER == 2.0.0a0`, else fail loudly ("version drifted — update the PEP440→SemVer translation"); emit `2.0.0-alpha.0+g$(git rev-parse --short HEAD)`. Read from HEAD so the stamp cannot lie about provenance.
- **Validate offline (unbilled):** `claude plugin validate dist/hydra-plugin` → expect exit 0. This confirms manifest acceptance. Note (verified): `validate` does **not** enforce the version format, so also keep `python3 -m json.tool` for JSON syntax and rely on our version being valid SemVer 2.0 by construction.

### D6 — Two structural asserts
1. **Exact inventory:** `find "$STAGE" -type f | sort` must equal the expected 8-path list computed from the `SURFACE` array + `plugin.json` (no duplicated data to drift).
2. **References completeness:** `SURFACE`'s `references/` entries must equal `git ls-tree HEAD --name-only references/`. Closes the silent-omission gap: a future `references/new.md` cited by SKILL.md but missing from `SURFACE` would otherwise build GREEN and ship a broken skill.

### D7 — Hygiene gate: PR-#24 regression class ONLY
```bash
if grep -RInE "(/Users/[A-Za-z]|/home/[a-z]|\b$(id -un)\b|[A-Za-z0-9._%+-]+@(gmail|gmx|web|outlook|proton|yahoo)\.[a-z]+)" "$STAGE"; then
  echo "HYGIENE GATE FAILED — offenders above" >&2; exit 1
fi
```
- Verified: **zero hits on the clean surface, fires on a planted `/Users/<user>/` leak** (red-capable).
- Username is **runtime-derived** via `$(id -un)` so the tracked script can never itself embed the OS username (the exact PR-#24 leak class).
- **Pin the idiom:** it MUST be `if grep …; then … exit 1; fi`. A bare `grep` under `set -e` exits 1 on a CLEAN surface and kills the build at the success path (a verified failure mode in two variants).
- **Deliberately excluded patterns:** `\.hydra/` (hits legitimate doc lines — the skill instructs agents to write there) and unbounded token-format strings like `github_pat_` (SKILL.md documents token formats for its advisors). This plugin's content *is* a secrets-scanning skill, so its docs are adversarial input to any naive secret grep; only the PII/abs-path regression class is cleanly gateable.

### D8 — Publish + structural billing gate
`rm -rf dist/hydra-plugin && mv "$STAGE" dist/hydra-plugin` (two steps, not atomic — acceptable for a local gitignored dir). The script then **prints** the optional live-trigger test and contains **no code path that can execute it**:
```
Optional (BILLED, run manually): claude --plugin-dir dist/hydra-plugin   # live trigger-firing only; manifest is already validated offline
```

## Non-Goals (cut as over-engineering for a maintain-mode personal tool)
- `--check` reproducibility mode (`dist` is a pure function of HEAD; manual rebuild + `diff -r` when curious), `--legacy-version`, `--allow-dirty`.
- CI job / workflow amendment (beyond the minimal tracked set).
- `marketplace.json` emission (deferred; a tracked stub pointing at gitignored `dist/` breaks every fresh clone — decision recorded, mechanism not built).
- SHA256SUMS, canary self-test, symlink/perm/hidden-file asserts, bidirectional `cmp` (no injection path once assembly is git-archive-allowlisted).
- Frontmatter description extraction (invalid-JSON hazard, D5); broad secret/cruft grep (red-on-green, D7).

## Open Questions
1. **~~Does the loader accept `+` build metadata in the version?~~ RESOLVED** — `claude plugin validate` passes `2.0.0-alpha.0+g<sha>` (and it is valid SemVer 2.0). Residual: `validate` does not strictly check the version, so strict marketplace SemVer conformance is only relevant at a future `claude plugin tag` / publish step (out of scope now).
2. Marketplace schema field names — irrelevant until publishing; do not model.

## Verification
**Already run during synthesis + independently re-verified by the orchestrator (2026-07-03, HEAD 2d1feb5):** archive extraction (7 files, `cmp` byte-identical), hygiene grep GREEN-on-clean / RED-on-planted, bogus pathspec exit 128, `dist/` ignored at `.gitignore:5`, `version = "2.0.0a0"` at HEAD, `claude plugin validate` exists and passes the real manifest shape offline (exit 0).

**Acceptance after implementation (all offline, unbilled):**
1. `bash scripts/build-plugin.sh` on clean HEAD → exit 0; `find dist/hydra-plugin -type f | wc -l` = 8.
2. `cmp SKILL.md dist/hydra-plugin/skills/hydra/SKILL.md` → identical; same for one reference file.
3. Rebuild → `diff -r` of two builds at the same HEAD is empty (reproducibility).
4. `claude plugin validate dist/hydra-plugin` → exit 0.
5. Red-capability: plant `/Users/$(id -un)/x` into a staged file → gate exits 1 listing the offender; add a bogus path to `SURFACE` → build fails (exit 128).
6. `git status --porcelain` after build → only the 2 intended tracked files; root surface untouched.
7. Edit root `SKILL.md` without committing → build REFUSES with the commit-first message.
8. (Optional, BILLED, manual, separate decision): `claude --plugin-dir dist/hydra-plugin` — live trigger-firing only.
