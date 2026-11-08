"""Which client the server serves, and where it listens. One place for the settings that differ
between the FO3 ID client this server was built on and the 3Sea client (build 655130, Thai).

FO3_CLIENT picks a profile ("3sea", the default, or "fo3id"); every value below can also be set
on its own by its environment variable:

    FO3_GAME            the client install (read only: the server never writes into it)
    FO3_ASSETS          the client's downloaded CDN copy (externalAssets/...); 3Sea has none
    FO3_LANGUAGE        the WebCache language key the client gets (kor eng chi vie tha ind jpn)
    FO3_REGION          the region in /info/server/config and the Blaze preAuth reply
    FO3_LAUNCH_REGION   `region <code>` on the game's command line (sg my th vn id)
    FO3_HTTP_BIND       the address the https server binds (127.0.0.2 with a hosts entry
                        "127.0.0.2 APSEODESK172" keeps 443 clear of another program on 127.0.0.1)
    FO3_MESSENGER_PORT  messenger.py's TCP port (its UDP push port is the next one)

The https port stays 443: fifazf.exe has it built in.
"""
import os

PROFILES = {
    "3sea": {"game": r"F:\FOServer\3Sea FIFA Online 3", "cache": None, "language": "tha", "region": "TH",
             "launch_region": "th"},
    "fo3id": {"game": r"D:\FO3ID\32795", "cache": "fo3id", "language": "ind", "region": "ID",
              "launch_region": "id"},
}

CLIENT = os.environ.get("FO3_CLIENT", "3sea").strip().lower()
if CLIENT not in PROFILES:
    raise SystemExit(f"FO3_CLIENT={CLIENT!r}: use one of {', '.join(PROFILES)}")
_P = PROFILES[CLIENT]


def _env(name, default):
    v = os.environ.get(name, "").strip()
    return v or default


GAME = _env("FO3_GAME", _P["game"])
ASSETS = _env("FO3_ASSETS", os.path.join(GAME, "_cache", "games", _P["cache"]) if _P["cache"] else "")
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


def summary():
    """One line for the server's start-up output."""
    return (f"client {CLIENT}: game {GAME!r}, language {LANGUAGE}, region {REGION}, "
            f"https bind {HTTP_BIND}, messenger :{MESSENGER_PORT}")
