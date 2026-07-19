---
name: build-init
description: Initialize a new BRAINS Build Platform project. Interactive wizard that produces project.yml, deliverables.yml, workstreams.yml, and config.yml under .brains-build/ in the current directory.
---

# Init a build project

Run this once per project. Refuses if `.brains-build/` already exists.

## Flow

1. **Confirm directory.** The active directory should be empty or a fresh repo. Confirm with the user.
2. **Gather inputs.** Ask one question at a time:
   - Project name (one-line slug)
   - Mission (ONE sentence — push back if longer)
   - Stack (multi-select common + free text: python, fastapi, react, postgres, ...)
   - Constraints (absolute things — "no GPL", "must run offline" — not preferences)
   - 3–5 top deliverables, each with: id (e.g., D-auth), title, why-one-line, ≥ 1 acceptance criterion
3. **Spawn `build-business-analyst`** with the gathered freeform inputs. The analyst produces structured YAML payloads matching the schemas; show them to the user, who is the Product Owner and makes the call.
4. **Confirm with user.** Accept edits.
5. **Run the CLI:**

```powershell
python -m build_platform.cli.init `
  --root . `
  --name "<name>" `
  --mission "<mission>" `
  --stack "<stack1>" --stack "<stack2>" `
  --constraint "<c1>" `
  --deliverable "D-x:Title:Why:Acceptance1;Acceptance2" `
  --json
```

1. **Print the next-step block** (returned by the CLI), including the exact `ollama pull` commands.

## What the CLI writes

- `.brains-build/project.yml` — project context
- `.brains-build/deliverables.yml` — deliverables with acceptance criteria
- `.brains-build/workstreams.yml` — default 5 workstreams (backend, frontend, qa, security, devops)
- `.brains-build/config.yml` — Ollama URL + default models + project test command
- `.brains-build/work-packages.jsonl` — empty
- `.brains-build/decisions.md` — seeded with the init event

## Don't

- Don't write any of these files directly via Write/Edit. Always go through the CLI so schema validation runs.
- Don't skip the Product Owner spawn even when inputs look clean — they shape the YAML, you don't.
