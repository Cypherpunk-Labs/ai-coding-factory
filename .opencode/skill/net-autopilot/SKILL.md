---
name: net-autopilot
description: Automate Work Item -> Branch -> PR -> Evidence Pack for AI Coding Factory
license: MIT
compatibility: opencode
metadata:
  audience: enterprise-teams
  governance: traceability
  integrations: github, azure-devops
  framework: dotnet
---

## What I Do

I help teams run **AI Coding Factory Autopilot** as the standard delivery workflow:
- Create a feature branch per story (`ACF-###`)
- Create/link the work item (GitHub Issue or Azure DevOps Work Item)
- Create a PR with a consistent title/body format
- Generate and maintain an **Evidence/Review Pack** to support human review and governance

## When to Use Me

Use this skill when you want “one workflow” that supports full-time employees:
- Starting work on a story and needing a PR immediately
- Enforcing Story → PR → Evidence Pack consistency across teams
- Keeping audit artifacts updated without manual overhead

## Inputs

- Story file in `artifacts/stories/ACF-###*.md`
- Git remote configured (GitHub or Azure Repos)
- Credentials via environment variables (do not store secrets in repo)

## Outputs

- Review pack: `artifacts/review-pack/ACF-###.md`
- Autopilot state (IDs/URLs only): `artifacts/autopilot/ACF-###.json`
- PR comment/thread: Evidence Pack marker `<!-- acf-autopilot:evidence -->`

## Commands

### Start (branch + PR + initial artifacts)

```bash
python3 scripts/autopilot/autopilot.py start ACF-0123 --commit --push --draft
```

### Evidence (run checks + post/update PR evidence comment)

```bash
python3 scripts/autopilot/autopilot.py evidence ACF-0123 --run-local
```

Optional full template verification:

```bash
python3 scripts/autopilot/autopilot.py evidence ACF-0123 --run-local --full-verify
```

## Configuration

### GitHub

- `GITHUB_TOKEN` (or `GH_TOKEN`)
- `GITHUB_REPOSITORY` (owner/repo) if it can’t be inferred from `origin`
- `GITHUB_API_URL` (optional; GitHub Enterprise Server)

### Azure DevOps

- `AZURE_DEVOPS_PAT`
- `AZURE_DEVOPS_ORG_URL` (e.g., `https://dev.azure.com/yourorg`)
- `AZURE_DEVOPS_PROJECT`
- `AZURE_DEVOPS_REPO`
- `AZURE_DEVOPS_WORK_ITEM_TYPE` (optional; default `User Story`)

## Governance Notes

- Autopilot stores **no secrets** on disk; only IDs/URLs.
- If credentials are missing, Autopilot still generates local artifacts; use `--require-integration` to hard-fail.
- PR creation requires the branch to be pushed; use `--push`.

