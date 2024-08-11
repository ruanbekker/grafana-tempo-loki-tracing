# grafana-tempo-loki-tracing
Grafana Distributed Tracing Example with: Tempo, Prometheus, Loki, Grafana and Python Flask

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/c0431d21-e7df-4d2b-a0f6-f1ed1f222eaf)

## Getting Started

Boot the stack:

```bash
make up
```

The datasources will be auto-configured defined in `configs/grafana/datasources.yaml`.

## Example Request

Run the request in `./create_order.sh`:

```bash
./create_order.sh
```

The response will be similar to the following:

```json
{
  "message": "Order 119 created and payment authorized",
  "status": "success",
  "trace_id": "25fb067b54465ea4ccecea93694c8824"
}
```

Logs using `make logs`:

```bash
api-gateway        | [2024-08-11 20:28:42,387] DEBUG in app: api-gateway received post request
api-gateway        | [2024-08-11 20:28:42,388] DEBUG in app: api-gateway makes a request to order-service trace_id=b6512704d84b6892c72f4b0706ba6d06
order-service      | [2024-08-11 20:28:42,397] DEBUG in app: order-service received a post request
order-service      | [2024-08-11 20:28:42,398] DEBUG in app: order-service makes a post request to inventory-service trace_id=b6512704d84b6892c72f4b0706ba6d06
inventory-service  | [2024-08-11 20:28:42,408] DEBUG in app: inventory-service received a post request
inventory-service  | [2024-08-11 20:28:42,409] DEBUG in app: inventory-service about to make a database query. trace_id=b6512704d84b6892c72f4b0706ba6d06
inventory-service  | [2024-08-11 20:28:42,424] DEBUG in app: the availability in the inv db is 96
warehouse-service  | [2024-08-11 20:28:42,434] DEBUG in app: warehouse-service received a post request
warehouse-service  | [2024-08-11 20:28:42,435] INFO in app: warehouse-service about to make a database query. trace_id=b6512704d84b6892c72f4b0706ba6d06
warehouse-service  | 192.168.128.8 - - [11/Aug/2024 20:28:42] "POST /warehouse/reserve HTTP/1.1" 200 -
inventory-service  | 192.168.128.12 - - [11/Aug/2024 20:28:42] "POST /inventory/check HTTP/1.1" 200 -
payment-service    | [2024-08-11 20:28:42,469] INFO in app: payment-service logged trace_id=b6512704d84b6892c72f4b0706ba6d06
fraud-service      | [2024-08-11 20:28:42,479] INFO in app: fraud-service logged trace_id=b6512704d84b6892c72f4b0706ba6d06
fraud-service      | [2024-08-11 20:28:42,480] INFO in app: Transaction passed fraud check: order_id=754, user_id=123
fraud-service      | 192.168.128.9 - - [11/Aug/2024 20:28:42] "POST /fraud/check HTTP/1.1" 200 -
payment-service    | 192.168.128.12 - - [11/Aug/2024 20:28:42] "POST /payment/authorize HTTP/1.1" 200 -
order-service      | 192.168.128.13 - - [11/Aug/2024 20:28:42] "POST /order HTTP/1.1" 200 -
api-gateway        | 192.168.128.1 - - [11/Aug/2024 20:28:42] "POST /api/order HTTP/1.1" 200 -
```

## Screenshots

Explore traces:

<img width="1337" alt="image" src="https://github.com/user-attachments/assets/bbe42a3a-749a-4e61-b201-0b5e02bf98c3">

Query our cluster and Table view:

<img width="1332" alt="image" src="https://github.com/user-attachments/assets/0ec28565-e391-42ac-98a5-53f7c2ccb458">

Node Graph:

<img width="1336" alt="image" src="https://github.com/user-attachments/assets/6007a689-c977-4dbb-baa1-6a71e6d79c2d">

When we use the `order-service` container logs in Loki:

<img width="1336" alt="image" src="https://github.com/user-attachments/assets/aaf41cc4-25fc-4943-a2b0-a69e083d0541">

## Extras

With `span.set_attribute` we can enrich some of the visuals:

```python
        with tracer.start_as_current_span("query_inventory_database") as span:
            inventory_item = Inventory.query.filter_by(id=item_id).first()
            sql_query = f"SELECT * FROM inventory WHERE item_id = {item_id}"
            span.set_attribute("db.query", sql_query)
            span.set_attribute("inventory.item_id", item_id)
            span.set_attribute("inventory.requested_quantity", quantity)
            span.set_attribute("inventory.availability", inventory_item.availability)
```

Produces:

<img width="1234" alt="image" src="https://github.com/user-attachments/assets/15c5470b-dc3e-4db1-9bbd-419b0c0fe78c">


