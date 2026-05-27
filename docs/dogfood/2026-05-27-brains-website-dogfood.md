# Real-product dogfood — brains-website

**Date:** 2026-05-27
**Operator:** Claude (running the dogfood loop)
**Target:** `shard-BRAINS/brains-website` — BRAINS Infiniti website prototype (static HTML + inline React + Babel + Railway). Cloned to `c:\brains-website-dogfood\`.

## Why this dogfood

The 2026-05-26 meta-dogfood ran the platform on itself. This run is the third-party real-product test: a separate codebase, a different stack (JSX/HTML, not Python), a real (private) GitHub repo. Goal: surface friction that's specific to using the platform on someone-else's-work, not just self-application.

## What ran end-to-end

1. **Clone target.** `gh repo clone shard-BRAINS/brains-website c:\brains-website-dogfood`.
2. **`/build-init`** with stack = html/jsx/react/babel/railway, real BRAINS constraints (brand-compliant, accessibility-first, no build step), 1 deliverable `D-brand` (brand-color compliance + canonical sign-off).
3. **`/build-package`** × 2 — WP-0001 tier-2 audit (10 files in scope across components/ + prototypes/), WP-0002 tier-2 footer add (10 prototype HTML files).
4. **`/build-dispatch` WP-0001** → emitted tier-2 brief at `runs/WP-0001/tier2-brief.md`, no warnings (persona installed).
5. **Real subagent spawn** as `build-security-sme` against the brief. Audit ran on 26 JSX + 10 HTML files. Returned thorough findings inline (could not write to disk — see Finding #12).
6. **Orchestrator** persisted findings to `runs/WP-0001/findings.md`, transitioned WP-0001 through `in_review` → `done` with QA verification recorded.
7. **`/build-package_edit` WP-0002** — refined spec based on audit (use existing `#b88313` token instead of brand-spec'd `#D99518` to avoid divergence).
8. **`/build-package` WP-0003** — created the audit's recommended follow-up (audit `#f5c14e` callsites against light surfaces).
9. **`/build-mirror init` + `push --dry-run` + `push`** to `shard-BRAINS/brains-website` (private). All 3 WPs landed as live GitHub issues; WP-0001 auto-closed because its state is `done`.

End-to-end wall time: ~10 minutes. Token usage: 1 leadership-tier subagent dispatch + the orchestrator's coordination.

## Headline result

**The platform worked end-to-end on a real third-party product** with no platform code changes. Init, package, edit, dispatch (tier-2), state transitions, mirror push (private repo, with dry-run preview), and audit-finding persistence all functioned. The audit subagent followed the persona contract (read-only, file+line citations, severity tags, adjacent findings surfaced separately).

**The audit's "adjacent findings" were more valuable than the original WP intent** — the dogfood surfaced a real brand-spec / source-code divergence that needed catching (Finding #13 below).

## New findings

Severity scale matches the previous dogfood: critical · important · minor · idea.

### Finding #12 — Subagent harness blocks writes to `runs/<wp-id>/` (important)

**Where:** tier-2 dispatch flow (the brief tells executors to write deliverables to `runs/<wp-id>/...`).

**Reproduction:** the spawned `build-security-sme` subagent followed the brief but its harness refused the file write to `c:\brains-website-dogfood\.brains-build\runs\WP-0001\findings.md`. Subagent reported: "The harness blocks writing findings to disk; the brief asked for a file, but I'll return the findings inline as the harness directs." Returned the audit content inline in its final response instead.

**Why it matters:** the platform's auditability invariant depends on `runs/<wp-id>/` capturing per-dispatch artifacts. If subagents can't write there, the orchestrator has to mirror their final response into the file system — adding a step that's easy to forget and breaks the "audit-from-disk" promise.

**Likely cause:** the Agent tool's general-purpose subagent runs with a constrained working-directory permission model. Writes outside its perceived working dir get refused. `.brains-build/runs/` is technically inside the project root but the subagent's notion of "working dir" may not include the dogfood project.

**Fix options:**
1. **Update tier-2 brief template** to instruct executors: "Return deliverables in your final response (markdown). The orchestrator will persist them to the right path." Remove the "write to runs/..." instruction.
2. Have the dispatcher pass a write-target path that's explicitly in the subagent's writable scope (less control over location).
3. Add an "ingest_subagent_output" verb that takes a final-response string and writes it to `runs/<wp-id>/<name>.md` — making persistence an orchestrator-side action.

Option 1 is simplest and matches what already happens: the subagent's "Result block" goes in the final response anyway. The brief should explicitly say so. Option 3 (orchestrator ingests) is the cleanest long-term — formalizes the orchestrator's role as the persistence boundary.

**Recommended fix:** Option 1 (brief template change) for v1; Option 3 (orchestrator ingest verb) for a future iteration.

---

### Finding #13 — Brand-doc vs source-code token divergence (important, but a product finding, not a platform finding)

**Where:** target codebase (`shard-BRAINS/brains-website`) vs. BRAINS brand standards.

**Detail:**
- Brand standards spec: `#FCC14D` (Gold, decorative) + `#D99518` (Gold Deep, text-on-white).
- Source code uses: `#f5c14e` (Gold) + `#e2a82a` / `#b88313` (Gold Deep variants).
- Neither standard token appears in source. Neither source token appears in the brand standards.

**This isn't a platform bug — it's a real finding the dogfood surfaced.** Every future audit against this codebase would either over- or under-report unless reconciled. Two reconciliation paths exist (see WP-0003 / the audit's A1 + A2 notes); Matthew should pick one.

**Why it matters for the platform:** validates the platform's claim that "audit work surfaces value the operator might not have asked for." The original WP-0001 expected to find `#FCC14D` violations and fix them; instead it found there are NONE — and surfaced a separate, equally important issue. The platform's persona contract ("note adjacent findings but don't expand scope") worked exactly as designed.

---

### Finding #14 — `.gitignore` of the target repo doesn't list `.brains-build/` (minor)

**Where:** any target repo using the platform.

**Reproduction:** `/build-init` creates `.brains-build/` in the target project root. The target project's `.gitignore` isn't updated. If the user runs `git add -A` later, they'll accidentally commit `.brains-build/` (audit trail + work-package log + Ollama runs) to the target repo. Some users may want this (commit audit trail with the code); others won't.

**Fix:** `/build-init` could optionally add `.brains-build/` to the target repo's `.gitignore` based on a CLI flag (`--gitignore-state` default true, or `--no-gitignore-state` opt-out). Or just print a one-line tip at the end of init output: "Tip: consider adding `.brains-build/` to your project's .gitignore — or commit it to share state with your team."

**Severity:** minor — the user can do this themselves. But it's an obvious-in-hindsight footgun.

---

### Finding #15 — Private-repo mirror push works correctly (positive validation, not a bug)

**What was tested:** mirror push to a private repo (`shard-BRAINS/brains-website` is private). All 15 labels seeded; 3 issues created; WP-0001's `done` state correctly closed the issue immediately on creation.

**No friction surfaced.** The mirror code is repo-visibility-agnostic, as it should be.

---

## What didn't run (deferred, not blockers)

- **WP-0002 dispatch.** The footer-add tier-2 work was created and refined but not dispatched in this session. Real value (the site gets the canonical sign-off) is left on the table for follow-up. Reason: the dogfood already produced strong friction signal from WP-0001; another full subagent spawn would have spent ~2 minutes for incremental signal.
- **WP-0003 dispatch.** Same reason. Created as a follow-up; dispatching is the next session's work or the next operator's first move.
- **Tier-1 dispatch through real Ollama** on this codebase. The audit didn't produce a tier-1-eligible follow-up (no `#FCC14D` to swap). The recommended follow-up (WP-0003) is tier-2 because it needs judgment per callsite. A real tier-1 dispatch on JSX/HTML is still untested.

## Recommendation for follow-up

1. **Patch tier-2 brief template** to address Finding #12 (subagent should return deliverable in final response, not write to disk).
2. **`/build-init --gitignore-state` flag** for Finding #14.
3. **Run WP-0002 + WP-0003** when there's a session for it — those are real product value, not just dogfood signal.
4. **Pick a reconciliation path for Finding #13** — Matthew's call: align brand spec to source, or align source to brand spec. WP-0003 unblocks the latter path.

## What this dogfood proved

- The platform works end-to-end on a real third-party project with no code changes. Init → package → edit → dispatch → state transitions → mirror push, all clean.
- The tier-2 brief flow drives quality subagent work — the audit was thorough, well-cited, severity-tagged, and surfaced unexpected adjacent findings (which the persona prompt explicitly encourages).
- The package_edit verb (Finding #7 from previous dogfood) was used in anger here for the first time outside its tests — refining a WP spec based on findings from a sibling WP. Worked cleanly.
- The mirror push (v2.5) worked on a private repo identically to a public one.

The remaining gaps are small, well-bounded, and don't block real-world use.
