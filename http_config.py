"""HTTP config/publisher service stub for FO3ID.

The client requests these relative paths (found in client memory):
    /info/server/config        -> expected: server list / endpoints config
    /game/my/ipaddress         -> expected: client's public IP echo
    /publisher/garena/sign     -> publisher token sign/verify
    /publisher/nexon/2ndauth   -> secondary auth
    /telemetry/gameconnection  -> telemetry sink (can be a no-op)
    /shop/cash/charge/url, /shop/cash/history/url -> cash shop URLs

Phase 1: log every request (method, path, query, headers, body) and return a minimal
placeholder so we can see which endpoint the client hits first and what it expects.
The real response shapes are unknown until captured — every handler is a guess.

Usage: python -I http_config.py [port=8080] [--tls]
Default port 8080 to avoid colliding with a local Apache on :80.

--tls serves HTTPS with certs/server.pem. fifazf.exe calls a hardcoded
https://APSEODESK172 (port 443) for /info/server/locale etc. — no launch arg
overrides it — so run `http_config.py 443 --tls` and map APSEODESK172 to
127.0.0.1 in the hosts file.
"""
import bisect, collections, copy, functools, gzip, http.server, math, os, random, re, sqlite3, ssl, statistics, sys, threading, time
from contextlib import closing

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # `python -I` leaves the script dir off sys.path
import gen_teams
TLS = "--tls" in sys.argv
_args = [a for a in sys.argv[1:] if a != "--tls"]
PORT = int(_args[0]) if _args else 8080
LOG = os.path.join(HERE, "captures", "http_config.log")
CERT = os.path.join(HERE, "certs", "server.pem")  # self-signed, CN/SAN APSEODESK172
os.makedirs(os.path.dirname(LOG), exist_ok=True)

import json

# Where this service tells the client the game servers live.
REDIR_HOST, REDIR_PORT = "127.0.0.1", 28000
NOTI_HOST, NOTI_PORT = "127.0.0.1", 28001

# --------------------------------------------------------------------------- #
# Endpoint bodies — TENTATIVE. The real response format (XML vs JSON, field
# names, the token/sign scheme) is unknown: the client has not been captured
# reaching these (XignCode blocks it earlier — see README). These return minimal
# plausible JSON so the client has *something* to parse; correct each shape from
# a capture. Every request is logged regardless, which is the point for now.
# --------------------------------------------------------------------------- #

def _json(obj):
    return ("application/json", json.dumps(obj).encode())


def ep_server_config(query, body):
    return _json({
        "redirector": {"host": REDIR_HOST, "port": REDIR_PORT},
        "notification": {"host": NOTI_HOST, "port": NOTI_PORT},
        "region": "ID",
        "status": "ok",
    })


def ep_locale(query, body):
    # First call fifazf.exe makes. Body "OK" -> JSON_PARSING_ERROR in-game; {"result": true}
    # passes. `language` must be a WebCache.setBaseUrl key (kor eng chi vie tha ind jpn,
    # default kor): "id" crashed the UI (the old black screen); "ind" = Indonesian, its
    # externalAssets/language_ind.big is in the client cache. Publisher (Garena) is chosen
    # by launch args `region id token <t>`, not by this response.
    # `url` = WebCache base for externalAssets (crests, uniforms, player cards...). Without
    # it the client uses the dead Garena CDN, every refresh fails and crests show
    # "PLACE HOLDER" even though the files sit in its own _cache. Served by cdn_file().
    return _json({"result": True, "language": LANGUAGE, "url": f"https://APSEODESK172/{CDN_PREFIX}"})


LANGUAGE = os.environ.get("FO3_LANGUAGE", "ind")


GAME = os.environ.get("FO3_GAME", r"D:\FO3ID\32795")  # the FO3 ID client install
# The client's own downloaded copy of the Garena CDN (externalAssets/...).
ASSETS = os.environ.get("FO3_ASSETS", os.path.join(GAME, "_cache", "games", "fo3id"))
CDN_PREFIX = "cdn/"


def cdn_file(rel):
    """(content-type, bytes) of ASSETS/rel, or None (-> 404, client shows its default)."""
    f = os.path.normpath(os.path.join(ASSETS, rel))
    if not f.startswith(os.path.normpath(ASSETS) + os.sep) or not os.path.isfile(f):
        return None
    ctype = {".png": "image/png", ".jpg": "image/jpeg", ".swf": "application/x-shockwave-flash"}
    with open(f, "rb") as fh:
        return (ctype.get(os.path.splitext(f)[1].lower(), "application/octet-stream"), fh.read())


def ep_server_time(query, body):
    # TimerUtil.getTime: retries every second (and holds the bootflow) until `timestamp`
    # (ms, fed to new Date()) is present. timezone guessed as JS getTimezoneOffset() for
    # WIB (UTC+7) — the backend looked like Node/Express.
    return _json({"timestamp": int(time.time() * 1000), "timezone": -420})


def ep_my_ip(query, body):
    # real HTTP PUT from the lobby; every reply is JSON-parsed
    return _json({"result": True, "ipaddress": "127.0.0.1"})


def ep_garena_sign(query, body):
    # Accept any token for local offline use; echo a success + a fake signed token.
    return _json({"result": "ok", "token": "LOCAL-SIGNED-TOKEN", "uid": 1})


def ep_nexon_2ndauth(query, body):
    return _json({"result": "ok", "passport": "LOCAL-PASSPORT"})


def ep_telemetry(query, body):
    # Client JSON-parses every reply; plain "OK" -> JSON_PARSING_ERROR in-game.
    return _json({"result": True})


# The starter song (music/starter.mp3) lives in the game's own EA Trax playlist as TrackID 1,
# put there by tools/eatrax_song.py; the server does not play music.


def ep_empty(query, body):
    return _json({})


def ep_shop_url(query, body):
    return _json({"url": "about:blank"})


# ponytail: one local account kept in a JSON file; a real multi-user store comes later.
STATE = os.path.join(HERE, "gamedata", "state.json")
# Handlers read-modify-write state.json; game requests and the admin page (admin.py) take this
# so one never reads a half-written file or overwrites the other's change.
STATE_LOCK = threading.Lock()


def _state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"coaches": [], "defaultcoachid": "", "teams": {}}


def _save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(st, f)


def coach_id(slot):
    return f"{slot + 1:024x}"  # Mongo-style _id


def front_player(me):
    """coachlist[].frontplayer: the 3D player on the manager select screen. Native LoadFrontPlayers
    (0x9A09E0) reads staticdata.preferredposition1 (0 = goalie -> kit.goalie), kit.home|goalie.id,
    spid, id (asCString: a string) and jersey; with no frontplayer the game shows its own default
    (a Barcelona player). The club's most valuable player (user: "pemain yang muncul dengan harga
    tertinggi")."""
    team = me["team"]
    p = max(team["players"], key=lambda x: x.get("price", 0), default=None)
    if p is None:
        return None
    with closing(_db()) as c:
        row = c.execute("SELECT preferredposition1 FROM players WHERE spid = ?", (int(p["spid"]),)).fetchone()
    return {"id": str(p["_id"]), "spid": int(p["spid"]), "jersey": p.get("jersey", 0),
            "staticdata": {"preferredposition1": row[0] if row else 25},
            "kit": {"home": {"id": me["teamid"] << 5}, "goalie": {"id": me["teamid"] << 5 | 2}}}


def ep_coaches(query, body):
    # StartupCoachCreationScreen: coachlist entries need _id, slot, name, state "active"
    # ("postpone" = deleted, restorable until hideat; recoveryperiod s goes in the delete notice).
    # initializeMyCoach also shows team name/crest from summary and teamvalue.val, same
    # values as the lobby HUD (coach_me); native LoadFrontPlayers reads teamid + frontplayer.
    st = _state()
    if purge_deleted_coaches(st):
        _save(st)
    def entry(c):
        me = coach_me(st, c["slot"])
        fp = front_player(me)
        return dict(c, summary=me["summary"], teamvalue={"val": sum(p["price"] for p in me["team"]["players"])},
                    levelinfo=me["levelinfo"], teamid=me["teamid"], **({"frontplayer": fp} if fp else {}),
                    recoveryperiod=COACH_RECOVERY, **({"hideat": w3c(c["deleteat"])} if "deleteat" in c else {}))
    usable = {c["_id"] for c in st["coaches"] if c.get("state", "active") == "active"}
    return _json({"coachlist": [entry(c) for c in st["coaches"]],
                  "defaultcoachid": st["defaultcoachid"] if st["defaultcoachid"] in usable else ""})


def ep_new_team(slot, query, body):
    # POST /coach/<slot>/new/step/3 {"id": teamid, "spids": [...]}: the client passes this
    # body on as the new club and reads data.team.players ("could not take the random
    # players!" otherwise). Built from gen_teams.py's roster file for that team.
    req = json.loads(body or b"{}")
    chosen = set(req.get("spids", []))
    team = roster(int(req.get("id") or 0))["team"]
    team["players"] = [p for p in team["players"] if p["spid"] in chosen]
    team["squad"]["positions"] = [p for p in team["squad"]["positions"] if p["spid"] in chosen]
    fix_formation(team, int(req.get("id") or 0))
    st = _state(); st["teams"][str(slot)] = team; _save(st)
    return _json({"result": True, "team": team})


def ep_create_coach(slot, query, body):
    # POST /coach/<slot> {"id": teamid, "coachName"}: needs body.result
    req = json.loads(body or b"{}")
    st = _state()
    purge_deleted_coaches(st)
    st["coaches"] = [c for c in st["coaches"] if c["slot"] != slot] + [{
        "_id": coach_id(slot), "slot": slot, "name": req.get("coachName", ""), "state": "active",
        # StartupCoachCreationScreen.initializeMyCoach reads teamvalue.val, levelinfo.level, summary
        "teamid": req.get("id"), "teamvalue": {"val": 0}, "levelinfo": {"level": 1}, "summary": {},
        "appat": w3c(time.time())}]  # coach_me career.appat: the manager's start date
    _save(st)
    return _json({"result": True})


# Deleting a manager (StartupCoachCreationScreen > Delete): PUT /coach/<slot>/postponed puts it in
# state "postpone" until hideat; "Kembalikan manager" = DELETE /coach/<_id>/postponed undoes it.
# Once hideat has passed CoachUtil.shouldDeleteCoach shows the slot as free ("Buat manager baru").
COACH_RECOVERY = 300  # s a deleted manager can still be restored (the real game: 72 h)


def purge_deleted_coaches(st):
    """Drop managers whose restore time is over, with their club. The account-wide club data
    (league, cups, market offers, last match, trade) belongs to the default manager's club."""
    gone = [c for c in st["coaches"] if c.get("state") == "postpone" and c.get("deleteat", 0) <= time.time()]
    for c in gone:
        st["coaches"].remove(c)
        st["teams"].pop(str(c["slot"]), None)
        if c["_id"] == st["defaultcoachid"]:
            st["defaultcoachid"] = ""
            for k in ("league2", "cups", "offers", "match", "trade"):
                st.pop(k, None)
    return gone


def ep_coach_postponed(key, query, body):
    """PUT /coach/<slot>/postponed: delete a manager; DELETE /coach/<_id>/postponed: restore it."""
    st = _state()
    purge_deleted_coaches(st)
    c = next((c for c in st["coaches"] if key in (str(c["slot"]), c["_id"])), None)
    if c is None:
        reply = {"result": False, "reason": "already removed"}  # restore: COACH_CREATION_RESTORE_ERROR
    elif json.loads(body or b"{}").get("_method") == "DELETE":
        c["state"] = "active"
        c.pop("deleteat", None)
        reply = {"result": True}
    else:
        c["state"] = "postpone"
        c["deleteat"] = time.time() + COACH_RECOVERY
        reply = {"result": True}
    _save(st)
    return _json(reply)


POS_SUB = 28  # Enums.PLAYERPOSITION: 0..27 pitch positions, 28 SUB, 29.. RESERVE


# OptionManager.applySoundSetting hands native volume * Master (each 0..10) for Commentary,
# PAVolume, PlayerCalls, SFX, Crowd and BGM; a missing key is NaN = silent (no music).
SOUND_DEFAULTS = {"Master": 10, "Commentary": 10, "PAVolume": 10, "PlayerCalls": 10, "SFX": 10, "Crowd": 10, "BGM": 10}

# Opsi > Kamera setting (OptionCameraSettingScreen) shows and steps OptionManager.cameraOption
# as-is: Camera 0..6 (F3..F9: TELE_BROADCAST, TELE, COOP, DYNAMIC, ENDTOEND, PRO, BROADCAST),
# CamDetail (Customise off/on), CamHeight/CamZoom (0..20, the custom gauges of every camera but Pro) and
# CamProZoom/CamProSpeed/CamProSwing (0..20, Pro only). OptionManager fills none of them: a
# missing key showed no value and could not be stepped (NaN + 1, issue #24). Defaults are
# OptionManager.OPTION_DEFAULT_CAM_* (10); Camera 0 = what native got from the missing key.
CAMERA_DEFAULTS = {"Camera": 0, "CamDetail": 0, "CamHeight": 10, "CamZoom": 10,
                   "CamProZoom": 10, "CamProSpeed": 10, "CamProSwing": 10}

# Opsi > Kontrol (OptionControlSettingScreen) edits OptionManager.controlOption in place and
# Konfirmasi applies it (applyControlSetting -> native onOptionControlSettingChanged) and sends it
# back. With no controlOption it edits a throwaway copy, so key changes were never applied or
# saved; with {} (no key lists) the native input thread crashes. So /account always carries a full
# one: the screen's own defaults (Controller 0 = keyboard; OptionManager.setDefaultControllerSetting,
# slots 5-8 copied from 1-4 like the screen does). Key codes are Flash keyCodes, 256-258 mouse.
_WASD = [87, 65, 68, 83, 81, 90, 67, 69]
_ARROWS = [38, 40, 37, 39, 256, 257, 258]
_KEY_ATT = (_WASD, _WASD, [69, 65, 68, 83, 81, 90, 67, 87], [80, 75, 186, 76, 73, 190, 191, 79])
_KEY_DEF = (_WASD, [87, 65, 83, 81, 68, 90, 67, 69], _KEY_ATT[2], _KEY_ATT[3],
            [87, 65, 68, 32, 81, 90, 67, 69], [87, 65, 83, 32, 68, 90, 67, 69],
            [69, 65, 68, 32, 81, 90, 67, 87], [80, 75, 186, 32, 73, 190, 191, 79])
_KEY_MOV = (_ARROWS, _ARROWS, _ARROWS, [87, 83, 65, 68, 256, 257, 258])
_JOY = ([4, 3, 2, 1, 5, 7, 6, 8], [4, 2, 3, 1, 5, 6, 8, 7], [4, 3, 2, 1, 5, 7, 6, 8])
_JOY_MOV = ([9, 11, 10], [9, 11, 10], [11, 9, 10])
CONTROL_DEFAULTS = {"Controller": 0, "Type": 0,
                    **{f"KeyAttType{i + 1}": _KEY_ATT[i % 4] for i in range(8)},
                    **{f"KeyDefType{i + 1}": _KEY_DEF[i] for i in range(8)},
                    **{f"KeyMovType{i + 1}": _KEY_MOV[i % 4] for i in range(8)},
                    **{f"Joy{k}Type{i + 1}": (_JOY_MOV if k == "Mov" else _JOY)[i] for k in ("Att", "Def", "Mov") for i in range(3)}}


def control_option_ok(c):
    """True if `c` has every controlOption field with the right shape (ints, non-empty int lists)."""
    def ok(v, want):
        if isinstance(want, list):
            return isinstance(v, list) and bool(v) and all(isinstance(x, int) for x in v)
        return isinstance(v, int)
    return isinstance(c, dict) and all(ok(c.get(k), v) for k, v in CONTROL_DEFAULTS.items())


def account_option():
    """The account's `option`: responses/account_base.json's, with the options the client saved
    through PUT /account/option layered over it."""
    with open(os.path.join(RESPONSES, "account_base.json"), encoding="utf-8") as f:
        opt = json.load(f)["option"]
    opt.update(_state().get("option", {}))
    opt["soundOption"] = {**SOUND_DEFAULTS, **(opt.get("soundOption") or {})}
    # a gauge stepped while it was NaN came back as null/NaN: such a value gets the default
    opt["cameraOption"] = {**CAMERA_DEFAULTS, **{k: v for k, v in (opt.get("cameraOption") or {}).items()
                                                 if isinstance(v, (int, float)) and math.isfinite(v)}}
    if not control_option_ok(opt.get("controlOption")):
        opt["controlOption"] = CONTROL_DEFAULTS
    return opt


def ep_account(query, body):
    """GET /account (AccountProxy.accountData)."""
    with open(os.path.join(RESPONSES, "account_base.json"), encoding="utf-8") as f:
        acc = json.load(f)
    acc["option"] = account_option()
    return _json(acc)


def ep_account_option(query, body):
    """PUT /account/option {soundOption, screenOption, controlOption, chatHotKeyOption, aiOption,
    cameraOption} (Opsi > Konfirmasi, leaving a match). A controlOption is kept only when it is
    complete (see CONTROL_DEFAULTS); otherwise the one saved before stays.
    The reply must carry the saved options as resources[0].body (AccountCommand.saveGameOption
    sets accountProxy.gameOptions from it, and that runs OptionManager.setOptions, which also
    takes the backup restoreOptions goes back to on every zone change). With no resources the
    callback threw TypeError #1010, so entering or leaving a match put back the options from
    login: keyboard instead of the gamepad, the old camera (issue #21)."""
    req = json.loads(body or b"{}")
    st = _state()
    old = st.get("option", {}).get("controlOption")
    st["option"] = {k: v for k, v in req.items() if k.endswith("Option") and k != "controlOption"}
    ctl = req.get("controlOption") if control_option_ok(req.get("controlOption")) else old
    if ctl:
        st["option"]["controlOption"] = ctl
    _save(st)
    return _json({"result": True, "resources": [{"uri": "/account/option", "body": account_option()}]})


def apply_squad(team, req):
    """Save a squad PUT {squad:{positions,formation,workrate}, kickers, captain} (instance ids)
    to a stored team. A client still holding old instance ids (e.g. from before a card
    migration) must not wipe the XI: False, team unchanged, unless it has 11 known starters."""
    sq = req.get("squad") or {}
    spid_of = {iid(p): p["spid"] for p in team["players"]}
    positions = [{"id": str(p["id"]), "spid": spid_of[str(p["id"])], "pos": p["pos"],
                  **({"starting": p["starting"]} if p.get("starting") else {})}
                 for p in sq.get("positions") or [] if str(p.get("id")) in spid_of and p.get("pos", 99) <= POS_SUB]
    if sum(p["pos"] < POS_SUB for p in positions) != 11:
        return False
    idx = req.get("presetidx")
    if isinstance(idx, int) and 0 <= idx < PRESET_SQUADS and idx != team.get("presetidx", 0):
        # a switch to another of Squad A / B / C (SquadScreenHandler sends the picked one with
        # its presetidx): the squad being left keeps its slot
        saved = (team.get("presets") or []) + [None] * PRESET_SQUADS
        saved[team.get("presetidx", 0)] = copy.deepcopy(team["squad"])
        team["presets"], team["presetidx"] = saved[:PRESET_SQUADS], idx
    team["squad"]["positions"] = positions
    for k in ("formation", "workrate"):
        if k in sq:
            team["squad"][k] = sq[k]
    if str(req.get("captain")) in spid_of:
        team["squad"]["captain"] = str(req["captain"])
    if req.get("kickers") and all(str(k) in spid_of for k in req["kickers"] if k):
        # a slot per KICKER_TYPES entry: dropping an empty one shifted the penalty taker (issue #8)
        team["squad"]["kickers"] = [str(k) if k else "" for k in req["kickers"]][:KICKERS]
    return True


def ep_coach_squad(query, body):
    """PUT /coach/me/squad {squad:{positions,formation,...}, kickers, captain} from Tim > Formasi."""
    st = _state(); slot = _default_slot(st); team = st["teams"].get(str(slot))
    if team is not None and apply_squad(team, json.loads(body or b"{}")):
        _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


def ep_match_squad(mid, side, query, body):
    """PUT /match/<id>/side/<side>/squad {squad, kickers, captain} from the pre-match squad screen
    (SquadScreenHandler.sendSquadToServer: a swap, a sub, a formation). It had no handler, so the
    generic {result: true} brought no new squad back and every change undid itself (issue #16).
    Saved to my club like Tim > Formasi; my side is rebuilt from it and comes back in the match
    resource, which the screen reads (side.<mine>.team.squad). result false shows reason."""
    st = _state(); slot = _default_slot(st); match = st.get("match") or {}
    s = (match.get("side") or {}).get(side) if match.get("id") == mid else None
    team = st["teams"].get(str(slot))
    if not s or not s["players"] or team is None or not apply_squad(team, json.loads(body or b"{}")):
        return _json({"result": False, "reason": "PLAYERLIST_CHANGEPLAYER_FAIL_POPUP_INFO_UNUSABLEPLAYER"})
    s.update(match_side(team, s["team"]["teamid"], s["players"][0], s["tactics"]), ready=s["ready"])
    _save(st)
    return _json({"result": True, "resources": [{"uri": f"/match/{mid}", "body": match}] + coach_me_resources(st, slot)})


KICKERS = 5  # squad.kickers slots, Enums.KICKER_TYPES: left corner, right corner, free kick, penalty, free kick 2


def ep_team_role(kicker, query, body):
    """PUT /game/my/team/captain {id} and PUT /game/my/team/kickers/<KICKER_TYPES index> {id}
    from Tim > Peran (TeamManagementPlayerRolesTabPage.onPlayerSelect; issue #8: both were
    missing, so a new captain or penalty taker was never saved). id = a card instance of my club."""
    req = json.loads(body or b"{}")
    st = _state(); slot = _default_slot(st); team = st["teams"].get(str(slot))
    pid = str(req.get("id"))
    if team is None or pid not in {iid(p) for p in team["players"]}:
        return _json({"result": False})
    sq = team["squad"]
    if kicker is None:
        sq["captain"] = pid
    else:
        sq["kickers"] = ([str(k) for k in sq.get("kickers") or []] + [""] * KICKERS)[:KICKERS]
        sq["kickers"][kicker] = pid
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


def roster(teamid):
    """{summary, team} of a club: the gen_teams.py roster file if there is one, else built
    the same way straight from fifadb (league opponents)."""
    f = os.path.join(RESPONSES, f"static_info_authentic_team_all_{teamid}.json")
    if os.path.isfile(f):
        with open(f) as fh:
            return json.load(fh)
    with closing(_db()) as c:
        return gen_teams.team(c, teamid) or {"summary": {}, "team": {"players": [], "squad": {"positions": [], "kickers": []}}}


def roster_team(teamid):
    """A club as a stored team, for AI opponents."""
    return roster(teamid)["team"]


def match_side(raw, teamid, user=None, tactics=None):
    """match.side.<left|right>: PlayerListUtil.generateCaptainFromMatchInfo reads side.team
    {teamid, squad, players}, side.players (the users: id, name, levelinfo), MatchProxy
    fetchMatchSide* read squad, tactics, ready. tactics is the preset ARRAY (as
    /game/my/tactic/all): native 0x949170 iterates it ({id, bus, cc, def, teammentality})."""
    team = owned_team(raw)
    # team color for the user's side only: an AI side is a whole club (+4 for free)
    team["teamcolors"] = active_teamcolors(team) if user else []
    team.update(teamid=teamid, summary=team_summary(team, teamid), kit=team_kit(teamid))
    if user:  # the pre-match squad screen's formation list (side.<mine>.team.formations; was empty, issue #16)
        team["formations"] = team_formations(teamid)
    # ready: a user side starts unready -- MatchController.sendReady skips the PUT .../ready
    # (no kick-off) when isMySideReady is already true; AI sides are always ready.
    return {"team": team, "squad": team["squad"], "players": [user] if user else [],
            "tactics": tactics or [default_tactic(0)], "ready": user is None, "kit": team_kit(teamid), "club": {}}


# gamesettings.halfLength, in 1/10 minute per half (the game setting screen shows
# halfLength/10*2 "menit"): 30 = a 6-minute match.
HALF_LENGTH = int(os.environ.get("FO3_HALF_LENGTH", "30"))


def new_match(mtype, left, right, **extra):
    """A /match/<id> resource (MatchProxy, base uri /match). MatchController.onMatchChangeReceived
    runs processMatch* over: side.X {ready, club, players, squad, team{teamid, players, captain,
    kit, summary.league}}, elo.X.rating, gamesettings {kit, ball, stadium, tod, weather,
    halfLength, difficulty}, result, reward, boostweekid, stage (created|squad|playing|canceled).
    These run inside a native->AS3 callback: a TypeError there aborts the client (0xDEAD)."""
    mid = f"{int(time.time()):08x}{os.urandom(8).hex()}"  # Mongo-style id
    lt, rt = left["team"]["teamid"], right["team"]["teamid"]
    match = {"id": mid, "type": mtype, "created": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
             "stage": "created", "side": {"left": left, "right": right},
             "elo": {"left": {"rating": 1000}, "right": {"rating": 1000}},
             "result": None, "reward": None, "boostweekid": 0,
             # native ApplyGameSettings gets this object as-is.
             # kit: [left uniform id, right uniform id] as STRINGS: AS3 reads them in
             # processMatchSideStandingPlayerResource, native (0x9480D0) with asCString
             # home: Boolean (MatchProxy.isLeftTeamHome = gamesettings.home as Boolean)
        "gamesettings": {"home": True, "simulated": False, "canHaveReferee": False,
                              "stadiumchange": False, "timechange": False, "weatherchange": False,
                              "matchtimechange": False, "cardstrictness": 0, "foulstrictness": 0,
                              # kit: per side the KIT TYPE ("home"/"away"); native (0x948260) loads
                              # side kit.availables[<type>].id -- uniform ids here = checkerboard kits.
                              # ball.availables feeds MatchProxy.ballsDataProvider; empty -> the
                              # game setting screen's ball stepper reads item 0 = null (UI error).
                              # 0 = the ball the practice match loads (id -> db.ball model).
                              "kit": ["home", "away"],
                              "ball": {"id": 0, "availables": [{"id": 0}]},
                              # stadium 112 = the lobby stadium (data/sceneassets/stadium/stadium_112.rx3
                              # is known to load); null -> crash while loading the GAME scene
                              "stadium": 112, "tod": 0, "weather": 0, "difficulty": 0,
                              "halfLength": HALF_LENGTH,
                              # the rest is what native ApplyGameSettings (0x946FD0) reads; values are
                              # its own defaults (0x959050). Missing gameSpeed broke the match clock.
                              "gameSpeed": 1, "crowd": 100, "pitchWear": 1, "refereeIdSelector": 845,
                              "subRefereeIds": [0, 0], "disableMomentum": False, "bookingsOn": True,
                              "offsidesOn": True, "injuriesOn": True, "foulsOn": True, "fatigueOn": True,
                              "subOnBench": 5, "availableSubs": 3, "drawMode": 0, "gameType": mtype,
                              "shootoutmode": False, "prevScore": {"home": 0, "away": 0}}}
    match.update(extra)
    return match


def ep_match_campaign(query, body):
    """POST /match/campaign (tutorial > Training Ground): MatchController
    .onMatchPracticeResponseReceived registers resources[] and fires ON_PRACTICE_STARTED with
    the match body -> ApplyGameSettings + StartSingleMatch (a local match in the client)."""
    st = _state(); slot = _default_slot(st); me = coach_me(st, slot)
    user = {"id": me["id"], "name": me["name"], "levelinfo": me["levelinfo"]}
    ai = 243 if me["teamid"] != 243 else 241
    # type must be a non-PvP one (MatchController.isPvPMatchType: League_league, Cup_PvE,
    # WorldCup_PvE, WorldCup_Live, League_2_league, League_2_league_MGR); anything else makes
    # stage "created" call connectToTheSession -> native LobbyManager::ConnectSession, which
    # needs relayServer.address (crash without it).
    match = new_match("League_league", match_side(st["teams"][str(slot)], me["teamid"], user, _tactics(st)[1]),
                      match_side(roster_team(ai), ai))
    return _json({"result": True, "resources": [{"uri": f"/match/{match['id']}", "body": match}]})


def roster_summary(teamid):
    """Static team info (name, league, nation, rival) written by gen_teams.py."""
    s = roster(teamid).get("summary", {})
    return {k: s[k] for k in ("name", "league", "nation", "rival") if k in s}


# --------------------------------------------------------------------------- #
# Player cards. Ratings come from the client's own fifadb, EP prices from fifaaddict.com's
# FO3 DB (Indonesia server, grade +1; gamedata/fa_prices.json, see tools/fa_sync.py).
# --------------------------------------------------------------------------- #
# all-attribute boost by grade +0..+10 (= responses/static_db_PLAYERGRADE.json): fifaaddict's
# playerEnchantList, e.g. World Best Neymar 83 base shows 88 at +1 and 93 at +5
GRADE_BOOST = (0, 5, 6, 7, 8, 10, 12, 14, 17, 20, 24)
# EP price of grade g relative to +1: geometric mean over 16 fifaaddict cards (Indonesia server)
GRADE_PRICE = (0, 1, 2.65, 7.1, 19.6, 53, 162, 420, 1090, 2680, 6290)
FA_PRICES = os.path.join(HERE, "gamedata", "fa_prices.json")
_FA = None
_OVR = {}


def fa_prices():
    """{spid: Indonesia-server EP price at +1 (0 = listed on fifaaddict without a price)};
    {} when the file is missing."""
    global _FA
    if _FA is None:
        try:
            with open(FA_PRICES) as f:
                _FA = {int(k): int(v) for k, v in json.load(f).items()}
        except OSError:
            _FA = {}
    return _FA


# The rating the client shows for a card ("Atribut"/OVR, as on fifaaddict) is Enums.calcPosOvr
# at its preferredposition1: floor(sum(stat * weight) / 100) with STAT_POSOVRS weights below
# (fifadb's overallrating column runs ~5 higher for 2017 cards). POS_ROLE[Enums.PLAYERPOSITION].
ROLE_WEIGHTS = {
    "GK": {"gkdiving": 21, "gkhandling": 21, "gkkicking": 5, "gkpositioning": 21, "gkreflexes": 21, "reactions": 11},
    "SW": {"aggression": 8, "ballcontrol": 5, "headingaccuracy": 10, "jumping": 4, "marking": 15, "reactions": 5,
           "shortpassing": 5, "slidingtackle": 15, "standingtackle": 15, "strength": 10, "interceptions": 8},
    "WB": {"acceleration": 4, "ballcontrol": 8, "crossing": 12, "dribbling": 4, "marking": 7, "reactions": 8, "shortpassing": 10,
           "slidingtackle": 11, "sprintspeed": 6, "stamina": 10, "standingtackle": 8, "interceptions": 12},
    "FB": {"acceleration": 5, "ballcontrol": 7, "crossing": 9, "headingaccuracy": 4, "marking": 8, "reactions": 8, "shortpassing": 7,
           "slidingtackle": 14, "sprintspeed": 7, "stamina": 8, "standingtackle": 11, "interceptions": 12},
    "CB": {"aggression": 7, "ballcontrol": 4, "headingaccuracy": 10, "jumping": 3, "marking": 14, "reactions": 5, "shortpassing": 5,
           "slidingtackle": 17, "sprintspeed": 2, "standingtackle": 10, "strength": 10, "interceptions": 13},
    "DM": {"aggression": 5, "ballcontrol": 10, "longpassing": 10, "marking": 9, "reactions": 7, "shortpassing": 14, "slidingtackle": 5,
           "stamina": 6, "standingtackle": 12, "strength": 4, "interceptions": 14, "vision": 4},
    "WM": {"acceleration": 7, "ballcontrol": 13, "crossing": 10, "dribbling": 15, "finishing": 6, "longpassing": 5, "positioning": 8,
           "reactions": 7, "shortpassing": 11, "sprintspeed": 6, "stamina": 5, "vision": 7},
    "CM": {"ballcontrol": 14, "dribbling": 7, "finishing": 2, "longpassing": 13, "longshots": 4, "positioning": 6, "reactions": 8,
           "shortpassing": 17, "stamina": 6, "standingtackle": 5, "interceptions": 5, "vision": 13},
    "AM": {"acceleration": 4, "agility": 3, "ballcontrol": 15, "dribbling": 13, "finishing": 7, "longpassing": 4, "longshots": 5,
           "positioning": 9, "reactions": 7, "shortpassing": 16, "sprintspeed": 3, "vision": 14},
    "CF": {"acceleration": 5, "ballcontrol": 15, "dribbling": 14, "finishing": 11, "headingaccuracy": 2, "longshots": 4, "positioning": 13,
           "reactions": 9, "shortpassing": 9, "shotpower": 5, "sprintspeed": 5, "vision": 8},
    "W": {"acceleration": 7, "agility": 3, "ballcontrol": 14, "crossing": 9, "dribbling": 16, "finishing": 10, "longshots": 4,
          "positioning": 9, "reactions": 7, "shortpassing": 9, "sprintspeed": 6, "vision": 6},
    "ST": {"acceleration": 4, "ballcontrol": 10, "dribbling": 7, "finishing": 18, "headingaccuracy": 10, "longshots": 3, "positioning": 13,
           "reactions": 8, "shortpassing": 5, "shotpower": 10, "sprintspeed": 5, "strength": 5, "volleys": 2},
}
POS_ROLE = "GK SW WB FB CB CB CB FB WB DM DM DM WM CM CM CM WM AM AM AM CF CF CF W ST ST ST W".split()
POSOVR = "(CASE p.preferredposition1 {} END)".format(" ".join(  # SQL: client rating of row p
    f"WHEN {i} THEN ({' + '.join(f'{w} * p.{k}' for k, w in ROLE_WEIGHTS[r].items())}) / 100" for i, r in enumerate(POS_ROLE)))


def card_ratings(spids):
    """{spid: (client rating, fifadb overallrating)} (cached)."""
    spids = [int(s) for s in spids]
    need = [s for s in set(spids) if s not in _OVR]
    if need:
        with closing(_db()) as c:
            for i in range(0, len(need), 500):
                chunk = need[i:i + 500]
                rows = {s: (o, d) for s, o, d in c.execute(
                    f"SELECT p.spid, {POSOVR}, p.overallrating FROM players p WHERE p.spid IN ({','.join('?' * len(chunk))})", chunk)}
                _OVR.update({s: rows.get(s, (0, 0)) for s in chunk})
    return {s: _OVR[s] for s in spids}


STAT_COLS = sorted(set().union(*ROLE_WEIGHTS.values()))
_STATS = {}


def card_stats(spids):
    """{spid: {stat: fifadb value}} of the stats any position rating uses (cached)."""
    need = [s for s in {int(s) for s in spids} if s not in _STATS]
    if need:
        with closing(_db()) as c:
            for i in range(0, len(need), 500):
                chunk = need[i:i + 500]
                rows = {r[0]: dict(zip(STAT_COLS, r[1:])) for r in c.execute(
                    f"SELECT spid, {', '.join(STAT_COLS)} FROM players WHERE spid IN ({','.join('?' * len(chunk))})", chunk)}
                _STATS.update({s: rows.get(s, dict.fromkeys(STAT_COLS, 0)) for s in chunk})
    return {int(s): _STATS[int(s)] for s in spids}


def card_ovrs(spids):
    """{spid: rating the client shows}."""
    return {s: r[0] for s, r in card_ratings(spids).items()}


def card_ovr(spid):
    return card_ovrs([spid])[int(spid)]


def grade_of(p):
    """+0..+10. A club's starting players (stored without a grade) are +0: no market value
    (CoachProxy.expandTeam counts only grade > 0), not sellable; bought/packed cards start at +1."""
    return min(10, max(0, int(p.get("grade") or 0)))


def player_ovr(p):
    """Card rating plus its enhancement boost."""
    return card_ovr(p["spid"]) + GRADE_BOOST[grade_of(p)]


def sig3(x):
    x = int(x)
    return round(x, 2 - len(str(x))) if x >= 1000 else x


def price_formula(ovr):
    """Fallback without gamedata/fa_prices.json: an early least-squares fit of fifaaddict's
    Indonesia-server prices on the client rating: exp(2.53 + 0.1113 * ovr), 65 ~ 17k, 85 ~ 160k."""
    return sig3(max(1000, math.exp(2.53 + 0.1113 * ovr)))


@functools.lru_cache(maxsize=None)
def market_spids():
    """Every tradeable card (Market, packs, trades): each one the client's own Market search can
    show (TransferUtil: permid.transferable = 1 and a namesind row; season 0 = engine cards) plus
    each one fifaaddict lists. fifaaddict alone left out 6,599 cards, 4,313 of them '17 (user:
    "jangan sampai ada pemain yang tidak ada di pack, trade, dan market"); prices come from the
    rating either way (card_price)."""
    with closing(_db()) as c:
        own = {s for (s,) in c.execute("""SELECT p.spid FROM players p JOIN permid m ON m.spid = p.spid
            AND m.transferable = 1 WHERE p.spid >= 1000000 AND p.playerid IN (SELECT playerid FROM namesind)""")}
    return frozenset(own | set(fa_prices()))


def on_market(spid):
    return int(spid) in market_spids()


@functools.lru_cache(maxsize=None)
def rating_prices():
    """{client rating: EP price at +1}: the median fifaaddict price of all listed cards with that
    rating (ratings with 5+ priced cards), each at least 5% above the rating below; {} without
    fa_prices.json."""
    fa = fa_prices()
    by = {}
    for s, o in card_ovrs([s for s, p in fa.items() if p]).items():
        if o:
            by.setdefault(o, []).append(fa[s])
    med = {o: statistics.median(v) for o, v in by.items() if len(v) >= 5}
    table, top = {}, 0
    for o in range(min(med), max(med) + 1) if med else ():
        top = max(top * 1.05, med.get(o, 0))
        table[o] = top
    return table


def stat_price(ovr):
    """EP price at +1 of a card rated ovr."""
    t = rating_prices()
    if len(t) < 6:
        return price_formula(ovr)
    lo, hi = min(t), max(t)
    if ovr > hi:  # above every listed rating: keep the top five ratings' growth per point
        return t[hi] * (t[hi] / t[hi - 5]) ** ((ovr - hi) / 5)
    return t[max(lo, ovr)]


def card_price(spid, grade=1):
    """EP value from the card's rating and grade only (user: "fix harga yang tidak sesua
    statsnya"): fifaaddict's own prices put scarce seasons (Legend, EL, UL, WL, CC, LP...) at up
    to 50,000x a card of the same rating, and some '17 cards rated 76 at 1,000 EP."""
    return sig3(stat_price(card_ovr(spid)) * GRADE_PRICE[min(10, max(0, int(grade)))])  # +0 = 0 EP


def iid(p):
    """Player instance id: str(spid) for squads made by gen_teams, a hex id for cards bought,
    opened or upgraded here (so two cards of one player can coexist, e.g. for upgrades)."""
    return str(p.get("_id") or p["spid"])


def new_iid():
    return os.urandom(12).hex()  # Mongo-style


# Levels (user: "akun dan pemain belum bisa dilevel up"). Both levelinfo = {level, exp within
# the level, to = exp the level needs}. Players: the client adds level - 1 to every attribute
# (PlayerListUtil.fillPlayerStaticData: totalBonus = level - 1 + grade boost; fifaaddict lists
# LV.1-23); EXPPLAYER {level: {requiredplayerexp}}, max level = rows - 1 (getMaxLevel). Coach:
# EXPCOACH {level: {totalexp}} = exp to finish levels 1..level (TeamManagementCoachExpScreen),
# max from STATICVALUES/max_coachlevel. The original tables were server data; curves made up.
PLAYER_MAX_LEVEL, COACH_MAX_LEVEL = 23, 100


def player_need(level):
    return 100 * level


def coach_need(level):
    return 500 + 100 * (level - 1)


EXPPLAYER = {str(lv): {"requiredplayerexp": player_need(lv)} for lv in range(1, PLAYER_MAX_LEVEL + 2)}
EXPCOACH = {str(lv): {"totalexp": sum(coach_need(k) for k in range(1, lv + 1))} for lv in range(1, COACH_MAX_LEVEL + 1)}


def make_levelinfo(info, need, top):
    level = min(top, max(1, int((info or {}).get("level") or 1)))
    return {"level": level, "exp": 0 if level >= top else int((info or {}).get("exp") or 0), "to": need(level)}


def player_levelinfo(p):
    return make_levelinfo(p.get("levelinfo"), player_need, PLAYER_MAX_LEVEL)


def coach_levelinfo(coach):
    return make_levelinfo(coach.get("levelinfo"), coach_need, COACH_MAX_LEVEL)


def gain_exp(owner, n, need, top):
    """Add n exp to owner["levelinfo"] (levels up, stops at top); (prev, current) levelinfo."""
    prev = make_levelinfo(owner.get("levelinfo"), need, top)
    level, exp = prev["level"], prev["exp"] + n
    while level < top and exp >= need(level):
        exp -= need(level)
        level += 1
    owner["levelinfo"] = {"level": level, "exp": 0 if level >= top else exp}
    return prev, make_levelinfo(owner["levelinfo"], need, top)


# Tim > Formasi combobox = coach team.formations (SquadScreenHandler.initializeFormationComboBox:
# entry 0 is shown with the club's name; picking one runs changeFormation: positions[i] -> squad
# slot i, offsets[i] -> starting x/y, then SquadUtil.getBestSquadPositions). Entries come from the
# client's own formations table (data_0.big data/db/fifa_ng_db.db): teamid 1 holds the 33 common
# shapes (their sweeper variants left out, like FORMATIONS_COMMON_WITHOUT_SWEEPER), other teams
# their own. That table numbers positions without SW: client Enums.PLAYERPOSITION = code + 1 (GK 0).
FORMATIONS_CACHE = os.path.join(HERE, "gamedata", "formations.json")
_FORMATIONS = None


def formation_table():
    """{"common": [entry], "teams": {teamid: entry}}; entry = {formationid, formationname,
    positions, offsets}. Read once from the client, then cached in gamedata/formations.json."""
    global _FORMATIONS
    if _FORMATIONS is None:
        try:
            with open(FORMATIONS_CACHE) as f:
                _FORMATIONS = json.load(f)
        except OSError:
            _FORMATIONS = {"common": [], "teams": {}}
            try:
                sys.path.insert(0, os.path.join(HERE, "tools", "re"))
                import bigdir, eadb
                big = os.path.join(GAME, "data", "data_0.big")
                rows = eadb.rows(bigdir.read(big, "data/db/fifa_ng_db.db"),
                                 bigdir.read(big, "data/db/fifa_ng_db-meta.xml").decode("utf-8", "replace"), "formations")
            except (OSError, KeyError, ImportError) as e:
                print("formations unavailable:", e, flush=True)
                return _FORMATIONS
            entry = lambda r: {"formationid": r["formationid"], "formationname": r["formationname"],
                               "positions": [r[f"position{i}"] + (r[f"position{i}"] > 0) for i in range(11)],
                               "offsets": [{"x": round(r[f"offset{i}x"], 4), "y": round(r[f"offset{i}y"], 4)} for i in range(11)]}
            _FORMATIONS["common"] = sorted((entry(r) for r in rows if r["teamid"] == 1 and not r["issweeper"]),
                                           key=lambda e: e["formationname"])
            _FORMATIONS["teams"] = {str(r["teamid"]): entry(r) for r in rows if r["teamid"] != 1 and not r["issweeper"]}
            os.makedirs(os.path.dirname(FORMATIONS_CACHE), exist_ok=True)
            with open(FORMATIONS_CACHE, "w") as f:
                json.dump(_FORMATIONS, f)
    return _FORMATIONS


STADIUMS_CACHE = os.path.join(HERE, "gamedata", "stadiums.json")


@functools.lru_cache(maxsize=None)
def stadium_table():
    """({stadium id: {name, yearbuilt, capacity}}, {club teamid: stadium id}) from the client's
    own fifa_ng_db, cached in gamedata/stadiums.json. stadiums.yearbuilt counts years after 1800
    (Bernabeu 147 = 1947), a "_" name is a generic stadium (an unlicensed club's); a club's
    stadium is the one with its hometeamid, else its teamstadiumlinks row (teamid there = real - 1)."""
    try:
        with open(STADIUMS_CACHE, encoding="utf-8") as f:
            t = json.load(f)
    except OSError:
        try:
            sys.path.insert(0, os.path.join(HERE, "tools", "re"))
            import bigdir, eadb
            big = os.path.join(GAME, "data", "data_0.big")
            db = bigdir.read(big, "data/db/fifa_ng_db.db")
            meta = bigdir.read(big, "data/db/fifa_ng_db-meta.xml").decode("utf-8", "replace")
            rows, links = eadb.rows(db, meta, "stadiums"), eadb.rows(db, meta, "teamstadiumlinks")
        except (OSError, KeyError, ImportError) as e:
            print("stadiums unavailable:", e, flush=True)
            return {}, {}
        t = {"stadiums": {str(r["stadiumid"]): {"name": r["name"].lstrip("_"), "yearbuilt": 1800 + r["yearbuilt"],
                                                "capacity": r["capacity"]} for r in rows},
             "teams": {**{str(r["teamid"] + 1): r["stadiumid"] for r in links},
                       **{str(r["hometeamid"]): r["stadiumid"] for r in rows if r["hometeamid"]}}}
        os.makedirs(os.path.dirname(STADIUMS_CACHE), exist_ok=True)
        with open(STADIUMS_CACHE, "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False)
    return {int(k): v for k, v in t["stadiums"].items()}, {int(k): v for k, v in t["teams"].items()}


def club_stadium(teamid):
    """A club's home stadium id (0: none in the client's database, e.g. a national team)."""
    return stadium_table()[1].get(int(teamid or 0), 0)


def ep_stadium(sid, query, body):
    """GET /stadium/<id> (TeamStaticInfo.onStadiumChanged via StaticData.getData): the home
    stadium's name and "yearbuilt / capacity" line in Tim > Klub > Informasi tim (issue #9)."""
    return _json(stadium_info(sid))


def stadium_info(sid):
    return {"id": int(sid), **(stadium_table()[0].get(int(sid)) or {"name": "-", "yearbuilt": "-", "capacity": "-"})}


def ep_team_summary(teamid, query, body):
    """GET /static/info/team/summary/<id> {summary, stadium, kit}: Item > Ganti tim
    (TeamChangeScreenSelectPage.onReceivedTeamInfo) shows summary name, league.id, rival.name and
    the stadium's name and "yearbuilt / capacity", and dresses its 3D player in kit.availables
    (no kit = no 3D player, birth date, height or weight; issue #23). The Cup and Boxing Day club
    pickers read summary.league from the same body."""
    t = int(teamid)
    return _json({"id": t, "summary": roster(t)["summary"], "stadium": stadium_info(club_stadium(t)), "kit": team_kit(t)})


def team_formations(teamid):
    """The club's own formation first (else 4-4-2(1), the shape of the gen_teams XI), then the
    common ones."""
    t = formation_table()
    own = t["teams"].get(str(teamid)) or next((e for e in t["common"] if e["formationname"] == "4-4-2(1)"), None)
    return ([own] if own else []) + [e for e in t["common"] if own is None or e["formationid"] != own["formationid"]]


def fix_formation(team, teamid):
    """A stored team built by gen_teams carries formations = [its 4-4-2, id 1] and squad
    .formation 1, which is 3-4-1-2 in the client's table: point it at the club's own entry."""
    if team.pop("formations", None) is not None and team["squad"].get("formation") in (None, 1):
        forms = team_formations(teamid)
        if forms:
            team["squad"]["formation"] = forms[0]["formationid"]


# Team color (user: "belum ada bonus stats pada saat memenuhi syarat tim/negara/ sesion").
# TeamColorController (data/ui/libs/Module.big) runs only with features.teamcolor
# (responses/account_base.json) and GET /static/info/teamcolor {teamColors, teamColorSpecials}.
# A color: {teamcolorid, type club|nation|special, name, description (both go through
# getLocalizedString, which returns an unknown key as-is), teamid (-1 = any club/nation),
# boostgroups [{count_min, count_max, boosts [{type "ovr" = every attribute, amount}]}]}.
# The server picks the colors the starting XI meets: team.teamcolors [{teamcolorid, boostindex,
# teamid}] in coach/me and the user's match side (isValidTeamData needs the array). The client
# then boosts the XI players that fit (availableTeamColor: club = staticdata.teamid or a club in
# clubhistory, nation = nationality, special = spid in teamColorSpecials[teamid]); per player only
# the best of club / nation / special applies, they do not stack. 17 and 131 are the client's own
# "Single team" / "Satu Negara" (LANGUAGESTRING TEAMCOLOR_ATTRIBUTES_TEAM<id>).
TC_CLUB, TC_NATION, TC_SEASON = 17, 131, 50000  # a season color is 50000 + its first season code


def _tc_groups(*tiers):
    return [{"count_min": lo, "count_max": hi, "boosts": [{"type": "ovr", "amount": n}]} for lo, hi, n in tiers]


TC_CLUB_GROUPS = _tc_groups((4, 5, 1), (6, 7, 2), (8, 9, 3), (10, 11, 4))
TC_GROUPS = _tc_groups((5, 6, 1), (7, 8, 2), (9, 11, 3))  # nation, season
# Upgrade colors (user: "tambah tim color untuk upgrade"): type "grade" = XI cards of at least
# that grade (availableTeamColor: player.grade >= color.grade; native 0x94EB70 reads color.grade
# as an int, no teamid). Names are the client's own; the boosts are ours.
TC_GRADE = (  # (teamcolorid, grade, name key, boostgroups)
    (10002, 2, "TEAMCOLOR_ATTRIBUTES_EVOLVE24", TC_GROUPS),
    (10005, 5, "TEAMCOLOR_ATTRIBUTES_EVOLVE10011", _tc_groups((5, 6, 2), (7, 8, 3), (9, 11, 4))),
    (10008, 8, "TEAMCOLOR_ATTRIBUTES_EVOLVE810", _tc_groups((5, 6, 3), (7, 8, 4), (9, 11, 5))),
)
# The client's single-grade colors (user: "Grade +3…+10 dulu", then "Bonus kecilkan dulu"):
# "+3 club" … "+10 Golden summit", all 11 starters at that grade or higher; one bonus per name
# tier (club / silver / Golden passion / Golden summit). A player gets only his best grade color
# (ChooseTeamColorBoostsPerPlayer keeps one __gradeTeamColor, added to his best club / nation /
# season color), so each tier tops the range color above it at 9-11 starters (+3 / +4 / +5).
TC_GRADE += tuple((10100 + g, g, f"TEAMCOLOR_ATTRIBUTES_EVOLVE{g}", _tc_groups((11, 11, n)))
                  for g, n in ((3, 4), (4, 4), (5, 5), (6, 5), (7, 5), (8, 6), (9, 6), (10, 7)))


def tc_seasons():
    """(label, card season codes) of every season color: fifaaddict's seasons and '07."""
    return (("07", (7,)),) + tuple((label, codes) for label, codes, _ in FA_SEASONS)


def tc_season_of(code):
    """Season color id of a card season code (None: no color, e.g. engine cards)."""
    return next((TC_SEASON + codes[0] for _, codes in tc_seasons() if code in codes), None)


# The client's own named colors (user: "pakai semua team color yang belum masuk"): names are its
# LANGUAGESTRING TEAMCOLOR_ATTRIBUTES_TEAM<id>. Their boosts and player lists were server data
# and are gone; what the client still has is one line per color, TOOLTIP<id>, so each named
# color gets our base tiers plus that boost and beats the generic color it overlaps (a player
# gets his best club / nation / special color: getBoostStatPoint sums the boosts that fit his
# position, an OVR one counting once per stat). A boost {type, amount, target} adds amount to that
# stat (type "ovr": every stat) of players in that position group (target fw/mf/df/gk, none = all;
# ApplyTeamColorBoostStat); the native half-time recheck (0x94EB70) reads only type, teamid,
# season, grade and __teamid, never boosts. Boosts are (target, stat, amount); "Grade +N" and
# "{0} +{1}" tooltips (stat not known) count as OVR. Left out: the [Test] colors 70000-70015,
# "Upgraded team (+2~7)" (the same as +2~4), "14 WC Single Nation" (the 14 WC nations cover it)
# and the newer copies of Atletico, Roma, Napoli and Monaco (20055-20058).
TC_NAMED_CLUBS = (  # (TEAM<id>, club teamid; a player counts for his club now or in his history)
    (1, 243, ("fw", "sprintspeed", 2)), (2, 241, ("mf", "agility", 3)), (3, 9, ("fw", "balance", 1)),
    (4, 10, ("fw", "longpassing", 2)), (5, 11, ("fw", "reactions", 2)), (6, 1, ("mf", "stamina", 2)),
    (7, 5, ("mf", "dribbling", 1)), (8, 18, ("mf", "acceleration", 2)), (9, 22, ("mf", "positioning", 2)),
    (10, 32, ("fw", "sprintspeed", 8)), (11, 21, ("mf", "finishing", 2)), (12, 47, ("fw", "positioning", 1)),
    (13, 45, ("df", "stamina", 2)), (14, 44, ("fw", "dribbling", 1)), (15, 73, ("fw", "ballcontrol", 2)),
    (16, 982, ("mf", "stamina", 12)), (43, 240, ("", "ovr", 1)), (44, 52, ("", "ovr", 1)),
    (45, 236, ("", "ballcontrol", 3)), (46, 69, ("", "stamina", 2)), (47, 110374, ("", "positioning", 3)),
    (48, 48, ("", "dribbling", 2)), (146, 981, ("", "ovr", 1)), (885, 110955, ("", "headingaccuracy", 4)),
    (20054, 112172, ("", "ovr", 1)), (20059, 72, ("", "ovr", 1)), (20060, 1477, ("", "ovr", 1)),
)
TC_NAMED_NATIONS = (  # (TEAM<id>, nationality)
    (101, 45, ("mf", "ballcontrol", 2)), (102, 21, ("fw", "positioning", 3)), (103, 54, ("fw", "dribbling", 2)),
    (104, 38, ("fw", "dribbling", 2)), (105, 52, ("fw", "balance", 2)), (106, 60, ("fw", "agility", 2)),
    (107, 56, ("mf", "shotpower", 3)), (108, 27, ("mf", "shortpassing", 3)), (109, 14, ("mf", "stamina", 1)),
    (110, 7, ("mf", "ballcontrol", 2)), (111, 95, ("fw", "jumping", 2)), (112, 34, ("fw", "reactions", 1)),
    (113, 18, ("fw", "positioning", 2)), (114, 10, ("fw", "headingaccuracy", 2)), (115, 40, ("fw", "ballcontrol", 2)),
    (116, 83, ("fw", "reactions", 2)), (117, 108, ("mf", "reactions", 2)), (118, 117, ("mf", "shortpassing", 2)),
    (119, 167, ("mf", "aggression", 2)), (120, 163, ("mf", "shortpassing", 2)), (121, 195, ("fw", "positioning", 2)),
    (122, 55, ("fw", "sprintspeed", 2)), (123, 49, ("fw", "finishing", 1)), (124, 50, ("fw", "reactions", 2)),
    (125, 46, ("fw", "shotpower", 2)), (126, 13, ("fw", "headingaccuracy", 2)), (127, 51, ("fw", "jumping", 2)),
    (128, 103, ("fw", "acceleration", 2)), (129, 133, ("fw", "sprintspeed", 1)), (130, 12, ("fw", "positioning", 2)),
)
# season colors the client names: card season code -> (TEAM<id>, boost); a season color keeps at
# least its +3 (2002 Legends, '16 Europe/Copa and EU Legends say +1)
TC_SEASON_NAMES = {91: (18, ("", "ovr", 5)), 93: (100, ("", "ovr", 3)), 95: (19, ("", "ovr", 3)),
                   77: (42, ("", "reactions", 1)), 65: (140, ("", "ovr", 3)), 53: (141, ("", "ovr", 3)),
                   47: (142, ("", "ovr", 3)), 63: (143, ("", "ovr", 3)), 69: (137, ("", "ovr", 3)),
                   67: (138, ("", "ovr", 3)), 35: (145, ("", "ovr", 3)), 27: (20044, ("", "ovr", 3))}
TC_LEGENDS = (93, 30, 27, 71, 51, 61, 89, 48, 55, 49)  # WL UL EL ML TL VL CL MUL MUA TCO92
TC_YEARS = (6, 7, 8, 9, 10, 11, 14, 15, 16, 88)


def _in(ids):
    return ",".join(map(str, ids))


def _S(*codes):  # card season
    return f"p.spid / 1000000 IN ({_in(codes)})"


def _CLUB(*ids):  # club now or in the player's history
    return f"(p.teamid IN ({_in(ids)}) OR p.playerid IN (SELECT playerid FROM playerhistory WHERE teamid IN ({_in(ids)})))"


def _PIDS(*ids):  # these players, any card
    return f"p.playerid IN ({_in(ids)})"


_SPECIAL = f"p.spid >= 1000000 AND p.spid / 1000000 NOT IN ({_in(TC_YEARS + TC_LEGENDS)})"  # special seasons


_TC_OVR = ("", "ovr", 3)
TC_NAMED_SPECIALS = (  # (TEAM<id>, description, SQL condition on players p, boost, best N Market cards)
    *((tid, "Pemain 14 WC dari negara ini", f"{_S(77)} AND p.nationality = {n}", b, None) for tid, n, b in (
        (20, 45, ("", "ovr", 2)), (21, 21, ("", "ovr", 3)), (22, 54, ("", "ballcontrol", 2)),
        (23, 38, ("", "positioning", 2)), (24, 52, ("", "dribbling", 2)), (25, 60, ("fw", "longshots", 3)),
        (26, 56, ("", "strength", 1)), (27, 27, ("", "agility", 2)), (28, 14, ("", "longpassing", 2)),
        (29, 7, ("", "shortpassing", 2)), (30, 95, ("mf", "stamina", 2)), (31, 34, ("", "ballcontrol", 2)),
        (32, 18, ("", "strength", 1)), (33, 10, ("fw", "acceleration", 2)), (34, 40, ("", "positioning", 2)),
        (35, 83, ("", "headingaccuracy", 2)), (36, 108, ("", "marking", 3)), (37, 117, ("", "reactions", 2)),
        (38, 167, ("", "reactions", 2)), (39, 163, ("", "shortpassing", 2)))),
    *((tid, "50 kartu terbaik negara ini", f"p.nationality = {n}", _TC_OVR, 50) for tid, n in (
        (20007, 21), (20008, 45), (20009, 18), (20010, 27), (20011, 14), (20012, 54), (20013, 52),
        (20014, 7), (20015, 38), (20016, 56), (20017, 60))),
    *((tid, "Pemain EC / Copa dari negara ini", f"{_S(35, 24)} AND p.nationality = {n}", _TC_OVR, None) for tid, n in (
        (20018, 21), (20019, 45), (20020, 18), (20021, 27), (20022, 14), (20023, 54), (20024, 52),
        (20025, 7), (20026, 38), (20027, 56))),
    *((tid, "Pemain season '10 klub ini", f"{_S(10)} AND {_CLUB(club)}", b, None) for tid, club, b in (
        (133, 241, ("fw", "positioning", 5)), (134, 47, ("fw", "sprintspeed", 5)),
        (135, 22, ("mf", "aggression", 5)), (136, 240, ("mf", "vision", 5)))),
    (132, "Pemain season spesial (bukan tahunan, bukan legenda)", _SPECIAL, ("", "ovr", 2), None),
    (139, "Juara liga 2016/17 (season '17)", f"{_S(88)} AND p.teamid IN (5, 243, 21, 45, 69)", ("", "ovr", 3), None),
    (41, "30 kartu terbaik", "1", ("", "shortpassing", 2), 30),
    (2014, "Kartu OVR 85 ke atas", f"{POSOVR} >= 85", ("", "ovr", 4), None),
    (886, "Pemain legenda dari China", f"p.nationality = 155 AND {_S(*TC_LEGENDS)}", ("", "ovr", 3), None),
    (20002, "Messi, Suarez, Neymar", _PIDS(158023, 176580, 190871), _TC_OVR, None),
    (20003, "Bale, Benzema, Cristiano Ronaldo", _PIDS(173731, 165153, 20801), _TC_OVR, None),
    (3059, "Messi dan Cristiano Ronaldo", _PIDS(158023, 20801), _TC_OVR, None),
    (3060, "Ramos, Pepe, Marcelo, Carvajal, Varane, Navas", _PIDS(155862, 120533, 176676, 204963, 201535, 193041), _TC_OVR, None),
    (3058, "Leicester City juara 2015/16", _PIDS(208830, 204485, 215914, 186132, 136113, 137785, 163587, 183130,
                                                 194365, 169600, 139313), _TC_OVR, None),
    (3064, "Pemain AC Milan dan Inter", _CLUB(47, 44), _TC_OVR, None),
    (34024, "Pemain AC Milan (rossoneri)", _CLUB(47), _TC_OVR, None),
    (20030, "Arsenal 2003/04 tak terkalahkan", _PIDS(805, 388, 119152, 34079, 6975, 1419, 1605, 4000, 1625,
                                                      140526, 111093), _TC_OVR, None),
    (20031, "Shevchenko dan Kaka", _PIDS(13128, 138449), _TC_OVR, None),
    (20032, "Terry, Lampard, Drogba, Cech", _PIDS(13732, 5471, 31432, 48940), _TC_OVR, None),
    (20033, "Figo, Ronaldo, Beckham, Raul, Roberto Carlos, Casillas", _PIDS(5589, 37576, 250, 45661, 1040, 5479), _TC_OVR, None),
    (20028, "Pemain season '17", _S(88), _TC_OVR, None),
    (20029, "Pemain season apa saja", "1", ("", "ovr", 1), None),
    (20043, "Pemain season legenda", _S(*TC_LEGENDS), ("", "ovr", 4), None),
    (40001, "50 kartu terbaik", "1", _TC_OVR, 50),
    (40002, "100 kartu terbaik", "1", _TC_OVR, 100),
    (40003, "100 kartu terbaik season spesial", _SPECIAL, _TC_OVR, 100),
    (40004, "100 kartu terbaik season '17", _S(88), _TC_OVR, 100),
    (40005, "100 kartu terbaik season legenda", _S(*TC_LEGENDS), _TC_OVR, 100),
    (20063, "Pemain Brasil skill 4 bintang ke atas", "p.nationality = 54 AND p.skillmoves >= 3", ("", "ballcontrol", 5), None),
    (20064, "Short pass dan vision 85 ke atas", "p.shortpassing >= 85 AND p.vision >= 85", ("", "shortpassing", 5), None),
    (20065, "Pemain Real Madrid dan Barcelona", _CLUB(243, 241), ("", "dribbling", 5), None),
    (20066, "Tackle 85 ke atas", "p.standingtackle >= 85", ("", "aggression", 5), None),
    (20067, "Work rate menyerang dan bertahan tinggi", "p.attackingworkrate = 2 AND p.defensiveworkrate = 2",
     ("", "positioning", 5), None),
    (20068, "Bek tinggi 188 cm ke atas", "p.height >= 188 AND p.preferredposition1 BETWEEN 1 AND 8", ("", "strength", 5), None),
    (20069, "Lahir 1995 ke atas", "CAST(substr(p.birthdate, instr(p.birthdate, ' ') - 4, 4) AS INTEGER) >= 1995",
     ("", "longshots", 5), None),
    (20070, "Heading 85 ke atas", "p.headingaccuracy >= 85", ("", "strength", 5), None),
    (20071, "Reputasi internasional 4 bintang ke atas", "p.internationalrep >= 4", ("", "ovr", 4), None),
)
TC_KEYS = {34024: "TEAMCOLOR_ATTRIBUTES_EVOLVE34024"}  # every other name is TEAMCOLOR_ATTRIBUTES_TEAM<id>


def _tc_boost(groups, boost):
    """groups with a TOOLTIP boost (target, stat, amount) added to every tier."""
    target, stat, n = boost
    extra = {"type": stat, "amount": n, **({"target": target} if target else {})}
    return [dict(g, boosts=g["boosts"] + [extra]) for g in groups]


def _tc_special_groups(boost, players=5):
    """A special color's tiers: 5-6 / 7-8 / 9-11 players, OVR up to the tooltip's OVR (else +3,
    with a stat tooltip on top). A set of fewer than 5 players has one tier: all of them."""
    target, stat, n = boost
    top = n if stat == "ovr" else 3
    groups = (_tc_groups((players, 11, top)) if players < 5
              else _tc_groups((5, 6, max(1, top - 2)), (7, 8, max(1, top - 1)), (9, 11, top)))
    return groups if stat == "ovr" else _tc_boost(groups, boost)


@functools.lru_cache(maxsize=None)
def tc_special_sets():
    """{special color id: (frozenset of its spids, number of players)}: season colors by card
    season, the named ones by their condition ("best N": of the Market cards, by rating)."""
    sets = {}
    with closing(_db()) as c:
        rows = c.execute("SELECT spid, playerid FROM players").fetchall()
        for _, codes in tc_seasons():
            sets[TC_SEASON + codes[0]] = [(s, p) for s, p in rows if s // 1000000 in codes]
        for cid, _, cond, _, best in TC_NAMED_SPECIALS:
            got = c.execute(f"SELECT p.spid, p.playerid FROM players p WHERE {cond} ORDER BY {POSOVR} DESC").fetchall()
            sets[cid] = [r for r in got if on_market(r[0])][:best] if best else got
    return {cid: (frozenset(s for s, _ in got), len({p for _, p in got})) for cid, got in sets.items()}


@functools.lru_cache(maxsize=None)
def tc_colors():
    """Every color (GET /static/info/teamcolor teamColors): the generic club / nation ones, the
    upgrade ones, the named clubs and nations, the season colors and the named specials (one
    with no card in fifadb is left out)."""
    key = lambda cid: TC_KEYS.get(cid, f"TEAMCOLOR_ATTRIBUTES_TEAM{cid}")
    club = {"teamcolorid": TC_CLUB, "type": "club", "teamid": -1, "name": key(TC_CLUB),
            "description": "Pemain dari klub yang sama", "boostgroups": TC_CLUB_GROUPS}
    nation = {"teamcolorid": TC_NATION, "type": "nation", "teamid": -1, "name": key(TC_NATION),
              "description": "Pemain dari negara yang sama", "boostgroups": TC_GROUPS}
    grades = [{"teamcolorid": cid, "type": "grade", "grade": g, "teamid": -1, "name": name,
               "description": f"Pemain grade +{g} ke atas", "boostgroups": groups} for cid, g, name, groups in TC_GRADE]
    clubs = [{"teamcolorid": cid, "type": "club", "teamid": t, "name": key(cid), "description": "Pemain klub ini (sekarang atau dulu)",
              "boostgroups": _tc_boost(TC_CLUB_GROUPS, b)} for cid, t, b in TC_NAMED_CLUBS]
    nations = [{"teamcolorid": cid, "type": "nation", "teamid": n, "name": key(cid), "description": "Pemain dari negara ini",
                "boostgroups": _tc_boost(TC_GROUPS, b)} for cid, n, b in TC_NAMED_NATIONS]
    # a special color's teamid is a STRING: TeamColorController copies teamid to __teamid and hands
    # the list to native (setTeamColorList); at half time native re-checks the colors (0x94EB70) and
    # reads a special one's __teamid with asCString -- a number there crashed every second half.
    sets = tc_special_sets()
    specials = []
    for label, codes in tc_seasons():
        cid = TC_SEASON + codes[0]
        tid, b = TC_SEASON_NAMES.get(codes[0], (None, None))
        specials.append({"teamcolorid": cid, "type": "special", "teamid": str(cid), "name": key(tid) if tid else f"Season {label}",
                         "description": f"Pemain season {label}", "boostgroups": _tc_special_groups(b) if b else TC_GROUPS})
    for cid, desc, _, b, _ in TC_NAMED_SPECIALS:
        if sets[cid][1]:
            specials.append({"teamcolorid": cid, "type": "special", "teamid": str(cid), "name": key(cid),
                             "description": desc, "boostgroups": _tc_special_groups(b, min(5, sets[cid][1]))})
    return [club, nation] + grades + clubs + nations + specials


def ep_teamcolor(query, body):
    """GET /static/info/teamcolor (once per login). A special color lists its cards by spid; only
    the cards I own are listed (every card would be MBs): one bought later counts on the server
    at once and gets its boost in the client from the next login."""
    st = _state()
    owned = {int(p["spid"]) for p in st["teams"].get(str(_default_slot(st)), {}).get("players", [])}
    sets = tc_special_sets()
    specials = {c["teamid"]: sorted(owned & sets[c["teamcolorid"]][0]) for c in tc_colors() if c["type"] == "special"}
    return _json({"teamColors": tc_colors(), "teamColorSpecials": specials})


@functools.lru_cache(maxsize=None)
def tc_static():
    """({spid: (playerid, teamid, nationality)}, {playerid: {former club ids}}) from fifadb."""
    with closing(_db()) as c:
        cards = {s: (p, t, n) for s, p, t, n in c.execute("SELECT spid, playerid, teamid, nationality FROM players")}
        hist = {}
        for p, t in c.execute("SELECT playerid, teamid FROM playerhistory"):
            hist.setdefault(p, set()).add(t)
    return cards, hist


def _tc_tier(groups, n):
    return next((i for i, g in enumerate(groups) if g["count_min"] <= n <= g["count_max"]), None)


def active_teamcolors(team):
    """team.teamcolors: the colors the starting XI meets, with enough distinct players (as
    TeamColorController.updatePlayerCount counts them): one generic club / nation color per club
    and nation, the named ones, the specials and the upgrade colors."""
    cards, hist = tc_static()
    sets = tc_special_sets()
    counts, seen = {}, set()
    for p in team["squad"]["positions"]:
        c = cards.get(int(p["spid"])) if p.get("pos", POS_SUB) < POS_SUB else None
        if c is None or c[0] in seen:
            continue
        seen.add(c[0])
        pid, teamid, nation = c
        keys = [(TC_CLUB, t) for t in {teamid} | hist.get(pid, set())] + [(TC_NATION, nation)]
        keys += [("special", cid) for cid, (spids, _) in sets.items() if int(p["spid"]) in spids]
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
    out = []
    for (cid, teamid), n in sorted((k, n) for k, n in counts.items() if k[0] != "special"):
        i = _tc_tier(TC_CLUB_GROUPS if cid == TC_CLUB else TC_GROUPS, n)
        if i is not None and teamid > 0:
            out.append({"teamcolorid": cid, "boostindex": i, "teamid": teamid})
    for c in tc_colors():
        if c["type"] == "grade" or c["teamid"] == -1:
            continue
        n = counts.get(("special", c["teamcolorid"]) if c["type"] == "special"
                       else (TC_CLUB if c["type"] == "club" else TC_NATION, c["teamid"]), 0)
        i = _tc_tier(c["boostgroups"], n)
        if i is not None:
            # special colors carry their teamid as a string, like tc_colors()
            out.append({"teamcolorid": c["teamcolorid"], "boostindex": i, "teamid": c["teamid"]})
    grade = {iid(p): grade_of(p) for p in team["players"]}
    xi = [grade.get(str(p.get("id") or p["spid"]), 0) for p in team["squad"]["positions"] if p.get("pos", POS_SUB) < POS_SUB]
    for cid, g, _, groups in TC_GRADE:
        i = _tc_tier(groups, sum(x >= g for x in xi))
        if i is not None:
            out.append({"teamcolorid": cid, "boostindex": i, "teamid": -1})
    return out


def fill_squad(sq, players):
    """11 starters + 7 subs (Enums.PLAYERPOSITION "SUB"; without a bench the squad screen says
    "Tidak cukup pemain"). A hole in the XI (issue #7: an upgrade of two starters of one
    player) takes the best sub; the bench is topped up with the best Tim inti cards. One card
    per player in the 18, like the client (PLAYERLIST_CHANGEPLAYER_FAIL_POPUP_INFO_DUPLICATIONPLAYER).
    ponytail: by rating, not by position; the manager re-arranges in Formasi."""
    pos = sq["positions"]
    card = {p["id"]: p for p in players}
    best = lambda ps: sorted(ps, key=lambda p: -player_ovr(card.get(p["id"], p)))
    taken = {int(s["spid"]) % 1000000 for s in pos}
    spare = []
    for p in best(p for p in players if p.get("state") == "first"):  # Tim inti only
        if int(p["spid"]) % 1000000 not in taken:
            taken.add(int(p["spid"]) % 1000000)
            spare.append({"spid": p["spid"], "pos": POS_SUB, "id": p["id"]})
    forms = formation_table()
    form = next((f for f in forms["common"] + list(forms["teams"].values()) if f["formationid"] == sq.get("formation")),
                {"positions": [f[0] for f in gen_teams.FORMATION], "offsets": [{"x": f[1], "y": f[2]} for f in gen_teams.FORMATION]})
    shape = form["positions"]
    used = {s["pos"] for s in pos if s["pos"] < POS_SUB}
    holes = [x for x in shape if x not in used][:max(0, 11 - len(used))]
    for hole, s in zip(holes, best(s for s in pos if s["pos"] == POS_SUB) + spare):
        s["pos"] = hole
        s.pop("starting", None)
        if s not in pos:
            pos.append(s)
    pos += [s for s in spare if s not in pos][:max(0, 7 - sum(s["pos"] == POS_SUB for s in pos))]
    # a starter needs starting [attacking, defensive participation, x, y]: without it the client
    # moves him to the bench (PlayerListUtil, issue #7 again: filled holes had none, and Formasi
    # then saved them without it). x/y = his slot in the formation.
    spot = dict(zip(shape, form["offsets"]))
    for s in pos:
        if s["pos"] < POS_SUB and len(s.get("starting") or []) < 4:
            xy = spot.get(s["pos"], {"x": 0.5, "y": 0.5})
            s["starting"] = [gen_teams.PARTICIPATION, gen_teams.PARTICIPATION, xy["x"], xy["y"]]


# Formasi's squad picker (SquadScreenHandler, issue #20: it was an empty box): STATICVALUES
# limit.preset_squad_count entries named MULTIPLE_SQUAD_SLOT1.. = Squad A, B, C; a slot i is
# locked below coach level limit["preset_squad_level<i>"] (none = open). Picking one sends
# PUT /coach/me/squad {squad, kickers, captain, presetidx} (apply_squad).
PRESET_SQUADS = 3


def preset_squads(team):
    """coach.teamsquadlist.preset of an owned team (owned_team): one squad per slot. The slot in
    use (presetidx) is the squad itself; the others as they were left, without cards that are
    gone and topped up like the squad (a slot never used starts as a copy of the squad)."""
    # like selectPresetSquad, which keeps only Tim inti cards
    saved, ids, out = team.get("presets") or [], {p["id"] for p in team["players"] if p.get("state") == "first"}, []
    for i in range(PRESET_SQUADS):
        if i == team.get("presetidx", 0) or i >= len(saved) or not saved[i]:
            out.append(team["squad"])
            continue
        sq = copy.deepcopy(saved[i])
        sq["positions"] = [s for s in sq["positions"] if str(s.get("id")) in ids]
        fill_squad(sq, team["players"])
        out.append(sq)
    return out


def owned_team(raw):
    """A stored team ({players:[{spid,...}], squad:{positions,captain,kickers,...}}) in the
    shape the client expects for a club it can show and play with (coach.team, match side.team)."""
    team = dict(raw)
    # An owned club refers to player *instances*: PlayerListUtil.getBestEleven maps
    # squad.positions[].id -> players[]._id (spid alone gives an empty XI -> null -> the
    # MenuScreen constructor throws = black FREEROAM).
    # CoachProxy.expandTeam: teamvalue = sum(price) of players with state "first" and grade > 0
    # getBestEleven matches positions[].id on players[]._id, attachSquadInfo and
    # generateFormatedPlayerList (Tim > Formasi / Peran pemain) on players[].id: send both.
    # Instance defaults: life = remaining contract matches (SquadUtil.needToReject drops <= 0),
    # levelinfo.level (FirstTeamInfo.updateAvgInfo average level). price = EP market value.
    # state "first" = Tim inti; no state = Tim Cadangan (Enums.getPlayerState: undefined ->
    # SECONDTEAM), set by /player/<id>/move/secondteam (stored as team2); Tukar Scout only
    # lists Tim Cadangan cards. A card in the 18 is always Tim inti (Formasi hides the others;
    # a state.json from before 5ffbfd8 can hold such a card, issue #7).
    # stamina 0..1: Liga's player lists draw it as a bar (PlayerListItemTeamColorRenderer in
    # ZONE_LEAGUE; without it the bar was empty, issue #16) and SquadUtil.getPositionScore weighs
    # it for the best XI. ponytail: always full, no fatigue kept between Liga matches.
    in18 = {str(s.get("id") or s["spid"]) for s in team["squad"]["positions"]}
    team["players"] = [{**({} if p.get("team2") and iid(p) not in in18 else {"state": "first"}), "grade": 0, "life": 100, "stamina": 1,
                        **{k: v for k, v in p.items() if k != "team2"}, "levelinfo": player_levelinfo(p),
                        "_id": iid(p), "id": iid(p), "price": card_price(p["spid"], grade_of(p))}
                       for p in team["players"]]
    sq = dict(team["squad"])
    sq["positions"] = [dict(p, id=str(p.get("id") or p["spid"])) for p in sq["positions"]]
    fill_squad(sq, team["players"])
    sq["captain"] = str(sq["captain"]) if sq.get("captain") else ""
    # all KICKER_TYPES slots, each a starter: an empty or stale one (saves before issue #8 dropped
    # empty slots; a kicker moved to the bench) takes gen_teams' default, the last 5 starters
    xi = [s["id"] for s in sq["positions"] if s["pos"] < POS_SUB]
    kick = ([str(k) for k in sq.get("kickers") or []] + [""] * KICKERS)[:KICKERS]
    sq["kickers"] = [k if k in xi or not xi else xi[-KICKERS:][i % len(xi[-KICKERS:])] for i, k in enumerate(kick)]
    team["squad"] = sq
    team.update({"staffs": [], "staffroles": [], "staffroleidx": 0, "maxstaff": 0, "staffsmc": {}})
    # PlayerListUtil.generateCaptainFromCoachInfo (Tim > Formasi) reads these at team level
    team.update({"captain": sq["captain"], "kickers": sq["kickers"], "presetidx": team.get("presetidx", 0)})
    team.setdefault("formations", [])
    return team


def xi_ratings(team):
    """{player id: rating} of an owned_team's XI as the squad lists show it (PlayerListUtil __ovr):
    Enums.calcPosOvr at his slot, on stats + grade boost + level - 1 (fillPlayerStaticData) +
    his team color boosts (TeamColorController over team.teamcolors: the best club / nation /
    special color by getBoostStatPoint plus the best grade color; "ovr" = every stat, a boost
    with a target only in that position group)."""
    card = {iid(p): p for p in team["players"]}
    xi = [(str(s.get("id") or s["spid"]), s["pos"]) for s in team["squad"]["positions"]
          if s.get("pos", POS_SUB) < POS_SUB and str(s.get("id") or s["spid"]) in card]
    stats = card_stats([card[i]["spid"] for i, _ in xi])
    colors = {c["teamcolorid"]: c for c in tc_colors()}
    cards, hist = tc_static()
    sets = tc_special_sets()
    out = {}
    for i, pos in xi:
        p = card[i]
        spid, grp = int(p["spid"]), "gk" if pos == 0 else "df" if pos <= 8 else "mf" if pos <= 19 else "fw"
        pid, club, nation = cards.get(spid, (None, None, None))
        def fits(e, c):
            return {"grade": lambda: grade_of(p) >= c["grade"], "nation": lambda: e["teamid"] == nation,
                    "club": lambda: e["teamid"] in {club} | hist.get(pid, set()),
                    "special": lambda: spid in sets[c["teamcolorid"]][0]}[c["type"]]()
        best = {}  # "base" / "grade": (point, boosts)
        for e in team.get("teamcolors") or []:
            c = colors[e["teamcolorid"]]
            if fits(e, c):
                bs = [b for b in c["boostgroups"][e["boostindex"]]["boosts"] if b.get("target", grp) == grp]
                point = sum(b["amount"] * (len(STAT_COLS) if b["type"] == "ovr" else 1) for b in bs)
                kind = "grade" if c["type"] == "grade" else "base"
                if point > best.get(kind, (0,))[0]:
                    best[kind] = (point, bs)
        add = dict.fromkeys(STAT_COLS, GRADE_BOOST[grade_of(p)] + player_levelinfo(p)["level"] - 1)
        for b in (b for _, bs in best.values() for b in bs):
            for k in (STAT_COLS if b["type"] == "ovr" else [b["type"]] if b["type"] in add else []):
                add[k] += b["amount"]
        w = ROLE_WEIGHTS[POS_ROLE[pos]]
        out[i] = sum(n * (stats[spid][k] + add[k]) for k, n in w.items()) // 100
    return out


def team_summary(team, teamid):
    # MenuScreen TeamInfoNew.setData: TEAMNAME(summary.id) + loadTeamCrest(summary.id), setOVR(ovr);
    # TeamStaticInfo (Tim > Klub) also reads name, league.id, nation{id,name}, rival.name.
    # TeamInfoNew.setOVR reads ovr.FW/MF/DF (rating bars) as sent: the average of the ratings the
    # squad list shows (issue #18: card ratings alone, without level, slot and team color, ran
    # ~12 under them). Enums.PLAYERPOSITION index ranges.
    ovr = xi_ratings(team)
    lines = {k: r for k, r in LINES.items() if k != "GK"}
    def line_ovr(r):
        v = [ovr.get(str(p.get("id") or p["spid"]), 0) for p in team["squad"]["positions"] if p.get("pos") in r]
        return round(sum(v) / len(v)) if v else 0
    return dict(roster_summary(teamid), id=teamid, ovr={k: line_ovr(r) for k, r in lines.items()})


def team_kit(teamid):
    # kit ids go to native as-is (freeroam kicker, 3D previews, match sides); {} = default goalie kit.
    # kit id = teamid << 5 | kittype (0 home, 1 away, 2 goalie): the match side reader (0x9480D0)
    # builds that itself for a side with no kit id, and the kit loader splits id >> 5 / id & 31 into
    # teamkits (teamtechid, teamkittypetechid) -> data/sceneassets/kit/kit_<team>_<type>_0.rx3.
    # teamid << 10 only looked right in FREEROAM (that path takes the team from elsewhere); in a
    # match it pointed at team (teamid << 5) = a checkerboard (GitHub issue #3).
    return {"availables": {k: {"id": teamid << 5 | t} for k, t in (("home", 0), ("away", 1), ("goalie", 2))}}


START_EP = 1000000
# Enums.VIP_DETAIL_*: NONE 0, VIP 1<<1, VVIP 1<<2, VVIP_SEA 1<<4
VIP_DETAIL = 2
VIP_UNTIL = 2051222400000  # 2035-01-01, ms


def add_ep(st, n):
    """Credit match/season/cup EP to the active coach (shown by /coach/me money.ep)."""
    coach = next(c for c in st["coaches"] if c["slot"] == _default_slot(st))
    coach["ep"] = coach.get("ep", START_EP) + int(n)


def coach_me(st, slot):
    """Body of the /coach/me resource (CoachProxy). Field paths are the ones its
    fetchCoach* methods read; values are a fresh account. startFreeRoam waits for this
    resource to validate before signing on."""
    coach = next(c for c in st["coaches"] if c["slot"] == slot)
    team = owned_team(st["teams"].get(str(slot), {"squad": {"positions": [], "kickers": []}, "players": []}))
    teamid = coach["teamid"]
    team["formations"] = team_formations(teamid)
    team["teamcolors"] = active_teamcolors(team)
    if team["formations"] and team["squad"].get("formation") is None:
        team["squad"]["formation"] = team["formations"][0]["formationid"]
    return {
        "id": coach["_id"], "name": coach["name"], "slot": slot, "teamid": coach["teamid"], "team": team,
        # CoachProxy.expandMoney parses money.mpdata.until as a W3C date; an exception there
        # silently aborts onChangeCoachMeResource before squad/players are read.
        "money": {"ep": coach.get("ep", START_EP), "es": coach.get("es", 0), "cash": 0, "mp": 0, "useable_mp": 0,
                  "mpdata": {"point": 0, "until": "2030-01-01T00:00:00.000Z"}},
        # always a VIP member playing from an official PC warnet (IGR / GCA): CoachProxy.igr,
        # isVip() = vipDetail > 0 and vipExpireAt in the future; vipStatus.VIP1 = VIP expiry
        # after a VVIP period (updateVipExpireAt)
        "igr": True, "vipDetail": VIP_DETAIL, "vipExpireAt": VIP_UNTIL, "vipStatus": {"VIP1": VIP_UNTIL},
        "sp": {"point": 0}, "gpdata": {"gp": 0}, "badges": [], "currentbadge": 0,
        # league.leagueid -> CoachProxy.leagueId: Single > Liga builds the league from it
        "levelinfo": coach_levelinfo(coach), "statistics": {},
        "league": {"leagueid": roster_summary(teamid).get("league", {}).get("id", 0)},
        # limits.cups -> CupProxy.playMax (cups you can run at once); limits.players/baseplayers
        # -> the market's player-slot check (TransferPurchaseTabPage._limitPlayerCount)
        # limits.firstTeam: Skuad tab moveToFirstTeam reads it first and silently gives up when
        # it is missing, so Tim Cadangan cards (packs, trades) could never reach Tim inti/Formasi
        "club": {}, "uimode": 0, "limits": {"cups": 3, "players": MAX_PLAYERS, "baseplayers": MAX_PLAYERS,
                                             "firstTeam": FIRST_TEAM_MAX},
        "transferfavorites": [], "currdivision": "",
        # playlimit {modeid: {playcount}}: Liga's Mulai/Simulasi buttons compare playcount with
        # PLAYLIMIT.maxplay; without the key playcount stays undefined and they stay disabled
        "playlimit": {},
        "kit": team_kit(teamid), "summary": team_summary(team, teamid),
        # Tim > Klub > Informasi tim (issue #9): TeamStaticInfo reads career.appat (start date,
        # W3C; a manager from before this field gets the day it is first sent) and stadium {id};
        # TeamManagementTeamInfoTabPage draws its player panel only once stadium is defined
        "career": {"appat": coach.setdefault("appat", w3c(time.time()))},
        "stadium": {"id": club_stadium(teamid)},
        # cups -> CupProxy.cupPlayList: {metaid, cupid} of cups not left yet (front screen resumes
        # them; an ended one shows its won/eliminated screen with the reward button -> /leave)
        "items": coach_items(st, slot), "matchstats": [], "scouters": coach_scouters(st, slot),
        "cups": [{"metaid": c["metaid"], "cupid": c["_id"]} for c in (st.get("cups") or {}).values()],
        # SquadScreenHandler: formation combobox reads /coach/me?path=formations
        "formations": team["formations"],
        # Formasi opens preset squad team.presetidx (STATICVALUES has `limit`): generateCaptainFrom
        # CoachInfo copies THIS coach-level teamsquadlist into its team and SquadUtil.selectPresetSquad
        # reads .preset[i] {formation, positions, kickers, captain}; none (was []) = "Tidak cukup
        # pemain". The client re-fills holes / bench and saves it.
        "teamsquadlist": {"preset": preset_squads(team)},
    }


def coach_me_resources(st, slot):
    """The /coach/me resource for a reply's `resources`. CoachProxy's fetchCoach* read
    getData("/coach/me?path=X"), which NetEvent.getDataEx resolves by walking this body; pushing
    every ?path= part too re-ran onChangeCoachMeResource per part and nested the client's
    resource chain until AS3 "Error #1023: Stack overflow" at login."""
    return [{"uri": "/coach/me", "body": coach_me(st, slot)}]


def _default_slot(st):
    return next((c["slot"] for c in st["coaches"] if c["_id"] == st["defaultcoachid"]),
                st["coaches"][0]["slot"] if st["coaches"] else 0)  # default manager deleted: the other one


def ep_coach_me(query, body):
    st = _state()
    return _json(coach_me(st, _default_slot(st)))


def ep_coach_onready(query, body):
    # POST /coach/me/onready comes right after CoachProxy.invalidate() -> reset() (which nulls
    # _squad); without /coach/me in this reply the menu is built with squad null (black FREEROAM).
    st = _state()
    return _json({"result": True, "resources": coach_me_resources(st, _default_slot(st))})


def ep_default_coach(slot, query, body):
    # PUT /coach/<slot>/default: the client calls setLocalCoachId(body.resources[0].body.id);
    # resources are also fed to cached resources, so /coach/me (CoachProxy) goes first.
    st = _state(); st["defaultcoachid"] = coach_id(slot)
    daily_login(st)  # first login of the day: today's reward goes to the Bag
    if str(slot) in st["teams"]:
        balance_first_team(st["teams"][str(slot)])
        fix_formation(st["teams"][str(slot)], next(c["teamid"] for c in st["coaches"] if c["slot"] == slot))
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


TACTIC_SLOTS = 6


def default_tactic(i):
    # TacticsController.setCurrentTactics fields; sliders 1..100, positioning/defenderline are
    # 0/1 radios, teammentality 1..5. name "" -> client fills the localized preset name.
    return {"id": i, "name": "", "teammentality": 3,
            "bus": {"buildupspeed": 50, "passing": 50, "positioning": 0},
            "cc": {"passing": 50, "crossing": 50, "shooting": 50, "positioning": 0},
            "def": {"mentality": 50, "aggression": 50, "teamwidth": 50, "defenderline": 0}}


def _tactics(st):
    slot = str(_default_slot(st))
    saved = st.setdefault("tactics", {}).setdefault(slot, {})
    return saved, [saved.get(str(i)) or default_tactic(i) for i in range(TACTIC_SLOTS)]


def ep_tactic_all(query, body):
    # GET /game/my/tactic/all -> Array of 6 tactics (TeamManagementTeamTacticsTabPage.onReceived)
    return _json(_tactics(_state())[1])


def ep_tactic(i, query, body):
    """Save (PUT, body = tactic) or reset (DELETE -> {result, resources:[{body: default}]})."""
    req = json.loads(body or b"{}")
    st = _state(); saved, _ = _tactics(st)
    if "bus" in req:
        saved[str(i)] = dict({k: v for k, v in req.items() if k != "_method"}, id=i)
        _save(st)
        return _json({"result": True})
    saved.pop(str(i), None); _save(st)
    return _json({"result": True, "resources": [{"uri": f"/game/my/tactic/{i}", "body": default_tactic(i)}]})


# --------------------------------------------------------------------------- #
# Single > Liga (League 2.0). LeagueCupProxy builds the whole calendar client-side from
# /league2/me: league.teams + openingday, one match per round from createSchedule (ported
# below as league_round). The server keeps results and the table:
#   creation screen: GET /league2/me (difficultybest/difficultyselect), /league2/reward,
#     POST /league2/sponsor/<difficulty>, POST /league2/calendar {difficulty, sponsor}
#   a round: POST /league2/match (-> /match/<id> resource, stage created) ->
#     PUT /match/<id>/side/<s>/ready (-> stage playing -> StartSingleMatch) ->
#     PUT /match/<id>/end {home:{id,score}, away:{id,score}} -> leagueparam + /league2/me
#   or POST /league2/match/sim (no play), POST /league2/sleep (bye round)
# laststatus "league:<round>" tells the client which day it is (LeagueCupProxy.setToday).
# --------------------------------------------------------------------------- #
LEAGUE_SIZE = 10  # the creation screen shows 10 opponent crests


def _db():
    c = sqlite3.connect(gen_teams.DB); c.row_factory = sqlite3.Row
    return c


def league_teams(leagueid, mine):
    """My club + the strongest clubs of its league in fifadb (base cards, full squads)."""
    with closing(_db()) as c:
        rows = c.execute("""SELECT p.teamid FROM players p JOIN permid m ON m.spid = p.spid AND m.licensed = 1
                            WHERE p.leagueid = ? AND p.spid < 1000000 GROUP BY p.teamid
                            HAVING COUNT(*) >= 16 ORDER BY MAX(p.overallrating) DESC""", (leagueid,)).fetchall()
    return [mine] + [r[0] for r in rows if r[0] != mine][:LEAGUE_SIZE - 1]


def league_round(teams, rnd):
    """Fixtures [(home, away)] of round rnd: LeagueCupProxy.createSchedule/getRotatedIndexAt
    (circle method; second half swaps home/away). None = bye (odd team count)."""
    n = len(teams); size = n + n % 2; per = size - 1
    flip, r = (rnd // per) % 2 == 1, rnd % per

    def rot(i):
        k = 0 if i == 0 else (i - 1 + r) % per + 1
        return teams[k] if k < n else None
    pairs = []
    for k in range(size // 2):
        a, b = rot(k), rot(size - 1 - k)
        f = (not flip) if (k == 0 and r % 4 > 1) else flip
        pairs.append((b, a) if f else (a, b))
    return pairs


def _poisson(rng, lam):
    lim, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= lim:
            return k
        k += 1


def team_strength(st, teamid):
    """Average rating (+ grade boost) of the best 11."""
    raw = st["teams"].get(str(_default_slot(st))) if teamid == my_teamid(st) else None
    ovrs = sorted((player_ovr(p) for p in (raw or roster_team(teamid))["players"]), reverse=True)[:11]
    return sum(ovrs) / len(ovrs) if ovrs else 60


def sim_score(rng, home, away):
    """ponytail: Poisson goals from the rating gap (+3 home edge); no match engine."""
    d = (home + 3 - away) / 10
    return _poisson(rng, max(0.3, 1.4 + 0.6 * d)), _poisson(rng, max(0.2, 1.1 - 0.6 * d))


def league_stats(teams, records, prev=None):
    """league.statistics {teamid: {wins, draws, losses, goals, goalsconceded, awaygoals,
    point, rank, before{rank, point}}} (LeagueCupProxy.makeLeagueRanking)."""
    s = {str(t): {"wins": 0, "draws": 0, "losses": 0, "goals": 0, "goalsconceded": 0,
                  "awaygoals": 0, "point": 0} for t in teams}
    for m in records:
        h, a = s[str(m["home"])], s[str(m["away"])]
        gh, ga = m["goals"]["home"], m["goals"]["away"]
        h["goals"] += gh; h["goalsconceded"] += ga
        a["goals"] += ga; a["goalsconceded"] += gh; a["awaygoals"] += ga
        if gh != ga:
            win, lose = (h, a) if gh > ga else (a, h)
            win["wins"] += 1; win["point"] += 3; lose["losses"] += 1
        else:
            h["draws"] += 1; a["draws"] += 1; h["point"] += 1; a["point"] += 1
    order = sorted(teams, key=lambda t: tuple(-v for v in (
        s[str(t)]["point"], s[str(t)]["goals"] - s[str(t)]["goalsconceded"], s[str(t)]["goals"], s[str(t)]["awaygoals"])))
    for i, t in enumerate(order):
        s[str(t)]["rank"] = i + 1
    for t, v in s.items():
        p = (prev or {}).get(t) or v
        v["before"] = {"rank": p["rank"], "point": p["point"]}
    return s


def my_teamid(st):
    return next(c["teamid"] for c in st["coaches"] if c["slot"] == _default_slot(st))


def l2_me(st):
    """GET /league2/me body; LeagueCupProxy.fetch* read each key as a path."""
    teamid = my_teamid(st)
    lg = st.get("league2") or {}
    me = {"teamid": teamid, "leagueid": lg.get("leagueid") or roster_summary(teamid).get("league", {}).get("id", 0),
          # creation screen: selectable = difficultybest - 10 (24 unlocks all 10 normal + 5
          # ultimate levels), preselected = difficultyselect - 10
          "difficultybest": 24, "difficultyselect": lg.get("difficultyselect", 10),
          # no cupqualifier/cupfinal keys: any object there makes fetchCupQualifier build
          # cup groups (makeLeagueCupGroupTeams -> TypeError on missing teamgroups)
          "laststatus": lg.get("laststatus", ""), "cupinfo": {"entered": False},
          "leader": {"league": {}, "cup": {}},
          # MenuScreen: season.status started/finished -> league front, else creation
          "sponsoroffice": lg.get("sponsoroffice", {"season": {"status": "none"}})}
    if lg.get("league"):
        me.update(openingday=lg["openingday"], league=lg["league"])
    return me


def l2_resources(st):
    return [{"uri": "/league2/me", "body": l2_me(st)}]


def ep_l2_me(query, body):
    return _json(l2_me(_state()))


def ep_l2_reward(query, body):
    # LeagueCupCreationScreen.onCalendarRewardsResourceReceived: Array indexed by difficulty
    # level (0-9 normal, 10-14 ultimate) of {ep, items[]}
    return _json([{"ep": 20000 * (i + 1), "items": []} for i in range(15)])


# sponsorid -> its mission id; LEAGUE2SPONSOR.mission[mid] = League2_sponsor_title_<mid> with
# the target in "lv1": 2 = finish in the top N, 3 = N wins in a row, 4 = N clean sheets in a row
SPONSORS = {"1": "2", "2": "3", "3": "4"}
MISSION_TARGET = {"2": 3, "3": 3, "4": 2}  # keep in sync with LEAGUE2SPONSOR lv1


def ep_l2_sponsor(difficulty, query, body):
    """POST /league2/sponsor/<difficulty>: offers. OnReceivedSponsorList reads level, maxround
    and sponsors[] {_id, sponsorid, missions[{mid}]} (names/logos/goals from LEAGUE2SPONSOR)."""
    return _json({"result": True, "level": 1, "maxround": 2 * (LEAGUE_SIZE - 1) - 1,
                  "sponsors": [{"_id": sid, "sponsorid": sid, "missions": [{"mid": mid}]} for sid, mid in SPONSORS.items()]})


def mission_progress(st, mid):
    """(progress args, achieved) of a sponsor mission from my league results so far."""
    lg = st.get("league2") or {}; league = lg.get("league") or {}
    me = my_teamid(st)
    mine = sorted((m for m in league.get("matchrecords", []) if me in (m["home"], m["away"])), key=lambda m: m["round"])
    goals = [(m["goals"]["home"], m["goals"]["away"]) if m["home"] == me else (m["goals"]["away"], m["goals"]["home"]) for m in mine]

    def best_run(ok):
        best = run = 0
        for g in goals:
            run = run + 1 if ok(g) else 0; best = max(best, run)
        return best
    target = MISSION_TARGET.get(mid, 1)
    if mid == "2":
        rank = league.get("statistics", {}).get(str(me), {}).get("rank", 0)
        done = len(mine) > league.get("maxround", 0)  # season over
        return [rank], done and 0 < rank <= target
    value = best_run((lambda g: g[0] > g[1]) if mid == "3" else (lambda g: g[1] == 0))
    return [value], value >= target


def ep_l2_achievement(query, body):
    """PUT /league2/sponsor/achievement -> the chosen sponsor's goals for the calendar tab
    (setSponsorGoalList: missions[{mid, achievement, progress[args]}]; getProgressString fills
    LEAGUE2SPONSOR.mission[mid].progress with progress)."""
    st = _state(); lg = st.get("league2") or {}
    mid = SPONSORS.get(str(lg.get("sponsor")), "2")
    progress, done = mission_progress(st, mid)
    return _json({"result": True, "level": 1, "missions": [{"mid": mid, "achievement": done, "progress": progress}]})


# Club creation > "Tim lain" (StartupTeamCreationScreen + TeamSelectionUtil): nation -> league ->
# club steppers from SORTNATION [nationid], SORTLEAGUE {nationid: [leagueid]} and SORTTEAM
# {leagueid: [teamid]}; the picked club's squad is /static/info/authentic/team/licensed/<id>
# ({teamid, summary, team}, built by gen_teams.team like the six recommended clubs).
CLUB_MIN_PLAYERS = 16  # licensed 2017 cards a club needs to be listed
_CLUBS = []


def club_index():
    """[(nationid, [(leagueid, [teamid])])] of clubs with a full 2017 squad, strongest first (by
    their best eleven); a league's nation is its players' most common nationality. National
    teams are league 78 with their players' nationalteamid as the squad (gen_teams.team)."""
    if not _CLUBS:
        with closing(_db()) as c:
            rows = c.execute(f"""SELECT p.spid, p.leagueid, p.teamid, p.nationalteamid, p.nationality, {POSOVR}
                                 FROM players p JOIN permid m ON m.spid = p.spid AND m.licensed = 1
                                 WHERE p.spid / 1000000 = ?""", (gen_teams.CURRENT_SEASON,)).fetchall()
        squads, nats = {}, {}
        for spid, lid, tid, ntid, nat, ovr in rows:
            squads.setdefault((lid, tid), {})[spid] = ovr
            if ntid > 0:  # -1 / 0 = none
                squads.setdefault((gen_teams.NATIONAL_LEAGUE, ntid), {})[spid] = ovr
            nats.setdefault(lid, collections.Counter())[nat] += 1
        power = {k: sum(sorted(v.values())[-11:]) / 11 for k, v in squads.items() if len(v) >= CLUB_MIN_PLAYERS}
        leagues = {}
        for (lid, tid), p in power.items():
            leagues.setdefault(lid, []).append((p, tid))
        by_nation = {}
        for lid, teams in leagues.items():
            teams.sort(reverse=True)
            by_nation.setdefault(nats[lid].most_common(1)[0][0], []).append((teams[0][0], lid, [t for _, t in teams]))
        # the national teams' nation last (they made it the strongest; the picker opens on the first)
        _CLUBS.extend((n, [(lid, ts) for _, lid, ts in sorted(ls, reverse=True)])
                      for n, ls in sorted(by_nation.items(), key=lambda kv: (
                          any(l[1] == gen_teams.NATIONAL_LEAGUE for l in kv[1]), -max(l[0] for l in kv[1]))))
    return _CLUBS


def ep_sortnation(query, body):
    return _json([n for n, _ in club_index()])


def ep_sortleague(query, body):
    return _json({str(n): [lid for lid, _ in ls] for n, ls in club_index()})


def ep_sortteam(query, body):
    """/static/db/SORTTEAM {leagueid: [teamid]}: the club picker above; Liga's creation screen
    counts my own league's clubs (the ones its calendar will use)."""
    st = _state()
    out = {str(lid): ts for _, ls in club_index() for lid, ts in ls}
    if st["coaches"]:
        teamid = my_teamid(st)
        lid = roster_summary(teamid).get("league", {}).get("id", 0)
        out[str(lid)] = league_teams(lid, teamid)
    return _json(out)


def ep_authentic_team(kind, teamid, query, body):
    """/static/info/authentic/team/licensed|all/<teamid>: a club's starter squad {teamid, summary,
    team} (responses/ files override for the recommended clubs). StartupPlayerSelectionScreen
    (after "Tim lain") looks up team.captain among team.players by id and dresses its 3D player
    in kit.availables.home/goalie."""
    r = roster(int(teamid))
    team = dict(r["team"], players=[dict(p, id=str(p["spid"])) for p in r["team"]["players"]])
    team["captain"] = str(team["squad"].get("captain") or "")
    return _json({**r, "team": team, "teamid": int(teamid), "kit": team_kit(int(teamid))})


def ep_l2_calendar(query, body):
    """POST /league2/calendar {difficulty, sponsor}: start a season."""
    req = json.loads(body or b"{}")
    st = _state(); teamid = my_teamid(st)
    lid = roster_summary(teamid).get("league", {}).get("id", 0)
    teams = league_teams(lid, teamid)
    day = int(time.time() // 86400 * 86400 * 1000)  # today 00:00 UTC, ms
    st["league2"] = {"leagueid": lid, "difficultyselect": int(req.get("difficulty") or 10),
                     "sponsor": req.get("sponsor"), "laststatus": "opening", "openingday": day,
                     "sponsoroffice": {"season": {"status": "started"}},
                     "league": {"teams": teams, "maxround": 2 * (len(teams) - 1) - 1, "nextround": 0,
                                "matchrecords": [], "statistics": league_stats(teams, [])}}
    _save(st)
    return _json({"result": True, "resources": l2_resources(st)})


def league_play_round(st, rnd, mine=None, seed=None):
    """Play league round rnd: my fixture gets `mine` (home, away goals) or is simulated,
    the rest is simulated. Updates table + laststatus, returns the client's leagueparam."""
    lg = st["league2"]; league = lg["league"]
    if any(m["round"] == rnd for m in league["matchrecords"]):
        return {"matchtype": "league", "round": rnd, "leaguematches": [m for m in league["matchrecords"] if m["round"] == rnd]}
    rng = random.Random(seed)
    me = my_teamid(st); played = []
    for h, a in league_round(league["teams"], rnd):
        if h is None or a is None:
            continue
        if mine is not None and me in (h, a):
            gh, ga = mine
        else:
            gh, ga = sim_score(rng, team_strength(st, h), team_strength(st, a))
        played.append({"type": "league", "matchtype": "league", "round": rnd, "home": h, "away": a,
                       "goals": {"home": gh, "away": ga}})
    league["matchrecords"] += played
    league["statistics"] = league_stats(league["teams"], league["matchrecords"], league["statistics"])
    league["nextround"] = rnd + 1
    lg["laststatus"] = f"league:{rnd}"
    return {"matchtype": "league", "round": rnd, "leaguematches": played}


def league_match_body(st, req, playtype):
    me = coach_me(st, _default_slot(st)); teamid = me["teamid"]
    opp = req["away"] if req["home"] == teamid else req["home"]
    user = {"id": me["id"], "name": me["name"], "levelinfo": me["levelinfo"]}
    lg = st["league2"]
    match = new_match("League_2_league_MGR" if playtype == "mgr" else "League_2_league",
                      match_side(st["teams"][str(_default_slot(st))], teamid, user, _tactics(st)[1]),
                      match_side(roster_team(opp), opp))
    gs = match["gamesettings"]
    gs["home"] = req["home"] == teamid  # I am always the left side
    gs["kit"] = ["home", "away"] if gs["home"] else ["away", "home"]
    # league level 10..24: the in-match overlay shows LEAGUE2_DIFFICULTY_<difficulty - 9>
    gs["difficulty"] = lg.get("difficultyselect", 10)
    # MatchProxy.leagueparam: LeagueCupGameSettingScreen.onPlaying reads leagueparam.matchtype
    # unguarded (`p != null && t == "cupqualifier" || p.matchtype == "cupfinal"`) -> required
    match["leagueparam"] = {"matchtype": req.get("matchtype", "league"), "round": req.get("round", 0),
                            "home": req["home"], "away": req["away"], "leagueid": lg.get("leagueid")}
    return match


def sim_events(match, mine, opp, rng=random):
    """eventlist for Liga's simulation screen (LeagueCupFrontScreenSimulation.rebuildSimulationEvent):
    [{time 1..90, team 0 = mine / 1, player = a starter's spid, event}] in time order. GOAL_EVENT
    adds to the score it shows, so there is one per goal of the result (an ASSIST_EVENT before
    some); SHOT_ON_GOAL_EVENT is a miss unless the keeper's SAVE_EVENT follows; a second
    YELLOW_CARD_EVENT for a player shows red. The screen adds kick-off, half time and full time.
    It was sent empty, so a simulated match showed 0-0 and no play whatever the result."""
    xi = [[(int(p["spid"]), p["pos"]) for p in match["side"][s]["team"]["squad"]["positions"] if p["pos"] < POS_SUB]
          for s in ("left", "right")]
    keeper = [next((s for s, pos in x if pos == 0), x[0][0]) for x in xi]
    def outfield(t, w=(1, 3, 6)):  # DF / MF / FW: forwards score and shoot most
        field = [(s, w[0] if pos <= 8 else w[1] if pos <= 19 else w[2]) for s, pos in xi[t] if pos]
        return rng.choices([s for s, _ in field], [n for _, n in field])[0]
    ev = []
    for t, goals in ((0, mine), (1, opp)):
        for _ in range(goals):
            minute, scorer = rng.randint(1, 90), outfield(t)
            if rng.random() < 0.6:
                ev.append({"time": minute, "team": t, "player": outfield(t, (2, 4, 2)), "event": "ASSIST_EVENT"})
            ev.append({"time": minute, "team": t, "player": scorer, "event": "GOAL_EVENT"})
    for _ in range(rng.randint(3, 7)):
        t, minute = rng.randint(0, 1), rng.randint(1, 90)
        ev.append({"time": minute, "team": t, "player": outfield(t), "event": "SHOT_ON_GOAL_EVENT"})
        if rng.random() < 0.6:
            ev.append({"time": minute, "team": 1 - t, "player": keeper[1 - t], "event": "SAVE_EVENT"})
    for _ in range(rng.randint(0, 3)):
        t = rng.randint(0, 1)
        ev.append({"time": rng.randint(1, 90), "team": t, "player": outfield(t, (4, 3, 1)), "event": "YELLOW_CARD_EVENT"})
    return sorted(ev, key=lambda e: e["time"])  # stable: an assist stays before its goal, a save after its shot


def sim_result(match, events, my_home, rng=random):
    """match.result for a simulated Liga match, shaped like the report a played match posts at
    /match/<id>/end, which PostMatchResultDefaultScene.onResultReceived reads (scores, the
    formation's player stats, possession, attack direction, MOTM). Built from the simulation's
    events; it was missing, so the result screen after a simulation stayed blank. id/dbid are
    player ids (spid % 1e6) as in the client's own report, spid the card's (fill_players); y counts
    from the far goal (keeper at 0.98)."""
    pair = lambda lo, hi, rate: (lambda n: [round(n * rate), n])(rng.randint(lo, hi))
    teams = []
    for t, s in ((0, "left"), (1, "right")):
        pos = match["side"][s]["team"]["squad"]["positions"]
        players = []
        for p in (p for p in pos if p["pos"] < POS_SUB):
            mine = [e["event"] for e in events if e["team"] == t and e["player"] == int(p["spid"])]
            goals, assists, shots = mine.count("GOAL_EVENT"), mine.count("ASSIST_EVENT"), mine.count("SHOT_ON_GOAL_EVENT")
            saves, yellow = mine.count("SAVE_EVENT"), mine.count("YELLOW_CARD_EVENT")
            pid, start = int(p["spid"]) % 1000000, p.get("starting") or [1, 1, 0.5, 0.5]
            players.append({
                # role = the squad position (0 = keeper put every player at the goal) and spid = the
                # card's, whose season the labels show (issue #26); id/dbid stay the player id
                "id": str(pid), "spid": int(p["spid"]), "dbid": pid, "role": p["pos"], "x": start[2], "y": round(1 - start[3], 4),
                "rating": round(min(10.0, max(4.0, 6.0 + goals + 0.5 * assists + 0.3 * saves - 0.4 * yellow
                                                   + rng.uniform(-0.4, 0.9))), 1),
                "goals": goals, "assists": assists, "saves": saves, "shotsOnGoal": goals + shots,
                "shotAttempt": goals + shots + rng.randint(0, 1) * bool(p["pos"]),
                "passes": pair(20, 50, rng.uniform(0.7, 0.92)) if p["pos"] else pair(5, 15, 0.8),
                "dribbles": pair(0, 6, 0.6), "tackles": pair(0, 5, 0.6) if p["pos"] else [0, 0],
                "cards": [min(yellow, 1), int(yellow >= 2)], "injure": [0, 0],
                "runDistanceMeter": round(rng.uniform(8000, 12000) if p["pos"] else rng.uniform(3000, 5000), 1),
                "longTermStamina": 1})
        total = lambda k: sum(p[k] for p in players)
        sums = lambda k: [sum(p[k][0] for p in players), sum(p[k][1] for p in players)]
        teams.append({
            "id": match["side"][s]["team"]["teamid"], "score": total("goals"), "goals": total("goals"),
            "assists": total("assists"), "saves": total("saves"), "shotsOnGoal": total("shotsOnGoal"),
            "shotAttempt": total("shotAttempt"), "passes": sums("passes"), "dribbles": sums("dribbles"),
            "tackles": sums("tackles"), "cards": sums("cards"), "crossPasses": pair(5, 20, 0.35),
            "throughPasses": pair(2, 10, 0.4), "blocks": pair(0, 5, 0.5), "fouls": sums("cards")[0] + rng.randint(2, 8),
            "offsides": rng.randint(0, 3), "clearances": rng.randint(5, 20), "intercepts": rng.randint(5, 20),
            "tackles_inbox": 0, "passes_inbox": 0, "intercepts_inbox": 0, "dribble_inbox": 0,
            "rating": round(sum(p["rating"] for p in players) / len(players), 2), "runDistanceKm": round(total("runDistanceMeter") / 1000, 1),
            "players": players, "substitutes": [], "users": [], "shootout": 0, "injuredPlayers": 0,
            "reserved": [{"id": str(int(p["spid"]) % 1000000), "rating": 0, "dbid": int(p["spid"]) % 1000000}
                         for p in pos if p["pos"] == POS_SUB]})
    mine_poss = rng.randint(40, 60)  # possession totals add up to 100; left / center / right likewise
    for team, share in zip(teams, (mine_poss, 100 - mine_poss)):
        left = rng.randint(15, 45); center = rng.randint(20, 100 - left - 10)
        team["possession"] = {"total": share, "left": left, "center": center, "right": 100 - left - center,
                              "df": rng.randint(10, 30), "mf": rng.randint(40, 60), "fw": rng.randint(10, 30)}
    me, opp = ("home", "away") if my_home else ("away", "home")
    side = {me: teams[0], opp: teams[1]}
    team_of, best = max(((name, p) for name, team in side.items() for p in team["players"]), key=lambda x: x[1]["rating"])
    return {"myTeam": me, "opponentTeam": opp, "home": side["home"], "away": side["away"], "matchFinishedTime": 5400,
            "forfeits": 0, "motm": {"team": team_of, "id": best["id"], "spid": best["spid"], "dbid": best["dbid"],
                                    "rating": best["rating"], "name": "XXDISPLAYNAMEXX"}}


def ep_l2_match(query, body, sim=False):
    """POST /league2/match {matchtype, playtype, round, home, away, date} -> a /match/<id>
    resource (MatchProxy.registerByResource). /match/sim plays the round right away."""
    req = json.loads(body or b"{}")
    st = _state(); lg = st.get("league2")
    if not lg or not lg.get("league"):
        return _json({"result": False, "reason": "LEAGUE_FAIL"})
    coupon = None
    if sim:  # one League Simulation coupon (any item of that type, as the client counts them)
        coupon = next((i for i in my_coach(st).get("items", []) if i["remains"] > 0 and i["itemid"] in ITEMS
                       and ITEMS[i["itemid"]][2] == "LEAGUE_SIMULATION"), None)
        if coupon is None:
            return _json({"result": False, "reason": "NOT_ENOUGH_ITEM"})
        coupon["remains"] -= 1
        my_coach(st)["items"] = [i for i in my_coach(st)["items"] if i["remains"] > 0]
    match = league_match_body(st, req, req.get("playtype"))
    st["match"] = match
    lg["pending"] = {"id": match["id"], "round": req.get("round", 0), "home": req["home"], "away": req["away"]}
    out = {"result": True}
    if sim:
        param = league_play_round(st, req.get("round", 0))
        mine = next((m for m in param["leaguematches"] if my_teamid(st) in (m["home"], m["away"])), None)
        match.update(stage="closed", simulated=True)
        match["gamesettings"]["simulated"] = True
        g = mine["goals"] if mine else {"home": 0, "away": 0}
        mine_g, opp_g = (g["home"], g["away"]) if mine and mine["home"] == my_teamid(st) else (g["away"], g["home"])
        events = sim_events(match, mine_g, opp_g)
        match["result"] = sim_result(match, events, match["gamesettings"]["home"])  # the result screen after it
        # then the reward screen: EXP and EP as after a played match (without it the screen stayed
        # empty and the way back to the Liga menu stopped there)
        match["reward"] = match_reward(st, match["result"])
        add_ep(st, match["reward"]["money"]["reward"]["total"])
        lg.pop("pending", None)  # the round is played already
        out.update(leagueparam=param, eventlist=events, score=mine and mine["goals"])
    _save(st)
    out["resources"] = ([{"uri": f"/match/{match['id']}", "body": match}]
                        + (l2_resources(st) + coach_me_resources(st, _default_slot(st)) if sim else []))  # coupon count
    return _json(out)


def ep_l2_sleep(query, body):
    """POST /league2/sleep {matchtype, round}: my bye round; the others still play."""
    req = json.loads(body or b"{}")
    st = _state(); lg = st.get("league2")
    param = league_play_round(st, req.get("round", 0)) if lg and lg.get("league") else {}
    _save(st)
    return _json({"result": True, "leagueparam": param, "resources": l2_resources(st)})


def ep_l2_finish(query, body):
    """PUT /league2/abandon: give up the season (back to the creation screen)."""
    st = _state()
    lg = st.get("league2") or {}
    st["league2"] = {"difficultyselect": lg.get("difficultyselect", 10)}
    _save(st)
    return _json({"result": True, "resources": l2_resources(st)})


LINES = {"GK": range(0, 1), "DF": range(1, 9), "MF": range(9, 20), "FW": range(20, 28)}  # Enums.PLAYERPOSITION
STAT_LEADERS = 3  # players per stat on the Rekor gabungan tab


def league_record(st, stats):
    """Add a played league match to my players' season record (st.league2.playerrecords, reset by
    a new season): what Rekor liga > Rekorku shows. Unused subs have no rating; passes and tackles
    are [done, tried] in matchStats; role = the position he played (Enums.PLAYERPOSITION)."""
    recs = st["league2"].setdefault("playerrecords", {})
    for p, s in match_cards(st, stats):
        if not s.get("rating"):
            continue
        r = recs.setdefault(iid(p), dict.fromkeys(("matches", "ratings", "goals", "assists", "passes",
                                                     "passtries", "tackles", "saves"), 0))
        pair = lambda k: (list(s.get(k) or []) + [0, 0])[:2]
        r.update(id=iid(p), spid=p["spid"], role=int(s.get("role") or 0))
        r["matches"] += 1
        r["ratings"] = round(r["ratings"] + float(s["rating"]), 2)
        for k in ("goals", "assists", "saves"):
            r[k] += int(s.get(k) or 0)
        r["passes"] += int(pair("passes")[0]); r["passtries"] += int(pair("passes")[1])
        r["tackles"] += int(pair("tackles")[0])


def ep_l2_history_players(query, body):
    """GET /league2/history/players/league: [{id: card _id, matches, ratings (sum), goals, assists,
    passes, tackles, saves}] (LeagueCupRecordTabPage.joinPlayerData; a card with none shows 0)."""
    return _json(list(((_state().get("league2") or {}).get("playerrecords") or {}).values()))


def ep_l2_leaders(query, body):
    """PUT /league2/leader/league -> Rekor gabungan (LeagueCupTotalRecordTabPage): best XI by line
    (my formation's slots, best average rating of the players who played there) and the top
    players per stat, each {spid, teamid, value}, from my players' season records. The page
    joins every key of the reply into one player list, so it holds nothing else. ponytail: my
    players only (AI players' stats are not kept)."""
    st = _state(); me = my_teamid(st)
    recs = [r for r in ((st.get("league2") or {}).get("playerrecords") or {}).values() if r["matches"]]
    avg = lambda r: round(r["ratings"] / r["matches"], 1)
    entry = lambda r, v: {"spid": r["spid"], "teamid": me, "value": v}
    squad = (st["teams"].get(str(_default_slot(st))) or {"squad": {"positions": []}})["squad"]["positions"]
    out = {}
    for line, rng in LINES.items():
        slots = sum(s["pos"] in rng for s in squad)
        out[line] = [entry(r, avg(r)) for r in sorted((r for r in recs if r["role"] in rng), key=avg, reverse=True)[:slots]]
    stat = {"ratings": avg, "goals": lambda r: r["goals"], "assists": lambda r: r["assists"],
            "tackles": lambda r: r["tackles"], "saves": lambda r: r["saves"],
            "passes": lambda r: round(r["passes"] / r["passtries"], 2) if r["passtries"] else 0}  # success rate
    for k, f in stat.items():
        out[k] = [entry(r, f(r)) for r in sorted(recs, key=f, reverse=True) if f(r)][:STAT_LEADERS]
    return _json(out)


def season_leaders(st, me, rank, goals):
    """leaderRewards for LeagueCupLeagueRewardScreen: best XI by line (FW/MF/DF/GK, 11 in
    all) + one leader per stat. ponytail: no per-player season stats are kept, so these
    come from my own squad (rating = card rating, stat values derived from team goals)."""
    team = owned_team(st["teams"][str(_default_slot(st))])
    rating = {p["spid"]: player_ovr(p) for p in team["players"]}
    lines = LINES
    starters = [p for p in team["squad"]["positions"] if p["pos"] < POS_SUB]
    entry = lambda spid, value, ep=0: {"spid": spid, "teamid": me, "value": value, "reward": {"count": ep}}
    out = {line: [entry(p["spid"], round(min(9.9, 6 + (rating.get(p["spid"], 80) - 80) / 25), 1))
                  for p in starters if p["pos"] in r] for line, r in lines.items()}
    best = lambda line: max((p["spid"] for p in starters if p["pos"] in lines[line]),
                            key=lambda s: rating.get(s, 0), default=0)
    played = 2 * (LEAGUE_SIZE - 1)
    out.update(ratings=[entry(best("FW"), 7.5, 3000)], goals=[entry(best("FW"), max(1, goals // 2), 3000)],
               assists=[entry(best("MF"), max(1, goals // 3), 2000)], tackles=[entry(best("DF"), played * 3, 2000)],
               passes=[entry(best("MF"), 0.85, 1000)],  # pass success rate; the UI shows value*100 %
               saves=[entry(best("GK"), played * 2, 1000)])
    return out


def league_promote(difficulty):
    """{promote_rank, demote_rank} of a league level: how many clubs go up / down at season end.
    /static/db/LEAGUE2DIFFICULTY: league2difficulty {level: {groupId}} + league2promote {groupId:
    ...}; the standings tab (LeagueCupRankTabPage) colours its rows by it and threw on a missing
    league2difficulty, leaving the table empty (issue #19). Normal 10-19 only go up (19 is the
    top), ultimate 20-24 also go down."""
    with open(os.path.join(RESPONSES, "static_db_LEAGUE2DIFFICULTY.json")) as f:
        t = json.load(f)
    group = t["league2difficulty"].get(str(difficulty), {}).get("groupId")
    return t["league2promote"].get(str(group), {"promote_rank": 0, "demote_rank": 0})


def ep_l2_end(query, body):
    """PUT /league2/end (closing day): season result for LeagueCupLeagueRewardScreen
    {promotion{current,next}, rewards{coach,money.reward{total,detail}}, sponsorRewards,
    leaderRewards, seasonRewards{items}}. The season stays (the reward screen reads it) but
    is marked finished: back on the front, the closing day then has seasonoff -> ON_CLOSED
    -> the creation screen, whose POST /league2/calendar starts the next season."""
    st = _state(); lg = st.get("league2") or {}; league = lg.get("league")
    if not league:
        return _json({"result": False, "reason": "LEAGUE_FAIL"})
    me = my_teamid(st); stats = league["statistics"][str(me)]; rank = stats["rank"]
    cur = lg.get("difficultyselect", 10)
    rule = league_promote(cur)
    nxt = cur + 1 if rank <= rule["promote_rank"] else cur - 1 if rank > len(league["teams"]) - rule["demote_rank"] else cur
    mid = SPONSORS.get(str(lg.get("sponsor")), "2")
    progress, done = mission_progress(st, mid)
    with open(os.path.join(RESPONSES, "static_db_LEAGUE2REWARD.json")) as f:
        sponsor_ep = json.load(f)["sponsor"].get(str(int(mid) - 1), {}).get(str(cur), {}).get("count", 0) if done else 0
    leaders = season_leaders(st, me, rank, stats["goals"])
    leader_ep = sum(e["reward"]["count"] for k in ("ratings", "goals", "assists", "tackles", "passes", "saves")
                    for e in leaders[k])
    base_ep = (LEAGUE_SIZE - rank + 1) * 2000
    season_exp = (LEAGUE_SIZE - rank + 1) * 100
    cprev, ccur = gain_exp(my_coach(st), season_exp, coach_need, COACH_MAX_LEVEL)
    out = {"result": True, "promotion": {"current": cur, "next": nxt},
           # setRewardRankExp: coach.prev/current/reward.total; setRewardRankEP: money.prev +
           # reward.detail.season; the sponsor/leader scenes read detail.sponsor/.leader
           "rewards": {"coach": {"prev": cprev, "current": ccur, "reward": {"total": season_exp}},
                       "money": {"prev": coach_me(st, _default_slot(st))["money"]["ep"],
                                 "reward": {"total": base_ep + sponsor_ep + leader_ep,
                                            "detail": {"season": base_ep, "sponsor": sponsor_ep, "leader": leader_ep}}}},
           "sponsorRewards": {"sponsorid": str(lg.get("sponsor")), "level": 1, "achievement": done,
                              "missions": [{"mid": mid, "achievement": done, "progress": progress}]},
           "leaderRewards": leaders, "seasonRewards": {"items": []}}
    lg.update(difficultyselect=nxt, sponsoroffice={"season": {"status": "finished"}})
    add_ep(st, out["rewards"]["money"]["reward"]["total"])
    _save(st)
    out["resources"] = l2_resources(st)
    return _json(out)


def match_step(mid, body, step):
    """Apply step(match, request) to the live league match (state["match"]) and answer with
    the updated /match/<id> resource; MatchController re-runs processMatchStageResource."""
    req = json.loads(body or b"{}")
    st = _state(); match = st.get("match")
    if not match or match["id"] != mid:
        return _json({"result": False})
    step(match, req)
    _save(st)
    return _json({"result": True, "resources": [{"uri": f"/match/{mid}", "body": match}]})


def _side_ready(side):
    def step(match, req):
        if side in match["side"]:
            match["side"][side]["ready"] = bool(req.get("ready", True))
        if req.get("ready", True):
            match["stage"] = "playing"
    return step


def ep_match_ready(mid, side, query, body):
    """PUT /match/<id>/side/<side>/ready {ready, stage}: single-player, so the match starts
    (stage playing -> LeagueCupGameSettingScreen.onPlaying -> StartSingleMatch)."""
    return match_step(mid, body, _side_ready(side))


NEXT_STAGE = {"created": "squad", "squad": "setting"}


def _player_ready(match, req):
    if req.get("ready", True) and req.get("stage", match["stage"]) == match["stage"]:
        match["stage"] = NEXT_STAGE.get(match["stage"], match["stage"])


def ep_match_player_ready(mid, query, body):
    """PUT /match/<id>/player/ready {ready, stage}: created -> squad (ON_SQUADING: squad screen),
    squad -> setting (LeagueCupSquadSettingHandler.updateStage: game setting screen)."""
    return match_step(mid, body, _player_ready)


def match_cards(st, stats):
    """[(my card, its matchStats player)] for my side's players. In-match spid = the card's
    player id (spid % 1e6); a card in the squad wins over another card of the same player."""
    team, done, out = st["teams"].get(str(_default_slot(st))) or {"players": []}, set(), []
    for s in (stats.get(stats.get("myTeam", "home")) or {}).get("players") or []:
        pid = int(s.get("spid") or 0) % 1000000
        mine = [p for p in team["players"] if int(p["spid"]) % 1000000 == pid and iid(p) not in done]
        p = next((p for p in mine if in_squad(team, p)), mine[0] if mine else None)
        if p is not None:
            done.add(iid(p))
            out.append((p, s))
    return out


# Post-match reward cards (issue #26): PostMatchRewardDefaultScene deals cards 1-3 ("normal";
# card 4 is the PC-bang one) and turns no request on a click: the pick is the server's. The
# clicked card shows extra.availables[extra.selected.normal[0]] (RewardCardFront.setItemData:
# staticdata name/unit/itemicon, count) and openRestCards shows the others on the rest; the
# top-level selected {type: [index]} takes the picked ones out of that rest.
# The admin page edits all of it (gamedata/match_rewards.json): EP and exp (coach, each of my
# players) by result, and the cards [[weight, itemid | {"ep": amount}]] as in shop.json's boxes.
MATCH_REWARD_FILE = os.path.join(HERE, "gamedata", "match_rewards.json")
MATCH_REWARD_DEFAULT = {
    "result": {"win": {"ep": 2000, "coach": 300, "player": 150}, "draw": {"ep": 1000, "coach": 200, "player": 100},
               "loss": {"ep": 500, "coach": 100, "player": 60}},
    "cards": [[30, {"ep": 1000}], [25, {"ep": 3000}], [15, {"ep": 5000}], [8, {"ep": 10000}],
              [10, 92000000], [7, 92000014], [5, 501]]}  # Semua Pemain, '14 Top 200, Lucky EP


def match_reward_cfg():
    try:
        with open(MATCH_REWARD_FILE, encoding="utf-8") as f:
            return {**MATCH_REWARD_DEFAULT, **json.load(f)}
    except (OSError, ValueError):
        return MATCH_REWARD_DEFAULT


def match_cards_reward(st):
    """extra/selected of match.reward: three cards, the first is mine (credited here). A card
    whose product is gone from the Shop is skipped (its staticdata would fail)."""
    pool = [(w, ("ep", p["ep"]) if isinstance(p, dict) else p) for w, p in match_reward_cfg()["cards"]
            if isinstance(p, dict) or p in ITEMS or p in PACKS]
    if not pool:
        return {"extra": {"selected": {}, "availables": []}, "selected": {}}
    cards = random.choices([p for _, p in pool], [w for w, _ in pool], k=3)
    if isinstance(cards[0], tuple):
        add_ep(st, cards[0][1])
    else:
        inventory_add(my_coach(st), cards[0], 1)
    pick = {"normal": [0]}
    return {"extra": {"selected": pick, "availables": [prize_item(p) for p in cards]}, "selected": pick}


def match_reward(st, stats):
    """match.reward for PostMatchRewardDefaultScene.onRewardReceived (paths it reads) and its
    player list (PlayerRewardListItemRenderer: id, spid, prev, current, reward.detail.extra).
    Credits EP, coach exp and exp for every player of mine in matchStats (in-match spid = the
    card's player id, i.e. spid % 1e6), plus a reward card. ponytail: flat exp by result + goals/assists."""
    me, opp = stats.get("myTeam", "home"), stats.get("opponentTeam", "away")
    g = lambda s: int((stats.get(s) or {}).get("score") or 0)
    won, drew = g(me) > g(opp), g(me) == g(opp)
    r = match_reward_cfg()["result"]["win" if won else "draw" if drew else "loss"]
    ep, cexp, pexp = r["ep"], r["coach"], r["player"]
    reward = lambda n: {"total": n, "detail": {"base": n, "extra": 0}}
    prev, cur = gain_exp(my_coach(st), cexp, coach_need, COACH_MAX_LEVEL)
    players = []
    for p, s in match_cards(st, stats):
        n = pexp + 20 * int(s.get("goals") or 0) + 10 * int(s.get("assists") or 0)
        pprev, pcur = gain_exp(p, n, player_need, PLAYER_MAX_LEVEL)
        players.append({"id": iid(p), "spid": p["spid"], "prev": pprev, "current": pcur, "reward": reward(n)})
    return {"matchRewardBackType": 0, **match_cards_reward(st),
            "coach": {"reward": reward(cexp), "prev": prev, "current": cur},
            "money": {"reward": reward(ep)},
            "players": players, "missions": [], "exptankinfo": {}}


def ep_match_get(mid, query, body):
    """GET /match/<id>: the post-match screens re-read result/reward from the match."""
    match = _state().get("match") or {}
    return _json(match if match.get("id") == mid else {})


def ep_match_gamesettings(mid, query, body):
    """PUT /match/<id>/gamesettings {kit: home|away, side: 0 left|1 right} from the game setting
    screen's kit steppers. gamesettings.kit is [left, right] (MatchController
    .processMatchGamesettingsKitResource: mine = kit[mySide == left ? 0 : 1]); the updated match
    resource brings the choice back, and native uses it at kick-off."""
    req = json.loads(body or b"{}")
    st = _state(); match = st.get("match") or {}
    if match.get("id") != mid:  # e.g. a Training Ground match (not stored): as before
        return _json({"result": True})
    if req.get("kit") in ("home", "away") and req.get("side") in (0, 1):
        match["gamesettings"]["kit"][req["side"]] = req["kit"]
        _save(st)
    return _json({"result": True, "resources": [{"uri": f"/match/{mid}", "body": match}]})


def fill_players(match, stats):
    """The game sends matchStats players with role 0 and the player id (spid % 1e6) as spid,
    though x/y are right. The result screen's pitch (GameResultPlayerInfo) puts role 0 = GK at
    the goal, so all eleven were stacked there, and its labels take the season from the spid
    (SeasonIcon.setSeasonBySpid), so every card showed the current season (issue #26).
    players[i] is squad slot i: role = that slot's pos; spid = the card's full spid (players,
    substitutes, MOTM)."""
    sides = match.get("side") or {}
    if not sides:
        return
    for key, default in (("home", "left"), ("away", "right")):
        t = stats.get(key) or {}
        hits = [s for s in sides if str(sides[s]["team"]["teamid"]) == str(t.get("id"))]
        pos = sides[hits[0] if len(hits) == 1 else default]["squad"]["positions"]
        for p, slot in zip(t.get("players") or [], pos):
            if not p.get("role"):
                p["role"] = slot["pos"]
        full = {int(s["spid"]) % 1000000: int(s["spid"]) for s in pos}
        mine = (t.get("players") or []) + (t.get("substitutes") or [])
        if (stats.get("motm") or {}).get("team") == key:
            mine.append(stats["motm"])
        for e in mine:
            if isinstance(e, dict) and e.get("spid"):
                e["spid"] = full.get(int(e["spid"]) % 1000000, e["spid"])


def ep_match_end(mid, query, body):
    """PUT /match/<id>/end matchStats {home:{id, score, players...}, away:{...}, myTeam,
    opponentTeam, motm, ...}. It comes back as match.result (PostMatchResultDefaultScene
    .onResultReceived reads exactly these fields) plus a match.reward."""
    req = json.loads(body or b"{}")
    st = _state(); lg = st.get("league2") or {}; p = lg.get("pending")
    match = st.get("match") if (st.get("match") or {}).get("id") == mid else None
    out = {"result": True}
    if match is not None and match.get("stage") != "closed":  # credit once
        fill_players(match, req)
        match["result"] = {k: v for k, v in req.items() if k != "_method"}
        match["reward"] = match_reward(st, req)
        add_ep(st, match["reward"]["money"]["reward"]["total"])
    cp = st.get("cup_pending") or {}
    if cp.get("id") == mid and cp.get("cupid") in (st.get("cups") or {}):
        h, a = req.get("home") or {}, req.get("away") or {}
        gh, ga = int(h.get("score") or 0), int(a.get("score") or 0)
        sh, sa = int(h.get("shootout") or 0), int(a.get("shootout") or 0)
        if str(h.get("id")) == str(cp["away"]):
            gh, ga, sh, sa = ga, gh, sa, sh
        st["cups"][cp["cupid"]]["_mine"] = (gh, ga, sh, sa)  # applied by PUT /cup/<id>/next
        st.pop("cup_pending")
    if p and p["id"] == mid:
        h, a = req.get("home") or {}, req.get("away") or {}
        gh, ga = int(h.get("score") or 0), int(a.get("score") or 0)
        if str(h.get("id")) == str(p["away"]):  # matchStats home/away are match sides
            gh, ga = ga, gh
        out["leagueparam"] = league_play_round(st, p["round"], (gh, ga))
        league_record(st, req)
        lg.pop("pending", None)
        out["resources"] = l2_resources(st)
    if match is not None:
        match["stage"] = "closed"
        out["resources"] = [{"uri": f"/match/{mid}", "body": match}] + out.get("resources", [])
    _save(st)
    return _json(out)


# --------------------------------------------------------------------------- #
# Single > Cup (PvE cups; also the "Eropa/Amerika Selatan" shortcut). CupProxy/CupController.
#   GET /cup/list -> metas the front screen lists; GET /cup/record -> my cup records.
# --------------------------------------------------------------------------- #
def cup_meta(metaid, name, trophy, quality, matchcount, teams, reward):
    """A /cup/list entry: CupFrontScreen.onCupDetailInternal + CupProxy.onCupListReceived
    fields. difficulty = minimum AI level index (0 amateur .. 4 legendary)."""
    # visible: Boolean (isVisibleValue indexes it per condition otherwise); joinable.allteams
    # skips the teamids/leagueids whitelist ("Tim ini tidak dapat bergabung")
    return {"metaid": metaid, "_id": str(metaid), "name": name, "type": "pve", "teamselect": "user", "visible": True,
            "difficulty": 0, "quality": quality, "matchcount": matchcount, "teamcount_desc": teams,
            "proviso_desc": "PVECUP_INFO_OPTION_NO", "trophy": trophy, "skin": str(metaid),
            # onCupDetailInternal sums bestrewards[-1][*].count where itemid == 1 (EP)
            "bestrewards": [[{"itemid": 1, "count": reward}]],
            "startat": "2020-01-01T00:00:00.000Z", "endat": "2030-12-31T00:00:00.000Z",
            "joinable": {"fee": 0, "igr": False, "vip": 0, "allteams": True, "dayofweek": [1, 1, 1, 1, 1, 1, 1]}}


CUPS = [cup_meta(1, "European Champions Cup", "66", 4, 6, 16, 60000),  # 3 group + QF/SF/F
        cup_meta(2, "South American Cup", "300000", 3, 6, 16, 40000)]


def ep_cup_list(query, body):
    return _json([] if "type=wcpve" in query else CUPS)  # wcpve = World Cup PvE list


def cup_pool(metaid, mine):
    """15 AI clubs: the strongest clubs in fifadb (cup 1) or the next tier (cup 2)."""
    with closing(_db()) as c:
        rows = c.execute("""SELECT p.teamid FROM players p JOIN permid m ON m.spid = p.spid AND m.licensed = 1
                            WHERE p.spid < 1000000 GROUP BY p.teamid HAVING COUNT(*) >= 16
                            ORDER BY MAX(p.overallrating) DESC LIMIT 60""").fetchall()
    ids = [r[0] for r in rows if r[0] != mine]
    return ids[:15] if metaid == 1 else ids[15:30]


def cup_team(st, teamid):
    me = my_teamid(st)
    return {"teamid": teamid, "coach": coach_id(_default_slot(st)) if teamid == me else None}


def new_cup(st, meta, difficulty):
    """A cup instance (CupProxy.updateCurrentCupData): 16 clubs, 4 round-robin groups of 4
    (3 rounds), then an 8-club knock-out. pairs[].legs[leg] = {homeidx, awayidx, score?,
    shootout?} index into that group's teams; rounds[].shuffle -> the draw screen."""
    me = my_teamid(st)
    teams = [me] + cup_pool(meta["metaid"], me)
    random.shuffle(teams)
    groups = [{"teams": [cup_team(st, t) for t in teams[g * 4:g * 4 + 4]],
               "rounds": [{"shuffle": r == 0, "pairs": [{"legs": [{"homeidx": h, "awayidx": a}]}
                                                         for h, a in league_round([0, 1, 2, 3], r)]}
                          for r in range(3)]} for g in range(4)]
    cupid = f"{int(time.time()):08x}{os.urandom(8).hex()}"
    cup = {"_id": cupid, "metaid": meta["metaid"], "name": meta["name"], "type": "pve",
           "difficulty": difficulty, "current": {"phase": 0, "round": 0, "leg": 0},
           "phases": [{"system": "round-robin", "name": "Fase grup", "maxrounds": 3, "groups": groups}],
           "coaches": [{"_id": coach_id(_default_slot(st)), "state": "playing"}],
           "teams": [cup_team(st, t) for t in teams]}
    cup_refresh_stats(cup)
    return cup


def cup_my_pair(cup):
    """(group, leg) of my fixture in the current round, or (None, None)."""
    cur = cup["current"]
    for g in cup["phases"][cur["phase"]]["groups"]:
        for pair in g["rounds"][cur["round"]]["pairs"]:
            leg = pair["legs"][cur["leg"]]
            idx = [leg.get("homeidx"), leg.get("awayidx")]
            if any(i is not None and g["teams"][i]["coach"] for i in idx):
                return g, leg
    return None, None


def group_table(g):
    """[(team index, points, goal diff, goals)] best first."""
    t = {i: [0, 0, 0] for i in range(len(g["teams"]))}
    for rnd in g["rounds"]:
        for pair in rnd["pairs"]:
            leg = pair["legs"][0]
            if "score" not in leg:
                continue
            gh, ga = leg["score"]["home"], leg["score"]["away"]
            for i, f, a in ((leg["homeidx"], gh, ga), (leg["awayidx"], ga, gh)):
                t[i][0] += 3 if f > a else 1 if f == a else 0
                t[i][1] += f - a; t[i][2] += f
    return sorted(t, key=lambda i: tuple(-v for v in t[i]))


def cup_refresh_stats(cup):
    """Per-team W/D/L over the whole cup + group points/rank on every team object (group
    tables, "Juara - <rank> (W/D/L)" next-match panel, "Grup C - Peringkat <rank>")."""
    wdl = {}
    for phase in cup["phases"]:
        for g in phase["groups"]:
            for rnd in g["rounds"]:
                for pair in rnd["pairs"]:
                    leg = pair["legs"][0]
                    if "score" not in leg:
                        continue
                    for i, f, a in ((leg["homeidx"], leg["score"]["home"], leg["score"]["away"]),
                                    (leg["awayidx"], leg["score"]["away"], leg["score"]["home"])):
                        r = wdl.setdefault(g["teams"][i]["teamid"], [0, 0, 0])
                        r[0 if f > a else 1 if f == a else 2] += 1
    for phase in cup["phases"]:
        for g in phase["groups"]:
            order = group_table(g) if phase["system"] == "round-robin" else range(len(g["teams"]))
            for rank, i in enumerate(order):
                t = g["teams"][i]; w, d, l = wdl.get(t["teamid"], [0, 0, 0])
                t.update(win=w, draw=d, lose=l, point=3 * w + d, rank=rank + 1)


def cup_play_round(st, cup, mine=None):
    """Play the current round (my fixture = `mine` (home, away) if given, the rest simulated),
    then advance current / build the knock-out / settle my state."""
    cur = cup["current"]; phase = cup["phases"][cur["phase"]]; ko = phase["system"] == "knock-out"
    rng = random.Random()
    for g in phase["groups"]:
        for pair in g["rounds"][cur["round"]]["pairs"]:
            leg = pair["legs"][cur["leg"]]
            if "score" in leg or leg.get("homeidx") is None:
                continue
            h, a = g["teams"][leg["homeidx"]], g["teams"][leg["awayidx"]]
            played = mine is not None and (h["coach"] or a["coach"])
            if played:
                gh, ga = mine[:2]
            else:
                gh, ga = sim_score(rng, team_strength(st, h["teamid"]), team_strength(st, a["teamid"]))
            leg["score"] = {"home": gh, "away": ga}
            if ko and gh == ga and played and len(mine) > 3 and mine[2] != mine[3]:  # shootout played in game
                leg["shootout"] = {"home": mine[2], "away": mine[3]}
            elif ko and gh == ga:  # penalties
                ph = rng.randint(3, 5); pa = ph + rng.choice((-1, 1)) if ph < 5 else ph - 1
                leg["shootout"] = {"home": ph, "away": pa}
    me_state = cup["coaches"][0]
    if not ko:
        if cur["round"] + 1 < len(phase["groups"][0]["rounds"]):
            cur["round"] += 1
            return
        # groups done: A1-B2, B1-A2, C1-D2, D1-C2
        tables = [group_table(g) for g in phase["groups"]]
        qual = []
        for x, y in ((0, 1), (2, 3)):
            qual += [phase["groups"][x]["teams"][tables[x][0]], phase["groups"][y]["teams"][tables[y][1]],
                     phase["groups"][y]["teams"][tables[y][0]], phase["groups"][x]["teams"][tables[x][1]]]
        cup["phases"].append({"system": "knock-out", "name": "Babak gugur", "maxrounds": 3, "groups": [{"teams": qual, "rounds": [
            {"shuffle": True, "pairs": [{"legs": [{"homeidx": i, "awayidx": i + 1}]} for i in range(0, 8, 2)]},
            {"pairs": [{"legs": [{}]} for _ in range(2)]}, {"pairs": [{"legs": [{}]}]}]}]})
        cup.update(current={"phase": cur["phase"] + 1, "round": 0, "leg": 0})
        if not any(t["coach"] for t in qual):
            me_state["state"] = "eliminated"
        return
    g = phase["groups"][0]
    winners = []
    for pair in g["rounds"][cur["round"]]["pairs"]:
        leg = pair["legs"][0]; s = leg.get("shootout") or leg["score"]
        winners.append(leg["homeidx"] if s["home"] > s["away"] else leg["awayidx"])
    my_idx = next(i for i, t in enumerate(g["teams"]) if t["coach"]) if any(t["coach"] for t in g["teams"]) else None
    if my_idx is not None and me_state["state"] == "playing" and my_idx not in winners and \
            any(my_idx in (p["legs"][0].get("homeidx"), p["legs"][0].get("awayidx")) for p in g["rounds"][cur["round"]]["pairs"]):
        me_state["state"] = "eliminated"
    if cur["round"] + 1 < len(g["rounds"]):
        for k, pair in enumerate(g["rounds"][cur["round"] + 1]["pairs"]):
            pair["legs"][0] = {"homeidx": winners[2 * k], "awayidx": winners[2 * k + 1]}
        cur["round"] += 1
    else:  # final played
        cup["finished"] = True
        if me_state["state"] == "playing":
            me_state["state"] = "won" if my_idx in winners else "eliminated"  # CupMainScreen._cupState


def cup_resources(cup):
    uri = f"/cup/{cup['_id']}"
    return [{"resource": uri, "uri": uri, "body": cup}]


def ep_cup_new(query, body):
    """POST /cup/new {metaid, difficulty, teamid, lineup}."""
    req = json.loads(body or b"{}")
    meta = next((m for m in CUPS if m["metaid"] == int(req.get("metaid") or 0)), None)
    if meta is None:
        return _json({"result": False, "reason": "invalid metaid"})
    st = _state()
    cup = new_cup(st, meta, int(req.get("difficulty") or 0))
    st.setdefault("cups", {})[cup["_id"]] = cup
    _save(st)
    return _json({"result": True, "resources": cup_resources(cup)})


def cup_step(cupid, fn):
    st = _state(); cup = (st.get("cups") or {}).get(cupid)
    if cup is None:
        return _json({"result": False, "reason": "not exist cupid"})
    out = fn(st, cup) or {}
    _save(st)
    return _json(dict({"result": True, "resources": cup_resources(cup)}, **out))


def ep_cup_resume(cupid, query, body):
    return cup_step(cupid, lambda st, cup: None)


def ep_cup_next(cupid, query, body):
    """PUT /cup/<id>/next: play out the current round (my result from the match just played,
    if any) and advance (CupController.onMatchEndReceived -> ON_CUP_SCHEDULE_NEXT_ROUND)."""
    def step(st, cup):
        if cup.get("finished"):
            return
        cup_play_round(st, cup, cup.pop("_mine", None))
        cup_refresh_stats(cup)
    return cup_step(cupid, step)


def cup_reward_ep(cup):
    """EP for an ended cup: the meta's prize for the champion, a share of it by the round
    reached otherwise (group exit 10%, QF 20%, SF 35%, final 50%); 0 while still playing."""
    state = cup["coaches"][0]["state"]
    meta = next((m for m in CUPS if m["metaid"] == cup["metaid"]), CUPS[0])
    prize = meta["bestrewards"][-1][0]["count"]
    if state == "won":
        return prize
    if state != "eliminated":
        return 0
    ko = cup["phases"][1]["groups"][0] if len(cup["phases"]) > 1 else None
    mine = next((i for i, t in enumerate(ko["teams"]) if t["coach"]), None) if ko else None
    if mine is None:
        return prize // 10
    played = sum(1 for r in ko["rounds"] for p in r["pairs"]
                 if mine in (p["legs"][0].get("homeidx"), p["legs"][0].get("awayidx")) and "score" in p["legs"][0])
    return prize * (20, 35, 50)[max(0, min(played, 3) - 1)] // 100


def ep_cup_leave(cupid, query, body):
    """PUT /cup/<id>/leave: give up, or collect an ended cup's reward. CupReward*Scene.onItemExpand
    reads body.rewards[]: itemid 1 = EP (count), anything else is an item card."""
    st = _state(); cup = (st.get("cups") or {}).pop(cupid, None)
    ep = cup_reward_ep(cup) if cup else 0
    add_ep(st, ep)
    _save(st)
    return _json({"result": True, "rewards": [{"itemid": 1, "count": ep}] if ep else []})


def ep_cup_match(cupid, query, body):
    """POST /cup/<id>/match -> my fixture of the current round as a /match/<id> resource."""
    st = _state(); cup = (st.get("cups") or {}).get(cupid)
    g, leg = cup_my_pair(cup) if cup else (None, None)
    if leg is None or "score" in leg:
        return _json({"result": False, "reason": "already played match"})
    me = coach_me(st, _default_slot(st)); teamid = me["teamid"]
    home = g["teams"][leg["homeidx"]]["teamid"]; away = g["teams"][leg["awayidx"]]["teamid"]
    opp = away if home == teamid else home
    user = {"id": me["id"], "name": me["name"], "levelinfo": me["levelinfo"]}
    match = new_match("Cup_PvE", match_side(st["teams"][str(_default_slot(st))], teamid, user, _tactics(st)[1]),
                      match_side(roster_team(opp), opp))
    gs = match["gamesettings"]
    gs["home"] = home == teamid
    gs["kit"] = ["home", "away"] if gs["home"] else ["away", "home"]
    gs["difficulty"] = cup.get("difficulty", 0)  # AI level 0..4
    if cup["phases"][cup["current"]["phase"]]["system"] == "knock-out":
        # native maps drawMode 1/2/3 to end rules 9/6/7 (0 = a draw stands). 2 plays extra time
        # (FIRST_EXTRA_HALF seen in game); a draw after it is settled by cup_play_round
        gs["drawMode"] = 2
    st["match"] = match
    st["cup_pending"] = {"id": match["id"], "cupid": cupid, "home": home, "away": away}
    _save(st)
    return _json({"result": True, "resources": [{"uri": f"/match/{match['id']}", "body": match}]})


def ep_cup_record(query, body):
    """GET /cup/record: CupProxy.onCupRecordResourceChanged takes resources[] entries whose
    `resource` is /cup/record and body._id is my coach id."""
    st = _state(); coach = coach_me(st, _default_slot(st))
    return _json({"result": True, "resources": [{"resource": "/cup/record", "uri": "/cup/record",
                  "body": {"_id": coach["id"], "recordsbymetaid": []}}]})


# --------------------------------------------------------------------------- #
# Market (Bursa transfer): an NPC market over the cards fifaaddict lists, at their Indonesia-
# server prices (card_price). Offer rows are {spid, expandme: "player", grade, price, count};
# the client fills staticdata (names, position, ratings) from its own DB via `expandme`.
# --------------------------------------------------------------------------- #
LINES = {"GK": range(0, 1), "DF": range(1, 9), "MF": range(9, 20), "FW": range(20, 28)}  # Enums.PLAYERPOSITION
MAX_PLAYERS = 200  # coach.limits.players (squad size; user: "max skuad naikan", was 60)
# Tim inti (player state "first": Formasi lists only these) can hold the whole club ("Tim inti
# x/200" in Skuad). Skuad's Tim column shows MAIN/SUB for the 18 of the squad, a green RES button
# for the rest of Tim inti and "-" for Tim Cadangan; the button moves a card between the two.
FIRST_TEAM_MAX = MAX_PLAYERS


def first_team_count(team):
    return sum(1 for p in team["players"] if not p.get("team2"))


def balance_first_team(team):
    """Tim inti over FIRST_TEAM_MAX (clubs from before the cap): the least valuable cards outside
    the 18 of the squad move to Tim Cadangan."""
    extra = first_team_count(team) - FIRST_TEAM_MAX
    spare = [p for p in team["players"] if not p.get("team2") and not in_squad(team, p)]
    for p in sorted(spare, key=lambda p: card_price(p["spid"], grade_of(p)))[:max(0, extra)]:
        p["team2"] = True


def market_offer(spid, grade=1):
    return {"spid": spid, "expandme": "player", "grade": grade, "price": card_price(spid, grade), "count": 1}


def ep_transfer_top(position, query, body):
    """GET /transfer/top/50[/position/<GK|DF|MF|FW>]: the 50 priciest tradeable cards."""
    rng = LINES.get(str(position or "").upper())
    where = f"AND p.preferredposition1 BETWEEN {rng.start} AND {rng.stop - 1}" if rng else ""
    with closing(_db()) as c:
        both = c.execute(f"""SELECT p.spid, {POSOVR}, p.overallrating FROM players p
                             WHERE 1 {where}""").fetchall()  # every Market card, licensed or not
    _OVR.update((s, (o, d)) for s, o, d in both)
    rows = [(s, o) for s, o, _ in both]
    spids = [s for s, ovr in sorted((r for r in rows if on_market(r[0])), key=lambda r: (-r[1], r[0]))[:50]]
    return _json([market_offer(s) for s in spids])


def ep_transfer_search(spid, query, body):
    """GET /transfer/search/<spid>: that card's offers (grades 1..3); none if not tradeable."""
    return _json([market_offer(int(spid), g) for g in (1, 2, 3)] if on_market(spid) else [])


def add_player(team, spid, grade=1):
    """A new card instance in my club, in Tim Cadangan ("-" in Skuad, ready for Tukar Scout; user:
    "neymar baru di pack harusnya jangan masuk res"): packs, trades, the Market, Bag gifts and the
    admin page all add through here. Returns it."""
    with closing(_db()) as c:
        r = c.execute("SELECT playerid FROM players WHERE spid = ?", (int(spid),)).fetchone()
        name = gen_teams.jersey_name(c, r[0]) if r else ""
    used = {p.get("jersey") for p in team["players"]}
    p = {"_id": new_iid(), "spid": int(spid), "expandme": "player", "grade": int(grade),
         "jersey": next((n for n in range(12, 100) if n not in used), 99), "jerseyname": name, "team2": True}
    team["players"].append(p)
    return p


def remove_player(team, p):
    """Drop a card instance from my club and from the squad, captain and kickers."""
    team["players"].remove(p)
    sq, pid = team["squad"], iid(p)
    sq["positions"] = [s for s in sq["positions"] if str(s.get("id") or s["spid"]) != pid]
    sq["kickers"] = ["" if str(k) == pid else k for k in sq.get("kickers", [])]  # slots stay in place
    if str(sq.get("captain")) == pid:
        sq["captain"] = next((str(s.get("id") or s["spid"]) for s in sq["positions"] if s["pos"]), "")


def is_starter(team, p):
    return any(str(s.get("id") or s["spid"]) == iid(p) and s["pos"] < POS_SUB for s in team["squad"]["positions"])


def in_squad(team, p):
    """Starter or sub (the 18 on the team sheet); reserves are not."""
    return any(str(s.get("id") or s["spid"]) == iid(p) for s in team["squad"]["positions"])


def ep_transfer_purchase(spid, grade, price, query, body):
    """POST /transfer/purchase/<spid>/<grade>/<price>/purchase: pay the market price (not the
    path's) and add a new instance of the card to my players (reserves)."""
    spid, grade = int(spid), int(grade)
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]
    if not on_market(spid):
        return _json({"result": False, "reason": "NOT_EXIST_OFFER"})
    if len(team["players"]) >= MAX_PLAYERS:
        return _json({"result": False, "reason": "Exceed plyer limit"})
    cost = card_price(spid, grade)
    if coach_me(st, slot)["money"]["ep"] < cost:
        return _json({"result": False, "reason": "NOT_ENOUGH_EP"})
    add_ep(st, -cost)
    add_player(team, spid, grade)
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


# Selling: the NPC market buys at once. The offer shows as "sold" in Daftar jual saya until
# its EP is collected (price minus SALE_FEE). Asking more than the market price is refused,
# so buying back is never cheaper than selling.
SALE_FEE = 0.10
# transfer-fee discounts (TransferMarketProxy.modifyOffersFee: floor(factor * completefee.base)):
# PC warnet (IGR) 20%, VIP 30% -- fifaaddict's FO3 tax calculator; both always active here
NO_BOOST = {"igr": 0.2, "vip": 0.3, "event": 0, "item": 0, "discountlimit": 0}


def sale_net(o):
    fee = o["completefee"]["base"]
    return o["price"] - fee + int(NO_BOOST["igr"] * fee) + int(NO_BOOST["vip"] * fee)


def offer_list(st):
    """/transfer/my/offer/list (TransferMarketProxy.fetch*): offers[] {_id, status
    selling|sold|expired, issuedat, completefee.base (fee in EP), spid, grade, price}."""
    return {"offerexpireoffset": 86400000, "boost": NO_BOOST, "offers": st.get("offers", [])}


def offer_resources(st):
    return [{"uri": "/transfer/my/offer/list", "body": offer_list(st)}] + coach_me_resources(st, _default_slot(st))


def ep_transfer_price(spid, grade, query, body):
    """GET /transfer/price/<spid>/<grade>: the Jual tab's price band and default."""
    p = card_price(spid, int(grade))
    return _json({"lower": p * 8 // 10, "upper": p, "default": p, "lowest": p, "registrationFee": 0})


def ep_transfer_offer(query, body):
    """POST /transfer/offer {playerobjectid, price}: sell one of my players (not a starter)."""
    req = json.loads(body or b"{}")
    st = _state(); team = st["teams"][str(_default_slot(st))]
    pid = str(req.get("playerobjectid"))
    p = next((p for p in team["players"] if iid(p) == pid), None)
    price = int(req.get("price") or 0)
    if p is None or is_starter(team, p):
        return _json({"result": False, "reason": "TRANSFERMARKET_SELECT_SELLABLE_PLAYER"})
    if not 0 < price <= card_price(p["spid"], grade_of(p)):
        return _json({"result": False, "reason": "TRANSFERMARKET_LOWERLIMIT"})
    remove_player(team, p)
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    st.setdefault("offers", []).append({
        "_id": f"{int(time.time()):08x}{os.urandom(8).hex()}", "status": "sold", "issuedat": now, "soldat": now,
        "spid": p["spid"], "expandme": "player", "grade": grade_of(p), "price": price,
        "playerobjectid": pid, "completefee": {"base": int(price * SALE_FEE)}})
    _save(st)
    return _json({"result": True, "resources": offer_resources(st)})


def ep_offer_collect(offerid, coupon, query, body):
    """DELETE /transfer/my/offer/completed/<id|all>[/<coupon>]: collect sold offers' EP."""
    st = _state(); offers = st.get("offers", [])
    done = [o for o in offers if o["status"] == "sold" and offerid in ("all", o["_id"])]
    if not done:
        return _json({"result": False, "reason": "NOT_EXIST_OFFER"})
    ep = sum(sale_net(o) for o in done)
    add_ep(st, ep)
    st["offers"] = [o for o in offers if o not in done]
    _save(st)
    return _json({"result": True, "ep": ep, "resources": offer_resources(st)})


# --------------------------------------------------------------------------- #
# Tim > Manajemen pemain > Upgrade (enhancement v1, TeamManagementPlayerEnhancementOldTabPage
# + TeamManagementPlayerEnhancingPopupScreen): two cards of the same player, the lower-grade
# one (material) is consumed. Buy a second copy on the Market to have a pair.
# --------------------------------------------------------------------------- #
ENHANCE_RATE = (1.0, 1.0, 0.81, 0.64, 0.50, 0.26, 0.15, 0.07, 0.04, 0.02, 0)  # +g -> +(g+1) chance
ENHANCE_DROP_FROM = 5  # a failed upgrade from +5 or higher drops one grade


def enhance_pair(team, a, b):
    pa = next((p for p in team["players"] if iid(p) == str(a)), None)
    pb = next((p for p in team["players"] if iid(p) == str(b)), None)
    if pa is None or pb is None or pa is pb or pa["spid"] != pb["spid"]:
        return None, None
    if grade_of(pa) >= 10 and grade_of(pb) > 0:  # a +10 may take only a +0 (onListItemClick)
        return None, None
    return pa, pb


def enhance_grade(target, material):
    """Grade after a successful upgrade: a +0 material (a club's own card) adds none (issue #5)."""
    return grade_of(target) + (grade_of(material) > 0)


def enhance_rate(target, material):
    """Base chance by target grade times the bonus the Upgrade tab shows as "Rasio bonus
    keberhasilan" (TeamManagementPlayerEnhancementOldTabPage.updatePreviewText): material +1 or
    lower = Kosong, at least 2/3 of the target grade = High, at least 1/3 = Normal, else Low.
    The multipliers are ours (user: "Ya, samakan"); the original ones were server data.
    A +0 material keeps the grade, so it always succeeds."""
    tg, mg = grade_of(target), grade_of(material)
    if mg == 0:
        return 1.0
    bonus = 1.0 if mg <= 1 else 1.5 if mg >= tg * 2 / 3 else 1.25 if mg >= tg / 3 else 1.1
    return min(1.0, ENHANCE_RATE[tg] * bonus)


def enhance_cost(target):
    return max(1000, sig3(card_price(target["spid"], grade_of(target)) // 50))  # 2% of its value


def merge_into(team, keep, gone):
    """The consumed card's squad slot (starter > sub) passes to the kept card of the same
    player, so an upgrade never leaves a hole in the XI; then the consumed card goes."""
    sq, k, g = team["squad"], iid(keep), iid(gone)
    slot = {str(s.get("id") or s["spid"]): s for s in sq["positions"]}
    if g in slot and (k not in slot or slot[g]["pos"] < POS_SUB <= slot[k]["pos"]):
        if k in slot:
            sq["positions"].remove(slot[k])
        slot[g]["id"] = k
        keep.pop("team2", None)  # the 18 of the squad stay in Tim inti (ep_player_move)
        if str(sq.get("captain")) == g:
            sq["captain"] = k
        sq["kickers"] = [k if str(x) == g else x for x in sq.get("kickers", [])]
    remove_player(team, gone)


def ep_enhance_preview(a, b, query, body):
    """GET /player/<target>/enhance/<material>/preview -> {grade, levelinfo, price, enhancepay}."""
    st = _state(); team = st["teams"][str(_default_slot(st))]
    pa, pb = enhance_pair(team, a, b)
    if pa is None:
        return _json({"result": False, "reason": "INVALID_PARAM"})
    g = enhance_grade(pa, pb)
    return _json({"result": True, "grade": g, "levelinfo": pa.get("levelinfo", {"level": 1, "exp": 0}),
                  "price": card_price(pa["spid"], g), "enhancepay": enhance_cost(pa),
                  "probability": round(enhance_rate(pa, pb) * 100)})


def ep_enhance(a, b, boost, guard, query, body):
    """PUT /player/<target>/enhance/<material>[/<boostitem>/<guarditem>] -> {success, grade,
    rgrade, rprice, attribPlus} (TeamManagementPlayerEnhancingPopupScreen.onEnhanceComplete)."""
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]
    pa, pb = enhance_pair(team, a, b)
    if pa is None:
        return _json({"result": False, "reason": "INVALID_PARAM"})
    cost = enhance_cost(pa)
    if coach_me(st, slot)["money"]["ep"] < cost:
        return _json({"result": False, "reason": "Invalid target ep price"})
    add_ep(st, -cost)
    before = grade_of(pa)
    success = random.random() < enhance_rate(pa, pb)
    after = enhance_grade(pa, pb) if success else before - 1 if before >= ENHANCE_DROP_FROM else before
    pa["grade"] = after
    merge_into(team, pa, pb)
    _save(st)
    return _json({"result": True, "success": success, "grade": after, "rgrade": after,
                  "rprice": card_price(pa["spid"], after), "attribPlus": GRADE_BOOST[after] - GRADE_BOOST[before],
                  "resources": coach_me_resources(st, slot)})


# --------------------------------------------------------------------------- #
# Upgrade 2.5 (features.teammanagement.playermanagement.enhancement.v2_5 ->
# TeamManagementPlayerEnhancement2_5TabPage: EnhanceControlPanel, EnhancementInfoPanel, popup
# version "v2_5"). Same pairs, grades and drop as v1, plus (user: "di upgrade belum ada tambahan
# item dan point upgrade"):
#   upgrade points (money.es): a failed upgrade grants enhance_es(target) points; "Gunakan poin"
#     spends that many for +ES_BOOST chance (PE2STATICVALUES bonus.use = ES_BOOST in 1/100 %);
#   boost items (coach items of type ENHANCEMENT_BOOST, sent by itemid): +their chance, one used;
#   a failure that dropped a grade shows "Coba pengembalian lagi": PUT /player/enhance2.5/restore
#     gives the grade back for usepoint.price points.
# The original numbers were server data; these are ours.
# --------------------------------------------------------------------------- #
ES_BOOST = 0.10
ES_RESTORE = 3  # restoring a dropped grade costs the points of this many failures
# GET /static/db/PE2STATICVALUES. The popup's constructor reads all three keys (a missing one
# threw #1010 there, so the popup came up half-built with dead buttons): bonus.use = the point
# boost in 1/100 %; simplify_step.use = cards cheaper than this restore without the button
# (isSimplify; 0 = never); effect_price {0..4} = EP thresholds, highest first, for the card
# glow effect6..effect2 (setPlayerCardBackEffect; below the last one = effect1).
PE2STATICVALUES = {"bonus": {"use": round(ES_BOOST * 10000)}, "simplify_step": {"use": 0},
                   "effect_price": {str(i): v for i, v in enumerate((10 ** 10, 10 ** 9, 10 ** 8, 10 ** 7, 10 ** 6))}}
# A never-ending Upgrade event (user: "aktifkan terus event upgrade"), GET /events for
# InGameEventProxy. InGameEventController keeps an event whose condition.type is "enhance" and
# that is active with no reason; condition.timeset dates are YYYYMMDD, times HHMM;
# targetuser_igr 255 = every user; enhance.season [] = every season. reward is a list of lists
# of {boosts} (getEnhanceGradeRange types each entry as Array: a flat list raised #1034 and
# stopped the preview); boost key BOOST_PLUS_ENHANCE without a grade suffix = targets +1..+9.
# The panel then sends its eventid with the upgrade.
EVENT_BOOST = 0.10
ENHANCE_EVENT = {
    "eventid": 1001, "active": True, "reason": [],
    "condition": {"type": "enhance", "enhance": {"season": []},
                  "timeset": {"startdate": "20140101", "enddate": "20351231", "starttime": "0000", "endtime": "2359"},
                  "targetuser": {"targetuser_igr": 255, "targetuser_vip": 255}},
    "reward": [[{"boosts": {"BOOST_PLUS_ENHANCE": round(EVENT_BOOST * 100)}}]],
    "messages": {"main": {"name": "Event Upgrade", "description": "Peluang sukses upgrade +10% untuk target +1 sampai +9."}},
}


def enhance_es(target):
    """Points a failed upgrade of this card grants, and what "Gunakan poin" costs on it."""
    return 10 * (grade_of(target) + 1)


def add_es(st, n):
    coach = my_coach(st)
    coach["es"] = coach.get("es", 0) + int(n)


def boost_stack(st, itemid):
    """The coach's stack of that boost item, or None (-1 = none chosen, or not owned)."""
    return next((i for i in my_coach(st).get("items", []) if str(i["itemid"]) == str(itemid) and i["remains"] > 0
                 and i["itemid"] in ITEMS and ITEMS[i["itemid"]][2] == "ENHANCEMENT_BOOST"), None)


def enhance25_rate(pa, pb, use_point, item, eventid):
    rate = enhance_rate(pa, pb)
    if grade_of(pb) > 0:  # a +0 material always succeeds: nothing to boost
        event = eventid == str(ENHANCE_EVENT["eventid"]) and 1 <= grade_of(pa) <= 9
        rate += ES_BOOST * use_point + (ITEMS[item["itemid"]][3]["boost"] if item else 0) + EVENT_BOOST * event
    return min(1.0, rate)


def ep_enhance25_preview(a, b, use_point, itemid, event, query, body):
    """GET /player/<target>/enhance2.5/<material>/preview/<usePoint 0|1>/<boost itemid|-1>/<eventid|-1>
    -> {grade, levelinfo, price, probability, enhancepay, needes} (EnhanceControlPanel.requestPreview)."""
    st = _state(); team = st["teams"][str(_default_slot(st))]
    pa, pb = enhance_pair(team, a, b)
    if pa is None:
        return _json({"result": False, "reason": "INVALID_PARAM"})
    g = enhance_grade(pa, pb)
    rate = enhance25_rate(pa, pb, use_point == "1", boost_stack(st, itemid), event)
    return _json({"result": True, "grade": g, "levelinfo": player_levelinfo(pa), "price": card_price(pa["spid"], g),
                  "probability": round(rate * 100), "enhancepay": enhance_cost(pa), "needes": enhance_es(pa)})


def enhance25_result(st, slot, p, success, before, grant, price):
    """Popup v2_5 reply: on a failure it shows the card broken, then restores it to rgrade
    (grade after a restore); grantes = points earned, usepoint = what a restore costs."""
    g = grade_of(p)
    return _json({"result": True, "success": success, "grade": g, "rgrade": g, "rprice": card_price(p["spid"], g),
                  "attribPlus": GRADE_BOOST[g] - GRADE_BOOST[before], "grantes": grant,
                  "usepoint": {"currency": "ES", "price": price}, "getitems": [], "resources": coach_me_resources(st, slot)})


def ep_enhance25(a, b, use_point, itemid, event, query, body):
    """PUT /player/<target>/enhance2.5/<material>/<usePoint 0|1>/<boost itemid|-1>/<eventid|-1>."""
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]
    pa, pb = enhance_pair(team, a, b)
    if pa is None:
        return _json({"result": False, "reason": "INVALID_PARAM"})
    boostable = grade_of(pb) > 0
    use_point = use_point == "1" and boostable
    item = boost_stack(st, itemid) if boostable else None
    if boostable and itemid != "-1" and item is None:
        return _json({"result": False, "reason": "expired item"})  # popup: ENHANCEMENT_25_ERROR_ITEM01
    cost, need = enhance_cost(pa), enhance_es(pa)
    if coach_me(st, slot)["money"]["ep"] < cost:
        return _json({"result": False, "reason": "Invalid target ep price"})
    if use_point and my_coach(st).get("es", 0) < need:
        return _json({"result": False, "reason": "NOT_ENOUGH_ES"})
    rate = enhance25_rate(pa, pb, use_point, item, event)
    add_ep(st, -cost)
    add_es(st, -need if use_point else 0)
    if item:
        item["remains"] -= 1
        if not item["remains"]:
            my_coach(st)["items"].remove(item)
    before = grade_of(pa)
    success = random.random() < rate
    pa["grade"] = enhance_grade(pa, pb) if success else before - 1 if before >= ENHANCE_DROP_FROM else before
    merge_into(team, pa, pb)
    grant = 0 if success else need
    add_es(st, grant)
    st.pop("enhance_restore", None)
    if grade_of(pa) < before:
        st["enhance_restore"] = {"id": iid(pa), "grade": before, "price": ES_RESTORE * need}
    _save(st)
    return enhance25_result(st, slot, pa, success, before, grant, ES_RESTORE * need)


def ep_enhance25_restore(query, body):
    """PUT /player/enhance2.5/restore ("Coba pengembalian lagi" after a failure that dropped a
    grade): pay the points, the card gets that grade back. The popup reads it as another failed
    result whose grade is the restored one."""
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]
    r = st.get("enhance_restore")
    p = next((x for x in team["players"] if r and iid(x) == r["id"]), None)
    if p is None:
        return _json({"result": False, "reason": "INVALID_PARAM"})
    if my_coach(st).get("es", 0) < r["price"]:
        return _json({"result": False, "reason": "NOT_ENOUGH_ES"})
    add_es(st, -r["price"])
    before, p["grade"] = grade_of(p), r["grade"]
    del st["enhance_restore"]
    _save(st)
    return enhance25_result(st, slot, p, False, before, 0, r["price"])


# --------------------------------------------------------------------------- #
# Tim > Manajemen pemain > Tukar (player trade v1, TeamManagementPlayerRecycleTabPage +
# TeamManagementPlayerRecyclePopupScreen). Give 2..10 reserves; clubs offer Market cards
# rated at least avg(card OVR) + playertrade_cardovrbonus[n] (the tab's "expected OVR"):
# playertrade_normal[n] offers plus one each for PC warnet and VIP (the popup has 5 slots).
# An offer is a card, a card plus EP, or EP only (no spid). Tables: static_db_STATICVALUES.json.
# --------------------------------------------------------------------------- #
_TRADE_POOL = {}


def static_values():
    with open(os.path.join(RESPONSES, "static_db_STATICVALUES.json"), encoding="utf-8") as f:
        return json.load(f)


def trade_grades(gsum):
    """PLAYERTRADE.playergrade[sum of the given cards' grades] -> {grade: weight}: +1 always,
    one more possible grade per 8 grade points traded (the tab shows its first..last key)."""
    return {str(g): 0.5 ** (g - 1) for g in range(1, min(10, 1 + int(gsum) // 8) + 1)}


def trade_pool():
    """{client rating: [(spid, teamid)]} of every Market card, any season (cached). It used to
    take only cards licensed for the ID region, which left out most old and special seasons
    (user: "trading munculkan semua playernya")."""
    if not _TRADE_POOL:
        with closing(_db()) as c:
            for s, t, o in c.execute(f"SELECT p.spid, p.teamid, {POSOVR} FROM players p"):
                if on_market(s):
                    _TRADE_POOL.setdefault(o, []).append((s, t))
    return _TRADE_POOL


def trade_props(give, rng):
    sv = static_values()
    lim, n = sv["playertrade_limit"], len(give)
    avg = sum(card_ovr(p["spid"]) for p in give) / n
    lo = int(min(max(avg + sv["playertrade_cardovrbonus"][str(n)], lim["CardMinValue"]), lim["CardMaxValue"]))
    total = sum(card_price(p["spid"], grade_of(p)) for p in give)
    weights = trade_grades(sum(grade_of(p) for p in give))
    pool = trade_pool()
    props = []
    for i, boost in enumerate([None] * int(sv["playertrade_normal"][str(n)]) + ["igr", "vip"]):
        ovr = lo
        while ovr < min(lo + 8, lim["CardMaxValue"]) and rng.random() < 0.55:  # sometimes better
            ovr += 1
        s, t = rng.choice(pool[min(pool, key=lambda r: (abs(r - ovr), -r))])
        if i == 1 and boost is None:  # a club buys the lot for EP
            props.append({"teamid": t, "ep": sig3(total * rng.uniform(0.9, 1.15))})
            continue
        g = int(rng.choices(list(weights), list(weights.values()))[0])
        offer = {"spid": s, "grade": g, "teamid": t, "price": card_price(s, g)}
        if i == 2 and boost is None:  # card plus a top-up
            offer["ep"] = sig3(total * rng.uniform(0.05, 0.2))
        if boost:
            offer["boost"] = boost  # always a PC warnet + VIP coach here
        props.append(offer)
    return props


def trade_proposal(body, make_props):
    """{players: [iid...]} -> {result, props}: Tukar v1 and v2 share the checks."""
    req = json.loads(body or b"{}")
    st = _state(); team = st["teams"][str(_default_slot(st))]
    ids = [str(i) for i in req.get("players") or []]
    give = [p for p in team["players"] if iid(p) in ids]
    if not 2 <= len(give) <= 10 or len(give) != len(set(ids)) or any(in_squad(team, p) for p in give):
        return _json({"result": False, "reason": "invalid playerid"})  # the tab lists reserves only
    props = make_props(give, random.Random())
    st["trade"] = {"players": ids, "props": props}
    _save(st)
    return _json({"result": True, "props": props})


def ep_trade_proposal(query, body):
    """POST /players/trade/proposal {players: [iid...]} -> {result, props}."""
    return trade_proposal(body, trade_props)


def ep_trade_contract(query, body):
    """POST /players/trade/contract {select: offer index}: the given players leave, the
    offer's card and/or EP arrive. With the trade3 feature on, the popup (shared with the
    Scout tab) posts /trade3/contract {slotnum, selectnum} instead, also for this tab."""
    req = json.loads(body or b"{}")
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]
    tr = st.get("trade") or {}
    props, ids = tr.get("props") or [], tr.get("players") or []
    sel = int(req.get("select", req.get("selectnum", -1)))
    give = [p for p in team["players"] if iid(p) in ids]
    if not 0 <= sel < len(props) or len(give) != len(ids):
        return _json({"result": False, "reason": "invalid playerid"})
    for p in give:
        remove_player(team, p)
    offer = props[sel]
    if "spid" in offer:
        add_player(team, offer["spid"], offer["grade"])
    add_ep(st, offer.get("ep", 0))
    st.pop("trade")
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


# --------------------------------------------------------------------------- #
# Tim > Manajemen pemain > Tukar #2 (trade3 "Scout": TeamManagementPlayerTrade3TabPage +
# ScouterController). Pick a scout, give 2..10 reserves: offers are Market cards worth about
# their total value (fifaaddict prices) times the scout's range. Scouts (coach/me `scouters`)
# differ in range and cooldown; meeting a scout's quest shifts the range up. Same popup and
# /trade3/contract as Tukar v1 (the shared popup runs in trade3 mode while the feature is on).
# --------------------------------------------------------------------------- #
NO_LIMIT = 9_000_000_000_000_000  # "unlimited": below 2^53, so exact as an AS3 Number
TRADE3_STATIC = {  # GET /trade3/staticvalues -> ScouterController.staticvalues
    # total EP given / reward cap; user: "buat tidak terbatas" (was 30 / 10 billion EP: the tab
    # warned "Hanya dapat memperoleh pemain maximum 10,000,000,000 EP")
    "playertrade3_limit": {"max_trade": NO_LIMIT, "max": NO_LIMIT},
    "vvip_playertrade3_limit": {"max_trade": NO_LIMIT, "max": NO_LIMIT},
    "playertrade3_normal": {str(n): 1 + (n >= 4) + (n >= 7) for n in range(2, 11)},  # offers by #players
    "playertrade3_effect_price": [10_000_000, 3_000_000, 1_000_000],  # popup premium effect tiers
}
LEGEND_SEASONS = (93, 30, 27, 71, 51, 61, 89, 48, 31, 33)  # WL UL EL ML TL VL CL MUL CEL
SCOUTS = (  # (key = scoutid, string id, cooldown s, offer value x total, quest); always PC + VIP here
    # no cooldowns (user: "buat scout tidak ada reset"; were 1 day / 1 hour / 1 hour)
    # At most 5: the list shows 5 rows and, once it scrolls, updateQuestAchievePossibility lights
    # getRendererAt(selected index) without the scroll offset (another scout's or none). Scout
    # Amatir ("default_A01", no quest, 0.8-1.1) left for the two below; Profesional covers it.
    ("default_B01", "STR_SCOUTER_KR_DEFAULT_B01", 0, (0.9, 1.3), {"require_value": 100000}),
    ("igr", "STR_SCOUTER_KR_IGR_A01", 0, (0.9, 1.4), {"require_grade": 2, "require_grade_count": 2}),
    ("vip", "STR_SCOUTER_KR_VIP_A01", 0, (1.0, 1.5), {"require_season": "88", "require_season_count": 2}),
    # the client's other two (user: "Ya, tambahkan"); ScouterSelectedItemRenderer picks the
    # portrait from the key (scouter_event.png / scouter_vvip.png are not in the client cache:
    # it shows its default), an id with "vvip" uses vvip_playertrade3_limit
    ("event", "STR_SCOUTER_KR_EVENT_A01", 0, (1.0, 1.5),
     {"require_season": ",".join(map(str, LEGEND_SEASONS)), "require_season_count": 2}),
    ("vvip", "STR_SCOUTER_KR_VVIP_A01", 0, (1.1, 1.6), {"require_value": 1_000_000_000}),
)
QUEST_BONUS = 0.2  # quest met: the offer value range moves up by this x total
_T3_POOL = []


def w3c(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def coach_scouters(st, slot):
    """coach/me `scouters` (CoachProxy.tradeScouters): a scout on cooldown is locked and carries
    `cooltime` (W3C) for the countdown (ScouterController re-asks /trade3/info when it ends)."""
    used, now = next(c for c in st["coaches"] if c["slot"] == slot).get("scout_used", {}), time.time()
    out = []
    for key, sid, cool, _, quest in SCOUTS:
        until = used.get(key, 0) + cool
        out.append({"key": key, "scoutid": key, "scoutername": sid + "_NAME", "scouterdesc": sid + "_DESC",
                    "lock": until > now, **({"cooltime": w3c(until)} if until > now else {}),
                    **({"quest": quest} if quest else {})})
    return out


def quest_met(quest, give):
    """The tab's quest checks: total value, cards of grade >= G, cards of the listed seasons."""
    if not quest:
        return False
    if sum(card_price(p["spid"], grade_of(p)) for p in give) < quest.get("require_value", 0):
        return False
    if "require_grade" in quest and sum(grade_of(p) >= quest["require_grade"] for p in give) < quest["require_grade_count"]:
        return False
    seasons = {int(s) for s in str(quest.get("require_season", "")).split(",") if s}
    return not seasons or sum(int(p["spid"]) // 1000000 in seasons for p in give) >= quest["require_season_count"]


def trade3_pool():
    """[(price, spid, teamid, grade)] of Market cards at every grade +1..+10, cheapest first
    (cached). Grade +1 only capped an offer at the dearest +1 card (~20 billion EP), so a trade
    of ~71 billion got far less back (user: "pertukaran tidak sebanding dengan nilai yang diawal")."""
    if not _T3_POOL:
        rows = [r for o in trade_pool().values() for r in o]
        card_ovrs([s for s, _ in rows])  # one bulk query instead of one per unpriced card
        _T3_POOL.extend(sorted((card_price(s, g), s, t, g) for s, t in rows for g in range(1, 11)))
    return _T3_POOL


def trade3_props(give, scout, rng):
    """playertrade3_normal[n] cards worth total x the scout's range (capped at the reward max;
    the last of them adds an EP top-up) + PC warnet and VIP extras."""
    lo, hi = scout[3]
    if quest_met(scout[4], give):
        lo, hi = lo + QUEST_BONUS, hi + QUEST_BONUS
    total = sum(card_price(p["spid"], grade_of(p)) for p in give)
    pool, normal = trade3_pool(), TRADE3_STATIC["playertrade3_normal"][str(len(give))]
    props = []
    for i, boost in enumerate([None] * normal + ["igr", "vip"]):
        target = min(TRADE3_STATIC["playertrade3_limit"]["max"], total * rng.uniform(lo, hi))
        k = bisect.bisect_left(pool, (target,))
        price, s, t, gr = rng.choice(pool[max(0, k - 10):k + 10])  # one of the 20 cards nearest in value
        offer = {"spid": s, "grade": gr, "teamid": t, "price": price}
        if i == normal - 1 and normal > 1:
            offer["ep"] = sig3(max(1000, total * rng.uniform(0.05, 0.15)))
        if boost:
            offer["boost"] = boost
        props.append(offer)
    return props


def ep_trade3_proposal(query, body):
    """POST /trade3/proposal {id: scout key, slotnum, playerids: [{id, spid, grade, price}]}
    -> {result, props} (tab.onResponseRecycle opens the popup; it posts /trade3/contract)."""
    req = json.loads(body or b"{}")
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]; coach = my_coach(st)
    scout = next((s for s in SCOUTS if s[0] == req.get("id")), None)
    sent = {str(p.get("id")): p for p in req.get("playerids") or []}
    give = [p for p in team["players"] if iid(p) in sent]
    if (scout is None or not 2 <= len(give) <= 10 or len(give) != len(sent)
            or any(in_squad(team, p) or not p.get("team2") for p in give)):  # Tim Cadangan only
        return _json({"result": False, "reason": "invalid playerid"})
    if any(int(sent[iid(p)].get("price") or 0) != card_price(p["spid"], grade_of(p)) for p in give):
        return _json({"result": False, "reason": "TRADE3_NOTICE_PLAYERPRICE03"})  # client shows a recheck notice
    used = coach.setdefault("scout_used", {})
    if used.get(scout[0], 0) + scout[2] > time.time():
        return _json({"result": False, "reason": "TRADE2_ERROR_TOO_MANY_TRY"})  # still cooling down
    if sum(card_price(p["spid"], grade_of(p)) for p in give) >= TRADE3_STATIC["playertrade3_limit"]["max_trade"]:
        return _json({"result": False, "reason": "invalid playerid"})  # the tab blocks this first
    props = trade3_props(give, scout, random.Random())
    if scout[2]:
        used[scout[0]] = time.time()  # a negotiation uses the scout, picked or not
    st["trade"] = {"players": [iid(p) for p in give], "props": props}
    _save(st)
    return _json({"result": True, "props": props, "resources": coach_me_resources(st, slot)})


# --------------------------------------------------------------------------- #
# Tim > Manajemen pemain > Tukar v2 (features.teammanagement.playermanagement.trade2; same
# TeamManagementPlayerRecycleTabPage and popup; user: "Ya, buat trade2"). The tab rates the
# chosen reserves by TP = sum(card price, x bonusplayergroup.bonus for a special card of at
# least that grade) x playertrade2_bonus[n] x IGR x VIP, then shows from GET /static/db/TRADE
# the level (tp: minimum TP -> possible offer grades, highest level = 15) and the number of
# offers, and from GET /players/trade2/info what another manager got "yesterday" at that TP
# (TRADE2_ESTIMATE "{0} merekrut {1} kemarin."). Special cards (/static/cache/
# TRADE_SPECIALPLAYERS, {spid: 1}) are the legend seasons' cards. Offers are cards worth about
# the TP, graded up to the level's maximum. No daily limit (usage maxcount 0) and no value cap.
# The original numbers were server data; these are ours.
# --------------------------------------------------------------------------- #
TRADE2_LEVELS = (0, 10 ** 6, 3 * 10 ** 6, 10 ** 7, 3 * 10 ** 7, 10 ** 8, 3 * 10 ** 8, 10 ** 9, 2 * 10 ** 9,
                 4 * 10 ** 9, 8 * 10 ** 9, 15 * 10 ** 9, 30 * 10 ** 9, 60 * 10 ** 9, 120 * 10 ** 9)  # levels 1..15
TRADE2_TABLE = {
    "bonusplayergroup": {"bonus": 1.5, "grade": 1},
    "playertrade2_bonus": {**{str(n): round(1 + 0.02 * (n - 2), 2) for n in range(2, 11)}, "IGR": 1.05, "VIP": 1.05},
    "legendgroup": list(LEGEND_SEASONS),
    "playertrade2_normal": {str(n): 1 + (n >= 4) + (n >= 7) for n in range(2, 11)},  # + PC warnet and VIP offers
    "tp": {str(tp): {"value": list(range(1, 2 + round(9 * i / 14)))} for i, tp in enumerate(TRADE2_LEVELS)},
    "trade2_limit": {"max": NO_LIMIT, "max_trade": NO_LIMIT},
    "trade_effect_price": [10 ** 10, 10 ** 9, 10 ** 8],  # popup premium effect tiers
}
TRADE2_MANAGERS = ("Budi", "Andi", "Rizky", "Dimas", "Fajar", "Yoga", "Agus", "Hendra", "Bayu", "Eko")


@functools.lru_cache(maxsize=None)
def trade2_special():
    return {str(s): 1 for rows in trade_pool().values() for s, _ in rows if s // 1000000 in LEGEND_SEASONS}


def trade2_tp(give):
    w, b = TRADE2_TABLE["bonusplayergroup"], TRADE2_TABLE["playertrade2_bonus"]
    tp = sum(card_price(p["spid"], grade_of(p)) * (w["bonus"] if str(p["spid"]) in trade2_special()
                                                    and grade_of(p) >= w["grade"] else 1) for p in give)
    return tp * b.get(str(len(give)), 1) * b["IGR"] * b["VIP"]  # always a PC warnet + VIP coach here


def trade2_max_grade(tp):
    level = TRADE2_LEVELS[max(0, bisect.bisect_right(TRADE2_LEVELS, tp) - 1)]
    return TRADE2_TABLE["tp"][str(level)]["value"][-1]


@functools.lru_cache(maxsize=None)
def trade2_pool(max_grade):
    return [r for r in trade3_pool() if r[3] <= max_grade]


def trade2_pick(target, max_grade, rng):
    """(price, spid, teamid, grade): a card of at most that grade worth within 25% of the
    target, else the nearest one (low values come in sparse steps, so "the 20 nearest in the
    list" could be worth twice the target)."""
    pool = trade2_pool(max_grade)
    lo, hi = bisect.bisect_left(pool, (target / 1.25,)), bisect.bisect_right(pool, (target * 1.25, math.inf))
    k = bisect.bisect_left(pool, (target,))
    return rng.choice(pool[lo:hi] or pool[max(0, k - 1):k + 1])


def trade2_props(give, rng):
    tp = trade2_tp(give)
    props = []
    for boost in [None] * TRADE2_TABLE["playertrade2_normal"][str(len(give))] + ["igr", "vip"]:
        price, s, t, g = trade2_pick(tp * rng.uniform(0.85, 1.15), trade2_max_grade(tp), rng)
        props.append({"spid": s, "grade": g, "teamid": t, "price": price, **({"boost": boost} if boost else {})})
    return props


def ep_trade2_info(query, body):
    """GET /players/trade2/info {minimum TP: a card a manager got at that level "yesterday"}
    (the same for the whole day; expandme lets the client fill its staticdata)."""
    rng = random.Random(time.strftime("%Y%m%d"))
    out = {}
    for tp in TRADE2_LEVELS[1:]:
        price, s, _, g = trade2_pick(tp * 1.1, trade2_max_grade(tp), rng)
        out[str(tp)] = {"spid": s, "grade": g, "expandme": "player", "price": price, "coach": rng.choice(TRADE2_MANAGERS)}
    return _json(out)


def ep_player_move(pid, where, query, body):
    """POST /player/<_id>/move/firstteam|secondteam (Tim > Manajemen pemain > Skuad): Tim inti <->
    Tim Cadangan. Players in the 18 of the squad stay in Tim inti."""
    st = _state(); slot = _default_slot(st); team = st["teams"][str(slot)]
    p = next((x for x in team["players"] if iid(x) == pid), None)
    if p is None or (where == "secondteam" and in_squad(team, p)):
        return _json({"result": False, "reason": "TRANSFERMARKET_SELL_ERROR_FIRSTTEAM"})
    if where == "firstteam" and p.get("team2") and first_team_count(team) >= FIRST_TEAM_MAX:
        return _json({"result": False, "reason": "FIRSTTEAM_REGISTRATION_FAIL_POPUP_TITLE"})  # Tim inti full
    if where == "secondteam":
        p["team2"] = True
    else:
        p.pop("team2", None)
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


def ep_trade3_info(query, body):
    """POST /trade3/info {}: the client only reads the pushed resources (scouters)."""
    st = _state()
    return _json({"result": True, "resources": coach_me_resources(st, _default_slot(st))})


# --------------------------------------------------------------------------- #
# Locker room (Tim > Locker room, issue #13) dresses a Tim inti player and changes shirt numbers.
# ItemController fills its panels from GET /static/db/LOCKERROOMITEM {lockerroomid: item}: Atas
# takes type TOP, Bawah PANTS, Boots SHOES, each only with visible true; LockerRoomController
# localizes itemname and splits color at ","; each stepper is sorted by order. With no table every
# stepper was empty and the boots panel threw (ItemPanelShoes.onStepperBrandChanged). Steppers:
#   TOP: TATTOO (tattocode), UNIFORMKIND (jerseystylecode; option FIT sets jerseyfit),
#        UNIFORMARM (jerseysleevlengthcode; option WINTERGEAR), WRIST, GLOVE
#   PANTS: SOCKS (socklengthcode), KNEE
#   SHOES: shoecode; option = brand, the brand stepper's LOCKERROOM_SHOES_BRAND_<option>
# WRIST, KNEE and GLOVE option PLAYERGLOVE are accessory meshes (0 = none): id [asset],
# [asset + 1] or both for left, right or both, colour = the LOCKERROOM_COLOR_<c> picked from
# `color`, minus 1. GLOVE option GKGLOVE (keepers only): mesh [asset, asset + 1], texture color[0].
# Only the client's own meshes are used (its default look: wrist 67, glove 6, knee 1, keeper
# glove 18 with the LOCKERROOM_GLOVEGK_<gkglovetypecode> textures); the ids of the other wrist,
# glove and knee kinds are not in the client.
# A look is saved as the card's lr {lockerroomid: {id, pos?, clr?}} (PUT /lockerroom/<_id>/itemset
# on player or panel change and on exit), which getPlayerAssetsFromLockerRoomItems turns into the
# 3D player in matches, only while the coach holds a running ticket: the first item with itemid
# 801 (LockerRoomController._lockerRoomItemID), createat set and expireat (ms) in the future. The
# shirt number needs the ticket too (LOCKERROOM_TICKET_BACKNUMBER_OVER).
# --------------------------------------------------------------------------- #
LR_TICKET = 801  # the client's own icon externalAssets/shop/801.png (a shirt and boots)
LR_TICKET_ITEM = {"_id": "lockerroomticket", "id": "lockerroomticket", "itemid": LR_TICKET, "remains": 1, "count": 1,
                  "expireable": True, "expired": False, "createat": 1483228800000, "expireat": VIP_UNTIL,
                  "staticdata": {"itemid": LR_TICKET, "productid": LR_TICKET, "name": "Tiket locker room",
                                 "category": "LOCKERROOM", "type": "LOCKERROOM", "unit": "COUNT",
                                 "itemicon": LR_TICKET}}
LR_COLORS = ",".join(map(str, range(1, 11)))  # LOCKERROOM_COLOR_1..10
LR_GK_GLOVES = (*range(1, 12), *range(91, 119))  # LOCKERROOM_GLOVEGK_<gkglovetypecode>
LR_SHOES = {  # LOCKERROOM_SHOES_<shoecode> by brand (LOCKERROOM_SHOES_BRAND_<brand>; the rest ETC)
    "ADIDAS": ('12 21-36 71-72 74-78 80-81 83-84 87 89 91-93 126-150 198-205 207-211 14085-14086 '
               '14088 14090 14126-14129 14131-14158 14216 14500-14503 15021-15023 15026 15029 '
               '15031-15032 15034-15035 15129-15160 15205-15213 15215-15227 16131 16147-16148 '
               '17130-17142 17144-17158 18019-18025 18027-18034 18038-18044 18099 18108-18109 '
               '18115 18123 18143 18209-18227'),
    "NIKE": ('38-45 117 161 224 226 228-232 14101 14168-14181 15045-15047 15049-15062 15168-15181 '
             '15230-15237 17173-17174 17176 17178-17180 17183 17185 18045-18048 18050-18058 18063 '
             '18080 18181 18235-18243 18253 18343'),
    "PUMA": ('47-51 109 170-178 14107 14185-14187 15063 15065 15184-15187 15238-15244 17189-17195 '
             '18065 18067-18069 18232-18234'),
    "MIZUNO": ('60-63 95-96 154-160 220 14162 14164 14167 15039-15042 15162 15164 15167 '
               '15203-15204 15255 17167-17170 18093-18094 18096-18097 18244-18245'),
    "UMBRO": ('52-57 70 182-183 185-186 188 212-217 14188-14193 15067-15070 15072-15073 '
              '15188-15193 15245-15251 17196-17204 18071-18073 18077-18079 18250-18252'),
    "UNDER ARMOUR": ('58-59 189-194 14194-14196 15075-15076 15078-15079 15081 15194-15196 '
                     '15252-15254 17205-17208 18083-18086'),
    "NEW BALANCE": ('15043-15044 17171-17172 18087-18090 18246-18249'),
    "ASICS": ('17159-17161 18105-18106'),
    "HUMMEL": ('15228-15229 18037'),
    "JOMA": ('17163-17166 18036 18111-18112 18128'),
    "LOTTO": ('37 73 152 14161 15161 17162 18018'),
    "PIRMA": ('17186-17188 18016-18017'),
    "ETC": ('0 15-20 46 64-69 153 196-197 218-219 14182-14183 14197-14202 15015-15020 15182-15183 '
            '15197-15202'),
}


def _spans(text):
    """'1-3 7' -> 1, 2, 3, 7."""
    for s in text.split():
        a, _, b = s.partition("-")
        yield from range(int(a), int(b or a) + 1)


def _lr_item(kind, category, name, asset, order, **extra):
    return {"type": kind, "visible": True, "category": category, "itemname": "LOCKERROOM_" + name,
            "asset": asset, "order": order, **extra}


@functools.lru_cache(maxsize=None)
def lockerroom_items():
    """GET /static/db/LOCKERROOMITEM. Ids stay fixed (saved looks refer to them): the rows below
    1-17, keeper gloves 1000 + texture, boots 100000 + shoecode."""
    rows = (("TOP", "TATTOO", "TOP_TATTOOSHOW", 0, {}), ("TOP", "TATTOO", "TOP_TATTOOHIDDEN", -1, {}),
            ("TOP", "UNIFORMKIND", "TOP_OUTSTYLE", 0, {}), ("TOP", "UNIFORMKIND", "TOP_INSTYLE", 1, {}),
            ("TOP", "UNIFORMKIND", "TOP_TECHSTYLE", 1, {"option": "FIT"}),
            ("TOP", "UNIFORMARM", "TOP_UNISHORT", 0, {}), ("TOP", "UNIFORMARM", "TOP_UNILONG", 1, {}),
            ("TOP", "UNIFORMARM", "TOP_UNIWINTERGEAR", 1, {"option": "WINTERGEAR"}),
            ("TOP", "WRIST", "TOP_WRISTHIDDEN", 0, {}), ("TOP", "WRIST", "TOP_WRISTSHORT", 67, {"color": LR_COLORS}),
            ("TOP", "GLOVE", "TOP_GLOVEHIDDEN", 0, {"option": "PLAYERGLOVE"}),
            ("TOP", "GLOVE", "TOP_GLOVEFIELD", 6, {"option": "PLAYERGLOVE", "color": LR_COLORS}),
            ("PANTS", "SOCKS", "PANTS_SOCKSNORMAL", 0, {}), ("PANTS", "SOCKS", "PANTS_SOCKSSHORT", 1, {}),
            ("PANTS", "SOCKS", "PANTS_SOCKSLONG", 2, {}),
            ("PANTS", "KNEE", "PANTS_KNEEHIDDEN", 0, {}), ("PANTS", "KNEE", "PANTS_KNEEPAD", 1, {"color": LR_COLORS}))
    items = {str(i): _lr_item(*row[:4], i, **row[4]) for i, row in enumerate(rows, 1)}
    for i, n in enumerate(LR_GK_GLOVES):
        items[str(1000 + n)] = _lr_item("TOP", "GLOVE", f"GLOVEGK_{n}", 18, i, option="GKGLOVE", color=str(n))
    for b, (brand, codes) in enumerate(LR_SHOES.items()):
        for k, code in enumerate(_spans(codes)):
            items[str(100_000 + code)] = _lr_item("SHOES", "SHOES", f"SHOES_{code}", code, b * 1000 + k, option=brand)
    return items


def _my_card(pid):
    st = _state(); slot = _default_slot(st)
    return st, slot, next((p for p in st["teams"][str(slot)]["players"] if iid(p) == pid), None)


def ep_lockerroom_itemset(pid, query, body):
    """PUT /lockerroom/<_id>/itemset {itemset: {lockerroomid: {id, pos?, clr?}}} ({} = Reset): the
    card's look. The reply's /coach/me gives the client the new lr, which it reads back when the
    player is picked again."""
    st, slot, p = _my_card(pid)
    if p is None:
        return _json({"result": False})
    items = lockerroom_items()
    itemset = json.loads(body or b"{}").get("itemset") or {}
    lr = {k: v for k, v in itemset.items() if k in items and isinstance(v, dict)}
    if lr:
        p["lr"] = lr
    else:
        p.pop("lr", None)
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


def ep_lockerroom_jersey(pid, query, body):
    """PUT /lockerroom/<_id>/jersey {desired, giverplayerid}: shirt number 1-99; the player who
    wears it gets this player's old number."""
    st, slot, p = _my_card(pid)
    n = int(json.loads(body or b"{}").get("desired") or 0)
    if p is None or not 1 <= n <= 99:
        return _json({"result": False})
    giver = next((x for x in st["teams"][str(slot)]["players"] if x is not p and x.get("jersey") == n), None)
    if giver is not None:
        giver["jersey"] = p.get("jersey", 0)
    p["jersey"] = n
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)})


# --------------------------------------------------------------------------- #
# Shop > Pemain sells player packs for EP; Item saya > Pemain opens them one card at a time
# (TeamManagementPlayerCardScreen: POST /item/<_id>/use -> {player}). Icons are the real FO3 ID
# shop images in the client's CDN cache (externalAssets/shop/<itemid>.png). A pack draws a
# Market card from its pool, cheaper cards more likely (weight price^-0.75: ~0.5% for a card
# worth 10x the pool median); its price is the expected card value at fifaaddict prices.
# --------------------------------------------------------------------------- #
POSITIONS = {"GK": (0, 0), "DF": (1, 8), "MF": (9, 19), "FW": (20, 27)}  # preferredposition1
PACKS = {  # itemid (= shop icon): (name, pool)
    28001: ("Premier League 65+", {"league": 13, "ovr": 65}),
    28002: ("Bundesliga 65+", {"league": 19, "ovr": 65}),
    28003: ("LaLiga 65+", {"league": 53, "ovr": 65}),
    28004: ("Serie A 65+", {"league": 31, "ovr": 65}),
    28005: ("Ligue 1 65+", {"league": 16, "ovr": 65}),
    28006: ("FW 60+", {"pos": "FW", "ovr": 60}),
    28007: ("MF 60+", {"pos": "MF", "ovr": 60}),
    28008: ("DF 60+", {"pos": "DF", "ovr": 60}),
    28009: ("GK 60+", {"pos": "GK", "ovr": 60}),
    8223600: ("FW 65+", {"pos": "FW", "ovr": 65}),
    8223601: ("MF 65+", {"pos": "MF", "ovr": 65}),
    8223602: ("DF 65+", {"pos": "DF", "ovr": 65}),
    8223603: ("GK 65+", {"pos": "GK", "ovr": 65}),
    8223508: ("FW NEW 70+ 2017", {"pos": "FW", "ovr": 70, "season": 88}),
    8223509: ("MF NEW 70+ 2017", {"pos": "MF", "ovr": 70, "season": 88}),
    8223510: ("DF NEW 70+ 2017", {"pos": "DF", "ovr": 70, "season": 88}),
    82214068: ("World Best 300 2017", {"top": 300, "season": 88}),
    82214180: ("World Best 50 2017", {"top": 50, "season": 88}),
    # This Season = 2017 (spid season 88 = the client's DEFAULT_SEASON_ID, badge '17)
    45011: ("This Season Top 10", {"top": 10, "season": 88}),
    45012: ("This Season Top 20", {"top": 20, "season": 88}),
    45013: ("This Season Top 30", {"top": 30, "season": 88}),  # (Top 50 = World Best 50 2017)
    45097: ("This Season Top 30 +8", {"top": 30, "season": 88, "grade": 8}),
    # older seasons; fifaaddict season codes: 2006..2011 = 6..11, 2014 = 14, 2015 = 15
    45004: ("06-11 Player Top 10", {"top": 10, "seasons": (6, 7, 8, 9, 10, 11)}),
    45006: ("06-11 Player Top 30", {"top": 30, "seasons": (6, 7, 8, 9, 10, 11)}),
    45007: ("06-11 Player Top 50", {"top": 50, "seasons": (6, 7, 8, 9, 10, 11)}),
    82214356: ("All '07", {"season": 7}),
    739: ("'08 Top 3", {"top": 3, "season": 8}),
    15031: ("'14 Top 30 +5", {"top": 30, "season": 14, "grade": 5}),
    16001: ("'15 Top 30 +5", {"top": 30, "season": 15, "grade": 5}),
    # special seasons: wc2010 = 47, ucl2010 = 69, wc2014 = 77, tots2014 = 53, 16ec = 35, lp = 23,
    # wb (World Best) = 91, wl (World Legend) = 93
    7622: ("World Cup '10 Top 30", {"top": 30, "season": 47}),
    7618: ("Europe '10 Top 30 +3", {"top": 30, "season": 69, "grade": 3}),
    880047: ("World Cup '14 Top 50", {"top": 50, "season": 77}),
    45020: ("Special Season '14 Top 30", {"top": 30, "season": 77}),
    45063: ("Special Season '14 Top 50 +5", {"top": 50, "season": 77, "grade": 5}),
    45026: ("Team of the Season '14 Top 20", {"top": 20, "season": 53}),
    45027: ("Team of the Season '14 Top 30", {"top": 30, "season": 53}),
    45028: ("Team of the Season '14 Top 50", {"top": 50, "season": 53}),
    45130: ("Team of the Season '14 All", {"season": 53}),
    8157: ("EC Top 10", {"top": 10, "season": 35}),
    82232124: ("EC Top 30 +3", {"top": 30, "season": 35, "grade": 3}),
    8135: ("Best EC 30 +5", {"top": 30, "season": 35, "grade": 5}),
    8329: ("LP Top 50 +3", {"top": 50, "season": 23, "grade": 3}),
    8334: ("World Best 5", {"top": 5, "season": 91}),
    8336: ("World Best 1", {"top": 1, "season": 91}),
    82231307: ("World Best +5", {"season": 91, "grade": 5}),
    8194: ("World Legend Top 30", {"top": 30, "season": 93}),
    8335: ("World Legend Top 3", {"top": 3, "season": 93}),
    # every season
    82214007: ("Top 300", {"top": 300}),
    8223562: ("Best 30", {"top": 30}),
    # user: "pack baru khusus all session grade 1-8", then "all session pack  top 50 ganti menjadi top 200",
    # then "all session top 200 pack ganti ke all session top 300" and "(OVR 81– sampai tertinggi)":
    # every Market card rated 81 and up (353 cards; a top-300 cut kept only 43 of the 96 81s)
    7675: ("All Season Top 300 +8", {"ovr": 81 + GRADE_BOOST[1], "grade": 8, "all": True}),
}
# "All <season>" like All '07 for every season fifaaddict lists (user: "yang keluar cuma 07,
# saya mau semua session"): (fifaaddict label, card season codes, closest shop icon). Codes
# checked against fifaaddict's own listings (e.g. tco92 = 49, mufclegend = 55, cel = 31 + 33).
FA_SEASONS = (
    ("06", (6,), 45004), ("06U", (63,), 7618), ("06WC", (65,), 7622), ("08", (8,), 739), ("08E", (67,), 8157),
    ("09", (9,), 45006), ("10", (10,), 45007), ("10U", (69,), 7618), ("10WC", (47,), 7622), ("11", (11,), 45004),
    ("14", (14,), 15031), ("14WC", (77,), 880047), ("14T", (53,), 45026), ("15", (15,), 16001), ("16", (16,), 16001),
    ("17", (88,), 45011), ("16EC", (35,), 8157), ("16TH", (45,), 8545), ("WB", (91,), 8334), ("WL", (93,), 8194),
    ("UB", (28,), 8336), ("UL", (30,), 8335), ("EL", (27,), 8194), ("LP", (23,), 8329), ("CP", (22,), 8549),
    ("CC", (24,), 8547), ("17TH", (44,), 8545), ("TCO92", (49,), 8546), ("MUA", (55,), 8547), ("ML", (71,), 8549),
    ("TL", (51,), 8549), ("VL", (61,), 8549), ("CL", (89,), 8549), ("KL02", (95,), 8546), ("CEL", (31, 33), 8335),
    ("U23", (29,), 8545), ("KXI", (97,), 8546), ("MUL", (48,), 8547), ("VS", (73,), 2000006),
)
# each one the season's 200 best cards (user: "all session pack  top 50 ganti menjadi top 200")
PACKS.update({92000000 + codes[0]: (f"{label} Top 200", {"seasons": codes, "icon": icon, "top": 200, "all": True})
              for label, codes, icon in FA_SEASONS})
PACKS[82214356] = ("07 Top 200", {"season": 7, "top": 200, "all": True})  # the original All '07 item
# every Market card of every season, so each one is in some pack (the season packs keep only
# their 200 best; '17 alone has 15,000+ cards); the "ALL" icon of All Season Top 300 +8
ALL_PLAYERS_PACK = 92000000
PACKS[ALL_PLAYERS_PACK] = ("Semua Pemain", {"all": True, "icon": 7675})
# Draft packs (issue #27, "Pilih pak pemain", category DRAFTPACK): Item saya > Pemain > Gunakan
# opens TeamManagementDraftPackScreen for one season (staticdata.draft {season, grade, availables}).
# GET /item/draftpack/<itemid>/players/<n> = the pack's n most valuable cards: the first call
# (n = availables) fills the pick list, the second (n = 100) is the search list; a searched card
# outside those is priced by POST /transfer/price/default/<grade>. "Konfirmasi" opens the card
# screen, which posts /item/<_id>/use {id, spids}: one of the picked cards, at the pack's grade.
PACKS.update({
    8223735: ("06 Draft Pick 3", {"season": 6, "all": True, "draft": 3}),
    200005: ("2017 Draft Pick 5", {"season": 88, "all": True, "draft": 5}),
    97093: ("World Legend Draft Pick 3", {"season": 93, "all": True, "draft": 3, "icon": 8335}),
})
PACK_BUNCHES = (1, 10)  # buy 1 or 10 (5% off)
_PACK_POOL = {}


def pack_pool(itemid):
    """[(spid, weight)] of the Market cards a pack can give (cached)."""
    if itemid not in _PACK_POOL:
        f = PACKS[itemid][1]
        lo, hi = POSITIONS.get(f.get("pos"), (0, 27))
        seasons = f.get("seasons") or ((f["season"],) if "season" in f else None)
        # "65+" = the rating the card shows once opened (POSOVR base + its grade's boost, as on fifaaddict)
        # "all" packs take every Market card; the others only cards licensed for the ID region
        # (permid), which leaves e.g. 37 of the 395 '06 cards
        with closing(_db()) as c:
            rows = c.execute(f"""SELECT p.spid, {POSOVR} AS ovr FROM players p LEFT JOIN permid m ON m.spid = p.spid
                                 WHERE ovr >= ?1 AND p.preferredposition1 BETWEEN ?2 AND ?3
                                 AND (?4 IS NULL OR p.leagueid = ?4) AND (?5 OR m.licensed = 1)""",
                             (f.get("ovr", 0) - GRADE_BOOST[1], lo, hi, f.get("league"), bool(f.get("all")))).fetchall()
        rows = sorted(((s, o) for s, o in rows if on_market(s) and (not seasons or s // 1000000 in seasons)),
                      key=lambda r: -r[1])[:f.get("top")]
        # a price far below the pool's (odd fifaaddict data, e.g. a 120k World Best card among 20M+
        # ones) would win almost every draw: weigh anything under a tenth of the median as that tenth
        card_ovrs([s for s, _ in rows])  # one batch: card by card took 12 s for Semua Pemain's 44,703
        prices = [card_price(s) for s, _ in rows]
        floor = sorted(prices)[len(prices) // 2] / 10 if prices else 0  # no card: an empty pool
        _PACK_POOL[itemid] = [(s, max(p, floor) ** -0.75) for (s, _), p in zip(rows, prices)]
    return _PACK_POOL[itemid]


def pack_grades(itemid):
    """[(grade, weight)]: a "+N" pack's card comes at a random grade +1..+N, lower grades more
    likely (weight N-g+1: for +5 that is 33/27/20/13/7%); other packs give +1. A draft pack's
    cards come at its grade (the draft screen shows their prices at it)."""
    f = PACKS[itemid][1]
    n = f.get("grade", 1)
    return [(n, 1)] if f.get("draft") else [(g, n - g + 1) for g in range(1, n + 1)]


def draft_top(itemid, n):
    """A draft pack's n most valuable cards (the default picks and the search list)."""
    return sorted((s for s, _ in pack_pool(itemid)), key=lambda s: (-card_price(s), s))[:n]


def pack_grade(itemid):
    grades = pack_grades(itemid)
    return random.choices([g for g, _ in grades], [w for _, w in grades])[0]


@functools.lru_cache(maxsize=None)
def pack_price(itemid):
    draft = PACKS[itemid][1].get("draft")
    if draft:  # worth the default picks (the n best cards) at the pack's grade
        g = pack_grades(itemid)[0][0]
        top = draft_top(itemid, draft)
        return sig3(sum(card_price(s, g) for s in top) / len(top)) if top else 0
    pool, grades = pack_pool(itemid), pack_grades(itemid)
    gw = sum(w for _, w in grades)
    return sig3(sum(card_price(s, g) * w * gwt for s, w in pool for g, gwt in grades) / sum(w for _, w in pool) / gw)


def warm_packs():
    """Build every pack pool and price and the trade pools once (~20 s) so the first Shop or
    Tukar request does not stall the client."""
    for itemid in PACKS:
        pack_price(itemid)
    trade3_pool()


SHOP_FREE = True  # user: "shop jadi 0 semua" -> every Shop product costs 0 EP (admin page: shop.json "free")


def item_def(itemid):
    """Item staticdata (POST /static/cache/item, shop products, coach items)."""
    if itemid == EP_ITEM:
        return EP_ITEM_DEF
    if itemid == ES_ITEM:
        return ES_ITEM_DEF
    if itemid in ITEMS:
        return use_item_def(itemid)
    if itemid in PACKAGES or itemid in MONTHLY:
        return package_def(itemid)
    name, f = PACKS[itemid]
    d = {"itemid": itemid, "productid": itemid, "name": name, "category": "PLAYERPACK",
         "type": "LEAGUE" if "league" in f else "POSITION" if "pos" in f else "CUSTOM",
         "unit": "COUNT", "itemicon": f.get("icon", itemid), "currency": "ep",
         **({"bundleicon": f["icon"]} if "icon" in f else {}),  # several packs share one icon
         "bunches": [{"bunch": n, "price": product_price(itemid, n, lambda: pack_price(itemid))} for n in PACK_BUNCHES],
         **({"draw": {"year": 2017}} if f.get("season") == 88 else {})}
    if f.get("draft"):  # one season: the draft screen's name search filters on it
        d.update(category="DRAFTPACK", type="DRAFTPACK", draft={
            "season": (f.get("seasons") or (f.get("season"),))[0], "grade": f.get("grade", 1), "availables": f["draft"]})
    return d


# --------------------------------------------------------------------------- #
# Shop items besides player packs (icons = the real FO3 ID shop images in the client cache).
# Category USE (Shop > Dapat dikonsumsi; Item saya > Dapat dikonsumsi): "Gunakan" opens the
# item's screen (GeneralInventoryTileItemRenderer.useUseItem by staticdata.type), which posts
# /item/<_id>/use (ItemUtil.postItemUse):
#   EP_LOTTERY (TeamManagementEPCardScreen) {id} -> {result, ep}
#   ITEM_LOTTERY (TeamManagementRandomCardScreen) {id} -> {result, ep} | {result, item:{itemid, count}}
#   COACHNAME_CHANGE {name} -> {result} (the name check first posts /coach/reservename {name})
#   TEAM_CHANGE (nation/league/club steppers, /static/info/team/summary/<id>) {teamid} -> {result}
# PACKAGE (Shop > Paket) bundles drop their items into the inventory on purchase; MILEAGE
# (MP Shop) sells copies of some items. All free while SHOP_FREE.
# --------------------------------------------------------------------------- #
EP_ITEM = 1  # externalAssets/shop/1.png = EP coin: EP in Bag entries and package contents
EP_ITEM_DEF = {"itemid": EP_ITEM, "productid": EP_ITEM, "name": "EP", "category": "EP", "type": "EP",
               "unit": "EP", "itemicon": EP_ITEM}
ES_ITEM = 2  # upgrade points (money.es) in package contents, credited like EP; icon 8700001 = "P"
ES_ITEM_DEF = {"itemid": ES_ITEM, "productid": ES_ITEM, "name": "Upgrade point", "category": "USE", "type": "ES",
               "unit": "COUNT", "itemicon": 8700001}
ITEMS = {  # itemid: (name, icon, type, effect, description)
    501: ("Lucky EP", 501, "EP_LOTTERY", {"ep": (10_000, 1_000_000)}, "Buka kartu: dapat 10.000 - 1.000.000 EP."),
    50029: ("Lucky EP max 20.000.000", "ID50029", "EP_LOTTERY", {"ep": (100_000, 20_000_000)},
            "Buka kartu: dapat 100.000 - 20.000.000 EP."),
    50028: ("Lucky EP max 50.000.000", "ID50028", "EP_LOTTERY", {"ep": (200_000, 50_000_000)},
            "Buka kartu: dapat 200.000 - 50.000.000 EP."),
    908: ("Jutawan EP Lottery", 908, "EP_LOTTERY", {"ep": (1_000_000, 10_000_000)}, "Undian EP: 1 - 10 juta EP."),
    50019: ("EP +200.000", "ID50019", "EP_LOTTERY", {"ep": (200_000, 200_000)}, "Langsung dapat 200.000 EP."),
    50020: ("EP +500.000", "ID50020", "EP_LOTTERY", {"ep": (500_000, 500_000)}, "Langsung dapat 500.000 EP."),
    50021: ("EP +1.000.000", "ID50021", "EP_LOTTERY", {"ep": (1_000_000, 1_000_000)}, "Langsung dapat 1.000.000 EP."),
    50840: ("Kantong EP", "ID50840", "EP_LOTTERY", {"ep": (500_000, 5_000_000)}, "Isi 500.000 - 5.000.000 EP."),
    50841: ("Peti EP", "ID50841", "EP_LOTTERY", {"ep": (5_000_000, 30_000_000)}, "Isi 5 - 30 juta EP."),
    119082304: ("Mesin Jackpot EP", 119082304, "EP_LOTTERY", {"ep": (100_000, 100_000_000)},
                "Jackpot: 100.000 - 100.000.000 EP."),
    # random boxes: one prize from the table, (weight, EP amount | pack itemid)
    50121: ("Kotak Platinum", "ID50121GP", "ITEM_LOTTERY",
            {"prizes": [(10, 8334), (5, 8194), (25, 82214007), (30, 45011), (30, ("ep", 10_000_000))]},
            "Hadiah acak: World Best 5, World Legend Top 30, Top 300, This Season Top 10 atau 10 juta EP."),
    50122: ("Kotak Emas", "ID50122GP", "ITEM_LOTTERY",
            {"prizes": [(30, 82214180), (40, 45012), (30, ("ep", 3_000_000))]},
            "Hadiah acak: World Best 50 2017, This Season Top 20 atau 3 juta EP."),
    50123: ("Kotak Perak", "ID50123GP", "ITEM_LOTTERY",
            {"prizes": [(25, 8223600), (25, 8223601), (25, 8223602), (25, ("ep", 1_000_000))]},
            "Hadiah acak: pak FW/MF/DF 65+ atau 1 juta EP."),
    50124: ("Kotak Perunggu", "ID50124GP", "ITEM_LOTTERY",
            {"prizes": [(25, 28006), (25, 28007), (25, 28008), (25, ("ep", 300_000))]},
            "Hadiah acak: pak FW/MF/DF 60+ atau 300.000 EP."),
    50125: ("Kotak Metal", "ID50125GP", "ITEM_LOTTERY",
            {"prizes": [(50, 82214356), (50, ("ep", 100_000))]}, "Hadiah acak: pak 07 Top 200 atau 100.000 EP."),
    200130000: ("Kotak Hadiah Perak", 200130000, "ITEM_LOTTERY",
                {"prizes": [(40, ("ep", 200_000)), (30, 28009), (30, 82214068)]},
                "Hadiah acak: 200.000 EP, pak GK 60+ atau World Best 300 2017."),
    200130001: ("Kotak Hadiah Emas", 200130001, "ITEM_LOTTERY",
                {"prizes": [(40, ("ep", 1_000_000)), (30, 45007), (30, 45013)]},
                "Hadiah acak: 1 juta EP, 06-11 Player Top 50 atau This Season Top 30."),
    3002: ("Ganti nama manager", 3002, "COACHNAME_CHANGE", {}, "Ganti nama manager Anda."),
    3001: ("Ganti tim", 3001, "TEAM_CHANGE", {}, "Pindah ke klub lain (logo, seragam, liga); pemain tetap."),
    # Upgrade 2.5 boost items (EnhanceControlPanel lists type ENHANCEMENT_BOOST; names from the
    # client's ENHANCEMENT_BOOST<id>; the cache has no icons of their own, 1000002 = green arrows)
    1000052: ("Enhancement Boost Gold", 1000002, "ENHANCEMENT_BOOST", {"boost": 0.15}, "Upgrade: peluang sukses +15%."),
    1000053: ("Enhancement Boost Silver", 1000002, "ENHANCEMENT_BOOST", {"boost": 0.10}, "Upgrade: peluang sukses +10%."),
    1000054: ("Enhancement Boost Bronze", 1000002, "ENHANCEMENT_BOOST", {"boost": 0.05}, "Upgrade: peluang sukses +5%."),
    # League Simulation coupon (user: "item untuk League Simulation, jadi tanpa main league langsung
    # hasil"): Liga's Simulasi button (LeagueCupFrontScreenCalendarTabPage) counts the Item saya
    # items of type LEAGUE_SIMULATION and stays off at 0 (a click then opens the Shop on its
    # SIMULATION_ITEM_ID "2001"); each simulated match uses one up (ep_l2_match)
    2001: ("Simulasi Liga", 2001, "LEAGUE_SIMULATION", {}, "Liga: hasil satu pertandingan langsung, tanpa main."),
    # EXP capsules (issue #27, "Level capsule"; TeamManagementExpCapsuleScreen): "Gunakan" lists the
    # players it fits (below the max level, at most level lv, of the season) and posts
    # /item/<_id>/use {targetid}; that player gets the EXP. LV.1 -> LV.23 takes 25.300 EXP.
    6001: ("EXP Capsule 1.000", "ID50071", "PLAYER_EXP_CAPSULE", {"exp": 1000}, "EXP pemain +1.000."),
    6002: ("EXP Capsule 5.000", "ID50071", "PLAYER_EXP_CAPSULE", {"exp": 5000}, "EXP pemain +5.000."),
    6003: ("EXP Capsule Max", "ID50071", "PLAYER_EXP_CAPSULE", {"exp": 25_300}, "Pemain langsung ke level max (LV.23)."),
    6004: ("EXP Capsule LV.10", "ID50071", "PLAYER_EXP_CAPSULE", {"exp": 3000, "lv": 10},
           "EXP pemain +3.000, untuk pemain LV.10 ke bawah."),
    6005: ("EXP Capsule 2017", "ID50071", "PLAYER_EXP_CAPSULE", {"exp": 10_000, "season": 88},
           "EXP pemain +10.000, untuk pemain musim 2017."),
}
SIM_COUPON = 2001
PACKAGES = {  # itemid: (name, icon, [(itemid, count)], description); bought = contents to Item saya
    801: ("Paket Starter", 801, [(28006, 1), (28007, 1), (28008, 1), (28009, 1), (50020, 2)],
          "Pak FW/MF/DF/GK 60+ dan 2x EP +500.000."),
    50880: ("Kotak Terima Kasih", "ID50880", [(50021, 1), (50122, 1), (501, 3)],
            "EP +1.000.000, Kotak Emas dan 3x Lucky EP."),
    50881: ("Kotak World Best", "ID50881", [(8334, 1), (82214180, 3), (82214068, 5)],
            "World Best 5, 3x World Best 50 2017, 5x World Best 300 2017."),
    50882: ("Kotak Legenda 06-11", "ID50882", [(45004, 1), (45006, 2), (45007, 3)],
            "06-11 Player Top 10, 2x Top 30, 3x Top 50."),
    118012902: ("Kotak Upgrade", 118012902, [(15031, 1), (7618, 1), (82232124, 1)],
                "'14 Top 30 +5, Europe '10 Top 30 +3, EC Top 30 +3."),
    80000001: ("VIP Premium", "vipterbaru", [(50028, 1), (50121, 1), (50021, 5)],
               "Lucky EP max 50 juta, Kotak Platinum, 5x EP +1.000.000."),
    # upgrade points (user: "point upgrade beli dimana?"): Upgrade's "Gunakan poin" / restore
    81000100: ("Upgrade Point 100", 8700001, [(ES_ITEM, 100)], "100 upgrade point untuk Upgrade."),
    81000500: ("Upgrade Point 500", 8700001, [(ES_ITEM, 500)], "500 upgrade point untuk Upgrade."),
    81001000: ("Upgrade Point 1.000", 8700001, [(ES_ITEM, 1000)], "1.000 upgrade point untuk Upgrade."),
}
PACKAGES.update({  # Serial product steps (CHAINED below), bought in order
    70000001: ("Paket Berantai 1/3", 200130000, [(501, 3), (28007, 1)], "Tahap 1: 3x Lucky EP dan pak MF 60+."),
    70000002: ("Paket Berantai 2/3", 200130001, [(50122, 1), (50021, 1)], "Tahap 2: Kotak Emas dan EP +1.000.000."),
    70000003: ("Paket Berantai 3/3", "ID50121GP", [(50121, 1), (8334, 1)], "Tahap 3: Kotak Platinum dan World Best 5."),
})
MP_SHOP = (501, 50123, 50122, 45013, 45006, 3002)  # MP Shop (shopcategory MILEAGE) copies
MP_SHOPID = 900_000_000  # MP Shop entries: shopid = MP_SHOPID + itemid (productid stays itemid)
# Serial product (ShopChainedPackageTabPage, ShopController.currentChainedItemCheck): one entry
# {shopcategory CHAINED, step, chained: [later steps]}; the client shows step 0 = the entry
# itself, step k = chained[k-1]; remainedperaccount 0 marks a bought step ("complete").
CHAINED = {70000001: (70000001, 70000002, 70000003)}  # first step's itemid: all steps
# Special Bonus (ShopSpecialTabPage): GET /specifictarget {issell, targets:[{stid, endtime}]} and
# GET /shop/list/STSHOP = [entries with those stids] (ShopController keeps the targeted ones).
SPECIAL = (8335, 8194, 50841, 50881)
STSHOPID = 910_000_000
# Paket Bulanan (ShopMonthlyPackageTabPage: shopcategory MONTHLYPACK; ShopMonthlyPackageProxy):
# items now, then dailyitems every day for daily_period days; GET /monthlypack = my packages
# [{productid, product, expireat, rewardedat}], POST /monthlypack (the proxy, once a day while
# active) drops the day's items into the Bag as type "monthlypack".
MONTHLY = {  # itemid: (name, icon, days, items now, daily items, description)
    81000001: ("Paket Bulanan EP", "ID50840", 30, [(50021, 1)], [(EP_ITEM, 200_000)],
               "Langsung EP +1.000.000, lalu 200.000 EP tiap hari selama 30 hari."),
    81000002: ("Paket Bulanan Pak", 200130001, 30, [(8223601, 1)], [(28007, 1), (EP_ITEM, 50_000)],
               "Langsung pak MF 65+, lalu pak MF 60+ dan 50.000 EP tiap hari selama 30 hari."),
    81000003: ("Paket Bulanan Premium", "ID50841", 30, [(50121, 1)], [(45013, 1), (EP_ITEM, 500_000)],
               "Langsung Kotak Platinum, lalu This Season Top 30 dan 500.000 EP tiap hari selama 30 hari."),
}


def use_item_def(itemid, prizes=True):
    name, icon, typ, eff, desc = ITEMS[itemid]
    return {"itemid": itemid, "productid": itemid, "name": name, "category": "USE", "type": typ, "unit": "COUNT",
            "itemicon": icon, "bundleicon": icon, "currency": "ep", "stackable": True, "description": desc,
            # TeamManagementEPCardScreen.onQuery sizes the coin counter from count.max
            **({"count": {"min": eff["ep"][0], "max": eff["ep"][1]}} if "ep" in eff else {}),
            # an EXP capsule's EXP and limits (GeneralInventoryTileItemRenderer.useUseItem)
            **{"capsule" + k: eff[k] for k in ("exp", "lv", "season") if eff.get(k)},
            # a random box's prizes: TeamManagementRandomCardScreen.SetItemBackground hands
            # staticdata.availables to its panel as item tiles (GeneralInventoryTileItemRenderer);
            # none crashed every box at "Gunakan" (issue #12). A box among the prizes shows no prizes
            # of its own (no loop).
            **({"availables": [prize_item(p) for _, p in eff["prizes"]]} if prizes and "prizes" in eff else {}),
            "bunches": [{"bunch": n, "price": product_price(itemid, n)} for n in PACK_BUNCHES]}


def prize_item(p):
    """A prize ("ep", amount) | itemid as an item entry {itemid, count, staticdata}."""
    if isinstance(p, tuple):
        return {"itemid": EP_ITEM, "count": p[1], "staticdata": EP_ITEM_DEF}
    return {"itemid": p, "count": 1, "staticdata": use_item_def(p, False) if p in ITEMS else item_def(p)}


def package_def(itemid):
    if itemid in MONTHLY:
        name, icon, days, now, daily, desc = MONTHLY[itemid]
        contents, extra = now, {"daily_period": days, "monthly_platform": "all",
                                "dailyitems": [{"itemid": i, "count": n, "staticdata": item_def(i)} for i, n in daily]}
    else:
        name, icon, contents, desc = PACKAGES[itemid]
        extra = {}
    return {"itemid": itemid, "productid": itemid, "name": name, "category": "PACKAGE", "type": "ITEM",
            "unit": "COUNT", "itemicon": icon, "bundleicon": icon, "currency": "ep", "description": desc,
            "bunches": [{"bunch": 1, "price": product_price(itemid, 1)}], **extra,
            "items": [{"itemid": i, "count": n, "staticdata": item_def(i)} for i, n in contents]}


SHOP_NEW = (45011, 45004, 50121, 50881, 501)  # Rekomendasi: "new" order
SHOP_BEST = (82214180, 8223600, 28001, 28003, 8223601)  # Rekomendasi: Terlaris rank


def shop_entry(itemid, category="PLAYERPACK", shopid=None):
    d = item_def(itemid)
    rank = {k: t.index(itemid) + 1 for k, t in (("new", SHOP_NEW), ("best", SHOP_BEST)) if itemid in t and not shopid}
    icon = d.get("bundleicon", itemid)
    items = d["items"] if category == "PACKAGE" else [{"itemid": itemid, "count": 1, "staticdata": d}]
    return {"_id": str(shopid or itemid), "shopid": shopid or itemid, "shopcategory": category, "forceenable": True,
            "visible": True, **rank, "salestart": "2014-01-01T00:00:00.000Z", "saleend": "2035-01-01T00:00:00.000Z",
            "product": {"itemid": itemid, "staticdata": {**d, "bundleicon": icon, "items": items}}}


CHAIN_STEPS = {i: (first, k) for first, steps in CHAINED.items() for k, i in enumerate(steps)}


def chained_entry(st, first):
    """A Serial product at my progress: step = steps bought (capped at the last)."""
    steps, done = CHAINED[first], my_coach(st).get("chain", {}).get(str(first), 0)
    parts = [dict(shop_entry(i, "CHAINED"), remainedperaccount=0 if k < done else 1, buy=k < done)
             for k, i in enumerate(steps)]
    return {**parts[0], "step": min(done, len(steps) - 1), "chained": parts[1:]}


def shop_list(st):
    """GET /shop/list: every Shop tab's products (ShopController filters them by shopcategory);
    the ones hidden on the admin page are left out."""
    on = lambda i: i not in SHOP_HIDDEN
    return ([shop_entry(i) for i in PACKS if on(i)] + [shop_entry(i, "USE") for i in ITEMS if on(i)]
            + [shop_entry(i, "PACKAGE") for i in PACKAGES if i not in CHAIN_STEPS and on(i)]
            + [shop_entry(i, "MILEAGE", MP_SHOPID + i) for i in MP_SHOP if on(i)]
            + [shop_entry(i, "MONTHLYPACK") for i in MONTHLY if on(i)]
            + [chained_entry(st, first) for first in CHAINED if on(first)])


def product_category(itemid):
    return "PLAYERPACK" if itemid in PACKS else "USE" if itemid in ITEMS else "PACKAGE"


# --------------------------------------------------------------------------- #
# Shop catalog from the admin page (user: "di admin page buatkan untuk kontrol shop semua tab, bisa
# buat pack baru, paket baru dll"; issue #10). gamedata/shop.json holds only what was changed
# there, on top of the built-in tables above:
#   free     every product costs 0 EP (default SHOP_FREE)
#   prices   {itemid: EP for one}: a fixed price, also while the Shop is free (0 = free)
#   hidden   [itemid]: left out of every Shop tab (cards and items already owned still work)
#   packs    {itemid: {name, icon, seasons [codes], top, ovr (rating at +1), grade (max +N), pos
#             (FW/MF/DF/GK), league, all (any card, else ID-licensed only), draft (pick N of
#             one season's cards, opened at +grade)}}
#   items    {itemid: {name, icon, type, description, ep [min, max] | prizes [[weight, itemid |
#             {"ep": n}]] | boost (0..1) | exp, lv, season (EXP capsule)}}: the types use_item knows
#   packages {itemid: {name, icon, contents [[itemid, count]], description}}
#   monthly  {itemid: {name, icon, days, now [[itemid, count]], daily [[itemid, count]], description}}
#   lists    {new, best (Rekomendasi), mp (MP Shop), special (Bonus spesial): [itemid],
#             chained: [[package itemid, ...]] (Paket berantai, bought in order)}
# A built-in itemid in packs/items/packages/monthly is replaced by that entry. apply_shop()
# rebuilds the tables in place (every lookup above keeps working) and drops the pack pools.
# --------------------------------------------------------------------------- #
SHOP_FILE = os.path.join(HERE, "gamedata", "shop.json")
SHOP_ITEM_TYPES = ("EP_LOTTERY", "ITEM_LOTTERY", "COACHNAME_CHANGE", "TEAM_CHANGE", "ENHANCEMENT_BOOST", "LEAGUE_SIMULATION",
                   "PLAYER_EXP_CAPSULE")
SHOP_ID_BASE = {"packs": 93_000_000, "items": 94_000_000, "packages": 95_000_000, "monthly": 96_000_000}
SHOP_HIDDEN = frozenset()
_SHOP_BASE = None
_SHOP = {}


def shop_config():
    """The admin page's Shop changes (gamedata/shop.json), {} when there are none."""
    try:
        with open(SHOP_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _pairs(rows):
    return [(int(i), int(n)) for i, n in rows]


def pack_from(v):
    f = {k: v[k] for k in ("top", "ovr", "grade", "pos", "league", "draft") if v.get(k) not in (None, "", 0)}
    if v.get("seasons"):
        f["seasons"] = tuple(int(s) for s in v["seasons"])
    if v.get("all"):
        f["all"] = True
    if v.get("icon"):
        f["icon"] = v["icon"]
    return (str(v["name"]), f)


def pack_to(entry):
    name, f = entry
    seasons = f.get("seasons") or ((f["season"],) if "season" in f else ())
    return {"name": name, "icon": f.get("icon", ""), "seasons": list(seasons), "all": bool(f.get("all")),
            **{k: f.get(k) for k in ("top", "ovr", "grade", "pos", "league", "draft")}}


def item_from(v):
    t = v["type"]
    eff = ({"ep": tuple(int(x) for x in v["ep"])} if t == "EP_LOTTERY"
           else {"prizes": [(int(w), ("ep", int(p["ep"])) if isinstance(p, dict) else int(p)) for w, p in v["prizes"]]}
           if t == "ITEM_LOTTERY" else {"boost": float(v["boost"])} if t == "ENHANCEMENT_BOOST"
           else {k: int(v[k]) for k in ("exp", "lv", "season") if v.get(k)} if t == "PLAYER_EXP_CAPSULE" else {})
    return (str(v["name"]), v.get("icon") or "", t, eff, str(v.get("description") or ""))


def item_to(entry):
    name, icon, t, eff, desc = entry
    return {"name": name, "icon": icon, "type": t, "description": desc,
            **({"ep": list(eff["ep"])} if "ep" in eff else {}), **({"boost": eff["boost"]} if "boost" in eff else {}),
            **{k: eff[k] for k in ("exp", "lv", "season") if k in eff},
            **({"prizes": [[w, {"ep": p[1]} if isinstance(p, tuple) else p] for w, p in eff["prizes"]]}
               if "prizes" in eff else {})}


def package_from(v):
    return (str(v["name"]), v.get("icon") or "", _pairs(v["contents"]), str(v.get("description") or ""))


def package_to(entry):
    name, icon, contents, desc = entry
    return {"name": name, "icon": icon, "contents": [list(c) for c in contents], "description": desc}


def monthly_from(v):
    return (str(v["name"]), v.get("icon") or "", int(v["days"]), _pairs(v["now"]), _pairs(v["daily"]),
            str(v.get("description") or ""))


def monthly_to(entry):
    name, icon, days, now, daily, desc = entry
    return {"name": name, "icon": icon, "days": days, "now": [list(c) for c in now], "daily": [list(c) for c in daily],
            "description": desc}


SHOP_KINDS = {"packs": (PACKS, pack_from, pack_to), "items": (ITEMS, item_from, item_to),
              "packages": (PACKAGES, package_from, package_to), "monthly": (MONTHLY, monthly_from, monthly_to)}


def apply_shop(cfg=None):
    """Rebuild the Shop tables from the built-in ones plus gamedata/shop.json (or cfg)."""
    global _SHOP_BASE, _SHOP, SHOP_FREE, SHOP_HIDDEN, SHOP_NEW, SHOP_BEST, MP_SHOP, SPECIAL, CHAINED, CHAIN_STEPS
    if _SHOP_BASE is None:
        _SHOP_BASE = {"free": SHOP_FREE, "new": SHOP_NEW, "best": SHOP_BEST, "mp": MP_SHOP, "special": SPECIAL,
                      "chained": dict(CHAINED), **{k: dict(t) for k, (t, _, _) in SHOP_KINDS.items()}}
    _SHOP = shop_config() if cfg is None else cfg
    before = dict(PACKS)
    for kind, (table, conv, _) in SHOP_KINDS.items():
        table.clear()
        table.update(_SHOP_BASE[kind])
        table.update({int(k): conv(v) for k, v in (_SHOP.get(kind) or {}).items()})
    lists = _SHOP.get("lists") or {}
    SHOP_FREE = bool(_SHOP.get("free", _SHOP_BASE["free"]))
    SHOP_HIDDEN = frozenset(int(i) for i in _SHOP.get("hidden") or ())
    SHOP_NEW, SHOP_BEST, MP_SHOP, SPECIAL = (tuple(int(i) for i in lists.get(k, _SHOP_BASE[k]))
                                             for k in ("new", "best", "mp", "special"))
    CHAINED = ({int(c[0]): tuple(int(i) for i in c) for c in lists["chained"] if c} if "chained" in lists
               else dict(_SHOP_BASE["chained"]))
    CHAIN_STEPS = {i: (first, k) for first, steps in CHAINED.items() for k, i in enumerate(steps)}
    for k in set(before) | set(PACKS):  # rebuild only the pools of changed packs (all of them take ~7 s)
        if before.get(k) != PACKS.get(k):
            _PACK_POOL.pop(k, None)


def product_price(itemid, n, value=lambda: 0):
    """EP for a bunch of n: the admin page's fixed price, else 0 while the Shop is free, else the
    value (a pack's expected card value); 5% off for 10."""
    fixed = (_SHOP.get("prices") or {}).get(str(itemid))
    if fixed is None and SHOP_FREE:
        return 0
    one = int(fixed) if fixed is not None else value()
    return sig3(one * n * (0.95 if n > 1 else 1)) if one else 0


apply_shop()


def ep_specifictarget(query, body):
    """GET /specifictarget: Special Bonus is open for me (ShopController.getSpecialShopInfo)."""
    return _json({"issell": True, "targets": [{"stid": STSHOPID + i, "endtime": "2035-01-01T00:00:00.000Z"}
                                              for i in SPECIAL if i not in SHOP_HIDDEN]})


def ep_stshop(query, body):
    """GET /shop/list/STSHOP: the Special Bonus products."""
    return _json([dict(shop_entry(i, product_category(i), STSHOPID + i), stid=STSHOPID + i)
                  for i in SPECIAL if i not in SHOP_HIDDEN])


def monthly_list(st):
    """GET /monthlypack body: my active monthly packages."""
    return [{"_id": f"{i:024x}", "productid": i, "product": {"itemid": i, "staticdata": item_def(i)},
             "purchasedat": w3c(m["since"]), "expireat": w3c(m["expire"]), "rewardedat": w3c(m["rewarded"])}
            for i, m in ((int(k), v) for k, v in my_coach(st).get("monthly", {}).items()) if m["expire"] > time.time()]


def ep_monthlypack(query, body):
    """GET /monthlypack: my packages; POST: today's daily items of each (once a day) to the Bag."""
    st = _state()
    if body:  # POST (ShopMonthlyPackageProxy.requestReward)
        today = today_wib()
        for k, m in my_coach(st).get("monthly", {}).items():
            if m["expire"] > time.time() and today_wib(m["rewarded"]) != today and int(k) in MONTHLY:
                name, _, _, _, daily, _ = MONTHLY[int(k)]
                e = bag_add(st, f"{name} - hadiah harian", [{"itemid": i, "count": n} for i, n in daily],
                            msg=f"Hadiah harian {name}.")
                e["type"] = "monthlypack"
                m["rewarded"] = time.time()
        _save(st)
        return _json({"result": True, "resources": [{"uri": "/monthlypack", "body": monthly_list(st)},
                                                    {"uri": "/bag", "body": bag_list(st)}]})
    return _json(monthly_list(st))


def inventory_add(coach, itemid, count):
    inv = coach.setdefault("items", [])
    it = next((i for i in inv if i["itemid"] == itemid), None)
    if it is None:
        it = {"_id": new_iid(), "itemid": itemid, "remains": 0}
        inv.append(it)
    it["remains"] += count
    return it


def my_coach(st):
    return next(c for c in st["coaches"] if c["slot"] == _default_slot(st))


def coach_items(st, slot, where="items"):
    """/coach/me items (where="depot": the Gudang list): one stack per pack ({_id, itemid,
    remains}); expireable marks an owned item (GeneralInventoryTileItemRenderer: Gunakan button
    instead of Beli). Item saya also holds the locker room ticket for good."""
    coach = next(c for c in st["coaches"] if c["slot"] == slot)
    return [{"_id": i["_id"], "id": i["_id"], "itemid": i["itemid"], "remains": i["remains"], "count": i["remains"],
             "expireable": True, "expired": False, "staticdata": item_def(i["itemid"])}
            for i in coach.get(where, []) if i["itemid"] in PACKS or i["itemid"] in ITEMS] + [LR_TICKET_ITEM] * (where == "items")


def ep_shop_purchase(query, body):
    """POST /shop/purchase {shopid, productid, bunch: price option index}: pay EP; packs and
    items go to Item saya, a package's contents too."""
    req = json.loads(body or b"{}")
    itemid = int(req.get("productid") or 0) or int(req.get("shopid") or 0) % MP_SHOPID % STSHOPID
    if itemid in SHOP_HIDDEN or not any(itemid in t for t in (PACKS, ITEMS, PACKAGES, MONTHLY)):
        return _json({"result": False, "reason": "NOT_EXIST_PRODUCT"})
    bunches = item_def(itemid)["bunches"]
    b = bunches[min(max(int(req.get("bunch") or 0), 0), len(bunches) - 1)]
    st = _state(); slot = _default_slot(st); coach = my_coach(st)
    if coach_me(st, slot)["money"]["ep"] < b["price"]:
        return _json({"result": False, "reason": "NOT_ENOUGH_EP"})
    add_ep(st, -b["price"])
    contents = PACKAGES[itemid][2] if itemid in PACKAGES else MONTHLY[itemid][3] if itemid in MONTHLY else [(itemid, 1)]
    for i, n in contents:
        if i == EP_ITEM:
            add_ep(st, n * b["bunch"])
        elif i == ES_ITEM:
            add_es(st, n * b["bunch"])
        else:
            inventory_add(coach, i, n * b["bunch"])
    if itemid in MONTHLY:  # a month of daily items (renewing extends it)
        m = coach.setdefault("monthly", {}).setdefault(str(itemid), {"since": time.time(), "expire": time.time(), "rewarded": 0})
        m["expire"] = max(m["expire"], time.time()) + MONTHLY[itemid][2] * 86400
    if itemid in CHAIN_STEPS:
        first, k = CHAIN_STEPS[itemid]
        chain = coach.setdefault("chain", {})
        chain[str(first)] = max(chain.get(str(first), 0), k + 1)
    _save(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)
                  + ([{"uri": "/monthlypack", "body": monthly_list(st)}] if itemid in MONTHLY else [])})


def use_item(st, slot, coach, it, req):
    """/item/<_id>/use for a USE item (see ITEMS): its effect, one used up."""
    _, _, typ, eff, _ = ITEMS[it["itemid"]]
    if typ in ("ENHANCEMENT_BOOST", "LEAGUE_SIMULATION"):  # spent by the Upgrade tab / Liga's Simulasi, not by "Gunakan"
        return {"result": False, "reason": "ITEM_USE_ERROR"}
    out = {"result": True}
    if typ == "EP_LOTTERY":  # lower amounts more likely
        lo, hi = eff["ep"]
        out["ep"] = lo if lo == hi else max(lo, round(random.triangular(lo, hi, lo), -4))
        add_ep(st, out["ep"])
    elif typ == "ITEM_LOTTERY":
        prize = random.choices([p for _, p in eff["prizes"]], [w for w, _ in eff["prizes"]])[0]
        if isinstance(prize, tuple):
            out["ep"] = prize[1]
            add_ep(st, prize[1])
        else:
            inventory_add(coach, prize, 1)
            out["item"] = {"itemid": prize, "count": 1, "staticdata": item_def(prize)}
    elif typ == "COACHNAME_CHANGE":
        name = str(req.get("name") or "").strip()
        if not 2 <= len(name) <= 12:
            return {"result": False, "reason": "COACH_CREATION_ERROR_COACH_TOO_SHORT"}
        coach["name"] = name
    elif typ == "TEAM_CHANGE":
        teamid = int(req.get("teamid") or 0)
        if not roster(teamid)["team"]["players"]:
            return {"result": False, "reason": "ITEM_USE_ERROR"}
        coach["teamid"] = teamid
    elif typ == "PLAYER_EXP_CAPSULE":  # the players ExpCapsuleSelectingPage lists: below the max level, lv, season
        p = next((p for p in st["teams"][str(slot)]["players"] if iid(p) == str(req.get("targetid"))), None)
        level = player_levelinfo(p)["level"] if p else PLAYER_MAX_LEVEL
        if (level >= PLAYER_MAX_LEVEL or level > (eff.get("lv") or PLAYER_MAX_LEVEL)
                or eff.get("season") and p["spid"] // 1000000 != eff["season"]):
            return {"result": False, "reason": "ITEM_USE_ERROR"}
        gain_exp(p, eff["exp"], player_need, PLAYER_MAX_LEVEL)
    it["remains"] -= 1
    if not it["remains"]:
        coach["items"].remove(it)
    return out


def ep_item_use(item_id, query, body):
    """POST /item/<_id>/use: open one pack -> {result, player: {spid, grade, price}}; USE items
    see use_item."""
    st = _state(); slot = _default_slot(st); coach = my_coach(st); team = st["teams"][str(slot)]
    it = next((i for i in coach.get("items", []) if i["_id"] == item_id and i["remains"] > 0), None)
    req = json.loads(body or b"{}")
    if it is not None and it["itemid"] in ITEMS:
        out = use_item(st, slot, coach, it, req)
        if out["result"]:
            _save(st)
        return _json({**out, "resources": coach_me_resources(st, slot)})
    if it is None or it["itemid"] not in PACKS:
        return _json({"result": False, "reason": "INVALID_ITEM"})
    if len(team["players"]) >= MAX_PLAYERS:
        return _json({"result": False, "reason": "Exceed plyer limit"})  # client shows "squad full"
    pool = pack_pool(it["itemid"])
    draft = PACKS[it["itemid"]][1].get("draft")
    if draft:  # one of the cards picked on the draft screen, each as likely
        try:
            picks = sorted({int(s) for s in req.get("spids") or []})
        except (TypeError, ValueError):
            picks = []
        if len(picks) != draft or not set(picks) <= {s for s, _ in pool}:
            return _json({"result": False, "reason": "ITEM_USE_ERROR"})
        spid = random.choice(picks)
    else:
        spid = random.choices([s for s, _ in pool], [w for _, w in pool])[0]
    g = pack_grade(it["itemid"])
    p = add_player(team, spid, g)
    it["remains"] -= 1
    if not it["remains"]:
        coach["items"].remove(it)
    _save(st)
    return _json({"result": True, "player": {"_id": p["_id"], "spid": spid, "grade": g, "price": card_price(spid, g)},
                  "resources": coach_me_resources(st, slot)})


def ep_draftpack_players(itemid, n, query, body):
    """GET /item/draftpack/<itemid>/players/<n>: the draft pack's n most valuable cards
    [{spid, price}] (the client sets their grade itself)."""
    itemid = int(itemid)
    if not PACKS.get(itemid, ("", {}))[1].get("draft"):
        return _json([])
    g = pack_grades(itemid)[0][0]
    return _json([{"spid": s, "price": card_price(s, g)} for s in draft_top(itemid, int(n))])


def ep_transfer_price_default(grade, query, body):
    """POST /transfer/price/default/<grade> {spids}: Market prices of cards at that grade
    ({prices: [{spid, price}]}; the draft screen's search results outside its list)."""
    spids = []
    for s in json.loads(body or b"{}").get("spids") or []:
        try:
            spids.append(int(s))
        except (TypeError, ValueError):
            pass
    return _json({"prices": [{"spid": s, "price": card_price(s, int(grade))} for s in spids if on_market(s)]})


def ep_static_item(query, body):
    """POST /static/cache/item {itemids} -> {itemid: staticdata} (ItemUtil cache)."""
    ids = []
    for i in json.loads(body or b"{}").get("itemids") or []:
        try:
            ids.append(int(i))
        except (TypeError, ValueError):
            pass
    return _json({str(i): item_def(i) for i in ids if i in (EP_ITEM, ES_ITEM) or i in PACKS or i in ITEMS or i in PACKAGES})


# --------------------------------------------------------------------------- #
# Gudang (Item saya > Gudang, ItemDepotTabPage; issue #12): coach["depot"] holds stacks like
# coach["items"]. An Item saya tile (packs, USE items: GeneralInventoryTileItemRenderer
# .isMovableItem) posts /items/itemtodepot {moveitems: [id]}; a Gudang tile posts
# /item/depottoitem/<_id> {} (ItemUtil.checkMovableItemsToInventory checks for room first).
# Whole stacks move. On {result: true} the client GETs /item/depot (an array of coach_items
# entries) and shows DepotItemMoveCompletePopup; otherwise a dialog with `reason`.
# --------------------------------------------------------------------------- #
def stack_move(coach, item_id, src, dst):
    """Move stack item_id from coach[src] to coach[dst], joining a stack of the same item there."""
    it = next((i for i in coach.get(src, []) if i["_id"] == item_id and i["remains"] > 0), None)
    if it is None:
        return False
    coach[src].remove(it)
    same = next((i for i in coach.setdefault(dst, []) if i["itemid"] == it["itemid"]), None)
    if same is None:
        coach[dst].append(it)
    else:
        same["remains"] += it["remains"]
    return True


def depot_reply(st, ok):
    if not ok:  # nothing saved: a refused move changes nothing
        return _json({"result": False, "reason": "Item tidak ditemukan."})
    _save(st)
    slot = _default_slot(st)
    return _json({"result": True, "resources": coach_me_resources(st, slot)
                  + [{"uri": "/item/depot", "body": coach_items(st, slot, "depot")}]})


def ep_item_to_depot(query, body):
    """POST /items/itemtodepot {moveitems: [_id...]}: Item saya -> Gudang (the locker room ticket stays)."""
    st = _state(); coach = my_coach(st)
    moved = [stack_move(coach, str(i), "items", "depot") for i in json.loads(body or b"{}").get("moveitems") or []
             if str(i) != LR_TICKET_ITEM["_id"]]
    return depot_reply(st, moved and all(moved))


def ep_depot_to_item(item_id, query, body):
    """POST /item/depottoitem/<_id> {}: Gudang -> Item saya."""
    st = _state()
    return depot_reply(st, stack_move(my_coach(st), item_id, "depot", "items"))


def ep_item_depot(query, body):
    """GET /item/depot: the Gudang list."""
    st = _state()
    return _json(coach_items(st, _default_slot(st), "depot"))


# --------------------------------------------------------------------------- #
# Daily login reward: the first login of a day (WIB, at PUT /coach/<slot>/default) drops that
# day's reward into the Bag (Item saya > Items, ItemBagTabPage: GET /bag; "Terima" = POST
# /bag/<id>/unpack, "Terima semua" = POST /bag/unpackall {reqUnpackItems}). 7-day cycle on a
# consecutive-login streak; the table is gamedata/daily_rewards.json (admin page edits it).
# Bag entries are event packs (ItemUtil.isEventItempackData: no product, type "event",
# items [{itemid, count}] expanded via /static/cache/item, players [{spid, grade}]).
# --------------------------------------------------------------------------- #
DAILY_FILE = os.path.join(HERE, "gamedata", "daily_rewards.json")
DAILY_DEFAULT = [{"ep": 10000}, {"ep": 20000}, {"pack": 28007}, {"ep": 30000}, {"pack": 28006},
                 {"ep": 50000}, {"ep": 100000, "pack": 82214068}]  # day 1..7
WIB = 7 * 3600


def daily_table():
    try:
        with open(DAILY_FILE, encoding="utf-8") as f:
            return json.load(f) or DAILY_DEFAULT
    except (OSError, ValueError):
        return DAILY_DEFAULT


def today_wib(ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime((time.time() if ts is None else ts) + WIB))


def reward_items(reward):
    return ([{"itemid": EP_ITEM, "count": int(reward["ep"])}] if reward.get("ep") else []) + \
           ([{"itemid": int(reward["pack"]), "count": int(reward.get("count") or 1)}] if reward.get("pack") else [])


def bag_add(st, title, items=(), players=(), msg=""):
    entry = {"_id": new_iid(), "title": title, "msg": msg, "items": list(items), "players": list(players),
             "createdat": int(time.time())}
    my_coach(st).setdefault("bag", []).append(entry)
    return entry


def daily_login(st, now=None):
    """Grant today's reward once per WIB day; returns the new bag entry or None."""
    now = time.time() if now is None else now
    d = my_coach(st).setdefault("daily", {"last": "", "streak": 0, "total": 0})
    if d["last"] == today_wib(now):
        return None
    d["streak"] = d["streak"] + 1 if d["last"] == today_wib(now - 86400) else 1
    d["total"] += 1
    d["last"] = today_wib(now)
    table, n = daily_table(), d["streak"]
    return bag_add(st, f"Hadiah login harian - hari ke-{n}", reward_items(table[(n - 1) % len(table)]),
                   msg=f"Login {n} hari berturut-turut. Login lagi besok untuk hadiah hari ke-{n + 1}.")


def bag_list(st):
    out = []
    for e in my_coach(st).get("bag", []):
        icon = next((PACKS.get(i["itemid"], ("", {}))[1].get("icon", i["itemid"])
                     for i in e["items"] if i["itemid"] != EP_ITEM), EP_ITEM)
        # ShopItemDescription.MakeEventItemDesc tooltip: msg = text, date (W3C) = "Tanggal diterima"
        out.append({"_id": e["_id"], "id": e["_id"], "type": e.get("type", "event"), "title": e["title"],
                    "msg": e.get("msg") or "Hadiah dari server.", "date": w3c(e["createdat"]),
                    "items": e["items"], "players": e["players"], "bundleicon": icon})
    return out


def bag_apply(st, entry):
    """Credit a bag entry: EP, packs and items to Item saya, players to the club."""
    coach = my_coach(st); team = st["teams"][str(_default_slot(st))]
    for it in entry["items"]:
        if it["itemid"] == EP_ITEM:
            add_ep(st, it["count"])
        elif it["itemid"] in PACKS or it["itemid"] in ITEMS:
            inventory_add(coach, it["itemid"], it["count"])
    for p in entry["players"]:
        add_player(team, p["spid"], p.get("grade", 1))
    coach["bag"].remove(entry)


def bag_reply(st):
    return _json({"result": True, "overdueitems": [],
                  "resources": coach_me_resources(st, _default_slot(st)) + [{"uri": "/bag", "body": bag_list(st)}]})


def ep_bag_unpack(bid, query, body):
    """POST /bag/<id>/unpack: take one bag entry."""
    st = _state()
    entry = next((e for e in my_coach(st).get("bag", []) if e["_id"] == bid), None)
    if entry is None:
        return _json({"result": False, "reason": "ITEM_USE_ERROR"})
    if len(st["teams"][str(_default_slot(st))]["players"]) + len(entry["players"]) > MAX_PLAYERS:
        return _json({"result": False, "reason": "TRANSFERMARKET_FULLSLOT_DESC"})
    bag_apply(st, entry)
    _save(st)
    return bag_reply(st)


def ep_bag_unpackall(query, body):
    """POST /bag/unpackall {reqUnpackItems: [id...]}: take them all (club slots permitting)."""
    ids = set(map(str, json.loads(body or b"{}").get("reqUnpackItems") or []))
    st = _state(); team = st["teams"][str(_default_slot(st))]
    for e in [e for e in my_coach(st).get("bag", []) if e["_id"] in ids]:
        if len(team["players"]) + len(e["players"]) <= MAX_PLAYERS:
            bag_apply(st, e)
    _save(st)
    return bag_reply(st)


# Path-pattern routes (ids in the path); checked after the exact ENDPOINTS.
ROUTES = [
    (re.compile(r"/item/(\w+)/use"), ep_item_use),
    (re.compile(r"/item/draftpack/(\d+)/players/(\d+)"), ep_draftpack_players),
    (re.compile(r"/transfer/price/default/(\d+)"), ep_transfer_price_default),
    (re.compile(r"/item/depottoitem/(\w+)"), ep_depot_to_item),
    (re.compile(r"/bag/(\w+)/unpack"), ep_bag_unpack),
    (re.compile(r"/coach/(\w+)/postponed"), ep_coach_postponed),
    (re.compile(r"/stadium/(\d+)"), ep_stadium),
    (re.compile(r"/lockerroom/(\w+)/itemset"), ep_lockerroom_itemset),
    (re.compile(r"/lockerroom/(\w+)/jersey"), ep_lockerroom_jersey),
    (re.compile(r"/static/info/authentic/team/(licensed|all)/(\d+)"), ep_authentic_team),
    (re.compile(r"/static/info/team/summary/(\d+)"), ep_team_summary),
    (re.compile(r"/player/(\w+)/move/(firstteam|secondteam)"), ep_player_move),
    (re.compile(r"/player/(\w+)/enhance/(\w+)/preview"), ep_enhance_preview),
    (re.compile(r"/player/(\w+)/enhance2\.5/(\w+)/preview/(\d)/(-?\d+)/(-?\d+)"), ep_enhance25_preview),
    (re.compile(r"/player/(\w+)/enhance2\.5/(\w+)/(\d)/(-?\d+)/(-?\d+)"), ep_enhance25),
    (re.compile(r"/player/(\w+)/enhance/(\w+)(?:/(-?\w+)/(-?\w+))?"), ep_enhance),
    (re.compile(r"/transfer/top/50(?:/position/(\w+))?"), ep_transfer_top),
    (re.compile(r"/transfer/search/(\d+)"), ep_transfer_search),
    (re.compile(r"/transfer/purchase/(\d+)/(\d+)/(\d+)/purchase"), ep_transfer_purchase),
    (re.compile(r"/transfer/price/(\d+)/(\d+)"), ep_transfer_price),
    (re.compile(r"/transfer/my/offer/completed/(\w+)(?:/(\w+))?"), ep_offer_collect),
    (re.compile(r"/match/([0-9a-f]+)/player/ready"), ep_match_player_ready),
    (re.compile(r"/match/([0-9a-f]+)/side/(\w+)/ready"), ep_match_ready),
    (re.compile(r"/match/([0-9a-f]+)/side/(\w+)/squad"), ep_match_squad),
    (re.compile(r"/match/([0-9a-f]+)/end"), ep_match_end),
    (re.compile(r"/match/([0-9a-f]+)/gamesettings"), ep_match_gamesettings),
    # StaticData bescripts go to native as-is (BeginnersGuideManager.startLeagueTutorial ->
    # ApplyCampaignScript); "{}" for an unknown GET crashed the script parser. Ones without a
    # responses/ file get camera_controller's do-nothing script (no tutorial prompts, no crash).
    (re.compile(r"/static/bescript/(\w+)"), lambda name, q, b: from_file("/static/bescript/camera_controller")),
    # GET /game/inweburl/<notice|webevent|cookie|vip_purchase|...> {url}: StartupNoticeScreen
    # .onReceivedNoticeUrl hands url straight to native LoadWebAddress, and a missing one (the
    # old "{}") is a NULL string there -> crash on the manager select screen whenever the notice
    # popup opens. Garena's pages are gone: an empty page.
    (re.compile(r"/game/inweburl/(\w+)"), lambda name, q, b: _json({"result": True, "url": "about:blank"})),
    (re.compile(r"/match/([0-9a-f]{24})"), ep_match_get),
    (re.compile(r"/league2/sponsor/(\d+)"), ep_l2_sponsor),
    (re.compile(r"/cup/([0-9a-f]{24})/match"), ep_cup_match),
    (re.compile(r"/cup/([0-9a-f]{24})/next"), ep_cup_next),
    (re.compile(r"/cup/([0-9a-f]{24})/(?:resume|test)"), ep_cup_resume),
    (re.compile(r"/cup/([0-9a-f]{24})/leave"), ep_cup_leave),
    (re.compile(r"/cup/([0-9a-f]{24})"), lambda cupid, q, b: _json((_state().get("cups") or {}).get(cupid, {}))),
]


def route(path):
    for pat, fn in ROUTES:
        m = pat.fullmatch(path)
        if m:
            return lambda q, b, g=m.groups(): fn(*g, q, b)


ENDPOINTS = {
    "/info/server/config": ep_server_config,
    "/info/server/locale": ep_locale,
    "/info/server/time": ep_server_time,
    "/game/my/ipaddress": ep_my_ip,
    "/publisher/garena/sign": ep_garena_sign,
    "/publisher/nexon/2ndauth": ep_nexon_2ndauth,
    "/telemetry/gameconnection": ep_telemetry,
    "/shop/cash/charge/url": ep_shop_url,
    "/shop/cash/history/url": ep_shop_url,
}
ENDPOINTS["/coaches"] = ep_coaches
ENDPOINTS["/coach/me"] = ep_coach_me
ENDPOINTS["/coach/me/onready"] = ep_coach_onready
for _slot in (0, 1):  # two coach slots
    ENDPOINTS[f"/coach/{_slot}"] = lambda q, b, s=_slot: ep_create_coach(s, q, b)
    ENDPOINTS[f"/coach/{_slot}/new/step/3"] = lambda q, b, s=_slot: ep_new_team(s, q, b)
    ENDPOINTS[f"/coach/{_slot}/default"] = lambda q, b, s=_slot: ep_default_coach(s, q, b)
ENDPOINTS["/account"] = ep_account
ENDPOINTS["/account/option"] = ep_account_option
ENDPOINTS["/coach/me/squad"] = ep_coach_squad
ENDPOINTS["/match/campaign"] = ep_match_campaign
ENDPOINTS["/game/my/tactic/all"] = ep_tactic_all
ENDPOINTS["/game/my/team/captain"] = lambda q, b: ep_team_role(None, q, b)
for _i in range(KICKERS):
    ENDPOINTS[f"/game/my/team/kickers/{_i}"] = lambda q, b, i=_i: ep_team_role(i, q, b)
for _i in range(TACTIC_SLOTS):
    ENDPOINTS[f"/game/my/tactic/{_i}"] = lambda q, b, i=_i: ep_tactic(i, q, b)
ENDPOINTS.update({
    "/league2/me": ep_l2_me, "/league2/reward": ep_l2_reward, "/league2/calendar": ep_l2_calendar,
    "/league2/match": ep_l2_match, "/league2/match/sim": lambda q, b: ep_l2_match(q, b, sim=True),
    "/league2/sleep": ep_l2_sleep, "/league2/end": ep_l2_end, "/league2/abandon": ep_l2_finish,
    "/league2/back": ep_telemetry, "/static/db/SORTTEAM": ep_sortteam,
    "/static/db/SORTNATION": ep_sortnation, "/static/db/SORTLEAGUE": ep_sortleague,
    "/league2/sponsor/achievement": ep_l2_achievement,
    # Rekor liga tabs: Rekorku (player records) and Rekor gabungan (best XI, stat leaders); the
    # league's own cup (cupinfo) is never entered, so its records stay empty
    "/league2/history/players/league": ep_l2_history_players, "/league2/leader/league": ep_l2_leaders,
    "/league2/history/players/cup": lambda q, b: _json([]),
    "/league2/leader/cup": lambda q, b: _json({k: [] for k in (*LINES, "ratings", "goals", "assists", "tackles", "passes", "saves")}),
    "/cup/list": ep_cup_list, "/cup/record": ep_cup_record, "/cup/new": ep_cup_new,
    "/transfer/offer": ep_transfer_offer, "/transfer/my/offer/list": lambda q, b: _json(offer_list(_state())),
    "/transfer/my/boostfactor": lambda q, b: _json(NO_BOOST),
    "/players/trade/proposal": ep_trade_proposal, "/players/trade/contract": ep_trade_contract,
    "/players/trade2/proposal": lambda q, b: trade_proposal(b, trade2_props), "/players/trade2/contract": ep_trade_contract,
    "/players/trade2/info": ep_trade2_info, "/static/db/TRADE": lambda q, b: _json(TRADE2_TABLE),
    "/static/cache/TRADE_SPECIALPLAYERS": lambda q, b: _json(trade2_special()),
    "/account/trade2/usage": lambda q, b: _json({"result": True, "usedcount": 0, "maxcount": 0, "remainsec": 0}),
    "/trade3/contract": ep_trade_contract, "/trade3/proposal": ep_trade3_proposal,
    "/trade3/staticvalues": lambda q, b: _json(TRADE3_STATIC), "/trade3/info": ep_trade3_info,
    "/trade3/notification": lambda q, b: _json({"result": True}),
    "/static/db/PLAYERTRADE": lambda q, b: _json({"playergrade": {str(s): trade_grades(s) for s in range(2, 101)}}),
    "/static/db/EXPPLAYER": lambda q, b: _json(EXPPLAYER), "/static/db/EXPCOACH": lambda q, b: _json(EXPCOACH),
    "/static/db/PE2STATICVALUES": lambda q, b: _json(PE2STATICVALUES),
    "/static/db/LOCKERROOMITEM": lambda q, b: _json(lockerroom_items()),
    "/player/enhance2.5/restore": ep_enhance25_restore,
    "/events": lambda q, b: _json({"events": [ENHANCE_EVENT]}),
    "/static/db/STATICVALUES/max_coachlevel": lambda q, b: _json(COACH_MAX_LEVEL),
    "/static/info/teamcolor": ep_teamcolor,
    "/shop/list": lambda q, b: _json(shop_list(_state())), "/shop/list/STSHOP": ep_stshop,
    "/specifictarget": ep_specifictarget, "/monthlypack": ep_monthlypack,
    "/shop/purchase": ep_shop_purchase, "/static/cache/item": ep_static_item,
    "/bag": lambda q, b: _json(bag_list(_state())), "/bag/unpackall": ep_bag_unpackall,
    "/items/itemtodepot": ep_item_to_depot, "/item/depot": ep_item_depot,
    "/players/trade/proposal/resend": lambda q, b: _json({"result": False, "reason": "NOT_SUPPORTED_REQUEST"}),
})


RESPONSES = os.path.join(HERE, "responses")


def from_file(path):
    """responses/<path, '/' -> '_'>.json overrides the handler; re-read every request so
    response shapes can be iterated against the live client without a restart."""
    f = os.path.join(RESPONSES, path.strip("/").replace("/", "_") + ".json")
    if os.path.isfile(f):
        with open(f, "rb") as fh:
            return ("application/json", fh.read())


class H(http.server.BaseHTTPRequestHandler):
    def _log(self, body):
        line = (f"{time.strftime('%H:%M:%S')} {self.command} {self.path} "
                f"from {self.client_address[0]} host={self.headers.get('Host')} "
                f"len={len(body)} body={body[:2000]!r}")  # UI error stack traces run long
        print(line, flush=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _respond(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if body[:2] == b"\x1f\x8b":  # the client gzips larger bodies (telemetry, /coach/me/squad)
            body = gzip.decompress(body)
        self._log(body)
        path = self.path.split("?")[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        # Unknown GETs get {}: a wrong shape in AS3 only raises a logged UI error, but []
        # where native code expects an object crashes the client (seen with
        # /static/db/PLAYER_EXTRA_GROWTH), and tables are id->row maps whose values get
        # iterated, so a stray "result": true becomes a bogus row. List endpoints get a
        # responses/ file with []. Unknown POSTs get {"result": true}.
        fallback = ep_telemetry if self.command == "POST" else ep_empty
        if path.startswith("/" + CDN_PREFIX):
            hit = cdn_file(path[len(CDN_PREFIX) + 1:])
            if hit is None:
                self.send_error(404)
                return
            ctype, data = hit
        else:
            try:
                with STATE_LOCK:
                    ctype, data = from_file(path) or (ENDPOINTS.get(path) or route(path) or fallback)(query, body)
            except Exception:
                # an empty reply is a curl error and the client quits (CLIENT_CLOSE); answer
                # something parseable and keep the traceback in the log instead
                import traceback
                self._log(traceback.format_exc().encode())
                ctype, data = _json({"result": False})
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _respond
    do_POST = _respond
    do_PUT = _respond  # /game/my/ipaddress is a real PUT; 501 there made the client quit
    do_DELETE = _respond

    def log_message(self, *a):
        pass  # we do our own logging


if __name__ == "__main__":
    # Windows SO_REUSEADDR lets a second copy bind the same port and split the client's
    # requests between two servers; refuse instead (a second play.bat then just fails)
    http.server.ThreadingHTTPServer.allow_reuse_address = os.name != "nt"
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H)
    if TLS:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT)
        # Lazy handshake: a failed handshake (e.g. client rejects the cert) then
        # surfaces as a logged traceback in the handler thread instead of vanishing.
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
    print(f"http config stub on 0.0.0.0:{PORT}{' (https)' if TLS else ''}, log -> {LOG}", flush=True)
    if not os.path.isdir(os.path.join(ASSETS, "externalAssets")):
        print(f"WARNING: no client cache at {ASSETS}: crests, faces and shop images will show the "
              "game's defaults. Set FO3_GAME to your FO3 ID folder (or FO3_ASSETS).", flush=True)
    admin_port = int(os.environ.get("FO3_ADMIN_PORT", "8088"))  # 0 = no admin page
    if admin_port:
        import admin
        admin.start(sys.modules[__name__], admin_port)
        print(f"admin page on http://127.0.0.1:{admin_port}/", flush=True)
    threading.Thread(target=warm_packs, daemon=True, name="packs").start()
    srv.serve_forever()
