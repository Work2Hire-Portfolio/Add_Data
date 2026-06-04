from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


GITHUB_API_BASE = "https://api.github.com"
ALLOWED_PERMISSIONS = {"pull", "triage", "push", "maintain", "admin"}
HISTORY_DB_PATH = Path(os.getenv("DEPLOYMENT_HISTORY_DB", "deployment_history.sqlite3"))
USERNAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")
load_dotenv()


class DeploymentError(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message


@dataclass(frozen=True)
class GitHubConfig:
    token: str
    username: str
    repo_visibility: str = "public"
    pages_branch: str = "main"
    repo_prefix: str = ""

    @property
    def private_repo(self) -> bool:
        return self.repo_visibility.lower() == "private"


@dataclass(frozen=True)
class DirectoryConfig:
    owner: str
    repo: str
    branch: str = "main"
    data_path: str = "data/portfolios.json"
    site_url: str = ""


@dataclass(frozen=True)
class PortfolioDirectoryEntry:
    username: str
    name: str
    role: str
    template_type: str
    image: str = ""


def _load_streamlit_secrets() -> dict[str, Any]:
    try:
        import streamlit as st
    except ImportError:
        return {}

    try:
        secrets = getattr(st, "secrets", None)
        if not secrets:
            return {}
        return dict(secrets)
    except Exception:
        return {}


def get_config_value(name: str, default: str = "") -> str:
    env_value = os.getenv(name)
    if env_value is not None and str(env_value).strip() != "":
        return str(env_value).strip().strip('"').strip("'")

    secrets = _load_streamlit_secrets()
    secret_value = secrets.get(name)
    if secret_value is None:
        return default

    clean = str(secret_value).strip().strip('"').strip("'")
    return clean or default


def get_github_config() -> GitHubConfig:
    token = get_config_value("GITHUB_TOKEN")
    username = get_config_value("GITHUB_USERNAME")
    if not token:
        raise DeploymentError("config", "Missing required environment variable GITHUB_TOKEN.")
    if not username:
        raise DeploymentError("config", "Missing required environment variable GITHUB_USERNAME.")

    visibility = get_config_value("GITHUB_REPO_VISIBILITY", "public").lower()
    if visibility not in {"public", "private"}:
        raise DeploymentError("config", "GITHUB_REPO_VISIBILITY must be either public or private.")

    return GitHubConfig(
        token=token,
        username=username,
        repo_visibility=visibility,
        pages_branch=get_config_value("GITHUB_PAGES_BRANCH", "main") or "main",
        repo_prefix=get_config_value("GITHUB_REPO_PREFIX"),
    )


def get_directory_config() -> DirectoryConfig:
    owner = get_config_value("DIRECTORY_REPO_OWNER")
    repo = get_config_value("DIRECTORY_REPO_NAME")
    site_url = get_config_value("DIRECTORY_SITE_URL")

    if not owner:
        raise DeploymentError("config", "Missing required environment variable DIRECTORY_REPO_OWNER.")
    if not repo:
        raise DeploymentError("config", "Missing required environment variable DIRECTORY_REPO_NAME.")
    if not site_url:
        raise DeploymentError("config", "Missing required environment variable DIRECTORY_SITE_URL.")

    branch = get_config_value("DIRECTORY_REPO_BRANCH", "main") or "main"
    data_path = get_config_value("DIRECTORY_DATA_PATH", "data/portfolios.json").strip("/")
    if not data_path:
        raise DeploymentError("config", "DIRECTORY_DATA_PATH cannot be empty.")
    if not re.fullmatch(r"[A-Za-z0-9._/\-]+", data_path):
        raise DeploymentError("config", "DIRECTORY_DATA_PATH contains invalid characters.")
    if not re.match(r"^https?://", site_url, flags=re.IGNORECASE):
        raise DeploymentError("config", "DIRECTORY_SITE_URL must start with http:// or https://.")

    return DirectoryConfig(
        owner=owner,
        repo=repo,
        branch=branch,
        data_path=data_path,
        site_url=site_url.rstrip("/"),
    )


def get_optional_directory_config() -> DirectoryConfig | None:
    owner = get_config_value("DIRECTORY_REPO_OWNER")
    repo = get_config_value("DIRECTORY_REPO_NAME")
    branch = get_config_value("DIRECTORY_REPO_BRANCH", "main") or "main"
    data_path = get_config_value("DIRECTORY_DATA_PATH", "data/portfolios.json")
    site_url = get_config_value("DIRECTORY_SITE_URL")

    configured_values = [owner, repo, site_url]
    if not any(value.strip() for value in configured_values):
        return None

    if not owner:
        raise DeploymentError("config", "DIRECTORY_REPO_OWNER is required when directory sync is enabled.")
    if not repo:
        raise DeploymentError("config", "DIRECTORY_REPO_NAME is required when directory sync is enabled.")
    if not site_url:
        raise DeploymentError("config", "DIRECTORY_SITE_URL is required when directory sync is enabled.")

    clean_data_path = data_path.strip("/")
    if not clean_data_path:
        raise DeploymentError("config", "DIRECTORY_DATA_PATH cannot be empty.")
    if not re.fullmatch(r"[A-Za-z0-9._/\-]+", clean_data_path):
        raise DeploymentError("config", "DIRECTORY_DATA_PATH contains invalid characters.")
    if not re.match(r"^https?://", site_url, flags=re.IGNORECASE):
        raise DeploymentError("config", "DIRECTORY_SITE_URL must start with http:// or https://.")

    return DirectoryConfig(
        owner=owner,
        repo=repo,
        branch=branch,
        data_path=clean_data_path,
        site_url=site_url.rstrip("/"),
    )


def sanitize_repo_name(repo_name: str, prefix: str | None = None) -> str:
    if not repo_name or not repo_name.strip():
        raise DeploymentError("validate", "Repository name is required.")

    clean = repo_name.strip().lower()
    clean = re.sub(r"\s+", "-", clean)
    clean = re.sub(r"[^a-z0-9._-]", "", clean)
    clean = re.sub(r"-{2,}", "-", clean)
    clean = clean.strip("-")

    if not clean:
        raise DeploymentError("validate", "Repository name contains no valid GitHub repository characters.")

    configured_prefix = (prefix or "").strip().lower()
    if configured_prefix:
        configured_prefix = re.sub(r"\s+", "-", configured_prefix)
        configured_prefix = re.sub(r"[^a-z0-9._-]", "", configured_prefix)
        configured_prefix = re.sub(r"-{2,}", "-", configured_prefix).strip("-")
        if configured_prefix and not clean.startswith(configured_prefix):
            clean = f"{configured_prefix}-{clean}" if not configured_prefix.endswith("-") else f"{configured_prefix}{clean}"

    if len(clean) > 100:
        clean = clean[:100].strip("-")

    if not clean:
        raise DeploymentError("validate", "Repository name is invalid after sanitization.")
    return clean


def validate_html_upload(html_content: str, filename: str | None = None) -> None:
    if not html_content or not html_content.strip():
        raise DeploymentError("validate", "HTML file is required.")
    if filename and not filename.lower().endswith(".html"):
        raise DeploymentError("validate", "Only .html files are accepted.")

    sample = html_content[:1000].lower()
    if "<html" not in sample and "<!doctype html" not in sample:
        raise DeploymentError("validate", "Uploaded file does not look like a valid HTML document.")


def validate_username(username: str) -> str:
    clean = username.strip().lower()
    if not clean:
        raise DeploymentError("validate", "Username is required for the public portfolio route.")
    if not USERNAME_PATTERN.fullmatch(clean):
        raise DeploymentError(
            "validate",
            "Username must use only lowercase letters, numbers, hyphens, or underscores.",
        )
    return clean


def validate_public_url(url: str, field_name: str) -> str:
    clean = url.strip()
    if not re.match(r"^https?://", clean, flags=re.IGNORECASE):
        raise DeploymentError("config", f"{field_name} must start with http:// or https://.")
    return clean.rstrip("/")


def pages_url_for(username: str, repo_name: str) -> str:
    return f"https://{username}.github.io/{repo_name}/"


def directory_route_url_for(site_url: str, username: str) -> str:
    return f"{validate_public_url(site_url, 'DIRECTORY_SITE_URL')}/{validate_username(username)}"


def init_history_db(db_path: Path = HISTORY_DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT,
                repo_url TEXT,
                pages_url TEXT,
                collaborator TEXT,
                collaborator_permission TEXT,
                collaborator_invited INTEGER,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
        conn.commit()


def save_deployment_history(result: dict[str, Any], db_path: Path = HISTORY_DB_PATH) -> None:
    init_history_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO deployments (
                repo_name, repo_url, pages_url, collaborator, collaborator_permission,
                collaborator_invited, status, created_at, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.get("repo_name"),
                result.get("repo_url"),
                result.get("pages_url"),
                result.get("collaborator"),
                result.get("collaborator_permission"),
                1 if result.get("collaborator_invited") else 0,
                result.get("status", "failed"),
                datetime.now(timezone.utc).isoformat(),
                result.get("error"),
            ),
        )
        conn.commit()


class GitHubClient:
    def __init__(self, config: GitHubConfig, session: requests.Session | None = None, timeout: int = 20):
        self.config = config
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "portfolio-github-deployer",
            }
        )

    def _request(self, method: str, url: str, stage: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.Timeout as exc:
            raise DeploymentError(stage, "GitHub API request timed out.") from exc
        except requests.RequestException as exc:
            raise DeploymentError(stage, f"GitHub API request failed: {exc}") from exc

        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            raise DeploymentError(stage, "GitHub API rate limit exceeded. Try again later.")
        return response

    @staticmethod
    def _error_message(response: requests.Response, fallback: str) -> str:
        try:
            data = response.json()
        except ValueError:
            return fallback
        message = data.get("message") if isinstance(data, dict) else None
        text = str(message or fallback)
        if "resource not accessible by personal access token" in text.lower():
            return (
                "Resource not accessible by personal access token. Update the token with "
                "Pages: read/write and Administration: read/write repository permissions."
            )
        return text

    def create_repo(self, requested_name: str) -> str:
        payload = {
            "name": requested_name,
            "private": self.config.private_repo,
            "auto_init": True,
            "description": "Auto deployed portfolio website",
            "has_issues": False,
            "has_projects": False,
            "has_wiki": False,
        }
        response = self._request("POST", f"{GITHUB_API_BASE}/user/repos", "create_repo", json=payload)
        if response.status_code == 201:
            return requested_name

        if response.status_code == 422:
            timestamped_name = f"{requested_name[:88].strip('-')}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            payload["name"] = timestamped_name
            retry = self._request("POST", f"{GITHUB_API_BASE}/user/repos", "create_repo", json=payload)
            if retry.status_code == 201:
                return timestamped_name
            raise DeploymentError("create_repo", self._error_message(retry, "GitHub repository already exists and unique retry failed."))

        raise DeploymentError("create_repo", self._error_message(response, "Failed to create GitHub repository."))

    def get_authenticated_user(self) -> dict[str, Any]:
        response = self._request("GET", f"{GITHUB_API_BASE}/user", "auth_check")
        if response.status_code != 200:
            raise DeploymentError("auth_check", self._error_message(response, "GitHub authentication failed."))
        data = response.json()
        return {
            "login": data.get("login"),
            "id": data.get("id"),
            "html_url": data.get("html_url"),
        }

    def repo_create_preflight(self) -> dict[str, Any]:
        response = self._request("GET", f"{GITHUB_API_BASE}/user/repos?per_page=1", "create_repo_preflight")
        accepted_scopes = response.headers.get("X-Accepted-OAuth-Scopes", "")
        token_scopes = response.headers.get("X-OAuth-Scopes", "")
        if response.status_code not in {200, 304}:
            raise DeploymentError("create_repo_preflight", self._error_message(response, "GitHub repository access check failed."))
        return {
            "status_code": response.status_code,
            "accepted_oauth_scopes": accepted_scopes,
            "token_oauth_scopes": token_scopes,
        }

    def _get_content_sha(self, repo_name: str, path: str) -> str | None:
        return self._get_content_sha_for_repo(self.config.username, repo_name, path, "upload_file")

    def _get_content_sha_for_repo(self, owner: str, repo_name: str, path: str, stage: str) -> str | None:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/contents/{path}"
        response = self._request("GET", url, stage)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DeploymentError(stage, self._error_message(response, f"Failed to read existing {path}."))
        data = response.json()
        return data.get("sha")

    def upload_content(self, repo_name: str, path: str, content: str, commit_message: str, stage: str = "upload_file") -> None:
        self.upload_content_to_repo(
            owner=self.config.username,
            repo_name=repo_name,
            path=path,
            content=content,
            commit_message=commit_message,
            branch=self.config.pages_branch,
            stage=stage,
        )

    def upload_content_to_repo(
        self,
        owner: str,
        repo_name: str,
        path: str,
        content: str,
        commit_message: str,
        branch: str,
        stage: str,
    ) -> None:
        sha = self._get_content_sha_for_repo(owner, repo_name, path, stage)
        payload: dict[str, Any] = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/contents/{path}"
        response = self._request("PUT", url, stage, json=payload)
        if response.status_code not in {200, 201}:
            raise DeploymentError(stage, self._error_message(response, f"Failed to upload {path}."))

    def read_text_content_from_repo(self, owner: str, repo_name: str, path: str, branch: str, stage: str) -> str | None:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/contents/{path}"
        response = self._request("GET", url, stage, params={"ref": branch})
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DeploymentError(stage, self._error_message(response, f"Failed to read {path}."))

        data = response.json()
        encoded = data.get("content")
        if not encoded:
            raise DeploymentError(stage, f"{path} did not return file content.")
        try:
            return base64.b64decode(encoded).decode("utf-8")
        except Exception as exc:
            raise DeploymentError(stage, f"Could not decode {path} from GitHub.") from exc

    def enable_pages(self, repo_name: str) -> None:
        payload = {"source": {"branch": self.config.pages_branch, "path": "/"}}
        url = f"{GITHUB_API_BASE}/repos/{self.config.username}/{repo_name}/pages"
        response = self._request("POST", url, "enable_pages", json=payload)
        if response.status_code in {201, 204}:
            return
        if response.status_code == 409:
            update = self._request("PUT", url, "enable_pages", json=payload)
            if update.status_code == 204:
                return
            raise DeploymentError("enable_pages", self._error_message(update, "Failed to update GitHub Pages settings."))
        if response.status_code == 422 and "already" in self._error_message(response, "").lower():
            return
        raise DeploymentError("enable_pages", self._error_message(response, "Failed to enable GitHub Pages."))

    def invite_collaborator(self, repo_name: str, collaborator: str, permission: str) -> bool:
        if permission not in ALLOWED_PERMISSIONS:
            raise DeploymentError("invite_collaborator", f"Invalid collaborator permission '{permission}'.")
        if "@" in collaborator:
            raise DeploymentError("invite_collaborator", "GitHub collaborator invites require a GitHub username. Email addresses are not supported by this API.")

        payload = {"permission": permission}
        url = f"{GITHUB_API_BASE}/repos/{self.config.username}/{repo_name}/collaborators/{collaborator}"
        response = self._request("PUT", url, "invite_collaborator", json=payload)
        if response.status_code in {201, 204}:
            return True
        if response.status_code == 404:
            raise DeploymentError("invite_collaborator", "Collaborator username was not found or cannot be invited.")
        raise DeploymentError("invite_collaborator", self._error_message(response, "Collaborator invite failed."))


def deploy_html_portfolio(
    html_content: str,
    repo_name: str,
    username: str,
    display_name: str | None = None,
    role: str | None = None,
    template_type: str | None = None,
    image: str | None = None,
    collaborator: str | None = None,
    collaborator_permission: str = "push",
) -> dict[str, Any]:
    try:
        validate_html_upload(html_content)
        config = get_github_config()
        directory_config = get_optional_directory_config()
        sanitized_repo = sanitize_repo_name(repo_name, config.repo_prefix)
        sanitized_username = validate_username(username)
        client = GitHubClient(config)

        final_repo_name = client.create_repo(sanitized_repo)
        live_url = pages_url_for(config.username, final_repo_name)
        repo_url = f"https://github.com/{config.username}/{final_repo_name}"

        client.upload_content(final_repo_name, "index.html", html_content, "Deploy portfolio index.html")
        readme = f"# Portfolio Website\n\nThis portfolio was automatically deployed.\n\nLive site:\n{live_url}\n"
        client.upload_content(final_repo_name, "README.md", readme, "Add portfolio README", stage="upload_file")
        client.enable_pages(final_repo_name)
        public_route_url = None
        if directory_config is not None:
            directory_entry = PortfolioDirectoryEntry(
                username=sanitized_username,
                name=(display_name or sanitized_username).strip(),
                role=(role or "Portfolio").strip(),
                template_type=(template_type or "custom").strip(),
                image=(image or "").strip(),
            )
            public_route_url = sync_portfolio_to_directory_repo(
                client=client,
                directory_config=directory_config,
                entry=directory_entry,
                portfolio_url=live_url,
            )

        collaborator_invited = False
        collaborator_value = collaborator.strip() if collaborator else None
        if collaborator_value:
            collaborator_invited = client.invite_collaborator(final_repo_name, collaborator_value, collaborator_permission)

        result = {
            "success": True,
            "repo_name": final_repo_name,
            "repo_url": repo_url,
            "pages_url": live_url,
            "username": sanitized_username,
            "public_route_url": public_route_url,
            "directory_repo_url": (
                f"https://github.com/{directory_config.owner}/{directory_config.repo}"
                if directory_config is not None
                else None
            ),
            "directory_sync_enabled": directory_config is not None,
            "collaborator_invited": collaborator_invited,
            "collaborator": collaborator_value,
            "collaborator_permission": collaborator_permission,
            "status": "deployed",
        }
        save_deployment_history(result)
        return result
    except DeploymentError as exc:
        result = {"success": False, "stage": exc.stage, "error": exc.message, "status": "failed"}
        save_deployment_history(result)
        return result
    except Exception as exc:
        result = {"success": False, "stage": "unknown", "error": f"Unexpected deployment error: {exc}", "status": "failed"}
        save_deployment_history(result)
        return result


def enable_pages_for_existing_repo(repo_name: str) -> dict[str, Any]:
    try:
        config = get_github_config()
        sanitized_repo = sanitize_repo_name(repo_name, config.repo_prefix)
        client = GitHubClient(config)
        client.enable_pages(sanitized_repo)

        result = {
            "success": True,
            "repo_name": sanitized_repo,
            "repo_url": f"https://github.com/{config.username}/{sanitized_repo}",
            "pages_url": pages_url_for(config.username, sanitized_repo),
            "collaborator_invited": False,
            "collaborator": None,
            "collaborator_permission": None,
            "status": "pages_enabled",
        }
        save_deployment_history(result)
        return result
    except DeploymentError as exc:
        result = {"success": False, "stage": exc.stage, "error": exc.message, "status": "failed"}
        save_deployment_history(result)
        return result
    except Exception as exc:
        result = {"success": False, "stage": "unknown", "error": f"Unexpected Pages error: {exc}", "status": "failed"}
        save_deployment_history(result)
        return result


def check_github_auth() -> dict[str, Any]:
    try:
        config = get_github_config()
        client = GitHubClient(config)
        user = client.get_authenticated_user()
        username_matches = (user.get("login") or "").lower() == config.username.lower()
        return {
            "success": True,
            "authenticated_as": user.get("login"),
            "configured_username": config.username,
            "username_matches": username_matches,
            "message": "GitHub token is accepted by the API.",
        }
    except DeploymentError as exc:
        return {"success": False, "stage": exc.stage, "error": exc.message}
    except Exception as exc:
        return {"success": False, "stage": "unknown", "error": f"Unexpected auth check error: {exc}"}


def check_repo_create_access() -> dict[str, Any]:
    try:
        config = get_github_config()
        client = GitHubClient(config)
        user = client.get_authenticated_user()
        preflight = client.repo_create_preflight()
        return {
            "success": True,
            "authenticated_as": user.get("login"),
            "configured_username": config.username,
            "repo_visibility": config.repo_visibility,
            "message": "GitHub token can read the repository API. If creation still fails, recreate the token with Administration: read/write and Repository access: All repositories.",
            **preflight,
        }
    except DeploymentError as exc:
        return {"success": False, "stage": exc.stage, "error": exc.message}
    except Exception as exc:
        return {"success": False, "stage": "unknown", "error": f"Unexpected repo access check error: {exc}"}


def history_as_json(db_path: Path = HISTORY_DB_PATH) -> str:
    init_history_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM deployments ORDER BY id DESC LIMIT 100").fetchall()
    return json.dumps([dict(row) for row in rows], indent=2)


def upsert_portfolio_record(
    portfolios: list[dict[str, Any]],
    entry: PortfolioDirectoryEntry,
    portfolio_url: str,
) -> list[dict[str, Any]]:
    next_portfolios = list(portfolios)
    created_at = datetime.now(timezone.utc).date().isoformat()
    updated = False

    for index, current in enumerate(next_portfolios):
        current_username = str((current or {}).get("username", "")).strip().lower()
        if current_username != entry.username:
            continue

        next_portfolios[index] = {
            **current,
            "username": entry.username,
            "name": entry.name,
            "role": entry.role,
            "template_type": entry.template_type,
            "portfolio_url": portfolio_url,
            "image": entry.image,
            "is_active": True,
            "created_at": current.get("created_at") or created_at,
        }
        updated = True
        break

    if not updated:
        next_portfolios.append(
            {
                "username": entry.username,
                "name": entry.name,
                "role": entry.role,
                "template_type": entry.template_type,
                "portfolio_url": portfolio_url,
                "image": entry.image,
                "is_active": True,
                "created_at": created_at,
            }
        )

    next_portfolios.sort(key=lambda item: str(item.get("username", "")))
    return next_portfolios


def sync_portfolio_to_directory_repo(
    client: GitHubClient,
    directory_config: DirectoryConfig,
    entry: PortfolioDirectoryEntry,
    portfolio_url: str,
) -> str:
    stage = "sync_directory"
    raw = client.read_text_content_from_repo(
        owner=directory_config.owner,
        repo_name=directory_config.repo,
        path=directory_config.data_path,
        branch=directory_config.branch,
        stage=stage,
    )

    if raw is None:
        portfolios: list[dict[str, Any]] = []
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeploymentError(stage, f"{directory_config.data_path} does not contain valid JSON.") from exc
        if not isinstance(parsed, list):
            raise DeploymentError(stage, f"{directory_config.data_path} must contain a JSON array.")
        portfolios = parsed

    next_portfolios = upsert_portfolio_record(portfolios, entry, portfolio_url)
    client.upload_content_to_repo(
        owner=directory_config.owner,
        repo_name=directory_config.repo,
        path=directory_config.data_path,
        content=json.dumps(next_portfolios, indent=2) + "\n",
        commit_message=f"Publish portfolio route for {entry.username}",
        branch=directory_config.branch,
        stage=stage,
    )
    return directory_route_url_for(directory_config.site_url, entry.username)
