# AWS key-scope: a real integration failure and its local regression

The first v2 AWS run exposed an error that the initial in-memory unit fixture
missed. DynamoDB's boto3 resource returns numbers as `Decimal`, including an
integer quantity of one. The provider attempted to include the existing order
in its `payload_conflict` JSON log. `json.dumps` raised `TypeError` before that
event could be emitted or the intended terminal rejection returned.

The [limited CloudWatch diagnostic](provider-diagnosis.json) preserves two
actual error events from that run. It was copied unchanged after checking for
credential patterns, account identifiers and private workstation paths. Its
`/var/task` and `/var/lang` paths refer to the Lambda runtime. This is an error
excerpt, not the complete AWS experiment evidence.

The first experiment's immutable source and report are in
[aws-key-scope-attempt-1.zip](../../../web/aws-key-scope-attempt-1.zip), SHA-256
`ea41a00d1a9a753c8ea3165110ccfad657aebb21a2ad5b14214182d59cc775b4`.
Run `85500aff-3d08-483e-9e63-78a9723eb67a` ended **unresolved** after the rejected
order instead retried into the DLQ. The SKU candidate's business evidence
remained **incomplete**: a zero receipt count alone did not establish a proved
terminal rejection. The raw counts looking correct did not make the run pass.

The original report also retains its unconfirmed cleanup state: the cleanup
poller encountered an exception with absent SDK response metadata. A separate
[later cleanup observation](../../../evidence/key-scope-20260920-cleanup-followup.json)
confirmed the exact original stack reached `DELETE_COMPLETE` at
19:07:27 UTC on September 19. That follow-up resolves cleanup only; it does not
repair the failed experiment or rewrite its report.

## Narrow repair

The receiver now normalizes only a **finite, integral stored quantity from 1
through 100** from `Decimal` to `int`, then validates the complete stored order.
It uses that normalized copy for comparison and conflict logging. It does not
stringify arbitrary values, coerce fractional quantities, or change the stored
observation. Missing fields, unexpected fields, invalid identifiers, booleans,
strings and unsupported numbers fail closed.

The cleanup poller separately tolerates absent or malformed SDK error metadata
while continuing its bounded deletion checks. That change is covered by the
standard-library unit suite, including the original `response=None` condition.

## Reproduce the SDK regression locally

[verify_sdk_regression.py](verify_sdk_regression.py) reads the old provider and
worker from the retained archive and the repaired source from `src/`. It
verifies the archive's recorded source hashes before executing either version.
The transport and ledger are local mocks, but value conversion uses boto3's
actual `TypeSerializer` and `TypeDeserializer`. AWS API calls and socket
connections are blocked during the check.

The [recorded result](validation.json) passed at **19:16:16 UTC on September
19, 2026** with Python 3.14.3 and boto3 1.42.70. All three local regression groups
passed; no AWS API or socket-connect attempt occurred:

| Source / check | Observed result |
| --- | --- |
| Archived original | A retry reused its receipt; B raised through the worker after provider `TypeError`; no payload-conflict log |
| Repaired source | A retry reused its receipt; B returned the intended rejection; one receipt remained and the conflict log held a native JSON integer |
| Input limits | Ten invalid quantity values and four invalid order shapes rejected; three supported Decimal quantities normalized without modifying their source values |

From the repository root, use an existing virtual environment containing the
optional AWS SDK dependency from `requirements.txt`:

```sh
.venv/bin/python docs/repair-lab/aws-key-scope/verify_sdk_regression.py \
  --output /tmp/replayguard-sdk-regression-new.json
```

No credentials are required. The script refuses to overwrite an existing
validation output. If creating a new virtual environment is necessary, install
`requirements.txt` using the repository's documented setup; that dependency
installation is separate from this network-blocked check.

The ordinary unit suite remains SDK-free:

```sh
python3 -I -S -m unittest discover -s tests -p test_aws_key_scope.py
```

Its local DynamoDB fixture now recursively converts integer values to the
standard-library `Decimal` type, matching the separately demonstrated boto3
deserialization behavior. Unit SDK interfaces are local stubs. This prevents a
repeat of the original fixture blind spot without requiring site packages.

These results validate local serialization and error handling. They do not
establish a new AWS run, SQS scheduling, real cloud cleanup or external
fulfillment. A fresh separately recorded AWS experiment is required for those
claims.
