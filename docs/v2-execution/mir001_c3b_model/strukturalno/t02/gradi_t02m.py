"""Pun skup mutacija TASK-02 nad konačnim kodom (GATE-02 5. prolaz N5): 47 iz 3. kruga + 15 iz 5. kruga + H11."""
import os
import json

S = os.environ.get("VINDEX_SCRATCH", ".").rstrip("/") + "/"
ld = lambda f: json.load(open(S + f, encoding="utf-8"))["mutacije"]
e, e3, j, l = ld("t02e_mut.json"), ld("t02e3_mut.json"), ld("t02j_mut.json"), ld("t02l_mut.json")
imena_e = [m["ime"].split()[0] for m in e]
M = e[:imena_e.index("Y23")] + [l[0]] + e3[1:]
STARI = "        if len(blok) == 1 and _RE_SAMO_AI.search(k) and not naslov:"
NOVI = "        if len(blok) == 1 and _RE_SAMO_AI.search(k) and _RE_RED_O_NACRTU.match(k) and not naslov:"
for m in j:
    m = dict(m)
    if m["old"] == STARI:
        m["old"] = NOVI
        if m["ime"].startswith("H3 "):
            m["new"] = "        if len(blok) == 1 and not naslov:"
    M.append(m)
M += [m for m in ld("t02g_mut.json") if m["ime"].split()[0] in ("G9", "G10", "G11")]
M.append({"ime": "H11 mesan red sa oznakom AI bez cuvara", "fajl": "shared/nacrt_za_sud.py", "old": NOVI,
          "new": "        if len(blok) == 1 and _RE_SAMO_AI.search(k) and not naslov:"})
for m in M:
    f = open(m["fajl"], "rb").read().decode("utf-8")
    o = m["old"].replace("\n", "\r\n") if "\r\n" in f else m["old"]
    assert f.count(o) == 1, (m["ime"], f.count(o))
assert len({m["ime"] for m in M}) == len(M)
json.dump({"cmd": json.load(open(S + "t02e_mut.json", encoding="utf-8"))["cmd"], "mutacije": M},
          open(S + "t02m_mut.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(M), "mutacija, sve jedinstvene")
