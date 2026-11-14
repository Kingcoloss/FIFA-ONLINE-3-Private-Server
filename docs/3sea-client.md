# Running the server with the 3Sea client

The server was built against the Garena FO3 ID client (build 654420, region ID, Indonesian).
The 3Sea community client (build 655130, region TH, Thai) is the same game build
(`FO3_SEA_STREAM`, Blaze CVER 20200217), so most of the server applies as it is. The points
that differ are settings in `fo3conf.py`. Which client a PC has is found by itself (see
"Any client, any folder" below); these are the two profiles:

| | FO3 ID | 3Sea (default) | Setting |
|---|---|---|---|
| Client folder (searched first; any folder is found) | `D:\FO3ID\32795` | `F:\FOServer\3Sea FIFA Online 3` | `FO3_GAME` |
| Downloaded CDN copy (crests, faces, Shop art) | `_cache\games\fo3id` | none | `FO3_ASSETS` |
| Language sent to the client | `ind` | `tha` | `FO3_LANGUAGE` |
| UI strings | `externalAssets/language_ind.big` (cache) | loose `data/ui/external/LANGUAGESTRING_THA.json` | follows the language |
| Region in `/info/server/config` and Blaze | `ID` | `TH` | `FO3_REGION` |
| fifadb licensing / name tables | `permid`, `namesind` | `permth`, `namestha` | follow region and language |
| Game command line | `region id`, `PUBLISHING_REGION=ID` | `region th`, `PUBLISHING_REGION=TH` | `FO3_LAUNCH_REGION` |

## Any client, any folder

The PCs this runs on do not have the same client, so nothing is tied to one folder:

1. environment variables (`FO3_GAME`, `FO3_CLIENT`, ...) win;
2. then `fo3.local.env` in the repository folder (this PC's own `NAME=value` lines, not in
   git), written by `python fo3conf.py set "<client folder>" [3sea|fo3id]` or by `play.bat`
   the first time it finds a client;
3. else `fifazf.exe` is searched for: the two usual folders, every drive two folders deep, and
   the Desktop, Downloads, Games and Documents folders;
4. the profile comes from the folder: a loose `data/ui/external/LANGUAGESTRING_THA.json` is
   3Sea, `fo3id.version` or `_cache\games\fo3id` is FO3 ID. `FO3_CLIENT` overrides it.

`python fo3conf.py` shows what this PC uses and every client it found. `fifalauncher.exe` reads
the same settings, so one build works on every PC. `gamedata\fifadb.sqlite` remembers which
client it came from (`fifadb.source.json`); `play.bat` extracts it again when the client changes.

The server only reads the client folder. Nothing in this setup writes into it.

## Thai on the FO3 ID client

The FO3 ID client ships the UI strings of six languages in
`data/ui/localization/language.big` (CHI ENG IND KOR THA VIE), with `fonts_th.big` and
`tha.big` beside them, but its cache has only the Indonesian pack
(`externalAssets/language_ind.big`). `python fo3conf.py language tha` (this PC's
`fo3.local.env`) switches the game to Thai: the server then builds
`gamedata/language_tha.built.big` from the Thai strings, with the English base string for each
of the 608 keys only the newer Indonesian pack has (later items, balls, seasons). The region
stays ID (`permid`); card names come from `namestha`. Text the server writes itself (virtual
managers' chat, some screens) stays Indonesian. `python fo3conf.py language default` goes back.

## FO3 ID's pictures for 3Sea (`cdn/fo3id-cdn.zip`)

The game does not ship most of its pictures: club crests, player faces, staff, balls, league
logos, trophies, uniforms and Shop art came from Garena's CDN at run time, and each client kept
what it downloaded in `_cache\games\<publisher>\externalAssets`. The CDN is gone. The FO3 ID
client still has its copy (1,450 files, 37 MB, the one this server was built on); 3Sea ships
none, so without help its screens show placeholders.

So the server keeps that copy itself:

- `cdn/fo3id-cdn.zip` (in git, 39 MB) holds the FO3 ID client's `externalAssets` as it was.
- `play.bat` (`prepare.py`) unpacks it into `gamedata\cdn` (not in git) when the client has no
  copy of its own and `gamedata\cdn` is missing. No FO3 ID client is needed on the PC.
- The server (`http_config.py`, `asset_path`) answers each picture the client asks for at
  `https://APSEODESK172/cdn/externalAssets/...` from, in order: the server's own `assets/`,
  the pictures the admin page's Aset tab fetched from fifaaddict (`externalAssets/` in this
  repository, also where new fetches go), then `gamedata\cdn`. A picture in none of them is a
  404 and the game shows its placeholder.
- An FO3 ID client uses its own `_cache` instead (and the Aset tab saves into it, as before).
- `python fo3conf.py assets "<FO3 ID client>"` copies a client's cache into `gamedata\cdn`;
  `python tools/cdn_zip.py pack` then rebuilds the zip from it (same files give the same zip).
- 3Sea keeps its own Thai strings: the copy's `language_ind.big` is not used for it, and the
  server builds no language pack when the client has its loose
  `data/ui/external/LANGUAGESTRING_THA.json`.

The zip is EA's data out of the game client, like the fifaaddict pictures already in
`externalAssets/`; this repository is public, so pushing it publishes those files.

## Setup

1. Python 3 with `pip install cryptography`.
2. As administrator, the hosts entry `127.0.0.1 APSEODESK172`.
3. Run `play.bat`. Its first step, `prepare.py`, does the rest when it is missing: finds the
   client, extracts the player database from it (read only; 3Sea's `data_0.big` keeps
   `data/db2/fifadb.db.db2` at the same offset and size as the FO3 ID build, checked
   2026-11-08: 60,174 cards), makes `certs\server.pem` for `APSEODESK172` and builds
   `launcher\fifalauncher.exe` from `launcher\fifalauncher.cs` (kept in this repo's `launcher`
   folder, not in the game folder). It stops with what is missing, such as the hosts entry.

## Ports

| Port | What | Setting |
|---|---|---|
| 443 | https `APSEODESK172` (built into `fifazf.exe`, cannot move) | bind address `FO3_HTTP_BIND` |
| 28002, 28003 | messenger TCP, its UDP push port (the next one) | `FO3_MESSENGER_PORT` |
| 8088 | admin page | `FO3_ADMIN_PORT` (0 = off) |

When another program already holds 443 on 127.0.0.1, bind the server to another loopback
address: hosts entry `127.0.0.2 APSEODESK172` and `set FO3_HTTP_BIND=127.0.0.2` in `play.bat`.
This still fails if that program holds 443 on every address (`0.0.0.0`), as some Windows
services do; then that program has to stop while you play.

## Not known yet

These need the real client and are checked in Phase 0:

- whether 3Sea's `fifazf.exe` calls `APSEODESK172` like the FO3 ID one;
- whether the client takes its Thai strings from the loose JSON when the server has no
  `language_tha.big` to send;
- whether region `TH` is what the client expects in `/info/server/config`.

Known gaps: 3Sea ships no CDN cache, so crests, faces, staff pictures and league logos are the
game's placeholders until the admin page's Aset tab fetches them from fifaaddict.com into this
repository's `externalAssets` folder (the server serves them from there). Shop pictures stay missing. The virtual
managers' chat has no Thai lines yet.
