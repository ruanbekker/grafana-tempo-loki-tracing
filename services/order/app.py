import os
import sys
import time
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

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////sqlite.db'
db = SQLAlchemy(app)

trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: os.environ['SERVICE_NAME']})
))

otlp_exporter = OTLPSpanExporter(
    endpoint=f"{TEMPO_HOSTNAME}:{TEMPO_PORT}",
    insecure=True
)

trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

# Instrument Flask
FlaskInstrumentor().instrument_app(app)
SQLAlchemyInstrumentor().instrument()
RequestsInstrumentor().instrument()

# Order model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(80))

@app.route('/order', methods=['POST'])
def create_order():
    headers = {"Content-Type": "application/json"}
    payload = request.get_json()
    item_id = payload.get('items')[0].get('item_id')
    quantity = payload.get('items')[0].get('quantity')
    payment_method = payload.get('payment_method')
    amount = payload.get('amount')
    user_id = payload.get('user_id')

    app.logger.debug('order-service received a post request')
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

        # TODO: capture order
        order_id = random.randint(1,1000)

        # Call 1: Inventory Service: create a new span for the inventory call
        with tracer.start_as_current_span("inventory_service_call") as span:
            span.set_attribute("inventory.sku", item_id)
            span.set_attribute("inventory.requested_quantity", quantity)
            app.logger.debug(f'order-service makes a post request to inventory-service trace_id={trace_id_hex}')
            try:
                response = requests.post("http://inventory-service:5000/inventory/check", 
                    json={'item_id': item_id, 'quantity': quantity}, headers=headers
                )

                # Handle inventory service response
                if response.status_code != 200:
                    app.logger.error(f'Inventory check failed: {response.text}')
                    return jsonify({
                        "status": "failure",
                        "message": "Inventory capacity failure",
                        "trace_id": trace_id_hex
                    }), 400

            except requests.exceptions.RequestException as e:
                app.logger.error(f"Error while calling inventory service: {e}")
                return jsonify({"status": "failure", "message": "Error contacting inventory service"}), 500

        # Call 2: Payment Authorization
        with tracer.start_as_current_span("order_to_payment_authorization") as span:
            span.set_attribute("order.order_id", order_id)
            span.set_attribute("order.user_id", user_id)
            span.set_attribute("order.payment_method", payment_method)
            span.set_attribute("order.amount", amount)
            payment_url = 'http://payment-service:5000/payment/authorize'
            span.set_attribute("order.payment_url", payment_url)

            with tracer.start_as_current_span("http_post_payment_authorization") as http_span:
                try:
                    response = requests.post(
                        payment_url,
                        json={
                            "order_id": order_id,
                            "user_id": user_id,
                            "payment_method": payment_method,
                            "amount": amount
                        }
                    )

                    http_span.set_attribute("http.method", "POST")
                    http_span.set_attribute("http.url", payment_url)
                    http_span.set_attribute("http.status_code", response.status_code)
                    http_span.set_attribute("http.request_body", f"order_id={order_id}, user_id={user_id}, payment_method={payment_method}, amount={amount}")
                    http_span.set_attribute("http.response_body", response.text)
                    http_span.set_attribute("http.response_time", response.elapsed.total_seconds())

                    with tracer.start_as_current_span("payment_response_handling") as resp_span:
                        if response.status_code == 200:
                            resp_span.set_attribute("response.status", "success")
                            resp_span.set_attribute("response.message", "Payment authorized")
                        else:
                            resp_span.set_attribute("response.status", "failure")
                            resp_span.set_attribute("response.message", response.text)

                        # Handle the response from the Payment Service
                        if response.status_code == 200:
                            # Payment was authorized
                            # Update the order status, send confirmation, etc.
                            return jsonify({
                                "status": "success", 
                                "message": f"Order {order_id} created and payment authorized",
                                "trace_id": trace_id_hex
                            }), 200
                        else:
                            # Payment failed
                            app.logger.error(f'payment authorization error: {response.text}')
                            app.logger.error(f'error_reason: {response.json()}')
                            return jsonify({
                                "status": "failure",
                                "message": "Payment authorization failed",
                                "category": response.json().get('category'),
                                "trace_id": trace_id_hex
                            }), 400

                except requests.exceptions.RequestException as e:
                    http_span.set_attribute("http.error", str(e))
                    app.logger.error(f"Error while calling payment service: {e}")
                    return jsonify({"status": "failure", "message": "Error contacting payment service"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
