# Code Assistant

> Multi-Agent AI System with Full Observability

An AI-powered assistant that helps developers find documentation and code examples using multi-agent orchestration, Oracle Database 23ai, and distributed tracing.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)
![Oracle](https://img.shields.io/badge/Oracle-23ai-red.svg)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Tracing-purple.svg)

---

## Overview

This project demonstrates building observable, production-grade multi-agent AI systems. It showcases:

- **Multi-Agent Orchestration** - LangGraph-based coordination between specialized agents
- **Oracle Database Integration** - Code snippet storage with SQLcl MCP Server
- **Real-Time Search** - Documentation retrieval via Tavily API
- **Distributed Tracing** - Full observability with OpenTelemetry and Jaeger

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
                ┌─────────────────────────┐
                │   Orchestrator Agent    │
                │   (LangGraph Router)    │
                └─────────────┬───────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                                     │
           ▼                                     ▼
┌─────────────────────┐             ┌─────────────────────┐
│  Doc Search Agent   │             │  Code Query Agent   │
│  ───────────────    │             │  ───────────────    │
│  Tavily API         │             │  Oracle 23ai DB     │
│  Web Documentation  │             │  40+ Code Snippets  │
└─────────────────────┘             └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │  SQLcl MCP Server   │
                                    │  (Model Context     │
                                    │   Protocol)         │
                                    └─────────────────────┘
                              │
                              ▼
                ┌─────────────────────────┐
                │   Combined Response     │
                │   + Trace Metadata      │
                └─────────────────────────┘

        ┌─────────────────────────────────────────┐
        │         OpenTelemetry → Jaeger          │
        │         (Distributed Tracing)           │
        └─────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Agent Framework | LangGraph | Multi-agent coordination |
| LLM | Claude 3.5 Sonnet | Reasoning and synthesis |
| Database | Oracle Database 23ai | Code snippet storage |
| DB Access | SQLcl MCP Server | AI-database interaction |
| Web Search | Tavily API | Documentation retrieval |
| Observability | OpenTelemetry + Jaeger | Distributed tracing |
| Frontend | Streamlit | Chat interface |

---

## Prerequisites

- **Python 3.11+**
- **Docker Desktop** (for Oracle and Jaeger)
- **API Keys:**
  - [Anthropic API Key](https://console.anthropic.com/)
  - [Tavily API Key](https://tavily.com/) (free tier: 1000 searches/month)

---

## Quick Start

### One-Command Setup

After cloning, use the helper scripts to start everything:

**macOS/Linux:**
```bash
git clone https://github.com/velloreakash21/code-assistant.git
cd code-assistant
# Edit .env with your API keys first
cp .env.example .env && nano .env
# Then start everything
./scripts/start.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/velloreakash21/code-assistant.git
cd code-assistant
# Edit .env with your API keys first
Copy-Item .env.example .env; notepad .env
# Then start everything
.\scripts\start.ps1
```

> **Important:** Edit `.env` with your API keys before running the start script!

---

### Step-by-Step Setup

#### 1. Clone Repository

```bash
git clone https://github.com/velloreakash21/code-assistant.git
cd code-assistant
```

#### 2. Start Infrastructure

```bash
docker-compose up -d
```

This starts:
- **Oracle Database 23ai** on port 1521
- **Jaeger** on port 16686 (UI) and 4317 (OTLP)

Wait for Oracle to be healthy (~2-3 minutes):

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
# oracle-23ai-code-assistant should show "healthy"
```

#### 3. Setup Python Environment

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
```

#### 5. Initialize Database

```bash
# Create schema and seed data
python -m src.database.seed_data
```

#### 6. Run Application

```bash
streamlit run streamlit_app.py
```

**Access:**
- **Application:** http://localhost:8501
- **Jaeger Traces:** http://localhost:16686

---

## Usage

### Sample Queries

Try these queries in the chat interface:

- "How do I connect to Oracle database in Python?"
- "Show me connection pooling examples"
- "What's the best way to handle database transactions?"
- "Show me FastAPI authentication examples"

### CLI Mode

```bash
python -m src.main "How do I handle Oracle transactions?"
```

### Python API

```python
from src.agents.orchestrator import ask_assistant

result = ask_assistant("Show me JWT authentication examples")
print(result["response"])
print(f"Total time: {result['timing']['total']:.2f}s")
```

---

## Project Structure

```
code-assistant/
├── src/
│   ├── agents/
│   │   ├── orchestrator.py      # Query routing and parallel execution
│   │   ├── doc_search.py        # Tavily documentation search
│   │   └── code_query.py        # Oracle database queries
│   ├── tools/
│   │   ├── tavily_search.py     # Tavily API wrapper
│   │   ├── oracle_mcp.py        # Oracle connection utilities
│   │   └── sqlcl_mcp_client.py  # MCP client implementation
│   ├── database/
│   │   ├── schema.sql           # Table definitions
│   │   └── seed_data.py         # 40+ code snippets
│   ├── telemetry/
│   │   └── tracing.py           # OpenTelemetry setup
│   ├── frontend/
│   │   ├── app.py               # Streamlit application
│   │   ├── components.py        # UI components
│   │   └── styles.py            # Custom styling
│   └── config.py                # Configuration management
├── scripts/
│   ├── start.sh                 # One-click start (macOS/Linux)
│   └── start.ps1                # One-click start (Windows)
├── docs/
│   └── blog_post.md             # Technical blog post
├── docker-compose.yml           # Infrastructure services
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
└── streamlit_app.py             # Application entry point
```

---

## Observability

### Trace Hierarchy

Every query generates distributed traces showing the complete request flow:

```
code_assistant_query [~45s with parallel execution]
├── orchestrator_analyze [4ms]
├── orchestrator_call_agents_parallel [~25s]  ← Runs both agents simultaneously
│   ├── doc_search_agent [parallel]
│   │   ├── doc_search_agent_reasoning
│   │   ├── tavily_search
│   │   └── format_doc_results
│   └── code_query_agent [parallel]
│       ├── code_query_agent_reasoning
│       ├── oracle_query
│       └── format_code_results
└── orchestrator_combine [~15s]
```

> **Performance:** Parallel agent execution reduces total query time by ~40% compared to sequential execution.

### Viewing Traces

1. Open Jaeger UI: http://localhost:16686
2. Select service: `code-assistant`
3. Click "Find Traces"
4. Select a trace to see the waterfall view

---

## Code Snippets Database

The Oracle database contains 40+ curated code examples:

| Category | Count | Topics |
|----------|-------|--------|
| database | 12 | Connections, queries, transactions, pooling |
| api | 8 | FastAPI endpoints, middleware, error handling |
| ai | 8 | LangChain, LangGraph, embeddings |
| auth | 5 | JWT, OAuth, RBAC patterns |
| data | 4 | Pandas, CSV, JSON processing |
| testing | 3 | Pytest fixtures, mocking |

---

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | (required) |
| `TAVILY_API_KEY` | Tavily search key | (required) |
| `ORACLE_HOST` | Database hostname | localhost |
| `ORACLE_PORT` | Database port | 1521 |
| `ORACLE_SERVICE` | Service name | FREEPDB1 |
| `ORACLE_USER` | Database user | codeassist |
| `ORACLE_PASSWORD` | Database password | CodeAssist123 |
| `OTEL_EXPORTER_ENDPOINT` | Jaeger OTLP endpoint | localhost:4317 |

---

## Troubleshooting

### Oracle Connection Issues

```bash
# Check container status
docker ps | grep oracle

# View container logs
docker logs -f oracle-23ai-code-assistant

# Test connection
docker exec -it oracle-23ai-code-assistant sqlplus codeassist/CodeAssist123@FREEPDB1
```

### Missing Traces in Jaeger

1. Verify Jaeger is running: `docker ps | grep jaeger`
2. Check OTLP endpoint in `.env`
3. Ensure `init_telemetry()` is called before traced operations

### API Rate Limits

Implement retry logic for production:

```python
from tenacity import retry, wait_exponential

@retry(wait=wait_exponential(min=4, max=60))
def call_llm(messages):
    return llm.invoke(messages)
```

---

## Documentation

- [Technical Blog Post](docs/blog_post.md) - Detailed implementation guide
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Oracle 23ai Docs](https://docs.oracle.com/en/database/oracle/oracle-database/23/)

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Author

**Vellore Akash**
AI/ML Architect

- [LinkedIn](https://www.linkedin.com/in/velloreakash/)
- [GitHub](https://github.com/velloreakash21)
- [Email](mailto:velloreakash21@gmail.com)
