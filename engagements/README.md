# Engagements (per-program hunt runtime)

Hunt evidence, brain, and sessions for each bug bounty program live here when
this repository is the Cursor workspace root.

**Nothing under `engagements/<slug>/` is committed** — local runtime only.

## Active engagement

`engagements/.active` contains the slug (e.g. `acme-corp`). Tools resolve
`brain/`, `evidence/`, and `recon/` under `engagements/<slug>/`.

Override: `PENTEST_ENGAGEMENT=<slug>`

## Autopilot gate

```bash
uv run python3 tools/autopilot_gate.py --root engagements/<slug> ...
```

## Portfolio dossier

Contract, STATUS, and summaries: `data/dossiers/<slug>/`

Phase 2 precondition:

```bash
uv run python tools/dossier_precondition.py <slug>
```

After a hunt session, sync back to the dossier:

```bash
uv run python tools/dossier_sync_from_engagement.py <slug>
```
