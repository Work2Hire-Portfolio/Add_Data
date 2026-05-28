import base64

import pytest

from github_deployer import (
    DeploymentError,
    GitHubClient,
    GitHubConfig,
    pages_url_for,
    sanitize_repo_name,
    validate_html_upload,
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


def test_pages_url_generation():
    assert pages_url_for("octocat", "portfolio-demo") == "https://octocat.github.io/portfolio-demo/"


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
