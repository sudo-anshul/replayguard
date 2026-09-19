"""Fulfill queued stationery dispatch requests through an injected gateway.

The application consumes its own business event. The queue envelope and the
gateway's transport are integration details outside this module.
"""

from collections.abc import Callable, Mapping
from typing import Any


def make_dispatch_worker(fulfillment_gateway: Callable[..., dict[str, Any]]):
    """Return a handler for ``dispatch.ready.v1`` business events.

    ``fulfillment_gateway(payload, idempotency_key=...)`` accepts a stable
    dispatch reference and normalized fulfillment details. It must enforce
    its key atomically and reject changed details under a previously used key.
    A missing response may mean fulfillment committed; callers can retry the
    same business event. This worker deliberately leaves gateway errors visible
    to the queue consumer, which must not acknowledge a failed invocation.
    """

    def handle(event: Mapping[str, Any]) -> dict[str, Any]:
        if event.get("kind") != "dispatch.ready.v1":
            raise ValueError("Unsupported DispatchDesk event")
        dispatch = event["dispatch"]
        reference = dispatch["reference"]
        item = dispatch["item"]
        code, units = item["code"], item["units"]
        shipping = dispatch["shipping"]
        service, zone = shipping["service"], shipping["zone"]

        if any(not isinstance(value, str) or not value for value in (reference, code, service, zone)):
            raise ValueError("Dispatch reference, item code and shipping details are required")
        if isinstance(units, bool) or not isinstance(units, int) or units < 1:
            raise ValueError("Dispatch quantity must be a positive integer")

        payload = {
            "reference": reference,
            "product_code": code,
            "units": units,
            "shipping": {"service": service, "zone": zone},
        }
        receipt = fulfillment_gateway(payload, idempotency_key=f"dispatchdesk:{reference}")
        return {"dispatch_reference": reference, "fulfillment": receipt}

    return handle
