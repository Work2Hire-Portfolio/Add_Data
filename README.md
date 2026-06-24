# Streamlit Portfolio Deployer

This folder is now ready to deploy as a Streamlit app.

The app lets you:

- upload a portfolio `.html` file
- optionally upload a resume and profile picture into the same GitHub repository
- create a GitHub repository automatically
- store the uploaded portfolio in that repository
- enable GitHub Pages for that repository as a background origin
- update your public directory repo so `https://yourportfolio.work/username` serves the portfolio through your custom domain
- optionally invite a GitHub collaborator

## Streamlit Deployment Settings

When you create the app on Streamlit Community Cloud, use:

- Repository: the GitHub repo that contains this `streamlit` folder
- Branch: your deploy branch
- Main file path: `streamlit/app.py`

If this folder itself is the repo root, then the main file path is:

- `app.py`

## Required Secrets

Add these in Streamlit:

`App Settings -> Secrets`

Use this template:

```toml
APP_LOGIN_USER = "admin"
APP_LOGIN_PASSWORD = "change-this-password"
GITHUB_TOKEN = "ghp_your_token_here"
GITHUB_USERNAME = "your-github-username"
GITHUB_REPO_VISIBILITY = "public"
GITHUB_PAGES_BRANCH = "main"
GITHUB_REPO_PREFIX = "portfolio-"
DIRECTORY_REPO_OWNER = "your-github-owner"
DIRECTORY_REPO_NAME = "your-directory-repo"
DIRECTORY_REPO_BRANCH = "main"
DIRECTORY_DATA_PATH = "data/portfolios.json"
DIRECTORY_SITE_URL = "https://yourportfolio.work"
```

You can also copy the example file:

- [`.streamlit/secrets.toml.example`](./.streamlit/secrets.toml.example)

## App Login Protection

The app now supports a simple login screen before anyone can use the deployer.

Add these two secrets:

- `APP_LOGIN_USER`
- `APP_LOGIN_PASSWORD`

After that, anyone opening the Streamlit URL must enter that user ID and password first.

If these two values are missing, the app will still open and show a warning that login protection is not active.

## Important Secret Meaning

- `APP_LOGIN_USER`: login user ID for the Streamlit admin app
- `APP_LOGIN_PASSWORD`: login password for the Streamlit admin app
- `GITHUB_TOKEN`: GitHub personal access token with repo create, contents write, pages, and collaborator permissions
- `GITHUB_USERNAME`: the GitHub account that will own the deployed portfolio repos
- `DIRECTORY_REPO_OWNER`: owner of the public directory repo
- `DIRECTORY_REPO_NAME`: repo that contains `data/portfolios.json`
- `DIRECTORY_SITE_URL`: the public custom-domain site for shared username links, usually `https://yourportfolio.work`

## Local Run

From this folder:

```powershell
streamlit run app.py
```

Optional resume files are stored in the generated portfolio repo under `assets/` and may be `.pdf`, `.doc`, or `.docx`.
Optional profile pictures are also stored under `assets/` and may be `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, or `.svg`.

## Install Dependencies

```powershell
pip install -r requirements.txt
```

## Share Online

After deployment, Streamlit gives you a public app URL. Anyone with that Streamlit link can open the deployer UI online.

The actual portfolio websites created by the app will be public at `https://yourportfolio.work/<username>` if:

- `DIRECTORY_SITE_URL=https://yourportfolio.work`
- the directory repo sync is configured
- your Vercel project is connected to `yourportfolio.work`

New deployments enable GitHub Pages in the background, but visitors and users receive the custom-domain URL. The Vercel route fetches the GitHub Pages origin server-side and returns it at `https://yourportfolio.work/<username>` instead of visibly redirecting visitors to GitHub Pages. If someone edits the portfolio repo later, the custom-domain page can reflect those changes after GitHub Pages rebuilds and the short Vercel cache expires.

## Notes

- The app stores deployment history in `deployment_history.sqlite3`.
- Streamlit loads secrets from its hosted secrets panel automatically.
- `github_deployer.py` already supports Streamlit secrets, so no extra config code is needed.
