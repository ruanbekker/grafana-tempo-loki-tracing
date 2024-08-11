import os
import sys
import time
import random
import requests
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
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
CHAOS_MONKEY_ENABLED = os.getenv('CHAOS_MONKEY_ENABLED', False)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////sqlite.db'
db = SQLAlchemy(app)

# Configure tracer
trace.set_tracer_provider(TracerProvider(
    resource=Resource.create({SERVICE_NAME: os.environ['SERVICE_NAME']})
))

# Set up the OTLP exporter
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

# Inventory model
class Inventory(db.Model):
    id = db.Column(db.String, primary_key=True)
    description = db.Column(db.String(80))
    availability = db.Column(db.Integer)

def chaos_monkey():
    if CHAOS_MONKEY_ENABLED:
        time.sleep(random.random())
    return CHAOS_MONKEY_ENABLED

@app.route('/inventory/check', methods=['POST'])
def inventory_check():
    app.logger.debug('inventory-service received a post request')
    payload = request.get_json()
    item_id = payload['item_id']
    quantity = payload['quantity']
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("check_availability"):
        # Access the current span
        current_span = trace.get_current_span()

        # Get the trace ID from the current span
        trace_id = current_span.get_span_context().trace_id

        # Format the trace ID into a hexadecimal string
        trace_id_hex = format(trace_id, '032x')

        # Log the trace ID
        app.logger.info(f"inventory-service about to make a database query. trace_id={trace_id_hex}")

        with tracer.start_as_current_span("query_inventory_database") as span:
            inventory_item = Inventory.query.filter_by(id=item_id).first()
            sql_query = f"SELECT * FROM inventory WHERE item_id = {item_id}"
            span.set_attribute("db.query", sql_query)
            span.set_attribute("inventory.item_id", item_id)
            span.set_attribute("inventory.requested_quantity", quantity)

            if inventory_item and inventory_item.availability >= quantity:
                # Reduce the availability with the quantity amount
                inventory_item.availability -= quantity
                db.session.commit()
                app.logger.debug(f'the availability in the inv db is {inventory_item.availability}')
                # Make the call to Warehouse Service
                chaos_monkey()
                with tracer.start_as_current_span("inventory_to_warehouse_call") as span:
                    span.set_attribute("inventory.item_id", item_id)
                    span.set_attribute("inventory.requested_quantity", quantity)
                    warehouse_url = 'http://warehouse-service:5000/warehouse/reserve'
                    span.set_attribute("inventory.warehouse_url", warehouse_url)

                    with tracer.start_as_current_span("http_post_warehouse_reserve") as http_span:
                        try:
                            response = requests.post(
                                warehouse_url,
                                json={"item_id": item_id, "quantity": quantity}
                            )
                            chaos_monkey()
                            http_span.set_attribute("http.method", "POST")
                            http_span.set_attribute("http.url", warehouse_url)
                            http_span.set_attribute("http.status_code", response.status_code)
                            http_span.set_attribute("http.request_body", f"item_id={item_id}, quantity={quantity}")
                            http_span.set_attribute("http.response_body", response.text)
                            http_span.set_attribute("http.response_time", response.elapsed.total_seconds())

                            with tracer.start_as_current_span("warehouse_response_handling") as resp_span:
                                if response.status_code == 200:
                                    resp_span.set_attribute("response.status", "success")
                                    resp_span.set_attribute("response.message", "Reservation successful")
                                else:
                                    app.logger.debug(f'[inventory-service] {response.status_code} status code : {response.text}') 
                                    resp_span.set_attribute("response.status", "failure")
                                    resp_span.set_attribute("response.message", response.text)

                        except requests.exceptions.RequestException as e:
                            http_span.set_attribute("http.error", str(e))
                            app.logger.error(f"Error while calling warehouse service: {e}")
                            return jsonify({"status": "failure", "message": "Error contacting warehouse service"}), 500

                return jsonify({"status": "success", "message": "Inventory available and reserved"}), 200
            else:
                return jsonify({"status": "failure", "message": "Insufficient inventory"}), 400
        
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        insert_query = text(
            "INSERT OR IGNORE INTO inventory (id, description, availability) VALUES (:id, :description, :availability)"
        )
        db.session.execute(
            insert_query,
            {"id": "sku001", "description": "test inventory", "availability": 10},
        )
        db.session.commit()
    app.run(debug=True, host='0.0.0.0', port=5000)
