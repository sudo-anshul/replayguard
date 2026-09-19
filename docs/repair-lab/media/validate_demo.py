#!/usr/bin/env python3
"""Check the already-rendered demo with existing ffmpeg/ffprobe, without network."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    video = Path(manifest['output'])
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg and ffprobe
    checks = []

    def check(name, passed, observed):
        checks.append({'name': name, 'status': 'pass' if passed else 'fail', 'observed': observed})

    actual_sha = sha(video)
    check('output-hash-matches-render', actual_sha == manifest['outputSha256'], actual_sha)
    probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(video)]))
    duration = float(probe['format']['duration'])
    streams = probe['streams']
    picture = next(s for s in streams if s['codec_type'] == 'video')
    audio = next(s for s in streams if s['codec_type'] == 'audio')
    check('duration-under-170-seconds', 0 < duration <= 170, duration)
    check('h264-1080p-24fps', (picture['codec_name'], picture['width'], picture['height'], picture['r_frame_rate']) == ('h264', 1920, 1080, '24/1'), picture)
    check('aac-narration-present', audio['codec_name'] == 'aac' and int(audio['sample_rate']) == 44100, audio)
    decode = subprocess.run([ffmpeg, '-v', 'error', '-i', str(video), '-f', 'null', '-'], capture_output=True, text=True)
    check('full-video-and-audio-decode', decode.returncode == 0 and not decode.stderr.strip(), {'exitCode': decode.returncode, 'stderr': decode.stderr})
    volume = subprocess.run([ffmpeg, '-hide_banner', '-i', str(video), '-af', 'volumedetect', '-vn', '-f', 'null', '-'], capture_output=True, text=True)
    (HERE / 'audio-volume-validation.txt').write_text(volume.stderr)
    mean = re.search(r'mean_volume: (-?[\d.]+) dB', volume.stderr)
    peak = re.search(r'max_volume: (-?[\d.]+) dB', volume.stderr)
    measured = {'meanDb': float(mean[1]) if mean else None, 'peakDb': float(peak[1]) if peak else None}
    check('audio-is-audible-and-below-clipping', volume.returncode == 0 and mean and peak and -30 < measured['meanDb'] < -5 and -12 < measured['peakDb'] < 0, measured)
    historical = {name: sha(video.parent / name) for name in manifest['historicalVideosBefore']}
    check('historical-videos-byte-identical', historical == manifest['historicalVideosBefore'] == manifest['historicalVideosAfter'], historical)
    capture_source = {c['file']: c['sha256'] for c in manifest['captureSource']['captures']}
    image_matches = []
    for scene in manifest['scenes']:
        provenance = scene['provenance']
        if 'screenshot' in provenance:
            path = REPO / provenance['screenshot']
            image_matches.append({'file': provenance['screenshot'], 'matches': sha(path) == provenance['screenshotSha256'] == capture_source[path.name]})
    check('actual-screenshot-hashes-match-frozen-capture-manifest', all(x['matches'] for x in image_matches), image_matches)
    srt = (HERE / 'narration.srt').read_text()
    timecodes = re.findall(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', srt)
    times = [tuple(int(x) for x in t) for t in timecodes]
    to_seconds = lambda t: t[0] * 3600 + t[1] * 60 + t[2] + t[3] / 1000
    ranges = [(to_seconds(t[:4]), to_seconds(t[4:])) for t in times]
    check('subtitles-monotonic-and-within-media', bool(ranges) and all(0 <= a < b <= duration for a, b in ranges) and all(ranges[i][1] <= ranges[i + 1][0] + .002 for i in range(len(ranges) - 1)), {'cues': len(ranges), 'lastEndSeconds': ranges[-1][1]})
    check('requested-closing-words', ' '.join(srt.splitlines()[-2:]).endswith('Test the repair.') and 'Keep the failure.' in srt, (HERE / 'transcript.txt').read_text().splitlines()[-1])
    end = HERE / 'validation-frames/last-second.jpg'
    subprocess.run([ffmpeg, '-y', '-v', 'error', '-ss', str(duration - .75), '-i', str(video), '-frames:v', '1', '-q:v', '2', str(end)], check=True)
    result = {'schemaVersion': 1, 'kind': 'local-demo-media-validation', 'completedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'video': str(video), 'videoSha256': actual_sha, 'videoBytes': video.stat().st_size, 'durationSeconds': duration, 'lastFrame': {'path': str(end.relative_to(REPO)), 'sha256': sha(end), 'timeSeconds': duration - .75}, 'checks': checks, 'passed': sum(x['status'] == 'pass' for x in checks), 'failed': sum(x['status'] != 'pass' for x in checks)}
    (HERE / 'video-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('video', 'durationSeconds', 'videoBytes', 'videoSha256', 'passed', 'failed')}))
    return int(result['failed'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
