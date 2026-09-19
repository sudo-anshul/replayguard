# DispatchDesk

A small independent application example: a stationery shop queues a dispatch
when an order is ready. Different orders may contain the same SKU. A dispatch
reference remains stable across queue retries; a queue delivery ID does not.

The original application consumes this business event:

```json
{
  "kind": "dispatch.ready.v1",
  "dispatch": {
    "reference": "cedar-paper/DD-7319",
    "item": {"code": "NOTEBOOK-LINEN-A5", "units": 2},
    "shipping": {"service": "ground", "zone": "IN-SOUTH"}
  }
}
```

`worker.py` accepts an injected fulfillment gateway, sends normalized dispatch
details with a stable business key, and allows gateway failures to propagate.
The gateway contract requires atomic reuse of the same key for the same
payload and rejection of a changed payload under that key. A response loss
after acceptance is therefore retried with the same dispatch reference.

`adapter.py` is a thin bridge from ReplayGuard's public `build(effects)` API to
the original event and gateway contract. The application imports no ReplayGuard
code and knows no receipt store, fault schedule, assertion labels or evaluator
state. The adapter requires canonical `orderId`, `sku`, `quantity` plus
`attributes.service` and `attributes.destinationZone` in a lab delivery.

Both files use only the Python standard library. This is an independently
authored synthetic integration fixture, not an existing customer application,
commercial shipping provider or claim of user adoption. No shipment is made.
The local effect gateway's atomic-key guarantee is a stated assumption;
providers lacking that guarantee need a separate design and remain outside
this example's proof.
