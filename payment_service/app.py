from flask import Flask
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

app = Flask(__name__)

# Configure tracer
trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: "payment-service"})
))

# Set up the OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint="tempo:4317",
    insecure=True
    )

trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

# Instrument Flask
FlaskInstrumentor().instrument_app(app)

@app.route('/')
def root():
    print('ps')
    return 'payment-service'

@app.route('/process_payment')
def process_payment():
    with trace.get_tracer(__name__).start_as_current_span("process_payment"):
        # Access the current span
        current_span = trace.get_current_span()

        # Get the trace ID from the current span
        trace_id = current_span.get_span_context().trace_id

        # Format the trace ID into a hexadecimal string
        trace_id_hex = format(trace_id, '032x')

        # Log the trace ID
        app.logger.info(f"logged trace_id={trace_id_hex}")

        # Simulate some processing
        return "Payment processed", 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
