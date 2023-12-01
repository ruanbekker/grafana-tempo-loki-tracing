# grafana-tempo-loki-tracing
Grafana Distributed Tracing Example with: Tempo, Prometheus, Loki, Grafana and Python Flask

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/c0431d21-e7df-4d2b-a0f6-f1ed1f222eaf)

## Getting Started

Boot the stack:

```bash
docker compose up --build -d || docker-compose up -d
```

The datasources will be auto-configured defined in `configs/grafana/datasources.yaml`.

## Example Requests

Requests:

```bash
$ curl http://localhost:5002/process_payment
Payment processed 

$ curl http://localhost:5001/create_order
Order created with id 1 

$ curl http://localhost:5001/list_payments
Payments listed 
```

Logs:

```bash
order-service  | [2023-11-30 05:33:07,334] INFO in app: Trace ID: 1660e64b3807719aa4898445766895b8
order-service  | 172.18.0.1 - - [30/Nov/2023 05:33:07] "GET /create_order HTTP/1.1" 200 -
payment-service  | [2023-11-30 05:33:18,883] INFO in app: Trace ID: 335c0cd1cd947c3de92b7cc9a06386e9
payment-service  | 172.18.0.1 - - [30/Nov/2023 05:33:18] "GET /process_payment HTTP/1.1" 200 -
```

## Screenshots

Explore traces:

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/3c3d4823-3d21-468a-9af7-568b2b161b10)

Query:

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/cac612f6-1de8-4008-8ab9-a571b1f41bd1)

Node Graph:

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/c83057d5-e1a0-4e89-a3b5-ea83645211d4)

When we use the `payment-service` container logs in Loki:

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/d2f79115-45d0-4298-8301-636a481b23f5)

## Extras

With `span.set_attribute` we can enrich some of the visuals:

```python
        with tracer.start_as_current_span("database_operation") as span:
            sql_query = "INSERT INTO order (description) VALUES ('New Order')"
            span.set_attribute("db.statement", sql_query)  # Add SQL query to span
```

Produces:

![image](https://github.com/ruanbekker/grafana-tempo-loki-tracing/assets/567298/1c3ecd1e-fa48-4dc5-8caf-ce7a244c6fb3)
