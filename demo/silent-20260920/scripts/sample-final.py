#!/usr/bin/env python3
"""Sample the encoded film itself for a separate visual review; no source re-render."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('video', type=Path)
parser.add_argument('--output', type=Path, default=ROOT / 'final-review')
parser.add_argument('--scenes', help='Optional comma-separated scene IDs')
args = parser.parse_args()
video = args.video.resolve()
film = json.loads((ROOT / 'prepared.json').read_text())
selected = set(args.scenes.split(',')) if args.scenes else None
args.output.mkdir(parents=True, exist_ok=True)
frames = []
for scene in film['scenes']:
    if selected and scene['id'] not in selected:
        continue
    for label, offset in [('opening', min(.5, scene['duration'] / 4)),
                          ('evidence', min(scene['duration'] - .1, scene['duration'] * .72))]:
        frame = scene['startFrame'] + round(offset * film['fps'])
        seconds = frame / film['fps']
        output = args.output / f'{frame:05d}-{scene["id"]}-{label}.jpg'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-ss', str(seconds), '-i', str(video), '-frames:v', '1',
                        '-q:v', '2', str(output)], check=True)
        frames.append({'scene': scene['id'], 'label': label, 'frame': frame,
                       'seconds': seconds, 'title': scene['title'],
                       'scope': scene['scope'], 'path': str(output.resolve()),
                       'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
manifest = {'video': str(video), 'videoSha256': hashlib.sha256(video.read_bytes()).hexdigest(),
            'method': 'Exact-time ffmpeg samples from the encoded final video; visual review is separate from technical validation.',
            'frames': frames}
(args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'sampledFrames': len(frames), 'manifest': str((args.output / 'manifest.json').resolve())}))
