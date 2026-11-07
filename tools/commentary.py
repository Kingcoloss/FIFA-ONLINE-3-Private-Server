"""Issue #34: Vietnamese match commentary from an FO3 VN client.

The commentary is EA speech data in audiodata/speechdata/<language>/: <language>.xml (its
sample banks), COM_BANK and <LANGUAGE>_BANK*.sbr/.sbs (index and audio),
commentary_sentences.bin, commentary_pickups.xml, keyworddatabase.bin and the *.shst
histories. Which folder the game reads comes from data/loc/locale.big: this client (FO3 ID, the
SEA build) lists eng,us as AVAILABLE_COMMENTARY_LANG_1 and _2 in locale.ini and locale@id.ini,
and its own locale@vn.ini, the Vietnamese settings, lists vie,vn first. The game speaks its own
language (DEFAULT_LANGUAGE eng,us) while that one is in the list, so both entries name vie,vn
here (same length: patched in place); a match then reads speechdata\vie_vn (seen live: its
COM_BANK.sbs open, eng_us's not). So Vietnamese commentary takes the VN client's
audiodata/speechdata/vie_vn folder next to eng_us and these two lines.

    python tools/commentary.py "D:\\FO3 VN" [--game DIR]    copy vie_vn from the VN client and use it
    python tools/commentary.py --remove [--game DIR]        English commentary again (vie_vn stays)
Close the game first. The original locale.big is kept in backup/commentary.
"""
import argparse, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "re"))

BIG = os.path.join("data", "loc", "locale.big")
INIS = ("locale.ini", "locale@id.ini")  # the default settings and the ID region's (the launcher's)
SPEECH = os.path.join("audiodata", "speechdata")
LANG = "vie_vn"
PAIRS = tuple((b"AVAILABLE_COMMENTARY_LANG_%d = eng,us" % k, b"AVAILABLE_COMMENTARY_LANG_%d = vie,vn" % k)
              for k in (1, 2))
BACKUP = os.path.join(ROOT, "backup", "commentary", "locale.big")


def switched(ini):
    """The settings with only Vietnamese commentary, or None if they have it already.
    SystemExit for settings this tool does not know."""
    new = ini
    for eng, vie in PAIRS:
        if new.count(vie) != 1:
            if new.count(eng) != 1:
                raise SystemExit(f"locale.big: unknown client version (no {eng.decode()})")
            new = new.replace(eng, vie)
    return None if new == ini else new


def speech_folder(path):
    """The vie_vn speech folder of a VN client (or the folder itself), checked for its banks."""
    for d in (os.path.join(path, SPEECH, LANG), path):
        if os.path.isfile(os.path.join(d, LANG + ".xml")):
            if not any(f.lower().endswith(".sbs") for f in os.listdir(d)):
                raise SystemExit(f"{d}: no .sbs sound banks")
            return d
    there = os.path.join(path, SPEECH)
    found = sorted(os.listdir(there)) if os.path.isdir(there) else []
    raise SystemExit(f"no {SPEECH}\\{LANG} with {LANG}.xml in {path}"
                     + (f" (it has: {', '.join(found)})" if found else ""))


def install(game, source):
    """Copy the VN commentary into the client and switch its ID settings to it."""
    import bigdir
    src, big = speech_folder(source), os.path.join(game, BIG)
    dst = os.path.join(game, SPEECH, LANG)
    if os.path.normcase(os.path.abspath(src)) != os.path.normcase(os.path.abspath(dst)):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    new = {n: switched(bigdir.read(big, n)) for n in INIS}
    new = {n: v for n, v in new.items() if v is not None}
    if new:
        if not os.path.isfile(BACKUP):
            os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
            shutil.copyfile(big, BACKUP)
        bigdir.patch(big, new, in_place=True)  # same length: each entry keeps its place
        assert all(switched(bigdir.read(big, n)) is None for n in INIS)
    return dst


def remove(game):
    if not os.path.isfile(BACKUP):
        raise SystemExit("nothing to remove (no backup/commentary)")
    shutil.copyfile(BACKUP, os.path.join(game, BIG))


def main():
    from control_presets import game_running
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", nargs="?", help="the FO3 VN client folder (or its speechdata\\vie_vn)")
    ap.add_argument("--game", default=os.environ.get("FO3_GAME", r"D:\FO3ID\32795"))
    ap.add_argument("--remove", action="store_true", help="English commentary again")
    a = ap.parse_args()
    if game_running():
        raise SystemExit("close the game first (fifazf.exe is running)")
    if a.remove:
        remove(a.game)
        print(f"English commentary again ({os.path.join(a.game, BIG)} restored)")
    elif a.source:
        print(f"Vietnamese commentary from {install(a.game, a.source)}")
    else:
        ap.error("give the FO3 VN client folder, or --remove")


if __name__ == "__main__":
    main()
