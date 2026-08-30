import base64
from typing import Optional

import requests


class GitHubClient:
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}

    def get_repo_tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{branch}"
        resp = requests.get(url, headers=self._headers(), params={"recursive": "1"})
        resp.raise_for_status()
        data = resp.json()
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob" and item["path"].endswith(".py")
        ]

    def get_default_branch(self, owner: str, repo: str) -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()["default_branch"]

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=self._headers(), params={"ref": ref})
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    def get_codeowners(self, owner: str, repo: str) -> Optional[str]:
        for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            try:
                return self.get_file_content(owner, repo, path)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    continue
                raise
        return None

    def get_commit_history(self, owner: str, repo: str, path: str) -> list[dict]:
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        resp = requests.get(url, headers=self._headers(), params={"path": path})
        resp.raise_for_status()
        commits = resp.json()
        result = []
        for c in commits:
            linked_author = c.get("author")
            login = linked_author["login"] if linked_author is not None else c["commit"]["author"]["name"]
            result.append({"author": login, "date": c["commit"]["author"]["date"]})
        return result

    def get_open_pull_requests(self, owner: str, repo: str) -> list[dict]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        resp = requests.get(url, headers=self._headers(), params={"state": "open"})
        resp.raise_for_status()
        prs = resp.json()
        result = []
        for pr in prs:
            files_url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr['number']}/files"
            files_resp = requests.get(files_url, headers=self._headers())
            files_resp.raise_for_status()
            files = [f["filename"] for f in files_resp.json()]
            result.append({"number": pr["number"], "files_changed": files, "diff_summary": pr.get("title", "")})
        return result

    def post_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> dict:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        resp = requests.post(url, headers=self._headers(), json={"body": body})
        resp.raise_for_status()
        return resp.json()

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        assignee: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> dict:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        payload = {"title": title, "body": body}
        if assignee:
            payload["assignees"] = [assignee]
        if labels:
            payload["labels"] = labels
        resp = requests.post(url, headers=self._headers(), json=payload)
        resp.raise_for_status()
        return resp.json()
