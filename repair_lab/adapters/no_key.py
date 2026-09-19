"""Intentionally unsafe: each delivery submits a new fulfillment."""


def build(effects):
    def handle(delivery):
        return effects.fulfill(delivery["order"], key=None)
    return handle
