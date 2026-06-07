const form = document.querySelector("#deployForm");
const pagesForm = document.querySelector("#pagesForm");
const shareAccess = document.querySelector("#shareAccess");
const collaboratorFields = document.querySelector("#collaboratorFields");
const result = document.querySelector("#result");
const submitButton = document.querySelector("#submitButton");
const pagesButton = document.querySelector("#pagesButton");

shareAccess.addEventListener("change", () => {
  collaboratorFields.classList.toggle("hidden", !shareAccess.checked);
});

function row(label, value, copyable = false, link = false) {
  const safeValue = value || "Not provided";
  const body = link
    ? `<a href="${safeValue}" target="_blank" rel="noreferrer">${safeValue}</a>`
    : `<code>${safeValue}</code>`;
  const button = copyable ? `<button class="copy" type="button" data-copy="${safeValue}">Copy</button>` : "";
  return `<div class="result-row"><span>${label}</span>${body}${button}</div>`;
}

function showResult(payload) {
  result.className = `panel result ${payload.success ? "" : "error"}`;
  if (!payload.success) {
    result.innerHTML = `
      <h2>Deployment failed</h2>
      ${row("Stage", payload.stage || "unknown")}
      ${row("Error", payload.error || "Unknown error")}
    `;
    return;
  }

  const collaboratorText = payload.collaborator_invited
    ? `Invitation sent to ${payload.collaborator}`
    : "No collaborator invited";

  result.innerHTML = `
    <h2>${payload.status === "pages_enabled" ? "GitHub Pages enabled." : "Portfolio deployed successfully."}</h2>
    ${row("Repository", payload.repo_url, true, true)}
    ${payload.public_route_url ? row("Live Portfolio", payload.public_route_url, true, true) : ""}
    ${row("Collaborator", collaboratorText)}
  `;
}

result.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  await navigator.clipboard.writeText(button.dataset.copy);
  const original = button.textContent;
  button.textContent = "Copied";
  setTimeout(() => {
    button.textContent = original;
  }, 1200);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  submitButton.textContent = "Deploying...";
  result.classList.add("hidden");

  const data = new FormData(form);
  if (!shareAccess.checked) {
    data.delete("collaborator");
    data.delete("collaborator_permission");
  }

  try {
    const response = await fetch("/api/deploy-portfolio", {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    showResult(payload);
  } catch (error) {
    showResult({
      success: false,
      stage: "network",
      error: "Could not reach the deployment API. Check that the server is running.",
    });
  } finally {
    result.classList.remove("hidden");
    submitButton.disabled = false;
    submitButton.textContent = "Deploy Portfolio";
  }
});

pagesForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  pagesButton.disabled = true;
  pagesButton.textContent = "Enabling...";
  result.classList.add("hidden");

  try {
    const response = await fetch("/api/enable-pages", {
      method: "POST",
      body: new FormData(pagesForm),
    });
    const payload = await response.json();
    showResult(payload);
  } catch (error) {
    showResult({
      success: false,
      stage: "network",
      error: "Could not reach the deployment API. Check that the server is running.",
    });
  } finally {
    result.classList.remove("hidden");
    pagesButton.disabled = false;
    pagesButton.textContent = "Enable Pages";
  }
});
