# Building Observable Multi-Agent AI Systems with LangGraph and Oracle Database

*A practical guide to implementing distributed tracing in agentic AI applications*

---

## Introduction

As AI applications evolve from simple chatbots to complex multi-agent systems, observability becomes critical. When multiple agents coordinate to handle user requests—each making LLM calls, database queries, and API requests—understanding system behavior requires more than traditional logging.

This guide demonstrates building a **Code Assistant**—a production-grade multi-agent system where every operation is traced using OpenTelemetry. You'll see exactly what happens inside your agents, down to the millisecond.

**What we're building:**
- A conversational assistant that helps developers find documentation and code examples
- Multi-agent orchestration with LangGraph
- Oracle Database 23ai integration via SQLcl MCP Server
- Real-time documentation search via Tavily API
- Full distributed tracing with Jaeger

---

## Architecture Overview

The system follows a hub-and-spoke architecture with three specialized agents:

![Architecture Diagram](images/architecture-diagram.png)
<!--
SCREENSHOT: Architecture diagram showing the multi-agent system
- Create using draw.io, Excalidraw, or similar tool
- Show: User Query → Orchestrator Agent → Doc Search Agent (Tavily) + Code Query Agent (Oracle via MCP)
- Include OpenTelemetry/Jaeger for trace collection
-->

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | LangGraph | Multi-agent coordination and routing |
| LLM | Claude 3.5 Sonnet | Reasoning and response synthesis |
| Database | Oracle Database 23ai | Code snippet storage and retrieval |
| DB Access | SQLcl MCP Server | Standardized AI-database interaction |
| Web Search | Tavily API | Real-time documentation search |
| Observability | OpenTelemetry + Jaeger | Distributed tracing |
| Frontend | Streamlit | Interactive chat interface |

### Agent Responsibilities

**Orchestrator Agent** analyzes incoming queries, determines which specialized agents to invoke based on query intent, and synthesizes their responses into coherent answers.

**Doc Search Agent** connects to Tavily API for real-time web searches, specializing in finding official documentation, tutorials, and community solutions.

**Code Query Agent** interfaces with Oracle Database 23ai through the SQLcl MCP Server, retrieving relevant code snippets from a curated collection of 40+ examples.

---

## Why SQLcl MCP for Database Access?

The Code Query Agent doesn't connect directly to Oracle. Instead, it uses Oracle's **SQLcl MCP Server**—an implementation of the Model Context Protocol. This architectural choice provides several benefits:

1. **Security by Design** - MCP server defaults to read-only mode with complete audit logging to `DBTOOLS$MCP_LOG` table

2. **Standardized Protocol** - MCP is an open standard under the Linux Foundation, adopted by Anthropic, OpenAI, and major cloud providers

3. **Observable by Default** - Every query includes LLM context comments, making AI-generated queries identifiable in database logs

4. **Abstraction Layer** - Database backends can be swapped without modifying agent code

---

## Implementation Deep Dive

### LangGraph Agent Structure

LangGraph extends LangChain with graph-based workflows. Here's the Code Query Agent implementation:

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

    workflow = StateGraph(CodeQueryState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue,
                                   {"tools": "tools", "end": END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()
```

The key pattern: the agent reasons, decides to call a tool, executes it, and reasons again with the results—continuing until it has sufficient information to respond.

### Database Tool with Tracing

Every database operation is wrapped in OpenTelemetry spans:

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

        # Build parameterized query
        query = build_search_query(language, category, keyword, limit)
        span.set_attribute("db.statement", query[:500])

        result = execute_oracle_query(query, params)
        span.set_attribute("db.rows_returned", len(result))

        return json.dumps(result, indent=2, default=str)
```

---

## OpenTelemetry Integration

### Telemetry Setup

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

### Trace Visualization

A typical query generates this trace hierarchy:

```
code_assistant_query [77s]
├── orchestrator_analyze [4ms]
├── doc_search_agent [15.9s]
│   ├── doc_search_agent_reasoning [3.9s]
│   ├── tavily_search [865ms]
│   ├── tavily_search [874ms]
│   └── doc_search_agent_reasoning [11.1s]
├── code_query_agent [25.5s]
│   ├── code_query_agent_reasoning [3.5s]
│   ├── oracle_query [125ms]
│   ├── code_query_agent_reasoning [12.1s]
│   └── oracle_query [6ms]
└── orchestrator_combine [17s]
```

![Jaeger Trace Visualization](images/jaeger-trace.png)
<!--
SCREENSHOT: Jaeger UI showing distributed trace
- Open http://localhost:16686
- Find trace for "code-assistant" service
- Capture the waterfall view showing span hierarchy
- Should show: orchestrator → doc_search_agent + code_query_agent → oracle_query spans
-->

From this trace, we can immediately identify:
- Total request latency and breakdown by component
- LLM calls dominate processing time (as expected)
- Database queries are fast (~125ms)
- Which agents were invoked and their execution order

---

## The Streamlit Interface

The frontend provides real-time visibility into agent activity:

![Streamlit UI](images/streamlit-ui.png)
<!--
SCREENSHOT: Streamlit application interface
- Open http://localhost:8501
- Enter query: "How do I connect to Oracle database?"
- Wait for response to complete
- Capture showing: Chat panel, Agent Activity panel, Trace Visualization, Metrics bar
-->

**Key UI Components:**
- **Chat Panel** - Conversation history with formatted responses
- **Agent Activity** - Real-time status updates as agents process the query
- **Trace Visualization** - Inline timeline showing span hierarchy and timing
- **Metrics Bar** - Summary statistics (Total Time, LLM Time, DB Time, Search Time)

---

## Running the Application

### Prerequisites

- Python 3.11+
- Docker Desktop
- Anthropic API Key
- Tavily API Key (free tier: 1000 searches/month)

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/code-assistant.git
cd code-assistant

# Start infrastructure
docker-compose up -d

# Wait for Oracle to be healthy (~2-3 minutes)
docker ps --format "table {{.Names}}\t{{.Status}}"

# Setup Python environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python -m src.database.seed_data

# Run application
streamlit run streamlit_app.py
```

**Access Points:**
- Application: http://localhost:8501
- Jaeger Traces: http://localhost:16686

---

## Key Takeaways

### 1. Instrument from Day One
Adding observability later is painful. Build tracing into your agents from the start—every tool call, LLM invocation, and database query should be a span.

### 2. Use Standardized Protocols
The Model Context Protocol (MCP) provides a standardized interface for AI-database interaction with built-in security and observability.

### 3. Design for Graceful Degradation
Applications shouldn't crash when tracing infrastructure is unavailable. Implement no-op fallbacks:

```python
class NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield NoOpSpan()
```

### 4. Keep Agents Focused
Single-responsibility agents are easier to debug, test, and optimize. The orchestrator pattern works well for coordination.

---

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Oracle Database 23ai](https://docs.oracle.com/en/database/oracle/oracle-database/23/)
- [Oracle SQLcl MCP Server](https://docs.oracle.com/en/database/oracle/sql-developer-command-line/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Jaeger Tracing](https://www.jaegertracing.io/)

---

## About the Author

**Vellore Akash** | AI/ML Architect

Building enterprise AI platforms with LangChain, LlamaIndex, and cloud-native technologies. 6+ years of experience designing and deploying Generative AI solutions across EdTech, SaaS, and enterprise domains.

- [LinkedIn](https://www.linkedin.com/in/velloreakash/)
- [GitHub](https://github.com/velloreakash21)
