from __future__ import annotations

import hmac
import json
from pathlib import Path

import streamlit as st

from github_deployer import (
    HISTORY_DB_PATH,
    check_github_auth,
    check_repo_create_access,
    deploy_html_portfolio,
    enable_pages_for_existing_repo,
    init_history_db,
)


APP_TITLE = "Portfolio Deployment Admin"
APP_DESCRIPTION = (
    "Upload a portfolio HTML file, publish it to GitHub Pages, and sync the public username route."
)


def _get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value).strip()


def _is_auth_configured() -> bool:
    return bool(_get_secret("APP_LOGIN_USER")) and bool(_get_secret("APP_LOGIN_PASSWORD"))


def _credentials_match(username: str, password: str) -> bool:
    expected_username = _get_secret("APP_LOGIN_USER")
    expected_password = _get_secret("APP_LOGIN_PASSWORD")
    return hmac.compare_digest(username, expected_username) and hmac.compare_digest(password, expected_password)


def _require_login() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not _is_auth_configured():
        st.warning(
            "Login protection is not active yet. Add `APP_LOGIN_USER` and `APP_LOGIN_PASSWORD` in Streamlit Secrets."
        )
        return

    if st.session_state.authenticated:
        return

    st.subheader("Login Required")
    st.write("Enter your user ID and password to open the deployment dashboard.")
    with st.form("login_form"):
        username = st.text_input("User ID")
        password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Login", use_container_width=True)

    if login_submitted:
        if _credentials_match(username, password):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid user ID or password.")

    st.stop()


def _render_status_card(title: str, payload: dict) -> None:
    success = bool(payload.get("success"))
    box = st.success if success else st.error
    box(title if success else f"{title} failed")

    if success:
        if payload.get("message"):
            st.write(payload["message"])
    else:
        stage = payload.get("stage", "unknown")
        error = payload.get("error", "Unknown error")
        st.write(f"Stage: `{stage}`")
        st.write(f"Error: `{error}`")

    filtered = {
        key: value
        for key, value in payload.items()
        if key not in {"success", "message", "stage", "error"}
    }
    if filtered:
        st.json(filtered)


def _render_deploy_result(payload: dict) -> None:
    if not payload.get("success"):
        _render_status_card("Deployment", payload)
        return

    st.success("Portfolio deployed successfully.")
    st.write(f"Repository: {payload.get('repo_url', 'Not available')}")
    st.write(f"GitHub Pages URL: {payload.get('pages_url', 'Not available')}")
    if payload.get("public_route_url"):
        st.write(f"Public username URL: {payload['public_route_url']}")
    elif not payload.get("directory_sync_enabled"):
        st.info("Directory sync is not configured, so only the GitHub repo and GitHub Pages link were created.")

    collaborator = payload.get("collaborator")
    if payload.get("collaborator_invited") and collaborator:
        st.write(f"Collaborator invite sent to `{collaborator}`.")

    with st.expander("Full response"):
        st.json(payload)


def _load_recent_history(limit: int = 20) -> list[dict]:
    import sqlite3

    init_history_db(HISTORY_DB_PATH)
    with sqlite3.connect(HISTORY_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM deployments ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


st.set_page_config(page_title=APP_TITLE, page_icon=":rocket:", layout="centered")

_require_login()

st.title(APP_TITLE)
st.caption(APP_DESCRIPTION)

with st.sidebar:
    if _is_auth_configured():
        st.success("Logged in")
        if st.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.subheader("Required secrets")
    st.code(
        "\n".join(
            [
                'APP_LOGIN_USER = "admin"',
                'APP_LOGIN_PASSWORD = "change-this-password"',
                'GITHUB_TOKEN = "ghp_your_token_here"',
                'GITHUB_USERNAME = "your-github-username"',
                'GITHUB_REPO_VISIBILITY = "public"',
                'GITHUB_PAGES_BRANCH = "main"',
                'GITHUB_REPO_PREFIX = "portfolio-"',
                'DIRECTORY_REPO_OWNER = "your-github-owner"',
                'DIRECTORY_REPO_NAME = "your-directory-repo"',
                'DIRECTORY_REPO_BRANCH = "main"',
                'DIRECTORY_DATA_PATH = "data/portfolios.json"',
                'DIRECTORY_SITE_URL = "https://your-site.vercel.app"',
            ]
        ),
        language="toml",
    )
    st.write("Add these in Streamlit App Settings -> Secrets before deploying.")

col1, col2 = st.columns(2)

with col1:
    if st.button("Check GitHub auth", use_container_width=True):
        _render_status_card("GitHub auth", check_github_auth())

with col2:
    if st.button("Check repo create access", use_container_width=True):
        _render_status_card("Repository access", check_repo_create_access())

st.divider()

st.subheader("Deploy new portfolio")
st.caption("Required: HTML file, repository name, and username. Everything else is optional.")

with st.form("deploy_form"):
    uploaded_file = st.file_uploader("Portfolio HTML file", type=["html"])
    repo_name = st.text_input("Portfolio/repository name", placeholder="Ansh Prasad Portfolio")
    username = st.text_input("Public username route", placeholder="anshprasad")
    display_name = ""
    role = ""
    template_type = ""
    image = ""
    share_access = False
    collaborator = ""
    collaborator_permission = "push"

    with st.expander("Optional details for directory listing and sharing"):
        st.caption("You can leave all of these blank if you only want the GitHub repo link and GitHub Pages portfolio link.")
        display_name = st.text_input("Display name", placeholder="Ansh Prasad")
        role = st.text_input("Role", placeholder="Frontend Developer")
        template_type = st.text_input("Template type", placeholder="custom")
        image = st.text_input("Preview image path", placeholder="/assets/users/anshprasad.png")
        share_access = st.checkbox("Share repository access with someone")
        if share_access:
            collaborator = st.text_input("Collaborator GitHub username", placeholder="clientusername")
            collaborator_permission = st.selectbox(
                "Collaborator permission",
                options=["pull", "push", "admin"],
                index=1,
            )

    deploy_submitted = st.form_submit_button("Deploy portfolio", use_container_width=True)

if deploy_submitted:
    if uploaded_file is None:
        st.error("Upload an HTML file first.")
    else:
        try:
            html_content = uploaded_file.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.error("The HTML file must be UTF-8 encoded.")
        else:
            result = deploy_html_portfolio(
                html_content=html_content,
                repo_name=repo_name,
                username=username,
                display_name=display_name or None,
                role=role or None,
                template_type=template_type or None,
                image=image or None,
                collaborator=collaborator or None,
                collaborator_permission=collaborator_permission,
            )
            _render_deploy_result(result)

st.divider()

st.subheader("Enable GitHub Pages for an existing repository")
with st.form("pages_form"):
    existing_repo_name = st.text_input("Existing repository name", placeholder="portfolio-ansh-prasad")
    pages_submitted = st.form_submit_button("Enable GitHub Pages", use_container_width=True)

if pages_submitted:
    _render_status_card("Enable GitHub Pages", enable_pages_for_existing_repo(existing_repo_name))

st.divider()

st.subheader("Recent deployment history")

try:
    history_rows = _load_recent_history()
except Exception as exc:
    st.info(f"History is not available yet: {exc}")
else:
    if not history_rows:
        st.info("No deployments have been recorded yet.")
    else:
        st.dataframe(history_rows, use_container_width=True, hide_index=True)
        with st.expander("History JSON"):
            st.code(json.dumps(history_rows, indent=2), language="json")

st.divider()

st.subheader("Streamlit deploy entrypoint")
st.code("Main file path: app.py", language="text")
st.write(f"Working directory: `{Path(__file__).parent}`")
