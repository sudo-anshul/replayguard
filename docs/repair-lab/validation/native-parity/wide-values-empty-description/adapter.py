def build(e):
 return lambda d:e.fulfill(d["order"],key=d["order"]["orderId"])
