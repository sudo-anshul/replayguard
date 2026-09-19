#!/usr/bin/env python3
"""Deploy only tagged lab resources. No public experiment API is created."""
import argparse, json, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--profile')
p.add_argument('--region', default='us-east-1')
p.add_argument('--stack', default='replayguard-lab')
p.add_argument('--hours', type=int, choices=range(1, 49), default=24)
p.add_argument('--experiment', choices=('baseline', 'key-scope'), default='baseline')
a = p.parse_args()
if a.experiment == 'key-scope' and a.hours != 1:
    p.error('The key-scope experiment requires --hours 1')
base = ['aws', '--no-cli-pager', '--region', a.region]
if a.profile: base += ['--profile', a.profile]
subprocess.run(base + ['sts','get-caller-identity'], check=True, stdout=subprocess.DEVNULL)
limits = json.loads(subprocess.run(base + ['lambda','get-account-settings','--output','json'], check=True, capture_output=True, text=True).stdout)['AccountLimit']
reservation = 2 if limits.get('UnreservedConcurrentExecutions', 0) >= 104 else -1
if reservation == -1:
    print('Small account concurrency quota: using SQS maximum concurrency 2; Lambda reserved slots require 100 unreserved slots. The private experiment remains bounded by its queue mapping.', flush=True)
subprocess.run([sys.executable, str(ROOT/'infra/build_template.py'), '--experiment', a.experiment], cwd=ROOT, check=True)
expiry = int(time.time()) + a.hours * 3600
print(f'Deploying {a.stack} in {a.region}; processing expires after {a.hours} hours.', flush=True)
print('Finite private lab: two Lambdas, SQS + DLQ, one capped DynamoDB table. Expiry is a processing guard, not resource deletion or a billing cap.', flush=True)
template = ROOT / ('infra/template-key-scope.json' if a.experiment == 'key-scope' else 'infra/template.json')
tags = ['Project=ReplayGuard', 'Purpose=FirstCommitFailureLab']
if a.experiment == 'key-scope': tags.append('Experiment=key-scope')
subprocess.run(base + ['cloudformation','deploy','--stack-name',a.stack,'--template-file',str(template),'--capabilities','CAPABILITY_IAM','--parameter-overrides',f'LabName={a.stack}',f'LabExpiresAt={expiry}',f'ReservedConcurrency={reservation}','--tags'] + tags + ['--no-fail-on-empty-changeset'], check=True)
r = subprocess.run(base + ['cloudformation','describe-stacks','--stack-name',a.stack,'--query','Stacks[0].Outputs','--output','json'],check=True,capture_output=True,text=True)
outputs = {o['OutputKey']:o['OutputValue'] for o in json.loads(r.stdout)}
(ROOT/('deployment-key-scope.local.json' if a.experiment == 'key-scope' else 'deployment.local.json')).write_text(json.dumps(outputs,indent=2)+'\n')
runner = 'run_key_case.py' if a.experiment == 'key-scope' else 'run_case.py'
print('Deployment ready. Run: python scripts/'+runner+' --stack '+a.stack+' --region '+a.region+(' --profile '+a.profile if a.profile else ''))
if a.experiment == 'key-scope':
    print('The v2 runner automatically disables and deletes the verified tagged experiment, including after a collection/export failure. The separate Amplify host is never its cleanup target.')
