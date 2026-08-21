# The backend's MCP CLIENT.
#
# This is the boundary that makes the project real MCP: the backend does NOT
# import mcp_server's Python functions. It launches mcp_server/server.py as a
# separate process and talks to it over the MCP protocol (JSON-RPC on stdio),
# exactly like Claude Desktop or any other MCP client would.
#
# Swap this file for a client pointing at someone else's MCP server and the
# rest of the backend keeps working — that's the reusability MCP buys.

import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,  # the same venv python running the backend
    args=["-m", "mcp_server.server"],
)


class MCPConnection:
    """Keeps one long-lived MCP session open for the lifetime of the FastAPI app."""

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None

    async def connect(self) -> None:
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(SERVER_PARAMS))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()  # the MCP handshake

    async def close(self) -> None:
        if self._stack:
            await self._stack.aclose()
        self._stack = None
        self.session = None

    async def list_tools(self) -> list[dict]:
        """Ask the server what it can do — pure MCP discovery."""
        result = await self.session.list_tools()
        return [
            {"name": t.name, "description": t.description, "schema": t.input_schema}
            for t in result.tools
        ]

    async def call(self, tool_name: str, arguments: dict) -> str:
        """Call one MCP tool and return its text result."""
        result = await self.session.call_tool(tool_name, arguments)
        return "\n".join(c.text for c in result.content if hasattr(c, "text"))


# Single shared connection, wired up by FastAPI's lifespan in main.py.
connection = MCPConnection()
