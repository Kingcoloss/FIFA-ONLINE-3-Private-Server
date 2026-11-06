# FO3ID Private Server

**English** | [Bahasa Indonesia](README.id.md) | [简体中文](README.zh-CN.md) | [ไทย](README.th.md) | [Tiếng Việt](README.vi.md) | [한국어](README.ko.md)

A local private server for **FIFA Online 3 Indonesia** (Garena, client build 654420), written in
Python. Garena shut the official servers down on 2020-06-30; this project re-implements the
backend the client talks to, so the game can be played offline on one PC.

> Not affiliated with EA, Spearhead or Garena. This repository contains **no game files** (no
> client, database, assets or music) — you need your own FO3 ID install. It does **not** include,
> modify or circumvent the client's anti-cheat (XIGNCODE3 / HackShield); that is out of scope.
> Built for game preservation and research.

## What works

Tested in the real client (Indonesian UI):

- Login → manager select / create (club picker over 501 licensed clubs) → lobby (FREEROAM).
- **Single → Liga** (full season: calendar, matches, table, rewards, promotion) and **Cup**
  (draw, groups, knock-out, extra time, penalties).
- **Market** (buy / sell; a card's price follows its rating and grade: the median fifaaddict
  price of all cards with that rating), **Upgrade** (grade +1…+10), **Tukar** and
  **Tukar Scout** player trades (every Market card, not only the region's licensed ones),
  Tim inti / Tim Cadangan, squad and tactics saving.
- **Shop** with every tab (player packs, consumables, packages, MP Shop, monthly and chained
  packages, special bonus), pack opening with random grades, Item saya, Bag, daily login reward.
  **Gudang** (Item saya > Gudang): move packs and consumables there and back.
  Extra packs: **All Season +8** (any season, +1…+8) and one pack for '07 and every season
  fifaaddict lists.
- Always VIP + official PC warnet (IGR) perks, manager delete / restore, season '17 cards.
- Formation list (the club's own + the game's 33 common formations, read from the client's
  formations table) and manager / player levels: EXP after every match, player LV.1-23
  (+1 to every attribute per level), manager LV.1-100.
- Game sound and the EA Trax menu music. `tools/eatrax_song.py` puts your own song first in it,
  but the game then crashes after matches (see the known issue below).
- Admin web page on http://127.0.0.1:8088/ (EP, players, packs, gifts, daily rewards, match rewards, Shop, log)
  with a language switch (issue #15): Bahasa Indonesia, English, 简体中文, ไทย, Tiếng Việt, 한국어;
  the browser remembers the choice.
- Real club kits in matches (kit id = `teamid << 5 | type`; the old `<< 10` gave a checkerboard).
- Matches play through the second half with **team color** on (season colors used to crash it at
  half time), then show the EXP and reward screens.

Added, passing the tests but not yet checked in the client:

- **Team color** bonus itself: the starting XI gets an OVR bonus for players from the same club
  (4-5 players +1 up to 10-11 +4), nation or season (5-6 +1 up to 9-11 +3); per player only the
  best one counts.
- **Opsi > Kontrol** (keyboard and gamepad keys) is saved: the server always sends the game's own
  default key layout, so the screen can apply and save changes (it used to drop them).
- **Kit choice** on the game setting screen (home / away per side) is kept for the match.
- **Manager select** shows the club's most valuable player in the club's kit (it showed the
  game's default Barcelona player).
- Fixed crashes: the startup notice popup (empty web URL), the Beginner's Guide league tutorial
  (missing script).
- **Upgrade chance**: a base chance by target grade, times the "Rasio bonus keberhasilan" label
  the Upgrade tab shows from the material's grade (Kosong x1, Low x1.1, Normal x1.25,
  High x1.5). A failed upgrade from +5 or higher drops one grade.
- **Top 200 packs**: the extra packs now give their season's 200 best cards ("17 Top 200",
  "07 Top 200", …); **All Season Top 300 +8** gives any season's cards rated 81 and up.
- **Upgrade with a +0 card** (issue #5): a club's own +0 card keeps the target's grade at 100%
  (+4 with +0 stays +4) and a +10 may take one; the kept card leaves Tim Cadangan when it takes
  the used card's squad slot.
- **Upgrade 2.5** (the client's newer Upgrade screen, `features...enhancement.v2_5`):
  - **upgrade points**: a failed upgrade grants points; "Gunakan poin" spends them for +10%;
    buy more free in Shop > Paket (Upgrade Point 100 / 500 / 1.000);
  - **boost items** Enhancement Boost Gold / Silver / Bronze (+15 / +10 / +5%), free in
    Shop > Dapat dikonsumsi;
  - a permanent **upgrade event** (+10% for targets +1…+9, `GET /events`);
  - "Coba pengembalian lagi" gives back a grade lost to a failure, for points.
- **Tukar v2** (`trade2`): a trade is rated by its value (TP) in 15 levels, each with a maximum
  offer grade; the tab shows what another manager got "yesterday" at that level; legend-season
  cards count 1.5x; no daily or value limit. Tukar Scout keeps working beside it.
- **Tukar Scout**: the client's two other scouts, Scout Khusus (event; legend-season quest) and
  VVIP Scout (best offers; 1 billion EP quest). Scout Amatir is gone so the list fits its 5 rows
  (once it scrolled, a met quest lit another scout's card or none).
- **Upgrade team colors** (the client's "Upgraded Team"): starters of grade +2, +5 or +8 and
  higher; 5-6 / 7-8 / 9-11 of them give +1 / +2 / +3, +2 / +3 / +4 and +3 / +4 / +5 OVR. The
  single-grade ones ("+3 club" … "+10 Golden summit") need all 11 starters at that grade or higher:
  +4 (club +3/+4), +5 (silver +5…+7), +6 (Golden passion +8/+9), +7 (Golden summit +10). A
  player gets his best upgrade color on top of his best club / nation / season color.
- **Every team color the client names** (188 now):
  - 27 clubs (Real Madrid … Jeonbuk): Single team's tiers plus the club's own boost from the
    game's tooltip, e.g. Barcelona MF agility +3;
  - 30 nations: Satu Negara's tiers plus e.g. Spanyol MF ball control +2;
  - season colors under the game's names (World Best up to +5, World Legend, 2014 WC All-Star, …);
  - about 75 specials: '14 WC and EC per nation, nation BEST, MSN / BBC Trio, Arsenal
    Invincibles, Galácticos, LEGENDS, the TOP 100s, Power Header, New Star, ….

  The original boosts and player lists were server data and are gone. Player lists come from the
  player database (season, club, named players, stat limits); boosts come from the one tooltip
  line the game still has. Left out: the [Test] colors, "+2~7", "14 WC Single Nation" and four
  duplicate club entries.
- **Formasi** no longer opens with "Tidak cukup pemain" (it loads preset squad 1, which the
  server never sent). A hole in the XI (issue #7, an upgrade of two starters of one player) is
  filled from the bench, and the bench never holds a second card of a player. Every starter gets
  his `starting` data (workrate and pitch spot): without it the game shows him on the bench.
- **Tim > Peran** saves the captain and each set-piece taker (issue #8: `PUT /game/my/team/captain`
  and `/game/my/team/kickers/<0-4>` were missing). The five kicker slots (left corner, right
  corner, free kick, penalty, free kick 2) keep their place; an empty one takes a starter.
- **Tim > Locker room** works (issue #13): shirt style and sleeves, tattoo, wristband, gloves
  (keepers: 39 glove designs), socks, knee pads, 614 boots by brand, and shirt numbers (taking
  a number swaps it with its wearer). The item table `/static/db/LOCKERROOMITEM` was missing, so
  every list was empty and the boots panel broke. A player's look is saved on the card, and
  Item saya holds a permanent locker room ticket, which the game needs to show the look in matches.
  Only the client's own wristband, glove and knee pad models are offered (one of each).
- **Shop control on the admin page** (issue #10): every Shop tab (player packs, consumables,
  packages, monthly packages, Featured, MP Shop, Special bonus, chained packages). New packs (by
  season, top N, OVR, max grade, position, league), random boxes, EP cards, packages and monthly
  packages, with any of the client's 147 shop icons. Built-in products can be changed, hidden or
  given a fixed price, and the whole Shop can be made free or not. Changes go to
  `gamedata/shop.json`.
- **Simulasi Liga** coupon (item 2001, Shop > Dapat dikonsumsi): Liga's Simulasi button gives a
  match result without playing, one coupon per match. The simulation screen plays the match's goals,
  shots, saves and cards, matching the result (`eventlist` was empty, so it showed 0-0), and the
  result screen after it shows the score, player ratings and stats, possession and MOTM (it was blank),
  then the EP reward and back to the Liga menu. The button counts the coupons in Item saya
  and stayed off because the item did not exist. New coupons can be made on the admin page (type
  "Kupon Simulasi Liga").
- **Pre-match squad screen** (Liga and Cup, issue #16): swaps, subs and formation changes now
  stick and are saved to the club (`PUT /match/<id>/side/<side>/squad` had no handler, so each
  change undid itself). The formation list is filled, and the stamina bars show full (no fatigue
  is kept between matches).
- **Team FW / MF / DF ratings match the players** (issue #18): on the squad screens and in the lobby
  they are the average of the ratings the player list shows (rating at the player's slot plus
  upgrade grade, level and team color). They were built from the bare card ratings, about 12 lower.
- **Rekor liga tabs** (issue #19): the standings table shows (its tab broke on the missing
  `league2difficulty` table, which now also decides who goes up or down at season end). Rekorku
  lists each player's matches, rating, goals, assists, passes, tackles and saves from the season's
  played matches, and Rekor gabungan shows the season's best XI and stat leaders. Only my own
  players are counted, and simulated matches add no player stats.
- **Squad A / B / C in Formasi** (issue #20): the box left of the formation button picks one of
  three saved squads (it was empty: the server sent no squad count). Each squad keeps its own XI,
  formation and roles.
- **Controller and camera settings stay in matches** (issue #21): after Opsi > Konfirmasi the game
  reads the saved options back from the reply, which had none, so every match put back the options
  from login (keyboard, old camera). In a match, F3-F9 switch the camera (F5 = Co-op).
- **Ganti tim shows the club and your player** (issue #23): the item's club screen now shows the
  league, rival, stadium, year built and capacity, and your player in the new club's kit with
  birth date, height and weight. The server's club info had none of these, and without the kit
  the 3D player was never drawn.
- **Camera height and zoom can be changed** (issue #24): in Opsi > Kamera setting the Customise gauges
  (height and zoom; zoom, speed and swing for the Pro camera) had no value and could not be
  changed, because the server sent an empty camera setting. They now start at 10 (of 20).
- **Every national team in Tim lain** (issue #24): the International league (the last nation in
  the list) has 40 national teams, Italy, England, Germany, Spain and France among them. A
  national team's squad comes from each player's national-team link; before, only teams whose
  players had no licensed club were listed.
- **Player positions on the result screen** (issue #26): after a match the result screen's pitch
  stacked every player at the goal, because the game reports all of them as goalkeepers. The
  server now gives each player the position of their squad slot.
- **Reward cards after a match** (issue #26): the reward screen's cards were empty. Now three
  cards are dealt: the one you pick gives EP (1,000 to 10,000), a player pack (Semua Pemain or
  '14 Top 200) or a Lucky EP item, and the other two show what you could have got.
- **Draft packs and EXP capsules** (issue #27): Shop > Pak pemain sells draft packs ("06 Draft Pick 3",
  "2017 Draft Pick 5", "World Legend Draft Pick 3"). "Gunakan" opens the player picker, filled with the
  season's most valuable cards; pick N cards of that season (search by name, league or club) and one of
  them is opened. Shop > Dapat dikonsumsi sells EXP capsules (1,000, 5,000, Max = LV.23, one for LV.10
  and below, one for 2017 cards): pick a player and he gets the EXP. The draft screen's requests
  (`/item/draftpack/<id>/players/<n>`, `/transfer/price/default/<grade>`) and the capsule item type were
  missing. The admin page makes more of both (a pack's "Draft" field, item type "EXP Capsule").
- **Random boxes open** (Kotak Platinum and the rest, issue #12): the box screen lists its prizes
  from `staticdata.availables`, which was missing, so every box failed at "Gunakan".
- **New cards join Tim Cadangan**: a card from a pack, a trade, the Market, the Bag or the admin
  page shows "-" in Skuad's Tim column, ready for Tukar Scout. Its button moves it to Tim inti
  (green RES: Tim inti outside the 18 of the squad), which can hold the whole club (200). The admin
  page can move every Tim Cadangan card to Tim inti at once.
- **Market search** finds cards of every season: the game searches only the seasons in
  `/static/roster`, which lacked 29 seasons with Market cards (World Legend, World Best,
  '14 TOTS, …), so e.g. WL R. Gullit never showed up. The Market filter's season list works
  (issue #14: picking a season threw "cannot convert 39 to Array", as each season's `value` must
  be a list) and shows the client's season names (World Legend, 02 Chinese Legend, …).
- **Every tradeable card** is on the Market, in the trades and in a pack: a card counts when
  fifaaddict lists it or the game itself marks it tradeable (`permid.transferable`). fifaaddict
  alone left out 6,599 cards (4,313 of them '17); the Market now holds 44,703. The new
  **Semua Pemain** pack can give any of them.
- **Tim > Klub > Informasi tim** (issue #9) shows the start date, home stadium and "year built /
  capacity" (`coach.career`, `coach.stadium`, `GET /stadium/<id>` from the client's own stadium
  table), and its player panel (stepper, 3D player, price, grade), which stayed empty without a
  stadium. Names from the client's database read as UTF-8 (`tools/re/eadb.py` read latin-1).
- **Pack opening glow** follows the card's value: none below 10 million EP, then levels 1-3 from
  10 million, 100 million and 1 billion EP.

Known issue, not solved: with a custom EA Trax song installed by `tools/eatrax_song.py` the game
runs out of its RAssets memory pool after every match, while the Cup screen or the lobby loads
again (crash in `FifaRNA::Crowd::PlacementData::Seats[]`); with the game's own music it does not.
It crashed the same way with the song as raw PCM (37.7 MB), as EALayer3 (6.5 MB,
`tools/re/ealayer3.py`) added as a 10th track, and as EALayer3 replacing TrackID 1 with the music
bank smaller than the shipped one, so the size of the music is not the cause. Keep the game's own
music: `python -I tools/eatrax_song.py --restore` puts it back.

Not done: online modes (ranked, friendly, King of the Hill), Road to World, league simulation.

## Requirements

- Windows, Python 3.12, `pip install cryptography` (messenger + DB extraction).
- An FO3 ID client install (default path `D:\FO3ID\32795`; elsewhere, set `FO3_GAME` to its
  folder; the server warns at startup when it cannot find the client's image cache there).
- Optional: ffmpeg (only for `tools/eatrax_song.py`).

## Setup

1. Extract the player database from your client:
   `python extract_fifadb.py D:\FO3ID\32795` → `gamedata/fifadb.sqlite`.
2. Optional market prices: `python tools/fa_sync.py` → `gamedata/fa_prices.json` (polite
   fifaaddict.com scraper; without it prices come from a rating formula).
3. TLS certificate for the client's hardcoded API host `APSEODESK172` (self-signed is accepted):

   ```
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=APSEODESK172" -addext "subjectAltName=DNS:APSEODESK172" -keyout key.pem -out cert.pem
   python -c "open('certs/server.pem','w').write(open('cert.pem').read()+open('key.pem').read())"
   ```

4. Hosts file (as admin): `127.0.0.1 APSEODESK172`.
5. Build the launcher once (`launcher/fifalauncher.cs`, build line inside), then double-click
   **`play.bat`**: it opens the server window (`python start_all.py` = `http_config.py 443
   --tls` + `messenger.py`; close that window to stop the server) and starts the game without
   the UAC prompt.

6. By hand instead: `python start_all.py`, then start the client with the server arguments
   (what `launcher/fifalauncher.exe` and `launch_game.ps1` pass):

   ```
   fifazf.exe -QUICKMATCH/SERVER=127.0.0.1:28000 -QUICKMATCH/PROTOCOL=tcp -QUICKMATCH/NOTISERVER=127.0.0.1:28001 -FIFA/LAUNCHER/PID=<pid> -PUBLISHER/GARENA/TOKEN=testtoken -LOCALE/PUBLISHING_REGION=ID -DUMPTRUCK/SERVER=127.0.0.1 region id token testtoken
   ```

## Files

| File | Role |
|---|---|
| `http_config.py` | The REST backend the client calls (`https://APSEODESK172`): login, account, coaches, club creation, squad, league, cup, market, upgrade, trades, shop, items, Bag, daily reward, static tables, and `/cdn/` (serves crests and cards from the client's own `_cache`). State lives in `gamedata/state.json`. Env: `FO3_LANGUAGE` (default `ind`), `FO3_GAME` (client folder), `FO3_ASSETS`, `FO3_HALF_LENGTH`, `FO3_ADMIN_PORT`. |
| `messenger.py` | Notification server on `:28002`. Frames `<u16 LE len><u16 type=2><Blowfish-CBC(key "kueec", IV 0) of JSON+"\n">`; answers `auth`, `ping`, `signon`. `python messenger.py --selftest`. |
| `admin.py` + `admin/index.html` | Admin page (started by `http_config.py`, localhost only, no password). Its Shop tab saves to `gamedata/shop.json`. Every word on it, error messages included, is in the `I18N` tables at the end of `admin.py`, one per language; a new language is one more table, and `python admin.py` checks that every table has the same keys. |
| `responses/` | Per-endpoint JSON bodies (`/a/b/c` → `responses/a_b_c.json`, re-read on every request). Shapes come from the client's AS3 code. |
| `extract_fifadb.py` | Client player DB (`data_0.big`, RefPack + Blowfish) → SQLite. |
| `gen_teams.py` | Starter squads and club summaries from `gamedata/fifadb.sqlite`. |
| `tools/eatrax_song.py` | Puts a song first in the game's EA Trax menu music as EALayer3, replacing TrackID 1 (edits `data_0.big` / `data_1.big` by appending; `--restore` puts the originals back). Crashes the game after matches, see the known issue. |
| `tools/fa_sync.py` | fifaaddict.com price sync. |
| `tools/fa_faces.py` | Adds the player mini faces missing from the client's cache (fifaaddict serves the same 128x128 PNGs); `--crests` adds the missing club crests (most clubs have none in the cache, so the game shows a default one). Resumable, `--remove` undoes it. |
| `tools/re/` | Reverse-engineering helpers: `bigdir.py` (BIg4 archive tables), `refpack.py` (RefPack codec), `eadb.py` (EA "DB" database tables), `abc*.py` (AS3 bytecode parser / grep / schema miner), `gfxx.py` (UI SWFs), `memgrab.py`, `gamectl.ps1` (drive the client window for tests). |
| `blaze.py`, `server.py`, `test_client.py`, `analyze_capture.py` | EA Blaze framing (Fire/TDF) and a loopback test server from the first phase of the project; the client turned out to use REST + the messenger instead. |
| `analysis/` | Early client analysis scripts (strings, PE sections, network endpoints). |
| `FO3ID-private-server.md`, `reports/` | Findings and progress reports (`reports/` is in Indonesian). |

## Tests

```
python run_tests.py
```

Runs the Blaze/loopback self-tests and `test_league.py`, which drives every backend feature
(club creation, league, cup, market, upgrade, trades, shop, daily reward, admin API, manager
delete) against a fresh account. Needs `gamedata/fifadb.sqlite`.

## Contributors

- **SoloPlayer** — project owner, testing in the real client.
- **Claude** (Anthropic's AI assistant, via Claude Code) — reverse engineering and most of the
  server code, written together with the owner.

## License

[GNU GPL v3](LICENSE) for the code and documentation in this repository. FIFA Online 3, its
client, data, assets and music belong to their respective owners and are not covered.
