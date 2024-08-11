import os
import random
import requests
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
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
FRAUD_PERCENTAGE = os.getenv('FRAUD_PERCENTAGE', 5)
NOT_FRAUD_PERCENTAGE = os.getenv('NOT_FRAUD_PERCENTAGE', 95)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////sqlite.db'
db = SQLAlchemy(app)

# Configure tracer
trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: "fraud-service"})
))

# Set up the OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint=f"{TEMPO_HOSTNAME}:{TEMPO_PORT}",
    insecure=True
)

# Configure OpenTelemetry trace provider to 
# use BatchSpanProcessor with the OTLP exporter.
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

# Instrument Flask
FlaskInstrumentor().instrument_app(app)
SQLAlchemyInstrumentor().instrument()
RequestsInstrumentor().instrument()

# Example model
class FraudDetecton(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(20))
    user_id = db.Column(db.String(20))
    payment_method = db.Column(db.String(20))
    amount = db.Column(db.String(10))
    is_fraud = db.Column(db.Boolean)

def fraud_probability():
    decisions = { "fraud": int(FRAUD_PERCENTAGE), "not_fraud": int(NOT_FRAUD_PERCENTAGE) }
    decision = random.choice([each for each in decisions for this in range(decisions[each])])
    response = [True if decision == 'fraud' else False][0]
    return response

@app.route('/fraud/check', methods=['POST'])
def check_fraud():
    tracer = trace.get_tracer(__name__)
    payload = request.get_json()
    order_id = payload.get("order_id")
    user_id = payload.get("user_id")
    payment_method = payload.get("payment_method")
    amount = payload.get("amount")

    with tracer.start_as_current_span("check_fraud"):
        current_span = trace.get_current_span()
        trace_id = current_span.get_span_context().trace_id
        trace_id_hex = format(trace_id, '032x')
        app.logger.info(f"[fraud-service] logged trace_id={trace_id_hex}")

        # Simulate fraud detection logic
        with tracer.start_as_current_span("analyze_transaction") as span:
            span.set_attribute("fraud.order_id", order_id)
            span.set_attribute("fraud.user_id", user_id)
            span.set_attribute("fraud.payment_method", payment_method)
            span.set_attribute("fraud.amount", amount)

            # Basic Fraud detection logic
            # Randomly flag transactions as fraudulent for demonstration
            is_fraudulent = fraud_probability()
            span.set_attribute("fraud.is_fraudulent", is_fraudulent)

            # TODO: record activity to database

            if is_fraudulent:
                app.logger.warning(f"Transaction flagged as fraudulent: order_id={order_id}, user_id={user_id}")
                return jsonify({"status": "fraudulent", "message": "Transaction is fraudulent"}), 200
            else:
                app.logger.info(f"Transaction passed fraud check: order_id={order_id}, user_id={user_id}")
                return jsonify({"status": "legitimate", "message": "Transaction is legitimate"}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
