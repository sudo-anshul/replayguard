#!/usr/bin/env python3
"""Rebuild actual screenshot clips from package-relative, auditable recipes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inside(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Path escapes the source package: {name}")
    return path


def verify(pixels=False):
    manifest = json.loads((ROOT / "source-manifest.json").read_text())
    if manifest["status"] != "complete" or not manifest["selfContainedStaticInputs"]:
        raise RuntimeError("This source package is incomplete.")
    for name, expected in manifest["files"].items():
        if digest(inside(name).read_bytes()) != expected:
            raise RuntimeError(f"Static input hash mismatch: {name}")
    if pixels:
        decoder = subprocess.check_output(["ffmpeg", "-version"], text=True)
        recorded = manifest["canonicalPixelDecoder"]
        if digest(decoder.encode()) != recorded["versionOutputSha256"]:
            print("FFmpeg build differs from the canonical decoder; byte hashes remain authoritative. Pixel verification may differ due to JPEG decoder rounding.", flush=True)
        for name, frame in manifest["frames"].items():
            decoded = subprocess.check_output([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(inside(name)),
                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-",
            ])
            if len(decoded) != frame["width"] * frame["height"] * 4 or digest(decoded) != frame["rgbaSha256"]:
                raise RuntimeError(f"Canonical FFmpeg RGBA verification failed: {name}; use the recorded decoder build for exact pixel comparison.")
    return manifest


def encode(capture_id, settings):
    folder = inside(settings["directory"])
    capture_manifest = folder / "manifest.json"
    source = json.loads(capture_manifest.read_text())
    recipe = json.loads((folder / "encoding-recipe.json").read_text())
    frames = source["frames"]
    times = [frame["timestamp"] for frame in frames]
    if any(b < a for a, b in zip(times, times[1:])):
        raise ValueError(f"Non-monotonic capture timestamps: {capture_id}")
    records = recipe["frames"]
    concat, rebuilt_records = [], []
    output_time = 0.0
    for record in records:
        frame = frames[record["index"]]
        file = (folder / frame["path"]).resolve()
        if not file.is_relative_to(ROOT):
            raise ValueError("Frame path escapes source package")
        duration = record["retainedIntervalSeconds"] + record["editorialReadingHoldSeconds"]
        if abs(duration - record["outputDurationSeconds"]) > 0.00001:
            raise ValueError("Recipe hold/interval disagreement")
        if abs(output_time - record["outputStartSeconds"]) > 0.00001:
            raise ValueError("Recipe chronology disagreement")
        escaped = str(file).replace("'", "'\\''")
        concat.extend([f"file '{escaped}'", f"duration {duration:.9f}"])
        rebuilt_records.append({**record, "file": frame["path"], "sha256": digest(file.read_bytes()), "sourceFrameSha256": frame["sourceFrameSha256"], "sourceDetectedFormat": frame["sourceDetectedFormat"], "rgbaSha256": frame["rgbaSha256"]})
        output_time += duration
    last_file = (folder / frames[-1]["path"]).resolve()
    escaped = str(last_file).replace("'", "'\\''")
    concat.append(f"file '{escaped}'")
    concat_path = folder / "editorial.ffconcat"
    concat_path.write_text("\n".join(concat) + "\n")
    output = folder / "source.mp4"
    # MP4 format duration is rounded to milliseconds; use the exact 30fps
    # interval/hold sum so a fractional duration cannot gain an extra frame.
    target = round(output_time * 30) / 30
    if abs(target - recipe["outputDurationSeconds"]) > 0.002:
        raise ValueError("Encoded duration disagrees with the editorial recipe")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-vf", "fps=30", "-t", f"{target:.6f}", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-threads", "2", str(output)]
    subprocess.run(command, check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(output), "-f", "null", "-"], check=True)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]))
    video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    duration = float(probe["format"]["duration"])
    if abs(duration - target) > 1 / 30 or any(stream["codec_type"] == "audio" for stream in probe["streams"]):
        raise ValueError("Rebuilt capture duration/audio contract failed")
    expected_frames = round(target * 30)
    if int(video["nb_frames"]) != expected_frames:
        raise ValueError("Rebuilt capture frame-count contract failed")
    rebuilt = {**recipe, "id": capture_id, "captureManifestSha256": digest(capture_manifest.read_bytes()), "videoSha256": digest(output.read_bytes()), "outputDurationSeconds": duration, "width": video["width"], "height": video["height"], "frameCount": expected_frames, "fullDecodeExitCode": 0, "audioStreamCount": 0, "rawFramesRetained": False, "originalContainerBytesPreserved": True, "additionalLossyReencodesDuringPackaging": 0, "frames": rebuilt_records, "rebuildNote": "Original screenshot containers were preserved byte for byte and deduplicated. rawFramesRetained=false describes removal of the duplicate original directory layout, not removal of source bytes. Capture chronology and explicit reading holds/gap cuts are preserved. Canonical RGBA hashes use the FFmpeg build recorded in source-manifest.json; JPEG decoding and encoded MP4 bytes may vary by runtime version."}
    (folder / "encoded-source.json").write_text(json.dumps(rebuilt, indent=2) + "\n")
    print(f"Rebuilt {capture_id}: {duration:.3f}s, zero audio streams", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--pixels", action="store_true", help="Decode each unique original screenshot through FFmpeg and verify build-scoped canonical RGBA hashes")
    parser.add_argument("--capture", help="Rebuild only one capture ID")
    args = parser.parse_args()
    manifest = verify(pixels=args.pixels)
    if args.verify_only:
        print(f"Verified {len(manifest['files'])} static files and {len(manifest['frames'])} frame identities.")
        return
    captures = manifest["captures"]
    if args.capture and args.capture not in captures:
        parser.error("Unknown capture ID")
    for capture_id, settings in captures.items():
        if not args.capture or capture_id == args.capture:
            encode(capture_id, settings)


if __name__ == "__main__":
    main()
