# ReplayGuard silent demonstration — reproducible source

**Complete recorded-rendering source package.** All static frame, report, editorial, and composition inputs are included below the 10 MB source budget. Verify them with the commands below before rendering.

The package contains the 154-second silent Remotion composition, its locked JavaScript dependencies, original execution reports and source snapshots, and deduplicated original browser screenshots. Original screenshot containers are preserved byte for byte with no additional lossy conversion. Generated MP4s, `node_modules`, downloaded browsers, duplicate frame directories, and AWS credentials are excluded. No paid service or AWS account is required to render this recorded demonstration.

## Requirements

- Node.js 22 or newer and npm; install the exact packages with `npm ci`.
- Python 3.11 or newer for the standard-library rebuild script.
- FFmpeg/ffprobe with JPEG/PNG/WebP decoding and `libx264` encoding.
- An installed Chrome/Chromium executable, supplied in `CHROME_EXECUTABLE`.

The dependency lock is copied from the renderer used to make the demonstration. The reproducibility promise covers complete static inputs, exact original screenshot-container bytes, chronology, explicit editorial timing, report data, and composition source. System Chrome, FFmpeg, operating-system fonts, and encoder versions can affect final pixels or MP4 bytes. Encoded-byte hashes are authoritative for the preserved originals. Canonical RGBA pixel hashes use the FFmpeg build recorded in `source-manifest.json`; JPEG chroma/RGB rounding can differ across decoder implementations or builds.

## Render from this directory

```sh
npm ci
python3 scripts/rebuild-captures.py --verify-only --pixels
python3 scripts/rebuild-captures.py
export CHROME_EXECUTABLE="/absolute/path/to/installed/chrome"
npx --no-install tsc --noEmit
node scripts/prepare.mjs
node scripts/render-bounded.mjs --output render/replayguard-demo-silent.mp4
node scripts/validate.mjs render/replayguard-demo-silent.mp4
python3 scripts/sample-final.py render/replayguard-demo-silent.mp4
```

On macOS the executable is commonly `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`; on Linux it may be `/usr/bin/chromium` or `/usr/bin/google-chrome`. Supply the actual installed path. These commands do not download a browser automatically.

`rebuild-captures.py` verifies every packaged static-file hash. Its optional `--pixels` check decodes each unique original screenshot and checks the canonical RGBA hash. Use the recorded FFmpeg build for an exact pixel comparison. Rebuilding emits ignored source MP4s and fresh encoded-source manifests; final preparation then resolves all sources relative to this directory. `--capture CAPTURE_ID` rebuilds one clip for troubleshooting. Rendered outputs remain local and ignored by Git.

`render-bounded.mjs` renders inclusive ranges of at most 400 composition frames per chunk by default, using one bundled browser. It checks every chunk's frame count and zero-audio contract, then concatenates their H.264 streams without re-encoding. `bounded-render-manifest.json` retains the composition fingerprint, frame ranges, chunk hashes, and final hash. Final validation and sampled-frame review remain required. This limits temporary frame storage when low free RAM prevents Remotion from streaming the entire film; allow headroom for runtime bundles and chunk outputs. For environments with sufficient resources, `scripts/render.mjs` also supports a single render.

`sample-final.py` extracts two review frames per scene from the encoded movie itself and records the movie hash, frame positions, and timestamps. These samples support visual review; they do not replace it. The composition and review bundle disable disk caching to keep local intermediates bounded.

## Evidence and editorial boundaries

The browser footage consists of timestamped screenshots of actual interactions. Its source sampling rate varies. The output container and independent explanatory animation are 30 fps; this is not native 30 fps screen recording. Frames repeat during deliberately documented reading holds. Each capture's `encoding-recipe.json` retains original timestamps and intervals, retained intervals, omitted elapsed gaps, reading holds, and output positions. The film labels reading holds and distinguishes the recording helper from the product.

AWS observations, the recorded local comparison, and fresh local adapter execution retain separate labels. The local `orderId → sku → orderId` mutation does not imply a cloud deployment. The original three execution reports, raw stdout/stderr, source before/after, and execution records are retained in `evidence/`. Rendering reads those reports; it does not rerun the adapter or authenticate AWS origin. Receipt counts and status summaries are derived from the observed reports, not invented animation values. The JSON evidence export and runnable regression ZIP are different artifacts.

The captured files originally used `.png` filenames, but their actual containers are JPEG. The package detects the formats, uses `.jpg` filenames, and retains the misleading original names as provenance. Deduplication changes neither the encoded bytes nor their image dimensions; no new image encoding is performed. Hashes establish identity, not signatures or proof that an imported report came from AWS. Final-source manifests record original input hashes and package-relative replacements. Machine-specific capture paths are omitted from published capture manifests while chronology is preserved.

The frozen AWS experiment is run `82a1155f-c729-4b56-a32f-b4bc9a70a3ad`, recorded 19 September 2026 at 19:36:17 UTC. Its report SHA-256 is `49132ede7271bfa8c1e091bbde339a350eece3d47f8a41ce17af9fce4047d4f2`. All 22 experiment assertions passed; the business outcomes remain two violations and one pass. Independent receipt counts are A2/B2 with no key, A1/B0 with SKU, and A1/B1 with order ID. Cleanup was independently observed as deleted. The simulated provider fails after receipt commit and before a successful response returns. The film makes no OS-process-kill claim.

Captured-action scenes account for 75.974% of the film, including 98.119 seconds of explicitly disclosed reading holds. This is an editorial content measure, not a claim of continuous native-video footage. The final count shot returns to an earlier captured snapshot and is labeled accordingly. Long capture gaps are recorded as omitted elapsed time. The regression kit was verified from served HTTP bytes and extracted cleanly; the film does not claim that the native browser completed a fresh ZIP download.

`source-verification.json` records the completed same-runtime check: all 91 original screenshot identities and canonical RGBA hashes passed, all 16 rebuilt source clips matched their original MP4 hashes, and the prepared composition was byte-identical. The portable validator also checked the separately rendered 154-second master against these rebuilt assets. A second full-master render and fresh dependency installation were not performed.

The source package is **self-contained for recorded rendering only when `source-manifest.json` says `status: complete` and `selfContainedStaticInputs: true`**. Runtime dependencies listed above remain external. Reproducing new AWS experiments or new adapter executions is described by the main ReplayGuard repository, and is separate from rendering this captured evidence.
