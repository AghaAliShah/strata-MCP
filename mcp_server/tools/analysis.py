# The 5 analysis MCP tools. These combine GitHub data + an LLM (via OpenRouter).
#
# Pattern used by every tool here:
#   1. _gather_context() pulls real facts out of GitHub (metadata, tree, key files)
#   2. that context is pasted into a prompt
#   3. the LLM reasons over it and writes the analysis
#
# The LLM never guesses about the repo — it only sees real fetched data.

from mcp.server.mcpserver import MCPServer

from mcp_server import github_client, llm_client

# Files worth reading automatically: they reveal stack, deps, entry points, deployment.
KEY_FILES = [
    "README.md",
    "readme.md",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
]

MAX_TREE_ENTRIES = 300  # keep the prompt a sane size on huge repos
MAX_FILE_CHARS = 6000  # truncate any single file

# Big repos are often mostly docs/translations/assets. If we just take the first
# 300 paths we can end up showing zero source code, so low-signal paths are
# pushed to the back of the list and trimmed first.
LOW_SIGNAL_PREFIXES = ("docs/", "doc/", "website/", "examples/", "locale/", "i18n/", "translations/")
LOW_SIGNAL_SUFFIXES = (".md", ".rst", ".txt", ".po", ".svg", ".png", ".jpg", ".gif", ".ico", ".lock")


def _signal_rank(path: str) -> int:
    """0 = likely source code, 1 = supporting, 2 = docs/assets. Lower sorts first."""
    lower = path.lower()
    if lower.startswith(LOW_SIGNAL_PREFIXES):
        return 2
    if lower.endswith(LOW_SIGNAL_SUFFIXES):
        return 1
    return 0


def _sample_tree(files: list[dict]) -> list[dict]:
    """Pick a representative sample of the tree, not just the alphabetical first N.

    Files are grouped by top-level directory and taken round-robin, so one huge
    folder (docs, .github, generated code) can't crowd out the real source
    package. Within each folder, source-looking files come first.
    """
    groups: dict[str, list[dict]] = {}
    for f in files:
        top = f["path"].split("/")[0] if "/" in f["path"] else "<root>"
        groups.setdefault(top, []).append(f)

    for items in groups.values():
        items.sort(key=lambda f: (_signal_rank(f["path"]), f["path"]))

    # Root files and shallow dirs first, then round-robin across all groups.
    order = sorted(groups, key=lambda k: (k != "<root>", k))
    picked: list[dict] = []
    i = 0
    while len(picked) < MAX_TREE_ENTRIES:
        added = False
        for key in order:
            if i < len(groups[key]):
                picked.append(groups[key][i])
                added = True
                if len(picked) >= MAX_TREE_ENTRIES:
                    break
        if not added:  # every group exhausted
            break
        i += 1

    picked.sort(key=lambda f: f["path"])
    return picked


async def _gather_context(owner: str, repo: str) -> str:
    """Fetch a factual snapshot of the repo and format it as prompt text."""
    info = await github_client.get_repo(owner, repo)
    languages = await github_client.get_languages(owner, repo)
    tree = await github_client.get_tree(owner, repo, info["default_branch"])

    files = [t for t in tree if t["type"] == "blob"]
    paths = {f["path"] for f in files}

    parts = [
        f"# REPOSITORY: {info['full_name']}",
        f"Description: {info.get('description')}",
        f"Stars: {info['stargazers_count']} | Forks: {info['forks_count']} "
        f"| Open issues: {info['open_issues_count']}",
        f"License: {(info.get('license') or {}).get('name')}",
        f"Topics: {', '.join(info.get('topics', [])) or 'none'}",
        "",
        f"# LANGUAGES (bytes): {languages}",
        "",
    ]

    shown = _sample_tree(files)
    omitted = len(files) - len(shown)
    header = f"# FILE TREE ({len(files)} files total"
    if omitted:
        header += f"; showing {len(shown)}, {omitted} omitted — source files prioritised over docs/assets"
    parts.append(header + ")")
    parts += [f"  {f['path']}" for f in shown]

    # Read whichever key files actually exist in this repo.
    parts.append("\n# KEY FILE CONTENTS")
    for name in KEY_FILES:
        if name not in paths:
            continue
        try:
            content = await github_client.get_file_content(owner, repo, name)
        except Exception as e:  # missing/binary/too-large — skip, don't fail the tool
            parts.append(f"\n--- {name} --- (could not read: {e})")
            continue
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + "\n...[truncated]..."
        parts.append(f"\n--- {name} ---\n{content}")

    return "\n".join(parts)


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def analyze_architecture(owner: str, repo: str) -> str:
        """Explain what a repository does, its tech stack, folder structure, and architecture.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
        """
        context = await _gather_context(owner, repo)
        return await llm_client.ask(
            system_prompt=(
                "You are a senior software architect reviewing an unfamiliar codebase. "
                "Base every statement strictly on the provided data. If something is not "
                "visible in the data, say so rather than guessing."
            ),
            user_prompt=(
                f"{context}\n\n"
                "Write an architecture analysis with these sections:\n"
                "1. What this project does (plain language)\n"
                "2. Technology stack\n"
                "3. Folder/file structure and what each main area is for\n"
                "4. Architecture and main components\n"
                "5. How a request/data flows through the system"
            ),
        )

    @mcp.tool()
    async def analyze_dependencies(owner: str, repo: str) -> str:
        """Analyze a repository's dependencies: what they are, why they're there, and their risks.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
        """
        context = await _gather_context(owner, repo)
        return await llm_client.ask(
            system_prompt=(
                "You are a software supply-chain analyst. Base every statement strictly "
                "on the provided manifest files. Do not invent dependencies."
            ),
            user_prompt=(
                f"{context}\n\n"
                "Analyze the dependencies:\n"
                "1. Direct dependencies and what each is used for\n"
                "2. Whether versions are pinned, loose, or unspecified\n"
                "3. Heavy or unusual dependencies worth noting\n"
                "4. Supply-chain / maintenance concerns (clearly marked as needing verification)\n"
                "If no dependency manifest is present, say that plainly."
            ),
        )

    @mcp.tool()
    async def analyze_code_flow(owner: str, repo: str, focus: str = "") -> str:
        """Trace how important components in a repository work together.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
            focus: Optional area to focus on, e.g. "authentication" or "the API layer".
        """
        context = await _gather_context(owner, repo)
        focus_line = f"Focus specifically on: {focus}\n" if focus else ""
        return await llm_client.ask(
            system_prompt=(
                "You are a senior engineer onboarding onto a codebase. Trace control and "
                "data flow using only the provided file tree and file contents. Where you "
                "must infer, label it clearly as an inference."
            ),
            user_prompt=(
                f"{context}\n\n{focus_line}"
                "Trace the code flow:\n"
                "1. Entry points (how the program starts)\n"
                "2. The most important components and their responsibilities\n"
                "3. How those components call each other, step by step\n"
                "4. Where data enters, gets transformed, and exits\n"
                "5. Which files a new contributor should read first, in order"
            ),
        )

    @mcp.tool()
    async def detect_potential_issues(owner: str, repo: str) -> str:
        """Find POTENTIAL engineering, security, and operational issues needing verification.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
        """
        context = await _gather_context(owner, repo)
        return await llm_client.ask(
            system_prompt=(
                "You are a code reviewer producing a findings list. CRITICAL RULE: every "
                "item you report is a POTENTIAL issue requiring human verification, never a "
                "confirmed vulnerability. Never claim a repository IS vulnerable. Use "
                "phrasing like 'appears to', 'may', 'worth verifying'. For each finding give "
                "a confidence level (Low/Medium/High) and say exactly what evidence you saw. "
                "If you have no evidence for a category, say 'nothing observable in the data provided'."
            ),
            user_prompt=(
                f"{context}\n\n"
                "List POTENTIAL issues requiring verification, grouped as:\n"
                "1. Possible bugs / design weaknesses\n"
                "2. Possible security concerns\n"
                "3. Operational / deployment concerns\n"
                "4. Missing tests (based on the file tree)\n"
                "5. Missing or thin documentation\n\n"
                "Format each finding as:\n"
                "- [Confidence: Low/Medium/High] <finding>\n"
                "  Evidence: <what in the data suggests this>\n"
                "  To verify: <what a human should check>"
            ),
        )

    @mcp.tool()
    async def generate_report(owner: str, repo: str) -> str:
        """Produce a single complete engineering report covering everything about a repository.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
        """
        context = await _gather_context(owner, repo)
        return await llm_client.ask(
            system_prompt=(
                "You are a principal engineer writing a codebase assessment report for a "
                "team that has never seen this project. Base everything on the provided "
                "data. Any issue you raise must be framed as a potential finding requiring "
                "verification, never as a confirmed defect or vulnerability."
            ),
            user_prompt=(
                f"{context}\n\n"
                "Write a complete engineering report in Markdown:\n\n"
                "## Executive Summary\n"
                "## What This Project Does\n"
                "## Technology Stack\n"
                "## Folder & File Structure\n"
                "## Architecture & Key Components\n"
                "## Data & Control Flow\n"
                "## Dependencies\n"
                "## Potential Issues (Require Verification)\n"
                "   (bugs, design weaknesses, security, operational/deployment)\n"
                "## Testing & Documentation Gaps\n"
                "## Recommendations\n"
            ),
            max_tokens=4000,
        )
