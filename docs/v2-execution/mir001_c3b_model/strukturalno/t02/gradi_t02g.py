"""Mutacije 4. kruga TASK-02 (GATE-02 3. prolaz: polaritet, blok napomena, glagoli predaje)."""
import os
import json

S = os.environ.get("VINDEX_SCRATCH", ".").rstrip("/") + "/"
F = "shared/nacrt_za_sud.py"
M = []


def mut(ime, old, new):
    M.append({"ime": ime, "fajl": F, "old": old, "new": new})


mut("G1 polaritet se ne proverava", "            and pol <= _polaritet(_n(d[\"izvod\"]), rx) for d in izvori)",
    "            for d in izvori)")
mut("G2 negacija ispred se ne vidi", "    return {\"-\" if (_RE_NEG_U.search(m.group()) or _RE_NEG_ISPRED.search(t[max(0, m.start() - 40):m.start()]))",
    "    return {\"-\" if (_RE_NEG_U.search(m.group()))")
mut("G3 blok bez nastavka", "        while j < len(redovi) and redovi[j].strip() and (naslov or",
    "        while False and (naslov or")
mut("G4 naslov sa dvotackom ne nastavlja", "        naslov = red.rstrip().endswith(\":\")", "        naslov = False")
mut("G5 blok bez cuvara", "        if len(blok) > 1 or \"(natpis uklonjen)\" in red:", "        if False:")
mut("G6 lazna granica bez cuvara", "        if len(blok) > 1 or \"(natpis uklonjen)\" in red:", "        if len(blok) > 1:")
mut("G7 mnozina/varijante naslova", r'''_RE_INTERNO = re.compile(r"⚠|napomen\w*\s+za\s+advokat\w*|interne?\s+napomen\w*|upozorenj\w*\s+za\s+advokat\w*"''',
    r'''_RE_INTERNO = re.compile(r"⚠|napomena\s+za\s+advokata|interne?\s+napomenX|upozorenjX\s+za\s+advokat\w*"''')
mut("G8 naslov Napomena:", r'''                         r"|^\W*(?:napomen[ae]|upozorenj[ea]|interno|za\s+advokata)\s*:|\(natpis\s+uklonjen\)|ukloniti''',
    r'''                         r"|\(natpis\s+uklonjen\)|ukloniti''')
mut("G9 glagoli predaje/prijema", r'''                        r"nije\s+preduze\w*|predao|predala|predat\w*|stigl\w*|stigao|primio|primila|primljen\w*|"
                        r"zaprimljen\w*)\b")''', r'''                        r"nije\s+preduze\w*)\b")''')
mut("G10 trazena/pomenuta kao anafora", r'''                         r"trazen\w*|pomenut\w*|naveden\w*)\b")''', r'''                         r"XXXX)\b")''')
mut("G11 neutralizacija oznake bloka", '''    t = (tekst or "").replace(_SEP, "").replace(_BLOK, "")''', '''    t = (tekst or "").replace(_SEP, "")''')

for m in M:
    b = open(m["fajl"], "rb").read().decode("utf-8")
    o = m["old"].replace("\n", "\r\n") if "\r\n" in b else m["old"]
    assert b.count(o) == 1, (m["ime"], b.count(o))
stara = json.load(open(S + "t02e_mut.json", encoding="utf-8"))
json.dump({"cmd": stara["cmd"], "mutacije": M}, open(S + "t02g_mut.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(M), "mutacija, sve jedinstvene")
