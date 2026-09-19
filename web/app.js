'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const at = (root, id) => root.querySelector('#' + id);
  const set = (root, id, value) => { at(root, id).textContent = String(value ?? '—'); };
  const el = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; if (value !== undefined) node.textContent = String(value); return node; };
  const short = (value, length = 17) => { const s = String(value ?? '—'); return s.length > length ? s.slice(0, length) + '…' : s; };
  const objects = value => Array.isArray(value) ? value.filter(v => v && typeof v === 'object' && !Array.isArray(v)) : [];
  const date = value => { const d = new Date(value); return value && !Number.isNaN(d.getTime()) ? d.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC') : '—'; };
  const clock = value => { const d = new Date(value); return value && !Number.isNaN(d.getTime()) ? d.toISOString().slice(11, 19) : '—'; };
  const valueText = value => typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '—');
  let current = null;
  let lastImported = null;
  const recordedHow = $('how-it-works').cloneNode(true);
  let selectedMode = 'vulnerable';
  let operation = 0;
  let toastTimer;
  const MAX_BYTES = 5 * 1024 * 1024;
  function announce(message) { $('announcements').textContent = message; }
  function notify(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3000); announce(message); }
  function feedback(message, error = false) { $('import-message').className = 'import-message' + (error ? ' error' : ''); $('import-message').textContent = message; if($('journey-import-message')) { $('journey-import-message').className='import-message'+(error?' error':''); $('journey-import-message').textContent=message; } announce(message); }
  function workerEvents(data, mode) { return objects(data?.events).filter(e => e.mode === mode && e.runId === data.runId && e.component === 'worker').sort((a,b) => Number(a.eventTimestamp || new Date(a.timestamp).getTime() || 0) - Number(b.eventTimestamp || new Date(b.timestamp).getTime() || 0)); }
  function emptyTicket() { const node = el('div','empty-ticket'); const wrap = el('div'); wrap.append(el('span','','No receipts in the loaded data'), el('small','','Missing observations cannot establish fulfillment.')); node.append(wrap); return node; }
  function renderReceipts(view, analysis, mode) {
    const data = analysis?.data;
    const container = at(view, mode + '-receipts'); container.replaceChildren();
    const receipts = objects(data?.receipts?.[mode]).slice().sort((a,b) => new Date(a.createdAt) - new Date(b.createdAt));
    const deliveries = workerEvents(data, mode).filter(e => e.stage === 'received');
    set(view, mode + '-count', data ? receipts.length : '—');
    set(view, mode + '-attempts', data ? new Set(deliveries.map(e => e.requestId)).size : '—');
    if (!receipts.length) container.append(emptyTicket());
    const seen = new Set();
    for (const receipt of receipts.slice(0,6)) {
      const duplicate = seen.has(receipt.orderId); seen.add(receipt.orderId);
      const ticket = el('div','receipt-ticket');
      const top = el('div','ticket-top'); top.append(el('span','ticket-order',receipt.orderId),el('span','ticket-state' + (duplicate ? ' duplicate' : ''),duplicate ? 'DUPLICATE' : 'RECEIPT'));
      const bottom = el('div','ticket-bottom'); bottom.append(el('span','ticket-id',short(receipt.receiptId,22)),el('span','','QTY ' + receipt.quantity));
      const meta = el('div','ticket-meta'); meta.append(el('span','',receipt.sku),el('span','',clock(receipt.createdAt) + ' UTC'));
      const details = el('details','receipt-details'); details.append(el('summary','','Full receipt identity'),el('p','',receipt.receiptId));
      ticket.append(top,bottom,meta,details); container.append(ticket);
    }
    if (receipts.length > 6) container.append(el('p','panel-footnote',(receipts.length - 6) + ' more receipts in the original JSON.'));
    const counts = new Map(); receipts.forEach(r => counts.set(r.orderId,(counts.get(r.orderId) || 0) + 1));
    const extras = [...counts.values()].reduce((n,c) => n + Math.max(0,c-1),0);
    const result = !receipts.length ? 'Incomplete · no receipt observations' : extras ? extras + ' extra receipt' + (extras > 1 ? 's' : '') + ' for the same order' + (mode === 'repaired' ? ' · repair unresolved' : ' in this file') : receipts.length + ' reported receipt' + (receipts.length > 1 ? 's' : '') + ' · origin unverified';
    const resultNode = at(view, mode + '-result'); resultNode.replaceChildren(el('span','result-dot'),document.createTextNode(result));
    const card = resultNode.closest('.handler-card'); card.dataset.state = mode === 'repaired' && extras ? 'unresolved' : receipts.length ? 'unverified' : 'incomplete';
  }
  const stageTitles = {received:'SQS delivery reported',fulfillment_succeeded:'Fulfillment receipt reported',fault_injected:'Crash after fulfillment reported',failed:'Worker error reported',completed:'Worker completion reported'};
  function renderTimeline(view, data) {
    const node = at(view,'timeline'); node.replaceChildren();
    const events = workerEvents(data,selectedMode).filter(e => stageTitles[e.stage]);
    if (!events.length) { const li = el('li','empty-state'); li.append(el('strong','','No worker sequence available'),el('p','','Load an export with delivery, fulfillment, fault and retry observations.')); node.append(li); return; }
    for (const event of events.slice(0,24)) {
      const li = el('li',event.stage === 'fault_injected' || event.stage === 'failed' ? 'fault' : '');
      const title = event.stage === 'received' && event.receiveCount > 1 ? 'Redelivery reported' : event.stage === 'fulfillment_succeeded' && event.reused ? 'Receipt reuse reported' : stageTitles[event.stage];
      const info = event.stage === 'received' ? 'delivery ' + event.receiveCount + ' · message ' + short(event.messageId,12) : event.receiptId ? 'receipt ' + short(event.receiptId,20) : short(event.errorType || event.requestId,32);
      li.append(el('time','',clock(event.timestamp || event.eventTimestamp)),el('strong','',title),el('p','',info)); node.append(li);
    }
    if (events.length > 24) node.append(el('li','empty-state','More observations are available in the original JSON.'));
  }
  function assertionNode(check) {
    const node = el('details','assertion ' + check.status); node.dataset.checkId = check.id;
    const summary = el('summary'); const sign = el('span','assertion-sign',check.status === 'passed' ? '✓' : check.status === 'unresolved' ? '!' : '—'); sign.setAttribute('aria-hidden','true');
    const label = el('span','assertion-label',check.label); label.append(el('small','',check.businessStatus === 'violation' ? 'Violation · fulfillment invariant failed' : check.status === 'passed' ? 'Browser check passed' : check.status === 'unresolved' ? 'Unresolved · unsupported or contradictory observations' : 'Incomplete · observations missing'));
    summary.append(sign,label); node.append(summary);
    const body = el('div','assertion-detail'); body.append(el('p','',check.detail));
    const values = el('dl'); values.append(el('dt','','Expected'),el('dd','',valueText(check.expected)),el('dt','','Observed'),el('dd','',valueText(check.observed))); body.append(values); node.append(body); return node;
  }
  function renderAssertions(view, analysis) {
    const main = at(view,'assertions'); const restNode = at(view,'remaining-assertions'); main.replaceChildren(); restNode.replaceChildren();
    const checks = analysis?.checks || [];
    set(view,'assertion-counter',checks.filter(c => c.status === 'passed').length + ' / ' + checks.length);
    if (!checks.length) main.append(el('p','check-empty','No browser checks have run.'));
    const priority = check => check.status === 'unresolved' ? 0 : check.status === 'incomplete' ? 1 : check.id.includes('receipt-count') ? 2 : 3;
    const ordered = checks.slice().sort((a,b) => priority(a) - priority(b));
    ordered.slice(0,4).forEach(c => main.append(assertionNode(c))); ordered.slice(4).forEach(c => restNode.append(assertionNode(c)));
    at(view,'more-assertions').hidden = checks.length <= 4;
    set(view,'more-assertions-label','Inspect all ' + checks.length + ' browser checks');
  }
  function buildAwsView(candidate) {
    // All fallible rendering happens in detached DOM. No current state is changed.
    const view = $('main').cloneNode(true);
    const analysis = candidate.analysis; const data = analysis.data;
    renderSourceControls(view,candidate);
    at(view,'local-case-controls').hidden=true;at(view,'fingerprints').hidden=true;
    at(view,'how-it-works').replaceWith(recordedHow.cloneNode(true));
    set(view,'experiment-context','EXPERIMENT 001 / THE RETRY GAP');
    set(view,'experiment-intro','The fulfillment succeeds. The worker crashes. When SQS retries, does your customer get it twice?');
    set(view,'region-label','REGION');set(view,'origin-badge','AWS ORIGIN UNAUTHENTICATED');
    set(view,'fault-description','Fault condition: crash after durable fulfillment, before acknowledging the SQS message.');set(view,'fault-bound','FIRST DELIVERY ONLY');
    for(const mode of ['vulnerable','repaired']) {at(view,mode+'-local-summary').hidden=true;const card=at(view,mode+'-result').closest('.handler-card');card.querySelector('.metric-label').textContent='reported receipts';card.querySelector('.delivery-metric span').textContent='worker deliveries';card.querySelector('.handler-description').textContent=mode==='vulnerable'?'A retry makes a new fulfillment request.':'A stable order key reuses the original receipt.';}
    set(view,'receipt-caption','A receipt is the simulated fulfillment side effect. The worker cannot write to the ledger.');set(view,'trace-note','Events supplied in this file; their origin is unauthenticated.');set(view,'assertion-title','Browser consistency checks');set(view,'checks-note','These checks are recomputed from the loaded data. Open each row for its reason, expected value and observation. This is not the full archived AWS verifier.');
    set(view,'view-evidence','View JSON');set(view,'download-evidence','Download JSON');at(view,'aws-inspector-link').hidden=false;set(view,'comparison-origin-note','The comparison above displays the selected AWS-format observations.');
    set(view,'run-status',analysis.status.toUpperCase()); at(view,'run-status').className = 'status-badge ' + analysis.status;
    set(view,'evidence-title',candidate.source === 'import' ? 'Imported observations' : 'Recorded sample');
    set(view,'source-badge',candidate.source === 'import' ? 'YOUR FILE' : 'SHIPPED SAMPLE');
    set(view,'claimed-verdict','File claims: ' + (analysis.claimedStatus || 'not supplied').toUpperCase());
    set(view,'verification-summary',analysis.status === 'unresolved' ? 'The observations contradict the comparison. Inspect the failing checks below.' : analysis.status === 'incomplete' ? 'Required observations are missing. This file cannot establish a complete result.' : 'Supported browser checks found no contradiction. Full AWS verification has not run in this browser.');
    const reasons = at(view,'verification-reasons'); reasons.replaceChildren();
    const specificReasons = (analysis.reasons || []).filter(reason => !String(reason).startsWith('AWS origin is not authenticated.'));
    specificReasons.slice(0,3).forEach(reason => reasons.append(el('li','',typeof reason === 'string' ? reason : valueText(reason))));
    if (specificReasons.length > 3) reasons.append(el('li','',(specificReasons.length - 3) + ' more reasons are listed in the browser checks below.'));
    reasons.hidden = !reasons.childElementCount;
    set(view,'evidence-subtitle','Run ' + data.runId + ' · AWS origin is unauthenticated');
    set(view,'region',data.region); set(view,'recorded-at',date(data.recordedAt));
    const orders = objects(data.inputs?.orders || data.case?.orders);
    set(view,'hero-order',orders.length === 1 ? orders[0].orderId : orders.length ? orders.length + ' synthetic orders' : 'Input observations missing');
    set(view,'hero-sku',orders.length === 1 ? orders[0].sku + ' · QTY ' + orders[0].quantity : 'Recorded input comparison');
    set(view,'evidence-file-label',candidate.name + ' · original JSON retained · ZIP packages unchanged');
    at(view,'view-evidence').disabled = false; at(view,'download-evidence').disabled = false;
    renderReceipts(view,analysis,'vulnerable'); renderReceipts(view,analysis,'repaired'); renderTimeline(view,data); renderAssertions(view,analysis);
    const limits = at(view,'limitations'); limits.replaceChildren();
    limits.append(el('p','','Browser checks cover the supported internal consistency rules listed above. They do not authenticate AWS origin or re-run the full archived verifier. Supplied verdicts and assertions are retained only as claims in the original JSON.'));
    for (const limit of (Array.isArray(data.limitations) ? data.limitations : []).slice(0,20)) limits.append(el('p','',typeof limit === 'string' ? limit : valueText(limit)));
    set(view,'journey-import-message','');set(view,'import-message',''); at(view,'import-message').className = 'import-message';
    return view;
  }
  const caseLabels = {'no-fault':'No fault','crash-after-fulfillment':'Crash after fulfillment','different-message-ids':'Different message IDs','missing-observation':'Missing observation','ambiguous-side-effect':'Unsupported external effect'};
  const sourceChoice = candidate => candidate?.source === 'recorded-local' ? 'local-sample' : candidate?.source === 'import' ? 'import' : 'aws-sample';
  function renderSourceControls(view,candidate) {
    const select=at(view,'source-choice'); const option=select.querySelector('option[value="import"]');
    option.disabled=!(lastImported || candidate?.source === 'import');
    option.textContent=(candidate?.source === 'import' ? candidate : lastImported)?.kind === 'local' ? 'Imported local suite' : 'Imported file';
    select.value=sourceChoice(candidate);
  }
  function localCase(candidate) { return candidate.analysis.cases.find(item=>item.id===candidate.caseId); }
  function localEmpty(message,detail) { const node=el('div','empty-ticket'); const wrap=el('div');wrap.append(el('span','',message),el('small','',detail));node.append(wrap);return node; }
  function renderLocalReceipts(view,item,mode) {
    const observed=item.modes[mode],result=observed.result,receipts=result.ledgerSnapshot;
    const container=at(view,mode+'-receipts');container.replaceChildren();
    const unknown=observed.receiptCount===null;
    set(view,mode+'-count',unknown?'—':observed.receiptCount);
    set(view,mode+'-attempts',result.deliveries.length);
    at(view,mode+'-local-summary').hidden=false;
    const badge=at(view,mode+'-business-state');badge.textContent=observed.derivedStatus.toUpperCase();badge.className='business-state '+observed.derivedStatus;
    set(view,mode+'-run-id',result.runId);
    set(view,mode+'-execution',(!result.execution.performed?'No execution observed':result.execution.handlerInvocations+' worker invocation'+(result.execution.handlerInvocations===1?'':'s')+' · '+result.execution.providerInvocations+' provider calls')+' · expected '+observed.expectedStatus+' · file claims '+result.observedStatus);
    if(unknown) container.append(localEmpty(item.id==='ambiguous-side-effect'?'No effect was executed':'Ledger observation withheld',item.id==='ambiguous-side-effect'?'Unsupported external effect; no fulfillment is invented.':'Receipt count is unknown. A success response cannot replace the missing snapshot.'));
    else if(!receipts.length) container.append(localEmpty('No receipts in the observed snapshot','Zero observed receipts does not establish successful fulfillment.'));
    const seen=new Set();
    for(const receipt of (receipts||[]).slice(0,6)) {
      const duplicate=seen.has(receipt.orderId);seen.add(receipt.orderId);
      const ticket=el('div','receipt-ticket');
      const top=el('div','ticket-top');top.append(el('span','ticket-order',receipt.orderId),el('span','ticket-state'+(duplicate?' duplicate':''),duplicate?'DUPLICATE':'LOCAL RECEIPT'));
      const bottom=el('div','ticket-bottom');bottom.append(el('span','ticket-id',short(receipt.receiptId,22)),el('span','','QTY '+receipt.quantity));
      const meta=el('div','ticket-meta');meta.append(el('span','',receipt.sku),el('span','',clock(receipt.createdAt)+' UTC'));
      const detail=el('details','receipt-details');detail.append(el('summary','','Full receipt identity'),el('p','',receipt.receiptId));
      ticket.append(top,bottom,meta,detail);container.append(ticket);
    }
    const message=item.id==='ambiguous-side-effect'?'Unresolved · unsupported effect; no execution':unknown?'Incomplete · independent observation missing':observed.derivedStatus==='violation'?observed.receiptCount+' local receipts · fulfillment invariant violated':observed.derivedStatus==='pass'?'One local receipt · invariant held in these observations':observed.derivedStatus+' · inspect the case checks';
    const footer=at(view,mode+'-result');footer.replaceChildren(el('span','result-dot'),document.createTextNode(message));
    const card=footer.closest('.handler-card');card.dataset.state=observed.derivedStatus==='violation'?'unresolved':observed.derivedStatus;
    card.querySelector('.metric-label').textContent='local receipts';card.querySelector('.delivery-metric span').textContent='local deliveries';
    card.querySelector('.handler-description').textContent=mode==='vulnerable'?'Baseline code measured in this local case.':'Candidate repair measured in this local case.';
  }
  const localTitles={received:'Worker delivery executed',fulfillment_succeeded:'Fulfillment response received',fault_injected:'Crash injected after fulfillment',failed:'Worker raised an error',completed:'Worker completed',accepted:'Provider created a local receipt',reused:'Provider reused the local receipt',payload_conflict:'Provider rejected a payload conflict'};
  function renderLocalTimeline(view,item) {
    const node=at(view,'timeline');node.replaceChildren();
    const result=item.modes[selectedMode].result;
    if(!result.events.length){node.append(el('li','empty-state',item.id==='ambiguous-side-effect'?'No execution: the external effect model is unsupported.':'No captured events for this handler.'));return;}
    for(const event of result.events.slice().sort((a,b)=>a.localObservationIndex-b.localObservationIndex).slice(0,40)) {
      const li=el('li',event.stage==='fault_injected'||event.stage==='failed'?'fault':'');
      li.dataset.component=event.component;li.dataset.mode=result.mode;li.dataset.runId=result.runId;
      li.append(el('time','',clock(event.timestamp)),el('strong','',localTitles[event.stage]||event.stage),el('p','',event.component+' · delivery '+event.receiveCount+' · '+(event.receiptId?'receipt '+short(event.receiptId,20):'request '+short(event.requestId,20))));node.append(li);
    }
  }
  function renderLocalView(candidate) {
    const view=$('main').cloneNode(true),analysis=candidate.analysis,item=localCase(candidate),data=analysis.data;
    if(!item) throw Error('Selected local case is absent from the validated suite.');
    renderSourceControls(view,candidate);
    at(view,'local-case-controls').hidden=false;const selector=at(view,'case-selector');selector.replaceChildren();
    for(const entry of analysis.cases){const option=el('option','',caseLabels[entry.id]);option.value=entry.id;selector.append(option);}selector.value=item.id;
    set(view,'case-summary',item.title+' · '+item.order.orderId+' · '+item.order.sku+' · QTY '+item.order.quantity);
    set(view,'suite-summary','Suite expectations: '+analysis.derivedSuite.matchedCount+' / '+analysis.derivedSuite.totalCount+' matched. This includes intentional violations and non-passes; not all handlers are safe.');
    set(view,'experiment-context','LOCAL REGRESSION / RECORDED EXECUTION');
    set(view,'experiment-intro','Inspect the actual worker and provider observations from a bounded local execution. Choose a case, compare business outcomes, then inspect each trace.');
    set(view,'run-status',analysis.status.toUpperCase());at(view,'run-status').className='status-badge '+analysis.status;
    set(view,'evidence-title',(candidate.source==='import'?'Imported local suite':'Recorded local suite')+' · '+caseLabels[item.id]);
    set(view,'source-badge',candidate.source==='import'?'YOUR LOCAL REPORT':'RECORDED LOCAL RUN');
    set(view,'origin-badge','LOCAL ORIGIN UNAUTHENTICATED');
    set(view,'claimed-verdict','File claims: SUITE '+analysis.claimedStatus.toUpperCase());
    set(view,'evidence-subtitle','Local execution report · '+analysis.cases.length+' cases · generated '+date(data.recordedAt));
    set(view,'region-label','ENVIRONMENT');set(view,'region','Process-local adapters');set(view,'recorded-at',date(data.recordedAt));
    set(view,'verification-summary','The browser derives per-handler business outcomes from this report. It does not execute code or authenticate the imported run. Suite expectation matches are separate from handler safety.');
    const reasons=at(view,'verification-reasons');reasons.replaceChildren();
    for(const check of analysis.checks.filter(check=>check.status!=='passed'))reasons.append(el('li','',check.label+': '+check.detail+' Expected '+valueText(check.expected)+'; observed '+valueText(check.observed)+'.'));
    if(!item.expectationsMatched)reasons.append(el('li','','Expected outcome mismatch: this case differs from one or more frozen expected outcomes. Inspect the business verdicts and checks below.'));
    if(item.id==='missing-observation')reasons.append(el('li','','Both ledger snapshots are withheld. Counts are unknown and the business outcomes remain incomplete.'));
    if(item.id==='ambiguous-side-effect')reasons.append(el('li','','The external effect is unsupported. Neither handler executed; both business outcomes remain unresolved.'));
    reasons.hidden=!reasons.childElementCount;
    set(view,'hero-order',item.order.orderId);set(view,'hero-sku',item.order.sku+' · QTY '+item.order.quantity);
    const definition=item.modes.vulnerable.result.case;
    set(view,'fault-description',item.id==='ambiguous-side-effect'?'Unsupported external effect · no handler execution':item.id==='missing-observation'?'No injected fault · ledger snapshot deliberately withheld':definition.fault==='none'?'Fault condition: none · declared local delivery schedule':'Fault: crash after local fulfillment, then explicitly deliver the same message again');
    set(view,'fault-bound',definition.maxDeliveries+' DECLARED DELIVERIES');
    for(const mode of ['vulnerable','repaired'])renderLocalReceipts(view,item,mode);
    set(view,'receipt-caption','These receipts are observations from a process-local memory ledger. They are not durable AWS receipts.');
    renderLocalTimeline(view,item);set(view,'trace-note','All captured worker and provider events for the selected local handler, ordered by local observation index.');
    renderAssertions(view,{checks:item.checks});set(view,'assertion-title','Selected case checks');
    set(view,'checks-note','Recomputed from the selected case inputs, deliveries, events and ledger snapshot. Open each check for expected and observed values. Source and execution origin remain unauthenticated.');
    const fps=at(view,'fingerprints');fps.hidden=false;const list=at(view,'fingerprint-list');list.replaceChildren();
    for(const [name,digest] of Object.entries(analysis.fingerprints.sources))list.append(el('dt','',name),el('dd','',digest));
    const casePath='cases/local/'+item.id+'.json';list.append(el('dt','',casePath),el('dd','',analysis.fingerprints.cases[casePath]),el('dt','','Frozen case plan'),el('dd','',analysis.fingerprints.plan.sha256));
    set(view,'evidence-file-label',candidate.name+' · complete local suite retained · package downloads are unchanged');
    at(view,'view-evidence').disabled=false;at(view,'download-evidence').disabled=false;set(view,'view-evidence','View suite JSON');set(view,'download-evidence','Download suite JSON');at(view,'aws-inspector-link').hidden=true;
    set(view,'comparison-origin-note','The comparison above shows the selected process-local execution case, not a new cloud run.');
    set(view,'how-title','Run locally. Inspect the captured result.');
    const steps=at(view,'how-it-works').querySelector('.how-grid');steps.replaceChildren();
    [['01','Execute in your terminal','The unchanged Python runner invokes the real worker and provider through explicit local adapters.'],['02','Read the independent snapshot','The memory ledger records the modeled receipt effect. Missing snapshots stay unknown.'],['03','Compare business outcomes','The browser checks the selected case observations and preserves the original file. Expected buggy outcomes never mean all handlers are safe.']].forEach(([n,title,body])=>{const article=el('article');article.append(el('span','step-number',n),el('h3','',title),el('p','',body));steps.append(article);});
    at(view,'how-it-works').querySelector('.scope-note p').textContent='Local schedules do not emulate service durability, queue timing or concurrent delivery. An arbitrary external side effect without an atomic receiver contract remains unsupported.';
    const limits=at(view,'limitations');limits.replaceChildren();data.boundaries.forEach(boundary=>limits.append(el('p','',boundary)));
    set(view,'journey-import-message','');set(view,'import-message','');at(view,'import-message').className='import-message';return view;
  }
  function renderReferenceRepair() {
    const reference=window.ReplayGuardReferenceRepair;
    if(!reference)return;
    const content=$('reference-content');content.replaceChildren();
    content.append(el('p','reference-trust','Included reference source, not evidence of what an imported report executed. Matching self-reported hashes do not authenticate code or execution origin.'));
    const grid=el('div','repair-grid');
    function excerpt(parent,key,label) {
      const part=reference.excerpts[key],file=reference.files[part.file];
      const block=el('div','reference-excerpt');block.append(el('p','reference-location',file.path+' · lines '+part.start+'–'+part.end));
      const pre=el('pre','reference-code');pre.id='reference-'+key;pre.tabIndex=0;pre.setAttribute('aria-label',label+'; exact '+file.path+' excerpt, lines '+part.start+' to '+part.end+'. Scroll to inspect longer lines and more code.');pre.append(el('code','',part.text));block.append(pre, el('p', 'code-scroll-hint', 'Scroll to read the full source →'));parent.append(block);
    }
    const caller=el('section','repair-part');caller.setAttribute('aria-labelledby','reference-worker-title');
    const workerTitle=el('h3','','One key for the business operation');workerTitle.id='reference-worker-title';caller.append(workerTitle,el('p','','The vulnerable path omits the key. The repaired worker sends the same key when the order is delivered again, even with a different message ID.'));
    excerpt(caller,'workerRepair','Repaired worker supplies the stable key');
    excerpt(caller,'workerKey','Stable key construction');
    caller.append(el('p','reference-context','Here the key hashes [runId, orderId]. runId isolates one lab experiment and stays fixed across its deliveries. A production operation needs a stable business identity across retries; a fresh run or attempt ID would defeat that guarantee.'));
    const receiver=el('section','repair-part');receiver.setAttribute('aria-labelledby','reference-provider-title');
    const providerTitle=el('h3','','Let the receiver accept it once');providerTitle.id='reference-provider-title';receiver.append(providerTitle,el('p','','The receipt is the complete simulated effect. A conditional write creates it once. A matching retry reads and returns the original receipt; conflicting fulfillment inputs are rejected.'));
    excerpt(receiver,'providerWrite','Receiver conditional write and receipt reuse');
    const context=el('details','reference-context-disclosure');context.append(el('summary','','Inspect receiver key validation and receipt selection'));
    excerpt(context,'providerValidation','Receiver validates the supplied key');excerpt(context,'providerSelection','Receiver chooses the receipt identity');receiver.append(context);
    grid.append(caller,receiver);content.append(grid);
    content.append(el('p','reference-boundary','This requires the receiver to own the atomic effect. It does not guarantee exactly-once SQS delivery or make a separate shipping/payment API idempotent. The local runner exercises these included functions through memory and transport adapters.'));
    const identities=el('details','reference-identities');identities.append(el('summary','','Included source version and SHA-256'));
    identities.append(el('p','','Reference snapshot '+reference.version+' · source files unchanged in this build.'));
    const list=el('dl');for(const file of Object.values(reference.files))list.append(el('dt','',file.path),el('dd','',file.sha256));identities.append(list);content.append(identities);
    const next=el('a','button secondary','Next: run the local regression ↓');next.href='#regression';content.append(next);
  }
  function buildView(candidate) {
    const view = candidate.kind === 'local' ? renderLocalView(candidate) : buildAwsView(candidate);
    // The narrow-screen overview mirrors the already-derived comparison atomically.
    for (const mode of ['vulnerable', 'repaired']) {
      const count = at(view, mode + '-count').textContent;
      const card = at(view, mode + '-card');
      set(view, 'compact-' + mode + '-count', count);
      set(view, 'compact-' + mode + '-label', count === '—' ? 'count unknown' : card.querySelector('.metric-label').textContent);
      at(view, 'compact-' + mode).dataset.state = card.dataset.state;
      set(view, 'compact-' + mode + '-state', candidate.kind === 'local' ? at(view, mode + '-business-state').textContent : card.dataset.state.toUpperCase());
    }
    return view;
  }
  function changeLocalCase(id) {
    if(current?.kind!=='local')return;
    const candidate={...current,caseId:id};
    try {const view=buildView(candidate);commit({candidate,view});announce('Selected local case: '+caseLabels[id]+'.');}
    catch(error){feedback('Could not change case: '+error.message+' Previous data and view are unchanged.',true);}
  }

  function prepare(raw, blob, source, name) {
    const parsed = JSON.parse(raw);
    const kind=parsed?.provenance==='local-execution'?'local':'aws';
    const analysis=kind==='local'?window.ReplayGuardLocalReport.analyzeLocalReport(parsed):window.ReplayGuardEvidence.analyzeEvidence(parsed);
    const candidate = {raw,blob,source,name,analysis,kind,caseId:kind==='local'?'crash-after-fulfillment':null};
    return {candidate,view:buildView(candidate)};
  }
  function commit(prepared) {
    const focusedId = document.activeElement?.id;
    $('main').replaceWith(prepared.view); // Single atomic DOM commit; state follows it.
    current = prepared.candidate;
    if(current.source==='import')lastImported=current;
    if (focusedId) { try { $(focusedId)?.focus({preventScroll:true}); } catch {} }
  }
  function unavailable(message) {
    if (current) return;
    $('run-status').textContent = 'INCOMPLETE'; $('run-status').className = 'status-badge incomplete';
    $('evidence-title').textContent = 'No evidence loaded';
    $('evidence-subtitle').textContent = message;
    $('verification-summary').textContent = 'Choose a recorded sample to retry, or import a supported AWS export or full local suite. These actions read local evidence.';
  }
  async function loadRecordedSample(initial = false, local = false) {
    const token = ++operation;
    if (!initial) feedback('Loading the recorded sample. The current view stays available until it is ready.');
    try {
      const response = await fetch(local?'./local-example.json':'./evidence.json',{cache:'no-store'});
      if (!response.ok) throw new Error('Recorded sample could not be read (HTTP ' + response.status + ').');
      if (Number(response.headers.get('content-length')) > MAX_BYTES) throw new Error('Recorded sample exceeds the 5 MB limit.');
      const blob = await response.blob(); if (blob.size > MAX_BYTES) throw new Error('Recorded sample exceeds the 5 MB limit.');
      const raw = await blob.text(); if (token !== operation) return;
      const prepared = prepare(raw,blob,local?'recorded-local':'recorded',local?'Recorded local suite':'Recorded sample');
      commit(prepared);
      feedback((local?'Recorded local suite':'Recorded AWS sample')+' loaded. Browser report state: '+current.analysis.status+'. Execution origin remains unauthenticated.');
    } catch (error) {
      if (token !== operation) return;
      unavailable('The recorded data file could not be loaded.');
      feedback(error.message + (current ? ' The previous data and view are unchanged.' : ' Use Restore recorded sample to retry, or import a supported export.'),true);
    }
  }
  async function importFile(file) {
    const token = ++operation;
    try {
      if (file.size > MAX_BYTES) throw new Error('Evidence files must be at most 5 MB.');
      const raw = await file.text(); if (token !== operation) return;
      const prepared = prepare(raw,file,'import',file.name);
      commit(prepared);
      feedback('Loaded ' + file.name + ' locally. Browser result: ' + current.analysis.status + '. The original JSON is unchanged; no file was uploaded. ZIP downloads still contain their original packages.');
    } catch (error) {
      if (token !== operation) return;
      unavailable('No supported evidence file has been loaded.');
      const detail = ['UNSUPPORTED_SCHEMA', 'UNSUPPORTED_PROVENANCE'].includes(error.code)
        ? 'Unsupported report format. Choose a full local-results.json suite or a recorded AWS evidence export.'
        : error.message;
      feedback('Import rejected: ' + detail + ' Previous data and view are unchanged.',true);
    }
  }
  function download() {
    if (!current) return;
    const url = URL.createObjectURL(current.blob); const link = el('a'); link.href = url; link.download = current.kind==='local'?'replayguard-local-suite.json':'replayguard-' + current.analysis.data.runId + '.json'; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  async function copyCommand(id, label) {
    const command = $(id);
    try { await navigator.clipboard.writeText(command.textContent); notify(label + ' copied'); }
    catch { const range = document.createRange(); range.selectNodeContents(command); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); notify('Command selected. Press your copy shortcut.'); }
  }
  // Delegation keeps every control connected after an atomic main replacement.
  document.addEventListener('click',event => {
    const button = event.target.closest('button,a'); if (!button) return;
    if (button.matches('button[data-mode]')) { selectedMode = button.dataset.mode; document.querySelectorAll('button[data-mode]').forEach(b => { b.classList.toggle('selected',b === button); b.setAttribute('aria-pressed',String(b === button)); }); if(current?.kind==='local')renderLocalTimeline($('main'),localCase(current));else renderTimeline($('main'),current?.analysis.data); }
    if(button.matches('a[href="#reference-repair"]')) { event.preventDefault(); $('reference-repair').open=true; if(location.hash!=='#reference-repair')history.pushState(null,'','#reference-repair'); $('reference-repair').scrollIntoView({block:'start'}); $('reference-repair-summary').focus({preventScroll:true}); }
    if (button.matches('.nav-link')) document.querySelectorAll('.nav-link').forEach(l => l.classList.toggle('active',l === button));
    if (button.dataset.copy) copyCommand(button.dataset.copy,button.dataset.copyLabel);
    if (button.id === 'copy-cli') copyCommand('cli-code','Local execution commands');
    if (button.id === 'view-evidence' && current) { $('json-content').textContent = current.raw; $('json-dialog').showModal(); $('close-json').focus(); }
    if (button.id === 'close-json') $('json-dialog').close();
    if (button.id === 'download-evidence') download();
    if (button.id === 'import-evidence' || button.id === 'import-report-trigger' || button.id === 'import-local-report') $('evidence-upload').click();
    if (button.id === 'restore-sample') loadRecordedSample();
  });
  $('json-dialog').addEventListener('close',() => $('view-evidence').focus({preventScroll:true}));
  $('json-dialog').addEventListener('keydown',event => {
    if (event.key !== 'Tab') return;
    const first = $('close-json'), last = $('json-content');
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  document.addEventListener('change',event => {
    if(event.target.id==='case-selector'){const id=event.target.value;event.target.value=current.caseId;changeLocalCase(id);return;}
    if(event.target.id==='source-choice'){const choice=event.target.value;event.target.value=sourceChoice(current);if(choice==='aws-sample')loadRecordedSample();else if(choice==='local-sample')loadRecordedSample(false,true);else if(choice==='import' && lastImported){++operation;try{commit({candidate:lastImported,view:buildView(lastImported)});feedback('Restored the last accepted imported file.');}catch(error){feedback(error.message+' Previous view unchanged.',true);}}return;}
    if (event.target.id !== 'evidence-upload') return; const file = event.target.files?.[0]; event.target.value = ''; if (file) importFile(file); });
  renderReferenceRepair();
  renderReceipts($('main'),null,'vulnerable'); renderReceipts($('main'),null,'repaired'); renderTimeline($('main'),null); renderAssertions($('main'),null);
  loadRecordedSample(true);
})();
