"""Issue #32: the Kontrol screen shows each device's own preset when you switch device.

The client keeps one controlOption with ONE Type, the preset of the device in use, and
OptionControlSettingScreen.onControllerSelectorChanged sets Type 0 the first time you switch
device in a visit (later switches swap with _lastTypeChoice). The server remembers each
device's preset and sends both in controlOption: selectedIndex (keyboard) and index (gamepad),
names the screen's own code already has (2-byte multinames, so the patch keeps the handler's
55 bytes and nothing else moves). The patched switch:

    _option.selected = true            # tells the server the screen swapped the presets itself
    if (_option.Controller == 0) { _option.index = _option.Type; _option.Type = int(_option.selectedIndex) }
    else { _option.selectedIndex = _option.Type; _option.Type = int(_option.index) }

With an older server (no such fields) a switch gives Type 0, as before.

    python tools/control_presets.py [--game DIR]           patch the client (backup first)
    python tools/control_presets.py --remove [--game DIR]  put the original back
Close the game first.
"""
import argparse, os, shutil, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "re"))

BIG = os.path.join("data", "ui", "OptionControlSettingScreen.big")
ENTRY = "data/ui/OptionControlSettingScreen.gfx"
BACKUP = os.path.join(ROOT, "backup", "control_presets", "OptionControlSettingScreen.big")
# onControllerSelectorChanged from offset 34 (after "_option.Controller = selector index" and the
# first, initial INDEX_CHANGE) to 89 (setTypeSelectorTextAndImage and the rest), FO3 ID 32795
ORIGINAL = bytes.fromhex(
    "d0 66 db 01 24 ff 14 16 00 00"  # if (_lastTypeChoice == -1) {
    "d0 d0 66 4f 66 c3 01 68 db 01"  #   _lastTypeChoice = _option.Type
    "d0 66 4f 24 00 61 c3 01"        #   _option.Type = 0
    "10 17 00 00"                    # } else {
    "d0 66 db 01 82 d6 d0 d0 66 4f 66 c3 01 68 db 01 d0 66 4f d2 61 c3 01")  # swap with _lastTypeChoice }
PATCHED = bytes.fromhex(
    "d0 66 4f d5"                    # local1 = _option (the event is not used after this)
    "d1 26 61 f8 01"                 # local1.selected = true
    "d1 66 50 11 15 00 00"           # if (local1.Controller) goto pad
    "d1 d1 66 c3 01 61 df 01"        # keyboard: local1.index = local1.Type
    "d1 d1 66 bc 01 73 61 c3 01"     #   local1.Type = int(local1.selectedIndex)
    "10 12 00 00"                    #   goto end
    "d1 d1 66 c3 01 61 bc 01"        # pad: local1.selectedIndex = local1.Type
    "d1 d1 66 df 01 73 61 c3 01"     #   local1.Type = int(local1.index)
    "02")                            # end (nop)
assert len(ORIGINAL) == len(PATCHED) == 55


def patched_gfx(gfx):
    """The screen's .gfx (CFX: zlib after an 8-byte header) with the switch patched, or None if
    it is patched already. SystemExit for a client this patch does not know."""
    if gfx[:3] != b"CFX":
        raise SystemExit(f"{ENTRY}: not a compressed GFx file")
    body = zlib.decompress(gfx[8:])
    if body.count(PATCHED) == 1:
        return None
    if body.count(ORIGINAL) != 1:
        raise SystemExit(f"{ENTRY}: unknown client version (the code to patch is not there)")
    return gfx[:8] + zlib.compress(body.replace(ORIGINAL, PATCHED), 9)


def game_running():
    return "fifazf.exe" in os.popen('tasklist /FI "IMAGENAME eq fifazf.exe" /NH').read().lower()


def main():
    import bigdir
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game", default=os.environ.get("FO3_GAME", r"D:\FO3ID\32795"))
    ap.add_argument("--remove", action="store_true", help="put the original screen back")
    a = ap.parse_args()
    big = os.path.join(a.game, BIG)
    if game_running():
        raise SystemExit("close the game first (fifazf.exe is running)")
    if a.remove:
        if not os.path.isfile(BACKUP):
            raise SystemExit("nothing to remove (no backup/control_presets)")
        shutil.copyfile(BACKUP, big)
        print(f"original Kontrol screen back in {big}")
        return
    gfx = patched_gfx(bigdir.read(big, ENTRY))
    if gfx is None:
        print(f"already patched: {big}")
        return
    if not os.path.isfile(BACKUP):
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        shutil.copyfile(big, BACKUP)
    room = {n: size for n, off, size, usize in bigdir.entries(big)}[ENTRY]
    bigdir.patch(big, {ENTRY: gfx}, in_place=len(gfx) <= room)
    assert patched_gfx(bigdir.read(big, ENTRY)) is None
    print(f"patched {big} (backup in {BACKUP})")


if __name__ == "__main__":
    main()
