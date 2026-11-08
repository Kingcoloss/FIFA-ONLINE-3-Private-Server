"""Golden data for the .NET PyRandom port, drawn by the real Python server.

Writes two files into tests/FO3.Domain.Tests/Golden/:
  pyrandom.json   - CPython random.Random draws for int and str seeds, method by method
  vm_spike.json   - the virtual-manager crowd, their Rank games, the AI clubs, club points and
                    market prices, computed by http_config.py itself (inputs included)

Run from anywhere:  python dotnetVersion/tools/golden/gen_pyrandom_golden.py
The card catalogue (fifadb) is not needed: vm_thirds() is replaced by fixed team lists, which
only changes the team ids drawn, not the number of draws.
"""
import copy
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(HERE, "..", "..", "tests", "FO3.Domain.Tests", "Golden")
sys.path.insert(0, ROOT)

SEEDS = [("int", 0), ("int", 1), ("int", 30), ("int", -5), ("int", 2**32 + 7), ("int", 2**100 + 12345),
         ("str", ""), ("str", "vm0001/skill"), ("str", "30/extra"), ("str", "vmjoin/3"), ("str", "clubnames"),
         ("str", "price/230000123/5"), ("str", "clubofvm0042"), ("str", "seen:vm0007:20"),
         ("str", "ทดสอบ/ไทย"), ("str", "board:vm4999:20261108")]

OPS = [["random"], ["random"], ["randint", -60, 60], ["randint", 0, 0], ["randint", 0, 1], ["randint", 1000, 1250],
       ["randint", 3600, 72000], ["randint", 0, 2**40], ["randint", 0, 2**62], ["randrange", 7], ["randrange", 1, 20],
       ["randrange", 0, 100, 7], ["randrange", 10, -10, -3], ["uniform", 0.5, 1.5], ["uniform", -0.003, 0.003],
       ["choice", 19], ["choice", 1], ["shuffle", 10], ["shuffle", 200], ["sample", 50, 5], ["sample", 30, 25],
       ["sample", 1000, 100], ["sample", 300, 10], ["choices", [6, 3, 1], 1], ["choices", [0.7, 0.25, 0.05], 3],
       ["choices", [1 / (k + 10) for k in range(60)], 2], ["choices", None, 4]]


def run_op(r, op):
    name, *args = op
    if name == "random":
        return r.random()
    if name in ("randint", "randrange", "uniform"):
        return getattr(r, name)(*args)
    if name == "choice":
        return r.choice(range(args[0]))
    if name == "shuffle":
        x = list(range(args[0]))
        r.shuffle(x)
        return x
    if name == "sample":
        return r.sample(range(args[0]), args[1])
    if name == "choices":
        weights, k = args
        n = len(weights) if weights else 5
        return r.choices(range(n), weights, k=k)
    raise ValueError(name)


def primitives():
    cases = []
    for kind, seed in SEEDS:
        r = random.Random(seed)
        cases.append({"kind": kind, "seed": str(seed), "ops": OPS, "out": [run_op(r, op) for op in OPS]})
    r = random.Random(30)  # long run: several 624-word refills
    return {"cases": cases, "longrun": {"seed": "30", "random": [r.random() for _ in range(3000)]}}


def vm_spike():
    import http_config as hc
    thirds = (list(range(1000, 1037)), list(range(2000, 2041)), list(range(3000, 3029)))
    hc.vm_thirds = lambda: thirds
    base, extra = copy.deepcopy(hc.vm_base()), copy.deepcopy(hc.vm_extra())
    newcomers = hc.vm_newcomers(60)

    played = copy.deepcopy(base)
    for vm in played[:50]:
        for d in (1, 2, 3):
            hc.vm_play(vm, 202611, d, 1)
    for vm in played[50:]:
        for d in (1, 2):
            hc.vm_play(vm, 202611, d, 1, joined=(2, 10))
        hc.vm_play(vm, 202611, 3, 1, hour=12)

    crowd = base + extra
    hc.virtual_managers = lambda: crowd
    hc.club_line = lambda *a, **k: ""
    clubs = hc.ai_clubs(10, "en")
    ids = [m["_id"] for m in crowd]
    return {
        "inputs": {
            "VM_SEED": hc.VM_SEED, "VM_COUNT": hc.VM_COUNT, "LADDER_COUNT": hc.LADDER_COUNT,
            "VM_TIERS": hc.VM_TIERS, "THIRDS": thirds,
            "VM_WORDS": hc.VM_WORDS, "VM_TAGS": hc.VM_TAGS, "VM_WORDS2": hc.VM_WORDS2, "VM_TAGS2": hc.VM_TAGS2,
            "VM_WORDS3": hc.VM_WORDS3, "VM_NAMES3_MASKED": sorted(hc.VM_NAMES3_MASKED),
            "VM_EXTRA": hc.VM_EXTRA, "VM_EXTRA_ID": hc.VM_EXTRA_ID, "VM_EXTRA2": hc.VM_EXTRA2,
            "VM_EXTRA2_ID": hc.VM_EXTRA2_ID, "VM_MAX": hc.VM_MAX, "VM_JOIN": hc.VM_JOIN,
            "VM_JOIN_TIER": hc.VM_JOIN_TIER, "VM_GAMES": hc.VM_GAMES, "VM_HOURS": hc.VM_HOURS,
            "LADDER_START": hc.LADDER_START, "LADDER_K": hc.LADDER_K, "VM_EPOCH": hc.VM_EPOCH,
            "CLUB_AI": hc.CLUB_AI, "CLUB_IN": hc.CLUB_IN, "CLUB_LIMIT": hc.CLUB_LIMIT, "CLUB_EXPAND": hc.CLUB_EXPAND,
            "CLUB_SUFFIX": hc.CLUB_SUFFIX, "CLUB_COLORS": hc.CLUB_COLORS,
            "VM_PERSONALITIES": hc.VM_PERSONALITIES, "VM_STYLES": sorted(hc.VM_STYLES),
            "KOTH_LEAVES": sorted(hc.KOTH_LEAVES),
        },
        "base": base, "extra": extra,
        "newcomers": [{"day": d, "hour": h, "vm": vm} for d, h, vm in newcomers],
        "played": played,
        "skill": {v: hc.vm_skill(v) for v in ids},
        "personality": {v: hc.vm_personality({"_id": v}) for v in ids},
        "style": {v: hc.vm_style({"_id": v}) for v in ids},
        "region": {v: hc.vm_region(v) for v in ids},
        "club_points": {v: [hc.club_vm_points(v, 0, 20), hc.club_vm_points(v, 15, 20)] for v in ids},
        "clubs": [{"_id": c["_id"], "name": c["name"], "created": c["created"], "color": c["color"],
                   "allowjoin": c["allowjoin"], "limit": c["limit"],
                   "members": [{"id": m["id"], "joined": m["joined"], "grade": m["grade"]} for m in c["members"]]}
                  for c in clubs.values()],
        "market": [{"spid": s, "grade": g, "day": d, "factor": hc.market_factor(s, g, d)}
                   for s in (101000001, 230000123, 300190042) for g in (1, 5, 10) for d in range(0, 40, 3)],
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, data in (("pyrandom.json", primitives()), ("vm_spike.json", vm_spike())):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(name, os.path.getsize(os.path.join(OUT, name)), "bytes")
    print("python", sys.version.split()[0])


if __name__ == "__main__":
    main()
