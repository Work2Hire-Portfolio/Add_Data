import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from github_deployer import (
    DirectoryConfig,
    DeploymentError,
    GitHubClient,
    GitHubConfig,
    PortfolioAssetUpload,
    PortfolioDirectoryEntry,
    deploy_html_portfolio,
    get_optional_directory_config,
    get_config_value,
    directory_route_url_for,
    pages_url_for,
    sanitize_asset_filename,
    sanitize_repo_name,
    sync_portfolio_to_directory_repo,
    upsert_portfolio_record,
    validate_asset_upload,
    validate_html_upload,
    validate_username,
)


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url, "timeout": timeout, **kwargs})
        return self.responses.pop(0)


def config():
    return GitHubConfig(token="token", username="octocat", repo_visibility="public", pages_branch="main")


def test_sanitize_repo_name_with_prefix():
    assert sanitize_repo_name("Ansh Prasad Portfolio", "portfolio-") == "portfolio-ansh-prasad-portfolio"


def test_sanitize_repo_name_removes_invalid_characters_and_duplicate_hyphens():
    assert sanitize_repo_name(" My !! Test --- Repo__ ") == "my-test-repo__"


def test_sanitize_repo_name_rejects_empty_result():
    with pytest.raises(DeploymentError):
        sanitize_repo_name("!!!")


def test_validate_html_upload_accepts_html_file():
    validate_html_upload("<!DOCTYPE html><html><body>Hello</body></html>", "site.html")


def test_validate_html_upload_rejects_non_html_extension():
    with pytest.raises(DeploymentError) as exc:
        validate_html_upload("<html></html>", "site.txt")
    assert exc.value.stage == "validate"


def test_validate_html_upload_rejects_non_html_content():
    with pytest.raises(DeploymentError):
        validate_html_upload("plain text", "site.html")


def test_validate_username_normalizes_to_lowercase():
    assert validate_username("Ansh_Prasad") == "ansh_prasad"


def test_validate_username_rejects_invalid_characters():
    with pytest.raises(DeploymentError):
        validate_username("ansh prasad")


def test_sanitize_asset_filename_normalizes_safe_name():
    assert sanitize_asset_filename(" My Resume Final!.PDF ", {".pdf"}, "Resume") == "my-resume-final.pdf"


def test_validate_asset_upload_rejects_unsupported_extension():
    with pytest.raises(DeploymentError) as exc:
        validate_asset_upload(PortfolioAssetUpload("profile.exe", b"content"), {".png"}, "Profile picture")
    assert exc.value.stage == "validate"


def test_get_config_value_prefers_environment_over_streamlit_secrets(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setattr("github_deployer._load_streamlit_secrets", lambda: {"GITHUB_TOKEN": "secret-token"})

    assert get_config_value("GITHUB_TOKEN") == "env-token"


def test_get_config_value_uses_streamlit_secrets_when_environment_missing(monkeypatch):
    monkeypatch.delenv("DIRECTORY_SITE_URL", raising=False)
    monkeypatch.setattr("github_deployer._load_streamlit_secrets", lambda: {"DIRECTORY_SITE_URL": "https://yourportfolio.work"})

    assert get_config_value("DIRECTORY_SITE_URL") == "https://yourportfolio.work"


def test_get_optional_directory_config_returns_none_when_directory_sync_is_not_configured(monkeypatch):
    monkeypatch.delenv("DIRECTORY_REPO_OWNER", raising=False)
    monkeypatch.delenv("DIRECTORY_REPO_NAME", raising=False)
    monkeypatch.delenv("DIRECTORY_SITE_URL", raising=False)
    monkeypatch.setattr("github_deployer._load_streamlit_secrets", lambda: {})

    assert get_optional_directory_config() is None


def test_create_repo_payload():
    session = FakeSession([FakeResponse(201, {"name": "portfolio-demo"})])
    client = GitHubClient(config(), session=session)

    assert client.create_repo("portfolio-demo") == "portfolio-demo"
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.github.com/user/repos"
    assert call["json"] == {
        "name": "portfolio-demo",
        "private": False,
        "auto_init": True,
        "description": "Auto deployed portfolio website",
        "has_issues": False,
        "has_projects": False,
        "has_wiki": False,
    }


def test_create_repo_uses_timestamp_suffix_when_name_exists(monkeypatch):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime

            return datetime(2026, 5, 27, 12, 30, 0)

    monkeypatch.setattr("github_deployer.datetime", FixedDateTime)
    session = FakeSession([FakeResponse(422, {"message": "name already exists"}), FakeResponse(201, {})])
    client = GitHubClient(config(), session=session)

    assert client.create_repo("portfolio-demo") == "portfolio-demo-20260527123000"
    assert session.calls[1]["json"]["name"] == "portfolio-demo-20260527123000"


def test_upload_index_html_payload_without_existing_sha():
    session = FakeSession([FakeResponse(404), FakeResponse(201, {})])
    client = GitHubClient(config(), session=session)

    client.upload_content("portfolio-demo", "index.html", "<html>ok</html>", "Deploy portfolio index.html")
    put_call = session.calls[1]
    assert put_call["method"] == "PUT"
    assert put_call["url"] == "https://api.github.com/repos/octocat/portfolio-demo/contents/index.html"
    assert put_call["json"]["message"] == "Deploy portfolio index.html"
    assert put_call["json"]["branch"] == "main"
    assert base64.b64decode(put_call["json"]["content"]).decode("utf-8") == "<html>ok</html>"
    assert "sha" not in put_call["json"]


def test_upload_index_html_payload_with_existing_sha():
    session = FakeSession([FakeResponse(200, {"sha": "abc123"}), FakeResponse(200, {})])
    client = GitHubClient(config(), session=session)

    client.upload_content("portfolio-demo", "index.html", "<html>updated</html>", "Deploy portfolio index.html")
    assert session.calls[1]["json"]["sha"] == "abc123"


def test_upload_binary_content_payload():
    session = FakeSession([FakeResponse(404), FakeResponse(201, {})])
    client = GitHubClient(config(), session=session)

    client.upload_binary_content("portfolio-demo", "assets/profile.png", b"\x89PNG", "Upload profile picture")

    put_call = session.calls[1]
    assert put_call["method"] == "PUT"
    assert put_call["url"] == "https://api.github.com/repos/octocat/portfolio-demo/contents/assets/profile.png"
    assert base64.b64decode(put_call["json"]["content"]) == b"\x89PNG"


def test_pages_url_generation():
    assert pages_url_for("octocat", "portfolio-demo") == "https://octocat.github.io/portfolio-demo/"


def test_directory_route_url_generation():
    assert directory_route_url_for("https://yourportfolio.work/", "anshprasad") == "https://yourportfolio.work/anshprasad"


def test_enable_pages_payload():
    session = FakeSession([FakeResponse(201, {})])
    client = GitHubClient(config(), session=session)

    client.enable_pages("portfolio-demo")
    assert session.calls[0]["json"] == {"source": {"branch": "main", "path": "/"}}


def test_enable_pages_already_enabled_continues():
    session = FakeSession([FakeResponse(422, {"message": "GitHub Pages already enabled"})])
    client = GitHubClient(config(), session=session)

    client.enable_pages("portfolio-demo")


def test_enable_pages_conflict_updates_existing_pages_settings():
    session = FakeSession([FakeResponse(409, {"message": "Conflict"}), FakeResponse(204, {})])
    client = GitHubClient(config(), session=session)

    client.enable_pages("portfolio-demo")
    assert session.calls[1]["method"] == "PUT"
    assert session.calls[1]["url"] == "https://api.github.com/repos/octocat/portfolio-demo/pages"
    assert session.calls[1]["json"] == {"source": {"branch": "main", "path": "/"}}


def test_upsert_portfolio_record_updates_existing_user_and_preserves_created_at():
    entry = PortfolioDirectoryEntry(
        username="anshprasad",
        name="Ansh Prasad",
        role="Frontend Developer",
        template_type="modern-professional",
        image="/assets/users/anshprasad.png",
    )
    portfolios = [
        {
            "username": "anshprasad",
            "name": "Old Name",
            "role": "Old Role",
            "template_type": "old-template",
            "portfolio_url": "https://old.example.com",
            "image": "",
            "is_active": False,
            "created_at": "2026-01-01",
        }
    ]

    updated = upsert_portfolio_record(
        portfolios,
        entry,
        "https://yourportfolio.work/anshprasad",
        "<!doctype html><html><body>New</body></html>",
    )

    assert updated == [
        {
            "username": "anshprasad",
            "name": "Ansh Prasad",
            "role": "Frontend Developer",
            "template_type": "modern-professional",
            "portfolio_url": "https://yourportfolio.work/anshprasad",
            "image": "/assets/users/anshprasad.png",
            "is_active": True,
            "created_at": "2026-01-01",
            "html_content": "<!doctype html><html><body>New</body></html>",
        }
    ]


def test_sync_portfolio_to_directory_repo_updates_remote_json():
    existing_payload = base64.b64encode(
        (
            '[{"username":"riya","name":"Riya","role":"Designer","template_type":"creative",'
            '"portfolio_url":"https://riya.example.com","image":"","is_active":true,"created_at":"2026-05-20"}]'
        ).encode("utf-8")
    ).decode("ascii")
    session = FakeSession(
        [
            FakeResponse(200, {"content": existing_payload}),
            FakeResponse(200, {"sha": "abc123"}),
            FakeResponse(200, {}),
        ]
    )
    client = GitHubClient(config(), session=session)
    directory = DirectoryConfig(
        owner="orgname",
        repo="portfolio-directory",
        branch="main",
        data_path="data/portfolios.json",
        site_url="https://yourportfolio.work",
    )
    entry = PortfolioDirectoryEntry(
        username="anshprasad",
        name="Ansh Prasad",
        role="Frontend Developer",
        template_type="modern-professional",
        image="",
    )

    public_url = sync_portfolio_to_directory_repo(
        client=client,
        directory_config=directory,
        entry=entry,
        portfolio_url="https://octocat.github.io/portfolio-ansh/",
        html_content="<!doctype html><html><body>Ansh</body></html>",
    )

    assert public_url == "https://yourportfolio.work/anshprasad"
    put_call = session.calls[2]
    assert put_call["method"] == "PUT"
    assert put_call["url"] == "https://api.github.com/repos/orgname/portfolio-directory/contents/data/portfolios.json"
    payload = put_call["json"]
    decoded = base64.b64decode(payload["content"]).decode("utf-8")
    parsed = json.loads(decoded)
    assert [item["username"] for item in parsed] == ["anshprasad", "riya"]
    assert parsed[0]["portfolio_url"] == "https://octocat.github.io/portfolio-ansh/"
    assert parsed[0]["html_content"] == "<!doctype html><html><body>Ansh</body></html>"
    assert payload["branch"] == "main"
    assert payload["sha"] == "abc123"


def test_deploy_html_generates_pages_but_returns_custom_public_url(monkeypatch):
    class FakeDeployClient:
        calls = []

        def __init__(self, config):
            self.config = config

        def create_repo(self, requested_name):
            self.calls.append(("create_repo", requested_name))
            return requested_name

        def upload_content(self, repo_name, path, content, commit_message, stage="upload_file"):
            self.calls.append(("upload_content", repo_name, path, content, commit_message, stage))

        def enable_pages(self, repo_name):
            self.calls.append(("enable_pages", repo_name))

        def read_text_content_from_repo(self, owner, repo_name, path, branch, stage):
            self.calls.append(("read_text_content_from_repo", owner, repo_name, path, branch, stage))
            return "[]"

        def upload_content_to_repo(self, owner, repo_name, path, content, commit_message, branch, stage):
            self.calls.append(("upload_content_to_repo", owner, repo_name, path, content, commit_message, branch, stage))

    monkeypatch.setattr("github_deployer.GitHubClient", FakeDeployClient)
    monkeypatch.setattr("github_deployer.get_github_config", config)
    monkeypatch.setattr(
        "github_deployer.get_optional_directory_config",
        lambda: DirectoryConfig(
            owner="orgname",
            repo="portfolio-directory",
            branch="main",
            data_path="data/portfolios.json",
            site_url="https://yourportfolio.work",
        ),
    )
    monkeypatch.setattr("github_deployer.save_deployment_history", lambda result: None)

    result = deploy_html_portfolio(
        html_content="<!doctype html><html><body>Ansh</body></html>",
        repo_name="Ansh Portfolio",
        username="AnshPrasad",
    )

    assert result["success"] is True
    assert result["pages_url"] == "https://octocat.github.io/ansh-portfolio/"
    assert result["public_route_url"] == "https://yourportfolio.work/anshprasad"
    assert ("enable_pages", "ansh-portfolio") in FakeDeployClient.calls

    directory_upload = next(call for call in FakeDeployClient.calls if call[0] == "upload_content_to_repo")
    directory_records = json.loads(directory_upload[4])
    assert directory_records[0]["portfolio_url"] == "https://octocat.github.io/ansh-portfolio/"
    assert "html_content" not in directory_records[0]


def test_deploy_html_uploads_resume_and_profile_picture(monkeypatch):
    class FakeDeployClient:
        calls = []

        def __init__(self, config):
            self.config = config

        def create_repo(self, requested_name):
            self.calls.append(("create_repo", requested_name))
            return requested_name

        def upload_content(self, repo_name, path, content, commit_message, stage="upload_file"):
            self.calls.append(("upload_content", repo_name, path, content, commit_message, stage))

        def upload_binary_content(self, repo_name, path, content, commit_message, stage="upload_file"):
            self.calls.append(("upload_binary_content", repo_name, path, content, commit_message, stage))

        def enable_pages(self, repo_name):
            self.calls.append(("enable_pages", repo_name))

        def read_text_content_from_repo(self, owner, repo_name, path, branch, stage):
            self.calls.append(("read_text_content_from_repo", owner, repo_name, path, branch, stage))
            return "[]"

        def upload_content_to_repo(self, owner, repo_name, path, content, commit_message, branch, stage):
            self.calls.append(("upload_content_to_repo", owner, repo_name, path, content, commit_message, branch, stage))

    FakeDeployClient.calls = []
    monkeypatch.setattr("github_deployer.GitHubClient", FakeDeployClient)
    monkeypatch.setattr("github_deployer.get_github_config", config)
    monkeypatch.setattr(
        "github_deployer.get_optional_directory_config",
        lambda: DirectoryConfig(
            owner="orgname",
            repo="portfolio-directory",
            branch="main",
            data_path="data/portfolios.json",
            site_url="https://yourportfolio.work",
        ),
    )
    monkeypatch.setattr("github_deployer.save_deployment_history", lambda result: None)

    result = deploy_html_portfolio(
        html_content="<!doctype html><html><body>Ansh</body></html>",
        repo_name="Ansh Portfolio",
        username="AnshPrasad",
        resume_upload=PortfolioAssetUpload(filename="Resume Final.PDF", content=b"%PDF"),
        profile_picture_upload=PortfolioAssetUpload(filename="Profile Photo.JPG", content=b"jpg"),
    )

    assert result["success"] is True
    assert result["profile_picture_url"] == "https://octocat.github.io/ansh-portfolio/assets/profile-photo.jpg"
    assert result["resume_url"] == "https://octocat.github.io/ansh-portfolio/assets/resume-final.pdf"

    asset_uploads = [call for call in FakeDeployClient.calls if call[0] == "upload_binary_content"]
    assert asset_uploads == [
        ("upload_binary_content", "ansh-portfolio", "assets/profile-photo.jpg", b"jpg", "Upload profile picture", "upload_profile_picture"),
        ("upload_binary_content", "ansh-portfolio", "assets/resume-final.pdf", b"%PDF", "Upload resume", "upload_resume"),
    ]

    directory_upload = next(call for call in FakeDeployClient.calls if call[0] == "upload_content_to_repo")
    directory_records = json.loads(directory_upload[4])
    assert directory_records[0]["image"] == result["profile_picture_url"]


def test_collaborator_invite_payload():
    session = FakeSession([FakeResponse(201, {})])
    client = GitHubClient(config(), session=session)

    assert client.invite_collaborator("portfolio-demo", "clientusername", "push") is True
    assert session.calls[0]["method"] == "PUT"
    assert session.calls[0]["url"] == "https://api.github.com/repos/octocat/portfolio-demo/collaborators/clientusername"
    assert session.calls[0]["json"] == {"permission": "push"}


def test_collaborator_email_fails_clearly():
    client = GitHubClient(config(), session=FakeSession([]))

    with pytest.raises(DeploymentError) as exc:
        client.invite_collaborator("portfolio-demo", "person@example.com", "push")
    assert "username" in exc.value.message


def test_rate_limit_failure_message():
    session = FakeSession([FakeResponse(403, {"message": "rate limit"}, {"X-RateLimit-Remaining": "0"})])
    client = GitHubClient(config(), session=session)

    with pytest.raises(DeploymentError) as exc:
        client.enable_pages("portfolio-demo")
    assert exc.value.stage == "enable_pages"
    assert "rate limit" in exc.value.message.lower()
