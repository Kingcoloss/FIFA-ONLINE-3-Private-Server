"""Fill in the player mini faces (or, with --crests, club crests) the client's cache lacks, from
fifaaddict.com. User: "update semua mini face yang belum ada ambil dari FIFAADDICT"; crests for
GitHub issue #3 ("team emblems display incorrectly": most crests are not in the cache, so the
client shows its default one).

The client shows faces from its cache (_cache/games/fo3id/externalAssets/players, served by
http_config /cdn/): p<spid>.png for a season face, else p<player id>.png. fifaaddict serves
the same 128x128 PNGs at fo3img/players/p<player id>.png (byte-identical to the cached ones;
it has no per-season PNGs), so this adds the missing p<player id>.png files. Order: my club's
players, faces the game already asked for, then every Market card, dearest first.
Crests are crests/large/s<teamid>.png (256x256) and crests/small/s<teamid>.png (128x128);
fifaaddict has both sizes (fo3img/crests/large/s<id>.png and fo3img/crests/s<id>.png). Order:
crests the game already asked for, then every club with a 2017 squad (the club picker's).
One request every --delay seconds; existing files are never touched; gamedata/fa_faces.json
(fa_crests.json) records what was added or failed so a rerun resumes, and --remove deletes only
the added files.

Usage: python -I tools/fa_faces.py [--crests] [--delay 0.5] [--limit N] [--remove]
"""
import argparse, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ARGS, sys.argv = sys.argv[1:], sys.argv[:1]  # http_config reads a port from argv at import
import http_config as hc

EXT = os.path.join(hc.ASSETS, "externalAssets")
FA = "https://fifaaddict.com/fo3img/"
MANIFESTS = {"faces": os.path.join(ROOT, "gamedata", "fa_faces.json"),
             "crests": os.path.join(ROOT, "gamedata", "fa_crests.json")}


def _asked(pattern):
    """Ids in the /cdn/externalAssets/<pattern> requests the server log holds, in order."""
    with open(hc.LOG, encoding="utf-8", errors="replace") as f:
        return [int(m.group(1)) for m in re.finditer(r"GET /cdn/externalAssets/" + pattern, f.read())]


def _rel(entry):
    """Manifest entry -> path under externalAssets (older face manifests hold bare player ids)."""
    return f"players/p{entry}.png" if str(entry).isdigit() else entry


def wanted_faces():
    """[(path under externalAssets, url)] of faces in download order (club, asked, Market by price)."""
    st = hc._state()
    club = [int(p["spid"]) % 1000000 for t in st["teams"].values() for p in t["players"]]
    asked = [p % 1000000 for p in _asked(r"players/p(\d+)\.png")]
    fa = hc.fa_prices()
    market = [s % 1000000 for s in sorted(fa, key=lambda s: -fa[s])]
    return [(f"players/p{pid}.png", f"{FA}players/p{pid}.png") for pid in dict.fromkeys(club + asked + market)]


def wanted_crests():
    """[(path under externalAssets, url)] of both crest sizes (asked first, then every club)."""
    clubs = [t for _, leagues in hc.club_index() for _, teams in leagues for t in teams]
    ids = dict.fromkeys(_asked(r"crests/(?:large|small)/s(\d+)\.png") + clubs)
    return [job for t in ids for job in ((f"crests/large/s{t}.png", f"{FA}crests/large/s{t}.png"),
                                         (f"crests/small/s{t}.png", f"{FA}crests/s{t}.png"))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--crests", action="store_true", help="club crests instead of player faces")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--remove", action="store_true", help="delete the files this tool added")
    a = ap.parse_args(ARGS)
    kind = "crests" if a.crests else "faces"
    manifest = MANIFESTS[kind]
    man = json.load(open(manifest)) if os.path.isfile(manifest) else {"added": [], "failed": {}}
    man = {"added": [_rel(e) for e in man["added"]], "failed": {_rel(k): v for k, v in man["failed"].items()}}
    if a.remove:
        for rel in man["added"]:
            f = os.path.join(EXT, rel)
            if os.path.isfile(f):
                os.remove(f)
        print(len(man["added"]), kind, "removed")
        if os.path.isfile(manifest):
            os.remove(manifest)
        return
    jobs = wanted_crests() if a.crests else wanted_faces()
    todo = [(rel, url) for rel, url in jobs if not os.path.isfile(os.path.join(EXT, rel)) and rel not in man["failed"]]
    if a.limit:
        todo = todo[:a.limit]
    print(len(todo), kind, "to fetch", flush=True)
    done = 0
    for i, (rel, url) in enumerate(todo):
        time.sleep(a.delay)
        req = urllib.request.Request(url, headers={"User-Agent": f"Mozilla/5.0 (FO3 private server {kind} sync)"})
        try:
            body = urllib.request.urlopen(req, timeout=60).read()
            if not body.startswith(b"\x89PNG"):
                raise ValueError("not a PNG")
        except Exception as e:
            man["failed"][rel] = str(getattr(e, "code", e))[:40]
        else:
            path = os.path.join(EXT, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(body)
            man["added"].append(rel)
            done += 1
        if i % 50 == 49 or i == len(todo) - 1:
            os.makedirs(os.path.dirname(manifest), exist_ok=True)
            with open(manifest, "w") as f:
                json.dump(man, f)
            print(f"{i + 1}/{len(todo)} fetched {done}, failed {len(man['failed'])}", flush=True)
    print("done:", done, "added,", len(man["failed"]), "failed in total")


if __name__ == "__main__":
    main()
