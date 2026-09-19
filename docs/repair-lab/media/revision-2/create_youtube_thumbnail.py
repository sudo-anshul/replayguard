#!/usr/bin/env python3
"""Render a compact thumbnail from the existing brand and actual receipt data.

Uses the bundled Python/Pillow runtime, installed Avenir font, and native macOS
Quick Look to rasterize the existing SVG brand mark. No generated imagery/API.
"""
from pathlib import Path
import hashlib
import json
import subprocess
from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
FONT = "/System/Library/Fonts/Avenir Next.ttc"
S = 2
W, H = 1280, 720
PAPER, INK, MUTED = "#f4f7f9", "#182b35", "#586c77"
GREEN, ORANGE = "#176d50", "#994220"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size, weight=0):
    return ImageFont.truetype(FONT, round(size * S), index=weight)


def text(draw, xy, value, size, color=INK, weight=0):
    draw.text(tuple(round(v * S) for v in xy), value, font=font(size, weight), fill=color)


def rect(draw, bounds, fill, radius=0, outline=None, width=1):
    scaled = tuple(round(v * S) for v in bounds)
    if radius:
        draw.rounded_rectangle(scaled, radius=round(radius * S), fill=fill, outline=outline, width=round(width * S))
    else:
        draw.rectangle(scaled, fill=fill, outline=outline, width=round(width * S))


def receipt(draw, x, y, count, label, color, fill):
    width, height = 223, 293
    # A compact receipt illustration represents the actual report count.
    points = [(x,y),(x+width,y),(x+width,y+height-12)]
    for offset in range(width, -1, -12):
        points.append((x+offset,y+height if ((width-offset)//12)%2 else y+height-12))
    points += [(x,y+height-12),(x,y)]
    draw.polygon([(round(a*S),round(b*S)) for a,b in points], fill=fill)
    rect(draw,(x,y,x+width,y+7),color)
    text(draw,(x+23,y+29),label,27,color,2)
    text(draw,(x+22,y+65),str(count),126,color,0)
    text(draw,(x+25,y+217),"receipt" + ("s" if count!=1 else ""),28,color,5)


def main():
    evidence = {}
    for stage in ("broken", "repaired"):
        path = HERE / "execution" / stage / "report.json"
        report = json.loads(path.read_text())
        assert len(report["results"]) == 1 and report["cases"][0]["id"] == "crash-retry"
        receipts = report["results"][0]["receipts"]
        expected = report["cases"][0]["expectedOrders"][0]["order"]
        assert all(receipt["order"] == expected for receipt in receipts)
        evidence[stage] = {"count": len(receipts), "reportSha256": sha(path)}
    assert evidence["broken"]["count"] == 2 and evidence["repaired"]["count"] == 1
    logo = REPO / "web/mark.svg"
    subprocess.run(["qlmanage", "-t", "-s", "1024", "-o", str(HERE), str(logo)], check=True, stdout=subprocess.DEVNULL)
    image = Image.new("RGB", (W*S,H*S), PAPER)
    draw = ImageDraw.Draw(image)
    mark = Image.open(HERE / "mark.svg.png").convert("RGB")
    bounds = ImageChops.difference(mark, Image.new("RGB", mark.size, "white")).getbbox()
    mark = mark.crop(bounds).convert("RGBA").resize((48*S,48*S),Image.Resampling.LANCZOS)
    mask = Image.new("L", mark.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,48*S-1,48*S-1), radius=13*S, fill=255)
    mark.putalpha(mask)
    image.paste(mark,(64*S,55*S),mark)
    text(draw,(127,57),"ReplayGuard",33,INK,0)
    text(draw,(64,177),"One retry.",88,INK,0)
    text(draw,(64,284),"Two receipts.",88,INK,0)
    rect(draw,(68,399,630,406),ORANGE,radius=3)
    text(draw,(67,447),"Catch it. Test the repair.",31,MUTED,5)
    # Exactly two outcomes, drawn from the recorded broken/repaired reports.
    receipt(draw,724,188,evidence["broken"]["count"],"No key",ORANGE,"#f9e7da")
    receipt(draw,979,188,evidence["repaired"]["count"],"Repaired",GREEN,"#e3f1e9")
    text(draw,(735,513),"Same input. Same fault.",25,MUTED,5)
    draw.line((64*S,624*S,1216*S,624*S),fill="#d7e0e5",width=2*S)
    text(draw,(65,650),"SIMULATED FULFILLMENT",20,MUTED,2)
    text(draw,(778,650),"Actual local execution",22,GREEN,2)
    image = image.resize((W,H),Image.Resampling.LANCZOS)
    output = HERE / "youtube-thumbnail.png"
    image.save(output,optimize=True)
    manifest = {"kind":"youtube-thumbnail","width":W,"height":H,"outputSha256":sha(output),
                "brandAsset":"web/mark.svg","brandAssetSha256":sha(logo),"font":"Installed Avenir Next",
                "claim":"One retry. Two receipts.","visualization":"Actual local crash/retry receipt counts: broken 2, repaired 1",
                "evidence":evidence,"illustrationNotProductScreenshot":True,"externalGenerationUsed":False}
    (HERE / "youtube-thumbnail.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(output)
    print(f"{W}x{H}, {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
