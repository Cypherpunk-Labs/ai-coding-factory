#!/usr/bin/env python3
"""
AI Coding Factory Autopilot

Work Item (ACF-###) -> Branch -> PR -> Evidence Pack

This script is designed to be offline-first:
- It can prepare branches and generate local artifacts without network.
- GitHub / Azure DevOps integration activates only when credentials are present.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as _dt
import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


STORY_ID_RE = re.compile(r"^ACF-\d+$")


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def _run_live(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, check=check)


def _git(args: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return _run(["git", *args], check=check)


def _git_live(args: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return _run_live(["git", *args], check=check)


def _repo_root() -> pathlib.Path:
    cp = _git(["rev-parse", "--show-toplevel"])
    return pathlib.Path(cp.stdout.strip())


def _require_clean_worktree(*, allow_untracked: bool) -> None:
    cp = _git(["status", "--porcelain"])
    lines = [l for l in cp.stdout.splitlines() if l.strip()]
    if not lines:
        return
    if allow_untracked:
        lines = [l for l in lines if not l.startswith("?? ")]
        if not lines:
            return
    raise RuntimeError(
        "Working tree is not clean. Commit/stash changes, or re-run with --allow-untracked."
    )


def _slugify(text: str, *, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_len] or "work"


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _parse_story(stories_dir: pathlib.Path, story_id: str) -> Tuple[pathlib.Path, str, str]:
    if not STORY_ID_RE.fullmatch(story_id):
        raise ValueError(f"Invalid story id: {story_id} (expected ACF-###)")

    path = stories_dir / f"{story_id}.md"
    if not path.exists():
        # Fallback: locate by scanning
        matches = list(stories_dir.rglob("*.md"))
        for p in matches:
            if story_id in _read_text(p):
                path = p
                break

    if not path.exists():
        raise FileNotFoundError(f"Story file not found for {story_id} under {stories_dir}")

    content = _read_text(path)
    title = ""
    body_title = ""

    # Frontmatter title:
    if content.startswith("---"):
        for line in content.splitlines()[1:80]:
            if line.strip() == "---":
                break
            if line.lower().startswith("title:"):
                title = line.split(":", 1)[1].strip()
                break

    # Heading title:
    for line in content.splitlines():
        m = re.match(r"^#+\s+(.+)$", line.strip())
        if m:
            body_title = m.group(1).strip()
            break

    effective_title = title or body_title.replace(story_id, "").strip(" -:") or "Untitled"
    return path, effective_title, content


def _ensure_dir(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclasses.dataclass(frozen=True)
class ProviderRef:
    kind: str  # "github" | "azuredevops"
    issue: Optional[Dict[str, Any]]
    pr: Optional[Dict[str, Any]]


def _http_json(
    *,
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[Dict[str, Any]] = None,
    accept: str = "application/json",
) -> Any:
    req_headers = dict(headers)
    req_headers.setdefault("Accept", accept)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} {e.reason} for {url}: {raw[:1200]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error for {url}: {e}") from e


def _github_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-coding-factory-autopilot",
    }


def _github_repo_from_origin() -> Optional[str]:
    cp = _git(["remote", "get-url", "origin"], check=False)
    if cp.returncode != 0:
        return None
    url = cp.stdout.strip()
    if not url:
        return None
    # git@github.com:owner/repo.git
    m = re.match(r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # https://github.com/owner/repo.git
    m = re.match(r"^https?://github\.com/([^/]+)/(.+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def _github_find_or_create_issue(
    *,
    api_url: str,
    token: str,
    repo: str,
    story_id: str,
    story_title: str,
    story_content: str,
    dry_run: bool,
) -> Optional[Dict[str, Any]]:
    headers = _github_headers(token)
    q = urllib.parse.quote(f"repo:{repo} {story_id} in:title type:issue")
    search_url = f"{api_url}/search/issues?q={q}"
    if dry_run:
        return {"number": 0, "html_url": "(dry-run)", "title": f"{story_id}: {story_title}"}
    res = _http_json(method="GET", url=search_url, headers=headers)
    items = res.get("items", []) if isinstance(res, dict) else []
    if items:
        return {"number": items[0]["number"], "html_url": items[0]["html_url"], "title": items[0]["title"]}

    create_url = f"{api_url}/repos/{repo}/issues"
    body = textwrap.dedent(
        f"""\
        {story_id}: {story_title}

        This issue is managed by AI Coding Factory Autopilot.

        **Story File (source of truth)**: `{_relative_story_path_guess(story_id)}`

        ---
        {story_content}
        """
    ).strip()
    payload = {"title": f"{story_id}: {story_title}", "body": body, "labels": ["ai-coding-factory", "autopilot"]}
    issue = _http_json(method="POST", url=create_url, headers=headers, body=payload)
    return {"number": issue["number"], "html_url": issue["html_url"], "title": issue["title"]}


def _github_create_pr(
    *,
    api_url: str,
    token: str,
    repo: str,
    base_branch: str,
    head_branch: str,
    title: str,
    body: str,
    draft: bool,
    dry_run: bool,
) -> Optional[Dict[str, Any]]:
    if dry_run:
        return {"number": 0, "html_url": "(dry-run)", "title": title}
    headers = _github_headers(token)
    url = f"{api_url}/repos/{repo}/pulls"
    payload = {
        "title": title,
        "head": head_branch,
        "base": base_branch,
        "body": body,
        "draft": draft,
    }
    pr = _http_json(method="POST", url=url, headers=headers, body=payload)
    return {"number": pr["number"], "html_url": pr["html_url"], "title": pr["title"]}


def _github_upsert_pr_comment(
    *,
    api_url: str,
    token: str,
    repo: str,
    pr_number: int,
    marker: str,
    body: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    headers = _github_headers(token)
    list_url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments?per_page=100"
    comments = _http_json(method="GET", url=list_url, headers=headers) or []
    existing = None
    for c in comments:
        if marker in (c.get("body") or ""):
            existing = c
            break
    final_body = f"{marker}\n{body}"
    if existing:
        upd_url = f"{api_url}/repos/{repo}/issues/comments/{existing['id']}"
        _http_json(method="PATCH", url=upd_url, headers=headers, body={"body": final_body})
    else:
        create_url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments"
        _http_json(method="POST", url=create_url, headers=headers, body={"body": final_body})


def _azure_headers(pat: str) -> Dict[str, str]:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "User-Agent": "ai-coding-factory-autopilot",
    }


def _azure_repo_from_origin() -> Optional[Tuple[str, str, str]]:
    """
    Returns (org_url, project, repo_name) when origin points to Azure Repos.
    """
    cp = _git(["remote", "get-url", "origin"], check=False)
    if cp.returncode != 0:
        return None
    url = cp.stdout.strip()
    if not url:
        return None
    # https://dev.azure.com/{org}/{project}/_git/{repo}
    m = re.match(r"^(https?://dev\.azure\.com/[^/]+/[^/]+)/_git/([^/]+)$", url)
    if m:
        org_project = m.group(1)
        repo = m.group(2)
        # org_project includes org+project; split last segment as project
        parts = org_project.split("/")
        org_url = "/".join(parts[:-1])
        project = parts[-1]
        return (org_url, project, repo)
    return None


def _azure_wiql_find_work_item(
    *, org_url: str, project: str, pat: str, story_id: str, dry_run: bool
) -> Optional[int]:
    if dry_run:
        return 0
    headers = _azure_headers(pat)
    url = f"{org_url}/{project}/_apis/wit/wiql?api-version=7.1-preview.2"
    query = {
        "query": (
            "SELECT [System.Id] FROM WorkItems "
            "WHERE [System.TeamProject] = @project "
            f"AND [System.Title] CONTAINS '{story_id}' "
            "ORDER BY [System.ChangedDate] DESC"
        )
    }
    res = _http_json(method="POST", url=url, headers=headers, body=query)
    items = res.get("workItems", []) if isinstance(res, dict) else []
    if not items:
        return None
    return int(items[0]["id"])


def _azure_create_work_item(
    *,
    org_url: str,
    project: str,
    pat: str,
    work_item_type: str,
    story_id: str,
    story_title: str,
    story_content: str,
    dry_run: bool,
) -> int:
    if dry_run:
        return 0
    headers = _azure_headers(pat)
    headers["Content-Type"] = "application/json-patch+json"
    wi_type = urllib.parse.quote(work_item_type)
    url = f"{org_url}/{project}/_apis/wit/workitems/${wi_type}?api-version=7.1-preview.3"
    desc = textwrap.dedent(
        f"""\
        <p><strong>Managed by AI Coding Factory Autopilot</strong></p>
        <p><strong>Story ID:</strong> {story_id}</p>
        <pre>{_html_escape(story_content[:20000])}</pre>
        """
    ).strip()
    patch = [
        {"op": "add", "path": "/fields/System.Title", "value": f"{story_id}: {story_title}"},
        {"op": "add", "path": "/fields/System.Description", "value": desc},
    ]
    wi = _http_json(method="POST", url=url, headers=headers, body=patch, accept="application/json")
    return int(wi["id"])


def _azure_create_pr(
    *,
    org_url: str,
    project: str,
    repo: str,
    pat: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str,
    is_draft: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    if dry_run:
        return {"pullRequestId": 0, "url": "(dry-run)", "title": title}
    headers = _azure_headers(pat)
    url = f"{org_url}/{project}/_apis/git/repositories/{urllib.parse.quote(repo)}/pullrequests?api-version=7.1-preview.1"
    payload = {
        "sourceRefName": f"refs/heads/{source_branch}",
        "targetRefName": f"refs/heads/{target_branch}",
        "title": title,
        "description": description,
        "isDraft": is_draft,
    }
    pr = _http_json(method="POST", url=url, headers=headers, body=payload)
    return pr


def _azure_link_work_item_to_pr(
    *,
    org_url: str,
    project: str,
    pat: str,
    work_item_id: int,
    pr_id: int,
    repo: str,
    dry_run: bool,
) -> None:
    if dry_run or work_item_id == 0 or pr_id == 0:
        return
    headers = _azure_headers(pat)
    headers["Content-Type"] = "application/json-patch+json"
    artifact = f"vstfs:///Git/PullRequestId/{urllib.parse.quote(project)}%2F{urllib.parse.quote(repo)}%2F{pr_id}"
    url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}?api-version=7.1-preview.3"
    patch = [
        {
            "op": "add",
            "path": "/relations/-",
            "value": {"rel": "ArtifactLink", "url": artifact, "attributes": {"name": "Pull Request"}},
        }
    ]
    _http_json(method="PATCH", url=url, headers=headers, body=patch, accept="application/json")


def _azure_post_pr_comment(
    *,
    org_url: str,
    project: str,
    repo: str,
    pat: str,
    pr_id: int,
    body: str,
    dry_run: bool,
) -> None:
    if dry_run or pr_id == 0:
        return
    headers = _azure_headers(pat)
    url = (
        f"{org_url}/{project}/_apis/git/repositories/{urllib.parse.quote(repo)}"
        f"/pullRequests/{pr_id}/threads?api-version=7.1-preview.1"
    )
    payload = {"comments": [{"content": body, "commentType": 1}], "status": 1}
    _http_json(method="POST", url=url, headers=headers, body=payload)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _relative_story_path_guess(story_id: str) -> str:
    return f"artifacts/stories/{story_id}.md"


def _state_path(repo_root: pathlib.Path, story_id: str) -> pathlib.Path:
    return repo_root / "artifacts" / "autopilot" / f"{story_id}.json"


def _review_pack_path(repo_root: pathlib.Path, story_id: str) -> pathlib.Path:
    return repo_root / "artifacts" / "review-pack" / f"{story_id}.md"


def _write_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(_read_text(path))


def _write_review_pack(
    *, repo_root: pathlib.Path, story_id: str, story_title: str, story_file: pathlib.Path
) -> pathlib.Path:
    out = _review_pack_path(repo_root, story_id)
    _ensure_dir(out.parent)
    rel_story = str(story_file.relative_to(repo_root))
    out.write_text(
        textwrap.dedent(
            f"""\
            # Review Pack — {story_id}: {story_title}

            Generated: {_now_utc_iso()}

            ## Links
            - Story file: `{rel_story}`

            ## Scope (Human-verified)
            - [ ] Scope matches acceptance criteria
            - [ ] No new dependencies without ADR approval
            - [ ] Security model changes reviewed (if applicable)

            ## Evidence (Autopilot)
            - [ ] `scripts/validate-project.sh`
            - [ ] `scripts/validate-documentation.sh`
            - [ ] `scripts/validate-rnd-policy.sh`
            - [ ] `python3 scripts/traceability/traceability.py validate`
            - [ ] Optional: `scripts/scaffold-and-verify.sh` (template build/test/coverage)

            ## Notes
            - Add any reviewer notes, risks, or waivers here (link to ADRs/waivers if needed).
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return out


def _compose_pr_body(
    *,
    repo_root: pathlib.Path,
    story_id: str,
    story_title: str,
    story_file: pathlib.Path,
    issue_ref: Optional[str],
    review_pack_file: pathlib.Path,
) -> str:
    rel_story = str(story_file.relative_to(repo_root))
    rel_review = str(review_pack_file.relative_to(repo_root))
    parts = [
        f"## {story_id}: {story_title}",
        "",
        f"- Story: `{rel_story}`",
        f"- Review pack: `{rel_review}`",
    ]
    if issue_ref:
        parts.append(f"- Work item: {issue_ref}")
    parts.extend(
        [
            "",
            "## Autopilot checklist",
            "- [ ] Evidence pack generated/updated",
            "- [ ] Traceability passes (Story → Test → Commit → Release)",
            "- [ ] Policy self-checks completed",
        ]
    )
    return "\n".join(parts).strip() + "\n"


def cmd_start(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    stories_dir = repo_root / args.stories_dir

    story_file, story_title, story_content = _parse_story(stories_dir, args.story_id)
    branch_slug = _slugify(story_title)
    branch = f"feature/{args.story_id}-{branch_slug}"

    if not args.dry_run:
        _require_clean_worktree(allow_untracked=args.allow_untracked)

    # Ensure base branch exists locally.
    if not args.dry_run:
        _git_live(["fetch", "origin", args.base_branch], check=False)
        _git_live(["checkout", args.base_branch])
        _git_live(["pull", "--ff-only"], check=False)
        _git_live(["checkout", "-b", branch])

    review_pack = _write_review_pack(
        repo_root=repo_root, story_id=args.story_id, story_title=story_title, story_file=story_file
    )

    state = {
        "storyId": args.story_id,
        "storyTitle": story_title,
        "storyFile": str(story_file.relative_to(repo_root)),
        "branch": branch,
        "baseBranch": args.base_branch,
        "createdAt": _now_utc_iso(),
        "provider": {},
    }

    state_file = _state_path(repo_root, args.story_id)
    _write_json(state_file, state)

    if not args.dry_run and args.commit:
        _git_live(["add", str(review_pack.relative_to(repo_root)), str(state_file.relative_to(repo_root))])
        _git_live(["commit", "-m", f"{args.story_id}: start autopilot"])
        if args.push:
            _git_live(["push", "-u", "origin", branch])

    provider = args.provider
    if provider == "auto":
        provider = "azuredevops" if _azure_repo_from_origin() else "github"

    provider_ref: ProviderRef = ProviderRef(kind=provider, issue=None, pr=None)

    # Provider integration happens after the branch exists remotely (PR creation requires it).
    if provider == "github":
        token = args.github_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        repo = args.github_repo or os.environ.get("GITHUB_REPOSITORY") or _github_repo_from_origin()
        api_url = args.github_api_url or os.environ.get("GITHUB_API_URL") or "https://api.github.com"
        if not token or not repo:
            if args.require_integration:
                raise RuntimeError("GitHub integration requires GITHUB_TOKEN (or GH_TOKEN) and repo (GITHUB_REPOSITORY).")
        else:
            if not args.push and not args.dry_run:
                raise RuntimeError("GitHub PR creation requires pushing the branch. Re-run with --push.")
            issue = _github_find_or_create_issue(
                api_url=api_url,
                token=token,
                repo=repo,
                story_id=args.story_id,
                story_title=story_title,
                story_content=story_content,
                dry_run=args.dry_run,
            )
            issue_ref = f"#{issue['number']}" if issue and issue.get("number") else None
            pr_body = _compose_pr_body(
                repo_root=repo_root,
                story_id=args.story_id,
                story_title=story_title,
                story_file=story_file,
                issue_ref=issue_ref,
                review_pack_file=review_pack,
            )
            pr = _github_create_pr(
                api_url=api_url,
                token=token,
                repo=repo,
                base_branch=args.base_branch,
                head_branch=branch,
                title=f"{args.story_id}: {story_title}",
                body=pr_body,
                draft=args.draft,
                dry_run=args.dry_run,
            )
            provider_ref = ProviderRef(kind="github", issue=issue, pr=pr)
            state["provider"] = {"kind": "github", "apiUrl": api_url, "repo": repo, "issue": issue, "pr": pr}

    elif provider == "azuredevops":
        pat = args.azure_pat or os.environ.get("AZURE_DEVOPS_PAT")
        org_url = args.azure_org_url or os.environ.get("AZURE_DEVOPS_ORG_URL")
        project = args.azure_project or os.environ.get("AZURE_DEVOPS_PROJECT")
        repo = args.azure_repo or os.environ.get("AZURE_DEVOPS_REPO")
        wi_type = args.azure_work_item_type or os.environ.get("AZURE_DEVOPS_WORK_ITEM_TYPE") or "User Story"

        if not org_url or not project or not repo:
            inferred = _azure_repo_from_origin()
            if inferred and not org_url and not project and not repo:
                org_url, project, repo = inferred

        if not pat or not org_url or not project or not repo:
            if args.require_integration:
                raise RuntimeError(
                    "Azure DevOps integration requires AZURE_DEVOPS_PAT, AZURE_DEVOPS_ORG_URL, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_REPO."
                )
        else:
            if not args.push and not args.dry_run:
                raise RuntimeError("Azure DevOps PR creation requires pushing the branch. Re-run with --push.")
            wi_id = _azure_wiql_find_work_item(
                org_url=org_url, project=project, pat=pat, story_id=args.story_id, dry_run=args.dry_run
            )
            if wi_id is None:
                wi_id = _azure_create_work_item(
                    org_url=org_url,
                    project=project,
                    pat=pat,
                    work_item_type=wi_type,
                    story_id=args.story_id,
                    story_title=story_title,
                    story_content=story_content,
                    dry_run=args.dry_run,
                )
            wi_ref = f"WorkItem {wi_id}" if wi_id is not None else None
            pr_body = _compose_pr_body(
                repo_root=repo_root,
                story_id=args.story_id,
                story_title=story_title,
                story_file=story_file,
                issue_ref=wi_ref,
                review_pack_file=review_pack,
            )
            pr = _azure_create_pr(
                org_url=org_url,
                project=project,
                repo=repo,
                pat=pat,
                source_branch=branch,
                target_branch=args.base_branch,
                title=f"{args.story_id}: {story_title}",
                description=pr_body,
                is_draft=args.draft,
                dry_run=args.dry_run,
            )
            pr_id = int(pr.get("pullRequestId", 0) or 0)
            _azure_link_work_item_to_pr(
                org_url=org_url,
                project=project,
                pat=pat,
                work_item_id=int(wi_id or 0),
                pr_id=pr_id,
                repo=repo,
                dry_run=args.dry_run,
            )
            provider_ref = ProviderRef(
                kind="azuredevops",
                issue={"id": int(wi_id or 0), "url": f"{org_url}/{project}/_workitems/edit/{wi_id}"},
                pr={"id": pr_id, "url": pr.get("url"), "title": pr.get("title")},
            )
            state["provider"] = {
                "kind": "azuredevops",
                "orgUrl": org_url,
                "project": project,
                "repo": repo,
                "workItemType": wi_type,
                "workItemId": int(wi_id or 0),
                "prId": pr_id,
                "prUrl": pr.get("url"),
            }
    else:
        raise RuntimeError(f"Unknown provider: {provider}")

    _write_json(state_file, state)
    if not args.dry_run and args.commit and state.get("provider"):
        _git_live(["add", str(state_file.relative_to(repo_root))])
        _git_live(["commit", "-m", f"{args.story_id}: link work item and PR"], check=False)
        if args.push:
            _git_live(["push"], check=False)

    # Console output (human-friendly)
    print(f"Story: {args.story_id}: {story_title}")
    print(f"Branch: {branch}")
    print(f"Review pack: {review_pack.relative_to(repo_root)}")
    print(f"State: {state_file.relative_to(repo_root)}")
    if provider_ref.issue:
        print(f"{provider_ref.kind} work item: {provider_ref.issue}")
    if provider_ref.pr:
        print(f"{provider_ref.kind} PR: {provider_ref.pr}")
    return 0


def _local_evidence_summary(repo_root: pathlib.Path, story_id: str, story_title: str) -> str:
    return textwrap.dedent(
        f"""\
        ## Evidence Pack — {story_id}: {story_title}

        Generated: {_now_utc_iso()}

        ### Commands
        - `./scripts/validate-project.sh`
        - `./scripts/validate-documentation.sh`
        - `./scripts/validate-rnd-policy.sh`
        - `python3 scripts/traceability/traceability.py validate --stories-dir artifacts/stories --tests-root .`

        ### Notes
        - This comment is managed by AI Coding Factory Autopilot.
        """
    ).strip()


def cmd_evidence(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    state_file = _state_path(repo_root, args.story_id)
    if not state_file.exists():
        raise FileNotFoundError(f"Autopilot state not found: {state_file}")
    state = _read_json(state_file)
    story_title = state.get("storyTitle", "Untitled")

    if args.run_local:
        # Local validations (do not assume dotnet/docker availability).
        _git_live(["status"], check=False)
        _run_live(["bash", "scripts/validate-project.sh"], check=False)
        _run_live(["bash", "scripts/validate-documentation.sh"], check=False)
        _run_live(["bash", "scripts/validate-rnd-policy.sh"], check=False)
        _run_live(
            [
                "python3",
                "scripts/traceability/traceability.py",
                "validate",
                "--stories-dir",
                args.stories_dir,
                "--tests-root",
                args.tests_root,
                "--skip-commits",
            ],
            check=False,
        )

        if args.full_verify:
            _run_live(["bash", "scripts/scaffold-and-verify.sh"], check=False)

    marker = "<!-- acf-autopilot:evidence -->"
    comment = _local_evidence_summary(repo_root, args.story_id, story_title)

    provider = state.get("provider", {}).get("kind")
    if provider == "github":
        token = args.github_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        repo = state.get("provider", {}).get("repo")
        api_url = state.get("provider", {}).get("apiUrl") or os.environ.get("GITHUB_API_URL") or "https://api.github.com"
        pr = state.get("provider", {}).get("pr") or {}
        pr_number = int(pr.get("number", 0) or 0)
        if not token or not repo or pr_number == 0:
            raise RuntimeError("Missing GitHub provider info in state (repo/pr/token). Re-run start with integration enabled.")
        _github_upsert_pr_comment(
            api_url=api_url,
            token=token,
            repo=repo,
            pr_number=pr_number,
            marker=marker,
            body=comment,
            dry_run=args.dry_run,
        )
        print(f"Updated GitHub PR comment for PR #{pr_number}")
        return 0

    if provider == "azuredevops":
        pat = args.azure_pat or os.environ.get("AZURE_DEVOPS_PAT")
        org_url = state.get("provider", {}).get("orgUrl") or os.environ.get("AZURE_DEVOPS_ORG_URL")
        project = state.get("provider", {}).get("project") or os.environ.get("AZURE_DEVOPS_PROJECT")
        repo = state.get("provider", {}).get("repo") or os.environ.get("AZURE_DEVOPS_REPO")
        pr_id = int(state.get("provider", {}).get("prId", 0) or 0)
        if not pat or not org_url or not project or not repo or pr_id == 0:
            raise RuntimeError(
                "Missing Azure DevOps provider info in state (orgUrl/project/repo/prId/pat). Re-run start with integration enabled."
            )
        _azure_post_pr_comment(
            org_url=org_url,
            project=project,
            repo=repo,
            pat=pat,
            pr_id=pr_id,
            body=f"{marker}\n{comment}",
            dry_run=args.dry_run,
        )
        print(f"Posted Azure DevOps PR thread comment for PR {pr_id}")
        return 0

    raise RuntimeError("No provider integration recorded in state. Re-run start with integration enabled.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autopilot", description="ACF Autopilot: Story -> PR -> Evidence")
    sub = p.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Create branch + PR + initial review pack")
    start.add_argument("story_id", help="Story ID (e.g., ACF-0123)")
    start.add_argument("--stories-dir", default="artifacts/stories", help="Stories directory (default: artifacts/stories)")
    start.add_argument("--provider", choices=["auto", "github", "azuredevops"], default="auto")
    start.add_argument("--base-branch", default=os.environ.get("AUTOPILOT_BASE_BRANCH", "main"))
    start.add_argument("--draft", action="store_true", help="Create draft PR")
    start.add_argument("--dry-run", action="store_true", help="Print actions without network calls")
    start.add_argument("--allow-untracked", action="store_true", help="Allow untracked files in worktree")
    start.add_argument("--commit", action="store_true", help="Commit generated artifacts")
    start.add_argument("--push", action="store_true", help="Push branch to origin (implies --commit)")
    start.add_argument("--require-integration", action="store_true", help="Fail if provider credentials are missing")

    # GitHub
    start.add_argument("--github-token", default=None)
    start.add_argument("--github-repo", default=None, help="owner/repo (defaults to origin remote when possible)")
    start.add_argument("--github-api-url", default=None, help="GitHub API base (default: https://api.github.com)")

    # Azure DevOps
    start.add_argument("--azure-pat", default=None)
    start.add_argument("--azure-org-url", default=None, help="e.g., https://dev.azure.com/yourorg")
    start.add_argument("--azure-project", default=None)
    start.add_argument("--azure-repo", default=None, help="Azure Repos repository name")
    start.add_argument("--azure-work-item-type", default=None, help='Default: "User Story"')

    evidence = sub.add_parser("evidence", help="Run checks and post/update PR evidence comment")
    evidence.add_argument("story_id", help="Story ID (e.g., ACF-0123)")
    evidence.add_argument("--stories-dir", default="artifacts/stories")
    evidence.add_argument("--tests-root", default=".", help="Root directory to scan for tests (default: .)")
    evidence.add_argument("--run-local", action="store_true", help="Run local validations before posting evidence")
    evidence.add_argument("--full-verify", action="store_true", help="Also run scripts/scaffold-and-verify.sh")
    evidence.add_argument("--dry-run", action="store_true")
    evidence.add_argument("--github-token", default=None)
    evidence.add_argument("--azure-pat", default=None)

    return p


def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "start":
        if args.push:
            args.commit = True
        return cmd_start(args)
    if args.cmd == "evidence":
        return cmd_evidence(args)
    raise RuntimeError("Unknown command")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
