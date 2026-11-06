"""Add FIFA Online 4's 26 LIVE and 25 LIVE cards to the game as two new seasons.
User: "buatkan session baru untuk musim 2026 bedasarkan database fifa online 4
https://id.fifaaddict.com/fo4db?class=25,live ikuti stat nya dianggap +0 icon ikuti berdasarkan
fifa online 4".

    python tools/fo4_season.py fetch [--min-ovr 72]   fifaaddict search -> gamedata/fo4_cards.json
    python tools/fo4_season.py collect                 console script that reads the card pages
    python tools/fo4_season.py import FILE             its output -> gamedata/fo4_cards.json
    python tools/fo4_season.py build                   cards -> gamedata/fifadb.sqlite
    python tools/fo4_season.py install [--game DIR]    fifadb + season icons -> the client
    python tools/fo4_season.py restore [--game DIR]    put the client files back
    python tools/fo4_season.py selftest

Seasons keep FO4's own codes (Nexon's seasonid.json): 300 = "26 LIVE", 325 = "25 LIVE", so a card
is spid = season * 1e6 + player id, like every FO3 card (PlayerListUtil.getSeason is
floor(spid / 1e6) and takes codes over 99). Stats are the fifaaddict card page's attributes,
taken as +1 (user, after "+0" first: "Session 25,26 state grade 0 hanya untuk manager baru, untuk
trading marker dan pack harus pakai state+1"): stored PLUS1 lower, so the client's rating
(calcPosOvr) of a +1 card from the Market, a pack or a trade comes out as FO4's OVR, and a new
club's +0 starters are PLUS1 below it. Players FO3 already knows (same birth date and name) keep their player id,
face and names; the others get a new id from NEW_PID up, a generic head copied from a FO3 player
with the same skin tone, and names in every names table. No card photo for those (silhouette).
A player whose club FO3 does not have (no FO3 card plays there, so the client has neither its
name nor its crest) goes to FO3's Rest of the World team, like FO3's own players of unlicensed
clubs (user: "Jika player session 25 26 klub nya tidak ada di db maka masuk rest of world").

fetch walks fifaaddict's search (100 rows a page, so it splits by rating, then position; one
request every DELAY s, cached in %TEMP%/fo4_cache so a rerun resumes), plus one search per FO3
trait (trait=<slug>) for the cards' Karakteristik. FO4's LIVE cards only carry the newer traits:
of FO3's 30 they have 18 (no power header, swerve, second wind, ...). The stats are not in the
pages' HTML (see COLLECT_JS). After build and install, restart the server.
"""
import argparse, collections, difflib, hashlib, json, os, re, shutil, sqlite3, sys, tempfile, time, unicodedata
import urllib.request
from contextlib import closing

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "re"))

CARDS = os.path.join(ROOT, "gamedata", "fo4_cards.json")
FIFADB = os.path.join(ROOT, "gamedata", "fifadb.sqlite")
BACKUP = os.path.join(ROOT, "backup", "fo4season")
SITE = "https://id.fifaaddict.com"
CLASSES = {"live": 300, "25": 325}
SEASON_NAMES = {300: "26 LIVE", 325: "25 LIVE"}
POSITIONS = "st,lw,rw,cf,cam,lm,rm,cm,cdm,lwb,rwb,lb,rb,cb,gk".split(",")
CAP, DELAY = 100, 2.0
NEW_PID = 700000  # first player id for players FO3 does not have (FO3's are below 300000)
with open(os.path.join(ROOT, "responses", "static_db_PLAYERGRADE.json"), encoding="utf-8") as _f:
    PLUS1 = json.load(_f)["1"]["boost"]["PLAYER_ALLATTRIBUTES_ALL"]  # FO3's +1 all-attribute boost (5)
REST_OF_WORLD = (999998, 9998)  # FO3's (teamid, leagueid) for players of unlicensed clubs (11,000+ cards)
FO3_CLUB = {131682: 44, 115845: 39, 115841: 46}  # FO4's new ids of clubs FO3 has: Lombardia FC = Inter,
# Bergamo Calcio = Atalanta, SS Lazio = Lazio (Milano FC stays out: FO3 has no AC Milan)


# --- window.__NUXT__ (a JS function call returning an object literal) -------------------------

class _Ref(str):
    pass


_WORD, _NUM = re.compile(r"void 0|[\w$]+"), re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?")


def _js(s, i):
    """Parse one JS literal value at s[i:]; identifiers become _Ref (resolved later)."""
    while s[i] in " \n\t":
        i += 1
    c = s[i]
    if c in "{[":
        obj, end, i = c == "{", "}" if c == "{" else "]", i + 1
        out = {} if obj else []
        while True:
            while s[i] in " \n\t,":
                i += 1
            if s[i] == end:
                return out, i + 1
            if not obj:
                v, i = _js(s, i)
                out.append(v)
                continue
            if s[i] == '"':
                key, i = _js(s, i)
            else:
                m = _WORD.match(s, i)
                key, i = m.group(), m.end()
            assert s[i] == ":", s[i - 20:i + 20]
            out[key], i = _js(s, i + 1)
    if c == '"':
        j = i + 1
        while s[j] != '"':
            j += 2 if s[j] == "\\" else 1
        return json.loads(s[i:j + 1]), j + 1
    m = _NUM.match(s, i)
    if m:
        v = m.group()
        return (float(v) if m.group(1) or m.group(2) else int(v)), m.end()
    w = _WORD.match(s, i).group()
    return {"true": True, "false": False, "null": None, "void 0": None}.get(w, _Ref(w)), i + len(w)


def nuxt(html):
    """window.__NUXT__ of a fifaaddict page as Python data: (function(a,b,..){return {..}}(v,..)),
    or a plain {..} when the page needs no shared values."""
    head = "window.__NUXT__=(function("
    if head not in html:
        return _js(html, html.index("window.__NUXT__=") + len("window.__NUXT__="))[0]
    i = html.index(head) + len(head)
    j = html.index(")", i)
    params = html[i:j].split(",")
    body, k = _js(html, html.index("return", j) + len("return"))
    k = html.index("(", k) + 1
    vals = []
    while True:
        while html[k] in " ,":
            k += 1
        if html[k] == ")":
            break
        v, k = _js(html, k)
        vals.append(v)
    env = dict(zip(params, vals))

    def res(v):
        if isinstance(v, _Ref):
            return env.get(v)
        if isinstance(v, dict):
            return {k: res(x) for k, x in v.items()}
        if isinstance(v, list):
            return [res(x) for x in v]
        return v
    return res(body)


# --- fetch ------------------------------------------------------------------------------------

def fetcher(cache):
    os.makedirs(cache, exist_ok=True)
    last = [0.0]

    def fetch(path):
        f = os.path.join(cache, hashlib.sha1(path.encode()).hexdigest() + ".html")
        if os.path.exists(f):
            return open(f, encoding="utf-8").read()
        time.sleep(max(0.0, DELAY - (time.time() - last[0])))
        for attempt in range(4):
            try:
                req = urllib.request.Request(SITE + path, headers={"User-Agent": "Mozilla/5.0 (FO3 private server season sync)"})
                body = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
                break
            except OSError as e:
                print("retry", attempt, path, e, flush=True)
                time.sleep(15 * (attempt + 1))
        else:
            raise SystemExit("failed: " + path)
        last[0] = time.time()
        open(f, "w", encoding="utf-8").write(body)
        return body
    return fetch


def listing(fetch, cls, min_ovr):
    """{uid: search row} of a class at displayed rating >= min_ovr."""
    rows = {}

    def page(q):
        items = nuxt(fetch(f"/fo4db?class={cls}{q}"))["data"][0]["items"]
        for it in items:
            rows.setdefault(it["uid"], it)
        return len(items)

    for v in range(99, min_ovr - 1, -1):
        if page(f"&attr=ovr_{v}-{v}") >= CAP:
            for p in POSITIONS:
                if page(f"&attr=ovr_{v}-{v}&pos={p}") >= CAP:
                    print(f"  {cls} ovr {v} pos {p}: over {CAP}, some cards missed", flush=True)
        print(f"{cls} ovr {v}: {len(rows)} cards", flush=True)
    return rows


# trait1 bit order = the client's PlayerListUtil.PLAYER_TRAITS (TRAIT1_START_BIT 0 .. END 29;
# trait2 is not shown); fifaaddict's trait slugs are the same names (crowd-favourite: none)
FO3_TRAITS = ("inflexibility long-throw-in takes-powerful-driven-free-kicks diver injury-prone solid-player "
              "avoids-using-weaker-foot dives-into-tackles tries-to-beat-offside-trap selfish leadership "
              "argues-with-officials early-crosser finesse-shot flair long-passer long-shot-taker speed-dribbler "
              "play-maker pushes-up-for-corners puncher gk-long-thrower power-header gk-one-on-ones giant-throw-in "
              "outside-foot-shot crowd-favourite swerve second-wind acrobatic-clearance").split()


# Style = the badges bits in the client's PlayerListUtil.PLAYER_BADGES order. fifaaddict has no
# such thing for FO4, so they come from the stats, by rules fitted on FO3's own 15,274 2017
# cards (exact for speedster, dribbler, box to box, crosser, tackling, tactician, clinical
# finisher and complete defender; the others miss a few cards).
FO3_BADGES = ("poacher speedster aerial-threat dribbler playmaker box-to-box distance-shooter crosser "
              "fk-specialist tackling tactician agile strength clinical-finisher complete-defender "
              "complete-midfielder complete-forward").split()


def badges(r):
    """badges bits of a players row (dict with stats, weight and workrates)."""
    at = lambda **kv: all(r[k] >= v for k, v in kv.items())
    b = {"poacher": at(finishing=77, positioning=73, headingaccuracy=81),
         "speedster": r["acceleration"] + r["sprintspeed"] >= 154,
         "aerial-threat": at(headingaccuracy=77, strength=69),
         "dribbler": at(dribbling=73, balance=63),
         "playmaker": at(vision=73, shortpassing=74, longpassing=71),
         "box-to-box": r["stamina"] >= 73 and r["attackingworkrate"] == 2 == r["defensiveworkrate"],
         "distance-shooter": at(longshots=72, shotpower=74, ballcontrol=57),
         "crosser": at(crossing=73, curve=68),
         "fk-specialist": at(freekickaccuracy=73, ballcontrol=64, crossing=58),
         "tackling": at(slidingtackle=73, standingtackle=72),
         "tactician": at(reactions=68, interceptions=73),
         "agile": r["agility"] >= 76,
         "strength": at(strength=73, weight=83),
         "clinical-finisher": at(finishing=73, longshots=68)}
    b["complete-defender"] = b["tackling"] and b["tactician"] and (b["aerial-threat"] or b["agile"] or b["strength"])
    b["complete-midfielder"] = b["playmaker"] and (b["crosser"] or b["tackling"] or b["clinical-finisher"])
    b["complete-forward"] = b["clinical-finisher"] and b["speedster"] + b["aerial-threat"] + b["dribbler"] + b["strength"] >= 2
    return sum(1 << i for i, k in enumerate(FO3_BADGES) if b[k])


def search(fetch, cls, lo, hi, extra=""):
    """{uid: row} of a class at displayed rating lo..hi: halves the range while a page is full."""
    items = nuxt(fetch(f"/fo4db?class={cls}{extra}&attr=ovr_{lo}-{hi}"))["data"][0]["items"]
    if len(items) < CAP:
        return {it["uid"]: it for it in items}
    if lo < hi:
        mid = (lo + hi) // 2
        return {**search(fetch, cls, mid + 1, hi, extra), **search(fetch, cls, lo, mid, extra)}
    if "&pos=" in extra:
        print(f"  {cls}{extra} ovr {lo}: over {CAP}, some cards missed", flush=True)
        return {it["uid"]: it for it in items}
    out = {}
    for p in POSITIONS:
        out.update(search(fetch, cls, lo, hi, f"{extra}&pos={p}"))
    return out


def card_traits(fetch, cls, min_ovr, total):
    """{uid: [trait slugs]} from one search per FO3 trait. A search that finds (nearly) every
    one of the class's `total` cards ignored its filter (inflexibility does): left out."""
    out = collections.defaultdict(list)
    for slug in FO3_TRAITS:
        if slug == "crowd-favourite":
            continue
        hits = search(fetch, cls, min_ovr, 99, f"&trait={slug}")
        if total and len(hits) >= 0.9 * total:
            print(f"  {cls}: the {slug} search ignores its filter ({len(hits)} cards), left out", flush=True)
            continue
        for uid in hits:
            out[uid].append(slug)
    return out


def load_cards():
    return json.load(open(CARDS, encoding="utf-8")) if os.path.exists(CARDS) else {}


def save_cards(cards):
    tmp = CARDS + ".tmp"
    json.dump(cards, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, CARDS)


def cmd_fetch(a):
    fetch = fetcher(a.cache)
    cards = load_cards()
    for cls, season in CLASSES.items():
        for uid, row in listing(fetch, cls, a.min_ovr).items():
            if int(row["year"]) == season:
                cards.setdefault(uid, {}).update(row=row, season=season)
        traits = card_traits(fetch, cls, a.min_ovr, sum(c["season"] == season for c in cards.values()))
        for uid, c in cards.items():
            if c["season"] == season:
                c["fo3traits"] = traits.get(uid, [])
        print(f"{cls}: traits of {sum(1 for u in traits if u in cards)} cards", flush=True)
    save_cards(cards)
    print(f"{len(cards)} cards listed, {sum('attr' in c for c in cards.values())} with stats -> {CARDS}")


# The card pages load their stats from fifaaddict's own API after a handshake, so the stats are
# read in a browser tab on the site: `collect` prints a script for the tab's console that opens
# each card (in-app navigation, like a click), keeps one line per card in localStorage.fo4rows
# and copies them all at the end; save them to a file and run `import FILE`.
# Line: uid|ROW_FIELDS...|33 two-digit stats in STATS order.
ROW_FIELDS = ("name name_short birthdate height weight pos1 pos2 pos3 pos4 foot_pref foot_weak workrate_att "
              "workrate_def skill_level skintonecode reputation current_ovr nation_id team_id league_id nation_squad_id").split()
COLLECT_JS = """(async () => {
  const todo = %s, F = %s, S = %s, wait = ms => new Promise(r => setTimeout(r, ms));
  const rows = (localStorage.getItem('fo4rows') || '').split('\\n').filter(Boolean);
  const done = new Set(rows.map(r => r.split('|')[0]));
  for (const uid of todo) {
    if (done.has(uid)) continue;
    window.$nuxt.$router.push('/fo4db/pid' + uid);
    let s = null;
    for (let i = 0; i < 80 && !(s && s.attr && s.db); i++) {
      await wait(250);
      s = window.$nuxt.$store.state.foState['foPlayerpid' + uid + '_id'];
    }
    if (s && s.attr && s.db) {
      const st = S.map(k => String(Math.min(99, (s.attr[k] || {}).value || 0)).padStart(2, '0')).join('');
      rows.push([uid, ...F.map(f => String(s.db[f] ?? '').replace(/[|\\n]/g, ' ')), st].join('|'));
      localStorage.setItem('fo4rows', rows.join('\\n'));
    }
    window.fo4progress = rows.length + '/' + todo.length;
    await wait(%d);
  }
  window.fo4progress = 'done ' + rows.length;
  try { copy(rows.join('\\n')); console.log('fo4rows copied: save them to a file, then run import FILE'); } catch (e) {}
})();"""


def collect_js(cards):
    todo = [u for u, c in sorted(cards.items(), key=lambda kv: -kv[1]["row"].get("pos1val", 0)) if "attr" not in c]
    return COLLECT_JS % (json.dumps(todo), json.dumps(ROW_FIELDS), json.dumps(STATS), int(DELAY * 1000)), len(todo)


def cmd_collect(a):
    js, n = collect_js(load_cards())
    print(f"// {n} cards to read: paste into the console of a {SITE}/fo4db tab\n{js}")


def cmd_import(a):
    cards, got = load_cards(), 0
    for line in open(a.file, encoding="utf-8").read().splitlines():
        parts = line.split("|")
        if len(parts) != 2 + len(ROW_FIELDS) or parts[0] not in cards:
            continue
        st = parts[-1]
        cards[parts[0]].update(db=dict(zip(ROW_FIELDS, parts[1:-1])), attr={k: int(st[2 * i:2 * i + 2]) for i, k in enumerate(STATS)})
        got += 1
    save_cards(cards)
    print(f"{got} cards imported, {sum('attr' in c for c in cards.values())}/{len(cards)} with stats")


# --- build: cards -> gamedata/fifadb.sqlite ---------------------------------------------------
# fifaaddict values -> fifadb codes (checked on FO3's own 2017 cards: Messi, Ronaldo, Kante, Alba)
POS = {"GK": 0, "SW": 1, "RWB": 2, "RB": 3, "CB": 5, "LB": 7, "LWB": 8, "CDM": 10, "RM": 12, "CM": 14,
       "LM": 16, "CAM": 18, "RF": 20, "CF": 21, "LF": 22, "RW": 23, "ST": 25, "LW": 27}
WORKRATE = {"mid": 0, "medium": 0, "low": 1, "high": 2}
REPUTATION = {"regular player": 1, "famous player": 2, "top class": 3, "world class": 4, "legendary": 5}
STATS = ("acceleration aggression agility balance ballcontrol crossing curve dribbling finishing freekickaccuracy "
         "gkdiving gkhandling gkkicking gkpositioning gkreflexes headingaccuracy jumping longpassing longshots "
         "marking penalties positioning reactions shortpassing shotpower slidingtackle sprintspeed stamina "
         "standingtackle strength interceptions vision volleys").split()  # FO4's composure has no column
NAME_TABLES = ("nameskor", "nameschi", "namestha", "namesvie", "nameseng", "namesind")
PERM_TABLES = ("permkr", "permcn", "permth", "permvn", "permsg", "permid")
PIDS = os.path.join(ROOT, "gamedata", "fo4_pids.json")
HEADS = os.path.join(ROOT, "gamedata", "fo4_heads.json")  # {new player id: 2017 player whose head he wears}


def plain(s):
    """ASCII form of a name (FO3's own names carry no accents)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(ch)).replace("ø", "o").replace("Ø", "O")


def _key(s):
    return re.sub(r"[^a-z ]", "", plain(s).lower()).strip()


def _date(fo4):
    d, m, y = (int(x) for x in fo4.split("."))
    return y, m, d


def _same_name(a, b):
    """0..2: name likeness, +1 when the last names are the same (a shared first name is not enough:
    Lionel Messi and L. Gamba share a birthday)."""
    a, b = _key(a), _key(b)
    if not a or not b:
        return 0.0
    ta, tb = a.split(), b.split()
    # FO4's short form of a long FO3 name: "Rodri" / "Rodrigo Hernandez Cascante", "Fabian Ruiz" /
    # "Fabian Ruiz Pena" (every word starts a word of the other name, in order)
    it = iter(tb)
    inside = all(any(w.startswith(x) for w in it) for x in ta)
    return (ta[-1] == tb[-1] or inside) + difflib.SequenceMatcher(None, a, b).ratio()


def cmd_build(a):
    cards = {u: c for u, c in load_cards().items() if "attr" in c}
    pids = json.load(open(PIDS)) if os.path.exists(PIDS) else {}
    c = sqlite3.connect(FIFADB); c.row_factory = sqlite3.Row
    cols = [r[1] for r in c.execute("PRAGMA table_info(players)")]
    seasons = tuple(CLASSES.values())
    c.execute(f"DELETE FROM players WHERE spid / 1000000 IN ({','.join('?' * len(seasons))})", seasons)
    for t in PERM_TABLES:
        c.execute(f"DELETE FROM {t} WHERE spid / 1000000 IN ({','.join('?' * len(seasons))})", seasons)
    for t in NAME_TABLES:
        c.execute(f"DELETE FROM {t} WHERE playerid BETWEEN ? AND ?", (NEW_PID, NEW_PID + 99999))
    clubs = {r[0] for r in c.execute("SELECT DISTINCT teamid FROM players")}  # the clubs FO3 has
    # FO3's players: birth date -> [(pid, full, short)], and each pid's newest card (its face)
    born, best = collections.defaultdict(list), {}
    names = {r[0]: (r[1], r[2]) for r in c.execute("SELECT playerid, full_eng, short_eng FROM nameseng")}
    for r in c.execute("SELECT * FROM players ORDER BY spid"):
        pid, season = r["playerid"], r["spid"] // 1000000
        m = re.match(r"(\d+)/(\d+)/(\d+)", r["birthdate"] or "")
        if m and pid not in best:
            born[(int(m[3]), int(m[1]), int(m[2]))].append(pid)
        rank = (season == 88, season == 0, season)
        if pid not in best or rank > best[pid][0]:
            best[pid] = (rank, r)
    generic = collections.defaultdict(list)  # skin tone -> 2017 cards with a generic head
    for r in c.execute("SELECT * FROM players WHERE spid / 1000000 = 88 AND headclasscode = 1 ORDER BY spid"):
        generic[r["skintonecode"]].append(r)
    found = new = 0
    heads = {}
    for uid, card in sorted(cards.items(), key=lambda kv: kv[1]["season"]):
        db, attr, season = card["db"], card["attr"], card["season"]
        when = _date(db["birthdate"])
        cands = [(max(_same_name(db["name"], names.get(p, ("", ""))[0]), _same_name(db["name_short"], names.get(p, ("", ""))[1])), p)
                 for p in born.get(when, []) if p < NEW_PID]
        score, pid = max(cands, default=(0, None))
        person = f"{'-'.join(map(str, when))}|{_key(db['name'])}"
        if score >= 0.85:  # same last name, or a near-identical spelling (Haland / Haaland)
            base = dict(best[pid][1])
            found += 1
        else:
            pid = pids.get(person) or max([NEW_PID - 1, *pids.values()]) + 1
            pids[person] = pid
            tone = int(db.get("skintonecode") or 2)
            near = min(generic, key=lambda t: (abs(t - tone), t))
            pool = generic[near]
            base = dict(pool[int(hashlib.md5(person.encode()).hexdigest(), 16) % len(pool)])
            heads[pid] = base["playerid"]  # the engine DB row install copies for the 3D player
            base.update(trait1=0, trait2=0)
            new += 1
        spid = season * 1000000 + pid
        poss = [POS[p] for p in (db.get(f"pos{i}") for i in range(1, 5)) if p in POS][:4]
        ovr = int(db.get("current_ovr") or db.get("pos1val") or 0)
        tid = FO3_CLUB.get(int(db.get("team_id") or 0), int(db.get("team_id") or 0))
        team, league = (tid, int(db.get("league_id") or 0)) if tid in clubs else REST_OF_WORLD
        base.update({k: max(1, min(99, int(attr[k]))) for k in STATS if k in attr})
        base.update(spid=spid, playerid=pid, birthdate=f"{when[1]}/{when[2]}/{when[0]} 12:00:00 AM",
                    height=int(db["height"]), weight=int(db["weight"]),
                    preferredfoot=2 if db.get("foot_pref") == "left" else 1,
                    weakfootabilitytypecode=int(db.get("foot_weak") or 3), skillmoves=max(0, int(db.get("skill_level") or 1) - 1),
                    attackingworkrate=WORKRATE.get(db.get("workrate_att"), 0), defensiveworkrate=WORKRATE.get(db.get("workrate_def"), 0),
                    internationalrep=REPUTATION.get((db.get("reputation") or "").lower(), 1),
                    overallrating=ovr, potential=ovr, nationality=int(db["nation_id"]),
                    leagueid=league, teamid=team,
                    nationalteamid=int(db.get("nation_squad_id") or 0) or -1,
                    trait1=sum(1 << FO3_TRAITS.index(t) for t in card.get("fo3traits", [])),  # Karakteristik
                    contractvaliduntil=2027, playerjointeamdate="Tue, 01 Jul 2025 00:00:00 GMT", historyopen=0,
                    **{f"preferredposition{i + 1}": (poss[i] if i < len(poss) else -1) for i in range(4)})
        base["badges"] = badges(base)  # Style, from FO4's stats (the +1 card's)
        base.update({k: max(1, base[k] - PLUS1) for k in STATS if k in attr}, overallrating=ovr - PLUS1, potential=ovr - PLUS1)
        c.execute(f"INSERT INTO players ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [base[k] for k in cols])
        for t in PERM_TABLES:
            c.execute(f"INSERT INTO {t} (spid, licensed, transferable) VALUES (?, 1, 1)", (spid,))
        if pid >= NEW_PID:
            full, short = plain(db["name"]), plain(db.get("name_short") or db["name"])
            jersey = short.split(". ", 1)[-1]
            for t in NAME_TABLES:
                c.execute(f"INSERT OR REPLACE INTO {t} (playerid, full, short, full_eng, short_eng, jersey) VALUES (?,?,?,?,?,?)",
                          (pid, full, short, full, short, jersey))
    c.commit()
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    c.close()
    json.dump(pids, open(PIDS, "w"), indent=0)
    json.dump(heads, open(HEADS, "w"))
    per = collections.Counter(card["season"] for card in cards.values())
    print(f"{len(cards)} cards ({', '.join(f'{SEASON_NAMES[s]} {n}' for s, n in sorted(per.items()))}): "
          f"{found} players FO3 has, {new} new -> {FIFADB}")


# --- season icons: data/ui/components/Label.big ------------------------------------------------
# Label.gfx (CFX = zlib SWF) holds the two SeasonIcon clips: sprite 144 "seasonIconBig" and sprite
# 735, one frame per season labelled "<code>season" (SeasonIcon does gotoAndStop(season +
# "season")). Each frame puts a shape at depth 1 whose bitmap fill is a DefineSubImage (GFx tag
# 1008: id, image 0, x1, y1, x2, y2) of the DXT5 atlas Label_I1.dds. A new season gets its FO4
# icon drawn into free atlas space, a copy of the '17 shapes pointing at it, and one more frame
# in both clips.
LABEL_BIG = "data/ui/components/Label.big"
LABEL_GFX, LABEL_DDS = "data/ui/components/Label.gfx", "data/ui/components/Label_I1.dds"
ICON_SPRITES = (144, 735)
ICON_FREE_Y = 640  # the atlas is empty from about y 580 down
DEFINES = {2, 6, 7, 10, 11, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37, 39, 46, 48, 60, 75, 83, 84, 1008}


def _tags(b, p, end):
    out = []
    while p < end:
        h = int.from_bytes(b[p:p + 2], "little"); p += 2
        code, ln = h >> 6, h & 0x3F
        if ln == 0x3F:
            ln = int.from_bytes(b[p:p + 4], "little"); p += 4
        out.append([code, bytes(b[p:p + ln])])
        p += ln
        if code == 0:
            break
    return out


def _join(tags):
    out = bytearray()
    for code, data in tags:
        if len(data) < 0x3F and code not in (6, 20, 21, 35, 36):
            out += ((code << 6) | len(data)).to_bytes(2, "little")
        else:
            out += ((code << 6) | 0x3F).to_bytes(2, "little") + len(data).to_bytes(4, "little")
        out += data
    return bytes(out)


class _Bits:
    def __init__(self, b, p):
        self.b, self.bit = b, p * 8

    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | (self.b[self.bit >> 3] >> (7 - (self.bit & 7)) & 1)
            self.bit += 1
        return v

    def end(self):
        return (self.bit + 7) // 8


def _fills(d):
    """Byte offsets of the bitmap ids of a DefineShape payload's bitmap fill styles."""
    r = _Bits(d, 2); r.u(4 * r.u(5)); p = r.end()  # id, bounds
    out, n, p = [], d[p], p + 1
    for _ in range(n):
        assert 0x40 <= d[p] <= 0x43, f"fill style {d[p]:#x}"
        out.append(p + 1)
        m = _Bits(d, p + 3)
        for _ in range(2):  # scale, rotate
            if m.u(1):
                m.u(2 * m.u(5))
        m.u(2 * m.u(5))  # translate
        p = m.end()
    return out


def _bitmaps(shape):
    return [int.from_bytes(shape[p:p + 2], "little") for p in _fills(shape)]


def _shape_copy(data, new_id, bitmap):
    """A DefineShape payload with a new id and every real bitmap fill (not 0xFFFF) on `bitmap`."""
    d = bytearray(data)
    d[0:2] = new_id.to_bytes(2, "little")
    for p in _fills(d):
        if d[p:p + 2] != b"\xff\xff":
            d[p:p + 2] = bitmap.to_bytes(2, "little")
    return bytes(d)


def _bc3(px):
    """One DXT5 block from 16 RGBA pixels (row-major): min/max endpoints, nearest indices."""
    al = [p[3] for p in px]
    a0, a1 = max(al), min(al)
    out = bytearray([a0, a1])
    bits = 0
    if a0 > a1:
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
        for i, a in enumerate(al):
            bits |= min(range(8), key=lambda k: abs(pal[k] - a)) << (3 * i)
    out += bits.to_bytes(6, "little")
    seen = [p for p in px if p[3]] or px
    # endpoints: the two most different pixels (min/max per channel makes colours none of them has)
    hi, lo = max(((p, q) for p in seen for q in seen), key=lambda pq: sum((pq[0][c] - pq[1][c]) ** 2 for c in range(3)))
    pack = lambda c: (c[0] >> 3) << 11 | (c[1] >> 2) << 5 | c[2] >> 3
    c0, c1 = pack(hi), pack(lo)
    unpack = lambda v: ((v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)
    bits = 0
    if c0 != c1:
        if c0 < c1:
            c0, c1 = c1, c0
        e0, e1 = unpack(c0), unpack(c1)
        pal = [e0, e1, tuple((2 * x + y) // 3 for x, y in zip(e0, e1)), tuple((x + 2 * y) // 3 for x, y in zip(e0, e1))]
        for i, p in enumerate(px):
            bits |= min(range(4), key=lambda k: sum((pal[k][c] - p[c]) ** 2 for c in range(3))) << (2 * i)
    return bytes(out + c0.to_bytes(2, "little") + c1.to_bytes(2, "little") + bits.to_bytes(4, "little"))


def _draw(dds, img, x, y):
    """Encode an RGBA PIL image into the DXT5 atlas at (x, y) (multiples of 4, free space)."""
    w = int.from_bytes(dds[16:20], "little")
    for by in range(0, img.height, 4):
        for bx in range(0, img.width, 4):
            px = [img.getpixel((bx + i, by + j)) if bx + i < img.width and by + j < img.height else (0, 0, 0, 0)
                  for j in range(4) for i in range(4)]
            at = 128 + (((y + by) // 4) * (w // 4) + (x + bx) // 4) * 16
            dds[at:at + 16] = _bc3(px)


def label_with_icons(gfx, dds, icons):
    """(gfx, dds) of Label.big with one more SeasonIcon frame per {season: PIL RGBA icon}."""
    import zlib
    from PIL import Image
    assert gfx[:3] == b"CFX", gfx[:3]
    body = zlib.decompress(gfx[8:])
    r = _Bits(body, 0); r.u(4 * r.u(5)); start = r.end() + 4
    tags = _tags(body, start, len(body))
    atlas = Image.open(__import__("io").BytesIO(bytes(dds))).convert("RGBA")
    dds = bytearray(dds)
    defs = {}
    for code, data in tags:
        if code in DEFINES:
            defs[int.from_bytes(data[:2], "little")] = (code, data)
    next_id = max(defs) + 1
    sprites = {sid: next(t for t in tags if t[0] == 39 and int.from_bytes(t[1][:2], "little") == sid) for sid in ICON_SPRITES}
    new_defs, x = [], 0
    for season, icon in sorted(icons.items()):
        label = f"{season}season".encode() + b"\0"
        for sid in ICON_SPRITES:
            inner = _tags(sprites[sid][1], 4, len(sprites[sid][1]))
            assert not any(c == 43 and d == label for c, d in inner), f"{season} already in Label.gfx"
            # the '17 frame's shape and its sub-image size
            i = next(k for k, (c, d) in enumerate(inner) if c == 43 and d.startswith(b"17season"))
            place = next(d for c, d in inner[i:] if c == 26)
            shape_id = int.from_bytes(place[3:5], "little")
            sc, shape = defs[shape_id]
            assert sc == 2, sc
            ref = next(defs[b][1] for b in _bitmaps(shape) if b in defs and defs[b][0] == 1008)
            x1, y1, x2, y2 = (int.from_bytes(ref[k:k + 2], "little") for k in (4, 6, 8, 10))
            w, h = x2 - x1, y2 - y1
            fit = icon.copy()
            fit.thumbnail((w, h), Image.LANCZOS)
            cell = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            cell.paste(fit, ((w - fit.width) // 2, (h - fit.height) // 2))
            y = ICON_FREE_Y + (0 if sid == ICON_SPRITES[0] else 48)
            assert atlas.crop((x, y, x + w, y + h)).getextrema()[3] == (0, 0), "atlas space not free"
            _draw(dds, cell, x, y)
            sub, shp = next_id, next_id + 1
            next_id += 2
            new_defs += [[1008, sub.to_bytes(2, "little") + bytes(2) + b"".join(v.to_bytes(2, "little") for v in (x, y, x + w, y + h))],
                         [2, _shape_copy(shape, shp, sub)]]
            frame = [[43, label], [26, bytes([0x03, 1, 0]) + shp.to_bytes(2, "little")], [1, b""]]
            inner = inner[:-1] + frame + inner[-1:]
            nf = int.from_bytes(sprites[sid][1][2:4], "little") + 1
            sprites[sid][1] = sid.to_bytes(2, "little") + nf.to_bytes(2, "little") + _join(inner)
        x += 40
    at = tags.index(sprites[ICON_SPRITES[0]])
    tags[at:at] = new_defs
    body = body[:start] + _join(tags)
    return b"CFX" + gfx[3:4] + (len(body) + 8).to_bytes(4, "little") + zlib.compress(body, 9), bytes(dds)


# --- install / restore -------------------------------------------------------------------------
# The client reads cards from data_0.big data/db2/fifadb.db.db2 and, per UI language, names /
# club names / league names from data/db2/<lang>.db.db2 (PlayerListUtil: "SELECT * FROM names
# WHERE playerid IN" on the ConnectionPool named Localization.LOCALE; a card whose player has
# no name there gets no staticdata, so its info popup stays empty). Each one is the RefPack of
# a Blowfish-encrypted SQLite (extract_fifadb.py). install rewrites them the same way, keeping
# the shipped first 16 encrypted bytes (they never decrypt to the SQLite magic), over the
# shipped entries (tools/re/bigdir.py in place: the game caches the whole archive, and a
# data_0.big 40 MB longer crashed it 5 s into boot). The first install copies data_0.big and
# Label.big to backup/fo4season/; every install starts from those copies and restore puts
# them back. tools/eatrax_song.py edits data_0.big too: after running it, run install again
# (from the copy, so the song is gone).
FIFADB_ENTRY = "data/db2/fifadb.db.db2"
LOCALES = ("chi", "eng", "ind", "kor", "tha", "vie")
ICON_URL = "https://open.api.nexon.com/static/fconline/meta/seasonid.json"


def _originals(game):
    """Put data_0.big and Label.big back as they were before the first install."""
    os.makedirs(BACKUP, exist_ok=True)
    out = []
    for path in (os.path.join(game, "data", "data_0.big"), os.path.join(game, LABEL_BIG)):
        copy = os.path.join(BACKUP, os.path.basename(path))
        if os.path.isfile(copy):
            shutil.copyfile(copy, path)
        else:
            shutil.copyfile(path, copy)
        out.append(path)
    return out


def _sqlite(plain, edit):
    """SQLite bytes after edit(connection) and a VACUUM."""
    tmp = os.path.join(tempfile.gettempdir(), "fo4_season_edit.sqlite")
    open(tmp, "wb").write(plain)
    c = sqlite3.connect(tmp)
    edit(c)
    c.commit()
    c.execute("VACUUM")
    c.close()
    data = open(tmp, "rb").read()
    os.remove(tmp)
    assert len(data) % 8 == 0
    return data


def client_db():
    """gamedata/fifadb.sqlite as the client gets it. Its packed DB has to fit the shipped one's
    place in data_0.big (with the engine DB too, see cmd_install), so the names of players
    without a card (half of each names table; the client reads names from its <lang>.db
    anyway) are left out."""
    def edit(c):
        for t in NAME_TABLES:
            c.execute(f"DELETE FROM {t} WHERE playerid NOT IN (SELECT playerid FROM players)")
    return _sqlite(open(FIFADB, "rb").read(), edit)


NG_ENTRY, NG_META = "data/db/fifa_ng_db.db", "data/db/fifa_ng_db-meta.xml"
ENGINE_COPY = ("height", "weight", "nationality", "preferredfoot")


def engine_db(db, meta):
    """fifa_ng_db (EA DB, tools/re/eadb.py) with a players row for every new player. The 3D
    player (club creation's player view, matches) looks a card up there by spid, then by player
    id ('17 cards have only their player id's row); a player with neither crashed the client.
    The row is a copy of the 2017 player whose generic head build gave him (fo4_heads.json),
    with his own id, height, weight, nationality and foot; rows stay sorted by player id."""
    import struct, eadb
    heads = {int(k): v for k, v in json.load(open(HEADS)).items()}
    m = re.search(r'<table name="players" shortname="(\w+)".*?</table>', meta, re.S)
    fld = {n: (sn, int(lo)) for n, sn, lo in re.findall(r'<field name="(\w+)" shortname="(\w+)"[^>]*rangelow="(-?\d+)"', m.group())}
    base, names, raws = eadb.db_tables(db)
    i = names.index(m.group(1).encode())
    t = eadb.Table(raws[i])
    pk = fld["playerid"][0]
    by = {t.get(r, pk): r for r in t.rows}
    generic = next(r for r in t.rows if t.get(r, fld["headclasscode"][0]) == 1)
    with closing(sqlite3.connect(FIFADB)) as c:
        c.row_factory = sqlite3.Row
        mine = {r["playerid"]: r for r in c.execute("SELECT * FROM players WHERE playerid BETWEEN ? AND ? ORDER BY spid",
                                                    (NEW_PID, NEW_PID + 99999))}
    for pid, r in mine.items():
        row = t.set(by.get(heads.get(pid), generic), pk, pid)
        for name in ENGINE_COPY:
            sn, lo = fld[name]
            v = r[name] - lo
            if 0 <= v < 1 << t.fields[sn][2]:
                row = t.set(row, sn, v)
        by[pid] = row
    t.rows = [by[k] for k in sorted(by)]
    raws[i] = t.raw()
    out, pos = bytearray(db[:base]), 0  # table offsets, sizes and checksums (as tools/eatrax_song.py)
    for j, raw in enumerate(raws):
        struct.pack_into("<I", out, 0x1C + 8 * j, pos)
        pos += len(raw)
    struct.pack_into("<I", out, base - 4, eadb.crc(out[0x18:base - 4]))
    struct.pack_into("<I", out, 8, base + pos)
    struct.pack_into("<I", out, 0x14, eadb.crc(out[:0x14]))
    return bytes(out) + b"".join(raws), len(mine)


def locale_additions():
    """The names rows of the new players for <lang>.db (its clubs are FO3's: build puts the
    players of the others in Rest of the World)."""
    with closing(sqlite3.connect(FIFADB)) as c:
        return c.execute("SELECT playerid, full, short, full_eng, short_eng, jersey FROM nameseng "
                         "WHERE playerid BETWEEN ? AND ?", (NEW_PID, NEW_PID + 99999)).fetchall()


def locale_db(plain_db, names, trim=False):
    """A <lang>.db with the new players' names; trim drops the names of players without a card
    (when the packed DB would not fit its place)."""
    cards = None
    if trim:
        with closing(sqlite3.connect(FIFADB)) as c:
            cards = [r[0] for r in c.execute("SELECT DISTINCT playerid FROM players")]

    def edit(c):
        c.executemany("INSERT OR REPLACE INTO names (playerid, full, short, full_eng, short_eng, jersey) VALUES (?,?,?,?,?,?)", names)
        if cards:
            c.execute("CREATE TEMP TABLE keep (playerid INTEGER PRIMARY KEY)")
            c.executemany("INSERT INTO keep VALUES (?)", [(p,) for p in cards])
            c.execute("DELETE FROM names WHERE playerid NOT IN (SELECT playerid FROM keep)")
    return _sqlite(plain_db, edit)


def _game_running():
    out = os.popen('tasklist /FI "IMAGENAME eq fifazf.exe" /NH').read()
    return "fifazf.exe" in out.lower()


def _icons():
    """{season: RGBA PIL image} of FO4's season badges (downloaded once to gamedata/fo4_icons)."""
    from PIL import Image
    d = os.path.join(ROOT, "gamedata", "fo4_icons")
    os.makedirs(d, exist_ok=True)
    out, meta = {}, None
    for season in CLASSES.values():
        f = os.path.join(d, f"{season}.png")
        if not os.path.exists(f):
            if meta is None:
                req = urllib.request.Request(ICON_URL, headers={"User-Agent": "Mozilla/5.0"})
                meta = {s["seasonId"]: s["seasonImg"] for s in json.load(urllib.request.urlopen(req, timeout=60))}
            req = urllib.request.Request(meta[season], headers={"User-Agent": "Mozilla/5.0"})
            open(f, "wb").write(urllib.request.urlopen(req, timeout=60).read())
        out[season] = Image.open(f).convert("RGBA")
    return out


def _seal(plain_db, shipped):
    """RefPack of plain_db encrypted like the client's DBs, with the shipped first 16 bytes."""
    from refpack import refpack_blocks
    from extract_fifadb import swap32, KEY
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish
    except ImportError:
        from cryptography.hazmat.primitives.ciphers.algorithms import Blowfish
    e = Cipher(Blowfish(KEY), modes.ECB()).encryptor()
    enc = bytearray(swap32(e.update(swap32(plain_db)) + e.finalize()))
    enc[:16] = shipped[:16]
    return refpack_blocks(bytes(enc)), len(enc)


def cmd_install(a):
    import bigdir
    from refpack import refpack
    sys.path.insert(0, ROOT)
    from extract_fifadb import decrypt
    if _game_running():
        raise SystemExit("close the game first (fifazf.exe is running)")
    data0, label = _originals(a.game)
    room = {n: size for n, off, size, usize in bigdir.entries(data0)}
    names = locale_additions()
    files, want = {}, {}
    for entry, make in [(FIFADB_ENTRY, lambda shipped, trim: client_db())] + [
            (f"data/db2/{loc}.db.db2", lambda shipped, trim: locale_db(_plain(shipped), names, trim)) for loc in LOCALES]:
        shipped = bigdir.read(data0, entry)  # inflated, encrypted
        for trim in (False, True):
            plain_db = make(shipped, trim)
            packed, usize = _seal(plain_db, shipped)
            if len(packed) <= room[entry]:
                break
        else:
            raise SystemExit(f"{entry}: {len(packed)} bytes do not fit its {room[entry]} in data_0.big "
                             "(fewer cards: fetch --min-ovr higher)")
        print(f"{entry}: {usize / 1e6:.2f} MB -> {len(packed) / 1e6:.2f} MB, slot {room[entry] / 1e6:.2f} MB"
              + (" (cardless names left out)" if trim else ""), flush=True)
        files[entry], want[entry] = (packed, usize), plain_db
    # the engine DB: its own slot if it still fits, else the space fifadb left free in its slot
    ng, n_new = engine_db(bigdir.read(data0, NG_ENTRY), bigdir.read(data0, NG_META).decode("utf-8", "replace"))
    packed = refpack(ng)
    assert len(packed) < len(ng)  # stored or literal-only DB entries hang the boot (eatrax_song.py)
    at = {}
    if len(packed) > room[NG_ENTRY]:
        off = {n: o for n, o, s, u in bigdir.entries(data0)}[FIFADB_ENTRY]
        at[NG_ENTRY] = -(-(off + len(files[FIFADB_ENTRY][0])) // 0x800) * 0x800
        if at[NG_ENTRY] + len(packed) > off + room[FIFADB_ENTRY]:
            raise SystemExit(f"{NG_ENTRY}: {len(packed)} bytes fit neither its slot nor fifadb's free space")
    print(f"{NG_ENTRY}: {n_new} new players, {len(packed) / 1e6:.2f} MB"
          + (" (in fifadb's slot)" if at else f", slot {room[NG_ENTRY] / 1e6:.2f} MB"), flush=True)
    files[NG_ENTRY] = (packed, len(ng))
    bigdir.patch(data0, files, in_place=True, at=at)
    assert bigdir.read(data0, NG_ENTRY) == ng
    gfx, dds = label_with_icons(bigdir.read(label, LABEL_GFX), bigdir.read(label, LABEL_DDS), _icons())
    bigdir.patch(label, {LABEL_GFX: gfx, LABEL_DDS: (refpack(dds), len(dds))})
    # check what the client will read
    for entry, plain_db in want.items():
        assert bytes(decrypt(bigdir.read(data0, entry))[16:]) == plain_db[16:], entry
    assert os.path.getsize(data0) == os.path.getsize(os.path.join(BACKUP, "data_0.big"))
    print(f"installed into {a.game}: {len(names)} new names, season icons "
          f"{', '.join(SEASON_NAMES[s] for s in CLASSES.values())}")


def _plain(shipped):
    from extract_fifadb import decrypt
    db = decrypt(bytes(shipped))
    db[:16] = b"SQLite format 3\x00"
    return bytes(db)


def cmd_restore(a):
    if _game_running():
        raise SystemExit("close the game first (fifazf.exe is running)")
    if not os.path.isfile(os.path.join(BACKUP, "data_0.big")):
        raise SystemExit("nothing to restore (no backup/fo4season)")
    _originals(a.game)
    c = sqlite3.connect(FIFADB)
    seasons = tuple(CLASSES.values())
    for t in ("players", *PERM_TABLES):
        c.execute(f"DELETE FROM {t} WHERE spid / 1000000 IN ({','.join('?' * len(seasons))})", seasons)
    for t in NAME_TABLES:
        c.execute(f"DELETE FROM {t} WHERE playerid BETWEEN ? AND ?", (NEW_PID, NEW_PID + 99999))
    c.commit()
    print("client files restored; the FO4 seasons are out of gamedata/fifadb.sqlite")


def cmd_selftest(a=None):
    d = nuxt('<script>window.__NUXT__=(function(a,b){return {x:[a,b,"c\\u002Fd"],y:{z:void 0,n:-1.5}}}(1,"s"));</script>')
    assert d == {"x": [1, "s", "c/d"], "y": {"z": None, "n": -1.5}}, d
    assert nuxt('window.__NUXT__={a:[]};') == {"a": []}
    assert _same_name("Lionel Messi", "Lionel Messi") > _same_name("Lionel Messi", "Lionel Gamba") >= 0
    assert _same_name("Lionel Messi", "Leandro Gamba") < 0.85 <= _same_name("Erling Haaland", "Erling Haland")
    assert _same_name("Rodri", "Rodrigo Hernandez Cascante") >= 0.85 > _same_name("Harry Kane", "Herbie Kane") - 1
    # trait1 bits as the client's PLAYER_TRAITS (Messi '17: finesse shot, long shot, speed dribbler, playmaker)
    assert sum(1 << FO3_TRAITS.index(t) for t in ("finesse-shot", "long-shot-taker", "speed-dribbler", "play-maker")) == 466944
    if os.path.exists(FIFADB):  # the Style rules against FO3's own 2017 cards
        with closing(sqlite3.connect(FIFADB)) as c:
            c.row_factory = sqlite3.Row
            rows = [dict(r) for r in c.execute("SELECT * FROM players WHERE spid / 1000000 = 88")]
        hit = sum(badges(r) == r["badges"] for r in rows)
        assert hit >= 0.98 * len(rows), (hit, len(rows))
        print(f"Style rules match {hit}/{len(rows)} 2017 cards exactly")
    px = [(0, 230, 100, 255)] * 8 + [(60, 64, 70, 255)] * 7 + [(0, 0, 0, 0)]
    b = _bc3(px)
    assert len(b) == 16 and b[0] == 255 and b[1] == 0
    print("fo4_season selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--min-ovr", type=int, default=72, help="lowest rating fifaaddict shows in its search")
    f.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "fo4_cache"))
    sub.add_parser("collect")
    sub.add_parser("import").add_argument("file")
    sub.add_parser("build")
    sub.add_parser("selftest")
    for name in ("install", "restore"):
        sub.add_parser(name).add_argument("--game", default=r"D:\FO3ID\32795")
    a = ap.parse_args()
    {"fetch": cmd_fetch, "collect": cmd_collect, "import": cmd_import, "build": cmd_build,
     "install": cmd_install, "restore": cmd_restore, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
