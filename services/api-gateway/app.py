import os
import requests
from flask import Flask, request, jsonify
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

TEMPO_HOSTNAME = os.getenv('TEMPO_HOSTNAME', 'tempo')
TEMPO_PORT     = os.getenv('TEMPO_PORT', '4317')

app = Flask(__name__)

# Configure tracer
trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: os.environ['SERVICE_NAME']})
))

# Set up the OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint=f"{TEMPO_HOSTNAME}:{TEMPO_PORT}",
    insecure=True
)

# Configure the OpenTelemetry trace provider to 
# use a BatchSpanProcessor with an OTLP exporter.
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

# Instrument Flask
FlaskInstrumentor().instrument_app(app)
SQLAlchemyInstrumentor().instrument()
RequestsInstrumentor().instrument()

# Order Service Routes
@app.route('/api/order', methods=['POST'])
def api_create_order():
    payload = request.get_json()
    app.logger.debug('api-gateway received post request')
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("request_to_order_service"):
        current_span = trace.get_current_span()
        trace_id = current_span.get_span_context().trace_id
        trace_id_hex = format(trace_id, '032x')
        app.logger.debug(f'api-gateway makes a request to order-service trace_id={trace_id_hex}')
        response = requests.post('http://order-service:5000/order', 
            headers={"Content-Type": "application/json"},
            json=payload
        )
        if response.status_code != 200:
            app.logger.error(response.text)
        
    return jsonify(response.json()), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
