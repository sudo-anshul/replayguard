#!/usr/bin/env python3
"""Render captured product UI and actual subprocess results using local tools only.

Requires existing Pillow, macOS say, ffmpeg and ffprobe. No installs or network.
Native speech chunks give the accompanying SRT exact measured sentence timings.
This is an edited narrated evidence walkthrough, not continuous screen footage.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORKSPACE = REPO.parents[1]
WORK = WORKSPACE / 'work/repair-demo-render'
CAPTURES = WORK / 'source-captures'
OUTPUT = WORKSPACE / 'outputs/replayguard-repair-demo.mp4'
FFMPEG = shutil.which('ffmpeg')
FFPROBE = shutil.which('ffprobe')
VOICE = 'Samantha'
RATE = 148
FPS = 24
SIZE = (1920, 1080)
BG, INK, MUTED, ACCENT = '#102a32', '#f1f6f4', '#b4c8cc', '#d7f47b'
GREEN, ORANGE = '#74d9b6', '#ffba8a'
FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    result = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f'Command failed: {args!r}\n{result.stderr.decode(errors="replace")}')
    return result


def probe(path):
    return json.loads(run([FFPROBE, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path]).stdout)


def font(size, bold=False, mono=False):
    return ImageFont.truetype(MONO if mono else BOLD if bold else FONT, size)


def text(draw, at, value, size, fill=INK, bold=False, mono=False, spacing=10):
    draw.multiline_text(at, value, font=font(size, bold, mono), fill=fill, spacing=spacing)


def wrapped(draw, at, value, size, width, **kwargs):
    lines = []
    for paragraph in value.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = f'{line} {word}'.strip()
            if draw.textlength(candidate, font=font(size, kwargs.get('bold', False), kwargs.get('mono', False))) > width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    text(draw, at, '\n'.join(lines), size, **kwargs)
    return len(lines) * (size + kwargs.get('spacing', 10))


def base(spec, index, total):
    canvas = Image.new('RGB', SIZE, BG)
    draw = ImageDraw.Draw(canvas)
    text(draw, (64, 30), 'REPLAYGUARD', 21, ACCENT, bold=True)
    text(draw, (285, 30), spec['label'], 19, MUTED)
    text(draw, (1770, 30), f'{index + 1:02d}/{total:02d}', 19, MUTED, mono=True)
    text(draw, (64, 77), spec['title'], 40, bold=True)
    draw.line((64, 995, 1856, 995), fill='#385159', width=1)
    wrapped(draw, (64, 1020), spec['caption'], 23, 1792, fill=MUTED)
    return canvas


def screenshot_frame(spec, index, total):
    canvas = base(spec, index, total)
    original = Image.open(CAPTURES / spec['image']).convert('RGB')
    crop = tuple(spec['crop'])
    assert 0 <= crop[0] < crop[2] <= original.width and 0 <= crop[1] < crop[3] <= original.height
    cropped = original.crop(crop)
    picture = ImageOps.contain(cropped, (1792, 810), Image.Resampling.LANCZOS)
    canvas.paste(picture, ((1920 - picture.width) // 2, 155 + (810 - picture.height) // 2))
    return canvas, {'screenshot': str((HERE / spec['image']).relative_to(REPO)), 'screenshotSha256': sha256(CAPTURES / spec['image']), 'crop': list(crop)}


def cli_frame(spec, index, total):
    canvas = base(spec, index, total)
    draw = ImageDraw.Draw(canvas)
    execution = HERE / 'execution/final'
    manifest = json.loads((execution / 'manifest.json').read_text())
    item = next(x for x in manifest['commands'] if x['label'] == spec['command'])
    color = GREEN if item['status'] == 'pass' else ORANGE
    draw.rounded_rectangle((64, 167, 1856, 950), radius=16, fill='#193740', outline='#36545c', width=2)
    text(draw, (104, 202), 'RECORDED INVOCATION', 21, MUTED, bold=True)
    # Display exact argv, wrapped for readability. No invented prompt or typing.
    wrapped(draw, (104, 241), ' '.join(item['argv']), 23, 1705, mono=True, spacing=10)
    draw.line((104, 371, 1816, 371), fill='#3d5960', width=1)
    text(draw, (104, 403), 'ACTUAL STANDARD OUTPUT', 21, MUTED, bold=True)
    stdout = (execution / item['stdout']).read_text().rstrip()
    text(draw, (104, 445), stdout, 29, color, mono=True)
    draw.line((104, 505, 1816, 505), fill='#3d5960', width=1)
    order = item['observedCases'][0]['orders'][0]
    text(draw, (104, 542), 'PARSED FROM THE GENERATED REPORT', 21, MUTED, bold=True)
    text(draw, (104, 592), str(order['observedReceipts']), 96, color, bold=True)
    text(draw, (190, 616), f"receipt{'s' if order['observedReceipts'] != 1 else ''} for {order['orderId']}", 36)
    text(draw, (104, 706), f"Expected receipts: {order['expectedReceipts']}", 26, MUTED)
    text(draw, (1035, 604), f"Process exit  {item['exitCode']}", 38, color, mono=True)
    text(draw, (1035, 669), f"Report status  {item['status']}", 27, color, mono=True)
    draw.line((104, 771, 1816, 771), fill='#3d5960', width=1)
    text(draw, (104, 802), 'ACTUALLY EXECUTED ADAPTER · SHA-256', 20, MUTED, bold=True)
    text(draw, (104, 843), item['sourceSha256']['adapter.py'], 25, mono=True)
    text(draw, (104, 906), item['startedAt'] + ' · local simulated fulfillment', 19, MUTED, mono=True)
    return canvas, {'executionManifest': str((execution / 'manifest.json').relative_to(REPO)), 'executionManifestSha256': sha256(execution / 'manifest.json'), 'actualCommand': item}


def transfer_frame(spec, index, total):
    canvas = base(spec, index, total)
    draw = ImageDraw.Draw(canvas)
    folder = REPO / 'docs/repair-lab/transfer-results/final-numeric-runtime'
    data = json.loads((folder / 'summary.json').read_text())
    refs = ['reference', 'no-business-key', 'sku-only-key']
    titles = ['Business reference', 'No business key', 'SKU-only key']
    results = []
    for ref in refs:
        report = json.loads((folder / (ref + '.json')).read_text())
        assert 'results' in report
        results.append(report['results'])
    names = ['Response loss', 'Interleaved orders', 'Distinct references', 'Quantity conflict', 'Shipping conflict after crash']
    xcols = [750, 1105, 1470]
    draw.rounded_rectangle((64, 172, 1856, 872), radius=16, fill='#f3f7f8')
    text(draw, (100, 214), 'FROZEN CASE', 24, '#506570', bold=True)
    for x, title in zip(xcols, titles):
        text(draw, (x, 214), title, 24, '#19313c', bold=True)
    for row, name in enumerate(names):
        y = 292 + row * 94
        draw.line((100, y - 22, 1812, y - 22), fill='#cedbe1', width=1)
        text(draw, (100, y), name, 31, '#19313c', bold=True)
        for col, reports in enumerate(results):
            status = reports[row]['status']
            text(draw, (xcols[col], y), status.upper(), 27, '#166d54' if status == 'pass' else '#a7441d', bold=True)
    text(draw, (100, 812), 'Source: final-numeric-runtime reports · frozen inputs and original source hashes preserved', 21, '#506570')
    text(draw, (64, 916), f"{data['passed']} / {data['passed'] + data['failed']} transfer checks passed", 29, ACCENT, bold=True)
    text(draw, (765, 923), 'Integrity + execution + outcomes; five application scenarios.', 24, MUTED)
    return canvas, {'summary': str((folder / 'summary.json').relative_to(REPO)), 'summarySha256': sha256(folder / 'summary.json'), 'reports': {name: sha256(folder / (name + '.json')) for name in refs}}


def speech(spec, index):
    slot = WORK / f'{index + 1:02d}-{spec["id"]}'
    slot.mkdir(parents=True, exist_ok=True)
    sentences = []
    cursor = 0.0
    for num, value in enumerate(spec['sentences']):
        txt = slot / f'sentence-{num + 1:02d}.txt'
        aiff = slot / f'sentence-{num + 1:02d}.aiff'
        txt.write_text(value, encoding='utf-8')
        args = ['/usr/bin/say', '-v', VOICE, '-r', str(RATE), '-f', txt, '-o', aiff]
        run(args)
        seconds = float(probe(aiff)['format']['duration'])
        sentences.append({'text': value, 'audio': str(aiff), 'startSeconds': cursor, 'durationSeconds': seconds, 'speechArgs': list(map(str, args))})
        cursor += seconds
    concat = slot / 'audio-concat.txt'
    concat.write_text(''.join("file '" + s['audio'].replace("'", "'\\''") + "'\n" for s in sentences))
    audio = slot / 'narration.wav'
    run([FFMPEG, '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', concat, '-c:a', 'pcm_s16le', audio])
    duration = math.ceil(max(spec['duration'], cursor + 0.4) * FPS) / FPS
    return {'index': index, 'slot': str(slot), 'sentences': sentences, 'audio': str(audio), 'speechSeconds': cursor, 'durationSeconds': duration}


def render_scene(item):
    slot = Path(item['slot'])
    clip = slot / 'scene.mp4'
    args = [FFMPEG, '-y', '-v', 'error', '-loop', '1', '-framerate', FPS, '-i', item['frame'], '-i', item['audio'], '-t', item['durationSeconds'], '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-tune', 'stillimage', '-pix_fmt', 'yuv420p', '-vf', 'setsar=1', '-af', 'apad', '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-movflags', '+faststart', '-threads', '2', clip]
    run(args)
    return {**item, 'clip': str(clip), 'renderArgs': list(map(str, args))}


def srt_time(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames-only', action='store_true')
    args = parser.parse_args()
    assert FFMPEG and FFPROBE and Path('/usr/bin/say').is_file()
    assert not OUTPUT.exists(), 'Refusing to overwrite a demo; move only this renderer\'s own output for an intentional revision.'
    before = {p.name: sha256(p) for p in OUTPUT.parent.glob('*.mp4')}
    WORK.mkdir(parents=True, exist_ok=True)
    specs = json.loads((HERE / 'narration.json').read_text())
    capture_manifest_bytes = (HERE / 'capture-manifest.json').read_bytes()
    captures = json.loads(capture_manifest_bytes)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    (CAPTURES / 'capture-manifest.json').write_bytes(capture_manifest_bytes)
    for capture in captures['captures']:
        capture_bytes = (HERE / capture['file']).read_bytes()
        assert hashlib.sha256(capture_bytes).hexdigest() == capture['sha256'], capture['file']
        (CAPTURES / capture['file']).write_bytes(capture_bytes)
    prepared = []
    for i, spec in enumerate(specs):
        slot = WORK / f'{i + 1:02d}-{spec["id"]}'
        slot.mkdir(parents=True, exist_ok=True)
        builder = screenshot_frame if spec['kind'] == 'screenshot' else cli_frame if spec['kind'] == 'cli' else transfer_frame
        frame, provenance = builder(spec, i, len(specs))
        frame_path = slot / 'frame.png'
        frame.save(frame_path)
        prepared.append({**spec, 'frame': str(frame_path), 'provenance': provenance})
    contact = Image.new('RGB', (1920, 360 * math.ceil(len(specs) / 3)), '#071e25')
    for i, item in enumerate(prepared):
        thumb = Image.open(item['frame']).resize((640, 360), Image.Resampling.LANCZOS)
        contact.paste(thumb, ((i % 3) * 640, (i // 3) * 360))
    contact.save(HERE / 'contact-sheet.jpg', quality=92)
    if args.frames_only:
        print(json.dumps({'frames': len(prepared), 'contactSheet': str(HERE / 'contact-sheet.jpg')}))
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        speech_items = list(pool.map(lambda pair: speech(pair[1], pair[0]), enumerate(specs)))
    total = sum(x['durationSeconds'] for x in speech_items)
    assert total <= 170, f'Actual narration needs {total:.2f}s; shorten prose before rendering.'
    for i in range(len(prepared)):
        prepared[i].update(speech_items[i])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        scenes = list(pool.map(render_scene, prepared))
    concat = WORK / 'video-concat.txt'
    concat.write_text(''.join("file '" + s['clip'].replace("'", "'\\''") + "'\n" for s in scenes))
    concat_args = [FFMPEG, '-v', 'error', '-f', 'concat', '-safe', '0', '-i', concat, '-c', 'copy', '-movflags', '+faststart', OUTPUT]
    run(concat_args)
    metadata = probe(OUTPUT)
    duration = float(metadata['format']['duration'])
    assert duration <= 170
    subtitles, transcript, evidence_frames = [], [], []
    cursor, serial = 0.0, 1
    validation = HERE / 'validation-frames'
    validation.mkdir(exist_ok=True)
    for item in scenes:
        item['startSeconds'] = cursor
        transcript.append(f'{cursor:.2f}s — {item["title"]}\n' + ' '.join(item['sentences'][i]['text'] for i in range(len(item['sentences']))))
        for sentence in item['sentences']:
            start = cursor + sentence['startSeconds']
            end = start + sentence['durationSeconds']
            subtitles.append(f'{serial}\n{srt_time(start)} --> {srt_time(end)}\n' + '\n'.join(textwrap.wrap(sentence['text'], 72)))
            serial += 1
        frame = validation / f'{item["index"] + 1:02d}-{item["id"]}.jpg'
        point = round(cursor + min(2, item['durationSeconds'] / 2), 3)
        run([FFMPEG, '-y', '-v', 'error', '-ss', point, '-i', OUTPUT, '-frames:v', 1, '-q:v', 2, frame])
        evidence_frames.append({'path': str(frame.relative_to(REPO)), 'sha256': sha256(frame), 'timeSeconds': point})
        cursor += item['durationSeconds']
    (HERE / 'transcript.txt').write_text('\n\n'.join(transcript) + '\n', encoding='utf-8')
    (HERE / 'narration.srt').write_text('\n\n'.join(subtitles) + '\n', encoding='utf-8')
    decode_args = [FFMPEG, '-v', 'error', '-i', OUTPUT, '-f', 'null', '-']
    run(decode_args)
    after = {name: sha256(OUTPUT.parent / name) for name in before}
    assert before == after, 'Historical videos changed'
    manifest = {
        'schemaVersion': 1, 'kind': 'narrated-captured-ui-and-recorded-cli-walkthrough',
        'completedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'output': str(OUTPUT), 'outputSha256': sha256(OUTPUT), 'durationSeconds': duration,
        'video': {'width': 1920, 'height': 1080, 'fps': FPS, 'codec': 'h264', 'pixelFormat': 'yuv420p'},
        'audio': {'voice': VOICE, 'wordsPerMinute': RATE, 'codec': 'aac', 'music': False},
        'limitations': ['Edited actual UI captures, not continuous interaction footage.', 'CLI panels reproduce actual recorded argv, stdout, process exits and parsed report data; no simulated typing.', 'AWS evidence is retained from September 18 UTC; this video performs no new AWS execution.', 'Local simulated receipts and trusted-code restrictions do not guarantee an external shipment or payment.', 'Independent transfer was authored by AI agents on synthetic data, not human/customer validation.'],
        'captureManifestSha256': hashlib.sha256(capture_manifest_bytes).hexdigest(),
        'captureSource': captures,
        'narrationSourceSha256': sha256(HERE / 'narration.json'),
        'narrationTranscriptSha256': sha256(HERE / 'transcript.txt'),
        'subtitlesSha256': sha256(HERE / 'narration.srt'),
        'rendererSha256': sha256(__file__), 'historicalVideosBefore': before, 'historicalVideosAfter': after,
        'scenes': scenes, 'probe': metadata, 'concatArgs': list(map(str, concat_args)),
        'fullDecode': {'argv': list(map(str, decode_args)), 'exitCode': 0},
        'validationFrames': evidence_frames,
    }
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(OUTPUT), 'durationSeconds': duration, 'sha256': manifest['outputSha256'], 'fullDecode': 'passed', 'historicalVideosUnchanged': True}))


if __name__ == '__main__':
    main()
