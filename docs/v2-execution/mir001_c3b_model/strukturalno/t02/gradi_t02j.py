"""Mutacije 5. kruga TASK-02 (GATE-02 4. prolaz) + G-mutacije preusmerene na izmenjene redove."""
import os
import json

S = os.environ.get("VINDEX_SCRATCH", ".").rstrip("/") + "/"
F = "shared/nacrt_za_sud.py"
M = []


def mut(ime, old, new):
    M.append({"ime": ime, "fajl": F, "old": old, "new": new})


mut("G1 polaritet se ne proverava", '            and pol <= _polaritet(_n(d["izvod"]), rx) for d in izvori)',
    "            for d in izvori)")
mut("G2 negacija ispred se ne vidi", "        elif _RE_NEG_U.search(m.group()) or _RE_NEG_U.search(pre):",
    "        elif _RE_NEG_U.search(m.group()):")
mut("G3 blok bez nastavka", "        while j < len(redovi) and redovi[j].strip() and (naslov or",
    "        while False and (naslov or")
mut("G4 naslov ne nastavlja", r'''        while j < len(redovi) and redovi[j].strip() and (naslov or re.match(''',
    r'''        while j < len(redovi) and redovi[j].strip() and (False or re.match(''')
mut("G5 premesteno bez cuvara", "        if len(blok) == 1 and _RE_SAMO_AI.search(k) and not naslov:",
    "        if True:")
mut("H1 markdown se ne skida", r'''        k = _n(re.sub(r"[*#_>`]+", " ", red)).strip()''', "        k = _n(red).strip()")
mut("H2 naslov bez dvotacke se ne prepoznaje", "        naslov = bool(_RE_NASLOV.match(k)) or (bool(_RE_INTERNO.search(k)) and k.endswith(\":\"))",
    "        naslov = bool(_RE_INTERNO.search(k)) and k.endswith(\":\")")
mut("H3 izolovan red bez cuvara", "        if len(blok) == 1 and _RE_SAMO_AI.search(k) and not naslov:",
    "        if len(blok) == 1 and not naslov:")
mut("H4 ai red dobija cuvar", "        if len(blok) == 1 and _RE_SAMO_AI.search(k) and not naslov:", "        if False:")
mut("H5 napomena u istom redu", " or _RE_NAPOMENA_U_REDU.search(k)):", "):")
mut("H6 modalitet se ne vidi", "        if _RE_MODAL.search(pre) or _RE_MODAL.search(m.group()):", "        if False:")
mut("H7 prozor 3 reci", "        pre = \" \".join(_RE_KLAUZA.split(t[:m.start()])[-1].split()[-6:])",
    "        pre = \" \".join(_RE_KLAUZA.split(t[:m.start()])[-1].split()[-3:])")
mut("H8 bez granice klauze", "        pre = \" \".join(_RE_KLAUZA.split(t[:m.start()])[-1].split()[-6:])",
    "        pre = \" \".join(t[:m.start()].split()[-6:])")
mut("H9 interna (a) napomena", r'''|intern[aei]\s+napomen\w*|upozorenj\w*\s+za\s+advokat\w*"''',
    r'''|interne?\s+napomenX|upozorenj\w*\s+za\s+advokat\w*"''')
mut("H10 model nije procitao", r'''|\bmodel\w*\s+(?:nije|ni|ne)\s+(?:procit|pregled|potvrd|uzeo)\w*|''', "|")

for m in M:
    b = open(m["fajl"], "rb").read().decode("utf-8")
    o = m["old"].replace("\n", "\r\n") if "\r\n" in b else m["old"]
    assert b.count(o) == 1, (m["ime"], b.count(o))
stara = json.load(open(S + "t02e_mut.json", encoding="utf-8"))
json.dump({"cmd": stara["cmd"], "mutacije": M}, open(S + "t02j_mut.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(M), "mutacija, sve jedinstvene")
