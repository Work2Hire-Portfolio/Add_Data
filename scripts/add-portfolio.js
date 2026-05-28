#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const USERNAME_PATTERN = /^[a-z0-9_-]+$/;
const DATA_FILE = path.join(__dirname, "..", "data", "portfolios.json");
const PUBLIC_BASE_URL = (process.env.PUBLIC_BASE_URL || "https://yourportfolio.work").replace(/\/+$/, "");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  const parsed = {};

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      fail(`Unexpected argument "${token}". Use --key value pairs.`);
    }

    const key = token.slice(2);
    const value = argv[index + 1];

    if (!key) {
      fail("Argument keys cannot be empty.");
    }

    if (!value || value.startsWith("--")) {
      fail(`Missing value for --${key}.`);
    }

    parsed[key] = value;
    index += 1;
  }

  return parsed;
}

function readPortfolios() {
  if (!fs.existsSync(DATA_FILE)) {
    return [];
  }

  const raw = fs.readFileSync(DATA_FILE, "utf8");
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) {
    fail("data/portfolios.json must contain a JSON array.");
  }

  return parsed;
}

function validateRequired(args) {
  const required = ["username", "name", "role", "template", "url"];
  for (const key of required) {
    if (!args[key] || !args[key].trim()) {
      fail(`--${key} is required.`);
    }
  }
}

function validateUsername(username, portfolios) {
  if (!USERNAME_PATTERN.test(username)) {
    fail("Username must contain only lowercase letters, numbers, hyphens, or underscores.");
  }

  if (portfolios.some((entry) => entry && entry.username === username)) {
    fail(`Username "${username}" already exists in data/portfolios.json.`);
  }
}

function validateUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch (error) {
    fail(`Invalid --url value "${url}".`);
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    fail("--url must start with http:// or https://.");
  }
}

function buildEntry(args) {
  return {
    username: args.username,
    name: args.name,
    role: args.role,
    template_type: args.template,
    portfolio_url: args.url,
    image: args.image || "",
    is_active: true,
    created_at: new Date().toISOString().slice(0, 10),
  };
}

function savePortfolios(portfolios) {
  fs.writeFileSync(DATA_FILE, `${JSON.stringify(portfolios, null, 2)}\n`, "utf8");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  validateRequired(args);

  const portfolios = readPortfolios();
  validateUsername(args.username, portfolios);
  validateUrl(args.url);

  const entry = buildEntry(args);
  portfolios.push(entry);
  savePortfolios(portfolios);

  console.log("Portfolio entry added successfully.");
  console.log(`Public link: ${PUBLIC_BASE_URL}/${entry.username}`);
}

main();
