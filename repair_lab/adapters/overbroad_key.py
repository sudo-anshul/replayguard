"""Intentionally wrong: unrelated orders sharing a SKU collide."""


def build(effects):
    def handle(delivery):
        order = delivery["order"]
        return effects.fulfill(order, key=order["sku"])
    return handle
