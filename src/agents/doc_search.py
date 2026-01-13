"""
Doc Search Agent - Searches the web for programming documentation.
Uses Tavily API to find relevant documentation, tutorials, and explanations.
"""
from typing import TypedDict, Annotated, Sequence
import operator
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.tools.tavily_search import (
    search_documentation,
    search_oracle_docs,
    search_python_docs,
    get_documentation_context
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
class DocSearchState(TypedDict):
    """State for the Doc Search Agent."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    query: str
    results: str


# System prompt for the agent
DOC_SEARCH_SYSTEM_PROMPT = """You are a Documentation Search Agent specialized in finding programming documentation and tutorials.

Your role:
1. Understand what documentation the user needs
2. Use your search tools to find relevant documentation
3. Summarize and present the most useful information

Available tools:
- search_documentation: General documentation search across programming sites
- search_oracle_docs: Search specifically for Oracle database documentation
- search_python_docs: Search specifically for Python documentation
- get_documentation_context: Get comprehensive context for a topic

Guidelines:
- Choose the most appropriate search tool based on the query
- For Oracle-specific queries, use search_oracle_docs
- For Python-specific queries, use search_python_docs
- For general queries, use search_documentation
- Summarize key points from search results
- Include relevant URLs for further reading
- Be concise but thorough in explanations

Focus areas:
- Official documentation
- Tutorials and how-to guides
- Best practices
- Common patterns and idioms
"""


def create_doc_search_agent():
    """Create and return the Doc Search Agent graph."""

    # Initialize LLM with tools - use max_tokens to speed up responses
    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=2048  # Limit response size for faster generation
    )

    tools = [
        search_documentation,
        search_oracle_docs,
        search_python_docs,
        get_documentation_context
    ]

    llm_with_tools = llm.bind_tools(tools)

    # Define nodes
    def agent_node(state: DocSearchState) -> DocSearchState:
        """Main agent reasoning node."""
        with tracer.start_as_current_span("doc_search_agent_reasoning") as span:
            span.set_attribute("agent.name", "doc_search")

            messages = state["messages"]

            # Add system message if not present
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=DOC_SEARCH_SYSTEM_PROMPT)] + list(messages)

            response = llm_with_tools.invoke(messages)

            span.set_attribute("agent.has_tool_calls", bool(response.tool_calls))

            return {"messages": [response]}

    def should_continue(state: DocSearchState) -> str:
        """Determine if agent should continue or end."""
        messages = state["messages"]
        last_message = messages[-1]

        # If there are tool calls, continue to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Otherwise, end
        return "end"

    def format_results(state: DocSearchState) -> DocSearchState:
        """Format the final results."""
        with tracer.start_as_current_span("format_doc_results"):
            messages = state["messages"]
            last_message = messages[-1]

            # Extract content from last AI message
            if isinstance(last_message, AIMessage):
                return {"results": last_message.content}

            return {"results": "No documentation found."}

    # Create tool node
    tool_node = ToolNode(tools)

    # Build the graph
    workflow = StateGraph(DocSearchState)

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


def get_doc_search_agent():
    """Get cached Doc Search Agent (created once, reused)."""
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = create_doc_search_agent()
    return _cached_agent


# Convenience function for direct invocation
def search_docs(query: str) -> str:
    """
    Search for documentation using the Doc Search Agent.

    Args:
        query: Natural language query about documentation

    Returns:
        Formatted response with relevant documentation
    """
    with tracer.start_as_current_span("doc_search_agent_invoke") as span:
        span.set_attribute("query", query)

        # Use cached agent instead of creating new one each time
        agent = get_doc_search_agent()

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
        "How do I use connection pooling with Oracle database?",
        "What are best practices for Python error handling?",
        "Explain LangChain agents and how to use them",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        result = search_docs(query)
        print(result[:2000])  # Truncate for readability
