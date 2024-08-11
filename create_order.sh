#!/usr/bin/env bash

curl -H "Content-Type: application/json" \
http://localhost:5000/api/order -d '{
  "user_id": "123", 
  "items": [{
    "item_id": "sku001", "quantity": 1
  }],
  "amount": "49.99",
  "payment_method": "credit_card",
  "shipping_address": "10 Main Street, CA"
}'
