const portfolioGrid = document.querySelector("#portfolioGrid");
const portfolioFeedback = document.querySelector("#portfolioFeedback");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildPortfolioCard(portfolio) {
  const imageMarkup = portfolio.image
    ? `<img class="portfolio-preview" src="${escapeHtml(portfolio.image)}" alt="${escapeHtml(
        portfolio.name
      )} portfolio preview" loading="lazy" />`
    : "";

  return `
    <article class="portfolio-card">
      ${imageMarkup}
      <div class="portfolio-header">
        <span class="portfolio-badge">${escapeHtml(portfolio.template_type)}</span>
        <h3>${escapeHtml(portfolio.name)}</h3>
      </div>
      <div class="portfolio-meta">
        <div><strong>@${escapeHtml(portfolio.username)}</strong></div>
        <div>${escapeHtml(portfolio.role)}</div>
      </div>
      <a class="portfolio-link" href="/${encodeURIComponent(portfolio.username)}">View Portfolio</a>
    </article>
  `;
}

async function loadPortfolios() {
  if (!portfolioGrid || !portfolioFeedback) {
    return;
  }

  try {
    const response = await fetch("/data/portfolios.json", {
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Portfolio data request failed with status ${response.status}`);
    }

    const portfolios = await response.json();
    const activePortfolios = Array.isArray(portfolios)
      ? portfolios.filter(
          (entry) =>
            entry &&
            entry.is_active === true &&
            typeof entry.username === "string" &&
            typeof entry.portfolio_url === "string" &&
            entry.portfolio_url.trim() !== ""
        )
      : [];

    if (activePortfolios.length === 0) {
      portfolioFeedback.textContent = "No portfolios are live yet.";
      return;
    }

    portfolioGrid.innerHTML = activePortfolios.map(buildPortfolioCard).join("");
    portfolioGrid.hidden = false;
    portfolioFeedback.hidden = true;
  } catch (error) {
    portfolioFeedback.textContent = "Unable to load portfolios right now.";
    portfolioFeedback.classList.add("error");
  }
}

loadPortfolios();
