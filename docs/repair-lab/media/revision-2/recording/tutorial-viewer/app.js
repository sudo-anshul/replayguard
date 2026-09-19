'use strict';
const $ = id => document.getElementById(id);
let savedCode = '', currentKind = '', runs = {}, busy = false;
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
function controls() {
  const dirty = $('code').value !== savedCode;
  $('save').disabled = busy || !dirty;
  $('code').disabled = busy;
  $('save-state').textContent = dirty ? 'Unsaved changes' : 'Saved to actual file';
  $('save-state').classList.toggle('dirty', dirty);
  $('key-state').textContent = currentKind === 'business-key' ? 'key = business order' : currentKind === 'no-key' ? 'key = None' : 'unknown key';
  for (const button of document.querySelectorAll('[data-stage]')) {
    const stage = button.dataset.stage;
    const matching = stage === 'broken' ? currentKind === 'no-key' : currentKind === 'business-key';
    button.disabled = busy || dirty || !matching || Boolean(runs[stage]);
    button.classList.toggle('ready', !button.disabled);
  }
}
async function request(path, payload) {
  const response = await fetch(path, payload === undefined ? {cache:'no-store'} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function acceptState(data) { savedCode = data.code; currentKind = data.kind; runs = data.runs; $('code').value = savedCode; }
$('code').addEventListener('input', () => { controls(); message('Save the changed adapter before running it.'); });
$('code').addEventListener('keydown', event => {
  if (event.key === 'Tab') {
    event.preventDefault();
    const field = event.target, start = field.selectionStart, end = field.selectionEnd;
    field.setRangeText('    ', start, end, 'end');
    field.dispatchEvent(new Event('input'));
  }
});
$('save').addEventListener('click', async () => {
  busy = true; controls();
  try { acceptState(await request('/api/save', {code:$('code').value})); message('Saved candidate/adapter.py. The next command will execute these bytes.'); }
  catch (error) { message(error.message, true); }
  finally { busy = false; controls(); }
});
for (const button of document.querySelectorAll('[data-stage]')) button.addEventListener('click', async () => {
  const stage = button.dataset.stage;
  busy = true; controls();
  for (const b of document.querySelectorAll('[data-stage]')) b.classList.toggle('current', b === button);
  $('result').className = 'result'; $('result').textContent = 'Running actual Python…';
  $('output').textContent = 'Executing the saved adapter…';
  message('The case is executing in the local Python process.');
  try {
    const data = await request('/api/run', {stage});
    acceptState(data);
    $('output').textContent = data.stdout + (data.stderr ? '\n' + data.stderr : '');
    const evidence = data.evidence;
    if (evidence) {
      const state = evidence.reportedStatus || 'incomplete';
      $('result').className = 'result ' + state;
      const status = {pass:'PASS', violation:'VIOLATION', incomplete:'INCOMPLETE', unresolved:'UNRESOLVED'}[state] || state.toUpperCase();
      const count = evidence.observedReceipts;
      $('result').textContent = `${status} · ${count === null ? 'unknown' : count} receipt${count === 1 ? '' : 's'} · exit ${evidence.processExitCode}`;
      $('report-path').textContent = `Generated ${evidence.report} · original bytes retained`;
      message('Actual command, process exit, source snapshots and report saved for this take.');
    } else {
      $('result').textContent = `Command exit ${data.processExitCode} · no run evidence`;
      message('The command did not produce a retained execution report. Inspect the actual output.', true);
    }
  } catch (error) {
    $('result').textContent = 'Execution not completed';
    $('output').textContent = error.message;
    message(error.message, true);
  } finally { busy = false; controls(); }
});
request('/api/state').then(data => { acceptState(data); controls(); }).catch(error => { message(error.message, true); });
