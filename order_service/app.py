import random
import requests
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///example.db'
db = SQLAlchemy(app)

# Configure tracer
trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: "order-service"})
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
SQLAlchemyInstrumentor().instrument()
RequestsInstrumentor().instrument()

# Example model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(80))

@app.route('/')
def root():
    print('os')
    return 'order-service'

@app.route('/create_order')
def create_order():
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("create_order"):
        # Access the current span
        current_span = trace.get_current_span()

        # Get the trace ID from the current span
        trace_id = current_span.get_span_context().trace_id

        # Format the trace ID into a hexadecimal string
        trace_id_hex = format(trace_id, '032x')

        # Log the trace ID
        app.logger.info(f"logged trace_id={trace_id_hex}")

        # Start a new span for the database operation
        randomid = random.randint(0,4)
        with tracer.start_as_current_span("database_operation") as span:
            sql_query = "INSERT INTO order (description) VALUES ('New Order')"
            span.set_attribute("db.statement", sql_query)  # Add SQL query to span

            new_order = Order(description=f'New Order {randomid}')
            db.session.add(new_order)
            db.session.commit()

        # Simulate some processing
        return f"Order created with id {new_order.id}", 200

@app.route('/list_payments')
def list_payments():
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("list_payments"):
        # Make a traced request to the Payment service
        response = requests.get("http://payment-service:5000/process_payment")

    return "Payments listed", 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
