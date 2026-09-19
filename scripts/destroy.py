#!/usr/bin/env python3
"""Delete only the named ReplayGuard stack after validating its project tag."""
import argparse, json, subprocess
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--profile'); p.add_argument('--region',default='us-east-1'); p.add_argument('--stack',default='replayguard-lab')
a=p.parse_args(); base=['aws','--no-cli-pager','--region',a.region]
if a.profile: base += ['--profile',a.profile]
r=subprocess.run(base+['cloudformation','describe-stacks','--stack-name',a.stack,'--output','json'],check=True,capture_output=True,text=True)
s=json.loads(r.stdout)['Stacks'][0]
if not any(t['Key']=='Project' and t['Value']=='ReplayGuard' for t in s.get('Tags',[])):
    raise SystemExit('Refusing: this stack is not tagged Project=ReplayGuard.')
subprocess.run(base+['cloudformation','delete-stack','--stack-name',a.stack],check=True)
print('Deletion requested. AWS will delete lab queues, receipts, functions and logs. Export evidence first.')
subprocess.run(base+['cloudformation','wait','stack-delete-complete','--stack-name',a.stack],check=True)
print('Lab resources deleted.')
