"""
Code Query Agent - Searches Oracle database for code snippets.
Uses Oracle SQLcl MCP tools to query the code_snippets table.
"""
from typing import TypedDict, Annotated, Sequence
import operator
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.tools.oracle_mcp import (
    search_code_snippets,
    get_snippet_by_id,
    list_available_categories,
    list_available_languages
)
from src.config import settings

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


# Agent State
class CodeQueryState(TypedDict):
    """State for the Code Query Agent."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    query: str
    results: str


# System prompt for the agent
CODE_QUERY_SYSTEM_PROMPT = """You are a Code Query Agent specialized in finding relevant code snippets from a database.

Your role:
1. Understand what kind of code the user is looking for
2. Use your tools to search the code snippets database
3. Return the most relevant code examples with explanations

Available tools:
- search_code_snippets: Search by language, category, framework, or keyword
- get_snippet_by_id: Get a specific snippet by ID
- list_available_categories: See what categories exist
- list_available_languages: See what languages are available

Guidelines:
- Always search for relevant snippets based on the query
- If multiple results, pick the most relevant ones
- Include the full code in your response
- Explain what the code does briefly
- If no results found, say so clearly

Database categories: database, api, ai, auth, data, testing
Languages: python (primary), sql, java
"""


def create_code_query_agent():
    """Create and return the Code Query Agent graph."""

    # Initialize LLM with tools - use max_tokens to speed up responses
    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=2048  # Limit response size for faster generation
    )

    tools = [
        search_code_snippets,
        get_snippet_by_id,
        list_available_categories,
        list_available_languages
    ]

    llm_with_tools = llm.bind_tools(tools)

    # Define nodes
    def agent_node(state: CodeQueryState) -> CodeQueryState:
        """Main agent reasoning node."""
        with tracer.start_as_current_span("code_query_agent_reasoning") as span:
            span.set_attribute("agent.name", "code_query")

            messages = state["messages"]

            # Add system message if not present
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=CODE_QUERY_SYSTEM_PROMPT)] + list(messages)

            response = llm_with_tools.invoke(messages)

            span.set_attribute("agent.has_tool_calls", bool(response.tool_calls))

            return {"messages": [response]}

    def should_continue(state: CodeQueryState) -> str:
        """Determine if agent should continue or end."""
        messages = state["messages"]
        last_message = messages[-1]

        # If there are tool calls, continue to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Otherwise, end
        return "end"

    def format_results(state: CodeQueryState) -> CodeQueryState:
        """Format the final results."""
        with tracer.start_as_current_span("format_code_results"):
            messages = state["messages"]
            last_message = messages[-1]

            # Extract content from last AI message
            if isinstance(last_message, AIMessage):
                return {"results": last_message.content}

            return {"results": "No code snippets found."}

    # Create tool node
    tool_node = ToolNode(tools)

    # Build the graph
    workflow = StateGraph(CodeQueryState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("format", format_results)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": "format"
        }
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("format", END)

    return workflow.compile()


# Cache the compiled agent for reuse
_cached_agent = None


def get_code_query_agent():
    """Get cached Code Query Agent (created once, reused)."""
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = create_code_query_agent()
    return _cached_agent


# Convenience function for direct invocation
def query_code_snippets(query: str) -> str:
    """
    Query code snippets using the Code Query Agent.

    Args:
        query: Natural language query about code

    Returns:
        Formatted response with relevant code snippets
    """
    with tracer.start_as_current_span("code_query_agent_invoke") as span:
        span.set_attribute("query", query)

        # Use cached agent instead of creating new one each time
        agent = get_code_query_agent()

        result = agent.invoke({
            "messages": [HumanMessage(content=query)],
            "query": query,
            "results": ""
        })

        span.set_attribute("result_length", len(result.get("results", "")))

        return result.get("results", "No results found.")


# For testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Test queries
    test_queries = [
        "Show me how to connect to Oracle database in Python",
        "Find code examples for FastAPI endpoints",
        "What LangChain examples do you have?",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        result = query_code_snippets(query)
        print(result)
