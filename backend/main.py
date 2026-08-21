# FastAPI backend. It owns NO GitHub or LLM logic — all of that lives behind
# MCP tools. This file only translates HTTP requests into MCP tool calls.

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.mcp_client import connection

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Only these MCP tools may be triggered from the web UI.
ANALYSIS_TOOLS = {
    "analyze_architecture",
    "analyze_dependencies",
    "analyze_code_flow",
    "detect_potential_issues",
    "generate_report",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spawn the MCP server process once at startup, shut it down at exit.
    await connection.connect()
    yield
    await connection.close()


app = FastAPI(title="Strata — Codebase Intelligence", lifespan=lifespan)

# Allows the UI to be hosted separately (e.g. on Vercel) from this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class AnalyzeRequest(BaseModel):
    owner: str
    repo: str
    tool: str
    focus: str = ""


@app.get("/api/tools")
async def list_tools():
    """Show what the MCP server advertises — this is MCP discovery, over HTTP."""
    return {"tools": await connection.list_tools()}


@app.post("/api/search")
async def search(req: SearchRequest):
    text = await connection.call(
        "search_repositories", {"query": req.query, "limit": req.limit}
    )
    return {"result": text}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if req.tool not in ANALYSIS_TOOLS:
        raise HTTPException(400, f"Unknown analysis tool: {req.tool}")

    args = {"owner": req.owner, "repo": req.repo}
    if req.tool == "analyze_code_flow" and req.focus:
        args["focus"] = req.focus

    try:
        text = await connection.call(req.tool, args)
    except Exception as e:
        raise HTTPException(500, f"MCP tool failed: {e}")
    return {"result": text}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/analyze/stream")
async def analyze_stream(owner: str, repo: str, tool: str, focus: str = ""):
    """Run a pipeline of MCP tools, streaming each tool's real status as it runs.

    This is what powers the UI's MCP activity panel — every line it shows
    corresponds to an actual call_tool() over the MCP protocol, not a mock.
    """
    if tool not in ANALYSIS_TOOLS:
        raise HTTPException(400, f"Unknown analysis tool: {tool}")

    base = {"owner": owner, "repo": repo}
    analysis_args = dict(base)
    if tool == "analyze_code_flow" and focus:
        analysis_args["focus"] = focus

    # (tool name, arguments, label shown in the UI, is this the final payload?)
    pipeline = [
        ("get_repo_info", base, "Reading repository metadata", False),
        ("get_repo_languages", base, "Detecting languages", False),
        ("list_repo_files", base, "Listing repository structure", False),
        (tool, analysis_args, "Running AI analysis", True),
    ]

    async def gen():
        for name, args, label, is_final in pipeline:
            yield _sse("tool", {"name": name, "status": "running", "label": label})
            try:
                text = await connection.call(name, args)
            except Exception as e:
                yield _sse("tool", {"name": name, "status": "error", "label": label})
                yield _sse("error", {"message": str(e), "tool": name})
                return
            yield _sse(
                "tool",
                {
                    "name": name,
                    "status": "done",
                    "label": label,
                    "result": text if not is_final else None,
                },
            )
            if is_final:
                yield _sse("result", {"tool": name, "text": text})
        yield _sse("done", {})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
