# YourPortfolio / Work to Hire Showcase

This project is a simple GitHub + Vercel workflow for a portfolio hosting platform:

- `https://yourportfolio.work/` shows the main dashboard.
- `https://yourportfolio.work/:username` redirects to the user's live portfolio.
- The homepage portfolio grid is generated from `data/portfolios.json`.
- The deploy app now creates the GitHub Pages repo and updates the public Vercel directory repo automatically.

No database is required right now. The admin deploy app commits the portfolio metadata into the directory repo through the GitHub API, then Vercel redeploys the main site.

## Required environment variables

```text
GITHUB_TOKEN=
GITHUB_USERNAME=
GITHUB_REPO_VISIBILITY=public
GITHUB_PAGES_BRANCH=main
GITHUB_REPO_PREFIX=portfolio-
DIRECTORY_REPO_OWNER=
DIRECTORY_REPO_NAME=
DIRECTORY_REPO_BRANCH=main
DIRECTORY_DATA_PATH=data/portfolios.json
DIRECTORY_SITE_URL=https://your-project.vercel.app
```

`DIRECTORY_*` values point to the GitHub repo that backs the public Vercel site, so `/username` routes can be updated automatically after each deploy.

## Streamlit secrets support

If you host the admin app on Streamlit, the same config keys can be stored in `.streamlit/secrets.toml` or in the app's Secrets panel.

```toml
GITHUB_TOKEN = "your_token"
GITHUB_USERNAME = "your_username"
GITHUB_REPO_VISIBILITY = "public"
GITHUB_PAGES_BRANCH = "main"
GITHUB_REPO_PREFIX = "portfolio-"
DIRECTORY_REPO_OWNER = "your-owner"
DIRECTORY_REPO_NAME = "your-vercel-repo"
DIRECTORY_REPO_BRANCH = "main"
DIRECTORY_DATA_PATH = "data/portfolios.json"
DIRECTORY_SITE_URL = "https://your-project.vercel.app"
```

Config loading order is:

- environment variable first
- Streamlit secret second
- default value last where supported

## Project Structure

```text
/
|-- index.html
|-- 404.html
|-- vercel.json
|-- assets/
|   |-- app.js
|   |-- styles.css
|   `-- users/
|-- api/
|   `-- portfolio.js
|-- data/
|   `-- portfolios.json
`-- scripts/
    `-- add-portfolio.js
```

## How It Works

### 1. Homepage

`index.html` keeps the dashboard static and lightweight. The live portfolio section is dynamic:

- `assets/app.js` fetches `data/portfolios.json`
- only entries with `is_active: true` are shown
- entries without `portfolio_url` are skipped
- loading, empty, and error states are handled in the UI

### 2. Username Routing

`vercel.json` sends clean one-segment routes like `/anshprasad` to `api/portfolio.js`.

The serverless function:

- reads `data/portfolios.json`
- matches the `username`
- checks that the entry is active
- redirects to `portfolio_url`
- returns a clean 404 page when the username is missing or inactive

### 3. Add Portfolio Workflow

Use the CLI script to append a new entry safely:

```powershell
node scripts/add-portfolio.js `
  --username anshprasad `
  --name "Ansh Prasad" `
  --role "Frontend Developer" `
  --template "modern-professional" `
  --url "https://anshprasad.github.io/portfolio" `
  --image "/assets/users/anshprasad.svg"
```

The script will:

- validate required fields
- validate the username format
- ensure the username is unique
- validate that the URL is public HTTP or HTTPS
- set `is_active` to `true`
- add `created_at`
- save formatted JSON back to `data/portfolios.json`
- print the final public link

By default, the printed link uses `https://yourportfolio.work`. You can override that locally:

```powershell
$env:PUBLIC_BASE_URL="https://staging.yourportfolio.work"
node scripts/add-portfolio.js --username demo --name "Demo User" --role "Designer" --template "creative-showcase" --url "https://example.com"
```

## Manual Deployment Workflow

### Step 1

Generate or host the user's portfolio on any public platform:

- GitHub Pages
- Vercel
- Netlify
- any public static hosting URL

### Step 2

Add the user to the directory:

```powershell
node scripts/add-portfolio.js `
  --username riya `
  --name "Riya Sharma" `
  --role "UI Engineer" `
  --template "creative-showcase" `
  --url "https://riyasharma-portfolio.vercel.app"
```

### Step 3

Commit and push the repo changes to GitHub.

### Step 4

Vercel automatically redeploys the main site.

### Step 5

After the deploy:

- the homepage automatically shows the new active user
- `https://yourportfolio.work/riya` redirects to the user's portfolio

## Portfolio Data Format

`data/portfolios.json`

```json
[
  {
    "username": "anshprasad",
    "name": "Ansh Prasad",
    "role": "Frontend Developer",
    "template_type": "modern-professional",
    "portfolio_url": "https://anshprasad.github.io/portfolio",
    "image": "/assets/users/anshprasad.svg",
    "is_active": true,
    "created_at": "2026-05-28"
  }
]
```

## Update or Disable a User

For now, edit `data/portfolios.json` manually when needed:

- set `is_active` to `false` to hide a portfolio and disable its public route
- update `portfolio_url` when the user changes hosting
- update `image`, `role`, or `template_type` as needed

## Future Admin Panel Readiness

The JSON structure is already ready for a later admin layer that can:

- add a user
- upload a preview image
- edit metadata
- toggle active or inactive
- delete a user

When you add an admin panel later, it can update the same JSON structure or move to a database without changing the public URL pattern.

## Local Preview

If you want to preview this as a static site locally, any simple static server will work. For example:

```powershell
npx serve .
```

Then open the local URL and test:

- `/`
- `/anshprasad`
- a missing route like `/unknown-user`
