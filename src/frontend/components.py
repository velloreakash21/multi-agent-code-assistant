"""
Reusable UI components for the Streamlit frontend.
"""
import streamlit as st
from datetime import datetime


def render_chat_message(message: dict):
    """Render a chat message."""
    role = message["role"]
    content = message["content"]

    if role == "user":
        with st.chat_message("user", avatar="user"):
            st.markdown(content)
    else:
        with st.chat_message("assistant", avatar="assistant"):
            st.markdown(content)


def render_agent_activity(activity: dict):
    """Render agent activity card."""
    agent = activity["agent"]
    status = activity["status"]
    details = activity.get("details", "")

    # Agent icons
    icons = {
        "Orchestrator": "target",
        "Doc Search Agent": "book",
        "Code Query Agent": "database",
        "Error": "x-circle"
    }

    # Status colors
    status_colors = {
        "analyzing": "blue",
        "searching": "orange",
        "querying": "orange",
        "complete": "green",
        "failed": "red"
    }

    icon = icons.get(agent, "settings")
    color = status_colors.get(status, "gray")

    with st.container():
        st.markdown(f"""
        <div style="
            padding: 12px;
            border-radius: 8px;
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
            margin-bottom: 8px;
            border-left: 4px solid {color};
            color: #ffffff;
        ">
            <div style="font-weight: bold; color: #ffffff; font-size: 1em;">{agent}</div>
            <div style="font-size: 0.9em; color: #b8d4e8;">
                {details}
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_trace_visualization(trace: dict):
    """Render trace visualization as a timeline."""
    if not trace or not trace.get("spans"):
        st.info("No trace data available")
        return

    total_time = trace.get("total_time", 1)

    def render_span(span: dict, indent: int = 0):
        name = span["name"]
        duration = span["duration"]
        percentage = (duration / total_time) * 100

        # Create bar visualization
        indent_str = "  " * indent
        bar_width = max(int(percentage * 0.5), 1)
        bar = "-" * bar_width

        # Color based on span type
        if "llm" in name.lower():
            color = "#ff6b6b"  # Red for LLM
        elif "oracle" in name.lower() or "db" in name.lower():
            color = "#4ecdc4"  # Teal for DB
        elif "search" in name.lower() or "tavily" in name.lower():
            color = "#ffe66d"  # Yellow for search
        else:
            color = "#95e1d3"  # Green for orchestrator

        st.markdown(f"""
        <div style="font-family: monospace; font-size: 0.85em;">
            <span style="color: #666;">{indent_str}+--</span>
            <span style="color: {color};">{bar}</span>
            <span style="color: #333;"> {name}</span>
            <span style="color: #888;"> {duration*1000:.0f}ms</span>
        </div>
        """, unsafe_allow_html=True)

        # Render children
        for child in span.get("children", []):
            render_span(child, indent + 1)

    # Render all top-level spans
    for span in trace["spans"]:
        render_span(span)

    # Link to Jaeger
    st.markdown("""
    <div style="margin-top: 10px;">
        <a href="http://localhost:16686" target="_blank" style="
            color: #1f77b4;
            text-decoration: none;
        ">View detailed trace in Jaeger</a>
    </div>
    """, unsafe_allow_html=True)


def render_metrics_bar(metrics: dict):
    """Render metrics bar at the bottom."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Time", f"{metrics.get('total_time', 0)*1000:.0f}ms")
    with col2:
        st.metric("LLM Time", f"{metrics.get('llm_time', 0)*1000:.0f}ms")
    with col3:
        st.metric("DB Time", f"{metrics.get('db_time', 0)*1000:.0f}ms")
    with col4:
        st.metric("Search Time", f"{metrics.get('search_time', 0)*1000:.0f}ms")


def render_code_block(code: str, language: str = "python"):
    """Render syntax-highlighted code block."""
    st.code(code, language=language)


def render_source_card(title: str, url: str, snippet: str):
    """Render a documentation source card."""
    with st.expander(f"{title}"):
        st.markdown(snippet[:300] + "..." if len(snippet) > 300 else snippet)
        st.markdown(f"[Read more]({url})")
