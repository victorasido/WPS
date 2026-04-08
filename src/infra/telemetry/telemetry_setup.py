import os
import logging
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

def setup_telemetry(service_name: str = "wordsigner-pipeline"):
    """
    Configure OpenTelemetry with safe fallbacks. 
    Maintains flow integrity if Jaeger is unreachable.
    """
    # Fallback to local jaeger if run outside Docker
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    
    resource = Resource(attributes={
        "service.name": service_name,
        "environment": os.getenv("APP_ENV", "production")
    })
    
    provider = TracerProvider(resource=resource)
    
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=True
        )
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)
    except Exception as e:
        logger.warning(f"Failed to initialize telemetry exporter: {e}")
        # Safe failure: trace provider will just act as a no-op locally
        
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

# Expose a singleton tracer for the services
tracer = setup_telemetry()
