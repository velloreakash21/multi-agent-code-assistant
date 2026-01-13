"""
Orchestrator Agent - Coordinates between Doc Search and Code Query agents.
Routes queries and combines results for comprehensive answers.
"""
from typing import TypedDict, Annotated, Sequence, Literal
import operator
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from src.agents.doc_search import search_docs
from src.agents.code_query import query_code_snippets
from src.config import settings

# Import OpenTelemetry context for thread propagation
try:
    from opentelemetry import context as otel_context
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

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


# Orchestrator State
class OrchestratorState(TypedDict):
    """State for the Orchestrator Agent."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    query: str
    doc_results: str
    code_results: str
    final_response: str
    agents_to_call: list[str]


# System prompt for orchestrator
ORCHESTRATOR_SYSTEM_PROMPT = """You are an Orchestrator Agent that helps developers find information and code examples.

You coordinate two specialized agents:
1. **Doc Search Agent**: Searches web for documentation, tutorials, and explanations
2. **Code Query Agent**: Searches a database of code snippets and examples

Your job:
1. Analyze the user's query
2. Decide which agent(s) to use:
   - Use Doc Search for: explanations, concepts, "how does X work?", best practices
   - Use Code Query for: code examples, implementations, "show me code for X"
   - Use BOTH for: comprehensive help like "How do I implement X?" (needs both explanation AND code)
3. Combine results into a helpful, coherent response

Response format:
- Start with a brief explanation (from docs if available)
- Include relevant code examples (from code query if available)
- Add tips or best practices
- Keep it practical and actionable

Be helpful and concise. Developers want answers, not fluff.
"""


def create_orchestrator_agent():
    """Create and return the Orchestrator Agent graph."""

    # Initialize LLM
    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0
    )

    def analyze_query(state: OrchestratorState) -> OrchestratorState:
        """Analyze query and decide which agents to call."""
        with tracer.start_as_current_span("orchestrator_analyze") as span:
            query = state["query"].lower()
            span.set_attribute("query", query)

            agents_to_call = []

            # Heuristics for routing
            needs_docs = any(word in query for word in [
                "how", "what", "why", "explain", "concept", "best practice",
                "documentation", "tutorial", "guide", "learn"
            ])

            needs_code = any(word in query for word in [
                "code", "example", "snippet", "implement", "show me",
                "sample", "function", "class", "script",
                # Database-related keywords - always query code snippets for these
                "database", "oracle", "connect", "sql", "query", "table",
                "insert", "select", "python", "java", "fastapi", "langchain"
            ])

            # Default: if unclear, call both
            if not needs_docs and not needs_code:
                needs_docs = True
                needs_code = True

            if needs_docs:
                agents_to_call.append("doc_search")
            if needs_code:
                agents_to_call.append("code_query")

            span.set_attribute("agents_to_call", str(agents_to_call))

            return {"agents_to_call": agents_to_call}

    def call_agents_parallel(state: OrchestratorState) -> OrchestratorState:
        """Call Doc Search and Code Query agents in parallel for faster response."""
        with tracer.start_as_current_span("orchestrator_call_agents_parallel") as span:
            query = state["query"]
            agents_to_call = state.get("agents_to_call", [])
            span.set_attribute("query", query)
            span.set_attribute("agents", str(agents_to_call))

            doc_results = ""
            code_results = ""

            # Capture current context for thread propagation
            current_context = otel_context.get_current() if OTEL_AVAILABLE else None

            def run_with_context(func, *args):
                """Run function with propagated OpenTelemetry context."""
                if OTEL_AVAILABLE and current_context:
                    token = otel_context.attach(current_context)
                    try:
                        return func(*args)
                    finally:
                        otel_context.detach(token)
                return func(*args)

            # Run agents in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {}

                if "doc_search" in agents_to_call:
                    futures[executor.submit(run_with_context, search_docs, query)] = "doc_search"
                if "code_query" in agents_to_call:
                    futures[executor.submit(run_with_context, query_code_snippets, query)] = "code_query"

                for future in as_completed(futures):
                    agent_name = futures[future]
                    try:
                        result = future.result()
                        if agent_name == "doc_search":
                            doc_results = result
                        else:
                            code_results = result
                    except Exception as e:
                        span.set_attribute(f"{agent_name}.error", str(e))

            span.set_attribute("doc_results_length", len(doc_results))
            span.set_attribute("code_results_length", len(code_results))

            return {"doc_results": doc_results, "code_results": code_results}

    def call_doc_search(state: OrchestratorState) -> OrchestratorState:
        """Call the Doc Search Agent (fallback for single agent)."""
        with tracer.start_as_current_span("orchestrator_call_doc_search") as span:
            query = state["query"]
            span.set_attribute("query", query)

            result = search_docs(query)

            span.set_attribute("result_length", len(result))

            return {"doc_results": result}

    def call_code_query(state: OrchestratorState) -> OrchestratorState:
        """Call the Code Query Agent (fallback for single agent)."""
        with tracer.start_as_current_span("orchestrator_call_code_query") as span:
            query = state["query"]
            span.set_attribute("query", query)

            result = query_code_snippets(query)

            span.set_attribute("result_length", len(result))

            return {"code_results": result}

    def combine_results(state: OrchestratorState) -> OrchestratorState:
        """Combine results from both agents into final response."""
        with tracer.start_as_current_span("orchestrator_combine") as span:
            doc_results = state.get("doc_results", "")
            code_results = state.get("code_results", "")
            query = state["query"]

            # Build prompt for final synthesis
            synthesis_prompt = f"""Based on the user's question and the gathered information, provide a comprehensive answer.

**User Question:** {query}

**Documentation/Explanation:**
{doc_results if doc_results else "No documentation found."}

**Code Examples:**
{code_results if code_results else "No code examples found."}

**Your Task:**
Synthesize this information into a clear, helpful response that:
1. Explains the concept briefly (if docs available)
2. Shows relevant code examples (if code available)
3. Provides practical tips
4. Is well-formatted with headers and code blocks

Keep it concise but complete."""

            messages = [
                SystemMessage(content="You are a helpful coding assistant synthesizing information for developers."),
                HumanMessage(content=synthesis_prompt)
            ]

            response = llm.invoke(messages)

            span.set_attribute("response_length", len(response.content))

            return {
                "final_response": response.content,
                "messages": [AIMessage(content=response.content)]
            }

    def route_to_agents(state: OrchestratorState) -> str:
        """Route to the appropriate agents - use parallel when both are needed."""
        agents = state.get("agents_to_call", [])

        if not agents:
            return "combine"

        # If both agents are needed, use parallel execution for speed
        if len(agents) == 2:
            return "parallel"

        # Single agent
        return agents[0]

    # Build the graph
    workflow = StateGraph(OrchestratorState)

    # Add nodes
    workflow.add_node("analyze", analyze_query)
    workflow.add_node("parallel", call_agents_parallel)  # Parallel execution
    workflow.add_node("doc_search", call_doc_search)     # Single agent fallback
    workflow.add_node("code_query", call_code_query)     # Single agent fallback
    workflow.add_node("combine", combine_results)

    # Set entry point
    workflow.set_entry_point("analyze")

    # Route based on analysis - parallel when both agents needed
    workflow.add_conditional_edges(
        "analyze",
        route_to_agents,
        {
            "parallel": "parallel",
            "doc_search": "doc_search",
            "code_query": "code_query",
            "combine": "combine"
        }
    )

    # All agent paths go to combine
    workflow.add_edge("parallel", "combine")
    workflow.add_edge("doc_search", "combine")
    workflow.add_edge("code_query", "combine")

    # Combine ends the workflow
    workflow.add_edge("combine", END)

    return workflow.compile()


# Cache the compiled orchestrator for reuse
_cached_orchestrator = None


def get_orchestrator_agent():
    """Get cached Orchestrator Agent (created once, reused)."""
    global _cached_orchestrator
    if _cached_orchestrator is None:
        _cached_orchestrator = create_orchestrator_agent()
    return _cached_orchestrator


def ask_assistant(query: str, status_callback=None) -> dict:
    """
    Main entry point for the Code Assistant.

    Args:
        query: User's question about coding
        status_callback: Optional callback function(agent, status, details) for real-time updates

    Returns:
        Dictionary with 'response' and 'timing' data
    """
    import time
    timing = {
        "orchestrator_analyze": 0,
        "doc_search": 0,
        "code_query": 0,
        "combine": 0,
        "total": 0
    }
    start_time = time.time()

    with tracer.start_as_current_span("code_assistant_query") as span:
        span.set_attribute("query", query)

        if status_callback:
            status_callback("Orchestrator", "analyzing", "Analyzing query...")

        # Use cached orchestrator for faster response
        orchestrator = get_orchestrator_agent()

        # Initial state
        initial_state = {
            "messages": [HumanMessage(content=query)],
            "query": query,
            "doc_results": "",
            "code_results": "",
            "final_response": "",
            "agents_to_call": []
        }

        # Use streaming for real-time updates
        node_start_time = time.time()
        final_state = None

        for event in orchestrator.stream(initial_state):
            # event is a dict with node name as key
            for node_name, node_output in event.items():
                node_end_time = time.time()
                node_duration = node_end_time - node_start_time

                # Track timing
                if node_name == "analyze":
                    timing["orchestrator_analyze"] = node_duration
                    if status_callback:
                        agents = node_output.get("agents_to_call", [])
                        status_callback("Orchestrator", "routing", f"Will query: {', '.join(agents) if agents else 'combining results'}")
                elif node_name == "parallel":
                    # Parallel execution - time is split between agents
                    timing["doc_search"] = node_duration / 2
                    timing["code_query"] = node_duration / 2
                    if status_callback:
                        status_callback("Doc Search Agent", "running", "Searching documentation...")
                        status_callback("Code Query Agent", "running", "Querying code snippets...")
                        status_callback("Doc Search Agent", "complete", "Documentation retrieved")
                        status_callback("Code Query Agent", "complete", "Code snippets retrieved")
                elif node_name == "doc_search":
                    timing["doc_search"] = node_duration
                    if status_callback:
                        status_callback("Doc Search Agent", "running", "Searching documentation...")
                        status_callback("Doc Search Agent", "complete", "Documentation retrieved")
                elif node_name == "code_query":
                    timing["code_query"] = node_duration
                    if status_callback:
                        status_callback("Code Query Agent", "running", "Querying code snippets...")
                        status_callback("Code Query Agent", "complete", "Code snippets retrieved")
                elif node_name == "combine":
                    timing["combine"] = node_duration
                    if status_callback:
                        status_callback("Orchestrator", "combining", "Synthesizing response...")

                # Update final state
                if final_state is None:
                    final_state = node_output
                else:
                    final_state.update(node_output)

                node_start_time = time.time()

        timing["total"] = time.time() - start_time

        response = final_state.get("final_response", "Sorry, I couldn't find an answer.") if final_state else "Sorry, I couldn't find an answer."

        if status_callback:
            status_callback("Orchestrator", "complete", f"Response generated in {timing['total']:.1f}s")

        span.set_attribute("response_length", len(response))
        span.set_attribute("total_time_ms", timing["total"] * 1000)

        return {
            "response": response,
            "timing": timing
        }


# For testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Initialize telemetry for testing
    try:
        from src.telemetry.tracing import init_telemetry
        init_telemetry()
    except Exception:
        pass

    # Test queries
    test_queries = [
        "How do I connect to Oracle database in Python?",
        "Show me FastAPI authentication examples",
        "What is connection pooling and how do I implement it with Oracle?",
    ]

    def print_status(agent, status, details):
        print(f"  [{agent}] {status}: {details}")

    for query in test_queries:
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print('='*70)
        result = ask_assistant(query, status_callback=print_status)
        print(f"\nResponse:\n{result['response']}")
        print(f"\nTiming: {result['timing']}")
