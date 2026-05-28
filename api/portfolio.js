const fs = require("fs/promises");
const path = require("path");

const DATA_FILE = path.join(process.cwd(), "data", "portfolios.json");
const USERNAME_PATTERN = /^[a-z0-9_-]+$/;

async function readPortfolios() {
  const raw = await fs.readFile(DATA_FILE, "utf8");
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [];
}

function renderNotFound(username) {
  const safeUsername = username ? String(username).replace(/[<>"']/g, "") : "unknown";
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Portfolio Not Found</title>
    <meta name="robots" content="noindex" />
    <link rel="stylesheet" href="/assets/styles.css" />
  </head>
  <body>
    <main class="shell shell-narrow">
      <section class="panel empty-state">
        <p class="eyebrow">Portfolio Lookup</p>
        <h1>This portfolio is not live.</h1>
        <p class="lead">We could not find an active portfolio for <strong>@${safeUsername}</strong>.</p>
        <a class="primary-link" href="/">Back to homepage</a>
      </section>
    </main>
  </body>
</html>`;
}

module.exports = async (req, res) => {
  try {
    const username = typeof req.query.username === "string" ? req.query.username.trim() : "";

    if (!username) {
      const portfolios = await readPortfolios();
      res.status(200).json({
        portfolios,
        active_count: portfolios.filter((entry) => entry && entry.is_active === true).length,
      });
      return;
    }

    if (!USERNAME_PATTERN.test(username)) {
      res.status(404).setHeader("Content-Type", "text/html; charset=utf-8").send(renderNotFound(username));
      return;
    }

    const portfolios = await readPortfolios();
    const match = portfolios.find(
      (entry) =>
        entry &&
        entry.username === username &&
        entry.is_active === true &&
        typeof entry.portfolio_url === "string" &&
        entry.portfolio_url.trim() !== ""
    );

    if (!match) {
      res.status(404).setHeader("Content-Type", "text/html; charset=utf-8").send(renderNotFound(username));
      return;
    }

    res.setHeader("Cache-Control", "no-store");
    res.redirect(302, match.portfolio_url);
  } catch (error) {
    res.status(500).json({
      error: "Unable to read portfolio directory.",
    });
  }
};
