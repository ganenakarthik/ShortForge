"""Round 2: search more candidates + fetch imageinfo for chosen files. Writes JSON."""
import json
import sys
import urllib.parse
import urllib.request

QUERIES = {
    "spoon_macro": "spoon macro photography",
    "spoon_white": "teaspoon white background",
    "neutron_city": "neutron star New York size comparison",
    "city_skyline": "New York City skyline night",
    "supernova_jpg": "supernova 1987A jpg",
    "pulsar_video": "pulsar neutron star filetype:video",
}

INFO_TITLES = [
    "File:Timelapse crab comp to blue.webm",
    "File:Crab Nebula- The Crab in Action & The Case of The Dog That Did Not Bark (2011-crab).webm",
    "File:Artist's Impression of Pulsar Wind from a Neutron Star (2018-43-4232).png",
    "File:Hubble Captures Spectacular \"Landscape\" in the Carina Nebula (heic1007e).jpg",
    "File:Hubble Optical Images of Supernova 1987A (2005-sn87a-more-5 - sn87a opt1).jpg",
    "File:Hubble and Webb\u2019s views of the Crab Nebula (weic2326c).jpg",
    "File:Atlanta City Night Lights And Traffic - December 2015 (42348114472).jpg",
    "File:Illustration of relative sizes of Grand Canyon, neutron star and quark star (2002-0211-more-4).jpg",
]


def api(params: dict) -> dict:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "OpenMontageSample/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def search(query: str) -> list[dict]:
    data = api({"action": "query", "format": "json", "list": "search",
                "srsearch": query, "srnamespace": "6", "srlimit": "8"})
    return [{"title": h.get("title"), "size": h.get("size"),
             "width": h.get("width"), "height": h.get("height"), "mime": h.get("mime")}
            for h in data.get("query", {}).get("search", [])]


def info(titles: list[str]) -> list[dict]:
    data = api({"action": "query", "format": "json", "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "titles": "|".join(titles)})
    out = []
    for p in data.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {})
        license_ = (em.get("LicenseShortName", {}) or {}).get("value", "?")
        artist = (em.get("Artist", {}) or {}).get("value", "?")
        out.append({
            "title": p.get("title"),
            "url": ii.get("url"),
            "width": ii.get("width"),
            "height": ii.get("height"),
            "mime": ii.get("mime"),
            "size": ii.get("size"),
            "duration_s": (em.get("Duration") or {}).get("value"),
            "license": license_,
            "artist": artist[:120] if artist else "?",
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
        results["chosen_info"] = info(INFO_TITLES)
    except Exception as e:
        results["chosen_info"] = [{"error": str(e)}]
    out_path = sys.argv[1] if len(sys.argv) > 1 else "search2_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
