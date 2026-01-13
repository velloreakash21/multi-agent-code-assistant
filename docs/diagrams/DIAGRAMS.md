# Diagram Generation Instructions

This directory contains diagram source files. Follow these instructions to generate the PNG images for the blog post.

## Required Images

| Image | Source | Destination |
|-------|--------|-------------|
| Architecture | `architecture.mmd` | `../images/architecture-overview.png` |
| Jaeger Trace | Screenshot | `../images/jaeger-trace.png` |
| Streamlit UI | Screenshot | `../images/streamlit-ui.png` |

## 1. Architecture Diagram

### Option A: Mermaid CLI (Recommended)

```bash
# Install Mermaid CLI
npm install -g @mermaid-js/mermaid-cli

# Generate PNG
mmdc -i architecture.mmd -o ../images/architecture-overview.png -w 1000 -H 800 -b white
```

### Option B: Mermaid Live Editor

1. Go to https://mermaid.live
2. Paste the contents of `architecture.mmd`
3. Click "Download PNG" (Actions menu)
4. Save as `../images/architecture-overview.png`

### Option C: VS Code Extension

1. Install "Markdown Preview Mermaid Support" extension
2. Open `architecture.mmd`
3. Right-click → Export as PNG

## 2. Jaeger Trace Screenshot

Capture a real trace from your running system:

```bash
# 1. Start all services
docker-compose up -d

# 2. Wait for Oracle to be healthy
docker ps --format "table {{.Names}}\t{{.Status}}"

# 3. Initialize database if needed
python -m src.database.seed_data

# 4. Run a query to generate trace
python -m src.main "Show me Python database connection examples"

# 5. Open Jaeger UI
open http://localhost:16686
```

In Jaeger UI:
1. Select Service: `code-assistant`
2. Click "Find Traces"
3. Click on a trace to see the waterfall view
4. Screenshot the expanded view showing:
   - `code_assistant_query` (parent span)
   - `orchestrator_analyze`
   - `doc_search_agent` with children
   - `code_query_agent` with `sqlcl_mcp.*` children
   - `orchestrator_combine`

Save as: `../images/jaeger-trace.png`

## 3. Streamlit UI Screenshot

```bash
# 1. Start the Streamlit app
streamlit run streamlit_app.py

# 2. Open in browser
open http://localhost:8501
```

In the UI:
1. Enter query: "Show me Python database connection examples"
2. Wait for response with code snippets
3. Screenshot the full window showing:
   - Chat input
   - User message
   - Assistant response with code blocks
   - Any sidebar/status indicators

Save as: `../images/streamlit-ui.png`

## Image Specifications

| Image | Recommended Size | Format |
|-------|-----------------|--------|
| Architecture | 1000x800 px | PNG |
| Jaeger Trace | 1200x600 px | PNG |
| Streamlit UI | 1200x800 px | PNG |

## Troubleshooting

### Mermaid CLI Issues

```bash
# If mmdc fails, try with puppeteer config
mmdc -i architecture.mmd -o ../images/architecture-overview.png -p puppeteer-config.json
```

Create `puppeteer-config.json`:
```json
{
  "args": ["--no-sandbox"]
}
```

### Screenshot Tips

- Use browser zoom at 100% for consistent sizing
- Crop to remove browser chrome if needed
- Use PNG format for crisp text
- Consider using a screenshot tool like:
  - macOS: Cmd+Shift+4
  - Windows: Snipping Tool
  - Cross-platform: Greenshot, Flameshot
