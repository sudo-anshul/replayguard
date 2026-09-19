# Reproduce the actual recording workbench

These are the source files used to edit and execute the disposable candidate through a browser. The helper is local production tooling, separate from the public app.

From the repository root, using Python 3.11+ on macOS/Linux:

```sh
python3 docs/repair-lab/media/revision-2/recording/prepare.py
python3 docs/repair-lab/media/revision-2/recording/tutorial-viewer/server.py
```

Open `http://127.0.0.1:8767`. Preparation checks and extracts the pinned public kit; it executes no case. The server binds only to `127.0.0.1` and uses only the standard library. Stop any prior workbench using the same port first.

1. Click **Run baseline**. This genuinely executes the selected case.
2. Change only `key=order["orderId"]` to `key=None`, keep the final newline, and click **Save adapter**.
3. Click **Run broken**. The expected observed regression returns process exit 1.
4. Restore the original key and save, then click **Run repaired**.

Reports are written to `recording/tutorial/{baseline,broken,repaired}.json`. Import those actual files into the product's **Import your run** control. The workbench output comes from real subprocess stdout/stderr; receipt counts come from retained execution records. No terminal typing, output, verdict or receipt is simulated by this UI.

To check the new recorded evidence without rerunning a candidate:

```sh
cd docs/repair-lab/media/revision-2/recording/tutorial
python3 validate_demo.py
```

The recorder refuses to overwrite stages. It captures sources before/after, command arguments, actual exit status, raw output and original report bytes. On macOS it invokes `sandbox-exec` to deny network when available. The public Python lab is for trusted code; this is not a hostile-code sandbox.

The loopback server restricts Host and Origin, routes, stage names, paths, JSON body size and accepted source variants. Save and Run operations are serialized. Preparation creates its own ignored `tutorial/` directory and never edits the repository's runtime sources. The original workbench and recorder files are copied byte-for-byte into this handoff; `prepare.py` is a portable packaging addition.
