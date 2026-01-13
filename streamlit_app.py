"""
Streamlit entry point for Code Assistant.
Run with: streamlit run streamlit_app.py
"""
# Suppress warnings before any other imports for clean production output
import warnings
import sys

# Filter out Pydantic v1 compatibility warnings with Python 3.14+
warnings.filterwarnings("ignore", message=".*Pydantic V1.*Python 3.14.*")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

# Configure logging to suppress debug messages in production
import logging
logging.getLogger("src").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.frontend.app import main

if __name__ == "__main__":
    main()
