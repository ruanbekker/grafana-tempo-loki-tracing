import os
import sys
import random
import requests
from flask import Flask, request, jsonify
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

TEMPO_HOSTNAME = os.getenv('TEMPO_HOSTNAME', 'tempo')
TEMPO_PORT     = os.getenv('TEMPO_PORT', '4317')
FRAUD_SERVICE_URL = os.getenv('FRAUD_SERVICE_URL', 'http://fraud-service:5000')

app = Flask(__name__)

# Configure tracer
trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: "payment-service"})
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
# Instrument Flask and Requests for context propagation
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

# In-Memory database
payments_db = {}

@app.route('/payment/authorize', methods=['POST'])
def authorize_payment():
    tracer = trace.get_tracer(__name__)
    payload = request.get_json()
    order_id = payload.get("order_id")
    user_id = payload.get("user_id")
    payment_method = payload.get("payment_method")
    amount = payload.get("amount")

    with tracer.start_as_current_span("authorize_payment"):
        current_span = trace.get_current_span()
        trace_id = current_span.get_span_context().trace_id
        trace_id_hex = format(trace_id, '032x')
        app.logger.info(f"[payment-service] logged trace_id={trace_id_hex}")

        # Simulate payment authorization logic
        with tracer.start_as_current_span("validate_payment_details") as span:
            span.set_attribute("payment.order_id", order_id)
            span.set_attribute("payment.user_id", user_id)
            span.set_attribute("payment.payment_method", payment_method)
            span.set_attribute("payment.amount", amount)

            # Dummy validation logic
            if not order_id or not user_id or not payment_method or not amount:
                span.set_attribute("payment.status", "failure")
                app.logger.error(f'invalid payment details error: order_id={order_id}, user_id={user_id}, payment_method={payment_method}, amount={amount}')
                return jsonify({"status": "failure", "message": "Invalid payment details"}), 400

        # Fraud Detection Service Call
        with tracer.start_as_current_span("fraud_detection_service_call") as span:
            fraud_payload = {
                "order_id": order_id,
                "user_id": user_id,
                "payment_method": payment_method,
                "amount": amount
            }
            try:
                response = requests.post(f'{FRAUD_SERVICE_URL}/fraud/check', json=fraud_payload)
                span.set_attribute("http.method", "POST")
                span.set_attribute("http.url", f'{FRAUD_SERVICE_URL}/fraud/check')
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.request_body", str(fraud_payload))
                span.set_attribute("http.response_body", response.text)

                if response.status_code != 200 or response.json().get("status") == "fraudulent":
                    span.set_attribute("fraud_check", "failed")
                    app.logger.error(f"Fraud detection failed: {response.text}")
                    return jsonify({
                        "status": "failure",
                        "message": "Fraudulent transaction detected",
                        "category": "fraud"
                    }), 403
                else:
                    span.set_attribute("fraud_check", "passed")

            except requests.exceptions.RequestException as e:
                span.set_attribute("http.error", str(e))
                app.logger.error(f"Error while calling fraud detection service: {e}")
                return jsonify({"status": "failure", "message": "Error contacting fraud detection service"}), 500

        # Proceed with payment processing after passing fraud check
        with tracer.start_as_current_span("process_payment") as span:
            # Simulated payment processing
            payment_status = "authorized"
            payments_db[order_id] = {
                "user_id": user_id,
                "payment_method": payment_method,
                "amount": amount,
                "status": payment_status
            }
            span.set_attribute("payment.status", payment_status)

        # Return the result of the payment authorization
        return jsonify({"status": "success", "message": "Payment authorized", "order_id": order_id}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
