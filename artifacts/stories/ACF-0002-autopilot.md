---
id: ACF-0002
title: Autopilot (Work Item → PR → Evidence Pack) with GitHub and Azure DevOps integration
type: Story
status: In Progress
owner: Product Owner Agent
---

# ACF-0002 - Autopilot (Work Item → PR → Evidence Pack) with GitHub and Azure DevOps integration

## User Story

As a full-time employee,
I want a single autopilot workflow that turns an `ACF-###` story into a branch, PR, and auditable evidence pack,
So that delivery is fast, consistent, and reviewable without losing governance.

## Acceptance Criteria

- `scripts/autopilot/autopilot.py` can:
  - Create a `feature/ACF-###-<slug>` branch from a base branch
  - Generate `artifacts/review-pack/ACF-###.md`
  - Persist integration state in `artifacts/autopilot/ACF-###.json` (no secrets)
- GitHub integration:
  - Create or re-use an Issue for the story ID
  - Create a PR titled `ACF-###: <title>` and post/update an evidence comment
- Azure DevOps integration:
  - Create or re-use a Work Item for the story ID
  - Create an Azure Repos PR titled `ACF-###: <title>`, link the Work Item to the PR, and post an evidence comment
- Offline-first behavior:
  - If credentials are missing, autopilot can still run locally and generate artifacts
  - `--dry-run` performs no network operations

## Traceability Expectations

- Tests reference `ACF-0002`
- Commits include `ACF-0002` in message
- Release notes include `ACF-0002`

