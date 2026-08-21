# Strata — Codebase Intelligence

Strata is a **real MCP server** that exposes GitHub repository search and AI codebase analysis
as 10 reusable tools — plus a FastAPI backend and web UI that consume it as an
**MCP client**.

The point is not "a web app that calls GitHub". The point is that the analysis
capability lives behind the Model Context Protocol, so the *same server* can be
used by this app, by Claude Desktop, by Claude Code, or by any other MCP client.

```
Web UI  →  FastAPI backend  →  [MCP protocol / JSON-RPC over stdio]  →  MCP server
                                                                          ├→ GitHub API
                                                                          └→ OpenRouter LLM
```

## The 10 MCP tools

**Core (raw GitHub data — no LLM):**
| Tool | Does |
|---|---|
| `search_repositories` | Search public repos |
| `get_repo_info` | Stars, forks, license, topics |
| `list_repo_files` | List one folder level |
| `read_repo_file` | Read one file's text |
| `get_repo_languages` | Language byte breakdown |

**Analysis (GitHub data + LLM reasoning):**
| Tool | Does |
|---|---|
| `analyze_architecture` | What it does, stack, structure, components |
| `analyze_dependencies` | Deps, pinning, supply-chain concerns |
| `analyze_code_flow` | Entry points, how components call each other |
| `detect_potential_issues` | Potential bugs/security/ops findings |
| `generate_report` | One full engineering report |

> `detect_potential_issues` is deliberately prompted to report **potential findings
> requiring verification**, with a confidence level and the evidence it saw — never
> "this repo IS vulnerable".

## Setup

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

- **`GITHUB_TOKEN`** — strongly recommended. Without it GitHub allows only
  **60 requests/hour**, and one analysis uses ~5–20. With a token it's 5000/hour.
  A classic token with no scopes ticked is enough for public repos.
- **`OPENROUTER_API_KEY`** — required for the 5 analysis tools.
- **`OPENROUTER_MODEL`** — defaults to a `:free` model. Free models are shared and
  frequently rate-limited (HTTP 429); adding OpenRouter credit and switching to
  e.g. `anthropic/claude-sonnet-5` gives far better and more reliable analysis.

## Run

```bash
.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8055
```

Open http://127.0.0.1:8055

## Test

Talk to the MCP server as a real MCP client (spawns it as a subprocess, does the
handshake, lists and calls tools):

```bash
.venv\Scripts\python.exe tests\test_mcp_tools.py
```

End-to-end analysis through MCP → GitHub → LLM:

```bash
.venv\Scripts\python.exe tests\test_analysis.py
```

## Use it from Claude Desktop / Claude Code

This is the payoff — the same server, no code changes:

```json
{
  "mcpServers": {
    "strata": {
      "command": "D:\\Github2\\MCP\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:\\Github2\\MCP"
    }
  }
}
```

## Structure

```
mcp_server/            THE REUSABLE PART (the MCP server)
  server.py            Creates MCPServer, registers all 10 tools, runs on stdio
  config.py            Loads .env
  github_client.py     GitHub REST wrapper (no MCP concepts here)
  llm_client.py        OpenRouter wrapper
  tools/
    github_core.py     The 5 data tools
    analysis.py        The 5 LLM tools + repo-context gathering
backend/               AN MCP CLIENT (one consumer of the server)
  mcp_client.py        Spawns the server, keeps one MCP session open
  main.py              FastAPI routes → MCP tool calls
frontend/
  index.html           Strata UI (glass/dark, live MCP activity panel)
  config.js            Backend URL for split (Vercel) deploys
tests/                 Real MCP client tests
```

## Concepts this project separates

| Term | Meaning here |
|---|---|
| **API** | A service you call — GitHub API, OpenRouter API |
| **Tool calling** | An LLM picking which function to run from a schema |
| **Agent** | Multi-step autonomous loop: plan → call → observe → repeat |
| **MCP** | The *standard* that exposes tools so any client can discover and call them |

## Deploying

See [DEPLOY.md](DEPLOY.md). Short version: the UI goes to **Vercel** (static), and the
backend + MCP server go to a host that allows a persistent process (Render/Railway/Fly),
because the backend keeps a long-lived MCP subprocess open and streams 30–90s analyses.
