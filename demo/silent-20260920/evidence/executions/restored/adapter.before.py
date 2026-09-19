"""Reference repair: one immutable fulfillment per business order."""


def build(effects):
    def handle(delivery):
        order = delivery["order"]
        return effects.fulfill(order, key=order["orderId"])
    return handle
