"""The only DispatchDesk file that knows ReplayGuard's public adapter protocol."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def build(effects):
    # Load this candidate's sibling application, including when the pair has
    # been copied to a clean directory. No repository-root import is required.
    spec = spec_from_file_location("dispatchdesk_application", Path(__file__).with_name("worker.py"))
    application = module_from_spec(spec)
    spec.loader.exec_module(application)

    def gateway(payload, *, idempotency_key):
        order = {
            "orderId": payload["reference"],
            "sku": payload["product_code"],
            "quantity": payload["units"],
            "attributes": {
                "service": payload["shipping"]["service"],
                "destinationZone": payload["shipping"]["zone"],
            },
        }
        receipt = effects.fulfill(order, key=idempotency_key)
        return {"receipt_number": receipt["receiptId"], "new_dispatch": receipt["accepted"]}

    worker = application.make_dispatch_worker(gateway)

    def handle(delivery):
        order = delivery["order"]
        attributes = order["attributes"]
        event = {
            "kind": "dispatch.ready.v1",
            "dispatch": {
                "reference": order["orderId"],
                "item": {"code": order["sku"], "units": order["quantity"]},
                "shipping": {"service": attributes["service"], "zone": attributes["destinationZone"]},
            },
        }
        return worker(event)

    return handle
