"""Self-check for the Single > Liga server logic in http_config.py (no client needed).

    python test_league.py

Runs a whole season through the handlers against a temporary copy of gamedata/state.json.
"""
import copy, json, os, shutil, sys, tempfile, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import http_config as hc


def body(resp):
    return json.loads(resp[1])


def main():
    # schedule: every club once per round, every pair twice, once at each ground
    teams = list(range(1, 11))
    rounds = [hc.league_round(teams, r) for r in range(2 * (len(teams) - 1))]
    for pairs in rounds:
        assert sorted(t for p in pairs for t in p) == teams, pairs
    meet = Counter(frozenset(p) for pairs in rounds for p in pairs)
    assert set(meet.values()) == {2} and len(meet) == 45, meet
    homes = Counter(p for pairs in rounds for p in pairs)
    assert set(homes.values()) == {1}, [p for p, n in homes.items() if n != 1]

    tmp = tempfile.mkdtemp()
    try:
        hc.STATE = os.path.join(tmp, "state.json")
        hc.SHOP_FILE = os.path.join(tmp, "shop.json"); hc.apply_shop({})  # the built-in Shop, not the live edits
        hc.MATCH_REWARD_FILE = os.path.join(tmp, "match_rewards.json")  # default match rewards; admin test writes here
        # a fresh account through the client's club creation (the live state may hold no manager)
        hc._save({"coaches": [], "defaultcoachid": "", "teams": {}})
        with open(os.path.join(hc.RESPONSES, "static_info_authentic_team_all_241.json")) as f:
            spids = [p["spid"] for p in json.load(f)["team"]["players"]]
        assert body(hc.ENDPOINTS["/coach/0/new/step/3"]("", json.dumps({"id": 241, "spids": spids}).encode()))["result"]
        assert body(hc.ENDPOINTS["/coach/0"]("", json.dumps({"id": 241, "coachName": "Tester"}).encode()))["result"]
        assert body(hc.ENDPOINTS["/coach/0/default"]("", b""))["result"]
        shown = hc.coach_me(hc._state(), 0)["team"]  # the client saves the squad it shows (11 + 7 subs)
        hc.ENDPOINTS["/coach/me/squad"]("", json.dumps({k: shown[k] for k in ("squad", "kickers", "captain")}).encode())
        st = hc._state()
        assert len(st["teams"]["0"]["squad"]["positions"]) == 18
        me = hc.my_teamid(st)
        # a new club's cards are +0: no market value, not sellable
        assert all(p["grade"] == 0 == p["price"] for p in hc.coach_me(st, 0)["team"]["players"])
        # levels start at 1; exp tables: player LV.1-23 (24 rows), coach 1-100
        assert hc.coach_me(st, 0)["levelinfo"] == {"level": 1, "exp": 0, "to": hc.coach_need(1)}
        assert len(body(hc.ENDPOINTS["/static/db/EXPPLAYER"]("", b""))) == hc.PLAYER_MAX_LEVEL + 1
        assert body(hc.ENDPOINTS["/static/db/STATICVALUES/max_coachlevel"]("", b"")) == hc.COACH_MAX_LEVEL
        # Tim > Formasi: the club's own formation first (Barcelona has none: 4-4-2(1)), then the
        # 33 common ones, each with 11 positions + offsets (needs the client's data_0.big)
        forms = hc.coach_me(st, 0)["team"]["formations"]
        if hc.formation_table()["common"]:
            assert len(forms) == 33 and forms[0]["formationname"] == "4-4-2(1)"
            assert all(len(f["positions"]) == 11 == len(f["offsets"]) and f["positions"][0] == 0 for f in forms)
            assert hc.coach_me(st, 0)["team"]["squad"]["formation"] == forms[0]["formationid"]
        # team color: feature on, the colors table, and the XI's active colors (a fresh Barcelona
        # XI = 11 Barcelona players: the top club tier); AI match sides get none
        # Opsi > Kontrol: /account always has a full controlOption (none = key changes never
        # apply or save, {} crashes the client); a saved one comes back, an incomplete one is ignored
        acc_ctl = lambda: body(hc.ENDPOINTS["/account"]("", b""))["option"]["controlOption"]
        assert acc_ctl() == hc.CONTROL_DEFAULTS and len(acc_ctl()) == 35
        # Controller 1 = the Gamepad tab (Joy* lists); the next login's OptionManager.initialize
        # then starts with the pad (keyboardControl = Controller == 0)
        mine = dict(hc.CONTROL_DEFAULTS, Controller=1, Type=2, JoyAttType3=[3, 4, 2, 1, 5, 7, 6, 8])
        save_opt = lambda o: hc.ENDPOINTS["/account/option"]("", json.dumps(o).encode())
        cam = {"Camera": 2, "CamDetail": 0}  # Co-op (F5 in a match)
        r = body(save_opt({"soundOption": {"BGM": 3}, "controlOption": mine, "cameraOption": cam}))
        # the reply carries the saved options: AccountCommand.saveGameOption reads resources[0].body
        # (OptionManager's backup for every zone change; none = login options back in a match, issue #21)
        opt = r["resources"][0]["body"]
        assert opt == body(hc.ENDPOINTS["/account"]("", b""))["option"] and opt["controlOption"] == mine
        assert opt["cameraOption"] == {**hc.CAMERA_DEFAULTS, **cam}
        # Opsi > Kamera: every gauge has a value (none = empty, could not be stepped, issue #24); a
        # null saved while one was NaN gets the default
        save_opt({"cameraOption": {"Camera": 1, "CamDetail": 1, "CamHeight": None, "CamZoom": 14}})
        assert body(hc.ENDPOINTS["/account"]("", b""))["option"]["cameraOption"] == dict(
            hc.CAMERA_DEFAULTS, Camera=1, CamDetail=1, CamHeight=10, CamZoom=14)
        save_opt({"soundOption": {"BGM": 4}, "controlOption": {}})  # e.g. leaving a match
        assert acc_ctl() == mine and body(hc.ENDPOINTS["/account"]("", b""))["option"]["soundOption"]["BGM"] == 4
        save_opt({"soundOption": {"BGM": 10}, "controlOption": hc.CONTROL_DEFAULTS})
        assert "teamcolor" in body(hc.ENDPOINTS["/account"]("", b""))["features"]
        tc = body(hc.ENDPOINTS["/static/info/teamcolor"]("", b""))
        assert {hc.TC_CLUB, hc.TC_NATION} <= {c["teamcolorid"] for c in tc["teamColors"]}
        assert set(tc["teamColorSpecials"]) == {str(c["teamid"]) for c in tc["teamColors"] if c["type"] == "special"}
        active = hc.coach_me(st, 0)["team"]["teamcolors"]
        assert {"teamcolorid": hc.TC_CLUB, "boostindex": 3, "teamid": 241} in active, active
        # a season (special) color's teamid must be a string: native reads it with asCString at
        # half time (a number crashed every second half)
        assert all(isinstance(c["teamid"], str) for c in tc["teamColors"] if c["type"] == "special")
        kind = {c["teamcolorid"]: c["type"] for c in tc["teamColors"]}
        assert len(kind) == len(tc["teamColors"])  # unique ids
        assert all(isinstance(c["teamid"], str) == (kind[c["teamcolorid"]] == "special") for c in active), active
        # the client's named colors (user: "pakai semua team color yang belum masuk"): a Barcelona XI
        # also meets "Barcelona" (TEAM2: Single team's tiers + MF agility +3) and "Spanyol" for its
        # Spaniards; every color the client names is sent except the left-out ones
        named = {c["teamcolorid"]: c for c in tc["teamColors"]}
        assert {"teamcolorid": 2, "boostindex": 3, "teamid": 241} in active, active
        assert named[2]["boostgroups"][3]["boosts"] == [{"type": "ovr", "amount": 4}, {"type": "agility", "amount": 3, "target": "mf"}]
        assert named[50091]["name"] == "TEAMCOLOR_ATTRIBUTES_TEAM18" and named[50091]["boostgroups"][2]["boosts"][0]["amount"] == 5
        assert {1, 16, 101, 130, 20, 39, 20002, 20030, 20043, 20071, 40001, 3064} <= set(named)
        assert named[50093]["name"] == "TEAMCOLOR_ATTRIBUTES_TEAM100"  # World Legend: a season color, the client's name
        msn = named[20002]
        assert [(g["count_min"], g["count_max"]) for g in msn["boostgroups"]] == [(3, 11)]
        assert all(c["teamcolorid"] < 70000 and c["teamcolorid"] not in (20055, 20056, 20057, 20058) for c in tc["teamColors"])
        assert hc.match_side(st["teams"]["0"], 241, user={"id": "me"})["team"]["teamcolors"] == active
        assert hc.match_side(st["teams"]["0"], 241)["team"]["teamcolors"] == []
        # upgrade colors (type "grade"): 7 starters at +5 or higher meet +2 (index 1) and +5 (index 1)
        grades = [c for c in tc["teamColors"] if c["type"] == "grade"]
        assert [(c["grade"], c["name"]) for c in grades] == [(g, n) for _, g, n, _ in hc.TC_GRADE]
        assert not {c["teamcolorid"] for c in grades} & {c["teamcolorid"] for c in active}  # +0 club cards
        t0 = json.loads(json.dumps(st["teams"]["0"]))
        xi_ids = [str(s.get("id") or s["spid"]) for s in t0["squad"]["positions"] if s["pos"] < hc.POS_SUB]
        for p in t0["players"]:
            p["grade"] = 6 if hc.iid(p) in xi_ids[:7] else p.get("grade", 0)
        got = {c["teamcolorid"]: c["boostindex"] for c in hc.active_teamcolors(hc.owned_team(t0)) if c["teamid"] == -1}
        assert got == {10002: 1, 10005: 1}, got
        # single-grade colors need all 11 starters: the whole XI at +8 meets "+3 club" … "+8 Golden passion"
        for p in t0["players"]:
            p["grade"] = 8 if hc.iid(p) in xi_ids else p.get("grade", 0)
        got = {c["teamcolorid"]: c["boostindex"] for c in hc.active_teamcolors(hc.owned_team(t0)) if c["teamid"] == -1}
        assert got == {10002: 2, 10005: 2, 10008: 2, **{10100 + g: 0 for g in range(3, 9)}}, got
        # issue #18: summary.ovr FW/MF/DF = the average of the ratings the squad list shows (rating
        # at the slot on stats + grade boost + level - 1, plus the team color boosts)
        tm = hc.owned_team(t0); tm["teamcolors"] = hc.active_teamcolors(tm)
        shown, bare = hc.xi_ratings(tm), hc.xi_ratings(dict(tm, teamcolors=[]))
        pos = {s["id"]: s["pos"] for s in tm["squad"]["positions"] if s["pos"] < hc.POS_SUB}
        summ = hc.team_summary(tm, 241)["ovr"]
        for k, r in hc.LINES.items():
            v = [shown[i] for i, p in pos.items() if p in r]
            assert k == "GK" or summ[k] == round(sum(v) / len(v)), (k, summ, v)
        card = {p["id"]: p for p in tm["players"]}
        gk = next(i for i, p in pos.items() if p == 0)
        assert bare[gk] == hc.card_ovr(card[gk]["spid"]) + hc.GRADE_BOOST[8] + card[gk]["levelinfo"]["level"] - 1
        assert all(shown[i] > bare[i] for i in pos), (shown, bare)  # club + grade colors
        res = next(p for p in st["teams"]["0"]["players"] if not hc.in_squad(st["teams"]["0"], p))
        assert not body(hc.ENDPOINTS["/transfer/offer"]("", json.dumps({"playerobjectid": hc.iid(res), "price": 1000}).encode()))["result"]
        # club picker ("Tim lain"): nation -> league -> club lists agree; a club without a starter
        # file (Man City) gets its squad built on the fly; starter files carry name id + stars
        nations, leagues = (body(hc.ENDPOINTS[f"/static/db/{t}"]("", b"")) for t in ("SORTNATION", "SORTLEAGUE"))
        clubs = body(hc.ENDPOINTS["/static/db/SORTTEAM"]("", b""))
        assert nations and all(clubs[str(lg)] for n in nations for lg in leagues[str(n)])
        city = body(hc.route("/static/info/authentic/team/licensed/10")("", b""))
        assert city["teamid"] == 10 == city["summary"]["id"] and len(city["team"]["squad"]["positions"]) == 11
        assert city["team"]["captain"] in {p["id"] for p in city["team"]["players"]}
        assert hc.roster(243)["summary"]["teamgrade"] == 5.0 and hc.roster(243)["summary"]["id"] == 243
        # national teams = their players' nationalteamid (most are at clubs): Italy (1343) is in the
        # International league with Italians only (issue #24); that nation stays last in the picker
        intl = clubs[str(hc.gen_teams.NATIONAL_LEAGUE)]
        assert 1343 in intl and len(intl) >= 40 and -1 not in intl
        assert str(hc.gen_teams.NATIONAL_LEAGUE) in {str(lg) for lg in leagues[str(nations[-1])]}
        ita = hc.roster(1343)
        assert ita["summary"]["league"]["id"] == 78 and ita["summary"]["nation"]["id"] == 27
        with hc.closing(hc._db()) as c:
            ita_nat = {r[0] for r in c.execute(f"SELECT nationality FROM players WHERE spid IN ({','.join(str(p['spid']) for p in ita['team']['players'])})")}
        assert ita_nat == {27} and len(ita["team"]["players"]) >= 18
        assert not hc.roster(-1)["team"]["players"] and not hc.roster(0)["team"]["players"]  # nationalteamid -1 = none

        assert "league" not in body(hc.ep_l2_me("", b""))  # -> creation screen
        offer = body(hc.route("/league2/sponsor/12")("", b"{}"))
        assert offer["result"] and len(offer["sponsors"]) == 3
        created = body(hc.ep_l2_calendar("", json.dumps({"difficulty": 12, "sponsor": "1"}).encode()))
        league = created["resources"][0]["body"]["league"]
        assert league["teams"][0] == me and len(league["teams"]) == hc.LEAGUE_SIZE

        # Simulasi needs a League Simulation coupon (item 2001, type LEAGUE_SIMULATION: the calendar
        # tab's Simulasi button counts them; user: "item untuk League Simulation, jadi tanpa main
        # league langsung hasil"), one per simulated match
        coupons = lambda: sum(i["remains"] for i in hc.coach_me(hc._state(), hc._default_slot(hc._state()))["items"]
                              if i["staticdata"]["type"] == "LEAGUE_SIMULATION")
        h1, a1 = next(p for p in hc.league_round(league["teams"], 1) if me in p)
        req1 = json.dumps({"matchtype": "league", "playtype": "nrm", "round": 1, "home": h1, "away": a1}).encode()
        assert coupons() == 0 and not body(hc.ep_l2_match("", req1, sim=True))["result"]  # none: refused
        st = hc._state(); hc.inventory_add(hc.my_coach(st), hc.SIM_COUPON, (league["maxround"] + 1) // 2); hc._save(st)
        for rnd in range(league["maxround"] + 1):
            home, away = next(p for p in hc.league_round(league["teams"], rnd) if me in p)
            req = json.dumps({"matchtype": "league", "playtype": "nrm", "round": rnd, "home": home, "away": away}).encode()
            if rnd % 2:  # simulate
                n0 = coupons()
                r = body(hc.ep_l2_match("", req, sim=True))
                assert r["result"] and coupons() == n0 - 1 and any(x["uri"] == "/coach/me" for x in r["resources"])
                # the simulation screen plays eventlist (LeagueCupController: ON_SIMULATED with
                # body.eventlist); its GOAL_EVENTs make the score it shows, so they match the result
                ev, g = r["eventlist"], r["score"]
                mine_g, opp_g = (g["home"], g["away"]) if home == me else (g["away"], g["home"])
                assert [sum(e["event"] == "GOAL_EVENT" and e["team"] == t for e in ev) for t in (0, 1)] == [mine_g, opp_g], (ev, g)
                assert [e["time"] for e in ev] == sorted(e["time"] for e in ev) and all(1 <= e["time"] <= 90 for e in ev)
                sim = r["resources"][0]["body"]["side"]
                xi = [{int(p["spid"]) for p in sim[s]["team"]["squad"]["positions"] if p["pos"] < hc.POS_SUB} for s in ("left", "right")]
                assert all(e["player"] in xi[e["team"]] for e in ev), ev
                # the result screen after it (PostMatchResultDefaultScene.onResultReceived) reads
                # match.result like the report a played match posts at /end; it was blank
                res = r["resources"][0]["body"]["result"]
                side = "home" if home == me else "away"
                assert res["myTeam"] == side and res["opponentTeam"] == ("away" if side == "home" else "home")
                assert (res["home"]["score"], res["away"]["score"]) == (g["home"], g["away"]) and res["home"]["id"] == home
                for s, t in ((res["myTeam"], 0), (res["opponentTeam"], 1)):
                    assert len(res[s]["players"]) == 11 and sum(p["goals"] for p in res[s]["players"]) == res[s]["score"]
                    # the card's spid: the labels show its season (issue #26)
                    assert {p["spid"] for p in res[s]["players"]} == xi[t]
                    # each at his squad position on the result screen's pitch, not all at the goal (issue #26)
                    slots = [p["pos"] for p in sim[("left", "right")[t]]["team"]["squad"]["positions"] if p["pos"] < hc.POS_SUB]
                    assert [p["role"] for p in res[s]["players"]] == slots and slots.count(0) == 1
                assert res["motm"]["team"] in ("home", "away") and res["home"]["possession"]["total"] + res["away"]["possession"]["total"] == 100
                # then the reward screen (PostMatchRewardDefaultScene) reads match.reward like after a
                # played match: player EXP, manager EXP, EP (it was empty and the flow stopped there)
                rw = r["resources"][0]["body"]["reward"]
                assert rw["coach"]["reward"]["total"] > 0 and rw["money"]["reward"]["total"] > 0 and len(rw["players"]) == 11
                assert "pending" not in hc._state()["league2"]  # the round is played: no /end can play it again
            else:  # play: create, ready, end 2-1 for the home side
                m = body(hc.ep_l2_match("", req))["resources"][0]["body"]
                assert m["type"] == "League_2_league" and m["stage"] == "created"
                assert m["leagueparam"]["matchtype"] == "league" and m["side"]["left"]["ready"] is False
                for stage, nxt in (("created", "squad"), ("squad", "setting")):
                    pr = body(hc.route(f"/match/{m['id']}/player/ready")("", json.dumps({"ready": True, "stage": stage}).encode()))
                    assert pr["resources"][0]["body"]["stage"] == nxt, pr
                # pre-match squad screen (issue #16): it needs the formation list and each player's
                # stamina; a sub swapped in comes back in the match resource and stays in my club
                left = m["side"]["left"]["team"]
                assert left["formations"] and all(p["stamina"] == 1 for p in left["players"])
                sq = json.loads(json.dumps(left["squad"]))
                a = next(p for p in sq["positions"] if 0 < p["pos"] < hc.POS_SUB)
                b = next(p for p in sq["positions"] if p["pos"] == hc.POS_SUB)
                a["id"], b["id"] = b["id"], a["id"]  # b now holds the benched starter
                put = lambda s, q: body(hc.route(f"/match/{m['id']}/side/{s}/squad")("", json.dumps(
                    {"squad": q, "kickers": left["kickers"], "captain": left["captain"], "_method": "PUT"}).encode()))
                r = put("left", sq)
                xi = lambda ps: {p["id"] for p in ps if p["pos"] < hc.POS_SUB}
                assert r["result"] and xi(r["resources"][0]["body"]["side"]["left"]["team"]["squad"]["positions"]) == xi(sq["positions"])
                assert b["id"] not in xi(hc.coach_me(hc._state(), 0)["team"]["squad"]["positions"])
                assert put("right", sq)["result"] is False  # the AI side
                assert put("left", dict(sq, positions=sq["positions"][:5]))["result"] is False  # no XI: kept
                assert xi(hc._state()["match"]["side"]["left"]["team"]["squad"]["positions"]) == xi(sq["positions"])
                rd = body(hc.route(f"/match/{m['id']}/side/left/ready")("", b'{"ready": true, "stage": "setting"}'))
                assert rd["resources"][0]["body"]["stage"] == "playing"
                stats = {"home": {"id": home, "score": 2}, "away": {"id": away, "score": 1}}
                stats.update(myTeam="home" if home == me else "away", opponentTeam="away" if home == me else "home")
                cm = hc.coach_me(hc._state(), hc._default_slot(hc._state()))
                ep0, lv0 = cm["money"]["ep"], cm["levelinfo"]
                xi = [p for p in cm["team"]["squad"]["positions"] if p["pos"] < hc.POS_SUB]
                # in-match player ids are the card's player id (spid % 1e6); the game sends role 0
                # for everyone (issue #26), the server takes it from the squad slot
                stats[stats["myTeam"]]["players"] = [{"spid": int(p["spid"]) % 1000000, "goals": int(i == 0), "rating": 7,
                                                      "passes": [3, 4], "tackles": [1, 2], "role": 0} for i, p in enumerate(xi)]
                stats[stats["myTeam"]]["reserved"] = [{"id": "1", "rating": 0}]
                stats["motm"] = {"team": stats["myTeam"], "spid": int(xi[1]["spid"]) % 1000000, "rating": 9}
                items0 = {i["itemid"]: i["remains"] for i in hc.my_coach(hc._state()).get("items", [])}
                r = body(hc.route(f"/match/{m['id']}/end")("", json.dumps(stats).encode()))
                body(hc.route(f"/match/{m['id']}/end")("", json.dumps(stats).encode()))  # a resend credits nothing
                done = r["resources"][0]["body"]["result"]
                roles = [p["role"] for p in done[stats["myTeam"]]["players"]]
                assert roles == [p["pos"] for p in xi], roles
                # the game reports player ids; the result carries the cards' spids (season labels)
                assert [p["spid"] for p in done[stats["myTeam"]]["players"]] == [int(p["spid"]) for p in xi]
                assert done["motm"]["spid"] == int(xi[1]["spid"])
                # reward card (issue #26): 3 cards, the first is mine and credited once
                rw0 = r["resources"][0]["body"]["reward"]
                cards = rw0["extra"]["availables"]
                assert len(cards) == 3 and rw0["extra"]["selected"] == rw0["selected"] == {"normal": [0]}
                assert all(c["staticdata"]["unit"] in ("EP", "COUNT") and c["count"] > 0 for c in cards)
                card_ep = cards[0]["count"] if cards[0]["itemid"] == hc.EP_ITEM else 0
                assert hc.coach_me(hc._state(), hc._default_slot(hc._state()))["money"]["ep"] == ep0 + (2000 if home == me else 500) + card_ep
                if not card_ep:
                    items = {i["itemid"]: i["remains"] for i in hc.my_coach(hc._state())["items"]}
                    assert items[cards[0]["itemid"]] == items0.get(cards[0]["itemid"], 0) + 1
                mine = next(x for x in r["leagueparam"]["leaguematches"] if me in (x["home"], x["away"]))
                assert mine["goals"] == {"home": 2, "away": 1}, mine
                got = body(hc.route(f"/match/{m['id']}")("", b""))
                assert got["result"]["home"]["score"] == 2 and got["stage"] == "closed"
                assert got["reward"]["money"]["reward"]["total"] == (2000 if home == me else 500)
                # exp: coach by result, each of my 11 players by result (+20 for a goal); kept
                rw, cexp = got["reward"], hc.MATCH_REWARD_DEFAULT["result"]["win" if home == me else "loss"]["coach"]
                assert rw["coach"]["prev"] == lv0 and rw["coach"]["reward"]["total"] == cexp
                assert hc.coach_me(hc._state(), 0)["levelinfo"] == rw["coach"]["current"]
                assert len(rw["players"]) == 11 and rw["players"][0]["reward"]["total"] == rw["players"][1]["reward"]["total"] + 20
                shown = {p["id"]: p["levelinfo"] for p in hc.coach_me(hc._state(), 0)["team"]["players"]}
                assert all(shown[x["id"]] == x["current"] for x in rw["players"])
                assert all((x["current"]["level"], x["current"]["exp"]) > (x["prev"]["level"], x["prev"]["exp"]) for x in rw["players"])
            assert r["leagueparam"]["round"] == rnd and len(r["leagueparam"]["leaguematches"]) == hc.LEAGUE_SIZE // 2

        lg = body(hc.ep_l2_me("", b""))
        assert lg["laststatus"] == f"league:{league['maxround']}"
        s = lg["league"]["statistics"]
        assert sorted(v["rank"] for v in s.values()) == list(range(1, hc.LEAGUE_SIZE + 1))
        assert all(v["wins"] + v["draws"] + v["losses"] == 2 * (hc.LEAGUE_SIZE - 1) for v in s.values())
        assert sum(v["goals"] for v in s.values()) == sum(v["goalsconceded"] for v in s.values())

        # Rekor liga (issue #19): Rekorku = my players' records of the played rounds; Rekor gabungan
        # = best XI by line + stat leaders from them, and nothing else (the page joins every key)
        played = (league["maxround"] + 2) // 2
        recs = body(hc.ENDPOINTS["/league2/history/players/league"]("", b""))
        assert sum(r["matches"] for r in recs) == 11 * played and sum(r["goals"] for r in recs) == played
        assert all(r["ratings"] == 7 * r["matches"] and r["passes"] * 4 == r["passtries"] * 3 for r in recs)
        mine_ids = {p["id"] for p in hc.coach_me(hc._state(), 0)["team"]["players"]}
        assert {r["id"] for r in recs} <= mine_ids
        lead = body(hc.ENDPOINTS["/league2/leader/league"]("", b""))
        assert set(lead) == {"GK", "DF", "MF", "FW", "ratings", "goals", "assists", "tackles", "passes", "saves"}
        assert sum(len(lead[k]) for k in hc.LINES) == 11 and len(lead["GK"]) == 1
        assert all(e["value"] == 7 and e["teamid"] == me for k in hc.LINES for e in lead[k])
        assert lead["passes"][0]["value"] == 0.75 and not lead["assists"] and not lead["saves"]
        assert len(lead["goals"]) <= hc.STAT_LEADERS and lead["goals"][0]["value"] >= 1
        assert body(hc.ENDPOINTS["/league2/history/players/cup"]("", b"")) == []
        # the standings tab reads league2difficulty[level].groupId -> league2promote (it threw
        # without them: empty table); season end promotes / demotes by the same table
        diff = json.load(open(os.path.join(hc.RESPONSES, "static_db_LEAGUE2DIFFICULTY.json")))
        assert all(str(diff["league2difficulty"][str(d)]["groupId"]) in diff["league2promote"] for d in range(10, 25))
        assert hc.league_promote(12) == {"promote_rank": 3, "demote_rank": 0}
        assert hc.league_promote(19)["promote_rank"] == 0 and hc.league_promote(24) == {"promote_rank": 0, "demote_rank": 3}

        ach = body(hc.ep_l2_achievement("", b"{}"))["missions"][0]
        assert ach["mid"] == hc.SPONSORS["1"] and ach["progress"][0] == s[str(me)]["rank"], ach
        assert ach["achievement"] == (s[str(me)]["rank"] <= hc.MISSION_TARGET[ach["mid"]])

        end = body(hc.ep_l2_end("", b"{}"))
        assert end["promotion"]["current"] == 12 and end["promotion"]["next"] == (13 if s[str(me)]["rank"] <= 3 else 12)
        assert sum(len(end["leaderRewards"][k]) for k in ("FW", "MF", "DF", "GK")) == 11
        assert all(len(end["leaderRewards"][k]) == 1 for k in ("ratings", "goals", "assists", "tackles", "passes", "saves"))
        assert end["rewards"]["money"]["reward"]["total"] == sum(end["rewards"]["money"]["reward"]["detail"].values())
        after = body(hc.ep_l2_me("", b""))
        assert after["sponsoroffice"]["season"]["status"] == "finished" and "league" in after
        assert after["difficultyselect"] == end["promotion"]["next"]
        body(hc.ep_l2_finish("", b"{}"))  # give up / reset
        assert "league" not in body(hc.ep_l2_me("", b""))
        # --- cup: groups of 4 then an 8-club knock-out; I win every match I play
        cup = body(hc.ep_cup_new("", b'{"metaid": 1, "difficulty": 2}'))["resources"][0]["body"]
        cid = cup["_id"]
        assert len(cup["teams"]) == 16 and cup["phases"][0]["system"] == "round-robin"
        played = 0
        for _ in range(10):
            g, leg = hc.cup_my_pair(hc._state()["cups"][cid])
            if leg is not None and "score" not in leg:
                m = body(hc.route(f"/cup/{cid}/match")("", b"{}"))["resources"][0]["body"]
                assert m["type"] == "Cup_PvE"
                # kits: native reads teamid = id >> 5, kit type = id & 31; the game setting
                # screen's kit stepper (side 0 = left) comes back in the match resource
                left = m["side"]["left"]["team"]
                assert left["kit"]["availables"]["away"]["id"] == left["teamid"] << 5 | 1
                put = lambda kit, side: body(hc.route(f"/match/{m['id']}/gamesettings")("", json.dumps({"kit": kit, "side": side}).encode()))
                assert put("away", 0)["resources"][0]["body"]["gamesettings"]["kit"][0] == "away"
                assert put("home", 0)["resources"][0]["body"]["gamesettings"]["kit"][0] == "home"
                mine_home = g["teams"][leg["homeidx"]]["coach"] is not None
                stats = {"home": {"id": m["side"]["left" if mine_home else "right"]["team"]["teamid"], "score": 3 if mine_home else 0},
                         "away": {"id": m["side"]["right" if mine_home else "left"]["team"]["teamid"], "score": 0 if mine_home else 3}}
                body(hc.route(f"/match/{m['id']}/end")("", json.dumps(stats).encode()))
                played += 1
            cup = body(hc.route(f"/cup/{cid}/next")("", b"{}"))["resources"][0]["body"]
            if cup.get("finished") or cup["coaches"][0]["state"] != "playing":
                break
        assert played == 6 and cup.get("finished") and cup["coaches"][0]["state"] == "won", (played, cup["coaches"])
        assert len(cup["phases"]) == 2 and all("score" in p["legs"][0] for r in cup["phases"][1]["groups"][0]["rounds"] for p in r["pairs"])
        assert {"metaid": 1, "cupid": cid} in hc.coach_me(hc._state(), hc._default_slot(hc._state()))["cups"]  # until reward taken
        ep = lambda: hc.coach_me(hc._state(), hc._default_slot(hc._state()))["money"]["ep"]
        ep0 = ep()
        lv = body(hc.route(f"/cup/{cid}/leave")("", b"{}"))
        assert lv["rewards"] == [{"itemid": 1, "count": 60000}], lv
        assert ep() == ep0 + 60000  # cup prize credited
        assert cid not in hc._state()["cups"]
        # --- market: top list, search, buy (EP checked, a new card instance in my players)
        top = body(hc.route("/transfer/top/50")("", b""))
        assert len(top) == 50 and top[0]["price"] >= top[-1]["price"] and top[0]["expandme"] == "player"
        assert all(o["spid"] for o in body(hc.route("/transfer/top/50/position/GK")("", b"")))
        assert body(hc.route("/transfer/search/158023")("", b"")) == []  # season-0 engine card: not tradeable
        buy = lambda o: body(hc.route(f"/transfer/purchase/{o['spid']}/{o['grade']}/{o['price']}/purchase")("", b"{}"))
        team = lambda: hc._state()["teams"][str(hc._default_slot(hc._state()))]
        copies = lambda spid: [p for p in team()["players"] if p["spid"] == spid]
        star = next((o for o in top if o["price"] > ep()), None)
        assert star is None or buy(star)["reason"] == "NOT_ENOUGH_EP"
        with hc.closing(hc._db()) as c:
            spid = next(r[0] for r in c.execute("SELECT spid FROM players WHERE overallrating BETWEEN 70 AND 75 ORDER BY spid")
                        if hc.on_market(r[0]) and not copies(r[0]) and hc.card_price(r[0]) * 3 < ep())
        offer = body(hc.route(f"/transfer/search/{spid}")("", b""))[0]
        ep0 = ep()
        assert buy(offer)["result"] and len(copies(spid)) == 1 and ep() == ep0 - offer["price"]
        assert buy(offer)["result"] and len(copies(spid)) == 2  # a second copy: an upgrade pair
        # --- upgrade (enhancement v1): +1 & +1 -> +2 at 100% (ENHANCE_RATE[1] = 1.0)
        a, b = (hc.iid(p) for p in copies(spid))
        pv = body(hc.route(f"/player/{a}/enhance/{b}/preview")("", b""))
        assert pv["grade"] == 2 and pv["enhancepay"] >= 1000 and pv["price"] == hc.card_price(spid, 2), pv
        ep1 = ep()
        up = body(hc.route(f"/player/{a}/enhance/{b}")("", b"{}"))
        assert up["success"] and up["grade"] == 2 and [hc.iid(p) for p in copies(spid)] == [a] and ep() == ep1 - pv["enhancepay"]
        assert hc.grade_of(copies(spid)[0]) == 2 and hc.player_ovr(copies(spid)[0]) == hc.card_ovr(spid) + hc.GRADE_BOOST[2]
        assert not body(hc.route(f"/player/{a}/enhance/{a}/preview")("", b""))["result"]  # needs two cards
        # bonus follows the tab's label: +6 target with +1 Kosong, +2 Normal, +4 High; +9 with +2 Low
        rate = lambda t, m: hc.enhance_rate({"grade": t}, {"grade": m})
        assert [round(rate(6, m), 4) for m in (1, 2, 4)] == [0.15, 0.1875, 0.225]
        assert round(rate(9, 2), 4) == 0.022 and rate(2, 1) == 0.81
        # +0 material (issue #5): a club card adds no grade, so the target keeps its grade at
        # 100% and a +10 may take one; the copy takes its squad slot and joins Tim inti
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        sub = min((s for s in t["squad"]["positions"] if s["pos"] >= hc.POS_SUB), key=lambda s: hc.card_price(s["spid"]))
        base = next(p for p in t["players"] if hc.iid(p) == str(sub.get("id") or sub["spid"]))
        assert hc.grade_of(base) == 0
        c10, c4 = (hc.add_player(t, base["spid"], g) for g in (10, 4))
        c10["team2"] = c4["team2"] = True
        hc.add_ep(st, 10 ** 9); hc._save(st)
        b0, c10, c4 = hc.iid(base), hc.iid(c10), hc.iid(c4)
        pv = body(hc.route(f"/player/{c10}/enhance/{b0}/preview")("", b""))
        assert pv["result"] and pv["grade"] == 10 and pv["probability"] == 100, pv
        assert not body(hc.route(f"/player/{c10}/enhance/{c4}/preview")("", b""))["result"]  # +10 with +4
        pv = body(hc.route(f"/player/{c4}/enhance/{b0}/preview")("", b""))
        assert pv["grade"] == 4 and pv["probability"] == 100, pv
        up = body(hc.route(f"/player/{c4}/enhance/{b0}")("", b"{}"))
        assert up["success"] and up["grade"] == 4 and up["attribPlus"] == 0, up
        kept = next(p for p in team()["players"] if hc.iid(p) == c4)
        assert not kept.get("team2") and hc.in_squad(team(), kept) and b0 not in {hc.iid(p) for p in team()["players"]}
        # issue #7: upgrading two starters of one player (a bench filled by the server could
        # hold a second card) left a hole in the XI; the shown squad fills it from the bench,
        # tops the bench up to 7 from Tim inti, and keeps one card per player in the 18
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        xi = [s for s in t["squad"]["positions"] if s["pos"] < hc.POS_SUB]
        keep = next(p for p in t["players"] if hc.iid(p) == str(xi[-1].get("id") or xi[-1]["spid"]))
        twin = hc.add_player(t, keep["spid"], 1)
        xi[-2].update(id=hc.iid(twin), spid=twin["spid"])  # both cards in the XI
        hc._save(st)
        assert body(hc.route(f"/player/{hc.iid(keep)}/enhance/{hc.iid(twin)}")("", b"{}"))["result"]
        assert sum(s["pos"] < hc.POS_SUB for s in team()["squad"]["positions"]) == 10  # the hole
        shown = hc.coach_me(hc._state(), 0)["team"]["squad"]["positions"]
        players = [int(s["spid"]) % 1000000 for s in shown]
        assert sum(s["pos"] < hc.POS_SUB for s in shown) == 11 and len(set(players)) == len(players) == 18, shown
        assert {s["pos"] for s in shown if s["pos"] < hc.POS_SUB} == {s["pos"] for s in xi}
        # every starter carries starting [attacking, defensive, x, y]: without it the client moves
        # him to the bench (issue #7 again: the filled hole and a Formasi save had none)
        assert all(len(s.get("starting") or []) == 4 for s in shown if s["pos"] < hc.POS_SUB), shown
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        for s in t["squad"]["positions"][:2]:
            s.pop("starting", None)
        hc._save(st)
        shown = hc.coach_me(hc._state(), 0)["team"]["squad"]["positions"]
        assert all(len(s.get("starting") or []) == 4 for s in shown if s["pos"] < hc.POS_SUB), shown
        # issue #9, Tim > Klub > Informasi tim: TeamStaticInfo shows coach.career.appat (start
        # date) and coach.stadium {id}, then GET /stadium/<id> {name, yearbuilt, capacity};
        # TeamManagementTeamInfoTabPage draws nothing (player stepper, 3D player) while coach.stadium is undefined
        me = hc.coach_me(hc._state(), 0)
        assert isinstance(me["stadium"]["id"], int) and me["career"]["appat"].endswith("Z")
        assert hc.club_stadium(243) == 2  # Real Madrid: Santiago Bernabeu
        bern = body(hc.route("/stadium/2")("", b""))
        assert bern == {"id": 2, "name": "Santiago Bernabéu", "yearbuilt": 1947, "capacity": 81044}, bern
        assert body(hc.route(f"/stadium/{me['stadium']['id']}")("", b""))["name"]
        # issue #8: Tim > Peran saves the captain and each set-piece taker on its own
        # (TeamManagementPlayerRolesTabPage: PUT /game/my/team/captain, .../kickers/<KICKER_TYPES
        # index: left corner, right corner, free kick, penalty, free kick 2>); the slots never shift
        xi_ids = [s["id"] for s in shown if s["pos"] < hc.POS_SUB]
        put = lambda uri, i: body(hc.ENDPOINTS[uri]("", json.dumps({"id": i, "_method": "PUT"}).encode()))
        r = put("/game/my/team/captain", xi_ids[3])
        assert r["result"] and r["resources"][0]["body"]["team"]["captain"] == xi_ids[3]
        assert put("/game/my/team/kickers/3", xi_ids[1])["result"] and put("/game/my/team/kickers/0", xi_ids[2])["result"]
        kick = hc.coach_me(hc._state(), 0)["team"]["kickers"]
        assert len(kick) == 5 and kick[3] == xi_ids[1] and kick[0] == xi_ids[2], kick
        assert not put("/game/my/team/kickers/2", "no-such-card")["result"]
        # issue #13, Tim > Locker room: every stepper has items (TOP / PANTS / SHOES, visible), boots
        # by brand; a look is saved on the card as lr and the shirt number swaps with its wearer;
        # Item saya holds the ticket (itemid 801, expireat in ms) that makes the look count in matches
        lri = body(hc.ENDPOINTS["/static/db/LOCKERROOMITEM"]("", b""))
        assert all(i["visible"] and i["type"] in ("TOP", "PANTS", "SHOES") for i in lri.values())
        cats = {(i["type"], i["category"], i.get("option") if i["category"] == "GLOVE" else None) for i in lri.values()}
        assert cats == {("TOP", c, None) for c in ("TATTOO", "UNIFORMKIND", "UNIFORMARM", "WRIST")} | {
            ("TOP", "GLOVE", "PLAYERGLOVE"), ("TOP", "GLOVE", "GKGLOVE"), ("PANTS", "SOCKS", None),
            ("PANTS", "KNEE", None), ("SHOES", "SHOES", None)}, cats
        shoes = [i for i in lri.values() if i["type"] == "SHOES"]
        assert len(shoes) == 614 and {i["option"] for i in shoes} == set(hc.LR_SHOES)
        assert lri["100012"]["asset"] == 12 and lri["100012"]["option"] == "ADIDAS" and lri["1001"]["color"] == "1"
        tix = [i for i in hc.coach_me(hc._state(), 0)["items"] if i["itemid"] == 801]
        assert len(tix) == 1 and tix[0]["createat"] and tix[0]["expireat"] > time.time() * 1000
        assert not body(hc.ENDPOINTS["/items/itemtodepot"]("", json.dumps({"moveitems": [tix[0]["_id"]]}).encode()))["result"]
        look = {"100012": {"id": "100012"}, "10": {"id": "10", "pos": "L", "clr": 3}, "nope": {"id": "nope"}}
        r = body(hc.route(f"/lockerroom/{xi_ids[0]}/itemset")("", json.dumps({"itemset": look, "_method": "PUT"}).encode()))
        card = lambda i: next(p for p in r["resources"][0]["body"]["team"]["players"] if p["_id"] == i)
        assert r["result"] and card(xi_ids[0])["lr"] == {k: look[k] for k in ("100012", "10")}
        r = body(hc.route(f"/lockerroom/{xi_ids[0]}/itemset")("", b'{"itemset":{},"_method":"PUT"}'))  # Reset
        assert r["result"] and "lr" not in card(xi_ids[0])
        n0, n1 = card(xi_ids[0])["jersey"], card(xi_ids[1])["jersey"]
        r = body(hc.route(f"/lockerroom/{xi_ids[0]}/jersey")("", json.dumps({"desired": n1, "giverplayerid": xi_ids[1]}).encode()))
        assert r["result"] and (card(xi_ids[0])["jersey"], card(xi_ids[1])["jersey"]) == (n1, n0)
        assert not body(hc.route(f"/lockerroom/{xi_ids[0]}/jersey")("", b'{"desired": 100}'))["result"]
        # a Formasi save with an empty slot keeps the others in place; a short list (old saves
        # dropped empty slots) comes back as 5 starters
        sq = hc.coach_me(hc._state(), 0)["team"]["squad"]
        hc.ENDPOINTS["/coach/me/squad"]("", json.dumps({"squad": sq, "kickers": ["", *kick[1:]], "captain": xi_ids[3]}).encode())
        kick2 = hc.coach_me(hc._state(), 0)["team"]["kickers"]
        assert kick2[1:] == kick[1:] and len(kick2) == 5 and kick2[0] in xi_ids, kick2
        st = hc._state(); st["teams"][str(hc._default_slot(st))]["squad"]["kickers"] = kick[:2]; hc._save(st)
        kick3 = hc.coach_me(hc._state(), 0)["team"]["kickers"]
        assert kick3[:2] == kick[:2] and len(kick3) == 5 and set(kick3) <= set(xi_ids), kick3
        # Formasi opens preset team.presetidx of the COACH-level teamsquadlist (none = "Tidak cukup pemain")
        me = hc.coach_me(hc._state(), 0); me_team = me["team"]
        preset = me["teamsquadlist"]["preset"][me_team["presetidx"]]
        assert preset["positions"] == me_team["squad"]["positions"] and preset["formation"] == me_team["squad"]["formation"]
        # Squad A / B / C (issue #20: the picker was an empty box without limit.preset_squad_count)
        assert body(hc.from_file("/static/db/STATICVALUES"))["limit"]["preset_squad_count"] == hc.PRESET_SQUADS
        assert len(me["teamsquadlist"]["preset"]) == hc.PRESET_SQUADS and me_team["presetidx"] == 0
        sq_a = me_team["squad"]
        put_sq = lambda sq, i=None: hc.ENDPOINTS["/coach/me/squad"]("", json.dumps(
            {"squad": sq, "kickers": sq["kickers"], "captain": sq["captain"], **({} if i is None else {"presetidx": i})}).encode())
        # pick B (starts as a copy of A), swap two starters there and save
        sq_b = copy.deepcopy(me["teamsquadlist"]["preset"][1])
        xi = [s for s in sq_b["positions"] if s["pos"] < hc.POS_SUB]
        xi[0]["pos"], xi[1]["pos"] = xi[1]["pos"], xi[0]["pos"]
        put_sq(sq_b, 1)
        me = hc.coach_me(hc._state(), 0)
        pos_of = lambda sq: {s["id"]: s["pos"] for s in sq["positions"]}
        assert me["team"]["presetidx"] == 1 and pos_of(me["team"]["squad"]) == pos_of(sq_b)
        assert pos_of(me["teamsquadlist"]["preset"][0]) == pos_of(sq_a) != pos_of(sq_b)  # A kept
        put_sq(me["team"]["squad"])  # an edit without presetidx stays on B
        assert hc.coach_me(hc._state(), 0)["team"]["presetidx"] == 1
        put_sq(me["teamsquadlist"]["preset"][0], 0)  # back to A
        me = hc.coach_me(hc._state(), 0)
        assert me["team"]["presetidx"] == 0 and pos_of(me["team"]["squad"]) == pos_of(sq_a)
        assert pos_of(me["teamsquadlist"]["preset"][1]) == pos_of(sq_b)
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        hc.remove_player(t, next(p for p in t["players"] if hc.iid(p) == c10)); hc._save(st)
        # --- Upgrade 2.5: the tab, upgrade points (money.es) and boost items
        assert body(hc.ep_account("", b""))["features"]["teammanagement"]["playermanagement"]["enhancement"] == {"v2_5": {}}
        pe2 = body(hc.ENDPOINTS["/static/db/PE2STATICVALUES"]("", b""))
        # the popup constructor reads all three (a missing key left it half-built)
        assert pe2["bonus"]["use"] == 1000 and "use" in pe2["simplify_step"]
        ladder = [pe2["effect_price"][str(i)] for i in range(len(pe2["effect_price"]))]
        assert ladder == sorted(ladder, reverse=True) and len(ladder) == 5  # effect6..effect2
        es = lambda: hc.coach_me(hc._state(), hc._default_slot(hc._state()))["money"]["es"]
        with hc.closing(hc._db()) as c:
            s25 = next(r[0] for r in c.execute("SELECT spid FROM players WHERE overallrating BETWEEN 60 AND 65 ORDER BY spid")
                       if hc.on_market(r[0]) and not copies(r[0]))
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        tg, mt = hc.iid(hc.add_player(t, s25, 6)), hc.iid(hc.add_player(t, s25, 2))
        gold = hc.inventory_add(hc.my_coach(st), 1000052, 2)["_id"]
        hc._save(st)
        es0 = es()
        boost_items = [i for i in hc.coach_items(hc._state(), hc._default_slot(hc._state())) if i["staticdata"]["type"] == "ENHANCEMENT_BOOST"]
        assert [i["remains"] for i in boost_items] == [2]
        assert not body(hc.route(f"/item/{gold}/use")("", b"{}"))["result"]  # not via "Gunakan"
        pv = lambda u, it, ev=-1: body(hc.route(f"/player/{tg}/enhance2.5/{mt}/preview/{u}/{it}/{ev}")("", b""))
        base = round(hc.enhance_rate({"grade": 6}, {"grade": 2}) * 100)
        assert pv(0, -1)["probability"] == base and pv(0, -1)["grade"] == 7 and pv(0, -1)["needes"] == 70
        assert pv(1, 1000052)["probability"] == base + 10 + 15
        # the never-ending Upgrade event (+10% for targets +1..+9)
        ev = body(hc.ENDPOINTS["/events"]("", b""))["events"]
        assert [e["condition"]["type"] for e in ev] == ["enhance"] and ev[0]["active"] and ev[0]["reason"] == []
        assert all(isinstance(r, list) for r in ev[0]["reward"])  # getEnhanceGradeRange: Array entries
        assert pv(0, -1, ev[0]["eventid"])["probability"] == base + 10 and pv(0, -1, 999)["probability"] == base
        # upgrade points in Shop > Paket: credited to money.es at once
        pkg = next(e for e in hc.shop_list(hc._state()) if e["shopid"] == 81000500)
        assert pkg["shopcategory"] == "PACKAGE" and pkg["product"]["staticdata"]["items"][0]["staticdata"]["name"] == "Upgrade point"
        es1 = es()
        assert body(hc.ep_shop_purchase("", json.dumps({"productid": 81000500, "bunch": 0}).encode()))["result"]
        assert es() == es1 + 500 and body(hc.ep_static_item("", b'{"itemids": [2]}'))["2"]["itemicon"] == 8700001
        st = hc._state(); hc.add_es(st, -500); hc._save(st)
        assert not body(hc.route(f"/player/{tg}/enhance2.5/{mt}/0/1000053/-1")("", b"{}"))["result"]  # no Silver owned
        roll = hc.random.random
        try:
            hc.random.random = lambda: 0.999  # fail: +6 drops to +5, 70 points earned
            up = body(hc.route(f"/player/{tg}/enhance2.5/{mt}/0/-1/-1")("", b"{}"))
            assert not up["success"] and up["grade"] == up["rgrade"] == 5 and up["grantes"] == 70, up
            assert up["usepoint"] == {"currency": "ES", "price": 210} and es() == es0 + 70
            assert not body(hc.ENDPOINTS["/player/enhance2.5/restore"]("", b"{}"))["result"]  # 70 < 210
            st = hc._state(); hc.add_es(st, 300); hc._save(st)
            rs = body(hc.ENDPOINTS["/player/enhance2.5/restore"]("", b"{}"))
            assert rs["result"] and not rs["success"] and rs["grade"] == 6 and es() == es0 + 70 + 300 - 210, rs
            assert not body(hc.ENDPOINTS["/player/enhance2.5/restore"]("", b"{}"))["result"]  # once
            st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
            mt = hc.iid(hc.add_player(t, s25, 2)); hc._save(st)
            hc.random.random = lambda: 0.0  # success with points and a Gold boost
            up = body(hc.route(f"/player/{tg}/enhance2.5/{mt}/1/1000052/-1")("", b"{}"))
            assert up["success"] and up["grade"] == 7 and up["grantes"] == 0 and es() == es0 + 160 - 70, up
            assert [i["remains"] for i in hc.coach_items(hc._state(), hc._default_slot(hc._state())) if i["itemid"] == 1000052] == [1]
        finally:
            hc.random.random = roll
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        hc.remove_player(t, next(p for p in t["players"] if hc.iid(p) == tg)); hc._save(st)
        # --- selling: a reserve at <= market price; the NPC buys at once, EP minus fee on collect
        band = body(hc.route(f"/transfer/price/{spid}/2")("", b""))
        assert band["upper"] == hc.card_price(spid, 2) and band["lower"] < band["upper"]
        sell = lambda pid, price: body(hc.ep_transfer_offer("", json.dumps({"playerobjectid": str(pid), "price": price}).encode()))
        squad = team()["squad"]
        starter = next(str(s.get("id") or s["spid"]) for s in squad["positions"] if s["pos"] < hc.POS_SUB)
        assert not sell(starter, 1000)["result"] and not sell(a, band["upper"] + 1)["result"]
        assert sell(a, band["upper"])["result"] and not copies(spid)
        offers = body(hc.ENDPOINTS["/transfer/my/offer/list"]("", b""))["offers"]
        assert len(offers) == 1 and offers[0]["status"] == "sold"
        ep1 = ep()
        got = body(hc.route(f"/transfer/my/offer/completed/{offers[0]['_id']}")("", b"{}"))
        fee = offers[0]["completefee"]["base"]  # minus PC warnet 20% + VIP 30% fee discounts
        assert got["result"] and ep() == ep1 + band["upper"] - fee + int(0.2 * fee) + int(0.3 * fee)
        me = hc.coach_me(hc._state(), hc._default_slot(hc._state()))
        assert me["igr"] is True and me["vipDetail"] == 2 and me["vipExpireAt"] > time.time() * 1000
        assert body(hc.ENDPOINTS["/transfer/my/offer/list"]("", b""))["offers"] == []
        # --- trade (Tukar v1): 2..10 reserves -> offers rated >= avg OVR + bonus, PC + VIP extra
        post = lambda path, req: body(hc.ENDPOINTS[path]("", json.dumps(req).encode()))
        with hc.closing(hc._db()) as c:
            cheap = [r[0] for r in c.execute("SELECT spid FROM players WHERE overallrating BETWEEN 58 AND 64 ORDER BY spid")
                     if hc.on_market(r[0])][:6]
        for s in cheap:  # bought cards land in the reserves
            assert buy(body(hc.route(f"/transfer/search/{s}")("", b""))[0])["result"]
        reserves = [p for p in team()["players"] if not hc.in_squad(team(), p)][:4]
        ids = [hc.iid(p) for p in reserves]
        sub = next(str(s.get("id") or s["spid"]) for s in team()["squad"]["positions"] if s["pos"] >= hc.POS_SUB)
        assert not post("/players/trade/proposal", {"players": ids[:1]})["result"]  # needs 2+
        assert not post("/players/trade/proposal", {"players": [starter] + ids[:1]})["result"]
        assert not post("/players/trade/proposal", {"players": [sub] + ids[:1]})["result"]  # subs neither
        pr = post("/players/trade/proposal", {"players": ids})
        sv = hc.static_values()
        # pack opening glow (TeamManagementPlayerCardScreen.getEffectType): highest threshold
        # first, and Market cards land in every tier (none, 1, 2, 3)
        star = sv["starplayer_price"]
        assert star == sorted(star, reverse=True)
        tiers = {sum(r[0] >= t for t in star) for r in hc.trade3_pool()[::997]}
        assert tiers == {0, 1, 2, 3}, tiers
        lo = min(int(sum(hc.card_ovr(p["spid"]) for p in reserves) / 4 + sv["playertrade_cardovrbonus"]["4"]),
                 sv["playertrade_limit"]["CardMaxValue"])
        assert pr["result"] and len(pr["props"]) == sv["playertrade_normal"]["4"] + 2, pr
        assert [o.get("boost") for o in pr["props"]][-2:] == ["igr", "vip"]
        assert all(hc.card_ovr(o["spid"]) >= lo and o["price"] == hc.card_price(o["spid"], o["grade"])
                   for o in pr["props"] if "spid" in o), (lo, pr)
        ep_only = next(i for i, o in enumerate(pr["props"]) if "spid" not in o)
        n0, ep1 = len(team()["players"]), ep()
        assert post("/players/trade/contract", {"select": ep_only})["result"]
        assert len(team()["players"]) == n0 - 4 and ep() == ep1 + pr["props"][ep_only]["ep"]
        assert not any(hc.iid(p) in ids for p in team()["players"])
        assert not post("/players/trade/contract", {"select": 0})["result"]  # proposal used up
        pr = post("/players/trade/proposal", {"players": [hc.iid(p) for p in team()["players"] if not hc.in_squad(team(), p)][:2]})
        n0, card = len(team()["players"]), pr["props"][0]
        assert post("/trade3/contract", {"selectnum": 0, "slotnum": 0})["result"] and len(team()["players"]) == n0 - 1
        assert (team()["players"][-1]["spid"], team()["players"][-1]["grade"]) == (card["spid"], card["grade"])
        # --- Tukar v2 (trade2): TP from card values, levels, "yesterday" ladder, no limits
        assert "trade2" in body(hc.ep_account("", b""))["features"]["teammanagement"]["playermanagement"]
        tt = body(hc.ENDPOINTS["/static/db/TRADE"]("", b""))
        maxg = [tt["tp"][k]["value"][-1] for k in sorted(tt["tp"], key=int)]
        assert len(maxg) == 15 and maxg == sorted(maxg) and maxg[0] == 1 and maxg[-1] == 10
        assert tt["trade2_limit"]["max"] == hc.NO_LIMIT and set(tt["playertrade2_bonus"]) >= {"IGR", "VIP", "2", "10"}
        assert body(hc.ENDPOINTS["/account/trade2/usage"]("", b""))["maxcount"] == 0  # unlimited
        special = body(hc.ENDPOINTS["/static/cache/TRADE_SPECIALPLAYERS"]("", b""))
        assert special and all(int(s) // 1000000 in hc.LEGEND_SEASONS for s in special)
        ladder = body(hc.ENDPOINTS["/players/trade2/info"]("", b""))
        assert len(ladder) == 14 and all(e["expandme"] == "player" and e["coach"] and e["grade"] <= hc.trade2_max_grade(int(k))
                                         for k, e in ladder.items())
        give = [p for p in team()["players"] if not hc.in_squad(team(), p)][:3]
        tp = hc.trade2_tp(give)
        pr = post("/players/trade2/proposal", {"players": [hc.iid(p) for p in give]})
        assert pr["result"] and len(pr["props"]) == tt["playertrade2_normal"]["3"] + 2, pr
        assert all(o["grade"] <= hc.trade2_max_grade(tp) and o["price"] == hc.card_price(o["spid"], o["grade"])
                   and 0.5 * tp <= o["price"] <= 2 * tp for o in pr["props"]), (tp, pr)
        assert not post("/players/trade2/proposal", {"players": [starter, hc.iid(give[0])]})["result"]  # reserves only
        n0 = len(team()["players"])
        assert post("/players/trade2/contract", {"select": 1})["result"] and len(team()["players"]) == n0 - 2
        assert team()["players"][-1]["spid"] == pr["props"][1]["spid"]
        pt = body(hc.ENDPOINTS["/static/db/PLAYERTRADE"]("", b""))
        assert list(pt["playergrade"]["2"]) == ["1"] and list(pt["playergrade"]["40"])[-1] == "6"
        # --- trade3 (Scout): offers worth about the total value; scouts cool down after use
        st = hc._state(); hc.my_coach(st).pop("scout_used", None); hc._save(st)
        scouts = lambda: {s["key"]: s for s in hc.coach_me(hc._state(), hc._default_slot(hc._state()))["scouters"]}
        assert set(scouts()) == {"default_B01", "igr", "vip", "event", "vvip"} and len(hc.SCOUTS) <= 5 and not any(s["lock"] for s in scouts().values())
        assert scouts()["vvip"]["scoutername"] == "STR_SCOUTER_KR_VVIP_A01_NAME" and scouts()["vvip"]["quest"]["require_value"] > 0
        legend = [{"spid": s, "grade": 1} for s in list(map(int, hc.trade2_special()))[:2]]
        assert hc.quest_met(scouts()["event"]["quest"], legend) and not hc.quest_met(scouts()["event"]["quest"], legend[:1])
        for s in cheap[:3]:
            assert buy(body(hc.route(f"/transfer/search/{s}")("", b""))[0])["result"]
        give3 = [p for p in team()["players"] if not hc.in_squad(team(), p)][-3:]
        pids = [{"id": hc.iid(p), "spid": p["spid"], "grade": hc.grade_of(p), "price": hc.card_price(p["spid"], hc.grade_of(p))}
                for p in give3]
        total = sum(x["price"] for x in pids)
        # Market cards arrive in Tim Cadangan, which Tukar Scout trades from; a Tim inti card is refused
        players = lambda: {p["_id"]: p for p in hc.coach_me(hc._state(), hc._default_slot(hc._state()))["team"]["players"]}
        assert all("state" not in players()[x["id"]] for x in pids)
        move = lambda pid, where: body(hc.route(f"/player/{pid}/move/{where}")("", b"{}"))
        assert not move(starter, "secondteam")["result"]  # the 18 stay in Tim inti
        assert move(pids[0]["id"], "firstteam")["result"] and players()[pids[0]["id"]]["state"] == "first"
        assert not post("/trade3/proposal", {"id": "vip", "slotnum": 3, "playerids": pids})["result"]
        assert move(pids[0]["id"], "secondteam")["result"] and players()[starter]["state"] == "first"
        pr = post("/trade3/proposal", {"id": "vip", "slotnum": 3, "playerids": pids})
        assert pr["result"] and len(pr["props"]) == hc.TRADE3_STATIC["playertrade3_normal"]["3"] + 2, pr
        assert all(total * 0.5 <= o["price"] <= total * 3 for o in pr["props"]), (total, pr["props"])
        # scouts have no cooldown: the same scout negotiates again at once
        assert not any(s["lock"] or "cooltime" in s for s in scouts().values())
        pr = post("/trade3/proposal", {"id": "vip", "slotnum": 3, "playerids": pids})
        assert pr["result"]
        stale = [dict(pids[0], price=pids[0]["price"] + 1)] + pids[1:]
        assert post("/trade3/proposal", {"id": "default_B01", "slotnum": 0, "playerids": stale})["reason"] == "TRADE3_NOTICE_PLAYERPRICE03"
        n0 = len(team()["players"])
        assert post("/trade3/contract", {"slotnum": 3, "selectnum": 0})["result"] and len(team()["players"]) == n0 - 2
        assert team()["players"][-1]["spid"] == pr["props"][0]["spid"]
        assert hc.quest_met({"require_grade": 1, "require_grade_count": 2}, give3) and not hc.quest_met(None, give3)
        assert body(hc.ENDPOINTS["/trade3/staticvalues"]("", b""))["playertrade3_normal"] == {
            "2": 1, "3": 1, "4": 2, "5": 2, "6": 2, "7": 3, "8": 3, "9": 3, "10": 3}
        # --- daily login reward: once per WIB day into the Bag; claim one ("Terima") / all
        hc.DAILY_FILE = os.path.join(tmp, "daily_rewards.json")  # default table; admin test writes here
        st = hc._state(); hc.my_coach(st).pop("daily", None); hc.my_coach(st)["bag"] = []
        t0, day, table = time.time(), 86400, hc.daily_table()
        e1 = hc.daily_login(st, t0)
        assert e1["items"] == hc.reward_items(table[0]) and hc.daily_login(st, t0 + 60) is None  # once a day
        e2 = hc.daily_login(st, t0 + day)
        assert hc.my_coach(st)["daily"]["streak"] == 2 and e2["items"] == hc.reward_items(table[1])
        e3 = hc.daily_login(st, t0 + 3 * day)
        assert hc.my_coach(st)["daily"] == {"last": hc.today_wib(t0 + 3 * day), "streak": 1, "total": 3}  # streak broken
        hc._save(st)
        bag = body(hc.ENDPOINTS["/bag"]("", b""))
        assert [b["title"] for b in bag] == [e1["title"], e2["title"], e3["title"]] and {b["type"] for b in bag} == {"event"}
        assert "hari ke-3" in bag[1]["msg"] and all(b["date"].endswith(".000Z") for b in bag)  # tooltip text + received date
        ep1 = ep()
        assert body(hc.route(f"/bag/{e1['_id']}/unpack")("", b"{}"))["result"] and ep() == ep1 + table[0].get("ep", 0)
        got = body(hc.ENDPOINTS["/bag/unpackall"]("", json.dumps({"reqUnpackItems": [e2["_id"], e3["_id"]]}).encode()))
        assert got["result"] and body(hc.ENDPOINTS["/bag"]("", b"")) == []
        assert not body(hc.route(f"/bag/{e1['_id']}/unpack")("", b"{}"))["result"]  # already taken
        assert list(body(hc.ENDPOINTS["/static/cache/item"]("", json.dumps({"itemids": [1]}).encode()))) == ["1"]
        st = hc._state(); hc.my_coach(st).pop("items", None); hc._save(st)  # packs from the rewards (shop test counts)
        # --- shop: player packs for EP (1 or 10); Item saya opens one card per use
        shop = body(hc.ENDPOINTS["/shop/list"]("", b""))
        cats = Counter(e["shopcategory"] for e in shop)
        assert cats == {"PLAYERPACK": len(hc.PACKS), "USE": len(hc.ITEMS), "PACKAGE": len(hc.PACKAGES) - len(hc.CHAIN_STEPS),
                        "MILEAGE": len(hc.MP_SHOP), "MONTHLYPACK": len(hc.MONTHLY), "CHAINED": len(hc.CHAINED)}
        assert all(b["price"] == 0 for e in shop for b in e["product"]["staticdata"]["bunches"])  # free Shop
        pid = 8223509  # MF NEW 70+ 2017
        bunches = next(e for e in shop if e["shopid"] == pid)["product"]["staticdata"]["bunches"]
        ep1 = ep()
        assert post("/shop/purchase", {"shopid": pid, "productid": pid, "bunch": 0})["result"] and ep() == ep1 - bunches[0]["price"]
        assert post("/shop/purchase", {"shopid": pid, "productid": pid, "bunch": 1})["result"] and ep() == ep1 - bunches[0]["price"] - bunches[1]["price"]
        items = lambda: [i for i in hc.coach_me(hc._state(), hc._default_slot(hc._state()))["items"] if i["itemid"] != hc.LR_TICKET]
        assert [(i["itemid"], i["remains"], i["staticdata"]["category"]) for i in items()] == [(pid, 11, "PLAYERPACK")]
        n0 = len(team()["players"])
        got = body(hc.route(f"/item/{items()[0]['_id']}/use")("", b"{}"))
        assert got["result"] and len(team()["players"]) == n0 + 1 and team()["players"][-1]["spid"] == got["player"]["spid"]
        with hc.closing(hc._db()) as c:
            pos = c.execute("SELECT preferredposition1 FROM players WHERE spid = ?", (got["player"]["spid"],)).fetchone()[0]
        # "70+" = the rating shown at +1 (base + 5, fifaaddict's enchant table)
        assert hc.card_ovr(got["player"]["spid"]) + hc.GRADE_BOOST[1] >= 70 and 9 <= pos <= 19 and got["player"]["spid"] // 1000000 == 88
        assert hc.GRADE_BOOST[:6] == (0, 5, 6, 7, 8, 10) and hc.player_ovr({"spid": 91190871, "grade": 5}) == 93  # WB Neymar +5
        assert items()[0]["remains"] == 10
        # client rating = Enums.calcPosOvr at preferredposition1 (fifaaddict shows the same):
        # Messi 2017 RW 80, Belotti 2017 ST 77, Andre Gomes 2017 CM 65 (fifadb column: 85/82/70)
        assert [hc.card_ovr(s) for s in (88158023, 88208596, 88211575)] == [80, 77, 65]
        assert list(body(hc.ENDPOINTS["/static/cache/item"]("", json.dumps({"itemids": [pid, "x", 9]}).encode()))) == [str(pid)]
        # USE items: buy (free), then "Gunakan" -> /item/<_id>/use per type; a package fills Item saya
        def use(itemid, req=None):
            it = next(i for i in hc.coach_me(hc._state(), hc._default_slot(hc._state()))["items"] if i["itemid"] == itemid)
            return body(hc.route(f"/item/{it['_id']}/use")("", json.dumps(req or {"id": it["_id"]}).encode()))
        assert post("/shop/purchase", {"shopid": 50021, "productid": 50021, "bunch": 0})["result"]
        ep1 = ep(); assert use(50021)["ep"] == 1_000_000 and ep() == ep1 + 1_000_000  # EP +1.000.000
        assert post("/shop/purchase", {"shopid": 501, "productid": 501, "bunch": 1})["result"]  # 10 Lucky EP
        assert all(10_000 <= use(501)["ep"] <= 1_000_000 for _ in range(10))
        assert not any(i["itemid"] == 501 for i in items())  # used up
        # issue #12: the random box screen (TeamManagementRandomCardScreen.SetItemBackground) shows
        # staticdata.availables, the prizes, as item tiles; without it every box crashed at "Gunakan"
        av = hc.item_def(50121)["availables"]
        assert [a["itemid"] for a in av] == [8334, 8194, 82214007, 45011, hc.EP_ITEM]
        assert av[-1]["count"] == 10_000_000 and av[-1]["staticdata"]["type"] == "EP" and av[0]["staticdata"]["name"]
        assert post("/shop/purchase", {"shopid": 50122, "productid": 50122, "bunch": 1})["result"]  # 10 Kotak Emas
        for _ in range(10):
            got = use(50122)
            assert got["result"] and (got.get("ep") == 3_000_000 or got["item"]["itemid"] in (82214180, 45012))
        assert post("/shop/purchase", {"shopid": hc.MP_SHOPID + 3002, "productid": 3002, "bunch": 0})["result"]  # MP Shop
        assert use(3002, {"name": "Juragan"})["result"] and hc.my_coach(hc._state())["name"] == "Juragan"
        assert post("/shop/purchase", {"shopid": 3001, "productid": 3001, "bunch": 0})["result"]
        club = hc.my_teamid(hc._state())
        assert use(3001, {"teamid": 10})["result"] and hc.my_teamid(hc._state()) == 10  # Ganti tim
        # Ganti tim's club info and 3D player (TeamChangeScreenSelectPage.onReceivedTeamInfo, issue #23)
        rm = body(hc.route("/static/info/team/summary/243")("", b""))
        assert rm["id"] == 243 and rm["summary"]["name"] == "Real Madrid" and rm["summary"]["league"]["id"] == 53
        assert rm["summary"]["rival"]["name"] and rm["stadium"]["name"] == "Santiago Bernabéu" and rm["stadium"]["capacity"] == 81044
        assert rm["kit"] == hc.team_kit(243)
        hc.my_coach(st := hc._state())["teamid"] = club; hc._save(st)
        n0 = {i["itemid"]: i["remains"] for i in items()}
        assert post("/shop/purchase", {"shopid": 50881, "productid": 50881, "bunch": 0})["result"]  # Kotak World Best
        n1 = {i["itemid"]: i["remains"] for i in items()}
        assert all(n1[i] - n0.get(i, 0) == n for i, n in hc.PACKAGES[50881][2]) and 50881 not in n1
        # Gudang (issue #12): whole stacks Item saya -> Gudang and back; a moved stack joins one of the same item
        depot = lambda: body(hc.ENDPOINTS["/item/depot"]("", b""))
        assert depot() == []
        wb = next(i for i in items() if i["itemid"] == 8334)
        got = post("/items/itemtodepot", {"moveitems": [wb["id"]]})
        assert got["result"] and [r["uri"] for r in got["resources"]] == ["/coach/me", "/item/depot"]
        assert [(i["_id"], i["remains"], i["staticdata"]["category"]) for i in depot()] == [(wb["_id"], wb["remains"], "PLAYERPACK")]
        assert 8334 not in {i["itemid"] for i in items()}
        assert not body(hc.route(f"/item/{wb['_id']}/use")("", b"{}"))["result"]  # not opened from the Gudang
        assert not post("/items/itemtodepot", {"moveitems": [wb["id"]]})["result"]  # already there
        some = items()[0]
        assert not post("/items/itemtodepot", {"moveitems": [some["id"], "nope"]})["result"] and items()[0] == some  # all or nothing
        assert not post("/items/itemtodepot", {})["result"]
        st = hc._state(); hc.inventory_add(hc.my_coach(st), 8334, 1); hc._save(st)
        again = next(i for i in items() if i["itemid"] == 8334)
        assert post("/items/itemtodepot", {"moveitems": [again["id"]]})["result"]
        assert [(i["_id"], i["remains"]) for i in depot()] == [(wb["_id"], wb["remains"] + 1)]
        assert body(hc.route(f"/item/depottoitem/{wb['_id']}")("", b"{}"))["result"]
        assert depot() == [] and {i["itemid"]: i["remains"] for i in items()} == {**n1, 8334: n1[8334] + 1}
        assert not body(hc.route(f"/item/depottoitem/{wb['_id']}")("", b"{}"))["result"]  # unknown id refused
        # Paket Bulanan: items now + one daily Bag entry per day; Serial product steps; Special Bonus
        ep1 = ep(); assert post("/shop/purchase", {"shopid": 81000001, "productid": 81000001, "bunch": 0})["result"]
        assert [m["productid"] for m in body(hc.ENDPOINTS["/monthlypack"]("", b""))] == [81000001]
        hc.my_coach(st := hc._state())["bag"] = []; hc._save(st)
        assert body(hc.ENDPOINTS["/monthlypack"]("", b"{}"))["result"]
        bag = body(hc.ENDPOINTS["/bag"]("", b""))
        assert [(b["type"], b["items"]) for b in bag] == [("monthlypack", [{"itemid": hc.EP_ITEM, "count": 200_000}])]
        hc.ENDPOINTS["/monthlypack"]("", b"{}"); assert len(body(hc.ENDPOINTS["/bag"]("", b""))) == 1  # once a day
        hc.my_coach(st := hc._state())["bag"] = []; hc._save(st)
        chain = lambda: next(e for e in body(hc.ENDPOINTS["/shop/list"]("", b"")) if e["shopcategory"] == "CHAINED")
        assert chain()["step"] == 0 and [c["shopid"] for c in chain()["chained"]] == [70000002, 70000003]
        assert post("/shop/purchase", {"shopid": 70000001, "productid": 70000001, "bunch": 0})["result"]
        assert chain()["step"] == 1 and chain()["remainedperaccount"] == 0
        targets = body(hc.ENDPOINTS["/specifictarget"]("", b""))
        special = body(hc.ENDPOINTS["/shop/list/STSHOP"]("", b""))
        assert targets["issell"] and {t["stid"] for t in targets["targets"]} == {e["stid"] for e in special}
        assert post("/shop/purchase", {"shopid": special[0]["shopid"], "productid": special[0]["product"]["itemid"], "bunch": 0})["result"]
        # "+N" packs give grade-N cards; 06-11 packs draw only from seasons 2006..2011
        assert len(hc.pack_pool(45007)) == 50 and {s // 1000000 for s, _ in hc.pack_pool(45007)} <= set(range(6, 12))
        wb = hc.pack_pool(82231307)  # one odd cheap card must not win most draws (it once won 80%)
        assert max(w for _, w in wb) / sum(w for _, w in wb) < 0.2
        gp = 15031  # '14 Top 30 +5
        assert hc.pack_price(gp) > 5 * sum(hc.card_price(s) * w for s, w in hc.pack_pool(gp)) / sum(w for _, w in hc.pack_pool(gp))
        assert hc.pack_grades(gp) == [(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)] and hc.pack_grades(28007) == [(1, 1)]
        # the Market's name search (TransferUtil: players.spid / 1000000 IN (availableSeasons))
        # only sees seasons listed in /static/roster: every season with Market cards is there
        # (user: "tidak ada r. gullid di world legend" -- WL and 15 more were missing)
        # issue #14: the Market filter's season combo hands value to TransferUtil.seasonQuery(Array)
        # ("cannot convert 39 to Array"); labels starting with $ are the client's season names
        seasons = body(hc.from_file("/static/roster"))["seasons"]
        assert all(isinstance(e["value"], list) for e in seasons) and seasons[23]["season"] == "$TRANSFERMARKET_SEASON_39"
        roster = {c for e in seasons for c in e["value"]}
        market = hc.market_spids()
        assert {s // 1000000 for s in market} <= roster, sorted({s // 1000000 for s in market} - roster)
        # every card the client itself can trade (its Market search: permid.transferable = 1 and a
        # name) is on the Market, in the trades and in a pack (user: "jangan sampai ada pemain yang
        # tidak ada di pack, trade, dan market"); fifaaddict alone left out 6,599, 4,313 of them '17
        with hc.closing(hc._db()) as c:
            tradeable ={s for (s,) in c.execute("""SELECT p.spid FROM players p JOIN permid m ON m.spid = p.spid
                AND m.transferable = 1 WHERE p.spid >= 1000000 AND p.playerid IN (SELECT playerid FROM namesind)""")}
        assert tradeable <= market and set(hc.fa_prices()) <= market
        assert {s for rows in hc.trade_pool().values() for s, _ in rows} == market
        assert {s for s, _ in hc.pack_pool(hc.ALL_PLAYERS_PACK)} == market
        # prices follow the rating only (user: "fix harga yang tidak sesua statsnya")
        assert all(hc.stat_price(o) < hc.stat_price(o + 1) for o in range(40, 95))
        # All Season Top 300 +8: every Market card rated 81+ of any season at +1..+8; season packs = their top 200
        assert [g for g, _ in hc.pack_grades(7675)] == list(range(1, 9))
        best = max(hc.card_ovr(s) for s in hc.market_spids())
        rated = [hc.card_ovr(s) for s, _ in hc.pack_pool(7675)]
        assert len(rated) > 300 and min(rated) == 81 and max(rated) == best
        assert len(hc.pack_pool(92000088)) == 200 and {s // 1000000 for s, _ in hc.pack_pool(92000088)} == {88}
        st = hc._state(); hc.my_coach(st)["ep"] = 10 ** 10; hc._save(st)
        assert post("/shop/purchase", {"shopid": gp, "productid": gp, "bunch": 1})["result"]  # 10 packs
        opened = [body(hc.route(f"/item/{next(i for i in items() if i['itemid'] == gp)['_id']}/use")("", b"{}"))["player"]
                  for _ in range(10)]
        assert all(1 <= p["grade"] <= 5 and p["spid"] // 1000000 == 14 and p["price"] == hc.card_price(p["spid"], p["grade"])
                   for p in opened) and len({p["grade"] for p in opened}) > 1  # a random grade +1..+5
        assert team()["players"][-1]["grade"] == opened[-1]["grade"]
        # issue #27: draft packs ("Pilih pak pemain", TeamManagementDraftPackScreen) and EXP capsules
        dp = 200005  # 2017 Draft Pick 5
        assert hc.item_def(dp)["category"] == "DRAFTPACK" and hc.item_def(dp)["draft"] == {"season": 88, "grade": 1, "availables": 5}
        top5 = body(hc.route(f"/item/draftpack/{dp}/players/5")("", b""))  # the default picks: the 5 most valuable
        assert len(top5) == 5 and all(p["spid"] // 1000000 == 88 and p["price"] == hc.card_price(p["spid"]) for p in top5)
        assert [p["price"] for p in top5] == sorted((p["price"] for p in top5), reverse=True)
        assert len(body(hc.route(f"/item/draftpack/{dp}/players/100")("", b""))) == 100  # the search list
        assert body(hc.route("/item/draftpack/28007/players/5")("", b"")) == []  # not a draft pack
        priced = body(hc.route("/transfer/price/default/3")("", json.dumps({"spids": [88158023, 1]}).encode()))
        assert priced == {"prices": [{"spid": 88158023, "price": hc.card_price(88158023, 3)}]}
        assert post("/shop/purchase", {"shopid": dp, "productid": dp, "bunch": 0})["result"]
        picks = [p["spid"] for p in top5]
        assert not use(dp, {"spids": picks[:4]})["result"]  # all 5 picks
        assert not use(dp, {"spids": picks[:4] + [91190871]})["result"]  # a World Best card is no 2017 pick
        got = use(dp, {"spids": picks})
        assert got["result"] and got["player"]["spid"] in picks and got["player"]["grade"] == 1
        assert not any(i["itemid"] == dp for i in items())  # used up
        # EXP capsule (PLAYER_EXP_CAPSULE): /item/<_id>/use {targetid} gives that player its EXP
        assert {k: hc.item_def(6004).get(k) for k in ("type", "capsuleexp", "capsulelv", "capsuleseason")} == {
            "type": "PLAYER_EXP_CAPSULE", "capsuleexp": 3000, "capsulelv": 10, "capsuleseason": None}
        for i in (6004, 6005, 6003, 6001):
            assert post("/shop/purchase", {"shopid": i, "productid": i, "bunch": 0})["result"]
        lv = lambda pid: hc.player_levelinfo(next(x for x in team()["players"] if hc.iid(x) == pid))
        assert lv(got["player"]["_id"]) == {"level": 1, "exp": 0, "to": 100}
        assert not use(6004, {"targetid": "nope"})["result"]
        assert use(6004, {"targetid": got["player"]["_id"]})["result"] and lv(got["player"]["_id"]) == {"level": 8, "exp": 200, "to": 800}
        assert not use(6005, {"targetid": opened[0]["_id"]})["result"]  # a '14 card, the capsule is for 2017 ones
        assert use(6005, {"targetid": got["player"]["_id"]})["result"] and lv(got["player"]["_id"]) == {"level": 16, "exp": 1000, "to": 1600}
        assert post("/shop/purchase", {"shopid": 6004, "productid": 6004, "bunch": 0})["result"]
        assert not use(6004, {"targetid": got["player"]["_id"]})["result"]  # above LV.10
        assert use(6003, {"targetid": opened[0]["_id"]})["result"] and lv(opened[0]["_id"])["level"] == hc.PLAYER_MAX_LEVEL
        assert not use(6001, {"targetid": opened[0]["_id"]})["result"]  # already at the max level
        # --- admin page API (admin.py)
        import admin, urllib.error, urllib.request
        admin.hc = hc
        A = lambda name, **p: admin.API[name](p)
        def refused(name, **p):
            try:
                A(name, **p)
            except admin.AdminError:
                return True
        assert A("ep", set=5000)["ep"] == 5000 and A("ep", add=-9000)["ep"] == 0 and A("ep", add=1500)["ep"] == ep() == 1500
        assert A("summary")["coach"]["ep"] == 1500 and A("summary")["players"] == len(team()["players"])
        assert any(r["spid"] == 88158023 and r["ovr"] == 80 for r in A("search", q="Messi")["rows"])
        roster = lambda: {p["id"]: p for p in A("players")["players"]}
        if len(team()["players"]) >= hc.MAX_PLAYERS:  # make room for one
            A("player_remove", id=next(i for i, p in roster().items() if p["role"] == "RES"))
        new = A("player_add", spid=88158023, grade=3)["id"]
        assert (roster()[new]["role"], roster()[new]["ovr"]) == ("RES", 80 + hc.GRADE_BOOST[3])
        A("player_grade", id=new, grade=5); A("player_team", id=new, team="second")
        assert (roster()[new]["grade"], roster()[new]["team2"]) == (5, True)
        A("player_team", id=new, team="first"); assert not roster()[new]["team2"]
        A("player_remove", id=new); assert new not in roster()
        main_id = next(i for i, p in roster().items() if p["role"] == "MAIN")
        assert refused("player_remove", id=main_id) and refused("player_team", id=main_id, team="second")
        assert refused("player_add", spid=1) and refused("player_grade", id="nope", grade=2) and refused("ep", set="x")
        A("give_pack", itemid=pid, count=2); assert items()[0]["remains"] == 12 and refused("give_pack", itemid=2)
        gift = A("bag_send", title="tes", ep=777, pack=pid, count=1, spid=88158023, grade=2)["id"]
        g = next(b for b in body(hc.ENDPOINTS["/bag"]("", b"")) if b["_id"] == gift)
        assert g["items"] == [{"itemid": hc.EP_ITEM, "count": 777}, {"itemid": pid, "count": 1}] and g["players"] == [{"spid": 88158023, "grade": 2}]
        ep1, n0 = ep(), len(team()["players"])
        assert body(hc.route(f"/bag/{gift}/unpack")("", b"{}"))["result"]
        assert ep() == ep1 + 777 and items()[0]["remains"] == 13 and len(team()["players"]) == n0 + 1
        assert refused("bag_send", title="kosong") and refused("bag_send", pack=2)
        tbl = [{"ep": 1234}, {"pack": pid, "count": 2}]
        assert A("daily_set", table=tbl)["table"] == tbl == hc.daily_table()
        assert refused("daily_set", table=[{"ep": 0}]) and refused("daily_set", table=[{"pack": 2}]) and refused("daily_set", table=[])
        A("daily_reset")
        assert A("daily_grant")["title"].endswith("hari ke-1") and A("daily_grant")["title"].endswith("hari ke-2")
        assert [b["items"] for b in body(hc.ENDPOINTS["/bag"]("", b""))] == [hc.reward_items(r) for r in tbl]
        # --- match rewards (user: "tambahkan di admin page untuk setting reward hadiah match")
        assert A("match_rewards")["cards"] == hc.MATCH_REWARD_DEFAULT["cards"]
        res = {k: {"ep": 7000, "coach": 50, "player": 40} for k in ("win", "draw", "loss")}
        cfg = A("match_rewards_set", result=res, cards=[[1, {"ep": 777}], [2, pid]])
        assert cfg == {"result": res, "cards": [[1, {"ep": 777}], [2, pid]]} and hc.match_reward_cfg() == cfg
        ep1, n1, st = ep(), items()[0]["remains"], hc._state()
        rw = hc.match_reward(st, {"myTeam": "home", "opponentTeam": "away", "home": {"score": 1}, "away": {"score": 0}})
        hc._save(st)
        assert rw["money"]["reward"]["total"] == 7000 and rw["coach"]["reward"]["total"] == 50
        assert {c["itemid"] for c in rw["extra"]["availables"]} <= {hc.EP_ITEM, pid}
        mine = rw["extra"]["availables"][0]  # the opened card is credited
        assert (ep(), items()[0]["remains"]) == ((ep1 + 777, n1) if mine["itemid"] == hc.EP_ITEM else (ep1, n1 + 1))
        assert refused("match_rewards_set", result=res, cards=[[1, 2]]) and refused("match_rewards_set", result=res, cards=[])
        assert refused("match_rewards_set", result={}, cards=[[1, {"ep": 1}]])
        os.remove(hc.MATCH_REWARD_FILE)
        # --- Shop control (issue #10; user: "kontrol shop semua tab, bisa buat pack baru, paket baru
        # dll"): new pack / item / package / monthly with the client's icons, prices, hidden, tab lists
        sh = A("shop")
        assert sh["free"] and "8194" in sh["icons"] and {p["kind"] for p in sh["products"]} == set(hc.SHOP_KINDS)
        save = lambda kind, d, **k: A("shop_save", kind=kind, **k, **{"def": d})["itemid"]
        newpack = save("packs", {"name": "Tes WL", "icon": "8194", "seasons": [93], "top": 5, "grade": 3, "all": True})
        assert newpack == hc.SHOP_ID_BASE["packs"] + 1 and len(hc.pack_pool(newpack)) == 5
        assert any(e["product"]["itemid"] == newpack for e in hc.shop_list(hc._state()))
        assert refused("shop_save", kind="packs", **{"def": {"name": "kosong", "seasons": [93], "ovr": 130}})  # no card
        draftpack = save("packs", {"name": "Draft Tes", "icon": "200005", "seasons": [93], "draft": 3, "grade": 2, "all": True})
        assert hc.item_def(draftpack)["draft"] == {"season": 93, "grade": 2, "availables": 3}
        assert refused("shop_save", kind="packs", **{"def": {"name": "x", "seasons": [93, 91], "draft": 3}})  # one season
        capsule = save("items", {"name": "Kapsul Tes", "icon": "ID50071", "type": "PLAYER_EXP_CAPSULE", "exp": 500, "lv": 5,
                                 "season": 88})
        assert [hc.item_def(capsule)[k] for k in ("capsuleexp", "capsulelv", "capsuleseason")] == [500, 5, 88]
        assert refused("shop_save", kind="items", **{"def": {"name": "x", "icon": "nope", "type": "EP_LOTTERY", "ep": [1, 2]}})
        box = save("items", {"name": "Kotak Tes", "icon": "ID50121GP", "type": "ITEM_LOTTERY",
                             "prizes": [[1, newpack], [1, {"ep": 5000}]]})
        assert [a["itemid"] for a in hc.item_def(box)["availables"]] == [newpack, hc.EP_ITEM]
        pkg = save("packages", {"name": "Paket Tes", "icon": "801", "contents": [[box, 2], [hc.EP_ITEM, 1000]]})
        mon = save("monthly", {"name": "Bulanan Tes", "icon": "801", "days": 7, "now": [], "daily": [[newpack, 1]]})
        assert {e["shopcategory"] for e in hc.shop_list(hc._state()) if e["product"]["itemid"] in (box, pkg, mon)} == {
            "USE", "PACKAGE", "MONTHLYPACK"}
        ep1 = ep()
        assert post("/shop/purchase", {"shopid": pkg, "productid": pkg, "bunch": 0})["result"] and ep() == ep1 + 1000
        assert use(box)["result"] and use(box)["result"]
        A("shop_price", itemid=newpack, price=5000); assert hc.item_def(newpack)["bunches"][0]["price"] == 5000
        A("shop_price", itemid=newpack, price=None); assert hc.item_def(newpack)["bunches"][0]["price"] == 0
        A("shop_hide", itemid=8336, hidden=True)
        assert all(e["product"]["itemid"] != 8336 for e in hc.shop_list(hc._state()))
        assert not post("/shop/purchase", {"shopid": 8336, "productid": 8336, "bunch": 0})["result"]
        A("shop_hide", itemid=8336, hidden=False)
        save("items", {**hc.item_to(hc.ITEMS[501]), "name": "Lucky EP baru"}, itemid=501)  # a built-in, changed
        assert hc.item_def(501)["name"] == "Lucky EP baru"
        A("shop_delete", kind="items", itemid=501); assert hc.item_def(501)["name"] == "Lucky EP"  # back to the original
        assert refused("shop_delete", kind="packs", itemid=newpack)  # still a prize of the box
        A("shop_lists", lists={"new": [newpack, 501], "mp": [box], "chained": [[pkg, 801]]})
        assert hc.SHOP_NEW == (newpack, 501) and hc.MP_SHOP == (box,) and hc.CHAINED == {pkg: (pkg, 801)}
        assert refused("shop_lists", lists={"mp": [pkg]}) and refused("shop_lists", lists={"chained": [[newpack]]})
        A("shop_free", free=False); assert hc.item_def(8336)["bunches"][0]["price"] > 0; A("shop_free", free=True)
        hc.apply_shop(); assert newpack in hc.PACKS and hc.SHOP_NEW == (newpack, 501)  # all of it read back from the file
        # issue #15 + user: "tambahkan juga thai ,vietnam, korea": one string table per language
        err = admin.AdminError("e_day", ("day_n", 2), ("e_range", ("pack_count",), 1, 99))
        assert (err.text("en"), err.text(None), err.text("zh")) == (
            "Day 2: Pack count must be 1..99", "Hari 2: Jumlah pak harus 1..99", "第 2 天：卡包数量 必须在 1..99 之间")
        admin.check_i18n()
        assert set(admin.I18N) == {"id", "en", "zh", "th", "vi", "ko"}
        assert all("t_" + x in admin.I18N["id"] for x in hc.SHOP_ITEM_TYPES)  # a label for every item type
        hc.apply_shop({}); os.remove(hc.SHOP_FILE)  # the built-in Shop again
        # every Tim Cadangan card back to Tim inti at once (they went there by themselves while it held 36)
        st = hc._state(); next(p for p in team()["players"] if not hc.in_squad(team(), p))
        t = st["teams"][str(hc._default_slot(st))]; t["players"][-1]["team2"] = True; hc._save(st)
        assert A("team2_clear")["moved"] >= 1 and not any(p.get("team2") for p in team()["players"])
        st = hc._state(); hc.my_coach(st)["scout_used"] = {"vip": time.time()}; hc._save(st)
        assert [s["lock"] for s in A("summary")["scouts"]] == [False] * len(hc.SCOUTS)  # no cooldowns
        A("scouts_reset"); assert not any(s["lock"] for s in A("summary")["scouts"])
        assert len(A("log", n=5)["lines"]) <= 5
        # HTTP: reads are GETs; a change needs POST + X-FO3-Admin (a cross-site form can't add it)
        srv = admin.start(hc, 0)
        url, web = f"http://127.0.0.1:{srv.server_address[1]}", urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            page = web.open(url + "/").read()
            assert b"FO3ID admin" in page and b"/*I18N*/" not in page and b'"lang_name": "\\u7b80\\u4f53\\u4e2d\\u6587"' in page
            assert web.open(url + "/icon/8194.png").read()[:4] == b"\x89PNG"  # the client's shop icon
            err = urllib.request.Request(url + "/api/player_grade", b'{"id": "nope", "grade": 2}',
                                         {"X-FO3-Admin": "1", "X-FO3-Lang": "en"}, method="POST")
            assert json.load(web.open(err)) == {"error": "player not found"}
            assert json.load(web.open(url + "/api/summary"))["coach"]["ep"] == ep()
            for req in (urllib.request.Request(url + "/api/ep?add=5"),
                        urllib.request.Request(url + "/api/ep", b'{"add": 5}', method="POST")):
                try:
                    web.open(req); raise AssertionError("change without POST + header")
                except urllib.error.HTTPError as e:
                    assert e.code == 403
            ep1, hdr = ep(), {"X-FO3-Admin": "1", "Content-Type": "application/json"}
            assert json.load(web.open(urllib.request.Request(url + "/api/ep", b'{"add": 5}', hdr, method="POST")))["ep"] == ep1 + 5 == ep()
            assert json.load(web.open(urllib.request.Request(url + "/api/player_grade", b'{"id": "nope", "grade": 2}', hdr, method="POST"))) == {
                "error": "pemain tidak ditemukan"}
        finally:
            srv.shutdown(); srv.server_close()
        # --- Tim inti can hold the whole club; a new card joins Tim Cadangan ("-" in Skuad, user:
        # "neymar baru di pack harusnya jangan masuk res"), a login keeps the cards where they are,
        # and a Tim Cadangan card can always move to Tim inti
        assert hc.FIRST_TEAM_MAX == hc.MAX_PLAYERS
        st = hc._state(); t = st["teams"][str(hc._default_slot(st))]
        for p in t["players"]:
            p.pop("team2", None)
        while len(t["players"]) < 45:
            t["players"].append(dict(t["players"][-1], _id=hc.new_iid()))
        res = next(p for p in t["players"] if not hc.in_squad(t, p))
        res["team2"] = True
        hc._save(st)
        assert body(hc.ENDPOINTS[f"/coach/{hc._default_slot(st)}/default"]("", b""))["result"]
        t = hc._state()["teams"][str(hc._default_slot(st))]
        assert hc.first_team_count(t) == 44 and sum(bool(p.get("team2")) for p in t["players"]) == 1
        # the Skuad tab's move to Tim inti reads limits.firstTeam (missing = it never asks)
        assert hc.coach_me(hc._state(), hc._default_slot(hc._state()))["limits"]["firstTeam"] == hc.FIRST_TEAM_MAX
        new = hc.add_player(t, 88158023)
        assert new["team2"] and not next(p for p in hc.owned_team(t)["players"] if p["id"] == new["_id"]).get("state")
        hc._save(hc._state() | {"teams": {**hc._state()["teams"], str(hc._default_slot(st)): t}})
        res = next(p for p in t["players"] if p.get("team2"))
        assert body(hc.route(f"/player/{hc.iid(res)}/move/firstteam")("", b"{}"))["result"]
        # --- delete a manager: PUT /coach/<slot>/postponed -> "postpone" until hideat (restorable with
        # DELETE /coach/<_id>/postponed), then the slot is free and the club data goes with it
        slot = hc._default_slot(hc._state()); cid = hc.coach_id(slot)
        coaches = lambda: body(hc.ENDPOINTS["/coaches"]("", b""))
        mine_c = lambda: next((x for x in coaches()["coachlist"] if x["_id"] == cid), None)
        postpone = lambda key, method: body(hc.route(f"/coach/{key}/postponed")("", json.dumps({"_method": method}).encode()))
        assert mine_c()["recoveryperiod"] == hc.COACH_RECOVERY and "hideat" not in mine_c()
        # manager select screen: native LoadFrontPlayers needs teamid + frontplayer (captain, club kit)
        fp = mine_c()["frontplayer"]
        assert isinstance(fp["id"], str) and fp["kit"]["home"]["id"] == mine_c()["teamid"] << 5
        assert fp["spid"] and "preferredposition1" in fp["staticdata"]
        mine_team = hc.coach_me(hc._state(), slot)["team"]["players"]
        assert fp["spid"] == max(mine_team, key=lambda x: x.get("price", 0))["spid"]  # most valuable
        # Beginner's Guide league tutorial script: a JS source string, never "{}" (crashed native)
        assert body(hc.route("/static/bescript/campaign_tutorial01")("", b"")).startswith("function main()")
        # the startup notice popup passes url to native LoadWebAddress: never missing
        assert body(hc.route("/game/inweburl/notice")("", b""))["url"]
        assert postpone(slot, "PUT")["result"]
        assert mine_c()["state"] == "postpone" and mine_c()["hideat"].endswith(".000Z") and coaches()["defaultcoachid"] == ""
        assert postpone(cid, "DELETE")["result"] and mine_c()["state"] == "active" and coaches()["defaultcoachid"] == cid
        assert postpone(slot, "PUT")["result"]
        st = hc._state(); hc.my_coach(st)["deleteat"] = time.time() - 1; st["offers"] = []; hc._save(st)  # restore time over
        assert mine_c() is None and coaches()["defaultcoachid"] == ""
        st = hc._state(); assert str(slot) not in st["teams"] and "offers" not in st and "cups" not in st
        assert postpone(cid, "DELETE") == {"result": False, "reason": "already removed"}
    finally:
        shutil.rmtree(tmp)
    print("league + cup + market + upgrade + trade + trade3 + daily + shop + admin + coach delete OK")


if __name__ == "__main__":
    main()
