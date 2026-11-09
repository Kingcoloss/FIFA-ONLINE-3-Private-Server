# Moving the server to another PC

Everything that is code is in git (branch `claude/project-thread-hp2use`). What is not in git
stays out on purpose: this repository is public, and these files are either extracted from the
game client, a private key, or your own save. They are rebuilt or copied by hand.

| Not in git | Why | On the new PC |
|---|---|---|
| `gamedata/fifadb.sqlite`, `formations.json`, `stadiums.json` | extracted from the client (EA data) | rebuilt from the client (step 3); the two caches come back on first run |
| `gamedata/state.json` | your save: managers, clubs, EP, items | copy it over (step 6) |
| `gamedata/shop.json`, `economy.json`, `match_rewards.json`, `missions.json`, `daily_rewards.json`, `vm_chat.json`, `notice.png` | your admin page settings, if you saved any | copy them over (step 6) |
| `gamedata/fa_prices.json` | fifaaddict prices, if you fetched them | copy, or run `python tools/fa_sync.py` again |
| `certs/server.pem` | TLS private key | make a new one (step 4) |
| `launcher/fifalauncher.exe` | build output | build again (step 5) |
| `captures/` | logs and golden recordings of your sessions | copy if you want them for the .NET golden tests |

## Steps

1. Install Python 3.12 or newer with `pip install cryptography`, and the .NET 10 SDK (only for
   `play_dotnet.bat` and `dotnet test`).
2. Clone and check out the branch:

       git clone https://github.com/Kingcoloss/FIFA-ONLINE-3-Private-Server
       cd FIFA-ONLINE-3-Private-Server
       git checkout claude/project-thread-hp2use

3. Copy or install the 3Sea client on the new PC. If its folder is not
   `F:\FOServer\3Sea FIFA Online 3`, set `FO3_GAME` to it (in `play.bat` or as a user environment
   variable). Then extract the player database: `python extract_fifadb.py "<client folder>"`
   (60,174 cards for 3Sea build 655130).
4. TLS certificate for `APSEODESK172`, as in the README:

       openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=APSEODESK172" -addext "subjectAltName=DNS:APSEODESK172" -keyout key.pem -out cert.pem
       python -c "open('certs/server.pem','w').write(open('cert.pem').read()+open('key.pem').read())"

5. Build the launcher once (the build line is at the top of `launcher/fifalauncher.cs`) and add
   `127.0.0.1 APSEODESK172` to the hosts file as admin.
6. Copy your save and settings from the old PC's `gamedata` folder into the new one (the files in
   the table above, not `fifadb.sqlite`). Without `state.json` the game starts with a new account.
7. `python run_tests.py` should pass all five suites. Then `play.bat` (Python only) or
   `play_dotnet.bat` (the .NET host in front of Python).

The game's own display settings live in `graphics.ini` in the client folder (`FULLSCREEN=0` is
windowed); the in-game Options > Visual screen changes them too.
