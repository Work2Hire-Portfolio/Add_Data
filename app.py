from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from github_deployer import (
    check_github_auth,
    check_repo_create_access,
    deploy_html_portfolio,
    enable_pages_for_existing_repo,
    validate_html_upload,
)


app = FastAPI(title="GitHub Portfolio Deployer")

STATIC_DIR = Path(__file__).parent / "static"


@app.post("/api/deploy-portfolio")
async def deploy_portfolio_endpoint(
    file: UploadFile = File(...),
    repo_name: str = Form(...),
    username: str = Form(...),
    display_name: str | None = Form(default=None),
    role: str | None = Form(default=None),
    template_type: str | None = Form(default=None),
    image: str | None = Form(default=None),
    collaborator: str | None = Form(default=None),
    collaborator_permission: str = Form(default="push"),
):
    try:
        if not file.filename or not file.filename.lower().endswith(".html"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "stage": "validate", "error": "Only .html files are accepted."},
            )
        raw = await file.read()
        html_content = raw.decode("utf-8")
        validate_html_upload(html_content, file.filename)
    except UnicodeDecodeError:
        return JSONResponse(
            status_code=400,
            content={"success": False, "stage": "validate", "error": "HTML file must be UTF-8 encoded."},
        )
    except Exception as exc:
        stage = getattr(exc, "stage", "validate")
        message = getattr(exc, "message", str(exc))
        return JSONResponse(status_code=400, content={"success": False, "stage": stage, "error": message})

    result = deploy_html_portfolio(
        html_content=html_content,
        repo_name=repo_name,
        username=username,
        display_name=display_name,
        role=role,
        template_type=template_type,
        image=image,
        collaborator=collaborator or None,
        collaborator_permission=collaborator_permission or "push",
    )
    return JSONResponse(status_code=200 if result.get("success") else 400, content=result)


@app.post("/api/enable-pages")
async def enable_pages_endpoint(repo_name: str = Form(...)):
    result = enable_pages_for_existing_repo(repo_name)
    return JSONResponse(status_code=200 if result.get("success") else 400, content=result)


@app.get("/api/github-auth-check")
async def github_auth_check_endpoint():
    result = check_github_auth()
    return JSONResponse(status_code=200 if result.get("success") else 400, content=result)


@app.get("/api/repo-create-check")
async def repo_create_check_endpoint():
    result = check_repo_create_access()
    return JSONResponse(status_code=200 if result.get("success") else 400, content=result)


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
