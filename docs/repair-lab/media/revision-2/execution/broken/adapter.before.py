def build(effects):
    def handle(delivery):
        order = delivery["order"]
        return effects.fulfill(order, key=None)
    return handle
