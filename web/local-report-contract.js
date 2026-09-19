/* Local suite JSON consistency adapter. It never authenticates execution origin. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ReplayGuardLocalReport = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MODES = ['vulnerable', 'repaired'];
  const IDS = ['no-fault', 'crash-after-fulfillment', 'different-message-ids', 'missing-observation', 'ambiguous-side-effect'];
  const EXPECTED = {
    'no-fault': {vulnerable: 'pass', repaired: 'pass'},
    'crash-after-fulfillment': {vulnerable: 'violation', repaired: 'pass'},
    'different-message-ids': {vulnerable: 'violation', repaired: 'pass'},
    'missing-observation': {vulnerable: 'incomplete', repaired: 'incomplete'},
    'ambiguous-side-effect': {vulnerable: 'unresolved', repaired: 'unresolved'}
  };
  const EXIT = {pass: 0, violation: 1, incomplete: 2, unresolved: 3};
  const PLAN_HASH = '0a16692d69cb7b9a066eb9ba20c774cfd3b022f36aec243c304f0b71a59db26e';
  const INJECTED = 'Injected crash AFTER successful simulated fulfillment; SQS must redeliver';
  const WORKER_STAGES = new Set(['received', 'fulfillment_succeeded', 'fault_injected', 'failed', 'completed']);
  const PROVIDER_STAGES = new Set(['accepted', 'reused', 'payload_conflict']);
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  function fail(path, message, code = 'MALFORMED_LOCAL_REPORT') {
    const error = new Error(path + ': ' + message + ' Import a fresh full report from python3 -I -S scripts/run_local.py --output local-results.json.');
    error.name = 'LocalReportContractError'; error.code = code; error.path = path; throw error;
  }
  function object(value, path) { if (value === null || typeof value !== 'object' || Array.isArray(value)) fail(path, 'must be an object.'); }
  function array(value, path, max = 200) { if (!Array.isArray(value) || value.length > max) fail(path, 'must be an array of at most ' + max + ' entries.'); }
  function string(value, path, max = 2000, empty = false) { if (typeof value !== 'string' || (!empty && !value.length) || value.length > max) fail(path, 'must be a ' + (empty ? '' : 'nonempty ') + 'string.'); }
  function integer(value, path, min = 0, max = Number.MAX_SAFE_INTEGER) { if (!Number.isSafeInteger(value) || value < min || value > max) fail(path, 'must be an integer from ' + min + ' to ' + max + '.'); }
  function bool(value, path) { if (typeof value !== 'boolean') fail(path, 'must be a boolean.'); }
  function stamp(value, path) { if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) fail(path, 'must be a valid ISO timestamp.'); }
  function hash(value, path) { if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value)) fail(path, 'must be a SHA-256 hex fingerprint. Fingerprints here are supplied, not authenticated.'); }
  function keys(value, expected, path) { object(value, path); if (Object.keys(value).sort().join('|') !== expected.slice().sort().join('|')) fail(path, 'has unexpected or missing fields.'); }
  function equal(a, b) { if (a === b) return true; if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false; const ak = Object.keys(a).sort(), bk = Object.keys(b).sort(); return ak.length === bk.length && ak.every((key, index) => key === bk[index] && equal(a[key], b[key])); }
  function clone(input) {
    const active = new Set(); let nodes = 0;
    function copy(value, path, depth) {
      if (++nodes > 100000 || depth > 40) fail(path, 'exceeds the supported size/nesting limit.');
      if (value === null || ['string', 'boolean'].includes(typeof value)) return value;
      if (typeof value === 'number' && Number.isFinite(value)) return value;
      if (typeof value !== 'object') fail(path, 'must contain JSON values only.');
      if (active.has(value)) fail(path, 'contains a circular reference.'); active.add(value);
      const out = Array.isArray(value) ? [] : {};
      if (Array.isArray(value) && value.length > 2000) fail(path, 'contains too many entries.');
      if (!Array.isArray(value) && Object.prototype.toString.call(value) !== '[object Object]') fail(path, 'must contain plain JSON objects.');
      for (const key of Object.keys(value)) {
        const descriptor = Object.getOwnPropertyDescriptor(value, key);
        if (!own(descriptor, 'value')) fail(path + '.' + key, 'cannot contain an accessor.');
        Object.defineProperty(out, key, {value: copy(descriptor.value, path + '.' + key, depth + 1), enumerable: true, writable: true, configurable: true});
      }
      active.delete(value); return out;
    }
    return copy(input, 'report', 0);
  }
  function schedule(id) {
    if (id === 'ambiguous-side-effect') return [];
    const first = {messageKey: 'message-a', receiveCount: 1};
    if (id === 'crash-after-fulfillment') return [first, {messageKey: 'message-a', receiveCount: 2}];
    if (id === 'different-message-ids') return [first, {messageKey: 'message-b', receiveCount: 1}];
    return [first];
  }
  function order(value, path) {
    keys(value, ['orderId', 'sku', 'quantity'], path);
    if (typeof value.orderId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(value.orderId)) fail(path + '.orderId', 'is invalid.');
    if (typeof value.sku !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/.test(value.sku)) fail(path + '.sku', 'is invalid.');
    integer(value.quantity, path + '.quantity', 1, 100);
  }
  function validateCase(value, id, path) {
    keys(value, ['schemaVersion', 'id', 'title', 'order', 'fault', 'deliveries', 'observation', 'effectModel', 'expectedStatus', 'maxDeliveries'], path);
    if (value.schemaVersion !== 1 || value.id !== id) fail(path, 'does not match its result case identity.', 'IDENTITY_MISMATCH');
    string(value.title, path + '.title', 120); order(value.order, path + '.order');
    if (!equal(value.expectedStatus, EXPECTED[id]) || !equal(value.deliveries, schedule(id))) fail(path, 'changes the frozen scenario or expectations.', 'FROZEN_CASE_MISMATCH');
    const fault = id === 'crash-after-fulfillment' ? 'crash-after-fulfillment' : 'none';
    const observation = id === 'missing-observation' ? 'withhold-ledger' : 'independent-ledger';
    const effect = id === 'ambiguous-side-effect' ? 'ambiguous-external-effect' : 'receiver-owned-receipt';
    if (value.fault !== fault || value.observation !== observation || value.effectModel !== effect || value.maxDeliveries !== schedule(id).length) fail(path, 'changes the frozen fault, observation, model or delivery bound.', 'FROZEN_CASE_MISMATCH');
  }
  function error(value, path) { object(value, path); string(value.type, path + '.type', 200); string(value.message, path + '.message', 2000, true); }
  function claim(condition, path, message) { if (!condition) fail(path, message, 'CONTRADICTORY_CLAIM'); }
  function check(id, label, businessStatus, expected, observed, detail) { return {id, label, status: businessStatus === 'pass' ? 'passed' : businessStatus === 'incomplete' ? 'incomplete' : 'unresolved', businessStatus, expected, observed, detail}; }
  function verdict(checks) { for (const status of ['unresolved', 'violation', 'incomplete']) if (checks.some(item => item.businessStatus === status)) return status; return 'pass'; }

  function analyzeResult(result, index) {
    const path = 'results[' + index + ']'; object(result, path);
    if (!IDS.includes(result.caseId) || !MODES.includes(result.mode)) fail(path, 'contains an unknown case or mode.', 'IDENTITY_MISMATCH');
    if (result.provenance !== 'local-execution') fail(path + '.provenance', 'mixes local and other evidence.', 'UNSUPPORTED_PROVENANCE');
    if (typeof result.runId !== 'string' || !/^local-[a-f0-9]{32}$/.test(result.runId)) fail(path + '.runId', 'must be this local result\'s run identifier.');
    validateCase(result.case, result.caseId, path + '.case');
    if (result.title !== result.case.title) fail(path + '.title', 'does not match its declared case.');
    if (result.expectedStatus !== EXPECTED[result.caseId][result.mode]) fail(path + '.expectedStatus', 'changes the frozen expected business outcome.', 'FROZEN_CASE_MISMATCH');
    if (!own(EXIT, result.observedStatus)) fail(path + '.observedStatus', 'must name a business verdict.');
    integer(result.exitCode, path + '.exitCode', 0, 3); bool(result.expectationMatched, path + '.expectationMatched');
    for (const key of ['deliveries', 'providerInvocations', 'events', 'ledgerOperations', 'errors', 'assertions']) array(result[key], path + '.' + key, key === 'deliveries' ? 2 : 200);
    if (result.ledgerSnapshot !== null) array(result.ledgerSnapshot, path + '.ledgerSnapshot', 200);
    object(result.execution, path + '.execution');
    for (const key of ['performed', 'sourcesLoaded']) bool(result.execution[key], path + '.execution.' + key);
    for (const key of ['handlerInvocations', 'providerInvocations', 'maxDeliveries', 'maximumDeliveryRuntimeSeconds']) integer(result.execution[key], path + '.execution.' + key, 0, 200);
    claim(result.execution.handlerInvocations === result.deliveries.length && result.execution.providerInvocations === result.providerInvocations.length && result.execution.performed === (result.deliveries.length > 0), path + '.execution', 'execution counts/flags disagree with raw calls.');
    claim(result.execution.maxDeliveries === result.case.maxDeliveries, path + '.execution.maxDeliveries', 'does not match the frozen delivery bound.');
    const deliveries = new Map(), providerCalls = new Map(), receipts = new Map();
    function identity(item, itemPath) {
      if (item.runId !== result.runId || item.mode !== result.mode || item.orderId !== result.case.order.orderId) fail(itemPath, 'mixes run, mode or business-order identity.', 'IDENTITY_MISMATCH');
    }
    function payload(value, itemPath) {
      object(value, itemPath); order(value.order, itemPath + '.order');
      if (value.runId !== result.runId || value.mode !== result.mode || !equal(value.order, result.case.order) || value.fault !== result.case.fault) fail(itemPath, 'does not match this result\'s run/mode/order/fault.', 'IDENTITY_MISMATCH');
    }
    result.deliveries.forEach((delivery, i) => {
      const dp = path + '.deliveries[' + i + ']'; object(delivery, dp);
      const declared = schedule(result.caseId)[i];
      if (!declared || delivery.index !== i + 1 || delivery.receiveCount !== declared.receiveCount || delivery.messageId !== result.runId + '-' + declared.messageKey) fail(dp, 'does not follow the exact declared delivery schedule.', 'IDENTITY_MISMATCH');
      string(delivery.requestId, dp + '.requestId', 200); stamp(delivery.startedAt, dp + '.startedAt'); stamp(delivery.finishedAt, dp + '.finishedAt');
      if (deliveries.has(delivery.requestId)) fail(dp + '.requestId', 'duplicates a handler invocation.', 'IDENTITY_MISMATCH');
      bool(delivery.returnedNormally, dp + '.returnedNormally');
      if (delivery.error !== null) error(delivery.error, dp + '.error');
      if (delivery.returned !== null) { object(delivery.returned, dp + '.returned'); string(delivery.returned.receiptId, dp + '.returned.receiptId', 200); bool(delivery.returned.reused, dp + '.returned.reused'); }
      if (delivery.returnedNormally && delivery.error !== null) fail(dp, 'claims both a normal return and an exception.', 'CONTRADICTORY_CLAIM');
      object(delivery.input, dp + '.input'); array(delivery.input.Records, dp + '.input.Records', 1);
      if (delivery.input.Records.length !== 1) fail(dp + '.input', 'requires exactly one SQS-shaped record.');
      const record = delivery.input.Records[0]; object(record, dp + '.input.Records[0]'); object(record.attributes, dp + '.input.attributes'); string(record.body, dp + '.input.body', 16384);
      if (record.messageId !== delivery.messageId || record.attributes.ApproximateReceiveCount !== String(delivery.receiveCount)) fail(dp + '.input', 'does not match the recorded delivery.', 'IDENTITY_MISMATCH');
      let body; try { body = JSON.parse(record.body); } catch (_) { fail(dp + '.input.body', 'is not valid JSON.'); }
      keys(body, ['runId', 'mode', 'order', 'fault'], dp + '.input.body'); payload(body, dp + '.input.body');
      deliveries.set(delivery.requestId, delivery);
    });
    result.providerInvocations.forEach((invocation, i) => {
      const ip = path + '.providerInvocations[' + i + ']'; object(invocation, ip); string(invocation.requestId, ip + '.requestId', 200);
      if (providerCalls.has(invocation.requestId)) fail(ip, 'duplicates a provider request.', 'IDENTITY_MISMATCH');
      payload(invocation.payload, ip + '.payload');
      const delivery = deliveries.get(invocation.payload.workerRequestId);
      if (!delivery || invocation.payload.messageId !== delivery.messageId || invocation.payload.receiveCount !== delivery.receiveCount) fail(ip + '.payload', 'references a different or missing worker delivery.', 'IDENTITY_MISMATCH');
      if (own(invocation.payload, 'idempotencyKey')) string(invocation.payload.idempotencyKey, ip + '.payload.idempotencyKey', 200);
      if (invocation.functionError === null) {
        object(invocation.returned, ip + '.returned'); string(invocation.returned.receiptId, ip + '.returned.receiptId', 200);
        bool(invocation.returned.accepted, ip + '.returned.accepted'); bool(invocation.returned.reused, ip + '.returned.reused');
        if (invocation.returned.idempotencyKey !== null) string(invocation.returned.idempotencyKey, ip + '.returned.idempotencyKey', 200);
        stamp(invocation.returned.createdAt, ip + '.returned.createdAt');
      } else { if (invocation.functionError !== 'Unhandled') fail(ip + '.functionError', 'has an unsupported error shape.'); object(invocation.error, ip + '.error'); string(invocation.error.errorType, ip + '.error.errorType', 200); string(invocation.error.errorMessage, ip + '.error.errorMessage', 2000, true); }
      providerCalls.set(invocation.requestId, invocation);
    });
    result.events.forEach((event, i) => {
      const ep = path + '.events[' + i + ']'; object(event, ep); identity(event, ep);
      if (!['worker', 'provider'].includes(event.component) || !(event.component === 'worker' ? WORKER_STAGES : PROVIDER_STAGES).has(event.stage)) fail(ep, 'contains an unsupported component/stage.');
      if (event.localObservationIndex !== i) fail(ep + '.localObservationIndex', 'must preserve the recorded event order.');
      integer(event.localDeliveryIndex, ep + '.localDeliveryIndex', 1, 2); integer(event.receiveCount, ep + '.receiveCount', 1, 2); string(event.requestId, ep + '.requestId', 200); stamp(event.timestamp, ep + '.timestamp');
      if (event.receiptId !== null) string(event.receiptId, ep + '.receiptId', 200);
      for (const flag of ['accepted', 'reused']) if (own(event, flag)) bool(event[flag], ep + '.' + flag);
      const workerId = event.component === 'worker' ? event.requestId : event.workerRequestId;
      const delivery = deliveries.get(workerId);
      if (!delivery || event.messageId !== delivery.messageId || event.receiveCount !== delivery.receiveCount || event.localDeliveryIndex !== delivery.index) fail(ep, 'does not match its actual recorded delivery.', 'IDENTITY_MISMATCH');
      if (event.component === 'provider') {
        const invocation = providerCalls.get(event.requestId);
        if (!invocation || invocation.payload.workerRequestId !== workerId) fail(ep, 'does not match a provider invocation.', 'IDENTITY_MISMATCH');
      }
    });
    if (result.ledgerSnapshot !== null) result.ledgerSnapshot.forEach((row, i) => {
      const rp = path + '.ledgerSnapshot[' + i + ']'; object(row, rp); identity(row, rp); string(row.receiptId, rp + '.receiptId', 200);
      if (receipts.has(row.receiptId) || [...receipts.values()].some(other => other.PK === row.PK && other.SK === row.SK)) fail(rp, 'duplicates a ledger row identity.', 'DUPLICATE_RECEIPT_IDENTITY');
      if (row.sku !== result.case.order.sku || row.quantity !== result.case.order.quantity || row.PK !== 'RUN#' + result.runId + '#MODE#' + result.mode || row.SK !== 'RECEIPT#' + row.receiptId) fail(rp, 'does not match the declared business input and ledger identity.', 'IDENTITY_MISMATCH');
      integer(row.quantity, rp + '.quantity', 1, 100); integer(row.receiveCount, rp + '.receiveCount', 1, 2); integer(row.expiresAt, rp + '.expiresAt', 1); stamp(row.createdAt, rp + '.createdAt'); string(row.invocationId, rp + '.invocationId', 200);
      if (![...deliveries.values()].some(delivery => delivery.messageId === row.messageId && delivery.receiveCount === row.receiveCount)) fail(rp + '.messageId', 'does not match a recorded delivery.', 'IDENTITY_MISMATCH');
      if (row.idempotencyKey !== null) string(row.idempotencyKey, rp + '.idempotencyKey', 200);
      receipts.set(row.receiptId, row);
    });
    result.errors.forEach((item, i) => { error(item, path + '.errors[' + i + ']'); if (own(item, 'expectedInjectedFault')) bool(item.expectedInjectedFault, path + '.errors[' + i + '].expectedInjectedFault'); if (own(item, 'deliveryIndex')) integer(item.deliveryIndex, path + '.errors[' + i + '].deliveryIndex', 1, 2); });
    result.ledgerOperations.forEach((item, i) => { object(item, path + '.ledgerOperations[' + i + ']'); if (!['conditional-create', 'get-receipt'].includes(item.operation) || !['created', 'conflict', 'found', 'missing'].includes(item.outcome)) fail(path + '.ledgerOperations[' + i + ']', 'has an unsupported ledger operation.'); });
    result.assertions.forEach((item, i) => { object(item, path + '.assertions[' + i + ']'); string(item.id, path + '.assertions[' + i + '].id'); if (!own(EXIT, item.status)) fail(path + '.assertions[' + i + '].status', 'has an unknown claimed status.'); });

    const checks = [];
    const add = (id, label, status, expected, observed, detail) => checks.push(check(id, label, status, expected, observed, detail));
    const unknown = result.ledgerSnapshot === null;
    if (result.caseId === 'ambiguous-side-effect') {
      claim(!result.execution.performed && !result.execution.sourcesLoaded && !result.deliveries.length && !result.providerInvocations.length && !result.events.length && !result.ledgerOperations.length && !result.errors.length && unknown, path, 'unsupported external effects must not contain invented calls, receipts or execution.');
      add('effect-model', 'External effect cannot be modeled', 'unresolved', 'receiver-owned atomic receipt', result.case.effectModel, 'The runner explicitly rejected this model without executing either handler. No external fulfillment is inferred.');
    } else {
      add('finite-deliveries', 'Declared deliveries were recorded', result.deliveries.length === schedule(result.caseId).length ? 'pass' : 'incomplete', schedule(result.caseId).length, result.deliveries.length, 'Schedules are explicit local inputs, not observations of SQS delivery or timing.');
      add('source-execution', 'Handler entry points were reached', result.execution.sourcesLoaded && result.execution.performed ? 'pass' : 'incomplete', 'loaded source and invoked handler', {sourcesLoaded: result.execution.sourcesLoaded, performed: result.execution.performed}, 'These are local report fields, not authenticated source execution. Fingerprints remain supplied claims.');
      let completionMissing = 0, faultMissing = 0, correlationMissing = 0, correlationContrary = 0;
      const provedFaultDeliveries = new Set();
      for (const delivery of result.deliveries) {
        if (!result.providerInvocations.some(invocation => invocation.payload.workerRequestId === delivery.requestId)) correlationMissing++;
        const worker = result.events.filter(event => event.component === 'worker' && event.requestId === delivery.requestId);
        const received = worker.filter(event => event.stage === 'received');
        const successes = worker.filter(event => event.stage === 'fulfillment_succeeded');
        const completed = worker.filter(event => event.stage === 'completed');
        const successesProved = successes.filter(success => {
          const provider = result.events.find(event => event.component === 'provider' && event.workerRequestId === delivery.requestId && event.receiptId === success.receiptId && ['accepted', 'reused'].includes(event.stage));
          const call = provider && providerCalls.get(provider.requestId);
          if (!provider || !call || call.functionError !== null) { correlationMissing++; return false; }
          const flags = ['accepted', 'reused'];
          const contrary = flags.some(flag => !own(success, flag) || !own(provider, flag) || success[flag] !== provider[flag] || success[flag] !== call.returned[flag]) || provider.accepted !== (provider.stage === 'accepted') || provider.reused !== (provider.stage === 'reused') || call.returned.receiptId !== success.receiptId;
          if (contrary) { correlationContrary++; return false; }
          return received.some(event => event.localObservationIndex < provider.localObservationIndex) && provider.localObservationIndex < success.localObservationIndex;
        });
        const expectedFault = result.case.fault === 'crash-after-fulfillment' && delivery.receiveCount === 1;
        if (expectedFault) {
          const good = worker.some(fault => fault.stage === 'fault_injected' && fault.fault === 'crash-after-fulfillment' && successesProved.some(success => success.receiptId === fault.receiptId && success.localObservationIndex < fault.localObservationIndex) && worker.some(failed => failed.stage === 'failed' && failed.localObservationIndex > fault.localObservationIndex) && receipts.has(fault.receiptId) && receipts.get(fault.receiptId).receiveCount === 1);
          if (!good || delivery.returnedNormally || !delivery.error || delivery.error.type !== 'RuntimeError' || delivery.error.message !== INJECTED || completed.length) { faultMissing++; completionMissing++; }
          else provedFaultDeliveries.add(delivery.index);
        } else {
          const good = completed.some(end => successesProved.some(success => success.receiptId === end.receiptId && success.localObservationIndex < end.localObservationIndex));
          if (!good || !delivery.returnedNormally || delivery.error !== null) completionMissing++;
          if (good && delivery.returned && (!completed.some(event => event.receiptId === delivery.returned.receiptId) || !successesProved.some(event => event.receiptId === delivery.returned.receiptId && event.reused === delivery.returned.reused))) correlationContrary++;
        }
      }
      for (const invocation of result.providerInvocations) {
        if (invocation.functionError !== null) continue;
        const linked = result.events.find(event => event.component === 'provider' && event.requestId === invocation.requestId && event.receiptId === invocation.returned.receiptId && ['accepted', 'reused'].includes(event.stage));
        if (!linked) correlationMissing++;
        else if (linked.accepted !== invocation.returned.accepted || linked.reused !== invocation.returned.reused) correlationContrary++;
        if (!unknown && !receipts.has(invocation.returned.receiptId)) correlationMissing++;
      }
      // Check provider -> ledger as well as ledger -> provider. Reused events
      // reference the original row and must not manufacture a second receipt.
      if (!unknown) {
        for (const provider of result.events.filter(event => event.component === 'provider' && ['accepted', 'reused'].includes(event.stage))) if (!receipts.has(provider.receiptId)) correlationMissing++;
        result.ledgerSnapshot.forEach((row, index) => {
          const acceptance = result.events.find(event => event.component === 'provider' && event.stage === 'accepted' && event.requestId === row.invocationId && event.receiptId === row.receiptId);
          if (!acceptance) { correlationMissing++; return; }
          // The row records the creation delivery. A later reuse can refer to it,
          // but cannot replace that original message or receive count.
          if (row.messageId !== acceptance.messageId || row.receiveCount !== acceptance.receiveCount) fail(path + '.ledgerSnapshot[' + index + ']', 'messageId and receiveCount must match the original accepting provider invocation, not a later reuse delivery.', 'IDENTITY_MISMATCH');
        });
      }
      const unexpectedErrors = result.errors.filter(item => !(provedFaultDeliveries.has(item.deliveryIndex) && item.type === 'RuntimeError' && item.message === INJECTED));
      add('required-completions', 'Required deliveries completed', completionMissing || !result.deliveries.length ? 'incomplete' : 'pass', 'normal completion except a proved configured first crash', {missingCompletions: completionMissing}, 'Immediate exceptions, missing completion events and successful return values alone cannot establish a pass.');
      if (result.case.fault !== 'none') add('post-fulfillment-fault', 'Crash followed a local receipt', faultMissing || !provedFaultDeliveries.size ? 'incomplete' : 'pass', 'provider acceptance → worker success → configured failure', {provedFaults: provedFaultDeliveries.size}, 'The actual delivered input, ordered events, exception and independent snapshot must agree.');
      add('provider-ledger-correlation', 'Provider, worker and ledger agree', correlationContrary ? 'unresolved' : correlationMissing || unknown ? 'incomplete' : 'pass', 'matching results and bidirectional receipt links', {missingLinks: correlationMissing, contradictoryLinks: correlationContrary}, unknown ? 'The snapshot is withheld; this only compares delivery/provider events. Ledger existence remains unknown.' : 'Accepted and reused provider receipts must appear in the snapshot; every row must link to its accepting provider request.');
      add('independent-observation', 'Independent receipt snapshot is available', unknown ? 'incomplete' : 'pass', 'ledger snapshot', unknown ? null : result.ledgerSnapshot.length, unknown ? 'No snapshot was observed. Receipt count is unknown, not zero; logs and return values cannot substitute.' : 'The count comes from the raw local memory-ledger snapshot, not saved assertions.');
      if (!unknown) add('single-fulfillment', 'Exactly one modeled fulfillment', receipts.size > 1 ? 'violation' : receipts.size === 1 ? 'pass' : 'incomplete', 1, receipts.size, 'More than one distinct receipt is a business safety violation even when that buggy outcome was expected by the suite.');
      if (unexpectedErrors.length) add('execution-errors', 'No unexplained execution failures', 'incomplete', 0, unexpectedErrors.length, 'The browser evaluates error content and proved fault sequence, not expectedInjectedFault flags.');
    }
    const derivedStatus = verdict(checks);
    claim(result.observedStatus === derivedStatus, path + '.observedStatus', 'the saved ' + result.observedStatus + ' claim contradicts the raw-derived ' + derivedStatus + ' verdict.');
    claim(result.exitCode === EXIT[derivedStatus], path + '.exitCode', 'does not match the derived business verdict.');
    const expectationMatched = derivedStatus === EXPECTED[result.caseId][result.mode];
    claim(result.expectationMatched === expectationMatched, path + '.expectationMatched', 'does not match the frozen expectation and raw-derived verdict.');
    return {result, derivedStatus, expectedStatus: EXPECTED[result.caseId][result.mode], expectationMatched, receiptCount: unknown ? null : receipts.size, checks};
  }

  function analyzeLocalReport(input) {
    object(input, 'report'); const data = clone(input);
    if (data.schemaVersion !== 1 || data.provenance !== 'local-execution') fail('report', 'requires schemaVersion 1 and provenance local-execution.', 'UNSUPPORTED_LOCAL_FORMAT');
    if (data.supervisorIteration !== 'RG-SUP-001-9c7acfba') fail('supervisorIteration', 'requires the existing frozen local runner format.', 'UNSUPPORTED_LOCAL_FORMAT');
    array(data.results, 'results', 10);
    if (data.results.length !== 10) fail('results', 'this view supports the complete ten-result/five-case suite, not a single-handler report.', 'FULL_SUITE_REQUIRED');
    stamp(data.startedAt, 'startedAt'); stamp(data.recordedAt, 'recordedAt'); array(data.boundaries, 'boundaries', 100); data.boundaries.forEach((value, index) => string(value, 'boundaries[' + index + ']'));
    keys(data.sourceSha256, ['src/worker.py', 'src/provider.py'], 'sourceSha256'); Object.entries(data.sourceSha256).forEach(([key, value]) => hash(value, 'sourceSha256.' + key));
    keys(data.caseSha256, IDS.map(id => 'cases/local/' + id + '.json'), 'caseSha256'); Object.entries(data.caseSha256).forEach(([key, value]) => hash(value, 'caseSha256.' + key));
    object(data.plan, 'plan'); if (data.plan.sha256 !== PLAN_HASH || data.plan.path !== 'docs/iteration-01/plan.json' || data.plan.frozenBeforeImplementation !== true) fail('plan', 'does not identify the supported frozen expectations.', 'FROZEN_CASE_MISMATCH');
    object(data.runtime, 'runtime'); string(data.runtime.python, 'runtime.python', 100); for (const key of ['isolated', 'noSitePackages', 'sdkImported']) bool(data.runtime[key], 'runtime.' + key);
    object(data.noNetworkGuard, 'noNetworkGuard'); const guard = data.noNetworkGuard;
    for (const key of ['installedBeforeHandlerImport', 'passed']) bool(guard[key], 'noNetworkGuard.' + key);
    for (const key of ['auditEventsSeen', 'blockedOperationCount', 'handlerBlockedOperationCount']) integer(guard[key], 'noNetworkGuard.' + key);
    array(guard.selfTests, 'noNetworkGuard.selfTests', 20); array(guard.blockedOperations, 'noNetworkGuard.blockedOperations', 200);
    guard.selfTests.forEach((item, index) => { object(item, 'noNetworkGuard.selfTests[' + index + ']'); string(item.probe, 'noNetworkGuard.selfTests.probe'); bool(item.blocked, 'noNetworkGuard.selfTests.blocked'); });
    guard.blockedOperations.forEach((item, index) => { object(item, 'noNetworkGuard.blockedOperations[' + index + ']'); string(item.event, 'noNetworkGuard.blockedOperations.event'); bool(item.duringSelfTest, 'noNetworkGuard.blockedOperations.duringSelfTest'); });
    claim(guard.blockedOperationCount === guard.blockedOperations.length && guard.handlerBlockedOperationCount === guard.blockedOperations.filter(item => !item.duringSelfTest).length, 'noNetworkGuard', 'recorded operation counters disagree with the raw guard entries.');
    const guardProbes = ['socket-construction', 'aws-sdk-import', 'child-process-import', 'native-ffi-import'];
    const guardPassed = guard.installedBeforeHandlerImport && guardProbes.every(probe => guard.selfTests.some(item => item.probe === probe && item.blocked));
    claim(guard.passed === guardPassed, 'noNetworkGuard.passed', 'does not agree with the recorded self-test outcomes.');
    const byCase = new Map();
    data.results.forEach((result, index) => {
      const analyzed = analyzeResult(result, index); const id = result.caseId;
      if (!byCase.has(id)) byCase.set(id, {id, title: result.case.title, order: result.case.order, modes: {}, checks: []});
      const entry = byCase.get(id);
      if (own(entry.modes, result.mode)) fail('results[' + index + ']', 'duplicates the same case/mode result.', 'DUPLICATE_RESULT');
      if (!equal(entry.order, result.case.order) || entry.title !== result.case.title) fail('results[' + index + ']', 'cannot pair modes with different declared business inputs.', 'IDENTITY_MISMATCH');
      const other = Object.values(entry.modes)[0];
      if (other && !equal(other.result.case, result.case)) fail('results[' + index + ']', 'mixes mode results from different declared business cases.', 'IDENTITY_MISMATCH');
      entry.modes[result.mode] = analyzed;
    });
    const cases = IDS.map(id => {
      const item = byCase.get(id); if (!item || !MODES.every(mode => own(item.modes, mode))) fail('results', 'does not contain each required case/mode pair.', 'FULL_SUITE_REQUIRED');
      item.checks = MODES.flatMap(mode => item.modes[mode].checks.map(value => ({...value, id: mode + '-' + value.id, label: mode + ': ' + value.label})));
      item.expectationsMatched = MODES.every(mode => item.modes[mode].expectationMatched); return item;
    });
    const modes = cases.flatMap(item => MODES.map(mode => item.modes[mode]));
    const matchedCount = modes.filter(item => item.expectationMatched).length;
    const allMatched = matchedCount === 10, allSafe = modes.every(item => item.derivedStatus === 'pass');
    object(data.suite, 'suite'); object(data.command, 'command');
    for (const key of ['expectationsMatched', 'allHandlersSafe']) bool(data.suite[key], 'suite.' + key);
    for (const key of ['exitCode', 'matchedCount', 'totalCount']) integer(data.suite[key], 'suite.' + key);
    claim(data.suite.status === (allMatched ? 'passed' : 'failed') && data.suite.exitCode === (allMatched ? 0 : 1) && data.suite.expectationsMatched === allMatched && data.suite.matchedCount === matchedCount && data.suite.totalCount === 10, 'suite', 'saved suite success/match fields contradict raw-derived frozen expectations.');
    claim(data.suite.allHandlersSafe === allSafe, 'suite.allHandlersSafe', 'cannot claim all handlers are safe when a violation, missing observation or unsupported model is present.');
    claim(data.command.kind === 'expectation-suite' && data.command.exitCode === (allMatched ? 0 : 1), 'command', 'does not describe the complete expectation suite and its derived exit code.');
    const checks = [check('suite-expectations', 'Frozen suite expectations match', allMatched ? 'pass' : 'unresolved', 10, matchedCount, 'Expected vulnerable violations and incomplete/unresolved examples count as expectation matches, not as handler safety.'), check('local-runtime-metadata', 'Local runtime and guard fields agree', guardPassed && !guard.handlerBlockedOperationCount && data.runtime.isolated && data.runtime.noSitePackages && !data.runtime.sdkImported ? 'pass' : 'unresolved', 'isolated runtime and blocked guard probes', {guardPassed, blockedHandlerOperations: guard.handlerBlockedOperationCount, runtime: data.runtime}, 'These metadata fields are internally checked but cannot authenticate the imported execution.')];
    const unexpected = modes.filter(item => !item.expectationMatched);
    let status = allMatched ? 'unverified' : unexpected.every(item => item.derivedStatus === 'incomplete') ? 'incomplete' : 'unresolved';
    if (checks[1].status !== 'passed') status = 'unresolved';
    const reasons = ['Local execution origin and source/case fingerprints are not authenticated. The browser checks imported facts; it does not execute handlers or verify source bytes.', 'Suite expectation success never means every handler is safe. Inspect each mode\'s business verdict; null receipt snapshots remain unknown.'];
    if (!allMatched) reasons.unshift(matchedCount + ' of 10 frozen expected outcomes match the raw-derived business verdicts.');
    return {data, sourceType: 'local', status, claimedStatus: data.suite.status, provenanceAuthenticated: false, cases, checks, reasons, fingerprints: {sources: data.sourceSha256, cases: data.caseSha256, plan: data.plan}, derivedSuite: {status: allMatched ? 'passed' : 'failed', expectationsMatched: allMatched, matchedCount, totalCount: 10, allHandlersSafe: allSafe}, supportedChecksPassed: checks.filter(item => item.status === 'passed').length, totalChecks: checks.length};
  }
  return Object.freeze({analyzeLocalReport});
});
