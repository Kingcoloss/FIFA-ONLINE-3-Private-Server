# Moving the server to another PC

Everything that is code is in git (branch `develop`). What is not in git stays out on purpose:
this repository is public, and these files are either extracted from the game client, a private
key, your own save, or this PC's own settings. `play.bat` rebuilds most of them by itself
(`prepare.py`); the rest is copied by hand.

The PCs do not need the same client. Any 3Sea or FO3 ID client in any folder works: it is found
and its kind is read from the folder (docs/3sea-client.md, "Any client, any folder").

| Not in git | Why | On the new PC |
|---|---|---|
| `fo3.local.env` | this PC's client folder (and any other `FO3_*` setting) | written by `play.bat` when it finds the client, or `python fo3conf.py set "<folder>"` |
| `gamedata/fifadb.sqlite`, `fifadb.source.json` | extracted from the client (EA data) | `play.bat` extracts it, and again when the client changes |
| `gamedata/formations.json`, `stadiums.json` | caches from the client | come back on first run |
| `gamedata/state.json` | your save: managers, clubs, EP, items | copy it over (step 4) |
| `gamedata/shop.json`, `economy.json`, `match_rewards.json`, `missions.json`, `daily_rewards.json`, `vm_chat.json`, `notice.png` | your admin page settings, if you saved any | copy them over (step 4) |
| `gamedata/fa_prices.json` | fifaaddict prices, if you fetched them | copy, or run `python tools/fa_sync.py` again |
| `gamedata/fa_crests.json`, `fa_faces.json`, `fa_staffs.json`, `fa_leagues.json` | the Aset tab's record of what it fetched; the pictures themselves are in git (`externalAssets/`) | copy them if you want the record; a new fetch skips the pictures already there |
| `certs/server.pem` | TLS private key | `play.bat` makes a new one |
| `launcher/fifalauncher.exe` | build output | `play.bat` builds it (again when its source changes) |
| `captures/` | logs and golden recordings of your sessions | copy if you want them for the .NET golden tests |

## Steps

1. Install Python 3.12 or newer with `pip install cryptography`, and the .NET 10 SDK (only for
   `play_dotnet.bat` and `dotnet test`).
2. Clone and check out the branch:

       git clone https://github.com/Kingcoloss/FIFA-ONLINE-3-Private-Server
       cd FIFA-ONLINE-3-Private-Server
       git checkout develop

3. Have a client on the PC (3Sea or FO3 ID, any folder) and add `127.0.0.1 APSEODESK172` to the
   hosts file as administrator. `python fo3conf.py` shows the client it finds; when it finds none,
   or the wrong one, `python fo3conf.py set "<client folder>"`.
4. Copy your save and settings from the old PC's `gamedata` folder into the new one (the files in
   the table above, not `fifadb.sqlite`). Without `state.json` the game starts with a new account.
5. `play.bat` (Python only) or `play_dotnet.bat` (the .NET host in front of Python). The first
   start extracts the player database, makes the certificate and builds the launcher, and stops
   with a list when something it cannot do is missing. `python run_tests.py` runs the five suites.

The game's own display settings live in `graphics.ini` in the client folder (`FULLSCREEN=0` is
windowed); the in-game Options > Visual screen changes them too.
