# Running the server with the 3Sea client

The server was built against the Garena FO3 ID client (build 654420, region ID, Indonesian).
The 3Sea community client (build 655130, region TH, Thai) is the same game build
(`FO3_SEA_STREAM`, Blaze CVER 20200217), so most of the server applies as it is. The points
that differ are settings in `fo3conf.py`, and 3Sea is the default:

| | FO3 ID | 3Sea (default) | Setting |
|---|---|---|---|
| Client folder | `D:\FO3ID\32795` | `F:\FOServer\3Sea FIFA Online 3` | `FO3_GAME` |
| Downloaded CDN copy (crests, faces, Shop art) | `_cache\games\fo3id` | none | `FO3_ASSETS` |
| Language sent to the client | `ind` | `tha` | `FO3_LANGUAGE` |
| UI strings | `externalAssets/language_ind.big` (cache) | loose `data/ui/external/LANGUAGESTRING_THA.json` | follows the language |
| Region in `/info/server/config` and Blaze | `ID` | `TH` | `FO3_REGION` |
| fifadb licensing / name tables | `permid`, `namesind` | `permth`, `namestha` | follow region and language |
| Game command line | `region id`, `PUBLISHING_REGION=ID` | `region th`, `PUBLISHING_REGION=TH` | `FO3_LAUNCH_REGION` |

`FO3_CLIENT=fo3id` switches every default back to the FO3 ID client.

The server only reads the client folder. Nothing in this setup writes into it.

## Setup

1. Python 3 with `pip install cryptography`.
2. Extract the player database from the client (read only):
   `python extract_fifadb.py "F:\FOServer\3Sea FIFA Online 3"`.
   3Sea's `data_0.big` keeps `data/db2/fifadb.db.db2` at the same offset and size as the FO3 ID
   build (checked 2026-11-08: 60,174 cards).
3. The rest is as in the README: `certs\server.pem` for `APSEODESK172`, the hosts entry
   `127.0.0.1 APSEODESK172`, and `launcher\fifalauncher.exe` built from
   `launcher\fifalauncher.cs`. Keep the built launcher in this repo's `launcher` folder, not in
   the game folder; it finds `fifazf.exe` through `FO3_GAME`.
4. Run `play.bat`.

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
