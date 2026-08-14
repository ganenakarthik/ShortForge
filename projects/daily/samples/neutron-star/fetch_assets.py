"""Download sample assets from Wikimedia Commons (license-clean) + transcode the
Crab Nebula timelapse to h264 mp4 for Remotion. No API keys required."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
UA = {"User-Agent": "OpenMontageSample/1.0 (research sample; attribution kept)"}


def api(params: dict) -> dict:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def thumb_url(title: str, width: int) -> str:
    data = api({"action": "query", "format": "json", "prop": "imageinfo",
                "iiprop": "url", "iiurlwidth": str(width), "titles": title})
    page = next(iter(data["query"]["pages"].values()))
    return page["imageinfo"][0]["thumburl"]


def original_url(title: str) -> str:
    data = api({"action": "query", "format": "json", "prop": "imageinfo",
                "iiprop": "url", "titles": title})
    page = next(iter(data["query"]["pages"].values()))
    return page["imageinfo"][0]["url"]


def download(url: str, dest: str) -> None:
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"cached {dest}")
        return
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                f.write(r.read())
            print(f"downloaded {os.path.basename(dest)} ({os.path.getsize(dest)} bytes)")
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 20 * (attempt + 1)
                print(f"rate-limited (429), retrying in {wait}s")
                time.sleep(wait)
            else:
                raise
        time.sleep(3)
    raise RuntimeError(f"gave up downloading {url}")


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)

    jobs = [
        ("spoon_full.jpg", thumb_url("File:SplashArt Teaspoon (8134896559).jpg", 1600)),
        ("pulsar_art.png", original_url("File:Artist's Impression of Pulsar Wind from a Neutron Star (2018-43-4232).png")),
        ("carina_nebula.jpg", thumb_url("File:Hubble captures spectacular \u201clandscape\u201d in the Carina Nebula (heic1007e).jpg", 1600)),
        ("manhattan_night.jpg", thumb_url("File:Lower Manhattan from Jersey City September 2020 panorama.jpg", 1600)),
        ("crab_timelapse.webm", original_url("File:Timelapse crab comp to blue.webm")),
    ]
    for name, url in jobs:
        download(url, os.path.join(ASSETS, name))
        time.sleep(6)

    webm = os.path.join(ASSETS, "crab_timelapse.webm")
    mp4 = os.path.join(ASSETS, "crab_timelapse.mp4")
    if not os.path.exists(mp4) or os.path.getsize(mp4) < 1000:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", webm, "-c:v", "libx264", "-crf", "20",
             "-preset", "medium", "-pix_fmt", "yuv420p", "-an", mp4],
            capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print("TRANSCODE_FAIL", r.stderr[-400:])
            sys.exit(1)
        print("transcoded crab_timelapse.mp4")

    for f in sorted(os.listdir(ASSETS)):
        p = os.path.join(ASSETS, f)
        print(f, os.path.getsize(p))


if __name__ == "__main__":
    main()