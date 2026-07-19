---
name: build-adopt
description: Adopt an existing codebase into the BRAINS Build Platform. Surveys what is already there, then works backwards to deliverables and acceptance criteria that describe the project as it actually is. Use when the user wants to run BRAINS over a repo that already has code — "adopt this repo", "onboard this codebase", "reverse-engineer the spec", "set up BRAINS on an existing project".
---

# Adopt an existing codebase

`/build-init` assumes greenfield: you say what you want and it scaffolds. This verb is the other direction — the code already exists, and the spec has to be recovered from it.

Two halves, kept deliberately apart:

1. **Survey** (deterministic, no LLM) — enumerate what is in the repo.
2. **Inference** (analyst + user) — decide what those facts *mean*.

Never let half 2 quietly rewrite half 1. The survey is evidence; the deliverables are a claim about it.

## Step 1 — Survey

```powershell
python -m build_platform.cli.adopt --root .
```

Writes `.brains-build/adopt/survey.json` and `survey.md`. Add `--json` for machine-readable output, `--no-write` to inspect without writing.

The survey reports languages, dependency manifests, test layout, CI, docs, top-level structure, git history signals (commits, contributors, most-changed files), and suggested workstreams. It infers nothing about intent.

## Step 2 — Read the code the survey points at

Do not skip this. The survey says *where* the project is; it does not say what it does. Before spawning the analyst, read:

- The README and any architecture or ADR docs.
- The entry points named in the manifests.
- The **most-changed files** from the churn list — recent churn is the best available signal for where the project's real work lives.
- The test names. Existing tests are the closest thing to written-down acceptance criteria; a test suite is a spec that someone already agreed to.

## Step 3 — Spawn `build-business-analyst`

Hand it the survey plus what you read. Ask it to propose:

- A one-sentence **mission** — what this project is for, in the user's terms.
- The realistic **stack** and any **constraints** visible in the code (offline-only, no GPL, target runtime version).
- **Deliverables** describing what the project *already does*, each with acceptance criteria that name a test — preferring tests that already exist.
- Which **workstreams** to enable, using the survey's suggestions as a starting point.
- A **gaps** list: things the code implies were intended but are unfinished, untested, or contradictory.

## Step 4 — Confirm with the user

Show the proposal and get explicit confirmation before writing anything. The user is the Product Owner; the analyst is reconstructing their intent from artefacts and **will** get some of it wrong. Expect corrections and treat them as the point of the exercise, not as failure.

Ask directly about anything the analyst marked `[USER ACTION]` or listed under gaps.

## Step 5 — Write state

For a repo with no `.brains-build/` yet, drive `/build-init` with the confirmed values:

```powershell
python -m build_platform.cli.init --root . `
  --name "Acme API" `
  --mission "Serve the Acme product catalogue over a versioned REST API." `
  --stack "Python 3.12" --stack "FastAPI" --stack "Postgres" `
  --constraint "No breaking changes to /v1" `
  --deliverable "D1:Catalogue read API:Clients need product lookup:test_catalogue_get passes;OpenAPI schema validates" `
  --json
```

If `.brains-build/` already exists, do **not** re-init — add the newly recovered deliverables via the package/edit verbs instead.

Then log how the project entered the platform, so later readers know the deliverables were reconstructed rather than specified up front:

```powershell
python -m build_platform.cli.decision --root . `
  --title "Adopted existing codebase into BRAINS" `
  --owner "user:<name>" `
  --decision "Deliverables reverse-engineered from the existing repo via /build-adopt." `
  --why "Code predates the build platform; spec recovered from survey + existing tests." `
  --audit-link ".brains-build/adopt/survey.md" `
  --json
```

## Step 6 — Hand off

Recommend `/build-package` against the first deliverable, and flag the gaps list as candidate work packages. Gaps are usually the most valuable WPs in an adopted project — they are the things everyone knew were unfinished but nobody had written down.

## Don't

- **Don't invent deliverables the code does not support.** If it is not in the repo, it is a gap or a wish, not a deliverable.
- **Don't write acceptance criteria no test could check.** Prefer naming a test that already passes.
- **Don't trust the survey's suggested workstreams blindly** — they are shape-based heuristics. A repo full of `.ts` might be a build tool, not a UI.
- **Don't run this on a repo that already has `.brains-build/`** expecting a clean slate. It surveys fine, but writing state is an update, not an init.
- **Don't skip user confirmation.** Reconstructed intent that nobody confirmed is a guess with a schema wrapped around it.
