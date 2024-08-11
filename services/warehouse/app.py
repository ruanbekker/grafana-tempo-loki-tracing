import os
import sys
import time
import random
import requests
from datetime import datetime
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

# Configure OpenTelemetry trace provider to 
# use BatchSpanProcessor with the OTLP exporter.
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

# Instrument Flask
FlaskInstrumentor().instrument_app(app)
SQLAlchemyInstrumentor().instrument()
RequestsInstrumentor().instrument()

# Warehouse Reservations Model
class Reservations(db.Model):
    id = db.Column(db.String, primary_key=True)
    description = db.Column(db.String(80))
    availability = db.Column(db.Integer)

# Warehouse Inventory Model
class WarehouseInventory(db.Model):
    id = db.Column(db.String, primary_key=True)
    item_id = db.Column(db.String, nullable=False)
    warehouse_location = db.Column(db.String, nullable=False)
    available_quantity = db.Column(db.Integer, nullable=False)
    reserved_quantity = db.Column(db.Integer, default=0)
    reservation_timestamp = db.Column(db.DateTime, nullable=True)
    reservation_status = db.Column(db.String, nullable=True)

@app.route('/warehouse/reserve', methods=['POST'])
def reserve_item():
    app.logger.debug('warehouse-service received a post request')
    payload = request.get_json()
    item_id = payload['item_id']
    quantity = payload['quantity']
    warehouse_location = "Warehouse-A"
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("reserve_item"):
        # Access the current span
        current_span = trace.get_current_span()

        # Get the trace ID from the current span
        trace_id = current_span.get_span_context().trace_id

        # Format the trace ID into a hexadecimal string
        trace_id_hex = format(trace_id, '032x')

        # Log the trace ID
        app.logger.info(f"warehouse-service about to make a database query. trace_id={trace_id_hex}")

        # Start a new span for the database operation
        randomid = random.randint(0,4)

        with tracer.start_as_current_span("database_operation") as span:
            warehouse_item = WarehouseInventory.query.filter_by(item_id=item_id, warehouse_location=warehouse_location).first()
            if warehouse_item and warehouse_item.available_quantity >= quantity:
                warehouse_item.available_quantity -= quantity
                warehouse_item.reserved_quantity += quantity
                warehouse_item.reservation_timestamp = datetime.utcnow()
                warehouse_item.reservation_status = "reserved"
                db.session.commit()
                sql_query =  f"UPDATE warehouse_inventory SET available_quantity = {warehouse_item.available_quantity}, reserved_quantity = {warehouse_item.reserved_quantity} WHERE id = {warehouse_item.id}"
                span.set_attribute("db.query", sql_query)
                return jsonify({"status": "success", "message": f"Reserved {quantity} of item {item_id}"}), 200
            else:
                return jsonify({"status": "failure", "message": "Insufficient inventory in warehouse"}), 400

def seed_warehouse_inventory():
    with app.app_context():
        db.create_all()

        # Data to seed the database
        warehouse_items = [
            WarehouseInventory(
                id="sku001_warehouseA",
                item_id="sku001",
                warehouse_location="Warehouse-A",
                available_quantity=10,
                reserved_quantity=0,
                reservation_timestamp=None,
                reservation_status=None
            ),
            WarehouseInventory(
                id="sku002_warehouseA",
                item_id="sku002",
                warehouse_location="Warehouse-A",
                available_quantity=30,
                reserved_quantity=0,
                reservation_timestamp=None,
                reservation_status=None
            ),
            WarehouseInventory(
                id="sku001_warehouseB",
                item_id="sku001",
                warehouse_location="Warehouse-B",
                available_quantity=40,
                reserved_quantity=0,
                reservation_timestamp=None,
                reservation_status=None
            ),
        ]

        # Loop over warehouse items
        for item in warehouse_items:
            # Check if the item already exists in the database
            existing_item = WarehouseInventory.query.filter_by(id=item.id).first()
            if existing_item:
                print(f"Item with id {item.id} already exists. Skipping.")
            else:
                db.session.add(item)
        
        # Commit to the db
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        seed_warehouse_inventory()
    app.run(debug=True, host='0.0.0.0', port=5000)
