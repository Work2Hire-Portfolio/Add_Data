import json
import shutil
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_API = REPO_ROOT / "api" / "portfolio.js"
PORTFOLIO_API_REQUIRE = str(PORTFOLIO_API).replace("\\", "/")


def test_portfolio_api_serves_html_directly_without_redirect(tmp_path):
    node = shutil.which("node")
    if node is None:
        return

    data_file = tmp_path / "portfolios.json"
    data_file.write_text(
        json.dumps(
            [
                {
                    "username": "anshprasad",
                    "name": "Ansh Prasad",
                    "role": "Frontend Developer",
                    "template_type": "modern-professional",
                    "portfolio_url": "https://yourportfolio.work/anshprasad",
                    "html_content": "<!doctype html><html><body><h1>Direct Portfolio</h1></body></html>",
                    "is_active": True,
                    "created_at": "2026-05-28",
                }
            ]
        ),
        encoding="utf-8",
    )

    script = textwrap.dedent(
        f"""
        const assert = require("assert");
        process.env.PORTFOLIO_DATA_FILE = {json.dumps(str(data_file))};
        global.fetch = async () => {{
          throw new Error("fetch should not be needed for direct html_content records");
        }};
        const fs = require("fs");
        const vm = require("vm");
        const moduleForApi = {{ exports: {{}} }};
        vm.runInNewContext(fs.readFileSync({json.dumps(PORTFOLIO_API_REQUIRE)}, "utf8"), {{
          require,
          module: moduleForApi,
          exports: moduleForApi.exports,
          process,
          console,
          URL,
          fetch: global.fetch,
        }}, {{ filename: {json.dumps(PORTFOLIO_API_REQUIRE)} }});
        const mod = moduleForApi.exports;
        const handler = mod.default || mod.handler || mod;
        if (typeof handler !== "function") {{
          console.error("module shape", typeof mod, Object.keys(mod));
          process.exit(2);
        }}

        class FakeResponse {{
          constructor() {{
            this.statusCode = 200;
            this.headers = {{}};
            this.body = "";
            this.redirected = false;
          }}
          status(code) {{
            this.statusCode = code;
            return this;
          }}
          setHeader(name, value) {{
            this.headers[name.toLowerCase()] = value;
            return this;
          }}
          send(body) {{
            this.body = body;
            return this;
          }}
          json(payload) {{
            this.body = JSON.stringify(payload);
            this.payload = payload;
            return this;
          }}
          redirect() {{
            this.redirected = true;
            throw new Error("redirect should not be called");
          }}
        }}

        async function run() {{
          const res = new FakeResponse();
          await handler({{
            query: {{ username: "anshprasad" }},
            headers: {{ host: "yourportfolio.work", "x-forwarded-proto": "https" }},
          }}, res);
          assert.equal(res.statusCode, 200);
          assert.equal(res.redirected, false);
          assert.match(res.headers["content-type"], /text\\/html/);
          assert.match(res.body, /Direct Portfolio/);

          const invalid = new FakeResponse();
          await handler({{ query: {{ username: "bad user" }}, headers: {{}} }}, invalid);
          assert.equal(invalid.statusCode, 404);
          assert.match(invalid.body, /not live/i);

          const missing = new FakeResponse();
          await handler({{ query: {{ username: "missing" }}, headers: {{}} }}, missing);
          assert.equal(missing.statusCode, 404);
          assert.match(missing.body, /not live/i);
        }}

        run().catch((error) => {{
          console.error(error);
          process.exit(1);
        }});
        """
    )

    subprocess.run([node, "-e", script], check=True)


def test_portfolio_api_directory_listing_redacts_html(tmp_path):
    node = shutil.which("node")
    if node is None:
        return

    data_file = tmp_path / "portfolios.json"
    data_file.write_text(
        json.dumps(
            [
                {
                    "username": "riya",
                    "name": "Riya",
                    "role": "UI Engineer",
                    "template_type": "creative",
                    "portfolio_url": "https://legacy.example.com/riya",
                    "html_content": "<html>private public payload</html>",
                    "is_active": True,
                    "created_at": "2026-05-28",
                }
            ]
        ),
        encoding="utf-8",
    )

    script = textwrap.dedent(
        f"""
        const assert = require("assert");
        process.env.PORTFOLIO_DATA_FILE = {json.dumps(str(data_file))};
        const fs = require("fs");
        const vm = require("vm");
        const moduleForApi = {{ exports: {{}} }};
        vm.runInNewContext(fs.readFileSync({json.dumps(PORTFOLIO_API_REQUIRE)}, "utf8"), {{
          require,
          module: moduleForApi,
          exports: moduleForApi.exports,
          process,
          console,
          URL,
          fetch: global.fetch,
        }}, {{ filename: {json.dumps(PORTFOLIO_API_REQUIRE)} }});
        const mod = moduleForApi.exports;
        const handler = mod.default || mod.handler || mod;
        if (typeof handler !== "function") {{
          console.error("module shape", typeof mod, Object.keys(mod));
          process.exit(2);
        }}

        class FakeResponse {{
          constructor() {{
            this.statusCode = 200;
            this.headers = {{}};
          }}
          status(code) {{
            this.statusCode = code;
            return this;
          }}
          setHeader(name, value) {{
            this.headers[name.toLowerCase()] = value;
            return this;
          }}
          send(body) {{
            this.body = body;
            return this;
          }}
          json(payload) {{
            this.payload = payload;
            return this;
          }}
        }}

        async function run() {{
          const res = new FakeResponse();
          await handler({{
            query: {{}},
            headers: {{ host: "yourportfolio.work", "x-forwarded-proto": "https" }},
          }}, res);
          assert.equal(res.statusCode, 200);
          assert.equal(res.payload.active_count, 1);
          assert.equal(res.payload.portfolios[0].portfolio_url, "https://yourportfolio.work/riya");
          assert.equal(Object.hasOwn(res.payload.portfolios[0], "html_content"), false);
        }}

        run().catch((error) => {{
          console.error(error);
          process.exit(1);
        }});
        """
    )

    subprocess.run([node, "-e", script], check=True)
