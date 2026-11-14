"""Which client the server serves, and where it listens. One place for the settings that differ
between the FO3 ID client this server was built on and the 3Sea client (build 655130, Thai).

Nothing here is tied to one PC. The client folder and its kind are found in this order:

    1. environment variables (FO3_GAME, FO3_CLIENT, ...)
    2. fo3.local.env next to this file: this PC's own `NAME=value` lines (not in git), written by
       `python fo3conf.py set <client folder>` or by play.bat the first time it finds a client
    3. the client folder is searched for: the profiles' usual folders, then every drive two
       folders deep and the user's Desktop / Downloads / Games, for fifazf.exe
    4. the kind of client is read from the folder: a loose LANGUAGESTRING_THA.json is 3Sea,
       fo3id.version or a _cache\\games\\fo3id copy is FO3 ID

The settings (each one an environment variable or a fo3.local.env line):

    FO3_CLIENT          the profile: "3sea" or "fo3id" (found from the folder when not set)
    FO3_GAME            the client install (read only: the server never writes into it)
    FO3_ASSETS          the client's downloaded CDN copy (externalAssets/...); 3Sea has none
    FO3_LANGUAGE        the WebCache language key the client gets (kor eng chi vie tha ind jpn)
    FO3_REGION          the region in /info/server/config and the Blaze preAuth reply
    FO3_LAUNCH_REGION   `region <code>` on the game's command line (sg my th vn id)
    FO3_HTTP_BIND       the address the https server binds (127.0.0.2 with a hosts entry
                        "127.0.0.2 APSEODESK172" keeps 443 clear of another program on 127.0.0.1)
    FO3_MESSENGER_PORT  messenger.py's TCP port (its UDP push port is the next one)

The https port stays 443: fifazf.exe has it built in.

    python fo3conf.py                  what this PC uses, and every client found
    python fo3conf.py set <folder> [3sea|fo3id]   use that client on this PC (fo3.local.env)
    python fo3conf.py env              the resolved settings as NAME=value lines (play.bat)
"""
import json, os, string, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_FILE = os.path.join(HERE, "fo3.local.env")
FIFADB_SOURCE = os.path.join(HERE, "gamedata", "fifadb.source.json")  # written by extract_fifadb.py

PROFILES = {
    "3sea": {"game": r"F:\FOServer\3Sea FIFA Online 3", "cache": None, "language": "tha", "region": "TH",
             "launch_region": "th"},
    "fo3id": {"game": r"D:\FO3ID\32795", "cache": "fo3id", "language": "ind", "region": "ID",
              "launch_region": "id"},
}
EXE = "fifazf.exe"


def read_local(path=LOCAL_FILE):
    """fo3.local.env: `NAME=value` lines; blank lines and `#` comments are skipped."""
    out = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip().upper()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def write_local(values, path=LOCAL_FILE):
    """Merge `values` into fo3.local.env (a value of "" removes that line)."""
    cur = read_local(path)
    cur.update(values)
    cur = {k: v for k, v in cur.items() if v}
    with open(path, "w", encoding="utf-8") as f:
        f.write("# This PC's FO3 server settings (not in git). Environment variables win over these.\n")
        f.write("# Change the client with: python fo3conf.py set <client folder> [3sea|fo3id]\n")
        for k in sorted(cur):
            f.write(f"{k}={cur[k]}\n")


_LOCAL = read_local()


def _env(name, default=""):
    v = os.environ.get(name, "").strip() or _LOCAL.get(name, "").strip()
    return v or default


def is_client(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, EXE))


def detect_client(folder):
    """The profile a client folder belongs to, from what it ships."""
    if os.path.isfile(os.path.join(folder, "data", "ui", "external", "LANGUAGESTRING_THA.json")):
        return "3sea"
    if os.path.isfile(os.path.join(folder, "fo3id.version")) or os.path.isdir(
            os.path.join(folder, "_cache", "games", "fo3id")):
        return "fo3id"
    return "3sea"


def _drives():
    if os.name != "nt":
        return []
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.isdir(f"{d}:\\")]


def find_clients(prefer=""):
    """Every client folder found on this PC, the likeliest first (`prefer`'s usual folder first)."""
    order = [PROFILES[prefer]["game"]] if prefer in PROFILES else []
    order += [p["game"] for p in PROFILES.values()]
    home = os.path.expanduser("~")
    roots = _drives() + [os.path.join(home, d) for d in ("Desktop", "Downloads", "Games", "Documents")]
    skip = {"windows", "$recycle.bin", "system volume information", "programdata", "users", "perflogs"}
    for root in roots:
        try:
            level1 = [e.path for e in os.scandir(root) if e.is_dir() and e.name.lower() not in skip]
        except OSError:
            continue
        for d1 in level1:
            order.append(d1)
            try:
                order += [e.path for e in os.scandir(d1) if e.is_dir()]
            except OSError:
                pass
    seen, found = set(), []
    for d in order:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            if is_client(d):
                found.append(os.path.abspath(d))
    return found


_CLIENT_SET = _env("FO3_CLIENT").lower()
if _CLIENT_SET and _CLIENT_SET not in PROFILES:
    raise SystemExit(f"FO3_CLIENT={_CLIENT_SET!r}: use one of {', '.join(PROFILES)}")

_GAME_SET = _env("FO3_GAME")
if is_client(_GAME_SET):
    GAME, GAME_FROM = _GAME_SET, "set"
else:
    _found = find_clients(_CLIENT_SET)
    if _found:
        GAME, GAME_FROM = _found[0], "found"
    else:  # nothing here: keep the usual folder so the warnings name it
        GAME, GAME_FROM = _GAME_SET or PROFILES[_CLIENT_SET or "3sea"]["game"], "missing"
GAME_SET_MISSING = bool(_GAME_SET) and GAME_FROM != "set"  # FO3_GAME points at no client

CLIENT = _CLIENT_SET or (detect_client(GAME) if GAME_FROM != "missing" else "3sea")
_P = PROFILES[CLIENT]

ASSETS = _env("FO3_ASSETS", os.path.join(GAME, "_cache", "games", _P["cache"]) if _P["cache"] else "")
if ASSETS and not os.path.isdir(ASSETS):
    ASSETS = ""  # no CDN copy in this install: the game's placeholders, as on 3Sea
LANGUAGE = _env("FO3_LANGUAGE", _P["language"]).lower()
REGION = _env("FO3_REGION", _P["region"]).upper()
LAUNCH_REGION = _env("FO3_LAUNCH_REGION", _P["launch_region"]).lower()
HTTP_BIND = _env("FO3_HTTP_BIND", "0.0.0.0")
MESSENGER_HOST = "127.0.0.1"
MESSENGER_PORT = int(_env("FO3_MESSENGER_PORT", "28002"))
MESSENGER_PUSH_PORT = MESSENGER_PORT + 1
# fifadb tables the client reads for this region and language (TransferUtil, the card names)
PERM_TABLE = "perm" + REGION.lower()  # permth / permid / ...: licensed, transferable
NAMES_TABLE = "names" + LANGUAGE  # namestha / namesind / ...


def fifadb_source():
    try:
        with open(FIFADB_SOURCE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def setup_warnings():
    """Setup problems worth a line at start-up."""
    out = []
    if GAME_FROM == "missing":
        out.append(f"no client found (looked for {EXE}): run `python fo3conf.py set <client folder>`")
    elif GAME_SET_MISSING:
        out.append(f"FO3_GAME {_GAME_SET!r} has no {EXE}; using the client found at {GAME!r}")
    src = fifadb_source()
    if src.get("game") and os.path.normcase(os.path.abspath(src["game"])) != os.path.normcase(os.path.abspath(GAME)):
        out.append(f"gamedata/fifadb.sqlite was extracted from {src['game']!r}, not this client: "
                   f"run `python extract_fifadb.py` again")
    return out


def summary():
    """The start-up output: one line, then a line for each setup warning."""
    how = {"set": "", "found": " (found)", "missing": " (missing)"}[GAME_FROM]
    line = (f"client {CLIENT}{'' if _CLIENT_SET else ' (from the folder)'}: game {GAME!r}{how}, "
            f"language {LANGUAGE}, region {REGION}, https bind {HTTP_BIND}, messenger :{MESSENGER_PORT}")
    return "\n".join([line] + [f"WARNING: {w}" for w in setup_warnings()])


def resolved():
    """The settings the game and the launcher need, as fifalauncher.exe reads them."""
    return {"FO3_CLIENT": CLIENT, "FO3_GAME": GAME, "FO3_LAUNCH_REGION": LAUNCH_REGION}


def _main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "set":
        if len(argv) < 2:
            raise SystemExit("usage: python fo3conf.py set <client folder> [3sea|fo3id]")
        folder = os.path.abspath(argv[1])
        if not is_client(folder):
            raise SystemExit(f"{folder!r} has no {EXE}")
        kind = argv[2].lower() if len(argv) > 2 else ""
        if kind and kind not in PROFILES:
            raise SystemExit(f"client {kind!r}: use one of {', '.join(PROFILES)}")
        write_local({"FO3_GAME": folder, "FO3_CLIENT": kind})
        print(f"{LOCAL_FILE}: FO3_GAME={folder}, client {kind or detect_client(folder) + ' (from the folder)'}")
        return
    if cmd == "env":  # play.bat: `for /f` sets these; a client found the first time is kept
        if GAME_FROM == "found" and not _GAME_SET:
            write_local({"FO3_GAME": GAME})
        for k, v in resolved().items():
            print(f"{k}={v}")
        for w in setup_warnings():
            print(f"WARNING: {w}", file=sys.stderr)
        return
    print(summary())
    print(f"settings file: {LOCAL_FILE}{'' if os.path.isfile(LOCAL_FILE) else ' (none yet)'}")
    for d in find_clients(CLIENT):
        print(f"  client found: {d} ({detect_client(d)})")


if __name__ == "__main__":
    _main(sys.argv[1:])
