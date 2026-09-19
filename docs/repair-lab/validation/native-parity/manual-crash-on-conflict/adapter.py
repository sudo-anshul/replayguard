def build(e):
 seen=set()
 def handle(d):
  oid=d["order"]["orderId"]
  if oid in seen: raise e.CrashAfterCommit("manual, no harness injection")
  seen.add(oid)
  return e.fulfill(d["order"],key=oid)
 return handle
