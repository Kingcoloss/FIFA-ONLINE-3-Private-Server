"""Admin page for the FO3ID private server: http://127.0.0.1:8088/ (localhost only).

Started by http_config.py in its own thread (env FO3_ADMIN_PORT, default 8088, 0 = off). The
page (admin/index.html; its words come from the I18N tables at the end of this file, one per
language, and the page has a language switch) calls the JSON API below, which reads and edits
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
READ_ONLY = {"summary", "players", "search", "packs", "daily", "match_rewards", "log", "shop"}  # the rest must be POST + header
hc = None  # the http_config module, set by start() (or by tests)


def tr(lang, key, *args):
    """The I18N text of key in lang (Indonesian for an unknown lang or key) with {0}.. filled in;
    a tuple arg is (key, *args) of a nested text, anything else goes in as it is."""
    tb = I18N.get(lang) or I18N["id"]
    s = tb.get(key) or I18N["id"].get(key) or key
    return s.format(*(tr(lang, *a) if isinstance(a, tuple) else a for a in args))


class AdminError(Exception):
    """A message for the page: AdminError(key, *args), translated by tr()."""

    def text(self, lang):
        return tr(lang, *self.args)


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
        raise AdminError("e_player_missing")
    return p


def rel(path):
    """A settings file's path for the page: relative to the server folder when on its drive."""
    return os.path.relpath(path, HERE) if os.path.splitdrive(path)[0] == os.path.splitdrive(HERE)[0] else path


def as_int(v, lo, hi, what):
    """v as an int in lo..hi; what = a field name, or (I18N key,) of the page's label for it."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise AdminError("e_number", what)
    if not lo <= v <= hi:
        raise AdminError("e_range", what, lo, hi)
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
    spid, grade = as_int(p.get("spid"), 1, 10 ** 9, "spid"), as_int(p.get("grade", 1), 1, 10, ("grade",))
    if not names([spid]):
        raise AdminError("e_no_spid")
    if len(t["players"]) >= hc.MAX_PLAYERS:
        raise AdminError("e_club_full", hc.MAX_PLAYERS)
    x = hc.add_player(t, spid, grade)
    hc._save(st)
    return {"id": hc.iid(x)}


@api("player_grade")
def player_grade(p):
    st = hc._state()
    player(st, p.get("id"))["grade"] = as_int(p.get("grade"), 0, 10, ("grade",))
    hc._save(st)
    return {"ok": True}


@api("player_remove")
def player_remove(p):
    st = hc._state(); t = team(st); x = player(st, p.get("id"))
    if hc.in_squad(t, x):
        raise AdminError("e_in_squad")
    hc.remove_player(t, x)
    hc._save(st)
    return {"ok": True}


@api("player_team")
def player_team(p):
    st = hc._state(); t = team(st); x = player(st, p.get("id"))
    if p.get("team") == "second":
        if hc.in_squad(t, x):
            raise AdminError("e_squad_first")
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
    itemid = as_int(p.get("itemid"), 1, 10 ** 10, ("pack",))
    if itemid not in hc.PACKS and itemid not in hc.ITEMS:
        raise AdminError("e_unknown_item")
    give_pack(st, itemid, as_int(p.get("count", 1), 1, 999, ("count",)))
    hc._save(st)
    return {"ok": True}


@api("bag_send")
def bag_send(p):
    """A gift in the Bag (Item saya > Items): EP and/or a pack and/or a player."""
    st = hc._state()
    items = hc.reward_items({"ep": as_int(p.get("ep") or 0, 0, 10 ** 12, "EP"),
                             "pack": as_int(p["pack"], 1, 10 ** 10, ("pack",)) if p.get("pack") else None,
                             "count": as_int(p.get("count") or 1, 1, 999, ("pack_count",))})
    if any(i["itemid"] != hc.EP_ITEM and i["itemid"] not in hc.PACKS for i in items):
        raise AdminError("e_unknown_pack")
    players_ = []
    if p.get("spid"):
        spid = as_int(p["spid"], 1, 10 ** 9, "spid")
        if not names([spid]):
            raise AdminError("e_no_spid")
        players_ = [{"spid": spid, "grade": as_int(p.get("grade") or 1, 1, 10, ("grade",))}]
    if not items and not players_:
        raise AdminError("e_gift_empty")
    e = hc.bag_add(st, str(p.get("title") or "Hadiah admin")[:60], items, players_, msg="Hadiah dari admin server.")
    hc._save(st)
    return {"id": e["_id"]}


@api("daily")
def daily(p):
    st = hc._state()
    return {"table": hc.daily_table(), "status": coach(st).get("daily") or {"last": "", "streak": 0, "total": 0},
            "today": hc.today_wib(), "file": rel(hc.DAILY_FILE)}


@api("daily_set")
def daily_set(p):
    table = []
    for i, r in enumerate(p.get("table") or []):
        try:
            ep = as_int(r.get("ep") or 0, 0, 10 ** 12, "EP")
            pack = as_int(r["pack"], 1, 10 ** 10, ("pack",)) if r.get("pack") else None
            if pack is not None and pack not in hc.PACKS:
                raise AdminError("e_unknown_pack")
            if not ep and pack is None:
                raise AdminError("e_day_empty")
            table.append({**({"ep": ep} if ep else {}),
                          **({"pack": pack, "count": as_int(r.get("count") or 1, 1, 99, ("pack_count",))} if pack else {})})
        except AdminError as e:  # "Day 3: ..."
            raise AdminError("e_day", ("day_n", i + 1), e.args) from None
    if not 1 <= len(table) <= 31:
        raise AdminError("e_table_days")
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


@api("match_rewards")
def match_rewards(p):
    return {**hc.match_reward_cfg(), "file": rel(hc.MATCH_REWARD_FILE)}


@api("match_rewards_set")
def match_rewards_set(p):
    """EP and exp by result plus the reward cards (gamedata/match_rewards.json, read at every match end)."""
    res = p.get("result") or {}
    result = {k: {"ep": as_int((res.get(k) or {}).get("ep"), 0, 10 ** 9, "EP"),
                  "coach": as_int((res.get(k) or {}).get("coach"), 0, 10 ** 6, ("mr_coach_exp",)),
                  "player": as_int((res.get(k) or {}).get("player"), 0, 10 ** 6, ("mr_player_exp",))}
              for k in ("win", "draw", "loss")}
    cards = [prize_row(w, prize) for w, prize in p.get("cards") or []]
    if not 1 <= len(cards) <= 10:
        raise AdminError("e_prizes")
    cfg = {"result": result, "cards": cards}
    with open(hc.MATCH_REWARD_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return cfg


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
            "file": rel(hc.SHOP_FILE)}


def save_shop(cfg):
    """Write gamedata/shop.json and rebuild the Shop; a pack without a single card is refused."""
    old = hc.shop_config()
    hc.apply_shop(cfg)
    empty = [i for i, v in (cfg.get("packs") or {}).items() if len(hc.pack_pool(int(i))) < (v.get("draft") or 1)]
    if empty:
        hc.apply_shop(old)
        raise AdminError("e_pack_empty", empty[0])
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
        raise AdminError("e_length", what, n)
    return v


def icon_of(v, required=True):
    v = str(v or "").strip()
    if v and v not in shop_icons():
        raise AdminError("e_no_icon", v)
    if required and not v:
        raise AdminError("e_pick_icon")
    return v


def rows_of(rows, what, kinds, lo=1, hi=10):
    """[[itemid, count]] with every itemid known."""
    out = []
    for r in rows or []:
        i = as_int(r[0], 1, 10 ** 10, "itemid")
        if not known(i, *kinds):
            raise AdminError("e_row_item", what, i)
        out.append([i, as_int(r[1], 1, 10 ** 12, ("count",))])
    if not lo <= len(out) <= hi:
        raise AdminError("e_rows", what, lo, hi)
    return out


def prize_row(w, prize, not_id=None):
    """[weight, {"ep": n} | itemid of a pack or item] from a prize row of the page."""
    w = as_int(w, 1, 1000, ("f_weight",))
    if isinstance(prize, dict):
        return [w, {"ep": as_int(prize.get("ep"), 1, 10 ** 12, "EP")}]
    if int(prize) != not_id and known(prize, "packs", "items"):
        return [w, int(prize)]
    raise AdminError("e_unknown_prize", prize)


def check_def(kind, d, itemid):
    """A clean shop.json entry from the page's form, or AdminError."""
    name = text(d.get("name"), ("f_name",))
    desc = str(d.get("description") or "").strip()[:200]
    if kind == "packs":
        seasons = sorted({as_int(s, 0, 99, ("th_season",)) for s in d.get("seasons") or []})
        pos = str(d.get("pos") or "")
        if pos and pos not in hc.POSITIONS:
            raise AdminError("e_unknown_pos")
        opt = lambda k, lo, hi, w: as_int(d[k], lo, hi, w) if d.get(k) not in (None, "", 0, "0") else None
        draft = opt("draft", 1, 10, ("f_draft",))
        if draft and len(seasons) != 1:  # the draft screen searches one season
            raise AdminError("e_draft_season")
        return {"name": name, "icon": icon_of(d.get("icon"), False), "seasons": seasons, "all": bool(d.get("all")),
                "top": opt("top", 1, 100000, ("f_top",)), "ovr": opt("ovr", 40, 130, ("f_ovr",)),
                "grade": opt("grade", 1, 10, ("f_grade",)), "pos": pos or None,
                "league": opt("league", 1, 10 ** 6, ("f_league",)), "draft": draft}
    if kind == "items":
        t = str(d.get("type") or "")
        if t not in hc.SHOP_ITEM_TYPES:
            raise AdminError("e_unknown_type")
        out = {"name": name, "icon": icon_of(d.get("icon")), "type": t, "description": desc}
        if t == "EP_LOTTERY":
            lo, hi = (as_int(x, 0, 10 ** 12, "EP") for x in (d.get("ep") or [0, 0]))
            if not 0 < lo <= hi:
                raise AdminError("e_ep_range")
            out["ep"] = [lo, hi]
        elif t == "ITEM_LOTTERY":
            prizes = [prize_row(w, prize, itemid) for w, prize in d.get("prizes") or []]
            if not 1 <= len(prizes) <= 10:  # the box screen shows up to 10 (cardCandidate0..9)
                raise AdminError("e_prizes")
            out["prizes"] = prizes
        elif t == "ENHANCEMENT_BOOST":
            out["boost"] = as_int(round(float(d.get("boost") or 0) * 100), 1, 100, ("f_boost",)) / 100
        elif t == "PLAYER_EXP_CAPSULE":
            out["exp"] = as_int(d.get("exp"), 1, 10 ** 7, ("f_exp",))
            if d.get("lv") not in (None, "", 0, "0"):
                out["lv"] = as_int(d["lv"], 1, hc.PLAYER_MAX_LEVEL - 1, ("f_maxlv",))
            if d.get("season") not in (None, "", 0, "0"):
                out["season"] = as_int(d["season"], 1, 99, ("th_season",))
        return out
    if kind == "packages":
        return {"name": name, "icon": icon_of(d.get("icon")), "description": desc,
                "contents": rows_of(d.get("contents"), ("f_contents",), ("packs", "items", "ep"))}
    if kind == "monthly":
        return {"name": name, "icon": icon_of(d.get("icon")), "description": desc,
                "days": as_int(d.get("days"), 1, 365, ("f_days",)),
                "now": rows_of(d.get("now"), ("f_now",), ("packs", "items", "ep"), 0),
                "daily": rows_of(d.get("daily"), ("f_daily",), ("packs", "items", "ep"))}
    raise AdminError("e_unknown_kind")


def kind_of(p):
    k = str(p.get("kind") or "")
    if k not in hc.SHOP_KINDS:
        raise AdminError("e_unknown_kind")
    return k


@api("shop_save")
def shop_save(p):
    """Create (no itemid) or change a product; a built-in one is replaced by the saved copy."""
    kind = kind_of(p); cfg = hc.shop_config()
    table = hc.SHOP_KINDS[kind][0]
    if p.get("itemid"):
        itemid = as_int(p["itemid"], 1, 10 ** 10, "itemid")
        if itemid not in table:
            raise AdminError("e_product_missing")
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
        raise AdminError("e_not_changed")
    if itemid not in hc._SHOP_BASE[kind] and (user := in_use(itemid)):
        raise AdminError("e_in_use", user)
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
        raise AdminError("e_product_missing")
    prices = cfg.setdefault("prices", {})
    if p.get("price") in (None, ""):
        prices.pop(str(itemid), None)
    else:
        prices[str(itemid)] = as_int(p["price"], 0, 10 ** 12, ("th_fixed_price",))
    save_shop(cfg)
    return {"ok": True}


@api("shop_hide")
def shop_hide(p):
    cfg = hc.shop_config(); itemid = as_int(p.get("itemid"), 1, 10 ** 10, "itemid")
    if not product_exists(itemid):
        raise AdminError("e_product_missing")
    hidden =[i for i in cfg.get("hidden", []) if i != itemid]
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
                raise AdminError("e_list_item", ("list_" + k,), bad)
            lists[k] = list(dict.fromkeys(ids))
        elif k == "chained":
            chains = [[as_int(i, 1, 10 ** 10, "itemid") for i in c] for c in v if c]
            if any(not known(i, "packages") for c in chains for i in c):
                raise AdminError("e_chain_packages")
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
            with open(PAGE, "rb") as f:  # the string tables go in as JSON (ASCII, no "</" to end the script)
                page = f.read().replace(b"/*I18N*/{}", json.dumps(I18N).replace("</", "<\\/").encode())
            return self._send(200, page, "text/html; charset=utf-8")
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

# --- Strings: one table per language; the page gets all of them and has a language switch ------
# Every table needs the same keys and {0}.. placeholders as "id" (python admin.py checks that).
# The game's own screen names (Tim inti, Item saya, Terima, Formasi, ...) stay as the Indonesian
# client shows them. lang_name labels the switch, locale formats numbers and dates, e_* are the
# API's error messages (AdminError / tr). Adding a language = one more table.
I18N = {
    "id": dict(
        ep_balance="Saldo EP", language="Bahasa", menu="Menu admin",
        nav_ringkasan="Ringkasan", nav_pemain="Pemain klub", nav_tambah="Tambah pemain", nav_item="Pak & Bag", nav_shop="Shop",
        nav_harian="Hadiah harian", nav_scout="Scout", nav_log="Log server",
        status_default="Perubahan langsung tersimpan di server; game menampilkannya setelah dibuka ulang atau setelah layar klub dimuat ulang.",
        sum_title="Ringkasan klub", sum_lead="Keadaan akun di server sekarang.", ep_title="Saldo EP", amount="Jumlah",
        ep_add="Tambah EP", ep_sub="Kurangi EP", ep_set="Jadikan saldo ini", coach_line="{0}, tim {1}",
        f_players="Pemain di klub", f_team2="Di Tim Cadangan", f_packs="Pak di Item saya", f_bag="Hadiah di Bag belum diambil",
        f_streak="Login berturut-turut", days="{0} hari", f_today="Hadiah hari ini", given="sudah diberikan", waiting="menunggu login",
        f_vip="VIP + PC warnet aktif sampai", ep_empty="Isi jumlah EP dulu.", ep_now="Saldo EP sekarang {0}.",
        pl_lead="Ubah grade, pindahkan ke Tim Cadangan (dipakai Tukar Scout), atau keluarkan pemain di luar 18 skuad. Kartu baru dari pak, trade dan Market masuk Tim inti.",
        pl_filter="Cari di daftar", ph_player="nama pemain", pl_team2_clear="Semua Tim Cadangan ke Tim inti",
        th_role="Peran", th_name="Nama", th_season="Musim", th_value="Harga EP", th_team="Tim", th_pos="Posisi",
        reserve="Cadangan", to_first="Ke Tim inti", to_second="Ke Tim Cadangan", first_team="Tim inti", release="Keluarkan",
        no_player="Tidak ada pemain yang cocok.", confirm_release="Keluarkan {0} dari klub? Tidak bisa dibatalkan.",
        grade_saved="Grade disimpan.", moved_second="Pemain pindah ke Tim Cadangan.", moved_first="Pemain kembali ke Tim inti.",
        released="{0} dikeluarkan dari klub.", team2_moved="{0} pemain kembali ke Tim inti.",
        add_lead="Cari kartu di database (rating sama seperti di game dan fifaaddict), lalu masukkan langsung ke klub atau kirim lewat Bag.",
        add_name="Nama pemain", ph_messi="mis. Messi", search="Cari", add_hint="Ketik minimal 2 huruf nama pemain.",
        on_sale="dijual", not_on_sale="tidak dijual", add_club="Masukkan ke klub", add_bag="Kirim lewat Bag",
        no_card="Tidak ada kartu dengan nama itu.", found="{0} kartu ditemukan.", search_failed="Gagal mencari: ",
        added="{0} +{1} masuk ke klub (Tim inti).", gifted="{0} +{1} dikirim ke Bag.", gift_player="Pemain: {0}",
        item_title="Pak pemain & Bag", item_lead="Pak dan item masuk ke Item saya. Hadiah Bag masuk ke Item saya → Items dan diambil dengan tombol Terima.",
        item_give="Beri pak ke Item saya", pack="Pak", count="Jumlah", item_give_btn="Beri", bag_title="Kirim hadiah ke Bag",
        title="Judul", pack_count="Jumlah pak", bag_spid="spid pemain", ph_optional="opsional", bag_send="Kirim ke Bag", no_pack="tanpa pak",
        given_packs="{0}× {1} masuk ke Item saya.", gift_sent="Hadiah \"{0}\" dikirim ke Bag.",
        shop_lead="Atur semua tab Shop: buat pak, item, paket dan paket bulanan baru dengan ikon dari client, ubah atau sembunyikan produk bawaan, dan pasang harga. Tersimpan di {0}; game memakainya saat Shop dibuka lagi.",
        shop_free="Semua produk gratis (0 EP)", shop_free_note="Harga tetap di tabel tetap berlaku.",
        kind_packs_tab="Pak pemain", kind_items_tab="Dapat dikonsumsi", kind_packages_tab="Paket", kind_monthly_tab="Paket bulanan", kind_lists_tab="Daftar tab",
        kind_packs="pak", kind_items="item", kind_packages="paket", kind_monthly="paket bulanan",
        new_kind="Buat {0} baru", edit_kind="Ubah {0}", shop_filter="Cari", ph_shop_filter="nama atau itemid",
        th_icon="Ikon", th_source="Asal", th_shop_price="Harga di Shop", th_fixed_price="Harga tetap", th_shown="Tampil",
        src_builtin="Bawaan", src_changed="Diubah", src_new="Baru", chained="Berantai", edit="Ubah", delete="Hapus", restore="Kembalikan asli",
        ph_default="bawaan", price_saved="Harga {0} disimpan.", price_reset="Harga {0} kembali ke bawaan.",
        hidden_msg="{0} disembunyikan dari Shop.", shown_msg="{0} tampil lagi di Shop.", free_on="Shop gratis.", free_off="Shop memakai harga.",
        saved_product="{0} disimpan (itemid {1}).", deleted="{0} dihapus.", restored="{0} kembali ke aslinya.",
        confirm_delete="Hapus {0}? Salinan yang sudah ada di Item saya tidak bisa dipakai lagi.", confirm_restore="Kembalikan {0} ke aslinya?",
        no_product="Tidak ada produk yang cocok.",
        f_name="Nama", f_icon="Ikon", icon_pick="Pilih ikon", f_desc="Deskripsi", f_seasons="Musim", seasons_hint="kosong = semua musim",
        f_top="Top N kartu terbaik", f_ovr="OVR minimal (kartu +1)", f_grade="Grade maks. (+1 … +N)", f_pos="Posisi", any="semua",
        f_league="ID liga", f_all="Semua kartu Market (bukan hanya lisensi ID)", f_type="Jenis",
        t_EP_LOTTERY="Kartu EP (acak)", t_ITEM_LOTTERY="Kotak acak", t_COACHNAME_CHANGE="Ganti nama manager", t_TEAM_CHANGE="Ganti tim",
        t_ENHANCEMENT_BOOST="Boost upgrade", t_LEAGUE_SIMULATION="Kupon Simulasi Liga",
        t_PLAYER_EXP_CAPSULE="EXP Capsule (EXP pemain)", f_exp="EXP", f_maxlv="Untuk pemain sampai level (kosong = semua)", f_draft="Draft: pilih N pemain, kartu di grade maks. (kosong = pak biasa)",
        e_draft_season="Pak draft harus tepat satu musim", f_ep_min="EP minimal", f_ep_max="EP maksimal", f_prizes="Hadiah (maks. 10)",
        f_weight="Bobot", f_prize="Hadiah", f_ep_amount="Jumlah EP", add_prize="Tambah hadiah", f_boost="Boost peluang upgrade (%)",
        f_contents="Isi", add_row="Tambah baris", f_days="Lama (hari)", f_now="Isi langsung saat dibeli", f_daily="Isi tiap hari",
        remove="Hapus", save="Simpan", cancel="Batal", none_type="Tidak perlu isian lain.", icons_count="{0} ikon dari client", ph_icon="cari nama ikon",
        lists_lead="Urutan produk di tab Rekomendasi, MP Shop, Bonus spesial dan Paket berantai.",
        list_new="Rekomendasi: baru", list_best="Rekomendasi: terlaris", list_mp="MP Shop", list_special="Bonus spesial",
        list_chained="Paket berantai", list_chained_hint="Dibeli berurutan; tiap baris satu rangkaian paket.", list_chain_add="Tambah rangkaian",
        list_add="Tambah", lists_save="Simpan daftar", lists_saved="Daftar tab disimpan.", empty="kosong",
        daily_title="Hadiah login harian", daily_lead="Login pertama tiap hari (WIB) memberi hadiah hari itu ke Bag. Login berturut-turut menaikkan hari; bolos sehari mengulang dari hari 1. Setelah hari terakhir, siklus kembali ke awal.",
        daily_grant="Beri hadiah hari berikutnya sekarang", daily_reset="Reset streak", daily_table="Tabel hadiah", th_day="Hari", day_n="Hari {0}",
        drop_day="Hapus hari", daily_add="Tambah hari", daily_save="Simpan tabel", f_total="Total hari login", f_last="Terakhir dapat hadiah",
        never="belum pernah", f_today_wib="Hari ini (WIB)", daily_saved="Tabel hadiah harian disimpan.", sent_bag="\"{0}\" dikirim ke Bag.",
        confirm_reset_streak="Reset streak login ke 0?", streak_reset="Streak direset.",
        nav_match="Hadiah match", mr_title="Hadiah match", mr_lead="Diberikan setelah setiap match yang dimainkan dan setiap Simulasi Liga: EP dan EXP menurut hasil, lalu tiga kartu hadiah. Kartu yang dibuka pemain diambil acak dari daftar kartu menurut bobotnya. Tersimpan di {0}; berlaku mulai match berikutnya.", mr_result="Menurut hasil", th_result="Hasil", mr_win="Menang", mr_draw="Seri", mr_loss="Kalah", mr_coach_exp="EXP manajer", mr_player_exp="EXP tiap pemain", mr_cards="Kartu hadiah", mr_chance="peluang {0}%", mr_saved="Hadiah match disimpan.",
        scout_title="Scout (Tukar Scout)", scout_lead="Scout yang baru dipakai terkunci sampai cooldown habis.", th_available="Tersedia lagi",
        locked="terkunci", ready="siap dipakai", now="sekarang", no_quest="tanpa quest", scout_reset="Reset cooldown semua scout",
        scouts_ready="Semua scout siap dipakai lagi.", q_value="nilai pemain ≥", q_grade="grade ≥", q_count="jumlah", q_season="musim",
        log_lead="Baris terakhir dari captures/http_config.log.", log_reload="Muat ulang log", log_auto="Muat otomatis tiap 3 detik",
        failed="Gagal: ", load_failed="Gagal memuat: ",
        lang_name="Bahasa Indonesia", locale="id-ID",
        grade="Grade", th_market="Market", th_scout="Scout", th_status="Status", th_quest="Quest", f_item="Item", upgrade_point="Upgrade point",
        e_player_missing="pemain tidak ditemukan", e_number="{0} harus angka", e_range="{0} harus {1}..{2}",
        e_no_spid="spid tidak ada di database", e_club_full="klub penuh ({0} pemain)",
        e_in_squad="pemain ada di 18 skuad; ganti dulu di Formasi", e_squad_first="pemain 18 skuad tetap di Tim inti",
        e_unknown_item="pak atau item tidak dikenal", e_unknown_pack="pak tidak dikenal", e_gift_empty="isi EP, pak, atau pemain",
        e_day="{0}: {1}", e_day_empty="kosong", e_table_days="tabel harus 1..31 hari",
        e_pack_empty="pak {0} tidak berisi kartu satu pun", e_length="{0} harus 1..{1} huruf",
        e_no_icon="ikon {0} tidak ada di client", e_pick_icon="pilih ikon",
        e_row_item="{0}: item {1} tidak dikenal", e_rows="{0} harus {1}..{2} baris",
        e_unknown_pos="posisi tidak dikenal", e_unknown_type="jenis item tidak dikenal",
        e_ep_range="EP minimal harus > 0 dan <= maksimal", e_unknown_prize="hadiah {0} tidak dikenal", e_prizes="hadiah harus 1..10",
        e_unknown_kind="jenis produk tidak dikenal", e_product_missing="produk tidak ditemukan", e_not_changed="produk ini tidak diubah",
        e_in_use="masih dipakai oleh {0}", e_list_item="{0}: item {1} tidak cocok di sini", e_chain_packages="paket berantai hanya berisi paket",
    ),
    "en": dict(
        ep_balance="EP balance", language="Language", menu="Admin menu",
        nav_ringkasan="Overview", nav_pemain="Club players", nav_tambah="Add players", nav_item="Packs & Bag", nav_shop="Shop",
        nav_harian="Daily rewards", nav_scout="Scouts", nav_log="Server log",
        status_default="Changes are saved on the server at once; the game shows them after a restart or when the club screen reloads.",
        sum_title="Club overview", sum_lead="The account on the server right now.", ep_title="EP balance", amount="Amount",
        ep_add="Add EP", ep_sub="Take EP", ep_set="Set the balance to this", coach_line="{0}, club {1}",
        f_players="Players in the club", f_team2="In Tim Cadangan", f_packs="Packs in Item saya", f_bag="Bag gifts not collected",
        f_streak="Login streak", days="{0} days", f_today="Today's reward", given="given", waiting="waiting for a login",
        f_vip="VIP + PC café perks until", ep_empty="Enter an EP amount first.", ep_now="EP balance is now {0}.",
        pl_lead="Change a card's grade, move it to Tim Cadangan (Tukar Scout trades from there), or release a card outside the squad's 18. New cards from packs, trades and the Market join Tim inti.",
        pl_filter="Filter the list", ph_player="player name", pl_team2_clear="Move every Tim Cadangan card to Tim inti",
        th_role="Role", th_name="Name", th_season="Season", th_value="EP value", th_team="Team", th_pos="Position",
        reserve="Reserve", to_first="To Tim inti", to_second="To Tim Cadangan", first_team="Tim inti", release="Release",
        no_player="No matching player.", confirm_release="Release {0} from the club? This cannot be undone.",
        grade_saved="Grade saved.", moved_second="Moved to Tim Cadangan.", moved_first="Back in Tim inti.",
        released="{0} released from the club.", team2_moved="{0} cards moved back to Tim inti.",
        add_lead="Search the card database (ratings as in the game and on fifaaddict), then put a card straight into the club or send it through the Bag.",
        add_name="Player name", ph_messi="e.g. Messi", search="Search", add_hint="Type at least 2 letters of a name.",
        on_sale="on sale", not_on_sale="not on sale", add_club="Add to club", add_bag="Send via Bag",
        no_card="No card with that name.", found="{0} cards found.", search_failed="Search failed: ",
        added="{0} +{1} joined the club (Tim inti).", gifted="{0} +{1} sent to the Bag.", gift_player="Player: {0}",
        item_title="Player packs & Bag", item_lead="Packs and items go to Item saya. Bag gifts go to Item saya → Items and are collected with Terima.",
        item_give="Give a pack to Item saya", pack="Pack", count="Count", item_give_btn="Give", bag_title="Send a gift to the Bag",
        title="Title", pack_count="Pack count", bag_spid="Player spid", ph_optional="optional", bag_send="Send to the Bag", no_pack="no pack",
        given_packs="{0}× {1} added to Item saya.", gift_sent="Gift \"{0}\" sent to the Bag.",
        shop_lead="Run every Shop tab: create packs, items, packages and monthly packages with the client's own icons, change or hide the built-in ones, and set prices. Saved in {0}; the game uses it the next time the Shop opens.",
        shop_free="Every product is free (0 EP)", shop_free_note="Fixed prices in the table still apply.",
        kind_packs_tab="Player packs", kind_items_tab="Consumables", kind_packages_tab="Packages", kind_monthly_tab="Monthly packages", kind_lists_tab="Tab lists",
        kind_packs="pack", kind_items="item", kind_packages="package", kind_monthly="monthly package",
        new_kind="New {0}", edit_kind="Edit {0}", shop_filter="Filter", ph_shop_filter="name or itemid",
        th_icon="Icon", th_source="Source", th_shop_price="Shop price", th_fixed_price="Fixed price", th_shown="Shown",
        src_builtin="Built-in", src_changed="Changed", src_new="New", chained="Chained", edit="Edit", delete="Delete", restore="Restore original",
        ph_default="default", price_saved="Price of {0} saved.", price_reset="{0} uses its default price again.",
        hidden_msg="{0} is hidden from the Shop.", shown_msg="{0} shows in the Shop again.", free_on="The Shop is free.", free_off="The Shop charges prices.",
        saved_product="{0} saved (itemid {1}).", deleted="{0} deleted.", restored="{0} is back to the original.",
        confirm_delete="Delete {0}? Copies already in Item saya stop working.", confirm_restore="Restore {0} to the original?",
        no_product="No matching product.",
        f_name="Name", f_icon="Icon", icon_pick="Pick an icon", f_desc="Description", f_seasons="Seasons", seasons_hint="none = every season",
        f_top="Top N best cards", f_ovr="Min OVR (card at +1)", f_grade="Max grade (+1 … +N)", f_pos="Position", any="any",
        f_league="League id", f_all="Every Market card (not only ID-licensed)", f_type="Type",
        t_EP_LOTTERY="EP card (random)", t_ITEM_LOTTERY="Random box", t_COACHNAME_CHANGE="Manager name change", t_TEAM_CHANGE="Club change",
        t_ENHANCEMENT_BOOST="Upgrade boost", t_LEAGUE_SIMULATION="League Simulation coupon",
        t_PLAYER_EXP_CAPSULE="EXP Capsule (player EXP)", f_exp="EXP", f_maxlv="For players up to level (empty = any)", f_draft="Draft: pick N players, card at the max grade (empty = normal pack)",
        e_draft_season="A draft pack needs exactly one season", f_ep_min="Min EP", f_ep_max="Max EP", f_prizes="Prizes (up to 10)",
        f_weight="Weight", f_prize="Prize", f_ep_amount="EP amount", add_prize="Add a prize", f_boost="Upgrade chance boost (%)",
        f_contents="Contents", add_row="Add a row", f_days="Length (days)", f_now="Items at purchase", f_daily="Items every day",
        remove="Remove", save="Save", cancel="Cancel", none_type="Nothing else to fill in.", icons_count="{0} icons from the client", ph_icon="icon name",
        lists_lead="The order of products in the Featured, MP Shop, Special bonus and Chained package tabs.",
        list_new="Featured: new", list_best="Featured: best sellers", list_mp="MP Shop", list_special="Special bonus",
        list_chained="Chained packages", list_chained_hint="Bought in order; one chain of packages per row.", list_chain_add="Add a chain",
        list_add="Add", lists_save="Save lists", lists_saved="Tab lists saved.", empty="empty",
        daily_title="Daily login rewards", daily_lead="The first login each day (WIB) puts that day's reward in the Bag. Logging in on consecutive days moves to the next day; missing a day starts again at day 1. After the last day the cycle starts over.",
        daily_grant="Give the next day's reward now", daily_reset="Reset the streak", daily_table="Reward table", th_day="Day", day_n="Day {0}",
        drop_day="Remove day", daily_add="Add a day", daily_save="Save table", f_total="Days logged in", f_last="Last reward",
        never="never", f_today_wib="Today (WIB)", daily_saved="Daily reward table saved.", sent_bag="\"{0}\" sent to the Bag.",
        confirm_reset_streak="Reset the login streak to 0?", streak_reset="Streak reset.",
        nav_match="Match rewards", mr_title="Match rewards", mr_lead="Given after every played match and every Liga simulation: EP and exp by result, then three reward cards. The card the player opens is drawn from the card list by weight. Saved in {0}; used from the next match.", mr_result="By result", th_result="Result", mr_win="Win", mr_draw="Draw", mr_loss="Loss", mr_coach_exp="Manager exp", mr_player_exp="Exp per player", mr_cards="Reward cards", mr_chance="chance {0}%", mr_saved="Match rewards saved.",
        scout_title="Scouts (Tukar Scout)", scout_lead="A scout just used stays locked until its cooldown ends.", th_available="Available again",
        locked="locked", ready="ready", now="now", no_quest="no quest", scout_reset="Reset every scout's cooldown",
        scouts_ready="Every scout is ready again.", q_value="player value ≥", q_grade="grade ≥", q_count="count", q_season="season",
        log_lead="The last lines of captures/http_config.log.", log_reload="Reload log", log_auto="Reload every 3 seconds",
        failed="Failed: ", load_failed="Could not load: ",
        lang_name="English", locale="en-GB",
        grade="Grade", th_market="Market", th_scout="Scout", th_status="Status", th_quest="Quest", f_item="Item", upgrade_point="Upgrade point",
        e_player_missing="player not found", e_number="{0} must be a number", e_range="{0} must be {1}..{2}",
        e_no_spid="no such spid in the database", e_club_full="the club is full ({0} players)",
        e_in_squad="the player is in the squad's 18; swap him out in Formasi first", e_squad_first="players in the squad's 18 stay in Tim inti",
        e_unknown_item="unknown pack or item", e_unknown_pack="unknown pack", e_gift_empty="fill in EP, a pack or a player",
        e_day="{0}: {1}", e_day_empty="empty", e_table_days="the table must have 1..31 days",
        e_pack_empty="pack {0} holds no card at all", e_length="{0} must be 1..{1} characters",
        e_no_icon="icon {0} is not in the client", e_pick_icon="pick an icon",
        e_row_item="{0}: unknown item {1}", e_rows="{0} must have {1}..{2} rows",
        e_unknown_pos="unknown position", e_unknown_type="unknown item type",
        e_ep_range="EP min must be > 0 and <= max", e_unknown_prize="unknown prize {0}", e_prizes="prizes must be 1..10",
        e_unknown_kind="unknown product kind", e_product_missing="product not found", e_not_changed="this product was not changed",
        e_in_use="still used by {0}", e_list_item="{0}: item {1} does not fit here", e_chain_packages="a chained package holds packages only",
    ),
    "zh": dict(
        lang_name="简体中文", locale="zh-CN",
        ep_balance="EP 余额", language="语言", menu="管理菜单",
        nav_ringkasan="概览", nav_pemain="俱乐部球员", nav_tambah="添加球员", nav_item="卡包与 Bag", nav_shop="商城",
        nav_harian="每日奖励", nav_scout="球探", nav_log="服务器日志",
        status_default="修改会立即保存到服务器；游戏重新打开或俱乐部界面重新加载后才会显示。",
        sum_title="俱乐部概览", sum_lead="服务器上当前的账号状态。", ep_title="EP 余额", amount="数量",
        ep_add="增加 EP", ep_sub="扣除 EP", ep_set="设为此余额", coach_line="{0}，球队 {1}",
        f_players="俱乐部球员", f_team2="在 Tim Cadangan（替补队）", f_packs="Item saya 中的卡包", f_bag="Bag 中未领取的礼物",
        f_streak="连续登录", days="{0} 天", f_today="今日奖励", given="已发放", waiting="等待登录",
        f_vip="VIP + 网吧特权有效期至", ep_empty="请先填写 EP 数量。", ep_now="当前 EP 余额：{0}。",
        pl_lead="修改球员卡的强化等级、移到 Tim Cadangan（替补队，Tukar Scout 从这里选球员），或放走 18 人名单以外的球员。卡包、交易和 Market 获得的新球员卡进入 Tim inti（主力队）。",
        pl_filter="在列表中查找", ph_player="球员名", pl_team2_clear="把 Tim Cadangan 的球员全部移回 Tim inti",
        th_role="角色", th_name="名称", th_season="赛季", th_value="EP 身价", th_team="队伍", th_pos="位置",
        reserve="替补队", to_first="移到 Tim inti", to_second="移到 Tim Cadangan", first_team="Tim inti", release="放走",
        no_player="没有匹配的球员。", confirm_release="确定要把 {0} 从俱乐部放走吗？此操作无法撤销。",
        grade_saved="强化等级已保存。", moved_second="已移到 Tim Cadangan。", moved_first="已回到 Tim inti。",
        released="{0} 已离开俱乐部。", team2_moved="{0} 名球员已回到 Tim inti。",
        add_lead="在球员卡数据库中搜索（评分与游戏和 fifaaddict 相同），然后直接加入俱乐部或通过 Bag 发送。",
        add_name="球员名", ph_messi="例如 Messi", search="搜索", add_hint="请输入球员名的至少 2 个字母。",
        on_sale="可交易", not_on_sale="不可交易", add_club="加入俱乐部", add_bag="通过 Bag 发送",
        no_card="没有这个名字的球员卡。", found="找到 {0} 张球员卡。", search_failed="搜索失败：",
        added="{0} +{1} 已加入俱乐部（Tim inti）。", gifted="{0} +{1} 已发送到 Bag。",
        gift_player="Pemain: {0}",  # a Bag title the game shows: kept in the client's language
        item_title="球员卡包与 Bag", item_lead="卡包和道具进入 Item saya。Bag 礼物进入 Item saya → Items，用 Terima 按钮领取。",
        item_give="发放卡包到 Item saya", pack="卡包", count="数量", item_give_btn="发放", bag_title="发送礼物到 Bag",
        title="标题", pack_count="卡包数量", bag_spid="球员 spid", ph_optional="可选", bag_send="发送到 Bag", no_pack="无卡包",
        given_packs="{0}× {1} 已放入 Item saya。", gift_sent="礼物“{0}”已发送到 Bag。",
        shop_lead="管理商城的所有标签页：用客户端自带的图标创建新的卡包、道具、礼包和月卡礼包，修改或隐藏自带商品，设置价格。保存在 {0}；游戏下次打开商城时生效。",
        shop_free="所有商品免费（0 EP）", shop_free_note="表格中的固定价格仍然有效。",
        kind_packs_tab="球员卡包", kind_items_tab="消耗品", kind_packages_tab="礼包", kind_monthly_tab="月卡礼包", kind_lists_tab="标签页列表",
        kind_packs="卡包", kind_items="道具", kind_packages="礼包", kind_monthly="月卡礼包",
        new_kind="新建{0}", edit_kind="编辑{0}", shop_filter="筛选", ph_shop_filter="名称或 itemid",
        th_icon="图标", th_source="来源", th_shop_price="商城价格", th_fixed_price="固定价格", th_shown="显示",
        src_builtin="自带", src_changed="已修改", src_new="新建", chained="连锁", edit="编辑", delete="删除", restore="恢复原版",
        ph_default="默认", price_saved="{0} 的价格已保存。", price_reset="{0} 已恢复默认价格。",
        hidden_msg="{0} 已在商城隐藏。", shown_msg="{0} 已在商城重新显示。", free_on="商城已免费。", free_off="商城已恢复收费。",
        saved_product="{0} 已保存（itemid {1}）。", deleted="{0} 已删除。", restored="{0} 已恢复原版。",
        confirm_delete="确定删除 {0} 吗？Item saya 中已有的该物品将无法使用。", confirm_restore="确定把 {0} 恢复为原版吗？",
        no_product="没有匹配的商品。",
        f_name="名称", f_icon="图标", icon_pick="选择图标", f_desc="说明", f_seasons="赛季", seasons_hint="不选 = 所有赛季",
        f_top="最佳 N 张卡", f_ovr="最低 OVR（+1 时）", f_grade="最高强化等级（+1 … +N）", f_pos="位置", any="全部",
        f_league="联赛 ID", f_all="所有 Market 球员卡（不只是 ID 授权的）", f_type="类型",
        t_EP_LOTTERY="EP 卡（随机）", t_ITEM_LOTTERY="随机箱", t_COACHNAME_CHANGE="经理改名", t_TEAM_CHANGE="更换球队",
        t_ENHANCEMENT_BOOST="强化加成", t_LEAGUE_SIMULATION="联赛模拟券",
        t_PLAYER_EXP_CAPSULE="经验胶囊（球员经验）", f_exp="经验值", f_maxlv="适用球员最高等级（留空 = 不限）", f_draft="选秀：挑选 N 名球员，卡片为最高等级（留空 = 普通卡包）",
        e_draft_season="选秀卡包必须只选一个赛季", f_ep_min="最少 EP", f_ep_max="最多 EP", f_prizes="奖品（最多 10 个）",
        f_weight="权重", f_prize="奖品", f_ep_amount="EP 数量", add_prize="添加奖品", f_boost="强化成功率加成（%）",
        f_contents="内容", add_row="添加一行", f_days="天数", f_now="购买时立即获得", f_daily="每天获得",
        remove="移除", save="保存", cancel="取消", none_type="无需填写其他内容。", icons_count="客户端中的 {0} 个图标", ph_icon="搜索图标名",
        lists_lead="Rekomendasi（推荐）、MP Shop、Bonus spesial（特别奖励）和 Paket berantai（连锁礼包）标签页中的商品顺序。",
        list_new="推荐：新品", list_best="推荐：热卖", list_mp="MP Shop", list_special="特别奖励",
        list_chained="连锁礼包", list_chained_hint="按顺序购买；每行是一组礼包。", list_chain_add="添加一组",
        list_add="添加", lists_save="保存列表", lists_saved="标签页列表已保存。", empty="空",
        daily_title="每日登录奖励", daily_lead="每天（WIB，UTC+7）第一次登录时，当天的奖励会放进 Bag。连续登录时天数递增；断一天则从第 1 天重新开始。最后一天之后重新循环。",
        daily_grant="立即发放下一天的奖励", daily_reset="重置连续登录", daily_table="奖励表", th_day="天", day_n="第 {0} 天",
        drop_day="删除这一天", daily_add="添加一天", daily_save="保存奖励表", f_total="累计登录天数", f_last="上次领奖",
        never="从未", f_today_wib="今天（WIB）", daily_saved="每日奖励表已保存。", sent_bag="“{0}”已发送到 Bag。",
        confirm_reset_streak="把连续登录重置为 0？", streak_reset="连续登录已重置。",
        nav_match="比赛奖励", mr_title="比赛奖励", mr_lead="每场比赛结束后和每次联赛模拟后发放：按结果给 EP 和经验，然后发三张奖励卡。玩家翻开的卡按权重从卡片列表中随机抽取。保存在 {0}；从下一场比赛开始生效。", mr_result="按结果", th_result="结果", mr_win="胜", mr_draw="平", mr_loss="负", mr_coach_exp="经理经验", mr_player_exp="每名球员经验", mr_cards="奖励卡", mr_chance="概率 {0}%", mr_saved="比赛奖励已保存。",
        scout_title="球探（Tukar Scout）", scout_lead="刚用过的球探会锁定，直到冷却结束。", th_available="再次可用",
        locked="已锁定", ready="可用", now="现在", no_quest="无任务", scout_reset="重置所有球探的冷却",
        scouts_ready="所有球探已可再次使用。", q_value="球员身价 ≥", q_grade="强化等级 ≥", q_count="数量", q_season="赛季",
        log_lead="captures/http_config.log 的最后几行。", log_reload="刷新日志", log_auto="每 3 秒自动刷新",
        failed="失败：", load_failed="加载失败：",
        grade="强化等级", th_market="转会市场", th_scout="球探", th_status="状态", th_quest="任务", f_item="道具", upgrade_point="强化点数",
        e_player_missing="找不到该球员", e_number="{0} 必须是数字", e_range="{0} 必须在 {1}..{2} 之间",
        e_no_spid="数据库中没有这个 spid", e_club_full="俱乐部已满（{0} 名球员）",
        e_in_squad="该球员在 18 人名单中；请先在 Formasi 中把他换下", e_squad_first="18 人名单中的球员只能留在 Tim inti",
        e_unknown_item="未知的卡包或道具", e_unknown_pack="未知的卡包", e_gift_empty="请填写 EP、卡包或球员",
        e_day="{0}：{1}", e_day_empty="是空的", e_table_days="奖励表必须有 1..31 天",
        e_pack_empty="卡包 {0} 一张球员卡都没有", e_length="{0} 必须是 1..{1} 个字符",
        e_no_icon="客户端中没有图标 {0}", e_pick_icon="请选择图标",
        e_row_item="{0}：未知物品 {1}", e_rows="{0} 必须有 {1}..{2} 行",
        e_unknown_pos="未知的位置", e_unknown_type="未知的道具类型",
        e_ep_range="最少 EP 必须 > 0 且 <= 最多 EP", e_unknown_prize="未知的奖品 {0}", e_prizes="奖品必须有 1..10 个",
        e_unknown_kind="未知的商品种类", e_product_missing="找不到该商品", e_not_changed="该商品没有被修改过",
        e_in_use="仍被 {0} 使用", e_list_item="{0}：物品 {1} 不能放在这里", e_chain_packages="连锁礼包只能包含礼包",
    ),
    "th": dict(
        lang_name="ไทย", locale="th-TH",
        ep_balance="ยอด EP", language="ภาษา", menu="เมนูผู้ดูแล",
        nav_ringkasan="ภาพรวม", nav_pemain="นักเตะในสโมสร", nav_tambah="เพิ่มนักเตะ", nav_item="แพ็คและ Bag", nav_shop="ร้านค้า",
        nav_harian="รางวัลรายวัน", nav_scout="แมวมอง", nav_log="บันทึกเซิร์ฟเวอร์",
        status_default="การเปลี่ยนแปลงจะบันทึกบนเซิร์ฟเวอร์ทันที เกมจะแสดงผลหลังเปิดใหม่หรือเมื่อโหลดหน้าสโมสรใหม่",
        sum_title="ภาพรวมสโมสร", sum_lead="สถานะบัญชีบนเซิร์ฟเวอร์ตอนนี้", ep_title="ยอด EP", amount="จำนวน",
        ep_add="เพิ่ม EP", ep_sub="ลด EP", ep_set="ตั้งยอดเป็นค่านี้", coach_line="{0}, ทีม {1}",
        f_players="นักเตะในสโมสร", f_team2="อยู่ใน Tim Cadangan (ทีมสำรอง)", f_packs="แพ็คใน Item saya", f_bag="ของขวัญใน Bag ที่ยังไม่รับ",
        f_streak="ล็อกอินต่อเนื่อง", days="{0} วัน", f_today="รางวัลวันนี้", given="ให้แล้ว", waiting="รอการล็อกอิน",
        f_vip="สิทธิ์ VIP + ร้านเกม ใช้ได้ถึง", ep_empty="กรอกจำนวน EP ก่อน", ep_now="ยอด EP ตอนนี้ {0}",
        pl_lead="เปลี่ยนเกรดการ์ด ย้ายไป Tim Cadangan (ทีมสำรอง ที่ Tukar Scout ใช้เลือกนักเตะ) หรือปล่อยนักเตะที่อยู่นอก 18 คนของสควอด การ์ดใหม่จากแพ็ค การเทรด และ Market จะเข้า Tim inti (ทีมหลัก)",
        pl_filter="ค้นหาในรายการ", ph_player="ชื่อนักเตะ", pl_team2_clear="ย้ายการ์ดทั้งหมดใน Tim Cadangan ไป Tim inti",
        th_role="บทบาท", th_name="ชื่อ", th_season="ซีซั่น", th_value="มูลค่า EP", th_team="ทีม", th_pos="ตำแหน่ง",
        reserve="ทีมสำรอง", to_first="ไป Tim inti", to_second="ไป Tim Cadangan", first_team="Tim inti", release="ปล่อยตัว",
        no_player="ไม่มีนักเตะที่ตรงกัน", confirm_release="ปล่อย {0} ออกจากสโมสร? ยกเลิกไม่ได้",
        grade_saved="บันทึกเกรดแล้ว", moved_second="ย้ายไป Tim Cadangan แล้ว", moved_first="กลับมา Tim inti แล้ว",
        released="ปล่อย {0} ออกจากสโมสรแล้ว", team2_moved="ย้ายการ์ด {0} ใบกลับ Tim inti แล้ว",
        add_lead="ค้นหาการ์ดในฐานข้อมูล (เรตติ้งเหมือนในเกมและ fifaaddict) แล้วใส่เข้าสโมสรทันทีหรือส่งผ่าน Bag",
        add_name="ชื่อนักเตะ", ph_messi="เช่น Messi", search="ค้นหา", add_hint="พิมพ์ชื่อนักเตะอย่างน้อย 2 ตัวอักษร",
        on_sale="มีขาย", not_on_sale="ไม่มีขาย", add_club="ใส่เข้าสโมสร", add_bag="ส่งผ่าน Bag",
        no_card="ไม่มีการ์ดชื่อนี้", found="พบการ์ด {0} ใบ", search_failed="ค้นหาไม่สำเร็จ: ",
        added="{0} +{1} เข้าสโมสรแล้ว (Tim inti)", gifted="ส่ง {0} +{1} ไปที่ Bag แล้ว",
        gift_player="Pemain: {0}",  # a Bag title the game shows: kept in the client's language
        item_title="แพ็คนักเตะและ Bag", item_lead="แพ็คและไอเทมจะเข้า Item saya ของขวัญ Bag จะเข้า Item saya → Items และรับได้ด้วยปุ่ม Terima",
        item_give="ให้แพ็คเข้า Item saya", pack="แพ็ค", count="จำนวน", item_give_btn="ให้", bag_title="ส่งของขวัญไปที่ Bag",
        title="หัวข้อ", pack_count="จำนวนแพ็ค", bag_spid="spid นักเตะ", ph_optional="ไม่บังคับ", bag_send="ส่งไปที่ Bag", no_pack="ไม่มีแพ็ค",
        given_packs="{0}× {1} เข้า Item saya แล้ว", gift_sent="ส่งของขวัญ \"{0}\" ไปที่ Bag แล้ว",
        shop_lead="จัดการทุกแท็บของร้านค้า: สร้างแพ็ค ไอเทม แพ็กเกจ และแพ็กเกจรายเดือนใหม่ด้วยไอคอนของไคลเอนต์ แก้ไขหรือซ่อนสินค้าเดิม และตั้งราคา บันทึกไว้ที่ {0} เกมจะใช้เมื่อเปิดร้านค้าครั้งถัดไป",
        shop_free="สินค้าทั้งหมดฟรี (0 EP)", shop_free_note="ราคาคงที่ในตารางยังมีผล",
        kind_packs_tab="แพ็คนักเตะ", kind_items_tab="ไอเทมใช้แล้วหมด", kind_packages_tab="แพ็กเกจ", kind_monthly_tab="แพ็กเกจรายเดือน", kind_lists_tab="รายการในแท็บ",
        kind_packs="แพ็ค", kind_items="ไอเทม", kind_packages="แพ็กเกจ", kind_monthly="แพ็กเกจรายเดือน",
        new_kind="สร้าง{0}ใหม่", edit_kind="แก้ไข{0}", shop_filter="ค้นหา", ph_shop_filter="ชื่อหรือ itemid",
        th_icon="ไอคอน", th_source="ที่มา", th_shop_price="ราคาในร้าน", th_fixed_price="ราคาคงที่", th_shown="แสดง",
        src_builtin="ของเดิม", src_changed="แก้ไขแล้ว", src_new="ใหม่", chained="ต่อเนื่อง", edit="แก้ไข", delete="ลบ", restore="คืนค่าเดิม",
        ph_default="ค่าเริ่มต้น", price_saved="บันทึกราคา {0} แล้ว", price_reset="{0} กลับไปใช้ราคาเริ่มต้น",
        hidden_msg="ซ่อน {0} จากร้านค้าแล้ว", shown_msg="{0} แสดงในร้านค้าอีกครั้ง", free_on="ร้านค้าฟรีแล้ว", free_off="ร้านค้ากลับมาคิดราคาแล้ว",
        saved_product="บันทึก {0} แล้ว (itemid {1})", deleted="ลบ {0} แล้ว", restored="{0} กลับเป็นของเดิมแล้ว",
        confirm_delete="ลบ {0}? ชิ้นที่อยู่ใน Item saya แล้วจะใช้ไม่ได้อีก", confirm_restore="คืนค่า {0} เป็นของเดิม?",
        no_product="ไม่มีสินค้าที่ตรงกัน",
        f_name="ชื่อ", f_icon="ไอคอน", icon_pick="เลือกไอคอน", f_desc="คำอธิบาย", f_seasons="ซีซั่น", seasons_hint="ไม่เลือก = ทุกซีซั่น",
        f_top="การ์ดดีที่สุด N ใบ", f_ovr="OVR ขั้นต่ำ (การ์ด +1)", f_grade="เกรดสูงสุด (+1 … +N)", f_pos="ตำแหน่ง", any="ทั้งหมด",
        f_league="ID ลีก", f_all="การ์ดทั้งหมดใน Market (ไม่ใช่เฉพาะที่มีลิขสิทธิ์ ID)", f_type="ประเภท",
        t_EP_LOTTERY="การ์ด EP (สุ่ม)", t_ITEM_LOTTERY="กล่องสุ่ม", t_COACHNAME_CHANGE="เปลี่ยนชื่อผู้จัดการ", t_TEAM_CHANGE="เปลี่ยนทีม",
        t_ENHANCEMENT_BOOST="บูสต์อัปเกรด", t_LEAGUE_SIMULATION="คูปองจำลองลีก",
        t_PLAYER_EXP_CAPSULE="แคปซูล EXP (EXP นักเตะ)", f_exp="EXP", f_maxlv="ใช้กับนักเตะเลเวลไม่เกิน (ว่าง = ทั้งหมด)", f_draft="ดราฟต์: เลือกนักเตะ N คน การ์ดได้เกรดสูงสุด (ว่าง = แพ็คปกติ)",
        e_draft_season="แพ็คดราฟต์ต้องมีซีซั่นเดียวเท่านั้น", f_ep_min="EP ขั้นต่ำ", f_ep_max="EP สูงสุด", f_prizes="รางวัล (สูงสุด 10)",
        f_weight="น้ำหนัก", f_prize="รางวัล", f_ep_amount="จำนวน EP", add_prize="เพิ่มรางวัล", f_boost="เพิ่มโอกาสอัปเกรด (%)",
        f_contents="สิ่งที่ได้", add_row="เพิ่มแถว", f_days="ระยะเวลา (วัน)", f_now="ได้ทันทีเมื่อซื้อ", f_daily="ได้ทุกวัน",
        remove="ลบ", save="บันทึก", cancel="ยกเลิก", none_type="ไม่ต้องกรอกอย่างอื่น", icons_count="ไอคอน {0} รูปจากไคลเอนต์", ph_icon="ค้นหาชื่อไอคอน",
        lists_lead="ลำดับสินค้าในแท็บ Rekomendasi (แนะนำ), MP Shop, Bonus spesial (โบนัสพิเศษ) และ Paket berantai (แพ็กเกจต่อเนื่อง)",
        list_new="แนะนำ: ใหม่", list_best="แนะนำ: ขายดี", list_mp="MP Shop", list_special="โบนัสพิเศษ",
        list_chained="แพ็กเกจต่อเนื่อง", list_chained_hint="ซื้อตามลำดับ แต่ละแถวคือแพ็กเกจหนึ่งชุด", list_chain_add="เพิ่มชุด",
        list_add="เพิ่ม", lists_save="บันทึกรายการ", lists_saved="บันทึกรายการในแท็บแล้ว", empty="ว่าง",
        daily_title="รางวัลล็อกอินรายวัน", daily_lead="การล็อกอินครั้งแรกของแต่ละวัน (WIB, UTC+7) จะส่งรางวัลของวันนั้นเข้า Bag ล็อกอินต่อเนื่องจะเลื่อนไปวันถัดไป ขาดหนึ่งวันจะเริ่มใหม่ที่วันที่ 1 หลังวันสุดท้ายจะวนกลับไปเริ่มใหม่",
        daily_grant="ให้รางวัลของวันถัดไปตอนนี้", daily_reset="รีเซ็ตการล็อกอินต่อเนื่อง", daily_table="ตารางรางวัล", th_day="วัน", day_n="วันที่ {0}",
        drop_day="ลบวัน", daily_add="เพิ่มวัน", daily_save="บันทึกตาราง", f_total="จำนวนวันที่ล็อกอิน", f_last="ได้รางวัลล่าสุด",
        never="ยังไม่เคย", f_today_wib="วันนี้ (WIB)", daily_saved="บันทึกตารางรางวัลรายวันแล้ว", sent_bag="ส่ง \"{0}\" ไปที่ Bag แล้ว",
        confirm_reset_streak="รีเซ็ตการล็อกอินต่อเนื่องเป็น 0?", streak_reset="รีเซ็ตการล็อกอินต่อเนื่องแล้ว",
        nav_match="รางวัลหลังแมตช์", mr_title="รางวัลหลังแมตช์", mr_lead="มอบให้หลังทุกแมตช์ที่เล่นและทุกครั้งที่จำลองลีก: EP และ EXP ตามผลการแข่งขัน แล้วมีการ์ดรางวัลสามใบ การ์ดที่ผู้เล่นเปิดจะสุ่มจากรายการการ์ดตามน้ำหนัก บันทึกไว้ที่ {0} ใช้ตั้งแต่แมตช์ถัดไป", mr_result="ตามผลการแข่งขัน", th_result="ผล", mr_win="ชนะ", mr_draw="เสมอ", mr_loss="แพ้", mr_coach_exp="EXP ผู้จัดการ", mr_player_exp="EXP ต่อผู้เล่น", mr_cards="การ์ดรางวัล", mr_chance="โอกาส {0}%", mr_saved="บันทึกรางวัลหลังแมตช์แล้ว",
        scout_title="แมวมอง (Tukar Scout)", scout_lead="แมวมองที่เพิ่งใช้จะถูกล็อกจนกว่าคูลดาวน์จะหมด", th_available="ใช้ได้อีกครั้ง",
        locked="ล็อกอยู่", ready="พร้อมใช้", now="ตอนนี้", no_quest="ไม่มีเควสต์", scout_reset="รีเซ็ตคูลดาวน์ของแมวมองทั้งหมด",
        scouts_ready="แมวมองทั้งหมดพร้อมใช้อีกครั้ง", q_value="มูลค่านักเตะ ≥", q_grade="เกรด ≥", q_count="จำนวน", q_season="ซีซั่น",
        log_lead="บรรทัดล่าสุดของ captures/http_config.log", log_reload="โหลดบันทึกใหม่", log_auto="โหลดอัตโนมัติทุก 3 วินาที",
        failed="ไม่สำเร็จ: ", load_failed="โหลดไม่สำเร็จ: ",
        grade="เกรด", th_market="ตลาด", th_scout="แมวมอง", th_status="สถานะ", th_quest="เควสต์", f_item="ไอเทม", upgrade_point="แต้มอัปเกรด",
        e_player_missing="ไม่พบนักเตะ", e_number="{0} ต้องเป็นตัวเลข", e_range="{0} ต้องอยู่ระหว่าง {1}..{2}",
        e_no_spid="ไม่มี spid นี้ในฐานข้อมูล", e_club_full="สโมสรเต็มแล้ว ({0} คน)",
        e_in_squad="นักเตะอยู่ใน 18 คนของสควอด ให้เปลี่ยนตัวออกใน Formasi ก่อน", e_squad_first="นักเตะใน 18 คนของสควอดต้องอยู่ใน Tim inti",
        e_unknown_item="ไม่รู้จักแพ็คหรือไอเทมนี้", e_unknown_pack="ไม่รู้จักแพ็คนี้", e_gift_empty="กรอก EP แพ็ค หรือนักเตะ",
        e_day="{0}: {1}", e_day_empty="ว่างเปล่า", e_table_days="ตารางต้องมี 1..31 วัน",
        e_pack_empty="แพ็ค {0} ไม่มีการ์ดเลยสักใบ", e_length="{0} ต้องยาว 1..{1} ตัวอักษร",
        e_no_icon="ไม่มีไอคอน {0} ในไคลเอนต์", e_pick_icon="เลือกไอคอน",
        e_row_item="{0}: ไม่รู้จักไอเทม {1}", e_rows="{0} ต้องมี {1}..{2} แถว",
        e_unknown_pos="ไม่รู้จักตำแหน่งนี้", e_unknown_type="ไม่รู้จักประเภทไอเทมนี้",
        e_ep_range="EP ขั้นต่ำต้อง > 0 และ <= EP สูงสุด", e_unknown_prize="ไม่รู้จักรางวัล {0}", e_prizes="รางวัลต้องมี 1..10 รายการ",
        e_unknown_kind="ไม่รู้จักประเภทสินค้านี้", e_product_missing="ไม่พบสินค้า", e_not_changed="สินค้านี้ยังไม่เคยถูกแก้ไข",
        e_in_use="ยังถูกใช้โดย {0}", e_list_item="{0}: ใส่ไอเทม {1} ที่นี่ไม่ได้", e_chain_packages="แพ็กเกจต่อเนื่องใส่ได้เฉพาะแพ็กเกจ",
    ),
    "vi": dict(
        lang_name="Tiếng Việt", locale="vi-VN",
        ep_balance="Số dư EP", language="Ngôn ngữ", menu="Menu quản trị",
        nav_ringkasan="Tổng quan", nav_pemain="Cầu thủ CLB", nav_tambah="Thêm cầu thủ", nav_item="Gói & Bag", nav_shop="Cửa hàng",
        nav_harian="Quà hằng ngày", nav_scout="Tuyển trạch viên", nav_log="Nhật ký máy chủ",
        status_default="Thay đổi được lưu ngay trên máy chủ; game hiển thị sau khi mở lại hoặc khi màn hình CLB tải lại.",
        sum_title="Tổng quan CLB", sum_lead="Trạng thái tài khoản trên máy chủ lúc này.", ep_title="Số dư EP", amount="Số lượng",
        ep_add="Thêm EP", ep_sub="Trừ EP", ep_set="Đặt số dư bằng số này", coach_line="{0}, đội {1}",
        f_players="Cầu thủ trong CLB", f_team2="Trong Tim Cadangan (đội dự bị)", f_packs="Gói trong Item saya", f_bag="Quà trong Bag chưa nhận",
        f_streak="Đăng nhập liên tiếp", days="{0} ngày", f_today="Quà hôm nay", given="đã trao", waiting="chờ đăng nhập",
        f_vip="VIP + ưu đãi phòng máy đến", ep_empty="Hãy nhập số EP trước.", ep_now="Số dư EP hiện là {0}.",
        pl_lead="Đổi cấp thẻ, chuyển sang Tim Cadangan (đội dự bị, Tukar Scout chọn cầu thủ từ đây), hoặc giải phóng cầu thủ ngoài 18 người của đội hình. Thẻ mới từ gói, giao dịch và Market vào Tim inti (đội chính).",
        pl_filter="Tìm trong danh sách", ph_player="tên cầu thủ", pl_team2_clear="Chuyển tất cả Tim Cadangan về Tim inti",
        th_role="Vai trò", th_name="Tên", th_season="Mùa", th_value="Giá trị EP", th_team="Đội", th_pos="Vị trí",
        reserve="Dự bị", to_first="Về Tim inti", to_second="Sang Tim Cadangan", first_team="Tim inti", release="Giải phóng",
        no_player="Không có cầu thủ phù hợp.", confirm_release="Giải phóng {0} khỏi CLB? Không thể hoàn tác.",
        grade_saved="Đã lưu cấp thẻ.", moved_second="Đã chuyển sang Tim Cadangan.", moved_first="Đã về Tim inti.",
        released="Đã giải phóng {0} khỏi CLB.", team2_moved="{0} cầu thủ đã về Tim inti.",
        add_lead="Tìm thẻ trong cơ sở dữ liệu (chỉ số giống trong game và fifaaddict), rồi đưa thẳng vào CLB hoặc gửi qua Bag.",
        add_name="Tên cầu thủ", ph_messi="vd. Messi", search="Tìm", add_hint="Gõ ít nhất 2 chữ cái của tên cầu thủ.",
        on_sale="đang bán", not_on_sale="không bán", add_club="Thêm vào CLB", add_bag="Gửi qua Bag",
        no_card="Không có thẻ nào tên đó.", found="Tìm thấy {0} thẻ.", search_failed="Tìm thất bại: ",
        added="{0} +{1} đã vào CLB (Tim inti).", gifted="Đã gửi {0} +{1} vào Bag.",
        gift_player="Pemain: {0}",  # a Bag title the game shows: kept in the client's language
        item_title="Gói cầu thủ & Bag", item_lead="Gói và vật phẩm vào Item saya. Quà Bag vào Item saya → Items và nhận bằng nút Terima.",
        item_give="Tặng gói vào Item saya", pack="Gói", count="Số lượng", item_give_btn="Tặng", bag_title="Gửi quà vào Bag",
        title="Tiêu đề", pack_count="Số gói", bag_spid="spid cầu thủ", ph_optional="không bắt buộc", bag_send="Gửi vào Bag", no_pack="không có gói",
        given_packs="{0}× {1} đã vào Item saya.", gift_sent="Đã gửi quà \"{0}\" vào Bag.",
        shop_lead="Quản lý mọi tab của Cửa hàng: tạo gói, vật phẩm, gói quà và gói tháng mới bằng biểu tượng của client, sửa hoặc ẩn sản phẩm có sẵn, và đặt giá. Lưu trong {0}; game dùng khi mở Cửa hàng lần sau.",
        shop_free="Mọi sản phẩm miễn phí (0 EP)", shop_free_note="Giá cố định trong bảng vẫn được áp dụng.",
        kind_packs_tab="Gói cầu thủ", kind_items_tab="Vật phẩm tiêu hao", kind_packages_tab="Gói quà", kind_monthly_tab="Gói tháng", kind_lists_tab="Danh sách tab",
        kind_packs="gói", kind_items="vật phẩm", kind_packages="gói quà", kind_monthly="gói tháng",
        new_kind="Tạo {0} mới", edit_kind="Sửa {0}", shop_filter="Lọc", ph_shop_filter="tên hoặc itemid",
        th_icon="Biểu tượng", th_source="Nguồn", th_shop_price="Giá trong Cửa hàng", th_fixed_price="Giá cố định", th_shown="Hiển thị",
        src_builtin="Có sẵn", src_changed="Đã sửa", src_new="Mới", chained="Nối tiếp", edit="Sửa", delete="Xóa", restore="Khôi phục bản gốc",
        ph_default="mặc định", price_saved="Đã lưu giá của {0}.", price_reset="{0} dùng lại giá mặc định.",
        hidden_msg="Đã ẩn {0} khỏi Cửa hàng.", shown_msg="{0} hiện lại trong Cửa hàng.", free_on="Cửa hàng miễn phí.", free_off="Cửa hàng tính giá trở lại.",
        saved_product="Đã lưu {0} (itemid {1}).", deleted="Đã xóa {0}.", restored="{0} đã về bản gốc.",
        confirm_delete="Xóa {0}? Các bản đã có trong Item saya sẽ không dùng được nữa.", confirm_restore="Khôi phục {0} về bản gốc?",
        no_product="Không có sản phẩm phù hợp.",
        f_name="Tên", f_icon="Biểu tượng", icon_pick="Chọn biểu tượng", f_desc="Mô tả", f_seasons="Mùa", seasons_hint="để trống = mọi mùa",
        f_top="N thẻ tốt nhất", f_ovr="OVR tối thiểu (thẻ +1)", f_grade="Cấp tối đa (+1 … +N)", f_pos="Vị trí", any="tất cả",
        f_league="ID giải đấu", f_all="Mọi thẻ trên Market (không chỉ thẻ có bản quyền ID)", f_type="Loại",
        t_EP_LOTTERY="Thẻ EP (ngẫu nhiên)", t_ITEM_LOTTERY="Hộp ngẫu nhiên", t_COACHNAME_CHANGE="Đổi tên HLV", t_TEAM_CHANGE="Đổi đội",
        t_ENHANCEMENT_BOOST="Tăng tỉ lệ nâng cấp", t_LEAGUE_SIMULATION="Phiếu Mô phỏng giải đấu",
        t_PLAYER_EXP_CAPSULE="Viên EXP (EXP cầu thủ)", f_exp="EXP", f_maxlv="Cho cầu thủ đến cấp (trống = tất cả)", f_draft="Draft: chọn N cầu thủ, thẻ ở cấp tối đa (trống = gói thường)",
        e_draft_season="Gói draft phải có đúng một mùa giải", f_ep_min="EP tối thiểu", f_ep_max="EP tối đa", f_prizes="Phần thưởng (tối đa 10)",
        f_weight="Trọng số", f_prize="Phần thưởng", f_ep_amount="Số EP", add_prize="Thêm phần thưởng", f_boost="Tăng tỉ lệ nâng cấp (%)",
        f_contents="Nội dung", add_row="Thêm dòng", f_days="Thời hạn (ngày)", f_now="Nhận ngay khi mua", f_daily="Nhận mỗi ngày",
        remove="Xóa", save="Lưu", cancel="Hủy", none_type="Không cần nhập gì thêm.", icons_count="{0} biểu tượng từ client", ph_icon="tìm tên biểu tượng",
        lists_lead="Thứ tự sản phẩm trong các tab Rekomendasi (đề xuất), MP Shop, Bonus spesial (thưởng đặc biệt) và Paket berantai (gói nối tiếp).",
        list_new="Đề xuất: mới", list_best="Đề xuất: bán chạy", list_mp="MP Shop", list_special="Thưởng đặc biệt",
        list_chained="Gói nối tiếp", list_chained_hint="Mua theo thứ tự; mỗi dòng là một chuỗi gói.", list_chain_add="Thêm chuỗi",
        list_add="Thêm", lists_save="Lưu danh sách", lists_saved="Đã lưu danh sách tab.", empty="trống",
        daily_title="Quà đăng nhập hằng ngày", daily_lead="Lần đăng nhập đầu tiên mỗi ngày (WIB, UTC+7) đưa quà của ngày đó vào Bag. Đăng nhập liên tiếp thì sang ngày tiếp theo; bỏ một ngày thì bắt đầu lại từ ngày 1. Sau ngày cuối, chu kỳ quay lại từ đầu.",
        daily_grant="Trao quà ngày kế tiếp ngay", daily_reset="Đặt lại chuỗi đăng nhập", daily_table="Bảng quà", th_day="Ngày", day_n="Ngày {0}",
        drop_day="Xóa ngày", daily_add="Thêm ngày", daily_save="Lưu bảng", f_total="Tổng số ngày đăng nhập", f_last="Lần nhận quà gần nhất",
        never="chưa bao giờ", f_today_wib="Hôm nay (WIB)", daily_saved="Đã lưu bảng quà hằng ngày.", sent_bag="Đã gửi \"{0}\" vào Bag.",
        confirm_reset_streak="Đặt lại chuỗi đăng nhập về 0?", streak_reset="Đã đặt lại chuỗi đăng nhập.",
        nav_match="Thưởng sau trận", mr_title="Thưởng sau trận", mr_lead="Trao sau mỗi trận đã đá và mỗi lần mô phỏng Liga: EP và EXP theo kết quả, rồi ba thẻ thưởng. Thẻ người chơi lật được rút ngẫu nhiên từ danh sách thẻ theo trọng số. Lưu trong {0}; áp dụng từ trận tiếp theo.", mr_result="Theo kết quả", th_result="Kết quả", mr_win="Thắng", mr_draw="Hòa", mr_loss="Thua", mr_coach_exp="EXP huấn luyện viên", mr_player_exp="EXP mỗi cầu thủ", mr_cards="Thẻ thưởng", mr_chance="tỉ lệ {0}%", mr_saved="Đã lưu thưởng sau trận.",
        scout_title="Tuyển trạch viên (Tukar Scout)", scout_lead="Tuyển trạch viên vừa dùng sẽ bị khóa đến khi hết thời gian hồi.", th_available="Dùng lại được lúc",
        locked="đang khóa", ready="sẵn sàng", now="ngay bây giờ", no_quest="không có nhiệm vụ", scout_reset="Đặt lại thời gian hồi của mọi tuyển trạch viên",
        scouts_ready="Mọi tuyển trạch viên đã sẵn sàng.", q_value="giá trị cầu thủ ≥", q_grade="cấp ≥", q_count="số lượng", q_season="mùa",
        log_lead="Các dòng cuối của captures/http_config.log.", log_reload="Tải lại nhật ký", log_auto="Tự tải lại mỗi 3 giây",
        failed="Thất bại: ", load_failed="Không tải được: ",
        grade="Cấp", th_market="Thị trường", th_scout="Tuyển trạch viên", th_status="Trạng thái", th_quest="Nhiệm vụ", f_item="Vật phẩm", upgrade_point="Điểm nâng cấp",
        e_player_missing="không tìm thấy cầu thủ", e_number="{0} phải là số", e_range="{0} phải trong khoảng {1}..{2}",
        e_no_spid="không có spid này trong cơ sở dữ liệu", e_club_full="CLB đã đầy ({0} cầu thủ)",
        e_in_squad="cầu thủ đang trong 18 người của đội hình; hãy thay ra trong Formasi trước", e_squad_first="cầu thủ trong 18 người của đội hình phải ở Tim inti",
        e_unknown_item="không rõ gói hoặc vật phẩm", e_unknown_pack="không rõ gói", e_gift_empty="hãy nhập EP, gói hoặc cầu thủ",
        e_day="{0}: {1}", e_day_empty="trống", e_table_days="bảng phải có 1..31 ngày",
        e_pack_empty="gói {0} không có thẻ nào", e_length="{0} phải dài 1..{1} ký tự",
        e_no_icon="client không có biểu tượng {0}", e_pick_icon="hãy chọn biểu tượng",
        e_row_item="{0}: không rõ vật phẩm {1}", e_rows="{0} phải có {1}..{2} dòng",
        e_unknown_pos="không rõ vị trí", e_unknown_type="không rõ loại vật phẩm",
        e_ep_range="EP tối thiểu phải > 0 và <= EP tối đa", e_unknown_prize="không rõ phần thưởng {0}", e_prizes="phần thưởng phải có 1..10",
        e_unknown_kind="không rõ loại sản phẩm", e_product_missing="không tìm thấy sản phẩm", e_not_changed="sản phẩm này chưa được sửa",
        e_in_use="vẫn đang được {0} dùng", e_list_item="{0}: không đặt được vật phẩm {1} ở đây", e_chain_packages="gói nối tiếp chỉ chứa gói quà",
    ),
    "ko": dict(
        lang_name="한국어", locale="ko-KR",
        ep_balance="EP 잔액", language="언어", menu="관리자 메뉴",
        nav_ringkasan="개요", nav_pemain="구단 선수", nav_tambah="선수 추가", nav_item="팩 & Bag", nav_shop="상점",
        nav_harian="출석 보상", nav_scout="스카우트", nav_log="서버 로그",
        status_default="변경 사항은 서버에 바로 저장됩니다. 게임에는 다시 실행하거나 구단 화면을 다시 불러온 뒤 표시됩니다.",
        sum_title="구단 개요", sum_lead="지금 서버에 있는 계정 상태입니다.", ep_title="EP 잔액", amount="수량",
        ep_add="EP 추가", ep_sub="EP 차감", ep_set="이 금액으로 설정", coach_line="{0}, 팀 {1}",
        f_players="구단 선수", f_team2="Tim Cadangan(2군)에 있음", f_packs="Item saya의 팩", f_bag="Bag에서 받지 않은 선물",
        f_streak="연속 로그인", days="{0}일", f_today="오늘의 보상", given="지급됨", waiting="로그인 대기 중",
        f_vip="VIP + PC방 혜택 만료일", ep_empty="먼저 EP 수량을 입력하세요.", ep_now="현재 EP 잔액: {0}",
        pl_lead="카드의 강화 등급을 바꾸거나, Tim Cadangan(2군, Tukar Scout가 여기서 선수를 고름)으로 옮기거나, 18명 스쿼드 밖의 선수를 방출합니다. 팩, 트레이드, Market에서 얻은 새 카드는 Tim inti(1군)에 들어갑니다.",
        pl_filter="목록에서 찾기", ph_player="선수 이름", pl_team2_clear="Tim Cadangan 카드를 모두 Tim inti로",
        th_role="역할", th_name="이름", th_season="시즌", th_value="EP 가치", th_team="팀", th_pos="포지션",
        reserve="2군", to_first="Tim inti로", to_second="Tim Cadangan으로", first_team="Tim inti", release="방출",
        no_player="일치하는 선수가 없습니다.", confirm_release="{0} 선수를 구단에서 방출할까요? 되돌릴 수 없습니다.",
        grade_saved="강화 등급을 저장했습니다.", moved_second="Tim Cadangan으로 옮겼습니다.", moved_first="Tim inti로 돌아왔습니다.",
        released="{0} 선수를 구단에서 방출했습니다.", team2_moved="{0}명이 Tim inti로 돌아왔습니다.",
        add_lead="카드 데이터베이스에서 검색한 뒤(능력치는 게임 및 fifaaddict와 같음) 구단에 바로 넣거나 Bag으로 보냅니다.",
        add_name="선수 이름", ph_messi="예: Messi", search="검색", add_hint="선수 이름을 2글자 이상 입력하세요.",
        on_sale="판매 중", not_on_sale="판매 안 함", add_club="구단에 추가", add_bag="Bag으로 보내기",
        no_card="그 이름의 카드가 없습니다.", found="카드 {0}장을 찾았습니다.", search_failed="검색 실패: ",
        added="{0} +{1} 선수가 구단(Tim inti)에 들어왔습니다.", gifted="{0} +{1} 선수를 Bag으로 보냈습니다.",
        gift_player="Pemain: {0}",  # a Bag title the game shows: kept in the client's language
        item_title="선수 팩 & Bag", item_lead="팩과 아이템은 Item saya로 들어갑니다. Bag 선물은 Item saya → Items에 들어가며 Terima 버튼으로 받습니다.",
        item_give="Item saya에 팩 지급", pack="팩", count="수량", item_give_btn="지급", bag_title="Bag으로 선물 보내기",
        title="제목", pack_count="팩 수량", bag_spid="선수 spid", ph_optional="선택", bag_send="Bag으로 보내기", no_pack="팩 없음",
        given_packs="{0}× {1}: Item saya에 지급했습니다.", gift_sent="선물 \"{0}\"을(를) Bag으로 보냈습니다.",
        shop_lead="상점의 모든 탭을 관리합니다. 클라이언트 아이콘으로 새 팩, 아이템, 패키지, 월정액 패키지를 만들고, 기본 상품을 수정하거나 숨기고, 가격을 정합니다. {0}에 저장되며 게임은 다음에 상점을 열 때 사용합니다.",
        shop_free="모든 상품 무료(0 EP)", shop_free_note="표의 고정 가격은 그대로 적용됩니다.",
        kind_packs_tab="선수 팩", kind_items_tab="소모품", kind_packages_tab="패키지", kind_monthly_tab="월정액 패키지", kind_lists_tab="탭 목록",
        kind_packs="팩", kind_items="아이템", kind_packages="패키지", kind_monthly="월정액 패키지",
        new_kind="새 {0}", edit_kind="{0} 수정", shop_filter="찾기", ph_shop_filter="이름 또는 itemid",
        th_icon="아이콘", th_source="출처", th_shop_price="상점 가격", th_fixed_price="고정 가격", th_shown="표시",
        src_builtin="기본", src_changed="수정됨", src_new="새 상품", chained="연속", edit="수정", delete="삭제", restore="원래대로",
        ph_default="기본값", price_saved="{0} 가격을 저장했습니다.", price_reset="{0}: 기본 가격으로 돌아갔습니다.",
        hidden_msg="{0}: 상점에서 숨겼습니다.", shown_msg="{0}: 상점에 다시 표시됩니다.", free_on="상점이 무료가 되었습니다.", free_off="상점이 다시 가격을 받습니다.",
        saved_product="{0} 저장됨(itemid {1}).", deleted="{0} 삭제됨.", restored="{0}: 원래대로 되돌렸습니다.",
        confirm_delete="{0}을(를) 삭제할까요? Item saya에 이미 있는 것은 더 이상 쓸 수 없습니다.", confirm_restore="{0}을(를) 원래대로 되돌릴까요?",
        no_product="일치하는 상품이 없습니다.",
        f_name="이름", f_icon="아이콘", icon_pick="아이콘 선택", f_desc="설명", f_seasons="시즌", seasons_hint="비우면 모든 시즌",
        f_top="상위 N장", f_ovr="최소 OVR(+1 카드 기준)", f_grade="최대 강화 등급(+1 … +N)", f_pos="포지션", any="전체",
        f_league="리그 ID", f_all="Market의 모든 카드(ID 라이선스 카드만이 아님)", f_type="종류",
        t_EP_LOTTERY="EP 카드(랜덤)", t_ITEM_LOTTERY="랜덤 박스", t_COACHNAME_CHANGE="감독 이름 변경", t_TEAM_CHANGE="팀 변경",
        t_ENHANCEMENT_BOOST="강화 부스트", t_LEAGUE_SIMULATION="리그 시뮬레이션 쿠폰",
        t_PLAYER_EXP_CAPSULE="경험치 캡슐(선수 경험치)", f_exp="경험치", f_maxlv="사용 가능한 선수 최대 레벨(비우면 전체)", f_draft="드래프트: 선수 N명 선택, 카드는 최대 강화 등급(비우면 일반 팩)",
        e_draft_season="드래프트 팩은 시즌을 하나만 골라야 합니다", f_ep_min="최소 EP", f_ep_max="최대 EP", f_prizes="보상(최대 10개)",
        f_weight="가중치", f_prize="보상", f_ep_amount="EP 수량", add_prize="보상 추가", f_boost="강화 확률 부스트(%)",
        f_contents="구성", add_row="행 추가", f_days="기간(일)", f_now="구매 즉시 지급", f_daily="매일 지급",
        remove="삭제", save="저장", cancel="취소", none_type="더 입력할 것이 없습니다.", icons_count="클라이언트 아이콘 {0}개", ph_icon="아이콘 이름 검색",
        lists_lead="Rekomendasi(추천), MP Shop, Bonus spesial(특별 보너스), Paket berantai(연속 패키지) 탭의 상품 순서입니다.",
        list_new="추천: 신상품", list_best="추천: 인기 상품", list_mp="MP Shop", list_special="특별 보너스",
        list_chained="연속 패키지", list_chained_hint="순서대로 구매합니다. 한 행이 패키지 한 묶음입니다.", list_chain_add="묶음 추가",
        list_add="추가", lists_save="목록 저장", lists_saved="탭 목록을 저장했습니다.", empty="비어 있음",
        daily_title="출석 보상", daily_lead="매일(WIB, UTC+7) 첫 로그인 때 그날의 보상이 Bag으로 들어갑니다. 연속으로 로그인하면 다음 날로 넘어가고, 하루를 빠지면 1일차부터 다시 시작합니다. 마지막 날 다음에는 처음부터 다시 시작합니다.",
        daily_grant="다음 날 보상을 지금 지급", daily_reset="연속 로그인 초기화", daily_table="보상 표", th_day="일차", day_n="{0}일차",
        drop_day="이 날 삭제", daily_add="날 추가", daily_save="표 저장", f_total="총 로그인 일수", f_last="마지막 보상",
        never="없음", f_today_wib="오늘(WIB)", daily_saved="출석 보상 표를 저장했습니다.", sent_bag="\"{0}\"을(를) Bag으로 보냈습니다.",
        confirm_reset_streak="연속 로그인을 0으로 초기화할까요?", streak_reset="연속 로그인을 초기화했습니다.",
        nav_match="경기 보상", mr_title="경기 보상", mr_lead="플레이한 모든 경기와 리그 시뮬레이션 뒤에 지급됩니다: 결과에 따른 EP와 경험치, 그리고 보상 카드 3장. 선수가 여는 카드는 카드 목록에서 가중치에 따라 무작위로 뽑힙니다. {0}에 저장되며 다음 경기부터 적용됩니다.", mr_result="결과별", th_result="결과", mr_win="승", mr_draw="무", mr_loss="패", mr_coach_exp="감독 경험치", mr_player_exp="선수당 경험치", mr_cards="보상 카드", mr_chance="확률 {0}%", mr_saved="경기 보상을 저장했습니다.",
        scout_title="스카우트(Tukar Scout)", scout_lead="방금 쓴 스카우트는 쿨다운이 끝날 때까지 잠깁니다.", th_available="다시 사용 가능",
        locked="잠김", ready="사용 가능", now="지금", no_quest="퀘스트 없음", scout_reset="모든 스카우트 쿨다운 초기화",
        scouts_ready="모든 스카우트를 다시 쓸 수 있습니다.", q_value="선수 가치 ≥", q_grade="강화 등급 ≥", q_count="수량", q_season="시즌",
        log_lead="captures/http_config.log의 마지막 줄입니다.", log_reload="로그 새로고침", log_auto="3초마다 자동 새로고침",
        failed="실패: ", load_failed="불러오기 실패: ",
        grade="강화 등급", th_market="이적시장", th_scout="스카우트", th_status="상태", th_quest="퀘스트", f_item="아이템", upgrade_point="강화 포인트",
        e_player_missing="선수를 찾을 수 없습니다", e_number="{0}: 숫자여야 합니다", e_range="{0}: {1}..{2} 사이여야 합니다",
        e_no_spid="데이터베이스에 없는 spid입니다", e_club_full="구단이 가득 찼습니다({0}명)",
        e_in_squad="18명 스쿼드에 있는 선수입니다. 먼저 Formasi에서 교체하세요", e_squad_first="18명 스쿼드의 선수는 Tim inti에 있어야 합니다",
        e_unknown_item="알 수 없는 팩 또는 아이템", e_unknown_pack="알 수 없는 팩", e_gift_empty="EP, 팩 또는 선수를 입력하세요",
        e_day="{0}: {1}", e_day_empty="비어 있음", e_table_days="표는 1..31일이어야 합니다",
        e_pack_empty="팩 {0}에 카드가 한 장도 없습니다", e_length="{0}: 1..{1}자여야 합니다",
        e_no_icon="클라이언트에 아이콘 {0}이(가) 없습니다", e_pick_icon="아이콘을 선택하세요",
        e_row_item="{0}: 알 수 없는 아이템 {1}", e_rows="{0}: {1}..{2}행이어야 합니다",
        e_unknown_pos="알 수 없는 포지션", e_unknown_type="알 수 없는 아이템 종류",
        e_ep_range="최소 EP는 0보다 크고 최대 EP 이하여야 합니다", e_unknown_prize="알 수 없는 보상 {0}", e_prizes="보상은 1..10개여야 합니다",
        e_unknown_kind="알 수 없는 상품 종류", e_product_missing="상품을 찾을 수 없습니다", e_not_changed="수정된 적 없는 상품입니다",
        e_in_use="아직 {0}에서 사용 중입니다", e_list_item="{0}: 아이템 {1}은(는) 여기에 넣을 수 없습니다", e_chain_packages="연속 패키지에는 패키지만 넣을 수 있습니다",
    ),
}


def check_i18n():
    """Self-check (python admin.py; test_league.py runs it too): every language has the keys and
    {0}.. placeholders of "id", and every key admin/index.html and the errors above name exists."""
    ref, holes = I18N["id"], lambda s: sorted(re.findall(r"\{\d+\}", s))
    for lang, tb in I18N.items():
        assert tb.keys() == ref.keys(), f"{lang}: keys differ from id: {sorted(tb.keys() ^ ref.keys())}"
        bad = [k for k in tb if holes(tb[k]) != holes(ref[k])]
        assert not bad, f"{lang}: {{0}} placeholders differ from id: {bad}"
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    with open(__file__, encoding="utf-8") as f:
        me = f.read()
    used = (re.findall(r'data-i18n(?:-ph|-aria)?="(\w+)"', page) + re.findall(r'\bt\("(\w+)"[,)]', page)
            + re.findall(r'AdminError\("(\w+)"', me) + re.findall(r'\("(\w+)",\)', me))
    missing = sorted(set(used) - ref.keys())
    assert not missing, f"keys used but not in the tables: {missing}"


if __name__ == "__main__":
    check_i18n()
    print(f"I18N OK: {', '.join(I18N)} ({len(I18N['id'])} keys each)")
