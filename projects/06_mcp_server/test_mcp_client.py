import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(Path(__file__).resolve().parent / "pg_ai_mcp_server.py")


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_SCRIPT],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List all tools exposed by PG-AI MCP Server
            tools = await session.list_tools()
            print("[🔌] Connected to PG-AI MCP Server. Discovered tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")

            # 2. Test calling search_cloudops_runbooks
            print("\n[🔎] Calling tool: search_cloudops_runbooks...")
            res = await session.call_tool(
                "search_cloudops_runbooks",
                arguments={"query": "promtail duplicate action key"},
            )
            print(res.content[0].text)

            # 3. Test calling lint_iam_policy
            print("\n[🔐] Calling tool: lint_iam_policy...")
            bad_policy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:*","Resource":"*"}]}'
            lint_res = await session.call_tool(
                "lint_iam_policy",
                arguments={"policy_json": bad_policy},
            )
            print(lint_res.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())