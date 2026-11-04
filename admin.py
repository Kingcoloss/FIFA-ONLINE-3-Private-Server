"""Admin page for the FO3ID private server: http://127.0.0.1:8088/ (localhost only).

Started by http_config.py in its own thread (env FO3_ADMIN_PORT, default 8088, 0 = off). The
page (admin/index.html, Indonesian or English) calls the JSON API below, which reads and edits
gamedata/state.json through http_config's own helpers: EP, players (add / remove / grade / Tim
inti-Cadangan), packs, Bag gifts, the daily login reward table, scout cooldowns, the server log,
and the Shop catalog (gamedata/shop.json: every tab, new packs / items / packages, prices, hidden
products; issue #10) with the client's own shop icons.

Guards: only 127.0.0.1 / localhost may connect, and every change must be a POST carrying the
X-FO3-Admin header (a page on another origin cannot send it without a CORS preflight this server
never grants). ponytail: no login; anyone on this PC can use it, add a password if that matters.
"""
import http.server
import json
import os
import re
import threading
import time
import urllib.parse
from contextlib import closing

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "admin", "index.html")
POS_NAMES = "GK SW RWB RB RCB CB LCB LB LWB RDM CDM LDM RM RCM CM LCM LM RAM CAM LAM RF CF LF RW RS ST LS LW".split()
API = {}
READ_ONLY = {"summary", "players", "search", "packs", "daily", "log", "shop"}  # the rest must be POST + header
hc = None  # the http_config module, set by start() (or by tests)


class AdminError(Exception):
    """A message for the page: AdminError("Indonesian", "English")."""

    def text(self, lang):
        return self.args[1] if lang == "en" and len(self.args) > 1 else self.args[0]


def api(name):
    def reg(fn):
        API[name] = fn
        return fn
    return reg


def coach(st):
    return hc.my_coach(st)


def team(st):
    return st["teams"][str(hc._default_slot(st))]


def names(spids):
    """{spid: player name} from fifadb."""
    spids = sorted({int(s) for s in spids})
    if not spids:
        return {}
    with closing(hc._db()) as c:
        return {s: n for s, n in c.execute(
            f"""SELECT p.spid, COALESCE(n.full_eng, n.full, n.short) FROM players p JOIN nameseng n ON n.playerid = p.playerid
                WHERE p.spid IN ({','.join('?' * len(spids))})""", spids)}


def player(st, pid):
    p = next((x for x in team(st)["players"] if hc.iid(x) == str(pid)), None)
    if p is None:
        raise AdminError("pemain tidak ditemukan", "player not found")
    return p


def as_int(v, lo, hi, what):
    """v as an int in lo..hi; what = a field name, or (Indonesian, English)."""
    wid, wen = what if isinstance(what, tuple) else (what, what)
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise AdminError(f"{wid} harus angka", f"{wen} must be a number")
    if not lo <= v <= hi:
        raise AdminError(f"{wid} harus {lo}..{hi}", f"{wen} must be {lo}..{hi}")
    return v


@api("summary")
def summary(p):
    st = hc._state(); c = coach(st); slot = hc._default_slot(st)
    d = c.get("daily") or {"last": "", "streak": 0, "total": 0}
    return {"coach": {"name": c.get("name"), "ep": c.get("ep", hc.START_EP), "teamid": c.get("teamid")},
            "vip_until": time.strftime("%Y-%m-%d", time.gmtime(hc.VIP_UNTIL / 1000)), "igr": True,
            "players": len(team(st)["players"]), "max_players": hc.MAX_PLAYERS,
            "team2": sum(1 for x in team(st)["players"] if x.get("team2")),
            "packs": sum(i["remains"] for i in c.get("items", [])), "bag": len(c.get("bag", [])),
            "daily": {**d, "today": hc.today_wib(), "granted_today": d.get("last") == hc.today_wib()},
            "scouts": hc.coach_scouters(st, slot),
            "server_time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + hc.WIB)) + " WIB"}


@api("players")
def players(p):
    st = hc._state(); t = team(st)
    pos = {str(s.get("id") or s["spid"]): s["pos"] for s in t["squad"]["positions"]}
    nm = names(x["spid"] for x in t["players"])
    out = []
    for x in t["players"]:
        i, g = hc.iid(x), hc.grade_of(x)
        out.append({"id": i, "spid": x["spid"], "name": nm.get(x["spid"], "?"), "season": x["spid"] // 1000000,
                    "ovr": hc.card_ovr(x["spid"]) + hc.GRADE_BOOST[g], "grade": g, "price": hc.card_price(x["spid"], g),
                    "role": "MAIN" if pos.get(i, 99) < hc.POS_SUB else "SUB" if i in pos else "RES",
                    "team2": bool(x.get("team2"))})
    return {"players": out}


@api("search")
def search(p):
    q = str(p.get("q") or "").strip()
    if len(q) < 2:
        return {"rows": []}
    with closing(hc._db()) as c:
        rows = c.execute(f"""SELECT p.spid, COALESCE(n.full_eng, n.full, n.short), {hc.POSOVR}, p.preferredposition1
                             FROM players p JOIN nameseng n ON n.playerid = p.playerid
                             WHERE n.full LIKE ?1 OR n.short LIKE ?1 OR n.full_eng LIKE ?1 OR n.short_eng LIKE ?1
                             ORDER BY 3 DESC LIMIT 60""", (f"%{q}%",)).fetchall()
    return {"rows": [{"spid": s, "name": n, "season": s // 1000000, "ovr": o, "pos": POS_NAMES[pp] if 0 <= pp < 28 else "?",
                      "market": hc.on_market(s), "price": hc.card_price(s)} for s, n, o, pp in rows]}


@api("packs")
def packs(p):
    return {"packs": [{"itemid": i, "name": n, "price": hc.pack_price(i)} for i, (n, _) in hc.PACKS.items()]}


@api("ep")
def set_ep(p):
    st = hc._state(); c = coach(st)
    if "set" in p:
        c["ep"] = as_int(p["set"], 0, 10 ** 13, "EP")
    else:
        hc.add_ep(st, as_int(p.get("add"), -10 ** 13, 10 ** 13, "EP"))
        c["ep"] = max(0, c["ep"])
    hc._save(st)
    return {"ep": c["ep"]}


@api("player_add")
def player_add(p):
    st = hc._state(); t = team(st)
    spid, grade = as_int(p.get("spid"), 1, 10 ** 9, "spid"), as_int(p.get("grade", 1), 1, 10, "grade")
    if not names([spid]):
        raise AdminError("spid tidak ada di database", "no such spid in the database")
    if len(t["players"]) >= hc.MAX_PLAYERS:
        raise AdminError(f"klub penuh ({hc.MAX_PLAYERS} pemain)", f"the club is full ({hc.MAX_PLAYERS} players)")
    x = hc.add_player(t, spid, grade)
    hc._save(st)
    return {"id": hc.iid(x)}


@api("player_grade")
def player_grade(p):
    st = hc._state()
    player(st, p.get("id"))["grade"] = as_int(p.get("grade"), 0, 10, "grade")
    hc._save(st)
    return {"ok": True}


@api("player_remove")
def player_remove(p):
    st = hc._state(); t = team(st); x = player(st, p.get("id"))
    if hc.in_squad(t, x):
        raise AdminError("pemain ada di 18 skuad; ganti dulu di Formasi",
                         "the player is in the squad's 18; swap him out in Formasi first")
    hc.remove_player(t, x)
    hc._save(st)
    return {"ok": True}


@api("player_team")
def player_team(p):
    st = hc._state(); t = team(st); x = player(st, p.get("id"))
    if p.get("team") == "second":
        if hc.in_squad(t, x):
            raise AdminError("pemain 18 skuad tetap di Tim inti", "players in the squad's 18 stay in Tim inti")
        x["team2"] = True
    else:
        x.pop("team2", None)
    hc._save(st)
    return {"ok": True}


@api("team2_clear")
def team2_clear(p):
    """Every Tim Cadangan card back to Tim inti (they went there automatically while Tim inti held 36)."""
    st = hc._state(); n = 0
    for x in team(st)["players"]:
        n += bool(x.pop("team2", None))
    hc._save(st)
    return {"moved": n}


def give_pack(st, itemid, count):
    inv = coach(st).setdefault("items", [])
    stack = next((i for i in inv if i["itemid"] == itemid), None)
    if stack is None:
        stack = {"_id": hc.new_iid(), "itemid": itemid, "remains": 0}
        inv.append(stack)
    stack["remains"] += count


@api("give_pack")
def api_give_pack(p):
    st = hc._state()
    itemid = as_int(p.get("itemid"), 1, 10 ** 10, "pack")
    if itemid not in hc.PACKS and itemid not in hc.ITEMS:
        raise AdminError("pak atau item tidak dikenal", "unknown pack or item")
    give_pack(st, itemid, as_int(p.get("count", 1), 1, 999, ("jumlah", "count")))
    hc._save(st)
    return {"ok": True}


@api("bag_send")
def bag_send(p):
    """A gift in the Bag (Item saya > Items): EP and/or a pack and/or a player."""
    st = hc._state()
    items = hc.reward_items({"ep": as_int(p.get("ep") or 0, 0, 10 ** 12, "EP"),
                             "pack": as_int(p["pack"], 1, 10 ** 10, "pack") if p.get("pack") else None,
                             "count": as_int(p.get("count") or 1, 1, 999, ("jumlah", "count"))})
    if any(i["itemid"] != hc.EP_ITEM and i["itemid"] not in hc.PACKS for i in items):
        raise AdminError("pak tidak dikenal", "unknown pack")
    players_ = []
    if p.get("spid"):
        spid = as_int(p["spid"], 1, 10 ** 9, "spid")
        if not names([spid]):
            raise AdminError("spid tidak ada di database", "no such spid in the database")
        players_ = [{"spid": spid, "grade": as_int(p.get("grade") or 1, 1, 10, "grade")}]
    if not items and not players_:
        raise AdminError("isi EP, pak, atau pemain", "fill in EP, a pack or a player")
    e = hc.bag_add(st, str(p.get("title") or "Hadiah admin")[:60], items, players_, msg="Hadiah dari admin server.")
    hc._save(st)
    return {"id": e["_id"]}


@api("daily")
def daily(p):
    st = hc._state()
    return {"table": hc.daily_table(), "status": coach(st).get("daily") or {"last": "", "streak": 0, "total": 0},
            "today": hc.today_wib(), "file": os.path.relpath(hc.DAILY_FILE, HERE)}


@api("daily_set")
def daily_set(p):
    table = []
    for i, r in enumerate(p.get("table") or []):
        d = (f"hari {i + 1}", f"day {i + 1}")
        ep = as_int(r.get("ep") or 0, 0, 10 ** 12, (f"EP {d[0]}", f"EP of {d[1]}"))
        pack = as_int(r["pack"], 1, 10 ** 10, (f"pak {d[0]}", f"pack of {d[1]}")) if r.get("pack") else None
        if pack is not None and pack not in hc.PACKS:
            raise AdminError(f"pak {d[0]} tidak dikenal", f"unknown pack on {d[1]}")
        if not ep and pack is None:
            raise AdminError(f"{d[0]} kosong", f"{d[1]} is empty")
        table.append({**({"ep": ep} if ep else {}),
                      **({"pack": pack, "count": as_int(r.get("count") or 1, 1, 99, ("jumlah", "count"))} if pack else {})})
    if not 1 <= len(table) <= 31:
        raise AdminError("tabel harus 1..31 hari", "the table must have 1..31 days")
    with open(hc.DAILY_FILE, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1)
    return {"table": table}


@api("daily_reset")
def daily_reset(p):
    st = hc._state()
    coach(st)["daily"] = {"last": "", "streak": 0, "total": 0}
    hc._save(st)
    return {"ok": True}


@api("daily_grant")
def daily_grant(p):
    """Give the next day's reward now (as if logging in tomorrow), for testing."""
    st = hc._state()
    d = coach(st).setdefault("daily", {"last": "", "streak": 0, "total": 0})
    if d["last"] == hc.today_wib():
        d["last"] = hc.today_wib(time.time() - 86400)  # keep the streak going
    e = hc.daily_login(st)
    hc._save(st)
    return {"title": e["title"] if e else None}


@api("scouts_reset")
def scouts_reset(p):
    st = hc._state()
    coach(st)["scout_used"] = {}
    hc._save(st)
    return {"ok": True}


@api("log")
def log(p):
    n = as_int(p.get("n", 80), 1, 1000, "n")
    try:
        with open(hc.LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
    except OSError:
        lines = []
    return {"lines": [ln.rstrip("\n")[:300] for ln in lines]}


# --- Shop (gamedata/shop.json, format in http_config's "Shop catalog" block) ----------------------

def icon_dir():
    return os.path.join(hc.ASSETS, "externalAssets", "shop")


def shop_icons():
    """The client's own shop images (externalAssets/shop/<name>.png), the icons a product can use."""
    try:
        return sorted(f[:-4] for f in os.listdir(icon_dir()) if f.endswith(".png"))
    except OSError:
        return []


def product_tab(kind, itemid):
    return {"packs": "PLAYERPACK", "items": "USE", "monthly": "MONTHLYPACK"}.get(kind) or (
        "CHAINED" if itemid in hc.CHAIN_STEPS else "PACKAGE")


@api("shop")
def shop(p):
    cfg = hc.shop_config()
    prices = cfg.get("prices") or {}
    out = []
    for kind, (table, _, to) in hc.SHOP_KINDS.items():
        base, custom = hc._SHOP_BASE[kind], cfg.get(kind) or {}
        for i, entry in table.items():
            d = hc.item_def(i)
            out.append({"kind": kind, "itemid": i, "tab": product_tab(kind, i), "name": d["name"],
                        "icon": str(d.get("bundleicon") or d.get("itemicon") or i),
                        "price": d["bunches"][0]["price"], "fixed": prices.get(str(i)), "hidden": i in hc.SHOP_HIDDEN,
                        "builtin": i in base, "custom": str(i) in custom, "def": to(entry)})
    lists = {k: list(getattr(hc, n)) for k, n in (("new", "SHOP_NEW"), ("best", "SHOP_BEST"), ("mp", "MP_SHOP"),
                                                  ("special", "SPECIAL"))}
    lists["chained"] = [list(s) for s in hc.CHAINED.values()]
    return {"free": hc.SHOP_FREE, "products": out, "lists": lists, "icons": shop_icons(),
            "item_types": list(hc.SHOP_ITEM_TYPES), "positions": list(hc.POSITIONS),
            "seasons": [{"code": c, "label": label} for label, codes in hc.tc_seasons() for c in codes],
            "ep_item": hc.EP_ITEM, "es_item": hc.ES_ITEM,
            "file": os.path.relpath(hc.SHOP_FILE, HERE) if os.path.splitdrive(hc.SHOP_FILE)[0] == os.path.splitdrive(HERE)[0]
            else hc.SHOP_FILE}


def save_shop(cfg):
    """Write gamedata/shop.json and rebuild the Shop; a pack without a single card is refused."""
    old = hc.shop_config()
    hc.apply_shop(cfg)
    empty = [i for i in (cfg.get("packs") or {}) if not hc.pack_pool(int(i))]
    if empty:
        hc.apply_shop(old)
        raise AdminError(f"pak {empty[0]} tidak berisi kartu satu pun", f"pack {empty[0]} holds no card at all")
    os.makedirs(os.path.dirname(hc.SHOP_FILE), exist_ok=True)
    with open(hc.SHOP_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)


def known(i, *kinds):
    """itemid i is a product of one of kinds (packs / items / packages / monthly), or EP / ES."""
    i = int(i)
    return any(i in hc.SHOP_KINDS[k][0] for k in kinds if k in hc.SHOP_KINDS) or (
        "ep" in kinds and i in (hc.EP_ITEM, hc.ES_ITEM))


def text(v, what, n=40):
    v = str(v or "").strip()
    if not 1 <= len(v) <= n:
        raise AdminError(f"{what[0]} harus 1..{n} huruf", f"{what[1]} must be 1..{n} characters")
    return v


def icon_of(v, required=True):
    v = str(v or "").strip()
    if v and v not in shop_icons():
        raise AdminError(f"ikon {v} tidak ada di client", f"icon {v} is not in the client")
    if required and not v:
        raise AdminError("pilih ikon", "pick an icon")
    return v


def rows_of(rows, what, kinds, lo=1, hi=10):
    """[[itemid, count]] with every itemid known."""
    out = []
    for r in rows or []:
        i = as_int(r[0], 1, 10 ** 10, ("itemid", "itemid"))
        if not known(i, *kinds):
            raise AdminError(f"{what[0]}: item {i} tidak dikenal", f"{what[1]}: unknown item {i}")
        out.append([i, as_int(r[1], 1, 10 ** 12, ("jumlah", "count"))])
    if not lo <= len(out) <= hi:
        raise AdminError(f"{what[0]} harus {lo}..{hi} baris", f"{what[1]} must have {lo}..{hi} rows")
    return out


def check_def(kind, d, itemid):
    """A clean shop.json entry from the page's form, or AdminError."""
    name = text(d.get("name"), ("nama", "name"))
    desc = str(d.get("description") or "").strip()[:200]
    if kind == "packs":
        seasons = sorted({as_int(s, 0, 99, ("musim", "season")) for s in d.get("seasons") or []})
        pos = str(d.get("pos") or "")
        if pos and pos not in hc.POSITIONS:
            raise AdminError("posisi tidak dikenal", "unknown position")
        opt = lambda k, lo, hi, w: as_int(d[k], lo, hi, w) if d.get(k) not in (None, "", 0, "0") else None
        return {"name": name, "icon": icon_of(d.get("icon"), False), "seasons": seasons, "all": bool(d.get("all")),
                "top": opt("top", 1, 100000, ("top", "top")), "ovr": opt("ovr", 40, 130, ("OVR", "OVR")),
                "grade": opt("grade", 1, 10, ("grade", "grade")), "pos": pos or None,
                "league": opt("league", 1, 10 ** 6, ("liga", "league"))}
    if kind == "items":
        t = str(d.get("type") or "")
        if t not in hc.SHOP_ITEM_TYPES:
            raise AdminError("jenis item tidak dikenal", "unknown item type")
        out = {"name": name, "icon": icon_of(d.get("icon")), "type": t, "description": desc}
        if t == "EP_LOTTERY":
            lo, hi = (as_int(x, 0, 10 ** 12, "EP") for x in (d.get("ep") or [0, 0]))
            if not 0 < lo <= hi:
                raise AdminError("EP minimal harus > 0 dan <= maksimal", "EP min must be > 0 and <= max")
            out["ep"] = [lo, hi]
        elif t == "ITEM_LOTTERY":
            prizes = []
            for w, prize in d.get("prizes") or []:
                w = as_int(w, 1, 1000, ("bobot", "weight"))
                if isinstance(prize, dict):
                    prizes.append([w, {"ep": as_int(prize.get("ep"), 1, 10 ** 12, "EP")}])
                elif int(prize) != itemid and known(prize, "packs", "items"):
                    prizes.append([w, int(prize)])
                else:
                    raise AdminError(f"hadiah {prize} tidak dikenal", f"unknown prize {prize}")
            if not 1 <= len(prizes) <= 10:  # the box screen shows up to 10 (cardCandidate0..9)
                raise AdminError("hadiah harus 1..10", "prizes must be 1..10")
            out["prizes"] = prizes
        elif t == "ENHANCEMENT_BOOST":
            out["boost"] = as_int(round(float(d.get("boost") or 0) * 100), 1, 100, ("boost %", "boost %")) / 100
        return out
    if kind == "packages":
        return {"name": name, "icon": icon_of(d.get("icon")), "description": desc,
                "contents": rows_of(d.get("contents"), ("isi", "contents"), ("packs", "items", "ep"))}
    if kind == "monthly":
        return {"name": name, "icon": icon_of(d.get("icon")), "description": desc,
                "days": as_int(d.get("days"), 1, 365, ("hari", "days")),
                "now": rows_of(d.get("now"), ("isi langsung", "items now"), ("packs", "items", "ep"), 0),
                "daily": rows_of(d.get("daily"), ("isi harian", "daily items"), ("packs", "items", "ep"))}
    raise AdminError("jenis produk tidak dikenal", "unknown product kind")


def kind_of(p):
    k = str(p.get("kind") or "")
    if k not in hc.SHOP_KINDS:
        raise AdminError("jenis produk tidak dikenal", "unknown product kind")
    return k


@api("shop_save")
def shop_save(p):
    """Create (no itemid) or change a product; a built-in one is replaced by the saved copy."""
    kind = kind_of(p); cfg = hc.shop_config()
    table = hc.SHOP_KINDS[kind][0]
    if p.get("itemid"):
        itemid = as_int(p["itemid"], 1, 10 ** 10, "itemid")
        if itemid not in table:
            raise AdminError("produk tidak ditemukan", "product not found")
    else:
        taken = set().union(*(t for t, _, _ in hc.SHOP_KINDS.values()))
        itemid = next(i for i in range(hc.SHOP_ID_BASE[kind] + 1, 10 ** 10) if i not in taken)
    cfg.setdefault(kind, {})[str(itemid)] = check_def(kind, p.get("def") or {}, itemid)
    save_shop(cfg)
    return {"itemid": itemid}


def in_use(itemid):
    """Where another product still uses itemid (prizes, package contents, monthly items)."""
    for i, (_, _, _, eff, _) in hc.ITEMS.items():
        if any(prize == itemid for _, prize in eff.get("prizes", [])):
            return i
    for i, (_, _, contents, _) in hc.PACKAGES.items():
        if any(c == itemid for c, _ in contents):
            return i
    for i, (_, _, _, now, daily, _) in hc.MONTHLY.items():
        if any(c == itemid for c, _ in now + daily):
            return i


@api("shop_delete")
def shop_delete(p):
    """Drop a product's saved entry: a built-in one goes back to the original, a new one is gone."""
    kind = kind_of(p); cfg = hc.shop_config()
    itemid = as_int(p.get("itemid"), 1, 10 ** 10, "itemid")
    if str(itemid) not in (cfg.get(kind) or {}):
        raise AdminError("produk ini tidak diubah", "this product was not changed")
    if itemid not in hc._SHOP_BASE[kind] and (user := in_use(itemid)):
        raise AdminError(f"masih dipakai oleh {user}", f"still used by {user}")
    del cfg[kind][str(itemid)]
    if itemid not in hc._SHOP_BASE[kind]:  # gone: out of the lists, prices and hidden too
        cfg.get("prices", {}).pop(str(itemid), None)
        cfg["hidden"] = [i for i in cfg.get("hidden", []) if i != itemid]
        lists = cfg.get("lists") or {}
        for k, v in list(lists.items()):
            lists[k] = [[i for i in c if i != itemid] for c in v] if k == "chained" else [i for i in v if i != itemid]
    save_shop(cfg)
    return {"ok": True}


def product_exists(itemid):
    return any(itemid in t for t, _, _ in hc.SHOP_KINDS.values())


@api("shop_price")
def shop_price(p):
    """A fixed price for one (also while the Shop is free; 0 = free), or none (null) = the default."""
    cfg = hc.shop_config(); itemid = as_int(p.get("itemid"), 1, 10 ** 10, "itemid")
    if not product_exists(itemid):
        raise AdminError("produk tidak ditemukan", "product not found")
    prices = cfg.setdefault("prices", {})
    if p.get("price") in (None, ""):
        prices.pop(str(itemid), None)
    else:
        prices[str(itemid)] = as_int(p["price"], 0, 10 ** 12, ("harga", "price"))
    save_shop(cfg)
    return {"ok": True}


@api("shop_hide")
def shop_hide(p):
    cfg = hc.shop_config(); itemid = as_int(p.get("itemid"), 1, 10 ** 10, "itemid")
    if not product_exists(itemid):
        raise AdminError("produk tidak ditemukan", "product not found")
    hidden = [i for i in cfg.get("hidden", []) if i != itemid]
    cfg["hidden"] = hidden + ([itemid] if p.get("hidden") else [])
    save_shop(cfg)
    return {"ok": True}


@api("shop_free")
def shop_free(p):
    cfg = hc.shop_config(); cfg["free"] = bool(p.get("free"))
    save_shop(cfg)
    return {"free": hc.SHOP_FREE}


@api("shop_lists")
def shop_lists(p):
    """Rekomendasi (new, best), MP Shop (mp), Bonus spesial (special), Paket berantai (chained)."""
    cfg = hc.shop_config(); lists = {}
    kinds = {"new": ("packs", "items", "packages", "monthly"), "best": ("packs", "items", "packages", "monthly"),
             "mp": ("packs", "items"), "special": ("packs", "items", "packages")}
    for k, v in (p.get("lists") or {}).items():
        if k in kinds:
            ids = [as_int(i, 1, 10 ** 10, "itemid") for i in v]
            bad = next((i for i in ids if not known(i, *kinds[k])), None)
            if bad is not None:
                raise AdminError(f"{k}: item {bad} tidak cocok di sini", f"{k}: item {bad} does not fit here")
            lists[k] = list(dict.fromkeys(ids))
        elif k == "chained":
            chains = [[as_int(i, 1, 10 ** 10, "itemid") for i in c] for c in v if c]
            if any(not known(i, "packages") for c in chains for i in c):
                raise AdminError("paket berantai hanya berisi paket", "a chained package holds packages only")
            lists[k] = chains
    cfg["lists"] = {**(cfg.get("lists") or {}), **lists}
    save_shop(cfg)
    return {"ok": True}


class Admin(http.server.BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _route(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if self.client_address[0] not in ("127.0.0.1", "::1") or host not in ("127.0.0.1", "localhost", "[::1]"):
            return self._send(403, b"forbidden", "text/plain")
        url = urllib.parse.urlparse(self.path)
        if url.path in ("/", "/index.html"):
            with open(PAGE, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        m = re.fullmatch(r"/icon/([A-Za-z0-9_]+)\.png", url.path)  # the client's shop icons
        if m:
            f = os.path.join(icon_dir(), m.group(1) + ".png")
            if not os.path.isfile(f):
                return self._send(404, b"", "image/png")
            with open(f, "rb") as fh:
                return self._send(200, fh.read(), "image/png")
        name = url.path[len("/api/"):] if url.path.startswith("/api/") else ""
        fn = API.get(name)
        if fn is None:
            return self._send(404, b'{"error": "not found"}')
        if name not in READ_ONLY and (self.command != "POST" or self.headers.get("X-FO3-Admin") != "1"):
            return self._send(403, b'{"error": "changes need POST with the X-FO3-Admin header"}')
        params = dict(urllib.parse.parse_qsl(url.query))
        n = int(self.headers.get("Content-Length") or 0)
        try:
            if n:
                params.update(json.loads(self.rfile.read(n) or b"{}"))
            with hc.STATE_LOCK:  # same lock as the game's requests
                out = fn(params)
        except AdminError as e:
            out = {"error": e.text(self.headers.get("X-FO3-Lang"))}
        except Exception as e:  # keep the page usable; the detail shows in its message bar
            out = {"error": f"{type(e).__name__}: {e}"}
        self._send(200, json.dumps(out).encode())

    do_GET = _route
    do_POST = _route

    def log_message(self, *a):
        pass


def start(module, port):
    """Serve the admin page on 127.0.0.1:<port> in a daemon thread."""
    global hc
    hc = module
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Admin)
    threading.Thread(target=srv.serve_forever, daemon=True, name="admin").start()
    return srv
