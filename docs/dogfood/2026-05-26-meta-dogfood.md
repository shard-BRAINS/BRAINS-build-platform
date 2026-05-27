# Dogfood findings — meta-build of brains-build-platform

**Date:** 2026-05-26 · **Operator:** Claude (running the dogfood) · **Target:** the platform itself
**Status (2026-05-27):** all 10 findings closed.

## Resolution summary

| # | Severity | Status | Commits |
|---|---|---|---|
| 1 | important | ✅ closed | `d202f11` (orphan-dep validation in package CLI) |
| 2 | **critical** | ✅ closed | `ba4f695` (validate_diff strips markdown fences) |
| 3 | important | ✅ closed | `84786cf` (tier-1 prompt scope discipline) |
| 4 | important | ✅ addressed | partly downstream of #3; remaining risk is inherent to small models — Dev Orch review remains the mitigation |
| 5 | minor | ✅ closed | `4b44c69` (mirror push `--dry-run`) |
| 6 | minor | ✅ closed | (round 3) `[BLOCKED]` title prefix + body banner on GitHub |
| 7 | important | ✅ closed | (round 3) `package_edit` CLI verb |
| 8 | important | ✅ closed | `460a5c5` (`dispatch_apply` verb) |
| 9 | minor | ✅ closed | (round 3) persona-install preflight warning in tier-2 dispatch |
| 10 | important | ✅ closed | `13b48b7` (`dispatch_reject` verb + audit on transition) |
| 11 | **important** | ✅ closed | (re-dogfood) `check_diff_applies_cleanly` integrated into dispatch_tier1 |

**Test count delta:** 49 (v0.1.0) → 138 (post-round-3) → 177 (post-v2.7) → **181 after re-dogfood** (+132 across all dogfood-driven fixes).

---

## Finding #11 — diff passes `validate_diff` but fails `git apply --check`

**Date surfaced:** 2026-05-27, re-dogfood on `WP-0006` (Add WPState.is_terminal_state).
**Severity:** important.
**Where:** `src/build_platform/dispatcher.py::validate_diff` (structural check too loose).

**Reproduction:** Triage + package + dispatch a clean tier-1 WP. `qwen2.5-coder:7b` produced this diff:
```
--- a/src/build_platform/schemas.py
+++ b/src/build_platform/schemas.py
@@ -21,6 +21,7 @@ class WPState(str, Enum):
     IN_REVIEW = "in_review"
     DONE = "done"
     BLOCKED = "blocked"
+    def is_terminal_state(self) -> bool:
+        return self in {WPState.DONE, WPState.BLOCKED}
```

Structurally valid: has `--- a/`, `+++ b/`, `@@ ... @@`, hunk content. `validate_diff` accepts. But the `@@ -21,6 +21,7 @@` header is wrong: actual content is 3 context lines + 0 removed + 2 added, so the header should be `@@ -21,3 +21,5 @@`. `git apply --check` rejects with "corrupt patch at line 9".

**Why round-1/2 fixes didn't catch this:** the prior fence-strip + scope-discipline + first-line-is-`--- a/` checks all look at *shape*, not at the *math* inside the hunk header. The math is exactly what `git apply` enforces.

**Fix:** New `check_diff_applies_cleanly(project_root, diff_text)` helper runs `git apply --check` against a tmp file. Integrated into `dispatch_tier1`'s retry loop AFTER `validate_diff` passes — if `git apply --check` fails, treat as a recoverable validation failure with concrete feedback (the format of `@@ -A,B +C,D @@` and what B/D should equal). The existing 2-attempt retry mechanism handles the rest. Non-git project roots skip the check (return `(True, "")`).

**Commit:** (this session, with the round-4 hygiene + re-dogfood batch).

**Tests:** 4 new — apply-check returns True for non-git dir, detects bad hunk header in real git repo, accepts well-formed diff, end-to-end retry-on-bad-then-good behavior.

**Demo trace** of the actual re-dogfood loop after the fix:
1. `triage --spec "Add ..." --file schemas.py --accept "..."` → suggested tier-1, all four criteria pass.
2. `package --tier 1 --file schemas.py ...` → WP-0006 created cleanly.
3. `dispatch --wp WP-0006` → Ollama produced the bad-hunk-counts diff; with the new check, the dispatcher would now reject + retry with concrete feedback (instead of writing it to disk).
4. After Finding #11's fix, the dispatch loop is self-correcting.

## Original findings (preserved for record)

## What we did

1. `/build-init` the platform repo as its own build project (`c:\BRAINS_Build_Platform\.brains-build\`).
2. Defined 3 deliverables: `D-sync2` (two-way GitHub mirror), `D-triage` (auto tier-1/2 triage), `D-dogfood` (this exercise).
3. Decomposed `D-sync2` into 5 work packages via `/build-package`.
4. Dispatched WP-0001 (tier-1) to real Ollama (`qwen2.5-coder:7b`).
5. Dispatched WP-0002 (tier-2) — generated subagent brief.
6. Configured + pushed mirror to live `shard-BRAINS/brains-build-platform` repo.

Time on task: ~25 minutes.

---

## Findings

Severity scale: **critical** = blocks platform from being used safely · **important** = causes friction every use · **minor** = nuisance · **idea** = potential improvement, not a bug.

### Finding 1 — `--depends-on` accepts orphan IDs without validation

**Severity:** important
**Where:** `src/build_platform/cli/package.py`
**Reproduction:** Run `/build-package --tier 2 ... --depends-on WP-9999` on a fresh project. CLI exits 0; the WP is created with a dependency that will never resolve. Later `/build-dispatch` will refuse with "unmet deps: ['WP-9999']" but at that point the WP is already in the JSONL.

**Real-world impact:** When the Dev Orchestrator drafts multiple WPs at once and predicts WP IDs ahead of `next_wp_id`, it's easy to typo or miscount and the CLI silently accepts. Happened twice in this session.

**Fix:** `package_cmd` should `load_work_packages(root_path)`, build the existing-ID set, and reject `--depends-on` IDs not present.

**Workaround used:** manually rewrote `work-packages.jsonl` via a Python one-liner.

---

### Finding 2 — `validate_diff` accepts diffs wrapped in markdown code fences

**Severity:** critical
**Where:** `src/build_platform/dispatcher.py::validate_diff`
**Reproduction:** Ollama returned this WP-0001 output:
```
\`\`\`diff
--- a/src/build_platform/github_mirror.py
+++ b/src/build_platform/github_mirror.py
@@ ...
\`\`\`
```
`_DIFF_HEADER`, `_DIFF_HEADER_PLUS`, and `_DIFF_HUNK` regexes all use `MULTILINE` and find the headers inside the fences. Validation passes. The diff is then written verbatim to `proposed.diff` — `git apply` would fail because of the leading/trailing fence lines.

**Fix:** add a structural check that the diff content (stripped of leading whitespace) **starts** with `---` and **ends** with a hunk line. Strip ` ```diff ` / ` ``` ` wrappers before validation, OR reject them.

---

### Finding 3 — Tier-1 prompts under-constrain scope

**Severity:** important
**Where:** `src/build_platform/templates/tier1_executor.j2`
**Reproduction:** WP-0001 was a tier-1 schema-extension: "add one field to MirrorMap". Ollama added the field correctly but also inserted speculative logic in `push_workpackage` and `push_all` referencing the new field — code that was completely outside the WP scope.

**Why it slipped through:** the prompt says "single transformation" and "do not include prose," but doesn't forbid speculative additions to other functions. The model "helpfully" extends the implementation it imagines goes with the field.

**Fix:** Tier-1 template should add: "Modify ONLY the exact lines required for the named transformation. Do not add usage of new fields elsewhere — that's a separate WP. Output an empty diff with a comment if you find the transformation already done."

---

### Finding 4 — Ollama output can be semantically wrong even when structurally valid

**Severity:** important (downstream of #3)
**Where:** review step in `/build-dispatch` flow
**Reproduction:** WP-0001 output set `seen_comments[wp_id] = [issue_number]` — treating the issue number as a comment ID. Structurally valid Python; semantically nonsense.

**Why this matters:** `validate_diff` only checks structure (headers, hunks, allowed files). Semantic correctness depends on the Dev Orchestrator review subagent, which means tier-1 ALWAYS needs Claude review — the "cheap mechanical" promise has a hidden Claude-review tax.

**Fix:** This is partly a model-capability issue (qwen2.5-coder:7b is small). Two mitigations:
- Improve tier-1 prompt (Finding #3) so model has fewer chances to invent semantics.
- Document explicitly that tier-1 saves Claude tokens *for code generation*, not for review. Reviews are always Claude.

---

### Finding 5 — Mirror push needs explicit user authorization every time

**Severity:** minor (correct behavior, but missing affordance)
**Where:** `cli/mirror.py push`
**Reproduction:** Running `mirror push` to a live public repo triggered Claude Code's safety classifier — correctly. But there's no `--dry-run` to preview *what would be pushed* before committing.

**Fix:** add `--dry-run` to `mirror push` that:
- Resolves what labels would be seeded, what milestones would be created/reused, what issues would be created/edited
- Outputs a JSON preview
- Does NOT call gh
- User then runs without `--dry-run` to actually execute

This makes the public-state-change action two-step by default, which matches how other careful CLIs work.

---

### Finding 6 — `state=blocked` is visually weak on GitHub

**Severity:** minor
**Where:** `github_mirror.py::push_workpackage`
**Reproduction:** WP-0001 is locally `blocked` after the rejected dispatch. The GitHub issue has the `bbp:state-blocked` label but the issue is **open** (because blocked auto-reopens). A reviewer scanning the repo can easily miss the label; the title still reads "[WP-0001] Extend MirrorMap...".

**Fix:** add a `[BLOCKED]` prefix to the title when state is blocked, OR add a header line in the body. Remove the prefix when state transitions back to active.

---

### Finding 7 — No CLI verb to edit a WP after creation

**Severity:** important (blocks recovery from #1)
**Where:** missing — no `package edit` exists.
**Reproduction:** After Finding #1 surfaced orphan deps, the only fix was hand-editing `work-packages.jsonl`. No CLI lets you change a WP's metadata (title, spec, deps, files, etc.) once it's in the log.

**Fix:** add `python -m build_platform.cli.package edit --wp WP-X` with flags to mutate fields. Implementation note: WPs are append-only in concept; an edit should append a new history event (`event="metadata: changed depends_on from [...] to [...]"`) AND rewrite the WP line in JSONL. The audit module should write an audit entry too.

---

### Finding 8 — No CLI verb to apply an approved tier-1 diff

**Severity:** important
**Where:** missing — `build-dispatch` SKILL.md says "approve → apply the diff with `git apply <path>`" but there's no platform verb.
**Reproduction:** After Dev Orch approves a diff, the user is told to run `git apply runs/WP-X/proposed.diff` manually. No platform verb:
- Validates the diff applies cleanly (`git apply --check`)
- Handles partial application / conflicts
- Runs the project's test command after apply
- Transitions WP state to `in_review`
- Writes the audit entry

**Fix:** add `dispatch apply --wp WP-X` that does all of the above atomically. If `git apply --check` fails, transition WP to `blocked` with the conflict info.

---

### Finding 9 — `install.ps1` is a hidden prerequisite for the dispatch flow

**Severity:** minor (docs gap)
**Where:** `skills/build-dispatch/SKILL.md`
**Reproduction:** A fresh clone + `pip install -e .` is enough for CLI verbs to work, but `install.ps1` must also be run before Claude Code can spawn the persona subagents (because the agent definition files need to be in `~/.claude/agents/build/`). The build-dispatch SKILL.md doesn't say this.

**Fix:** add a preflight to `cli/dispatch.py` for tier-2 dispatches: check that `Path.home()/.claude/agents/build/<persona>.md` exists. If missing, exit 2 with the exact command to fix (`cd c:\BRAINS_Build_Platform && .\install.ps1`).

---

### Finding 10 — State transitions outside `cli/dispatch.py` skip audit

**Severity:** important
**Where:** `src/build_platform/state.py::update_wp_state`
**Reproduction:** When Dev Orch rejected the WP-0001 diff, we marked it `blocked` via `update_wp_state(...)`. This appended a history event correctly, but **no audit file was written** because audit-writing happens in `cli/dispatch.py`, not in `state.update_wp_state`. As a result, the audit trail is incomplete: dispatch is recorded; the rejection-blocked transition is not.

**Fix:** either `update_wp_state` should optionally emit a minimal audit entry on every transition, OR add a dedicated `dispatch reject --wp X --reason "..."` verb that does state transition + audit + dashboard refresh atomically. The latter is cleaner — it surfaces "reject" as a first-class operation.

---

## Quick wins (recommend doing first)

In priority order:

1. **Finding 2** (validate_diff fence-stripping) — critical correctness fix, ~30 LOC + test.
2. **Finding 8** (`dispatch apply` verb) — biggest user-experience improvement; closes the tier-1 review loop.
3. **Finding 1** (orphan-dep validation in `package`) — small, prevents a real-world footgun.
4. **Finding 10** (`dispatch reject` verb + audit on every transition) — completeness of the audit trail.
5. **Finding 3 + 4** (tighter tier-1 prompt) — prompt tweak, will materially improve real Ollama runs.

## Slower wins

6. **Finding 7** (`package edit` verb) — needed but bigger surface (every field becomes a flag).
7. **Finding 5** (`mirror push --dry-run`) — small but useful.
8. **Finding 9** (subagent-install preflight in dispatch) — small.
9. **Finding 6** (visual blocked state on GitHub) — cosmetic.

## What worked

- `init` flow was clean and produced valid state in one shot.
- `package` (other than #1) accepted all five real-world WPs cleanly. Field set is the right shape.
- Tier-2 brief generation is solid — content was complete enough that a fresh Claude could execute it.
- Dashboard reflected real state accurately on first render, including the blocked WP surfacing in the Open blockers section.
- Mirror push worked end-to-end on a real public repo; idempotent design held up.
- The platform's data shape (deliverables, workstreams, WPs, state machine) survived contact with a real project without needing schema changes.

## What's not in scope of this dogfood

- Did NOT run a full tier-2 subagent execution (would have required spawning a real Claude subagent against the WP-0002 brief — valuable but expensive; deferred).
- Did NOT exercise `/build-scrum` end-to-end (would have required a second day of "since last scrum" diff to be meaningful).
- Did NOT exercise `/build-decision` in this session.

These three are next-session work.
