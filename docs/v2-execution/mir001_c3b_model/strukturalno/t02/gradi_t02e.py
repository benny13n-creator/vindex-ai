"""Gradi specifikaciju mutacija za 3. krug TASK-02 iz tačnih redova koda i proverava da se svaki javlja tačno jednom."""
import os
import json
import re

S = os.environ.get("VINDEX_SCRATCH", ".").rstrip("/") + "/"
F = "shared/nacrt_za_sud.py"
kod = open(F, encoding="utf-8").read()


def red(pocetak: str) -> str:
    """Ceo red koji počinje datim tekstom (tačno jedan)."""
    nadjeni = [l for l in kod.split("\n") if l.startswith(pocetak)]
    assert len(nadjeni) == 1, (pocetak, len(nadjeni))
    return nadjeni[0]


M = []


def mut(ime, fajl, old, new):
    M.append({"ime": ime, "fajl": fajl, "old": old, "new": new})


stara = json.load(open(S + "t02c_mut.json", encoding="utf-8"))
zadrzi = {"Y1", "Y2", "Y3", "Y4", "Y5", "Y6", "Y10", "Y11", "Y12", "Y14", "Y15", "Y17", "Y21",
          "Y22", "Y23", "Y24", "Y25", "Y26", "Y28", "Y29", "Y30", "Y31", "Y32", "Y33", "Y34", "Y35", "Y36"}
for m in stara["mutacije"]:
    if m["ime"].split()[0] in zadrzi:
        M.append(m)
# usklađene i nove
mut("Y9 rok ostaje", F, "    if _RE_ROK.search(bez) and not _izvor_kaze(_RE_ROK):", "    if False:")
mut("Y18 odustanak ostaje", F, "    if ima_nalog and _RE_ODUSTANAK.search(bez) and not priznaje and not _izvor_kaze(_RE_ODUSTANAK):", "    if False:")
mut("Y7 uplata ostaje", F, "    if (_RE_UPLATA.search(bez) or (nalog_o_uplati and", "    if (False and (nalog_o_uplati and")
mut("Y8 izvrsenje ostaje", F, "    if izvrsenje and not _izvor_kaze(_RE_STANJE, grupe_rec or None):", "    if False:")
mut("Y13 nepotrebnost bez izricitog priznanja", F, "and _RE_NEPOTREBNO.search(bez) and not (priznaje_jasno and stav and",
    "and _RE_NEPOTREBNO.search(bez) and not (priznaje and stav and")
mut("Y19 pravilo predmeta iskljuceno", F, "    if o_predmetu and not ((stav and priznaje_jasno and not _RE_STANJE.search(bez)) or pripisano or parafraza",
    "    if False and not ((stav and priznaje_jasno and not _RE_STANJE.search(bez)) or pripisano or parafraza")
mut("Y20 pravilo predmeta stav bez priznanja", F, "    if o_predmetu and not ((stav and priznaje_jasno and",
    "    if o_predmetu and not ((stav and")
mut("Z1 dejstvo ostaje", F, "    if (ima_nalog or o_stanju) and _RE_DEJSTVO.search(bez):", "    if False:")
mut("Z2 navod bez provere izvora", F, "    preneseno = bool(_RE_PRENESENO.search(bez)) and (bool(izvori) or dok_navoda)",
    "    preneseno = bool(_RE_PRENESENO.search(bez)) and bool(_RE_DOK.search(seg) or tokeni)")
mut("Z3 izvor ne mora da sadrzi tvrdnju", F, "            rx.search(_n(d[\"izvod\"])) and (grupe is None or grupe & _grupe(_n(d[\"izvod\"]))) for d in izvori)",
    "            True for d in izvori)")
mut("Z4 izvor bez grupe radnje", F, "            rx.search(_n(d[\"izvod\"])) and (grupe is None or grupe & _grupe(_n(d[\"izvod\"]))) for d in izvori)",
    "            rx.search(_n(d[\"izvod\"])) for d in izvori)")
mut("Z5 bez prenosa predmeta na zamenicu", F,
    "    o_stanju = o_predmetu or (ima_nalog and prethodni_predmet and (not sadrzaj or bool(_RE_ANAFORA.search(bez))))",
    "    o_stanju = o_predmetu")
mut("Z6 izricito priznanje = bilo koja oznaka DOK", F, red("    priznaje_jasno = sudski_tok or parafraza"),
    "    priznaje_jasno = priznaje")
mut("Z7 parafraza bez uloga stranaka", F, "            return osn <= o and uloge <= u and (sudski_tok or bool(osn - _OPSTE_UVEK))",
    "            return osn <= o and (sudski_tok or bool(osn - _OPSTE_UVEK))")
mut("Z8 prozor parafraze stane na oznaci/zagradi", F,
    "        prozor = re.split(r\"[,;.]|\\b(?:jer|pa|te|a|cime|sto|time)\\b\", ostatak, maxsplit=1)[0]",
    "        prozor = re.split(r\"[,;.()|]|\\b(?:jer|pa|te|a|cime|sto|time)\\b\", bez_s[m.end():], maxsplit=1)[0]")
mut("Z9 opste reci su sadrzaj", F, "    sadrzaj = osn_rec - _OPSTE_UVEK - {w[:5]", "    sadrzaj = osn_rec - {w[:5]")
mut("Z10 uplata drugim recima ostaje", F, "    if (_RE_UPLATA.search(bez) or (nalog_o_uplati and", "    if (_RE_UPLATA.search(bez) or (False and")
mut("Z11 opsti glagol izvrsenja ne vazi za svaki nalog", F,
    "        bool(grupe_rec & grupe_naloga) or (\"IZVRSENJE\" in grupe_rec and o_predmetu and not navodima)",
    "        bool(grupe_rec & grupe_naloga)")
mut("Z12 sinonimi predmeta iskljuceni", F, "    for rx, osn in _SINONIMI:", "    for rx, osn in ():")
mut("Z13 parafraza bez razlikujuce reci", F, "            return osn <= o and uloge <= u and (sudski_tok or bool(osn - _OPSTE_UVEK))",
    "            return osn <= o and uloge <= u")

for m in M:
    b = open(m["fajl"], "rb").read().decode("utf-8")
    o = m["old"].replace("\n", "\r\n") if "\r\n" in b else m["old"]
    assert b.count(o) == 1, (m["ime"], b.count(o))
spec = {"cmd": stara["cmd"], "mutacije": M}
json.dump(spec, open(S + "t02e_mut.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(M), "mutacija, sve jedinstvene")
