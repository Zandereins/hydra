# Hydra Plugin Packaging — Design Spec

- **Date:** 2026-07-03
- **Status:** Approved (design), pending spec review → implementation plan
- **Branch:** `feat/plugin-packaging-buildstep` (off `main` @ `2d1feb5`)
- **Supersedes:** the stale `feat/plugin-packaging` @ `91182f5` (10 commits behind main; its 10-line draft `plugin.json` is referenced, not reused verbatim)

## Goal

Make Hydra cleanly installable by others as a Claude Code plugin, **without disrupting the live skill or the dev repo**. Produce a reproducible build step that assembles a clean plugin tree from only the skill surface. Distribution target: **shareable via git, marketplace-capable but not published** (marketplace submission is deferred).

## Context

- Hydra v2.0 is **feature-complete / maintain-mode** (no known prompt bugs; the dogfood→harden loop is closed; deep mode is cross-model production-validated). This spec adds distribution packaging — it does **not** change skill behavior.
- **Structural blocker (the thing this fixes):** the skill surface (`SKILL.md` + `references/`) sits at the repo root, conflated with dev infra (`hydra/` Python package, `bench/`, `tests/`, `docs/`, `pyproject.toml`, caches, logs, `.hydra/`). The standard plugin layout autodiscovers skills from `skills/<name>/SKILL.md`, so the root layout cannot be shipped as-is without dragging all dev infra along.
- **Verified skill surface (what the interactive skill actually needs):** `SKILL.md` + `references/{advisors,chairman-protocol,report-template,review-protocol}.md`. Confirmed 2026-07-03 by grep: `SKILL.md` has **zero runtime dependency** on the Python `hydra/` package or `bench/` (no `import hydra`, no `python -m hydra`, no bench calls). The Python package and bench are dev/measurement infra only.
- **Trigger survival is already confirmed** (roadmap 2026-06-03): a skill's free-text auto-activation (SKILL.md `description` triggers like "hydra this") is independent of plugin namespacing; only the explicit slash command becomes `/hydra:hydra`. Packaging does not break Hydra's triggers.
- The live skill loads from `~/.claude/skills/hydra/SKILL.md`. Switching that directory to a feature branch would revert the live skill, so all packaging work happens in an isolated git worktree.

## Requirements

### Functional
1. A deterministic, idempotent build script assembles a clean plugin tree under `dist/hydra-plugin/`.
2. The plugin tree contains **only** the skill surface (7 files) in the standard plugin layout:
   - `dist/hydra-plugin/.claude-plugin/plugin.json` (generated)
   - `dist/hydra-plugin/skills/hydra/SKILL.md`
   - `dist/hydra-plugin/skills/hydra/references/{advisors,chairman-protocol,report-template,review-protocol}.md` (4 files)
   - `dist/hydra-plugin/skills/hydra/README.md`, `LICENSE` (co-located with the skill)
3. `plugin.json` is generated with: `name` = `hydra`, `description` (sourced from the `SKILL.md` frontmatter, not re-typed), `author`, `license`. Marketplace-capable shape, but **no** `marketplace.json`.
4. **Version:** keep the git-SHA default (no real semver bump) — consistent with the `pyproject` `2.0.0a0` alpha hold. The build stamps the current `main` short SHA into `version` so the artifact is traceable to a commit. Exact string form (bare SHA vs a semver-legal `2.0.0-alpha.0+<sha>`) is settled at build time against whatever `plugin.json` accepts, and confirmed in the load-test — the invariant is "SHA-identified, not a real release."
5. The build is a **derived artifact**: `dist/` is git-ignored; re-running the build after a skill change regenerates it. Single source of truth stays the root `SKILL.md` + `references/`.
6. An optional, separately-gated validation path: `claude --plugin-dir dist/hydra-plugin` load-test (the only step that costs a billed model call).

### Non-functional
- **Zero disruption** to the dev repo and the live skill: the root `SKILL.md`/`references/` are read, never moved or modified.
- **Minimal changes** (per project convention): the only tracked additions are the build script, a `.gitignore` entry for `dist/`, and this spec. No restructure, no history churn.
- **Reproducible & offline:** the build itself needs no network and no billed model call (only the optional validation does).
- Prefer stdlib / shell built-ins; reuse existing files; no new heavy dependency.

## Technical Decisions

### Approach A — build-step assembly (chosen)
Assemble `dist/hydra-plugin/` by copying the six skill-surface files into the standard plugin layout and emitting `plugin.json`.

- **Chosen over B (repo restructure):** B is invasive/risky for a feature-complete skill — it breaks the live-skill path (`~/.claude/skills/hydra/SKILL.md`), churns the 1000-line `SKILL.md` + all `references/` paths + history, and violates "minimal changes."
- **Chosen over C (`skills:["."]` root pointer):** C ships the entire dev repo (Python pkg, bench, tests, `.venv`, caches, logs) inside the plugin — bloated, leaks dev cruft to users, and its validity is unverified.
- Matches the roadmap's own framing (2026-06-03): "a packaging step assembling `skills/hydra/` + `plugin.json` from just the skill surface, separate from the dev repo."

### Build script
- Location: `scripts/build-plugin.sh` (POSIX shell; ~15–25 lines).
- Steps: (1) resolve repo root + current short SHA; (2) clean/recreate `dist/hydra-plugin/skills/hydra/`; (3) copy `SKILL.md`, `references/`, `README.md`, `LICENSE`; (4) generate `.claude-plugin/plugin.json` with the description extracted from the `SKILL.md` YAML frontmatter and the SHA stamped into `version`; (5) print the resulting tree + a one-line "next: `claude --plugin-dir dist/hydra-plugin`" hint.
- Idempotent: a clean rebuild each run (remove + recreate the skill dir) so stale files never linger.

### plugin.json shape (marketplace-capable, not published)
```json
{
  "name": "hydra",
  "description": "<extracted from SKILL.md frontmatter at build time>",
  "version": "<SHA-stamped per Requirement 4>",
  "author": { "name": "Zandereins" },
  "license": "<from LICENSE / pyproject at build time>"
}
```
Fields present so a later marketplace step is only a `marketplace.json` entry + `claude plugin tag`. The angle-bracket values are build-time extractions, not spec placeholders. `version` honors the git-SHA-default decision without asserting a real release (see Requirement 4).

## Non-Goals
- No marketplace submission / `marketplace.json` (deferred).
- No repo restructure; no moving or editing the root `SKILL.md` / `references/`.
- No shipping of the Python `hydra/` package, `bench/`, `tests/`, or `docs/` in the plugin.
- No real semver version bump (stays alpha-held; SHA-stamped only).
- No change to skill behavior, triggers, or advisor prompts.

## Open Questions
1. **Plugin directory name:** `dist/hydra-plugin/` vs `dist/hydra/` — does the marketplace/`--plugin-dir` care about the wrapper dir name? (Load-test will confirm; default `hydra-plugin` unless it matters.)
2. **README scope for the plugin:** ship the existing 319-line dev README as-is, or generate a trimmed user-facing README for the plugin surface? (Default: ship as-is; revisit if it reads too dev-internal.)
3. **`author`/`license` exact values:** confirm `author.name` and the license string against `pyproject.toml` / `LICENSE` at build time.

## Verification / Acceptance
- Build runs offline, idempotently; `dist/hydra-plugin/` contains exactly the six surface files in the standard layout and a valid `plugin.json` (JSON parses; required fields present).
- `dist/` is git-ignored; the dev repo and live skill are byte-unchanged.
- **Gated (billed, separate step):** `claude --plugin-dir dist/hydra-plugin` loads the skill and its triggers fire — the empirical load-test that the roadmap left open.
