# The 5 core GitHub MCP tools. `register()` attaches them to a FastMCP instance.
# Each function's type hints + docstring become the JSON schema an MCP client
# sees when it calls list_tools() — that schema is how the LLM on the other
# end knows what arguments to pass and what the tool does.

from mcp.server.mcpserver import MCPServer

from mcp_server import github_client


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def search_repositories(query: str, limit: int = 10) -> list[dict]:
        """Search public GitHub repositories.

        Args:
            query: GitHub search syntax, e.g. "language:python stars:>1000 rag".
            limit: Max number of repos to return (default 10).
        """
        items = await github_client.search_repositories(query, limit)
        return [
            {
                "full_name": r["full_name"],
                "description": r.get("description"),
                "stars": r["stargazers_count"],
                "language": r.get("language"),
                "url": r["html_url"],
            }
            for r in items
        ]

    @mcp.tool()
    async def get_repo_info(owner: str, repo: str) -> dict:
        """Get metadata for a single repository: description, stars, forks, topics, license.

        Args:
            owner: Repository owner/org, e.g. "anthropics".
            repo: Repository name, e.g. "claude-code".
        """
        data = await github_client.get_repo(owner, repo)
        return {
            "full_name": data["full_name"],
            "description": data.get("description"),
            "stars": data["stargazers_count"],
            "forks": data["forks_count"],
            "open_issues": data["open_issues_count"],
            "default_branch": data["default_branch"],
            "topics": data.get("topics", []),
            "license": (data.get("license") or {}).get("name"),
            "url": data["html_url"],
        }

    @mcp.tool()
    async def list_repo_files(owner: str, repo: str, path: str = "") -> list[dict]:
        """List files and folders at a path in a repository (one level, non-recursive).

        Args:
            owner: Repository owner/org.
            repo: Repository name.
            path: Path within the repo; empty string lists the repo root.
        """
        items = await github_client.list_contents(owner, repo, path)
        return [
            {"name": i["name"], "path": i["path"], "type": i["type"], "size": i.get("size", 0)}
            for i in items
        ]

    @mcp.tool()
    async def read_repo_file(owner: str, repo: str, path: str) -> str:
        """Read the text content of a single file in a repository.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
            path: File path within the repo, e.g. "src/main.py".
        """
        return await github_client.get_file_content(owner, repo, path)

    @mcp.tool()
    async def get_repo_languages(owner: str, repo: str) -> dict:
        """Get the language breakdown (bytes of code per language) for a repository.

        Args:
            owner: Repository owner/org.
            repo: Repository name.
        """
        return await github_client.get_languages(owner, repo)
