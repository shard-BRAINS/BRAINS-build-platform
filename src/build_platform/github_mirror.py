"""One-way push mirror from .brains-build/ to GitHub Issues + Milestones.

Uses the `gh` CLI via subprocess — no token management here. Mirror state
(wp_id -> issue_number, sprint_file -> milestone_number) is persisted in
.brains-build/github-mirror.json so reconciliation is idempotent.
"""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from build_platform.paths import state_dir
from build_platform.schemas import (
    Deliverable,
    GitHubMirrorConfig,
    WorkPackage,
    Workstream,
    WPState,
    WPTier,
)
from build_platform.state import (
    load_config,
    load_deliverables,
    load_work_packages,
    load_workstreams,
    save_config,
)


class MirrorError(RuntimeError):
    """Raised when the mirror push fails."""


class MirrorMap(BaseModel):
    """Persisted maps for the mirror.

    - wps: wp_id -> issue_number
    - sprints: sprint_id -> milestone_number
    - seen_comments: issue_number_str -> [comment_id, ...] (v2.6 pull idempotency)
    """
    wps: dict[str, int] = Field(default_factory=dict)
    sprints: dict[str, int] = Field(default_factory=dict)
    seen_comments: dict[str, list[int]] = Field(default_factory=dict)
    labels_seeded: bool = False


def mirror_map_path(project_root: Path) -> Path:
    return state_dir(project_root) / "github-mirror.json"


def load_mirror_map(project_root: Path) -> MirrorMap:
    path = mirror_map_path(project_root)
    if not path.exists():
        return MirrorMap()
    return MirrorMap.model_validate_json(path.read_text(encoding="utf-8"))


def save_mirror_map(project_root: Path, mirror_map: MirrorMap) -> None:
    path = mirror_map_path(project_root)
    path.write_text(mirror_map.model_dump_json(indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# gh CLI wrapper
# ---------------------------------------------------------------------------

def _run_gh(args: list[str], *, input_: str | None = None) -> str:
    """Run a `gh` subprocess; return stdout. Raises MirrorError on non-zero exit."""
    if shutil.which("gh") is None:
        raise MirrorError(
            "`gh` CLI not found on PATH. Install from https://cli.github.com/ "
            "and run `gh auth login` before pushing the mirror."
        )
    proc = subprocess.run(
        ["gh", *args],
        input=input_,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise MirrorError(
            f"gh {' '.join(args)} failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def _gh_json(args: list[str]) -> object:
    return json.loads(_run_gh(args))


# ---------------------------------------------------------------------------
# Mappings: WP <-> Issue, Sprint <-> Milestone
# ---------------------------------------------------------------------------

_STATE_LABELS = {
    WPState.DEFINED: "state-defined",
    WPState.DISPATCHED: "state-dispatched",
    WPState.IN_REVIEW: "state-in-review",
    WPState.DONE: "state-done",
    WPState.BLOCKED: "state-blocked",
}

_TIER_LABELS = {WPTier.ONE: "tier-1", WPTier.TWO: "tier-2"}

# Color tokens chosen to match brand accents (no #FCC14D body — Gold Deep only).
_LABEL_COLORS = {
    "tier-1": "4DA8FF",       # Incubator Blue
    "tier-2": "D99518",       # Gold Deep
    "state-defined": "E5E5E5",
    "state-dispatched": "FCC14D",  # decorative gold OK on label, not body
    "state-in-review": "2A8B91",   # Trust Teal
    "state-done": "0E8A16",
    "state-blocked": "B45309",
}

_ALL_PLATFORM_LABELS = list(_STATE_LABELS.values()) + list(_TIER_LABELS.values())


def _prefixed(prefix: str, name: str) -> str:
    return f"{prefix}{name}" if not name.startswith(prefix) else name


def _wp_labels(prefix: str, wp: WorkPackage) -> list[str]:
    return [
        _prefixed(prefix, _STATE_LABELS[wp.state]),
        _prefixed(prefix, _TIER_LABELS[wp.tier]),
        _prefixed(prefix, f"workstream-{wp.workstream}"),
        _prefixed(prefix, f"deliverable-{wp.deliverable_id}"),
        _prefixed(prefix, f"persona-{wp.executor_persona}"),
    ]


def _wp_body(wp: WorkPackage) -> str:
    accept = "\n".join(f"- {a}" for a in wp.acceptance) or "- _None_"
    files = "\n".join(f"- `{f}`" for f in wp.spec_files) or "- _None_"
    depends = ", ".join(wp.depends_on) or "_None_"
    consult = ", ".join(wp.consult) or "_None_"
    history = "\n".join(
        f"- {ev.at} · {ev.by} · {ev.event}" for ev in wp.history
    ) or "- _None yet_"
    return f"""<!-- managed by BRAINS Build Platform; manual edits will be overwritten on next /build-mirror push -->

**Workstream:** `{wp.workstream}` · **Deliverable:** `{wp.deliverable_id}` · **Tier:** {wp.tier.value} · **Executor:** `{wp.executor_persona}`

## Spec
{wp.spec}

## Acceptance criteria
{accept}

## Files in scope
{files}

## Depends on
{depends}

## Consult
{consult}

## History
{history}
"""


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

def _repo_arg(cfg: GitHubMirrorConfig) -> str:
    if not cfg.owner or not cfg.repo:
        raise MirrorError("github.owner and github.repo must be set in config.yml")
    return f"{cfg.owner}/{cfg.repo}"


def ensure_label(cfg: GitHubMirrorConfig, name: str, *, color: str = "ededed",
                 description: str = "") -> None:
    """Create the label if missing; succeed silently if it exists."""
    repo = _repo_arg(cfg)
    full_name = _prefixed(cfg.label_prefix, name)
    # gh label list returns JSON we can scan for existence
    existing = _gh_json(["label", "list", "--repo", repo, "--json", "name", "--limit", "200"])
    names = {item["name"] for item in existing}
    if full_name in names:
        return
    _run_gh([
        "label", "create", full_name, "--repo", repo,
        "--color", color, "--description", description or full_name,
    ])


def seed_labels(cfg: GitHubMirrorConfig, workstreams: list[Workstream],
                deliverables: list[Deliverable], wps: list[WorkPackage]) -> list[str]:
    """Ensure all platform labels exist on the remote. Returns the labels seeded."""
    seeded: list[str] = []
    for base in _ALL_PLATFORM_LABELS:
        ensure_label(cfg, base, color=_LABEL_COLORS.get(base, "ededed"))
        seeded.append(_prefixed(cfg.label_prefix, base))
    for ws in workstreams:
        name = f"workstream-{ws.id}"
        ensure_label(cfg, name, color="0E8A16", description=ws.description)
        seeded.append(_prefixed(cfg.label_prefix, name))
    for d in deliverables:
        ensure_label(cfg, f"deliverable-{d.id}", color="5319E7",
                     description=d.title)
        seeded.append(_prefixed(cfg.label_prefix, f"deliverable-{d.id}"))
    personas = {wp.executor_persona for wp in wps}
    for p in personas:
        ensure_label(cfg, f"persona-{p}", color="C5DEF5", description=p)
        seeded.append(_prefixed(cfg.label_prefix, f"persona-{p}"))
    return seeded


def ensure_milestone(cfg: GitHubMirrorConfig, title: str,
                     description: str = "") -> int:
    """Create the milestone if missing; return its number."""
    repo = _repo_arg(cfg)
    existing = _gh_json([
        "api", f"repos/{repo}/milestones", "--paginate",
        "-q", "[.[] | {number, title}]",
    ])
    for m in existing:  # type: ignore[union-attr]
        if m["title"] == title:
            return int(m["number"])
    created = _gh_json([
        "api", f"repos/{repo}/milestones",
        "-f", f"title={title}",
        "-f", f"description={description}",
    ])
    return int(created["number"])  # type: ignore[index]


def _issue_title(wp: WorkPackage) -> str:
    """Issue title with a [BLOCKED] prefix when WP state is blocked (Finding #6)."""
    prefix = "[BLOCKED] " if wp.state == WPState.BLOCKED else ""
    return f"{prefix}[{wp.id}] {wp.title}"


def _blocker_banner(wp: WorkPackage) -> str:
    """Body header rendered when state is blocked. Empty otherwise."""
    if wp.state != WPState.BLOCKED:
        return ""
    last = wp.history[-1].event if wp.history else "no reason recorded"
    return (
        f"> ⚠️ **This work package is BLOCKED.**\n"
        f"> Last event: _{last}_\n"
        f"> Resolve via `/build-decision` or a follow-up WP, then re-dispatch.\n\n"
    )


def push_workpackage(cfg: GitHubMirrorConfig, wp: WorkPackage,
                     mirror_map: MirrorMap,
                     *, milestone_number: int | None = None) -> int:
    """Create or update the issue for a WP. Returns the issue number."""
    repo = _repo_arg(cfg)
    title = _issue_title(wp)
    body = _blocker_banner(wp) + _wp_body(wp)
    labels = _wp_labels(cfg.label_prefix, wp)

    if wp.id in mirror_map.wps:
        number = mirror_map.wps[wp.id]
        edit_args = [
            "issue", "edit", str(number), "--repo", repo,
            "--title", title,
            "--body", body,
        ]
        for label in labels:
            edit_args.extend(["--add-label", label])
        if milestone_number:
            edit_args.extend(["--milestone", str(milestone_number)])
        _run_gh(edit_args)
        if wp.state == WPState.DONE:
            _run_gh(["issue", "close", str(number), "--repo", repo])
        elif wp.state == WPState.BLOCKED:
            _run_gh(["issue", "reopen", str(number), "--repo", repo])
        return number

    create_args = [
        "issue", "create", "--repo", repo,
        "--title", title,
        "--body", body,
    ]
    for label in labels:
        create_args.extend(["--label", label])
    if milestone_number:
        create_args.extend(["--milestone", str(milestone_number)])
    url = _run_gh(create_args).strip().splitlines()[-1]
    # gh prints the issue URL; the trailing path component is the number
    number = int(url.rstrip("/").split("/")[-1])
    mirror_map.wps[wp.id] = number
    if wp.state == WPState.DONE:
        _run_gh(["issue", "close", str(number), "--repo", repo])
    return number


def plan_push(project_root: Path) -> dict:
    """Compute what `push_all` would do, without calling gh write operations.

    Returns a JSON-serializable plan: which labels would be ensured, which
    milestones would be created vs reused, which WPs would be created vs
    edited, and end-state transitions (close/reopen) per WP.

    Read-only gh calls (label list, milestone list) are still made — they're
    safe and let the plan distinguish "create" from "reuse".
    """
    config = load_config(project_root)
    cfg = config.github
    if not cfg.enabled:
        raise MirrorError(
            "GitHub mirror is disabled. Run `/build-mirror init --owner X --repo Y` first."
        )
    repo = _repo_arg(cfg)

    deliverables = load_deliverables(project_root)
    workstreams = load_workstreams(project_root)
    wps = load_work_packages(project_root)
    mirror_map = load_mirror_map(project_root)

    # Labels — compute the full target set from current state.
    target_labels = set()
    for base in _ALL_PLATFORM_LABELS:
        target_labels.add(_prefixed(cfg.label_prefix, base))
    for ws in workstreams:
        target_labels.add(_prefixed(cfg.label_prefix, f"workstream-{ws.id}"))
    for d in deliverables:
        target_labels.add(_prefixed(cfg.label_prefix, f"deliverable-{d.id}"))
    for p in {wp.executor_persona for wp in wps}:
        target_labels.add(_prefixed(cfg.label_prefix, f"persona-{p}"))

    # Read-only gh probe to find existing labels.
    try:
        existing = _gh_json(["label", "list", "--repo", repo, "--json", "name", "--limit", "200"])
        existing_label_names = {item["name"] for item in existing}  # type: ignore[union-attr]
    except MirrorError:
        existing_label_names = set()  # treat as 'all missing' if probe fails

    labels_to_create = sorted(target_labels - existing_label_names)
    labels_already_present = sorted(target_labels & existing_label_names)

    # Sprints / milestones.
    sprints_dir = state_dir(project_root) / "sprints"
    sprint_plan = []
    if sprints_dir.exists():
        for sprint_file in sorted(sprints_dir.glob("sprint-*.md")):
            sprint_id = sprint_file.stem
            sprint_plan.append({
                "sprint_id": sprint_id,
                "action": "reuse" if sprint_id in mirror_map.sprints else "create",
                "milestone_number": mirror_map.sprints.get(sprint_id),
            })

    # WPs — create vs edit + state transition.
    wp_plan = []
    for wp in wps:
        action = "edit" if wp.id in mirror_map.wps else "create"
        post_state = None
        if wp.state == WPState.DONE:
            post_state = "close"
        elif wp.state == WPState.BLOCKED:
            post_state = "reopen"
        wp_plan.append({
            "wp_id": wp.id,
            "issue": mirror_map.wps.get(wp.id),
            "action": action,
            "state": wp.state.value,
            "post_action": post_state,
        })

    return {
        "ok": True,
        "dry_run": True,
        "repo": repo,
        "labels": {
            "to_create": labels_to_create,
            "already_present": labels_already_present,
            "total_target": len(target_labels),
        },
        "sprints": sprint_plan,
        "wps": wp_plan,
        "counts": {
            "wps_to_create": sum(1 for w in wp_plan if w["action"] == "create"),
            "wps_to_edit": sum(1 for w in wp_plan if w["action"] == "edit"),
            "wps_to_close": sum(1 for w in wp_plan if w["post_action"] == "close"),
            "wps_to_reopen": sum(1 for w in wp_plan if w["post_action"] == "reopen"),
            "labels_to_create": len(labels_to_create),
            "sprints_to_create": sum(1 for s in sprint_plan if s["action"] == "create"),
        },
    }


# ---------------------------------------------------------------------------
# v2.6 Pull side — read remote state, reconcile local
# ---------------------------------------------------------------------------

def fetch_issue_state(cfg: GitHubMirrorConfig, issue_number: int) -> dict:
    """Return {state, closed_at, author_login} for one issue. Used by pull
    to detect remote state changes (closed/reopened)."""
    repo = _repo_arg(cfg)
    raw = _gh_json([
        "issue", "view", str(issue_number), "--repo", repo,
        "--json", "state,closedAt,author",
    ])
    return {
        "state": raw.get("state", "").lower(),  # type: ignore[union-attr]
        "closed_at": raw.get("closedAt"),       # type: ignore[union-attr]
        "author_login": (raw.get("author") or {}).get("login", "github"),  # type: ignore[union-attr]
    }


def fetch_issue_comments(cfg: GitHubMirrorConfig, issue_number: int) -> list[dict]:
    """Return all comments on an issue. Uses the REST API (not `gh issue view`)
    because the latter does not return comment ids — which we need for the
    seen_comments idempotency map."""
    repo = _repo_arg(cfg)
    return _gh_json([
        "api", f"repos/{repo}/issues/{issue_number}/comments",
        "--paginate",
    ])  # type: ignore[return-value]


def parse_bbp_decision_comment(body: str) -> dict | None:
    """Parse a comment body as a bbp:decision payload, or return None.

    Expected format (first line MUST be 'bbp:decision'):

      bbp:decision
      title: <one line>
      owner: <persona id or user:name>
      decision: <one sentence>
      why: <rationale>
      alternatives: name1:reason; name2:reason   (optional)
      related-wp: WP-XXXX, WP-YYYY               (optional)

    Returns a dict with normalized keys, or None if not a decision comment
    or missing required fields (title, decision).
    """
    lines = body.strip().splitlines()
    if not lines or lines[0].strip() != "bbp:decision":
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()
    if not fields.get("title") or not fields.get("decision"):
        return None
    related = fields.get("related-wp", "")
    return {
        "title": fields["title"],
        "owner": fields.get("owner", "user"),
        "decision": fields["decision"],
        "why": fields.get("why", ""),
        "alternatives": fields.get("alternatives", ""),
        "related_wps": [w.strip() for w in related.split(",") if w.strip()],
    }


def _format_decision_entry(date: str, parsed: dict, source_url: str) -> str:
    """Render a parsed bbp:decision dict into the decisions.md schema."""
    alts = parsed.get("alternatives", "")
    if alts:
        alt_str = ", ".join(
            f"{a.split(':', 1)[0].strip()} (rejected: {a.split(':', 1)[1].strip() if ':' in a else '—'})"
            for a in alts.split(";") if a.strip()
        )
    else:
        alt_str = "_None_"
    related = ", ".join(parsed["related_wps"]) or "_None_"
    return (
        f"\n## {date} — {parsed['title']}\n"
        f"**Owner:** {parsed['owner']}\n"
        f"**Decision:** {parsed['decision']}\n"
        f"**Why:** {parsed['why'] or '_Not specified_'}\n"
        f"**Alternatives considered:** {alt_str}\n"
        f"**Related WPs:** {related}\n"
        f"**Source:** [GitHub comment]({source_url})\n"
    )


def _reconcile_wp_state(
    project_root: Path,
    wp_id: str,
    local_state: WPState,
    remote: dict,
) -> dict | None:
    """Apply WP-0003 state-transition rules.

    Returns a dict describing the transition that happened, or None if no-op.
    """
    remote_state = remote["state"]
    actor = remote["author_login"]
    by = f"github:{actor}"

    # Remote closed -> local should be DONE (if it isn't already).
    if remote_state == "closed":
        if local_state == WPState.DONE:
            return None
        # Only transition from non-terminal states; preserve BLOCKED as a signal.
        if local_state == WPState.BLOCKED:
            return {"wp_id": wp_id, "from": local_state.value, "to": None,
                    "skipped": "remote closed but local is blocked; manual review"}
        from build_platform.state import update_wp_state
        update_wp_state(project_root, wp_id, WPState.DONE,
                        by=by, event=f"remote issue closed by {actor}")
        return {"wp_id": wp_id, "from": local_state.value, "to": "done"}

    # Remote open + local previously DONE -> someone reopened; surface as blocked.
    if remote_state == "open" and local_state == WPState.DONE:
        from build_platform.state import update_wp_state
        update_wp_state(project_root, wp_id, WPState.BLOCKED,
                        by=by, event=f"remote issue reopened by {actor}; needs review")
        return {"wp_id": wp_id, "from": "done", "to": "blocked"}

    return None  # all other combos: no-op


def _ingest_new_decision_comments(
    project_root: Path,
    cfg: GitHubMirrorConfig,
    wp_id: str,
    issue_number: int,
    mirror_map: MirrorMap,
) -> list[dict]:
    """WP-0004: fetch comments, append new bbp:decision ones to decisions.md.

    Idempotency: tracks ingested comment ids in mirror_map.seen_comments
    keyed by str(issue_number). Returns the list of ingested decisions.
    """
    key = str(issue_number)
    seen = set(mirror_map.seen_comments.get(key, []))
    try:
        comments = fetch_issue_comments(cfg, issue_number)
    except MirrorError:
        return []

    # state_dir() already returns the .brains-build/ directory.
    decisions_md = state_dir(project_root) / "decisions.md"

    ingested: list[dict] = []
    for c in comments:
        cid = c.get("id")
        if cid is None or cid in seen:
            continue
        parsed = parse_bbp_decision_comment(c.get("body", ""))
        if parsed is None:
            continue
        created_at = c.get("created_at", "")
        date = (created_at[:10] if created_at else datetime.now(timezone.utc).date().isoformat())
        entry = _format_decision_entry(date, parsed, c.get("html_url", ""))
        with decisions_md.open("a", encoding="utf-8") as f:
            f.write(entry)
        seen.add(cid)
        ingested.append({
            "comment_id": cid,
            "title": parsed["title"],
            "from_wp": wp_id,
            "from_issue": issue_number,
        })

    if ingested:
        mirror_map.seen_comments[key] = sorted(seen)
    return ingested


def pull_all(project_root: Path) -> dict:
    """v2.6: reconcile remote (GitHub) -> local. Returns a summary dict.

    Drives WP-0002/0003/0004 together:
      - For each mapped WP: fetch issue state + comments via gh.
      - Apply state-transition rules (closed -> done, reopened-done -> blocked).
      - Ingest new bbp:decision comments to decisions.md (idempotent).
    """
    config = load_config(project_root)
    cfg = config.github
    if not cfg.enabled:
        raise MirrorError(
            "GitHub mirror is disabled. Run `/build-mirror init --owner X --repo Y` first."
        )

    mirror_map = load_mirror_map(project_root)
    wps_state = {wp.id: wp.state for wp in load_work_packages(project_root)}

    remote_states: list[dict] = []
    transitions: list[dict] = []
    ingested_decisions: list[dict] = []

    for wp_id, issue_number in sorted(mirror_map.wps.items()):
        try:
            remote = fetch_issue_state(cfg, issue_number)
        except MirrorError:
            remote_states.append({"wp_id": wp_id, "issue": issue_number, "error": "fetch failed"})
            continue
        remote_states.append({
            "wp_id": wp_id, "issue": issue_number,
            "remote_state": remote["state"],
            "author": remote["author_login"],
        })

        local = wps_state.get(wp_id)
        if local is not None:
            transition = _reconcile_wp_state(project_root, wp_id, local, remote)
            if transition is not None:
                transitions.append(transition)

        ingested_decisions.extend(
            _ingest_new_decision_comments(project_root, cfg, wp_id, issue_number, mirror_map)
        )

    save_mirror_map(project_root, mirror_map)

    return {
        "ok": True,
        "repo": _repo_arg(cfg),
        "remote_states": remote_states,
        "transitions": transitions,
        "ingested_decisions": ingested_decisions,
    }


def push_all(project_root: Path, *, dry_run: bool = False) -> dict:
    """Reconcile every local WP + sprint to GitHub. Returns a summary dict.

    When dry_run=True, no state-changing gh calls are made. The function
    returns the same shape as plan_push().
    """
    if dry_run:
        return plan_push(project_root)

    config = load_config(project_root)
    cfg = config.github
    if not cfg.enabled:
        raise MirrorError(
            "GitHub mirror is disabled. Run `/build-mirror init --owner X --repo Y` first."
        )
    repo = _repo_arg(cfg)

    deliverables = load_deliverables(project_root)
    workstreams = load_workstreams(project_root)
    wps = load_work_packages(project_root)

    mirror_map = load_mirror_map(project_root)

    if not mirror_map.labels_seeded:
        seed_labels(cfg, workstreams, deliverables, wps)
        mirror_map.labels_seeded = True

    # Milestones: one per sprint file. Sprint files appear when /build-scrum runs.
    sprints_dir = state_dir(project_root) / "sprints"
    sprint_milestones: dict[str, int] = {}
    if sprints_dir.exists():
        for sprint_file in sorted(sprints_dir.glob("sprint-*.md")):
            sprint_id = sprint_file.stem
            if sprint_id in mirror_map.sprints:
                sprint_milestones[sprint_id] = mirror_map.sprints[sprint_id]
                continue
            number = ensure_milestone(
                cfg, title=sprint_id.replace("-", " ").title(),
                description=f"Auto-mirrored from {sprint_file.name}",
            )
            mirror_map.sprints[sprint_id] = number
            sprint_milestones[sprint_id] = number

    pushed = []
    for wp in wps:
        number = push_workpackage(cfg, wp, mirror_map)
        pushed.append({"wp_id": wp.id, "issue": number})

    cfg.last_synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_config(project_root, config)
    save_mirror_map(project_root, mirror_map)

    return {
        "ok": True,
        "repo": repo,
        "wps_pushed": len(pushed),
        "sprints_milestoned": len(sprint_milestones),
        "issues": pushed,
        "last_synced_at": cfg.last_synced_at,
    }
