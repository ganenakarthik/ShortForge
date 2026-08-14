"""Search Wikimedia Commons for sample assets. Writes results to JSON (no stdout)."""
import json
import sys
import urllib.parse
import urllib.request

QUERIES = {
    "crab_nebula": "Crab Nebula Hubble telescope",
    "sn1987a": "Supernova 1987A rings Hubble",
    "pulsar_art": "pulsar neutron star artist impression NASA",
    "spoon": "teaspoon spoon macro",
    "city_night": "city skyline night aerial lights",
    "carina_nebula": "Carina Nebula Hubble",
    "neutron_star_art": "neutron star illustration NASA",
    "crab_video": "Crab Nebula timelapse filetype:video",
}


def search(query: str) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",
        "srlimit": "8",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "OpenMontageSample/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    out = []
    for hit in data.get("query", {}).get("search", []):
        out.append({
            "title": hit.get("title"),
            "size": hit.get("size"),
            "width": hit.get("width"),
            "height": hit.get("height"),
            "mime": hit.get("mime"),
        })
    return out


def main() -> None:
    results = {}
    for key, q in QUERIES.items():
        try:
            results[key] = search(q)
        except Exception as e:
            results[key] = [{"error": str(e)}]
    out_path = sys.argv[1] if len(sys.argv) > 1 else "search_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
