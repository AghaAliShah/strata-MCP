# A real MCP CLIENT that spawns mcp_server/server.py as a subprocess and
# talks the MCP protocol to it over stdio. This proves the server is a
# genuine MCP server (list_tools / call_tool over JSON-RPC), not just a
# Python module with functions we happen to import.
#
# Run from the MCP/ project root:
#   .venv\Scripts\python.exe tests\test_mcp_tools.py

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mcp_server.server"],
)


async def main() -> None:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools exposed by the server:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            print("\nCalling get_repo_info(owner='anthropics', repo='claude-code')...")
            result = await session.call_tool(
                "get_repo_info", {"owner": "anthropics", "repo": "claude-code"}
            )
            print(result.content[0].text)

            print("\nCalling search_repositories(query='mcp server python', limit=3)...")
            result = await session.call_tool(
                "search_repositories", {"query": "mcp server python", "limit": 3}
            )
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
