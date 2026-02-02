# Autopilot (Work Item → PR → Evidence Pack)

Autopilot is the “glue” that makes AI Coding Factory practical for full-time employees: it turns a story (`ACF-###`) into a consistent, auditable delivery workflow.

## What it does

- Creates a feature branch named `feature/ACF-###-<slug>`
- Generates a Review Pack artifact at `artifacts/review-pack/ACF-###.md`
- Records integration state at `artifacts/autopilot/ACF-###.json`
- Optional integrations:
  - GitHub: creates/fetches an Issue and creates a PR
  - Azure DevOps: creates/fetches a Work Item and creates a PR (Azure Repos), linking the Work Item to the PR
- Evidence step can post/update a PR comment with a standardized Evidence Pack section

## Usage

### 1) Start (branch + PR + initial artifacts)

```bash
python3 scripts/autopilot/autopilot.py start ACF-0123 --commit --push --draft
```

Auto-detects provider from `origin` when possible. You can force a provider:

```bash
python3 scripts/autopilot/autopilot.py start ACF-0123 --provider github --commit --push
python3 scripts/autopilot/autopilot.py start ACF-0123 --provider azuredevops --commit --push
```

### 2) Evidence (run checks + post PR evidence comment)

```bash
python3 scripts/autopilot/autopilot.py evidence ACF-0123 --run-local
```

To also run the full template build/test/coverage verification:

```bash
python3 scripts/autopilot/autopilot.py evidence ACF-0123 --run-local --full-verify
```

## Configuration

Set credentials via environment variables (recommended via your local `.env`):

### GitHub

- `GITHUB_TOKEN` (or `GH_TOKEN`)
- `GITHUB_REPOSITORY` (owner/repo) if it can’t be inferred from `origin`
- Optional: `GITHUB_API_URL` for GitHub Enterprise Server

### Azure DevOps

- `AZURE_DEVOPS_PAT`
- `AZURE_DEVOPS_ORG_URL` (e.g., `https://dev.azure.com/yourorg`)
- `AZURE_DEVOPS_PROJECT`
- `AZURE_DEVOPS_REPO`
- Optional: `AZURE_DEVOPS_WORK_ITEM_TYPE` (default: `User Story`)

## Notes

- Tokens are never written to disk; only IDs/URLs are stored in `artifacts/autopilot/`.
- Network calls are skipped in `--dry-run` mode.
- Autopilot is designed to support both platform work (this repo) and generated projects; set `--stories-dir`/`--tests-root` accordingly.

