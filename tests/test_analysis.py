# Calls one LLM-backed analysis tool over MCP, end to end:
# MCP client -> MCP server -> GitHub API -> OpenRouter -> back.
#
#   .venv\Scripts\python.exe tests\test_analysis.py

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])


async def main() -> None:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Running analyze_architecture on tiangolo/fastapi ...\n")
            result = await session.call_tool(
                "analyze_architecture", {"owner": "tiangolo", "repo": "fastapi"}
            )
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
