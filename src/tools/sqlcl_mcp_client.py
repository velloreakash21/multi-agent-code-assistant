"""
SQLcl MCP Client - Connects to Oracle SQLcl MCP Server.

Uses the MCP SDK with SSE transport to communicate with the
SQLcl MCP server running in Docker.

SQLcl MCP Server Tools:
- list-connections: Get available database connections
- connect: Establish connection to a database
- run-sql: Execute SQL queries
- run-sqlcl: Execute SQLcl commands
- disconnect: Close database connection
"""
import asyncio
import json
import os
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

# Import tracer with graceful fallback
try:
    from src.telemetry import get_tracer
    tracer = get_tracer(__name__)
except ImportError:
    from contextlib import contextmanager
    class NoOpTracer:
        @contextmanager
        def start_as_current_span(self, name, **kwargs):
            class NoOpSpan:
                def set_attribute(self, k, v): pass
            yield NoOpSpan()
    tracer = NoOpTracer()

# Try to import MCP SDK
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("Warning: MCP SDK not available. Install with: pip install mcp")


class SQLclMCPClient:
    """
    Client for connecting to SQLcl MCP Server via SSE transport.

    The SQLcl MCP server runs in Docker and exposes an SSE endpoint
    that this client connects to for executing database operations.
    """

    def __init__(self, host: str = "localhost", port: int = 8080):
        """
        Initialize the SQLcl MCP client.

        Args:
            host: SQLcl MCP server hostname
            port: SQLcl MCP server port
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._connected = False

    @property
    def is_available(self) -> bool:
        """Check if MCP SDK is available."""
        return MCP_AVAILABLE

    @asynccontextmanager
    async def get_session(self):
        """
        Get an MCP session via SSE transport.

        Yields:
            ClientSession connected to SQLcl MCP server
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP SDK not installed")

        async with sse_client(self.base_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> List[str]:
        """
        List available tools from SQLcl MCP server.

        Returns:
            List of tool names
        """
        with tracer.start_as_current_span("sqlcl_mcp.list_tools") as span:
            try:
                async with self.get_session() as session:
                    tools = await session.list_tools()
                    tool_names = [t.name for t in tools.tools]
                    span.set_attribute("mcp.tools_count", len(tool_names))
                    return tool_names
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                return []

    async def connect_to_database(self, connection_name: str = None) -> Dict[str, Any]:
        """
        Connect to the database via SQLcl MCP.

        Args:
            connection_name: Named connection to use (optional)

        Returns:
            Dict with connection result
        """
        with tracer.start_as_current_span("sqlcl_mcp.connect") as span:
            span.set_attribute("mcp.server", "sqlcl")
            span.set_attribute("mcp.tool", "connect")

            try:
                async with self.get_session() as session:
                    # Build connection arguments
                    args = {}
                    if connection_name:
                        args["connection_name"] = connection_name
                    else:
                        # Use environment variables for connection
                        args["username"] = os.getenv("ORACLE_USER", "codeassist")
                        args["password"] = os.getenv("ORACLE_PASSWORD", "CodeAssist123")
                        args["connect_string"] = (
                            f"{os.getenv('ORACLE_HOST', 'localhost')}:"
                            f"{os.getenv('ORACLE_PORT', '1521')}/"
                            f"{os.getenv('ORACLE_SERVICE', 'FREEPDB1')}"
                        )

                    result = await session.call_tool("connect", args)
                    self._connected = True
                    return {"success": True, "data": result}

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                return {"success": False, "error": str(e)}

    async def execute_sql(self, query: str, params: dict = None) -> Dict[str, Any]:
        """
        Execute SQL via SQLcl MCP Server.

        This method:
        1. Connects to the database (if not connected)
        2. Executes the SQL query using run-sql tool
        3. Returns results

        Args:
            query: SQL query to execute
            params: Optional bind parameters (will be substituted into query)

        Returns:
            Dict with 'success', 'data' or 'error' keys
        """
        with tracer.start_as_current_span("sqlcl_mcp.execute") as span:
            span.set_attribute("db.system", "oracle")
            span.set_attribute("db.statement", query[:500])
            span.set_attribute("mcp.server", "sqlcl")

            try:
                # Substitute parameters into query if provided
                # MCP doesn't support bind parameters directly
                final_query = self._substitute_params(query, params)

                async with self.get_session() as session:
                    # Step 1: Connect to database
                    with tracer.start_as_current_span("sqlcl_mcp.connect") as conn_span:
                        conn_span.set_attribute("mcp.tool", "connect")
                        connect_args = {
                            "username": os.getenv("ORACLE_USER", "codeassist"),
                            "password": os.getenv("ORACLE_PASSWORD", "CodeAssist123"),
                            "connect_string": (
                                f"{os.getenv('ORACLE_HOST', 'oracle-db')}:"
                                f"{os.getenv('ORACLE_PORT', '1521')}/"
                                f"{os.getenv('ORACLE_SERVICE', 'FREEPDB1')}"
                            )
                        }
                        await session.call_tool("connect", connect_args)

                    # Step 2: Execute SQL
                    with tracer.start_as_current_span("sqlcl_mcp.run-sql") as sql_span:
                        sql_span.set_attribute("mcp.tool", "run-sql")
                        sql_span.set_attribute("db.statement", final_query[:500])

                        result = await session.call_tool("run-sql", {"sql": final_query})

                        # Parse result
                        data = self._parse_result(result)

                        if isinstance(data, list):
                            span.set_attribute("db.rows_affected", len(data))
                            sql_span.set_attribute("db.rows_affected", len(data))

                        return {"success": True, "data": data}

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                return {"success": False, "error": str(e)}

    def _substitute_params(self, query: str, params: dict) -> str:
        """
        Substitute bind parameters into query.

        Args:
            query: SQL query with :param placeholders
            params: Dict of parameter values

        Returns:
            Query with parameters substituted
        """
        if not params:
            return query

        result = query
        for key, value in params.items():
            placeholder = f":{key}"
            if isinstance(value, str):
                # Escape single quotes for SQL strings
                safe_value = value.replace("'", "''")
                result = result.replace(placeholder, f"'{safe_value}'")
            elif value is None:
                result = result.replace(placeholder, "NULL")
            else:
                result = result.replace(placeholder, str(value))
        return result

    def _parse_result(self, result) -> Any:
        """
        Parse MCP tool result into usable data.

        Args:
            result: Raw MCP tool result

        Returns:
            Parsed data (usually list of dicts for SELECT queries)
        """
        # MCP results come in various formats depending on the tool
        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                # Check if it's text content
                first_item = content[0]
                if hasattr(first_item, 'text'):
                    text = first_item.text
                    # Try to parse as JSON
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
                return content
            return content

        if isinstance(result, dict):
            return result.get("data", result)

        return result


# Singleton instance
_mcp_client: Optional[SQLclMCPClient] = None


def get_mcp_client(host: str = None, port: int = None) -> SQLclMCPClient:
    """
    Get or create the SQLcl MCP client singleton.

    Args:
        host: Override default host
        port: Override default port

    Returns:
        SQLclMCPClient instance
    """
    global _mcp_client

    # Import settings
    try:
        from src.config import settings
        default_host = settings.sqlcl_mcp_host
        default_port = settings.sqlcl_mcp_port
    except ImportError:
        default_host = "localhost"
        default_port = 8080

    actual_host = host or default_host
    actual_port = port or default_port

    if _mcp_client is None or _mcp_client.host != actual_host or _mcp_client.port != actual_port:
        _mcp_client = SQLclMCPClient(host=actual_host, port=actual_port)

    return _mcp_client


def run_async(coro):
    """
    Helper to run async code in sync context.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running (e.g., in Jupyter), use nest_asyncio or create task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(coro)


__all__ = [
    "SQLclMCPClient",
    "get_mcp_client",
    "run_async",
    "MCP_AVAILABLE"
]
