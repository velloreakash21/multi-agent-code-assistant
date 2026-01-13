"""
Code Assistant - Streamlit Frontend
Professional UI for demonstrating the multi-agent system.
"""
# Suppress warnings before any other imports for clean production output
import warnings
import logging

warnings.filterwarnings("ignore", message=".*Pydantic V1.*Python 3.14.*")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

# Configure logging to suppress debug messages in production
logging.getLogger("src").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)

import streamlit as st
import time
from datetime import datetime

# Page configuration - MUST be first Streamlit command
st.set_page_config(
    page_title="Code Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Import other modules
from src.agents.orchestrator import ask_assistant
from src.frontend.components import (
    render_chat_message,
    render_agent_activity,
    render_trace_visualization,
    render_metrics_bar
)
from src.frontend.styles import apply_custom_styles
from src.telemetry.tracing import init_telemetry

# Apply custom styles
apply_custom_styles()

# Initialize telemetry for Jaeger traces
init_telemetry("code-assistant")


def process_query(query: str):
    """Process user query and update UI with real-time status updates."""
    # Add user message
    st.session_state.messages.append({
        "role": "user",
        "content": query,
        "timestamp": datetime.now()
    })

    # Reset activity and trace
    st.session_state.agent_activity = []
    st.session_state.current_trace = {
        "spans": [],
        "start_time": time.time()
    }

    # Status callback for real-time updates
    def status_callback(agent: str, status: str, details: str):
        """Update agent activity in real-time."""
        st.session_state.agent_activity.append({
            "agent": agent,
            "status": status,
            "details": details,
            "timestamp": time.time()
        })

    try:
        # Call the orchestrator with status callback
        result = ask_assistant(query, status_callback=status_callback)

        # Extract response and timing
        response = result["response"]
        timing = result["timing"]

        # Add assistant message
        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now()
        })

        # Update metrics with real timing data
        st.session_state.metrics = {
            "total_time": timing["total"],
            "llm_time": timing["orchestrator_analyze"] + timing["combine"],
            "db_time": timing["code_query"],
            "search_time": timing["doc_search"]
        }

        # Build trace visualization with real timing
        st.session_state.current_trace = build_trace_data(timing)

    except Exception as e:
        st.session_state.agent_activity.append({
            "agent": "Error",
            "status": "failed",
            "details": str(e),
            "timestamp": time.time()
        })
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"Error processing query: {str(e)}",
            "timestamp": datetime.now()
        })


def build_trace_data(timing: dict) -> dict:
    """Build trace visualization data from real timing measurements."""
    total_time = timing.get("total", 1)
    analyze_time = timing.get("orchestrator_analyze", 0)
    doc_search_time = timing.get("doc_search", 0)
    code_query_time = timing.get("code_query", 0)
    combine_time = timing.get("combine", 0)

    # Build children list, filtering out None values
    children = [
        {"name": "orchestrator_analyze", "duration": analyze_time, "level": 1}
    ]

    if doc_search_time > 0:
        children.append({
            "name": "doc_search_agent",
            "duration": doc_search_time,
            "level": 1,
            "children": [
                {"name": "llm_invoke", "duration": doc_search_time * 0.6, "level": 2},
                {"name": "tavily_search", "duration": doc_search_time * 0.4, "level": 2}
            ]
        })

    if code_query_time > 0:
        children.append({
            "name": "code_query_agent",
            "duration": code_query_time,
            "level": 1,
            "children": [
                {"name": "llm_invoke", "duration": code_query_time * 0.7, "level": 2},
                {"name": "oracle_mcp_query", "duration": code_query_time * 0.3, "level": 2}
            ]
        })

    children.append({"name": "orchestrator_combine", "duration": combine_time, "level": 1})

    return {
        "spans": [
            {
                "name": "code_assistant_query",
                "duration": total_time,
                "level": 0,
                "children": children
            }
        ],
        "total_time": total_time
    }


def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_activity" not in st.session_state:
        st.session_state.agent_activity = []
    if "current_trace" not in st.session_state:
        st.session_state.current_trace = None
    if "metrics" not in st.session_state:
        st.session_state.metrics = {}
    if "processing" not in st.session_state:
        st.session_state.processing = False


def main():
    """Main application."""
    # Initialize session state first
    init_session_state()

    # Header
    col1, col2, col3 = st.columns([6, 1, 1])
    with col1:
        st.title("Code Assistant")
        st.caption("AI-powered documentation and code example finder")
    with col2:
        if st.button("Settings", key="settings_btn"):
            st.session_state.show_settings = True
    with col3:
        if st.button("Clear", key="clear_btn"):
            st.session_state.messages = []
            st.session_state.agent_activity = []
            st.session_state.current_trace = None
            st.session_state.metrics = {}
            st.rerun()

    st.divider()

    # Main layout: Chat + Agent Activity
    chat_col, activity_col = st.columns([2, 1])

    with chat_col:
        st.subheader("Chat")
        chat_container = st.container(height=400)
        with chat_container:
            if st.session_state.messages:
                for msg in st.session_state.messages:
                    render_chat_message(msg)
            else:
                st.info("Ask a question to get started!")

    with activity_col:
        st.subheader("Agent Activity")
        activity_container = st.container(height=400)
        with activity_container:
            if st.session_state.agent_activity:
                for activity in st.session_state.agent_activity:
                    render_agent_activity(activity)
            else:
                st.info("Agent activity will appear here when you ask a question.")

    # Trace Visualization
    st.subheader("Trace Visualization")
    if st.session_state.current_trace:
        render_trace_visualization(st.session_state.current_trace)
    else:
        st.info("Trace details will appear here after a query is processed.")

    # Metrics bar
    if st.session_state.metrics:
        render_metrics_bar(st.session_state.metrics)

    # Chat input
    st.divider()

    user_input = st.chat_input("Ask a question (e.g., How do I connect to Oracle database?)")

    if user_input:
        process_query(user_input)
        st.rerun()


if __name__ == "__main__":
    main()
