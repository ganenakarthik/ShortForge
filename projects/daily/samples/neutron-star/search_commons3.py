"""Round 3: spoon search + license checks for finalists. Writes JSON."""
import json
import sys
import urllib.parse
import urllib.request

QUERIES = {"spoon": "teaspoon", "spoon_cutlery": "spoon silverware cutlery closeup"}

INFO_TITLES = [
    "File:SplashArt Teaspoon (8134896559).jpg",
    "File:New York City at night HDR.jpg",
    "File:Manhattan from Weehawken, NJ.jpg",
    "File:Lower Manhattan from Jersey City September 2020 panorama.jpg",
    "File:Supernova 1987A (opo9017a).jpg",
    "File:Hubble captures spectacular \u201clandscape\u201d in the Carina Nebula (heic1007e).jpg",
]


def api(params: dict) -> dict:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "OpenMontageSample/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def search(query: str) -> list[dict]:
    data = api({"action": "query", "format": "json", "list": "search",
                "srsearch": query, "srnamespace": "6", "srlimit": "10"})
    return [{"title": h.get("title"), "size": h.get("size")}
            for h in data.get("query", {}).get("search", [])]


def info(titles: list[str]) -> list[dict]:
    data = api({"action": "query", "format": "json", "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "titles": "|".join(titles)})
    out = []
    for p in data.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {})
        out.append({
            "title": p.get("title"),
            "url": ii.get("url"),
            "width": ii.get("width"),
            "height": ii.get("height"),
            "mime": ii.get("mime"),
            "size": ii.get("size"),
            "license": (em.get("LicenseShortName") or {}).get("value"),
        })
    return out


def main() -> None:
    results = {}
    for key, q in QUERIES.items():
        try:
            results[key] = search(q)
        except Exception as e:
            results[key] = [{"error": str(e)}]
    try:
        results["finalists_info"] = info(INFO_TITLES)
    except Exception as e:
        results["finalists_info"] = [{"error": str(e)}]
    with open(sys.argv[1] if len(sys.argv) > 1 else "search3_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
