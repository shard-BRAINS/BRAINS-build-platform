---
name: build-decision
description: Log a project decision to decisions.md. Captures owner, decision, rationale, alternatives considered, and related WPs.
---

# Log a decision

## Flow

1. **Gather inputs.** If user input is freeform, spawn `build-product-owner` to shape it into the standard fields:
   - title (one line, imperative)
   - owner (persona id or `user:<name>`)
   - decision (one sentence)
   - why (rationale)
   - alternatives (each: name + why rejected)
   - related WP ids
2. **Run the CLI:**

```powershell
python -m build_platform.cli.decision --root . `
  --title "Use Argon2 for password hashing" `
  --owner build-security-sme `
  --decision "Argon2id with t=3, m=64MB, p=4" `
  --why "OWASP 2024 recommendation; prior bcrypt instances flagged" `
  --alternative "bcrypt:weaker, legacy" `
  --alternative "scrypt:less library support" `
  --related-wp WP-0041 `
  --json
```

## Don't

- Don't write to `decisions.md` directly. The CLI enforces format.
