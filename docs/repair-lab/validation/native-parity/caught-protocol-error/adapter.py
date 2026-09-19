def build(e):
 try:e.fulfill({"orderId":"A","sku":"B","quantity":1})
 except RuntimeError:pass
 return lambda d:e.fulfill(d["order"],key=d["order"]["orderId"])
