#!/usr/bin/env python3
"""
Gitea Helper CLI for Hermes AI Software Engineering Team
Provides unified commands for git repo management, issues, PRs, reviews, and releases.
"""

import sys
import os
import argparse
import subprocess
import json
import requests

GITEA_API = os.environ.get("GITEA_API_URL", "http://gitea-service:3000/api/v1")
DEFAULT_ORG = os.environ.get("GITEA_ORG", "hermes-software-team")
WORKSPACE_BASE = os.environ.get("WORKSPACE_BASE", "/opt/data/workspace")

def get_auth(custom_user=None):
    user = custom_user or os.environ.get("HERMES_PROFILE") or os.environ.get("USER") or "dev-pm"
    password = os.environ.get("GITEA_PASSWORD", user)
    return (user, password)

def get_repo_url(user, password, org, project):
    return f"http://{user}:{password}@gitea-service:3000/{org}/{project}.git"

def clean_text(text):
    if not text:
        return ""
    # Convert literal '\n' and '\t' escape sequences from shell args into real newlines/tabs
    return text.replace("\\n", "\n").replace("\\t", "\t")

def cmd_init_project(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    desc = args.description or f"Hermes Project: {project}"
    
    # 1. Create remote repo via Gitea API if not exists
    r = requests.get(f"{GITEA_API}/repos/{org}/{project}", auth=(user, pwd))
    if r.status_code == 404:
        print(f"[*] Creating Gitea repository '{org}/{project}'...")
        r = requests.post(f"{GITEA_API}/orgs/{org}/repos", auth=(user, pwd), json={
            "name": project,
            "description": desc,
            "private": True,
            "auto_init": False
        })
        if r.status_code not in (200, 201):
            print(f"[!] Failed to create repo: {r.status_code} {r.text}", file=sys.stderr)
            sys.exit(1)
        print(f"[+] Remote repository created: {org}/{project}")
    else:
        print(f"[*] Remote repository '{org}/{project}' already exists.")

    # 2. Initialize local git repo in workspace
    project_dir = os.path.join(WORKSPACE_BASE, project)
    os.makedirs(project_dir, exist_ok=True)
    os.chdir(project_dir)

    if not os.path.exists(os.path.join(project_dir, ".git")):
        print(f"[*] Initializing local git repository at {project_dir}...")
        subprocess.run(["git", "init", "-b", "main"], check=True)
    
    # Config git user
    subprocess.run(["git", "config", "user.name", user], check=True)
    subprocess.run(["git", "config", "user.email", f"{user}@hermes.local"], check=True)

    # Set remote origin
    remote_url = get_repo_url(user, pwd, org, project)
    subprocess.run(["git", "remote", "remove", "origin"], stderr=subprocess.DEVNULL)
    subprocess.run(["git", "remote", "add", "origin", remote_url], check=True)

    # Initial commit if empty
    readme_path = os.path.join(project_dir, "README.md")
    if not os.path.exists(readme_path):
        with open(readme_path, "w") as f:
            f.write(f"# {project}\n\n{desc}\n\nDeveloped by Hermes Software Engineering Team.\n")
    
    subprocess.run(["git", "add", "."], check=True)
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
    if status.strip():
        subprocess.run(["git", "commit", "-m", f"chore: initialize project {project}"], check=True)
    
    # Push main branch
    subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
    print(f"[+] Project {project} successfully linked and pushed to Gitea!")

def cmd_create_issue(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    
    assignees = [a.strip() for a in args.assignees.split(",") if a.strip()] if args.assignees else []
    labels = [int(l.strip()) for l in args.labels.split(",") if l.strip().isdigit()] if args.labels else []

    payload = {
        "title": args.title,
        "body": clean_text(args.body),
        "assignees": assignees
    }
    if labels:
        payload["labels"] = labels

    r = requests.post(f"{GITEA_API}/repos/{org}/{project}/issues", auth=(user, pwd), json=payload)
    if r.status_code not in (200, 201):
        print(f"[!] Failed to create issue: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    
    data = r.json()
    issue_num = data.get("number")
    html_url = data.get("html_url")
    print(f"[+] Issue #{issue_num} created: {args.title} ({html_url})")
    print(json.dumps({"issue_number": issue_num, "url": html_url}))

def cmd_comment_issue(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    issue = args.issue
    
    r = requests.post(f"{GITEA_API}/repos/{org}/{project}/issues/{issue}/comments", auth=(user, pwd), json={
        "body": clean_text(args.body)
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to comment on issue: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Comment added to issue #{issue} by {user}")

def cmd_close_issue(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    issue = args.issue
    
    if args.comment:
        requests.post(f"{GITEA_API}/repos/{org}/{project}/issues/{issue}/comments", auth=(user, pwd), json={
            "body": clean_text(args.comment)
        })
    
    r = requests.patch(f"{GITEA_API}/repos/{org}/{project}/issues/{issue}", auth=(user, pwd), json={
        "state": "closed"
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to close issue: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Issue #{issue} closed.")

def cmd_create_pr(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    branch = args.branch
    base = args.base or "main"
    title = args.title
    body = clean_text(args.body or "")
    
    if args.issue:
        body += f"\n\nResolves #{args.issue}"

    # Push branch if locally in repo
    project_dir = os.path.join(WORKSPACE_BASE, project)
    if os.path.exists(project_dir):
        os.chdir(project_dir)
        subprocess.run(["git", "config", "user.name", user], check=True)
        subprocess.run(["git", "config", "user.email", f"{user}@hermes.local"], check=True)
        remote_url = get_repo_url(user, pwd, org, project)
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
        if status.strip():
            print(f"[*] Committing pending changes on branch '{branch}'...")
            subprocess.run(["git", "commit", "-am", title], check=True)
        
        print(f"[*] Pushing branch '{branch}' to Gitea...")
        subprocess.run(["git", "push", "-u", "origin", branch], check=True)

    r = requests.post(f"{GITEA_API}/repos/{org}/{project}/pulls", auth=(user, pwd), json={
        "head": branch,
        "base": base,
        "title": title,
        "body": body
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to create PR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    
    data = r.json()
    pr_num = data.get("number")
    html_url = data.get("html_url")
    print(f"[+] Pull Request #{pr_num} created: {title} ({html_url})")

    # Request reviewers (default to dev-reviewer)
    req_revs = getattr(args, "reviewers", None) or "dev-reviewer"
    reviewers = [rv.strip() for rv in req_revs.split(",") if rv.strip()]
    if reviewers:
        r_rev_req = requests.post(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr_num}/requested_reviewers", auth=(user, pwd), json={
            "reviewers": reviewers
        })
        if r_rev_req.status_code in (200, 201):
            print(f"[+] Requested reviewer(s) {reviewers} on PR #{pr_num}")
        else:
            print(f"[*] Notice: Could not assign reviewers {reviewers}: {r_rev_req.text}", file=sys.stderr)

    print(json.dumps({"pr_number": pr_num, "url": html_url, "reviewers": reviewers}))

def cmd_review_pr(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    pr = args.pr
    status = args.status.upper() # APPROVE, REQUEST_CHANGES, COMMENT
    
    event_map = {
        "APPROVE": "APPROVED",
        "APPROVED": "APPROVED",
        "REQUEST_CHANGES": "REQUEST_CHANGES",
        "COMMENT": "COMMENT"
    }
    event = event_map.get(status, "COMMENT")

    r = requests.post(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr}/reviews", auth=(user, pwd), json={
        "event": event,
        "body": clean_text(args.comment) or f"Review submitted by {user} ({event})"
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to submit PR review: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Review '{event}' submitted on PR #{pr} by {user}")

def cmd_merge_pr(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    pr = args.pr
    msg = args.message or f"Merge PR #{pr} by {user}"
    
    # Fetch PR details to get head branch name
    r_pr = requests.get(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr}", auth=(user, pwd))
    head_branch = None
    if r_pr.status_code == 200:
        head_branch = r_pr.json().get("head", {}).get("ref")

    r = requests.post(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr}/merge", auth=(user, pwd), json={
        "Do": "merge",
        "MergeMessageField": msg,
        "delete_branch_after_merge": True
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to merge PR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] PR #{pr} merged successfully into main.")

    # Clean up merged remote branch
    if head_branch and head_branch != "main":
        r_del = requests.delete(f"{GITEA_API}/repos/{org}/{project}/branches/{head_branch}", auth=(user, pwd))
        if r_del.status_code in (200, 204):
            print(f"[+] Cleaned up merged remote branch '{head_branch}'.")

def cmd_create_release(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    tag = args.tag
    title = args.title or tag
    notes = clean_text(args.notes or "")
    target = getattr(args, "target", None) or "main"

    r = requests.post(f"{GITEA_API}/repos/{org}/{project}/releases", auth=(user, pwd), json={
        "tag_name": tag,
        "target_commitish": target,
        "name": title,
        "body": notes,
        "draft": False,
        "prerelease": False
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to create release: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Release '{title}' ({tag}) published on Gitea.")


def cmd_list_prs(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    state = getattr(args, "state", "open") or "open"

    r = requests.get(f"{GITEA_API}/repos/{org}/{project}/pulls?state={state}", auth=(user, pwd))
    if r.status_code != 200:
        print(f"[!] Failed to fetch PRs: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    
    prs = r.json()
    summary = []
    for pr in prs:
        num = pr.get("number")
        title = pr.get("title")
        pr_state = pr.get("state")
        merged = pr.get("merged", False)
        head = pr.get("head", {}).get("ref")
        base = pr.get("base", {}).get("ref")
        author = pr.get("user", {}).get("username")
        mergeable = pr.get("mergeable", True)

        # Get latest review status
        rev_state = "NONE"
        r_rev = requests.get(f"{GITEA_API}/repos/{org}/{project}/pulls/{num}/reviews", auth=(user, pwd))
        if r_rev.status_code == 200 and r_rev.json():
            rev_state = r_rev.json()[-1].get("state", "NONE")

        item = {
            "number": num,
            "title": title,
            "state": pr_state,
            "merged": merged,
            "mergeable": mergeable,
            "head": head,
            "base": base,
            "author": author,
            "review": rev_state,
            "html_url": pr.get("html_url")
        }
        summary.append(item)
        print(f"PR #{num}: [{pr_state.upper()}] (Merged: {merged}, Mergeable: {mergeable}, Review: {rev_state}) {title}")
        print(f"     {author}: {head} -> {base}")

    print(json.dumps(summary))

def cmd_close_pr(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    pr = args.pr
    comment = args.comment

    if comment:
        requests.post(f"{GITEA_API}/repos/{org}/{project}/issues/{pr}/comments", auth=(user, pwd), json={
            "body": comment
        })

    r = requests.patch(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr}", auth=(user, pwd), json={
        "state": "closed"
    })
    if r.status_code not in (200, 201):
        print(f"[!] Failed to close PR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] PR #{pr} closed.")

def cmd_status(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project

    r_issues = requests.get(f"{GITEA_API}/repos/{org}/{project}/issues?state=open&type=issues", auth=(user, pwd))
    r_pulls = requests.get(f"{GITEA_API}/repos/{org}/{project}/pulls?state=open", auth=(user, pwd))
    
    issues = r_issues.json() if r_issues.status_code == 200 else []
    pulls = r_pulls.json() if r_pulls.status_code == 200 else []
    
    print(f"=== Project Status: {org}/{project} ===")
    print(f"\n[Open Issues: {len(issues)}]")
    for i in issues:
        assignee = ", ".join([a["username"] for a in i.get("assignees", [])]) or "Unassigned"
        print(f"  #{i['number']} {i['title']} (Assignee: {assignee})")
        
    print(f"\n[Open Pull Requests: {len(pulls)}]")
    for p in pulls:
        print(f"  #{p['number']} {p['title']} ({p['head']['ref']} -> {p['base']['ref']}) by {p['user']['username']}")

def cmd_get_pr(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    pr = args.pr

    r_pr = requests.get(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr}", auth=(user, pwd))
    r_rev = requests.get(f"{GITEA_API}/repos/{org}/{project}/pulls/{pr}/reviews", auth=(user, pwd))

    if r_pr.status_code != 200:
        print(f"[!] Failed to get PR #{pr}: {r_pr.status_code} {r_pr.text}", file=sys.stderr)
        sys.exit(1)

    pr_data = r_pr.json()
    reviews = r_rev.json() if r_rev.status_code == 200 else []

    output = {
        "number": pr_data.get("number"),
        "title": pr_data.get("title"),
        "state": pr_data.get("state"),
        "merged": pr_data.get("merged", False),
        "head": pr_data.get("head", {}).get("ref"),
        "base": pr_data.get("base", {}).get("ref"),
        "author": pr_data.get("user", {}).get("username"),
        "reviews": [{"user": rev.get("user", {}).get("username"), "state": rev.get("state"), "body": rev.get("body")} for rev in reviews]
    }
    print(json.dumps(output, indent=2))

def cmd_get_issue(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    issue = args.issue

    r_iss = requests.get(f"{GITEA_API}/repos/{org}/{project}/issues/{issue}", auth=(user, pwd))
    r_com = requests.get(f"{GITEA_API}/repos/{org}/{project}/issues/{issue}/comments", auth=(user, pwd))

    if r_iss.status_code != 200:
        print(f"[!] Failed to get Issue #{issue}: {r_iss.status_code} {r_iss.text}", file=sys.stderr)
        sys.exit(1)

    iss_data = r_iss.json()
    comments = r_com.json() if r_com.status_code == 200 else []

    output = {
        "number": iss_data.get("number"),
        "title": iss_data.get("title"),
        "state": iss_data.get("state"),
        "body": iss_data.get("body"),
        "assignees": [a.get("username") for a in iss_data.get("assignees", [])],
        "comments": [{"user": c.get("user", {}).get("username"), "body": c.get("body"), "created_at": c.get("created_at")} for c in comments]
    }
    print(json.dumps(output, indent=2))

def cmd_commit_wbs(args):
    user, pwd = get_auth(args.user)
    org = args.org or DEFAULT_ORG
    project = args.project
    msg = args.message or "docs(wbs): update project WBS"

    project_dir = os.path.join(WORKSPACE_BASE, project)
    wbs_path = os.path.join(project_dir, "wbs.md")

    if not os.path.exists(wbs_path):
        print(f"[!] WBS file not found at {wbs_path}", file=sys.stderr)
        sys.exit(1)

    os.chdir(project_dir)
    subprocess.run(["git", "config", "user.name", user], check=True)
    subprocess.run(["git", "config", "user.email", f"{user}@hermes.local"], check=True)
    remote_url = get_repo_url(user, pwd, org, project)
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

    subprocess.run(["git", "add", "wbs.md"], check=True)
    status = subprocess.run(["git", "status", "--porcelain", "wbs.md"], capture_output=True, text=True).stdout
    if status.strip():
        subprocess.run(["git", "commit", "-m", msg], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"[+] WBS successfully committed and pushed to {org}/{project} on main!")
    else:
        print("[*] No changes in wbs.md to commit.")

def main():
    parser = argparse.ArgumentParser(description="Hermes Gitea Workflow Helper CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-project
    p_init = subparsers.add_parser("init-project")
    p_init.add_argument("--project", required=True)
    p_init.add_argument("--org", default=DEFAULT_ORG)
    p_init.add_argument("--description", default="")
    p_init.add_argument("--user", default=None)
    p_init.set_defaults(func=cmd_init_project)

    # create-issue
    p_issue = subparsers.add_parser("create-issue")
    p_issue.add_argument("--project", required=True)
    p_issue.add_argument("--org", default=DEFAULT_ORG)
    p_issue.add_argument("--title", required=True)
    p_issue.add_argument("--body", default="")
    p_issue.add_argument("--assignees", default="")
    p_issue.add_argument("--labels", default="")
    p_issue.add_argument("--user", default=None)
    p_issue.set_defaults(func=cmd_create_issue)

    # comment-issue
    p_com = subparsers.add_parser("comment-issue")
    p_com.add_argument("--project", required=True)
    p_com.add_argument("--org", default=DEFAULT_ORG)
    p_com.add_argument("--issue", type=int, required=True)
    p_com.add_argument("--body", required=True)
    p_com.add_argument("--user", default=None)
    p_com.set_defaults(func=cmd_comment_issue)

    # close-issue
    p_cls = subparsers.add_parser("close-issue")
    p_cls.add_argument("--project", required=True)
    p_cls.add_argument("--org", default=DEFAULT_ORG)
    p_cls.add_argument("--issue", type=int, required=True)
    p_cls.add_argument("--comment", default="")
    p_cls.add_argument("--user", default=None)
    p_cls.set_defaults(func=cmd_close_issue)

    # get-issue
    p_gi = subparsers.add_parser("get-issue")
    p_gi.add_argument("--project", required=True)
    p_gi.add_argument("--org", default=DEFAULT_ORG)
    p_gi.add_argument("--issue", type=int, required=True)
    p_gi.add_argument("--user", default=None)
    p_gi.set_defaults(func=cmd_get_issue)

    # create-pr
    p_pr = subparsers.add_parser("create-pr")
    p_pr.add_argument("--project", required=True)
    p_pr.add_argument("--org", default=DEFAULT_ORG)
    p_pr.add_argument("--branch", required=True)
    p_pr.add_argument("--base", default="main")
    p_pr.add_argument("--title", required=True)
    p_pr.add_argument("--body", default="")
    p_pr.add_argument("--issue", type=int, default=None)
    p_pr.add_argument("--reviewers", default="dev-reviewer", help="Comma-separated list of reviewers to request")
    p_pr.add_argument("--user", default=None)
    p_pr.set_defaults(func=cmd_create_pr)

    # review-pr
    p_rev = subparsers.add_parser("review-pr")
    p_rev.add_argument("--project", required=True)
    p_rev.add_argument("--org", default=DEFAULT_ORG)
    p_rev.add_argument("--pr", type=int, required=True)
    p_rev.add_argument("--status", choices=["APPROVE", "REQUEST_CHANGES", "COMMENT"], required=True)
    p_rev.add_argument("--comment", required=True)
    p_rev.add_argument("--user", default=None)
    p_rev.set_defaults(func=cmd_review_pr)

    # merge-pr
    p_mrg = subparsers.add_parser("merge-pr")
    p_mrg.add_argument("--project", required=True)
    p_mrg.add_argument("--org", default=DEFAULT_ORG)
    p_mrg.add_argument("--pr", type=int, required=True)
    p_mrg.add_argument("--message", default="")
    p_mrg.add_argument("--user", default=None)
    p_mrg.set_defaults(func=cmd_merge_pr)

    # get-pr
    p_gp = subparsers.add_parser("get-pr")
    p_gp.add_argument("--project", required=True)
    p_gp.add_argument("--org", default=DEFAULT_ORG)
    p_gp.add_argument("--pr", type=int, required=True)
    p_gp.add_argument("--user", default=None)
    p_gp.set_defaults(func=cmd_get_pr)

    # commit-wbs
    p_wbs = subparsers.add_parser("commit-wbs")
    p_wbs.add_argument("--project", required=True)
    p_wbs.add_argument("--org", default=DEFAULT_ORG)
    p_wbs.add_argument("--message", default="docs(wbs): update project status")
    p_wbs.add_argument("--user", default=None)
    p_wbs.set_defaults(func=cmd_commit_wbs)

    # create-release
    p_rel = subparsers.add_parser("create-release")
    p_rel.add_argument("--project", required=True)
    p_rel.add_argument("--org", default=DEFAULT_ORG)
    p_rel.add_argument("--tag", required=True)
    p_rel.add_argument("--title", default="")
    p_rel.add_argument("--notes", default="")
    p_rel.add_argument("--target", default="main")
    p_rel.add_argument("--user", default=None)
    p_rel.set_defaults(func=cmd_create_release)

    # list-prs
    p_list_prs = subparsers.add_parser("list-prs", help="List pull requests")
    p_list_prs.add_argument("--project", required=True, help="Project name")
    p_list_prs.add_argument("--org", help="Organization name")
    p_list_prs.add_argument("--state", choices=["open", "closed", "all"], default="open", help="PR state filter")
    p_list_prs.add_argument("--user", help="User to authenticate as")
    p_list_prs.set_defaults(func=cmd_list_prs)

    # close-pr
    p_close_pr = subparsers.add_parser("close-pr", help="Close a pull request without merging")
    p_close_pr.add_argument("--project", required=True, help="Project name")
    p_close_pr.add_argument("--org", help="Organization name")
    p_close_pr.add_argument("--pr", type=int, required=True, help="PR number")
    p_close_pr.add_argument("--comment", help="Comment explaining why PR was closed")
    p_close_pr.add_argument("--user", help="User to authenticate as")
    p_close_pr.set_defaults(func=cmd_close_pr)

    # status
    p_st = subparsers.add_parser("status")
    p_st.add_argument("--project", required=True)
    p_st.add_argument("--org", default=DEFAULT_ORG)
    p_st.add_argument("--user", default=None)
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
