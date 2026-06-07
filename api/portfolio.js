const fs = require("fs/promises");
const path = require("path");

const DEFAULT_DATA_FILE = path.join(process.cwd(), "data", "portfolios.json");
const USERNAME_PATTERN = /^[a-z0-9_-]+$/;

function getDataFile() {
  return process.env.PORTFOLIO_DATA_FILE || DEFAULT_DATA_FILE;
}

async function readPortfolios() {
  const raw = await fs.readFile(getDataFile(), "utf8");
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [];
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderNotFound(username) {
  const safeUsername = username ? escapeHtml(username) : "unknown";
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

function publicPortfolioUrl(req, username) {
  const host = req.headers && (req.headers["x-forwarded-host"] || req.headers.host);
  if (!host) {
    return `/${encodeURIComponent(username)}`;
  }
  const proto = (req.headers["x-forwarded-proto"] || "https").split(",")[0].trim() || "https";
  return `${proto}://${host}/${encodeURIComponent(username)}`;
}

function toPublicDirectoryEntry(entry, req) {
  const { html_content: _htmlContent, ...publicEntry } = entry;
  if (typeof entry.username === "string" && entry.username.trim() !== "") {
    publicEntry.portfolio_url = publicPortfolioUrl(req, entry.username);
  }
  return publicEntry;
}

function findActivePortfolio(portfolios, username) {
  return portfolios.find(
    (entry) =>
      entry &&
      entry.username === username &&
      entry.is_active === true &&
      ((typeof entry.html_content === "string" && entry.html_content.trim() !== "") ||
        (typeof entry.portfolio_url === "string" && entry.portfolio_url.trim() !== ""))
  );
}

function validateOriginUrl(portfolioUrl) {
  const parsed = new URL(portfolioUrl);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("Unsupported portfolio origin.");
  }
  return parsed.toString();
}

function injectBaseHref(html, portfolioUrl) {
  const baseHref = escapeHtml(portfolioUrl);
  const baseTag = `<base href="${baseHref}" />`;

  if (/<base\s/i.test(html)) {
    return html;
  }
  if (/<head[^>]*>/i.test(html)) {
    return html.replace(/<head([^>]*)>/i, `<head$1>\n    ${baseTag}`);
  }
  return `${baseTag}\n${html}`;
}

async function fetchPortfolioHtml(portfolioUrl) {
  const originUrl = validateOriginUrl(portfolioUrl);
  const response = await fetch(originUrl, {
    redirect: "follow",
    headers: {
      Accept: "text/html,application/xhtml+xml",
      "User-Agent": "yourportfolio-work-renderer",
    },
  });

  if (!response.ok) {
    throw new Error(`Portfolio origin returned ${response.status}.`);
  }

  return injectBaseHref(await response.text(), originUrl);
}

function sendHtml(res, html, cacheControl = "public, max-age=60, s-maxage=300") {
  res.status(200);
  res.setHeader("Cache-Control", cacheControl);
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.send(html);
}

async function portfolioHandler(req, res) {
  try {
    const username = typeof req.query.username === "string" ? req.query.username.trim() : "";

    if (!username) {
      const portfolios = await readPortfolios();
      const publicPortfolios = portfolios.map((entry) =>
        entry && typeof entry === "object" ? toPublicDirectoryEntry(entry, req) : entry
      );
      res.status(200).json({
        portfolios: publicPortfolios,
        active_count: portfolios.filter((entry) => entry && entry.is_active === true).length,
      });
      return;
    }

    if (!USERNAME_PATTERN.test(username)) {
      res.status(404).setHeader("Content-Type", "text/html; charset=utf-8").send(renderNotFound(username));
      return;
    }

    const portfolios = await readPortfolios();
    const match = findActivePortfolio(portfolios, username);

    if (!match) {
      res.status(404).setHeader("Content-Type", "text/html; charset=utf-8").send(renderNotFound(username));
      return;
    }

    if (typeof match.html_content === "string" && match.html_content.trim() !== "") {
      sendHtml(res, match.html_content);
      return;
    }

    const html = await fetchPortfolioHtml(match.portfolio_url);
    sendHtml(res, html, "public, max-age=60, s-maxage=120");
  } catch (error) {
    res.status(500).json({
      error: "Unable to read portfolio directory.",
    });
  }
};

portfolioHandler.default = portfolioHandler;
portfolioHandler.handler = portfolioHandler;
portfolioHandler.readPortfolios = readPortfolios;
portfolioHandler.findActivePortfolio = findActivePortfolio;
portfolioHandler.fetchPortfolioHtml = fetchPortfolioHtml;

module.exports = portfolioHandler;
module.exports.default = portfolioHandler;
module.exports.handler = portfolioHandler;
