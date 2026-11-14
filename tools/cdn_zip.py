"""Pack or unpack the FO3 ID CDN copy the server serves to 3Sea (gamedata/cdn) as cdn/fo3id-cdn.zip.

The 3Sea client ships no CDN copy (crests, faces, staff, balls, league logos, Shop art). The
FO3 ID client's _cache\\games\\fo3id\\externalAssets is the one the server was built on;
`python fo3conf.py assets <FO3 ID client>` copies it into gamedata/cdn, and this zip keeps it in
git so a PC without an FO3 ID client gets it too: prepare.py (play.bat) unpacks it when
gamedata/cdn is missing.

    python tools/cdn_zip.py pack      gamedata/cdn/externalAssets -> cdn/fo3id-cdn.zip
    python tools/cdn_zip.py unpack    cdn/fo3id-cdn.zip -> gamedata/cdn (files already there stay)
"""
import os, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(ROOT, "cdn", "fo3id-cdn.zip")
CDN = os.path.join(ROOT, "gamedata", "cdn")
STAMP = (2020, 1, 1, 0, 0, 0)  # fixed times: packing the same files gives the same zip


def pack(src=CDN, out=ZIP):
    base = os.path.join(src, "externalAssets")
    names = sorted(os.path.relpath(os.path.join(d, f), src).replace(os.sep, "/")
                   for d, _, fs in os.walk(base) for f in fs)
    if not names:
        raise SystemExit(f"nothing in {base}: run `python fo3conf.py assets <FO3 ID client>` first")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in names:
            info = zipfile.ZipInfo(n, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(src, *n.split("/")), "rb") as f:
                z.writestr(info, f.read())
    os.replace(tmp, out)
    return len(names)


def unpack(zpath=ZIP, dst=CDN):
    """Extract what gamedata/cdn lacks; returns the number of files written."""
    n = 0
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or not name.startswith("externalAssets/") or ".." in name.split("/"):
                continue
            f = os.path.join(dst, *name.split("/"))
            if os.path.isfile(f):
                continue
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with z.open(info) as a, open(f, "wb") as b:
                b.write(a.read())
            n += 1
    return n


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pack":
        print(f"{ZIP}: {pack()} files, {os.path.getsize(ZIP) / 1e6:.1f} MB")
    elif cmd == "unpack":
        print(f"{CDN}: {unpack()} files unpacked")
    else:
        raise SystemExit(__doc__)
