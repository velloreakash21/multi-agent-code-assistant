"""
OpenTelemetry tracing with graceful degradation.
Works even before full telemetry initialization.
"""
import logging
import os
from functools import wraps
from typing import Callable, Any, Optional
from contextlib import contextmanager

# Configure module logger
logger = logging.getLogger(__name__)

# Track if telemetry is initialized
_telemetry_initialized = False
_tracer_provider = None


def init_telemetry(service_name: str = None) -> Any:
    """Initialize OpenTelemetry. Safe to call multiple times."""
    global _telemetry_initialized, _tracer_provider

    if _telemetry_initialized:
        return _tracer_provider

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        from src.config import settings

        service_name = service_name or settings.otel_service_name

        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_endpoint,
            insecure=True
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)

        _tracer_provider = provider
        _telemetry_initialized = True

        logger.debug(f"Telemetry initialized: {service_name}")
        return provider

    except Exception as e:
        logger.debug(f"Telemetry initialization skipped: {e}")
        return None


def get_tracer(name: str):
    """Get tracer with graceful fallback."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except Exception:
        return _NoOpTracer()


class _NoOpSpan:
    """No-op span for when telemetry is not available."""
    def set_attribute(self, key, value): pass
    def add_event(self, name, attributes=None): pass
    def record_exception(self, exception): pass
    def set_status(self, status): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _NoOpTracer:
    """No-op tracer for when telemetry is not available."""
    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield _NoOpSpan()


def traced(name: str = None) -> Callable:
    """Decorator for tracing functions. Works even without telemetry."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            tracer = get_tracer(func.__module__)
            span_name = name or func.__name__
            with tracer.start_as_current_span(span_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def shutdown_telemetry():
    """Gracefully shutdown telemetry."""
    global _telemetry_initialized
    if _tracer_provider and hasattr(_tracer_provider, 'shutdown'):
        _tracer_provider.shutdown()
    _telemetry_initialized = False
