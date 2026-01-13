# Building Observable Multi-Agent AI Systems with LangGraph and Oracle Database

*How I built a production-ready Code Assistant with full distributed tracing*

![Hero Banner](images/hero-banner.png)
<!--
IMAGE PROMPT (DALL-E/Midjourney):
"A futuristic digital illustration showing multiple AI agents working together in a neural network. Three glowing orbs (blue, green, orange) connected by flowing data streams. Dark blue gradient background with subtle circuit patterns. Modern tech startup aesthetic. No text."
-->

---

## The Problem I Wanted to Solve

Last year, while building enterprise AI platforms, I kept running into the same issue: when a multi-agent system behaved unexpectedly, debugging felt like finding a needle in a haystack. Which agent failed? Was it the LLM? The database? The external API?

I decided to build something that would solve this once and for all - a Code Assistant that not only helps developers find documentation and code examples but also provides complete visibility into every single operation through distributed tracing.

This post walks through how I built it using **LangGraph**, **Oracle Database 23ai**, and **OpenTelemetry**.

---

## What We're Building

A conversational AI assistant that:

1. **Understands developer queries** - "How do I connect to Oracle in Python?"
2. **Searches real-time documentation** - Using Tavily API for web search
3. **Retrieves code examples** - From an Oracle database with 40+ curated snippets
4. **Combines everything intelligently** - Using Claude 3.5 Sonnet
5. **Traces every operation** - Full observability with Jaeger

![Tech Stack](images/tech-stack.png)
<!--
IMAGE: Arrange official logos horizontally - LangGraph, Claude/Anthropic, Oracle, Tavily, OpenTelemetry, Jaeger, Streamlit, Docker. 64x64px each with consistent styling.
-->

| Layer | Technology | Purpose |
|-------|------------|---------|
| Orchestration | LangGraph | Multi-agent coordination |
| LLM | Claude 3.5 Sonnet | Reasoning and synthesis |
| Database | Oracle 23ai | Code snippet storage |
| Search | Tavily API | Real-time documentation |
| Tracing | OpenTelemetry + Jaeger | Full observability |
| Frontend | Streamlit | Chat interface |

---

## Architecture Deep Dive

### Multi-Agent Design

The system uses three specialized agents, each with a single responsibility:

![Architecture Overview](images/architecture-overview.png)
<!--
IMAGE PROMPT (Eraser DiagramGPT):
"Create a system architecture diagram showing: User Query box at top, Orchestrator Agent in center (main coordinator), two parallel branches: Doc Search Agent (connects to Tavily API) and Code Query Agent (connects to Oracle Database), OpenTelemetry spans wrapping all components, Combined Response at bottom. Blue color scheme with orange highlights."
-->

**Orchestrator Agent** - The brain of the operation. It analyzes incoming queries, decides which specialized agents to invoke, and synthesizes their responses into a coherent answer.

**Doc Search Agent** - Connects to Tavily API for real-time web searches. Specialized in finding official documentation, tutorials, and Stack Overflow answers.

**Code Query Agent** - Queries our Oracle database containing curated code snippets across multiple categories: database connections, API patterns, authentication, and more.

### Why This Architecture?

I've built monolithic AI applications before. They work until they don't. When something breaks, you're grepping through logs hoping to find a clue.

This modular approach gives us:

- **Isolation** - A bug in the doc search doesn't crash code queries
- **Scalability** - Each agent can be optimized independently
- **Testability** - Unit test each component in isolation
- **Observability** - Clear boundaries make tracing meaningful

---

## LangGraph: The Agent Framework

LangGraph extends LangChain with graph-based workflows. Instead of linear chains, we define nodes (processing steps) and edges (transitions).

![LangGraph Flow](images/langgraph-flow.png)
<!--
IMAGE PROMPT (Eraser):
"Create a state machine diagram for LangGraph agent: START node, Agent Node (reasoning), conditional edge 'has_tool_calls?', if yes: Tool Node (execute tools) loops back to Agent, if no: END node. Show state object flowing between nodes. Green and blue colors."
-->

Here's how I implemented the Code Query Agent:

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

class CodeQueryState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    query: str
    results: str

def create_code_query_agent():
    llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
    tools = [search_code_snippets, get_snippet_by_id]
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: CodeQueryState) -> CodeQueryState:
        with tracer.start_as_current_span("code_query_reasoning") as span:
            span.set_attribute("agent.name", "code_query")
            response = llm_with_tools.invoke(state["messages"])
            return {"messages": [response]}

    def should_continue(state: CodeQueryState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

    workflow = StateGraph(CodeQueryState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()
```

The key insight: the `should_continue` function creates a loop. The agent reasons, decides to call a tool, executes it, and reasons again with the results. This continues until the agent has enough information to respond.

---

## Oracle Database Integration

### Schema Design

I designed a simple but effective schema for storing code snippets:

![Database Schema](images/database-schema.png)
<!--
IMAGE: ERD diagram showing code_snippets table with all fields and data types. Use dbdiagram.io or similar tool.
-->

```sql
CREATE TABLE code_snippets (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR2(200) NOT NULL,
    description VARCHAR2(2000),
    language VARCHAR2(50) NOT NULL,
    framework VARCHAR2(100),
    category VARCHAR2(100),
    difficulty VARCHAR2(20) DEFAULT 'intermediate',
    code CLOB NOT NULL,
    tags VARCHAR2(500),
    source_url VARCHAR2(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_snippets_language ON code_snippets(language);
CREATE INDEX idx_snippets_category ON code_snippets(category);
```

### The Query Tool

The tool exposes our database to the LLM with proper parameter handling:

```python
@tool
def search_code_snippets(
    language: str = None,
    category: str = None,
    keyword: str = None,
    limit: int = 5
) -> str:
    """Search for code snippets in the Oracle database."""

    with tracer.start_as_current_span("oracle_query") as span:
        span.set_attribute("db.system", "oracle")

        conditions, params = [], {}

        if language:
            conditions.append("LOWER(language) = LOWER(:language)")
            params["language"] = language
        if category:
            conditions.append("LOWER(category) = LOWER(:category)")
            params["category"] = category
        if keyword:
            conditions.append("LOWER(title) LIKE LOWER(:keyword) OR LOWER(tags) LIKE LOWER(:keyword)")
            params["keyword"] = f"%{keyword}%"

        query = f"""
            SELECT id, title, description, language, framework, category, code, tags
            FROM code_snippets
            WHERE {' AND '.join(conditions) if conditions else '1=1'}
            ORDER BY created_at DESC
            FETCH FIRST {min(limit, 20)} ROWS ONLY
        """

        span.set_attribute("db.statement", query[:500])
        result = execute_oracle_query(query, params)
        span.set_attribute("db.rows_returned", len(result))

        return json.dumps(result, indent=2, default=str)
```

Notice how every operation is wrapped in a span. This is crucial for debugging - when a query is slow, I can see exactly which database operation caused it.

---

## The Observability Layer

This is where it gets interesting. Every request generates a complete trace showing exactly what happened.

### OpenTelemetry Setup

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def init_telemetry(service_name: str = "code-assistant"):
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    otlp_exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(provider)
```

### What a Trace Looks Like

![Jaeger Trace](images/jaeger-trace.png)
<!--
IMAGE: Screenshot from Jaeger UI showing a complete trace with 8+ spans in waterfall view. Alternatively, use the DALL-E prompt from IMAGE_PROMPTS.md
-->

A typical query generates this trace hierarchy:

```
code_assistant_query [2.3s]
├── orchestrator_analyze [45ms]
├── doc_search_agent [1.1s]
│   ├── llm_invoke [650ms]
│   └── tavily_search [420ms]
├── code_query_agent [890ms]
│   ├── llm_invoke [580ms]
│   └── oracle_query [95ms]
└── orchestrator_combine [290ms]
```

From this, I can immediately see:
- Total request took 2.3 seconds
- LLM calls dominate latency (as expected)
- Database query is fast (95ms)
- Agents ran in parallel (their times overlap in the real trace)

### Graceful Degradation

The app shouldn't crash if Jaeger is down. I implemented a no-op fallback:

```python
class NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield NoOpSpan()

def get_tracer(name: str):
    try:
        return trace.get_tracer(name)
    except Exception:
        return NoOpTracer()
```

---

## Query Routing Logic

The orchestrator decides which agents to invoke based on query analysis:

![Routing Logic](images/routing-logic.png)
<!--
IMAGE PROMPT (Eraser/Draw.io):
"Decision tree flowchart: Start 'User Query', Decision 'Contains how/what/why?' -> Yes: needs_docs=true, Decision 'Contains code/example/snippet?' -> Yes: needs_code=true, Decision 'Neither flag set?' -> Yes: set both=true, End 'Route to agents'. Diamond shapes for decisions, rectangles for actions."
-->

```python
def analyze_query(state: OrchestratorState) -> OrchestratorState:
    with tracer.start_as_current_span("orchestrator_analyze") as span:
        query = state["query"].lower()

        needs_docs = any(word in query for word in ["how", "what", "why", "explain", "documentation"])
        needs_code = any(word in query for word in ["code", "example", "snippet", "implement", "show me"])

        # Default: call both if intent is unclear
        if not needs_docs and not needs_code:
            needs_docs = needs_code = True

        agents = []
        if needs_docs:
            agents.append("doc_search")
        if needs_code:
            agents.append("code_query")

        span.set_attribute("routing.agents", str(agents))
        return {"agents_to_call": agents}
```

This simple heuristic works surprisingly well. For production, you could replace it with a classifier or let the LLM decide.

---

## Running It Locally

### Prerequisites

- Python 3.11+
- Docker Desktop
- Anthropic API key
- Tavily API key (free tier: 1000 searches/month)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/velloreakash21/multi-agent-code-assistant.git
cd multi-agent-code-assistant

# Start Oracle and Jaeger
docker-compose up -d

# Wait for Oracle to be ready (~3 minutes first time)
docker logs -f oracle-23ai-code-assistant
# Look for: "DATABASE IS READY TO USE!"

# Setup Python environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add your API keys to .env

# Initialize database
python -m src.database.seed_data

# Run the app
streamlit run streamlit_app.py
```

### The UI

![Streamlit UI](images/streamlit-ui.png)
<!--
IMAGE: Screenshot of the Streamlit interface showing a conversation with the Code Assistant. Include the chat messages, agent activity sidebar, and trace visualization.
-->

Open http://localhost:8501 and try queries like:
- "How do I connect to Oracle database in Python?"
- "Show me FastAPI authentication examples"
- "What's the best way to handle database connection pooling?"

View traces at http://localhost:16686 (Jaeger UI).

---

## Performance Insights

After running this in my local environment, here's what the traces revealed:

![Performance Chart](images/performance-chart.png)
<!--
IMAGE: Horizontal bar chart showing time breakdown - Orchestrator (45ms), Doc Search (1100ms), Code Query (890ms), LLM Calls (1230ms), DB Query (95ms). Use matplotlib or Chart.js.
-->

| Component | Average Time | Notes |
|-----------|--------------|-------|
| Orchestrator Analysis | 45ms | Fast routing decision |
| Doc Search Agent | 1.1s | Tavily API + LLM reasoning |
| Code Query Agent | 890ms | LLM + Oracle query |
| LLM Invocations | 1.2s total | The main bottleneck |
| Oracle Query | 95ms | Indexed queries are fast |

**Key Takeaway**: LLM latency dominates. For production, consider streaming responses, caching common queries, or using a faster model for routing decisions.

---

## Lessons Learned

### 1. Trace Everything from Day One

Adding observability later is painful. Build it in from the start. Every tool call, every LLM invocation, every database query should be a span.

### 2. Keep Agents Focused

Single-responsibility agents are easier to debug, test, and optimize. The orchestrator pattern works well for coordinating them.

### 3. Graceful Degradation Matters

Your app shouldn't crash because Jaeger is down. NoOp fallbacks for telemetry are essential.

### 4. Oracle 23ai is Solid

The free tier of Oracle 23ai runs great in Docker. Connection pooling with oracledb works smoothly with proper configuration.

---

## What's Next

I'm planning to extend this with:

- **Vector Search** - Using Oracle AI Vector Search for semantic code matching
- **Metrics Dashboard** - Grafana integration for request rates and error tracking
- **Caching Layer** - Redis for common query patterns
- **More Agents** - GitHub integration, Stack Overflow search

---

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Oracle 23ai Documentation](https://docs.oracle.com/en/database/oracle/oracle-database/23/)
- [Jaeger Tracing](https://www.jaegertracing.io/)
- [Tavily API](https://tavily.com/)

---

## Get the Code

Full source code: [github.com/velloreakash21/multi-agent-code-assistant](https://github.com/velloreakash21/multi-agent-code-assistant)

---

*Have questions? Connect with me on [LinkedIn](https://www.linkedin.com/in/velloreakash/).*

---

**Vellore Akash** | AI/ML Architect

Building enterprise AI platforms with LangChain, LlamaIndex, and cloud-native technologies. Currently exploring the intersection of multi-agent systems and observability.
