def build(e):
 def handle(d):
  order=dict(d["order"],attributes={"one":1.0,"zero":-0.0})
  return e.fulfill(order,key=order["orderId"])
 return handle
