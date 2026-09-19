/* Supported consistency checks for untrusted AWS JSON. Never an AWS attestation. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ReplayGuardEvidence = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MODES = ['vulnerable', 'repaired'];
  const CLAIM_STATES = new Set(['passed', 'incomplete', 'unresolved']);
  const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
  const SHA256 = /^[a-f0-9]{64}$/;
  const WORKER_STAGES = new Set(['received', 'fulfillment_succeeded', 'fault_injected', 'failed', 'completed']);
  const PROVIDER_STAGES = new Set(['accepted', 'reused', 'payload_conflict']);
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);

  function fail(path, message, code = 'MALFORMED_EVIDENCE') {
    const error = new Error(path + ': ' + message);
    error.name = 'EvidenceContractError'; error.code = code; error.path = path;
    throw error;
  }
  function object(value, path) {
    if (!isObject(value)) fail(path, 'must be an object, not null, an array, or another type. Import a complete AWS JSON export.');
  }
  function string(value, path, maximum = 2000) {
    if (typeof value !== 'string' || value.length === 0 || value.length > maximum) fail(path, 'must be a nonempty string of at most ' + maximum + ' characters.');
  }
  function integer(value, path, minimum = 0, maximum = Number.MAX_SAFE_INTEGER) {
    if (!Number.isSafeInteger(value) || value < minimum || value > maximum) fail(path, 'must be an integer from ' + minimum + ' to ' + maximum + '.');
  }
  function timestamp(value, path) {
    if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) fail(path, 'must be a valid ISO timestamp with an explicit timezone.');
  }
  function exactKeys(value, keys, path) {
    object(value, path);
    if (Object.keys(value).sort().join('|') !== keys.slice().sort().join('|')) fail(path, 'must contain exactly ' + keys.join(', ') + '.');
  }
  function cloneJSON(input) {
    const active = new Set(); let nodes = 0;
    function copy(value, path, depth) {
      if (++nodes > 250000 || depth > 40) fail(path, 'exceeds the supported JSON size or nesting limit.');
      if (value === null || typeof value === 'boolean' || typeof value === 'string') return value;
      if (typeof value === 'number' && Number.isFinite(value)) return value;
      if (typeof value !== 'object') fail(path, 'must contain JSON values only.');
      if (active.has(value)) fail(path, 'cannot contain cyclic references.');
      active.add(value);
      const array = Array.isArray(value);
      if (array && value.length > 20000) fail(path, 'exceeds 20,000 array entries.');
      if (!array && Object.prototype.toString.call(value) !== '[object Object]') fail(path, 'must contain plain JSON objects.');
      const result = array ? [] : {};
      for (const key of Object.keys(value)) {
        const descriptor = Object.getOwnPropertyDescriptor(value, key);
        if (!descriptor || !own(descriptor, 'value')) fail(path + '.' + key, 'cannot contain accessor properties.');
        Object.defineProperty(result, key, {value: copy(descriptor.value, path + '.' + key, depth + 1), enumerable: true, configurable: true, writable: true});
      }
      if (array && Object.keys(result).length !== value.length) fail(path, 'must be a dense JSON array.');
      active.delete(value); return result;
    }
    return copy(input, 'evidence', 0);
  }
  function eventTime(event) {
    return own(event, 'eventTimestamp') ? event.eventTimestamp : own(event, 'timestamp') ? Date.parse(event.timestamp) : null;
  }
  function requiredAssertionIds(orders) {
    const ids = ['aws-provenance', 'case-integrity', 'collection-complete', 'bounded-dispatch', 'queues-drained'];
    for (const mode of MODES) {
      ids.push(mode + '-ledger-inputs');
      for (const order of orders) {
        for (const suffix of ['receipt-count', 'redelivery', 'fault-after-fulfillment', 'completed']) ids.push(mode + '-' + order.orderId + '-' + suffix);
        if (mode === 'repaired') ids.push(mode + '-' + order.orderId + '-same-receipt');
      }
    }
    return ids;
  }

  function analyzeEvidence(input) {
    object(input, 'evidence');
    const data = cloneJSON(input);
    if (data.schemaVersion !== 1) fail('schemaVersion', 'unsupported schema. Import a schemaVersion 1 AWS export.', 'UNSUPPORTED_SCHEMA');
    if (data.provenance === 'local-execution') fail('provenance', 'this viewer does not render local suite reports. Open local-results.json in a text editor, or regenerate it with python3 -I -S scripts/run_local.py --output local-results.json.', 'UNSUPPORTED_PROVENANCE');
    if (data.provenance !== 'aws') fail('provenance', 'unsupported provenance. Import an original schemaVersion 1 AWS evidence JSON export.', 'UNSUPPORTED_PROVENANCE');
    if (typeof data.runId !== 'string' || !IDENTIFIER.test(data.runId)) fail('runId', 'must be the export\'s 1–64 character run identifier.');
    const missing = [], checks = [];
    const markMissing = path => { if (!missing.includes(path)) missing.push(path); };
    const optionalObject = (parent, key, path) => {
      if (!own(parent, key)) { parent[key] = {}; markMissing(path); }
      object(parent[key], path); return parent[key];
    };
    const array = (parent, key, path, limit) => {
      if (!own(parent, key)) { parent[key] = []; markMissing(path); }
      if (!Array.isArray(parent[key]) || parent[key].length > limit) fail(path, 'must be an array of at most ' + limit + ' entries; null is not a missing observation.');
      return parent[key];
    };
    const optional = (parent, key, path, validator) => { if (own(parent, key)) validator(parent[key], path); };
    const add = (id, label, status, expected, observed, detail) => checks.push({id, label, status, expected, observed, detail});
    const matchRun = (value, path) => { if (value !== data.runId) fail(path, 'does not match the top-level runId. Do not mix observations from different runs.', 'IDENTITY_MISMATCH'); };
    if (own(data, 'status') && !CLAIM_STATES.has(data.status)) fail('status', 'must be a supplied passed, incomplete, or unresolved claim. It will not be treated as verification.');
    if (!own(data, 'status')) markMissing('status');
    const claimedStatus = own(data, 'status') ? data.status : null;
    for (const key of ['region', 'stack']) optional(data, key, key, string);
    optional(data, 'recordedAt', 'recordedAt', timestamp);
    if (!own(data, 'region')) markMissing('region');
    if (!own(data, 'recordedAt')) markMissing('recordedAt');

    exactKeys(data.case, ['schemaVersion', 'name', 'orders', 'fault', 'bounds'], 'case');
    if (data.case.schemaVersion !== 1 || typeof data.case.name !== 'string' || !IDENTIFIER.test(data.case.name)) fail('case', 'requires schemaVersion 1 and a valid case name.');
    if (!Array.isArray(data.case.orders) || data.case.orders.length < 1 || data.case.orders.length > 3) fail('case.orders', 'requires the original 1–3 orders; an absent case cannot define an assertion.');
    const orderMap = new Map();
    function validateOrder(order, path) {
      exactKeys(order, ['orderId', 'sku', 'quantity'], path);
      if (typeof order.orderId !== 'string' || !IDENTIFIER.test(order.orderId)) fail(path + '.orderId', 'must be a valid order identifier.');
      if (typeof order.sku !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/.test(order.sku)) fail(path + '.sku', 'must be a valid SKU.');
      integer(order.quantity, path + '.quantity', 1, 100);
    }
    data.case.orders.forEach((order, index) => {
      validateOrder(order, 'case.orders[' + index + ']');
      if (orderMap.has(order.orderId)) fail('case.orders', 'contains a duplicate orderId.', 'IDENTITY_MISMATCH');
      orderMap.set(order.orderId, order);
    });
    exactKeys(data.case.fault, ['type'], 'case.fault');
    if (data.case.fault.type !== 'crash-after-fulfillment') fail('case.fault.type', 'this view supports only the crash-after-fulfillment AWS comparison.', 'UNSUPPORTED_CASE');
    exactKeys(data.case.bounds, ['maxWaitSeconds', 'maxMessages', 'drainGraceSeconds'], 'case.bounds');
    integer(data.case.bounds.maxWaitSeconds, 'case.bounds.maxWaitSeconds', 30, 180);
    integer(data.case.bounds.maxMessages, 'case.bounds.maxMessages', 2, 6);
    integer(data.case.bounds.drainGraceSeconds, 'case.bounds.drainGraceSeconds', 10, 30);
    if (data.case.bounds.maxMessages < data.case.orders.length * 2 || data.case.bounds.maxWaitSeconds < data.case.bounds.drainGraceSeconds + 20) fail('case.bounds', 'does not allow the declared orders and observation grace.');
    const inputs = optionalObject(data, 'inputs', 'inputs');
    const inputOrders = array(inputs, 'orders', 'inputs.orders', 3);
    const seenInputOrders = new Set();
    inputOrders.forEach((order, index) => {
      validateOrder(order, 'inputs.orders[' + index + ']');
      if (!orderMap.has(order.orderId) || seenInputOrders.has(order.orderId)) fail('inputs.orders[' + index + '].orderId', 'is unknown or duplicated relative to the original case.', 'IDENTITY_MISMATCH');
      seenInputOrders.add(order.orderId);
    });
    const fault = optionalObject(data, 'fault', 'fault');
    if (own(fault, 'type')) { string(fault.type, 'fault.type', 64); if (fault.type !== data.case.fault.type) fail('fault.type', 'does not match the original case.', 'IDENTITY_MISMATCH'); }
    else markMissing('fault.type');

    function identity(item, path, forcedMode) {
      object(item, path); matchRun(item.runId, path + '.runId');
      if (!MODES.includes(item.mode) || (forcedMode && item.mode !== forcedMode)) fail(path + '.mode', 'must match its vulnerable or repaired group.', 'IDENTITY_MISMATCH');
      if (typeof item.orderId !== 'string' || !orderMap.has(item.orderId)) fail(path + '.orderId', 'is not an order in this case.', 'IDENTITY_MISMATCH');
    }
    const messages = array(data, 'messages', 'messages', 6), messageMap = new Map(), messageIds = new Set();
    messages.forEach((message, index) => {
      const path = 'messages[' + index + ']'; object(message, path);
      if (!MODES.includes(message.mode) || !orderMap.has(message.orderId)) fail(path, 'has an unknown mode or orderId.', 'IDENTITY_MISMATCH');
      if (own(message, 'runId')) matchRun(message.runId, path + '.runId');
      string(message.messageId, path + '.messageId', 200);
      const key = message.mode + '|' + message.orderId;
      if (messageMap.has(key) || messageIds.has(message.messageId)) fail(path, 'duplicates a submitted message identity; the case submits exactly one message per mode and order.', 'IDENTITY_MISMATCH');
      optional(message, 'sentAt', path + '.sentAt', timestamp);
      if (own(message, 'bodySha256') && (typeof message.bodySha256 !== 'string' || !SHA256.test(message.bodySha256))) fail(path + '.bodySha256', 'must be a SHA-256 hex string. This browser does not recompute that hash.');
      messageMap.set(key, message); messageIds.add(message.messageId);
    });
    function bindMessage(item, path) {
      string(item.messageId, path + '.messageId', 200);
      const sent = messageMap.get(item.mode + '|' + item.orderId);
      if (sent && item.messageId !== sent.messageId) fail(path + '.messageId', 'does not match the original submitted SQS message.', 'IDENTITY_MISMATCH');
    }
    const receipts = optionalObject(data, 'receipts', 'receipts');
    if (Object.keys(receipts).some(key => !MODES.includes(key))) fail('receipts', 'contains an unsupported handler mode.', 'IDENTITY_MISMATCH');
    for (const mode of MODES) {
      const rows = array(receipts, mode, 'receipts.' + mode, 200), identities = new Set();
      rows.forEach((receipt, index) => {
        const path = 'receipts.' + mode + '[' + index + ']'; identity(receipt, path, mode);
        string(receipt.receiptId, path + '.receiptId', 200);
        if (identities.has(receipt.receiptId)) fail(path + '.receiptId', 'duplicates a receipt identity. Repeating a row cannot establish another fulfillment.', 'DUPLICATE_RECEIPT_IDENTITY');
        identities.add(receipt.receiptId); bindMessage(receipt, path);
        string(receipt.sku, path + '.sku', 128); integer(receipt.quantity, path + '.quantity', 1, 100);
        integer(receipt.receiveCount, path + '.receiveCount', 1);
        for (const key of ['PK', 'SK', 'invocationId']) string(receipt[key], path + '.' + key, 256);
        timestamp(receipt.createdAt, path + '.createdAt'); integer(receipt.expiresAt, path + '.expiresAt', 1);
        if (receipt.idempotencyKey !== null) string(receipt.idempotencyKey, path + '.idempotencyKey', 200);
      });
    }

    function validateEvent(event, path, forcedMode) {
      identity(event, path, forcedMode); bindMessage(event, path);
      if (!['worker', 'provider'].includes(event.source) || event.component !== event.source) fail(path + '.source', 'must match a worker/provider component.', 'IDENTITY_MISMATCH');
      if (!(event.source === 'worker' ? WORKER_STAGES : PROVIDER_STAGES).has(event.stage)) fail(path + '.stage', 'is unsupported for this component.', 'UNSUPPORTED_OBSERVATION');
      string(event.requestId, path + '.requestId', 200); integer(event.receiveCount, path + '.receiveCount', 1);
      if (event.receiptId !== null) string(event.receiptId, path + '.receiptId', 200);
      optional(event, 'timestamp', path + '.timestamp', timestamp);
      optional(event, 'eventTimestamp', path + '.eventTimestamp', (value, name) => integer(value, name, 1));
      optional(event, 'ingestionTime', path + '.ingestionTime', (value, name) => integer(value, name, 1));
      if (!own(event, 'timestamp') && !own(event, 'eventTimestamp')) markMissing(path + '.timestamp');
      for (const key of ['accepted', 'reused']) if (own(event, key) && typeof event[key] !== 'boolean') fail(path + '.' + key, 'must be a boolean.');
      for (const key of ['eventId', 'sourceLogGroup', 'logStreamName', 'error', 'errorType', 'fault']) optional(event, key, path + '.' + key, string);
      if (own(event, 'idempotencyKey') && event.idempotencyKey !== null) string(event.idempotencyKey, path + '.idempotencyKey', 200);
      if (event.source === 'provider') string(event.workerRequestId, path + '.workerRequestId', 200);
    }
    const events = array(data, 'events', 'events', 20000), workerRequests = new Map(), providerRequests = new Map();
    events.forEach((event, index) => {
      const path = 'events[' + index + ']'; validateEvent(event, path);
      if (event.source === 'worker') {
        const signature = [event.mode, event.orderId, event.messageId, event.receiveCount].join('|');
        if (workerRequests.has(event.requestId) && workerRequests.get(event.requestId) !== signature) fail(path + '.requestId', 'is reused across incompatible deliveries.', 'IDENTITY_MISMATCH');
        workerRequests.set(event.requestId, signature);
      } else {
        const signature = [event.mode, event.orderId, event.messageId, event.receiveCount, event.workerRequestId].join('|');
        if (providerRequests.has(event.requestId) && providerRequests.get(event.requestId) !== signature) fail(path + '.requestId', 'is reused across incompatible provider invocations.', 'IDENTITY_MISMATCH');
        providerRequests.set(event.requestId, signature);
      }
    });
    let missingProviderLinks = 0;
    events.forEach((event, index) => {
      if (event.source !== 'provider') return;
      const signature = [event.mode, event.orderId, event.messageId, event.receiveCount].join('|');
      if (workerRequests.has(event.workerRequestId) && workerRequests.get(event.workerRequestId) !== signature) fail('events[' + index + '].workerRequestId', 'points to a different worker delivery.', 'IDENTITY_MISMATCH');
      if (!workerRequests.has(event.workerRequestId)) missingProviderLinks++;
    });
    if (own(data, 'attempts')) {
      object(data.attempts, 'attempts');
      for (const key of Object.keys(data.attempts)) if (!MODES.includes(key)) fail('attempts.' + key, 'is an unsupported mode.', 'IDENTITY_MISMATCH');
      for (const mode of MODES) {
        if (!own(data.attempts, mode)) data.attempts[mode] = [];
        if (!Array.isArray(data.attempts[mode]) || data.attempts[mode].length > 20000) fail('attempts.' + mode, 'must be an array.');
        data.attempts[mode].forEach((event, index) => { validateEvent(event, 'attempts.' + mode + '[' + index + ']', mode); if (event.source !== 'worker' || event.stage !== 'received') fail('attempts.' + mode, 'must contain worker received observations only.'); });
      }
    } else data.attempts = {vulnerable: [], repaired: []};

    const snapshots = array(data, 'queueObservations', 'queueObservations', 1000);
    snapshots.forEach((snapshot, index) => {
      const path = 'queueObservations[' + index + ']'; object(snapshot, path); timestamp(snapshot.observedAt, path + '.observedAt');
      if (own(snapshot, 'runId')) matchRun(snapshot.runId, path + '.runId');
      for (const queue of ['queue', 'dlq']) {
        const attributes = optionalObject(snapshot, queue, path + '.' + queue);
        for (const key of ['visible', 'notVisible', 'delayed']) {
          if (own(attributes, key)) integer(attributes[key], path + '.' + queue + '.' + key);
          else markMissing(path + '.' + queue + '.' + key);
        }
      }
    });
    const collection = optionalObject(data, 'collection', 'collection');
    if (own(collection, 'runId')) matchRun(collection.runId, 'collection.runId');
    for (const key of ['apiCalls', 'maxApiCalls', 'maxPagesPerRead', 'unparsedLogEvents', 'logsStartTime']) optional(collection, key, 'collection.' + key, integer);
    for (const key of ['startedAt', 'finishedAt']) optional(collection, key, 'collection.' + key, timestamp);
    if (own(collection, 'lastLogReadAt') && collection.lastLogReadAt !== null) timestamp(collection.lastLogReadAt, 'collection.lastLogReadAt');
    if (own(collection, 'stopReason') && collection.stopReason !== null) string(collection.stopReason, 'collection.stopReason');
    const lastReads = optionalObject(collection, 'lastLedgerReadAt', 'collection.lastLedgerReadAt');
    for (const key of Object.keys(lastReads)) if (!MODES.includes(key)) fail('collection.lastLedgerReadAt.' + key, 'is an unsupported mode.', 'IDENTITY_MISMATCH');
    for (const mode of MODES) { if (own(lastReads, mode)) timestamp(lastReads[mode], 'collection.lastLedgerReadAt.' + mode); else markMissing('collection.lastLedgerReadAt.' + mode); }
    const apiErrors = array(data, 'apiErrors', 'apiErrors', 300);
    apiErrors.forEach((error, index) => { const path = 'apiErrors[' + index + ']'; object(error, path); for (const key of ['operation', 'code', 'message']) string(error[key], path + '.' + key); optional(error, 'recordedAt', path + '.recordedAt', timestamp); });
    const assertions = array(data, 'assertions', 'assertions', 300), claimIds = new Set();
    assertions.forEach((claim, index) => {
      const path = 'assertions[' + index + ']'; object(claim, path); string(claim.id, path + '.id', 200); string(claim.label, path + '.label', 500);
      if (!CLAIM_STATES.has(claim.status)) fail(path + '.status', 'must be passed, incomplete, or unresolved; supplied statuses never override raw checks.');
      if (claimIds.has(claim.id)) fail(path + '.id', 'is duplicated. Import the original assertion list.');
      claimIds.add(claim.id); optional(claim, 'detail', path + '.detail', string);
    });
    if (own(data, 'limitations')) { if (!Array.isArray(data.limitations) || data.limitations.length > 100) fail('limitations', 'must be an array.'); data.limitations.forEach((value, index) => string(value, 'limitations[' + index + ']')); }
    else data.limitations = [];
    const artifacts = optionalObject(data, 'artifacts', 'artifacts');
    for (const key of ['caseSha256', 'canonicalCaseSha256', 'runnerSha256', 'verifierSha256']) {
      if (!own(artifacts, key)) markMissing('artifacts.' + key);
      else if (typeof artifacts[key] !== 'string' || !SHA256.test(artifacts[key])) fail('artifacts.' + key, 'must be a SHA-256 hex string.');
    }
    if (own(artifacts, 'sourceFiles')) { object(artifacts.sourceFiles, 'artifacts.sourceFiles'); for (const [name, digest] of Object.entries(artifacts.sourceFiles)) if (typeof digest !== 'string' || !SHA256.test(digest)) fail('artifacts.sourceFiles.' + name, 'must be a SHA-256 hex string.'); }
    if (own(data, 'deployment')) {
      object(data.deployment, 'deployment');
      for (const key of ['stackStatus', 'expiry', 'workerLogGroup', 'providerLogGroup', 'ledgerTable']) optional(data.deployment, key, 'deployment.' + key, string);
    }

    add('observation-shape', 'Required observation fields are present', missing.length ? 'incomplete' : 'passed', 'complete supported export fields', missing, 'Missing fields are reported as incomplete; null and wrong-type containers are rejected.');
    const missingClaims = requiredAssertionIds(data.case.orders).filter(id => !claimIds.has(id));
    add('required-assertion-ids', 'Expected assertion identifiers are present', missingClaims.length ? 'incomplete' : 'passed', 'all assertion IDs for each declared order', missingClaims, 'Only presence is checked. The supplied assertion statuses and values do not determine these browser results.');
    const inputsMatch = inputOrders.length === data.case.orders.length && inputOrders.every(order => { const original = orderMap.get(order.orderId); return order.sku === original.sku && order.quantity === original.quantity; });
    add('case-inputs', 'Inputs agree with the original case', inputsMatch ? 'passed' : inputOrders.length ? 'unresolved' : 'incomplete', data.case.orders, inputOrders, 'This compares order payloads inside the JSON; it does not recompute exported hashes or authenticate origin.');
    add('bounded-dispatch', 'Submitted SQS messages cover the case', messageMap.size === data.case.orders.length * 2 ? 'passed' : 'incomplete', data.case.orders.length * 2, messageMap.size, 'Exactly one submitted message per mode and order anchors delivery checks. Message-body SHA-256 values are not recomputed here.');
    const completedCollection = !apiErrors.length && collection.unparsedLogEvents === 0 && collection.lastLogReadAt && collection.stopReason === 'Assertions satisfied within the observation window' && collection.startedAt && collection.finishedAt && Number.isSafeInteger(collection.apiCalls) && Number.isSafeInteger(collection.maxApiCalls) && collection.apiCalls <= collection.maxApiCalls;
    add('collection-complete', 'Collection reports no missing or failed reads', completedCollection ? 'passed' : 'incomplete', 'no API errors or unparsed logs; final reads, successful stop reason and calls within budget', {apiErrors: apiErrors.length, unparsedLogs: collection.unparsedLogEvents ?? null, lastLogReadAt: collection.lastLogReadAt ?? null, stopReason: collection.stopReason ?? null, apiCalls: collection.apiCalls ?? null, maxApiCalls: collection.maxApiCalls ?? null}, 'Timeout, interruption, budget exhaustion, an unknown stop reason, or missing collection metadata leaves this check incomplete. The remaining checks independently inspect raw observations.');
    const providerEvents = events.filter(event => event.source === 'provider');
    const workerSuccesses = events.filter(event => event.source === 'worker' && event.stage === 'fulfillment_succeeded');
    const responseMatches = (provider, worker) => provider.workerRequestId === worker.requestId && provider.receiptId === worker.receiptId && provider.mode === worker.mode && provider.orderId === worker.orderId && provider.receiveCount === worker.receiveCount;
    const missingProviderResponses = workerSuccesses.filter(worker => !providerEvents.some(provider => responseMatches(provider, worker))).length;
    const contraryProviderResponses = workerSuccesses.filter(worker => providerEvents.some(provider => responseMatches(provider, worker) && ['accepted', 'reused'].some(key => own(provider, key) && own(worker, key) && provider[key] !== worker[key]))).length;
    const successfulProviderEvents = providerEvents.filter(event => ['accepted', 'reused'].includes(event.stage));
    const missingResponseFlags = [...workerSuccesses, ...successfulProviderEvents].filter(event => !own(event, 'accepted') || !own(event, 'reused')).length;
    const contraryProviderStages = successfulProviderEvents.filter(event => (own(event, 'accepted') && event.accepted !== (event.stage === 'accepted')) || (own(event, 'reused') && event.reused !== (event.stage === 'reused'))).length;
    const acceptedProviderEvents = providerEvents.filter(event => event.stage === 'accepted');
    const acceptedReceiptMatches = (provider, receipt) => provider.requestId === receipt.invocationId && provider.receiptId === receipt.receiptId && provider.runId === receipt.runId && provider.mode === receipt.mode && provider.orderId === receipt.orderId && provider.messageId === receipt.messageId && provider.receiveCount === receipt.receiveCount;
    const missingLedgerProviderReferences = MODES.reduce((count, mode) => count + receipts[mode].filter(receipt => !acceptedProviderEvents.some(provider => acceptedReceiptMatches(provider, receipt))).length, 0);
    // A fresh acceptance must also appear in the final ledger. Reuse events point
    // to the original receipt and do not require a new receipt for the retry.
    const missingAcceptedProviderReceipts = acceptedProviderEvents.filter(provider => !receipts[provider.mode].some(receipt => acceptedReceiptMatches(provider, receipt))).length;
    const modesCovered = MODES.every(mode => ['worker', 'provider'].every(source => events.some(event => event.mode === mode && event.source === source)));
    const correlationsContradict = contraryProviderResponses > 0 || contraryProviderStages > 0;
    const correlationsComplete = modesCovered && !missingProviderLinks && !missingProviderResponses && !missingResponseFlags && !missingLedgerProviderReferences && !missingAcceptedProviderReceipts;
    add('event-correlations', 'Worker and provider observations correlate', correlationsContradict ? 'unresolved' : correlationsComplete ? 'passed' : 'incomplete', 'matching worker/provider results; each receipt and fresh acceptance linked in both directions', {events: events.length, modesCovered, missingWorkerReferences: missingProviderLinks, missingProviderResponses, missingResponseFlags, missingLedgerProviderReferences, missingAcceptedProviderReceipts, contraryProviderResponses, contraryProviderStages}, 'Missing invocation links or a fresh provider acceptance absent from the final ledger stay incomplete. Reuse may reference the original receipt. Opposing accepted/reused flags or stage claims are unresolved. Correlations inside supplied JSON do not authenticate its origin.');
    const completedTimes = [];
    for (const mode of MODES) {
      const rows = receipts[mode];
      const badRows = rows.filter(row => { const order = orderMap.get(row.orderId); return row.sku !== order.sku || row.quantity !== order.quantity || row.PK !== 'RUN#' + data.runId + '#MODE#' + mode || row.SK !== 'RECEIPT#' + row.receiptId || (mode === 'repaired' && row.idempotencyKey !== row.receiptId); }).map(row => row.receiptId);
      add(mode + '-ledger-inputs', mode + ' receipt fields agree with the case', badRows.length ? 'unresolved' : rows.length ? 'passed' : 'incomplete', 'consistent order payload and ledger keys', badRows.length ? badRows : rows.length, 'A distinct second receipt still counts as a contradiction even when its supplied ledger key is inconsistent.');
      for (const order of data.case.orders) {
        const prefix = mode + '-' + order.orderId, orderRows = rows.filter(row => row.orderId === order.orderId), ledgerIds = new Set(orderRows.map(row => row.receiptId));
        const countStatus = mode === 'repaired' ? ledgerIds.size > 1 ? 'unresolved' : ledgerIds.size === 1 ? 'passed' : 'incomplete' : ledgerIds.size >= 2 ? 'passed' : 'incomplete';
        add(prefix + '-receipt-count', mode + ': receipt count for ' + order.orderId, countStatus, mode === 'repaired' ? 1 : 'at least 2', ledgerIds.size, 'Recomputed from raw distinct receipt identities for this exact case order. A supplied passed claim cannot override a duplicate.');
        const sent = messageMap.get(mode + '|' + order.orderId);
        const matching = events.filter(event => event.source === 'worker' && event.mode === mode && event.orderId === order.orderId && sent && event.messageId === sent.messageId);
        const received = matching.filter(event => event.stage === 'received'), first = received.filter(event => event.receiveCount === 1), retried = received.filter(event => event.receiveCount >= 2);
        const redelivered = first.some(a => retried.some(b => a.requestId !== b.requestId && eventTime(a) !== null && eventTime(b) !== null && eventTime(b) > eventTime(a)));
        add(prefix + '-redelivery', mode + ': same message has separate deliveries', redelivered ? 'passed' : 'incomplete', 'receiveCount 1 then >=2, distinct requests, same submitted message', received.map(event => ({messageId: event.messageId, requestId: event.requestId, receiveCount: event.receiveCount})), 'Derived from worker events, never from the supplied attempts or assertion summaries.');
        const faults = matching.filter(event => event.stage === 'fault_injected');
        const goodFaults = faults.filter(f => {
          const row = orderRows.find(receipt => receipt.receiptId === f.receiptId && receipt.receiveCount === 1);
          const successes = matching.filter(s => s.stage === 'fulfillment_succeeded' && s.requestId === f.requestId && s.receiptId === f.receiptId && s.receiveCount === 1 && eventTime(s) !== null && eventTime(f) !== null && eventTime(s) <= eventTime(f));
          return row && eventTime(f) !== null && Date.parse(row.createdAt) <= eventTime(f) + 2000 && f.receiveCount === 1 && f.fault === data.case.fault.type && successes.some(s => first.some(r => r.requestId === f.requestId && eventTime(r) !== null && eventTime(r) <= eventTime(s))) && matching.some(e => e.stage === 'failed' && e.requestId === f.requestId && eventTime(e) !== null && eventTime(e) >= eventTime(f));
        });
        const contradictoryFault = faults.some(event => event.receiveCount !== 1 || event.fault !== data.case.fault.type);
        add(prefix + '-fault-after-fulfillment', mode + ': recorded fault follows a receipt', contradictoryFault ? 'unresolved' : goodFaults.length ? 'passed' : 'incomplete', 'first-delivery success → configured fault → failure, tied to a raw receipt', faults.map(event => event.receiptId), 'Checks recorded ordering with a two-second cross-host receipt-clock allowance; it does not authenticate execution.');
        const completed = matching.filter(e => e.stage === 'completed' && e.receiveCount >= 2 && ledgerIds.has(e.receiptId) && eventTime(e) !== null && matching.some(s => s.stage === 'fulfillment_succeeded' && s.requestId === e.requestId && s.receiveCount === e.receiveCount && s.receiptId === e.receiptId && eventTime(s) !== null && eventTime(s) <= eventTime(e) && retried.some(r => r.requestId === e.requestId && r.receiveCount === e.receiveCount && eventTime(r) !== null && eventTime(r) <= eventTime(s))));
        add(prefix + '-completed', mode + ': retry has a completed sequence', completed.length ? 'passed' : 'incomplete', 'retry receive → success → completion referencing a receipt', completed.map(event => event.receiptId), 'Completion is derived from correlated raw events and receipts. Missing events cannot be replaced by a saved pass.');
        completedTimes.push(...completed.map(eventTime));
        if (mode === 'repaired') {
          const successes = matching.filter(e => e.stage === 'fulfillment_succeeded' && e.receiveCount >= 2 && completed.some(c => c.requestId === e.requestId && c.receiptId === e.receiptId));
          const contradictory = successes.some(e => (own(e, 'accepted') && e.accepted !== false) || (own(e, 'reused') && e.reused !== true));
          const reused = goodFaults.some(f => completed.some(c => c.receiptId === f.receiptId)) && successes.length && successes.every(e => e.accepted === false && e.reused === true);
          add(prefix + '-same-receipt', 'repaired: retry refers to the original receipt', ledgerIds.size > 1 || contradictory ? 'unresolved' : reused ? 'passed' : 'incomplete', 'one receipt; accepted=false and reused=true on retry', {receiptCount: ledgerIds.size, retryResponses: successes.map(e => ({accepted: e.accepted, reused: e.reused}))}, 'Receipt reuse cannot pass when the raw ledger contains more than one repaired receipt for this order.');
        }
      }
    }
    let zeroSince = null, lastZero = null, deadLetter = false;
    const latestCompletion = completedTimes.length ? Math.max(...completedTimes) : Infinity;
    for (const snapshot of snapshots.slice().sort((a, b) => Date.parse(a.observedAt) - Date.parse(b.observedAt))) {
      const time = Date.parse(snapshot.observedAt);
      deadLetter = deadLetter || ['visible', 'notVisible', 'delayed'].some(key => snapshot.dlq[key] > 0);
      const zero = ['queue', 'dlq'].every(queue => ['visible', 'notVisible', 'delayed'].every(key => snapshot[queue][key] === 0));
      if (time >= latestCompletion && zero) { if (zeroSince === null) zeroSince = time; lastZero = time; }
      else { zeroSince = null; lastZero = null; }
    }
    const stableSeconds = lastZero !== null && zeroSince !== null ? (lastZero - zeroSince) / 1000 : 0;
    const finalReads = lastZero !== null && MODES.every(mode => own(lastReads, mode) && Date.parse(lastReads[mode]) >= lastZero);
    const drained = stableSeconds >= data.case.bounds.drainGraceSeconds && finalReads;
    add('queues-drained', 'Recorded queues stay empty after completion', deadLetter ? 'unresolved' : drained ? 'passed' : 'incomplete', 'empty source and DLQ for at least ' + data.case.bounds.drainGraceSeconds + ' seconds, then final ledger reads', {stableDrainSeconds: stableSeconds, deadLetterObserved: deadLetter, finalLedgerReads: finalReads}, 'SQS counts are approximate. This bounded check does not prove no future duplicate or authenticate the supplied observations.');
    const status = checks.some(check => check.status === 'unresolved') ? 'unresolved' : checks.some(check => check.status === 'incomplete') ? 'incomplete' : 'unverified';
    const reasons = checks.filter(check => check.status !== 'passed').map(check => check.label + ': ' + check.detail);
    reasons.push('AWS origin is not authenticated. These browser consistency checks do not replace scripts/verify_case.py, recompute artifact hashes, or establish a verified AWS result.');
    return {data, status, claimedStatus, checks, reasons, supportedChecksPassed: checks.filter(check => check.status === 'passed').length, totalChecks: checks.length, provenanceAuthenticated: false};
  }
  return Object.freeze({analyzeEvidence, requiredAssertionIds});
});
