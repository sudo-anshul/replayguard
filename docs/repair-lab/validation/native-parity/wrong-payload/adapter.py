def build(e):
 def handle(d):
  order=dict(d["order"],quantity=999)
  return e.fulfill(order,key=order["orderId"])
 return handle
