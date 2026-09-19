# ReplayGuard repair demo source

The new companion video is `outputs/replayguard-repair-demo.mp4`, outside the
repository directory. This is a narrated edit of actual local UI captures and
recorded command results. It is not continuous screen-recording footage and
does not show a new AWS execution. The two earlier videos remain unchanged.

`narration.json` is the spoken script and shot list. `transcript.txt` and
`narration.srt` are generated from measured native speech chunks.
`capture-manifest.json` identifies the exact loopback-rendered product states;
`manifest.json` freezes that capture provenance again inside the render record.
It also records each source image hash and crop, voice, actual command data,
output hash, codec, duration, full-decode result and sampled exported frames.
`contact-sheet.jpg` shows the source composition for every shot, while
`validation-frames/` contains frames extracted from the exported MP4.

The CLI section reproduces actual argv, stdout and process exits from
[`execution/final/`](execution/final/). The receipt counts and source hashes
come from those generated reports. The candidate was copied from a fresh
portable-kit extraction, changed to remove its key, and restored to the exact
original bytes. The four actual subprocesses ran with isolated/no-site Python
and the existing macOS network-denial wrapper. No typing or execution output
was fabricated for the video.

The transfer table is generated from the three reports in
[`../transfer-results/final-numeric-runtime/`](../transfer-results/final-numeric-runtime/).
The first, previously unseen execution and the frozen fixture remain separately
retained. Both fixture and evaluator authors were AI agents; this is bounded
API transfer on synthetic inputs, not customer validation.

## Re-render locally

The renderer uses already-installed Pillow, FFmpeg, FFprobe and macOS `say`
with the Samantha voice. It performs no install, network request or paid media
call. A Python environment with Pillow is needed only for video composition;
the repair runtime itself uses the Python standard library.

```sh
python3 docs/repair-lab/media/render_demo.py --frames-only
python3 docs/repair-lab/media/render_demo.py
```

The renderer refuses to overwrite the output MP4. For an intentional revision,
preserve the existing new demo elsewhere first; never move or overwrite a
historical demo. Temporary speech and intermediate videos live under the
workspace `work/repair-demo-render/` directory. It freezes input screenshots
before composing frames, verifies the known capture hashes, checks all earlier
MP4 hashes before and after, limits the duration to 170 seconds, and fully
decodes the resulting video.

Native speech varies by macOS voice version, so a re-render need not be byte
identical. The source snapshots and manifests identify the bytes actually used.
