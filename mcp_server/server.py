# Entry point for the GitHub Codebase Analyst MCP server.
#
# MCPServer is the high-level part of the MCP Python SDK: it handles the
# protocol plumbing (JSON-RPC framing, capability negotiation, schema
# generation from type hints) so tool code only has to be a decorated
# Python function. Running this module spawns a server that speaks MCP
# over stdio — the same transport Claude Desktop/Code use to launch
# local MCP servers, and what backend/mcp_client.py uses in Part 3.

from mcp.server.mcpserver import MCPServer

from mcp_server.tools import analysis, github_core

mcp = MCPServer("strata-codebase-intelligence")

github_core.register(mcp)  # 5 raw-data tools
analysis.register(mcp)  # 5 LLM-backed reasoning tools

if __name__ == "__main__":
    mcp.run()  # defaults to stdio transport
