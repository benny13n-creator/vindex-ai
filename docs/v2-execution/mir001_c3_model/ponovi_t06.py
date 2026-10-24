"""TASK-06 — merila UPISANA PRE POKRETANJA. 5 uzoraka stvarnog gpt-4o (parametri proizvoda) nad tačnim promptom savetnika
„Pisanje podnesaka“ za izjašnjenje tužioca na nalaz veštaka (Golden Case).
Upotreba: python -I ponovi_t06.py snimak_t06.json izlaz.json   |   python -I ponovi_t06.py --oceni izlaz.json"""
import json
import os
import re
import sys

MERILA = {
    "D1_izvori_dok05_dok06": lambda o: "DOK-05" in o and "DOK-06" in o,
    "D2_nalaz_hidroizolacija": lambda o: "hidroizolacij" in o.lower(),
    "D3_bez_izmisljene_adrese": lambda o: not any(re.search(r"\b(ulica|ul\.|bulevar|br\.\s*\d+[a-z]?\b)", l, re.I) and "PROVERITI" not in l
                                                   for l in o.splitlines()),
    "D4_oznaka_proveriti": lambda o: "[PROVERITI" in o,
    "D5_zaglavlje_sud_broj": lambda o: re.search(r"PRIVREDN\w* SUD", o, re.I) is not None and "P 9901/2026" in o,
    "D6_rociste": lambda o: "18.11.2026" in o,
    "D7_vestak_ne_utvrdjuje": lambda o: re.search(r"vešta\w*\s+(je\s+)?(utvrdi\w*|potvrdi\w*)", o, re.I) is None,
    "D8_osporavanje_tuzenog": lambda o: re.search(r"osporav", o, re.I) is not None,
    "D9_bez_procenata": lambda o: re.search(r"\d+\s*%", o) is None,
    "D10_bez_nepotvrdjenog_clana_zakona": lambda o: not any(
        re.search(r"(čl\.|član\w*)\s*\d+[^\n]{0,25}(ZOO|ZPP|Zakon)", l, re.I) and "PROVERITI" not in l for l in o.splitlines()),
    "D11_ai_upozorenje": lambda o: "mora ga pregledati" in o,
    # dodato POSLE ručnog čitanja prvog kruga (uzorci_t06.json): zastareo procesni predlog, DOK-07, šira provera „utvrdio“
    "D12_ne_trazi_vec_odluceno": lambda o: not any(re.search(r"(odbij\w*|protiv\w*|nepotreb\w*)[^\n]{0,80}dopun", l, re.I)
                                                    and not re.search(r"(već|vec)\s+prihvat", l, re.I) for l in o.splitlines()),
    "D13_procesno_stanje_dok07": lambda o: "DOK-07" in o,
    "D7b_bez_utvrdio_uz_vestaka": lambda o: re.search(r"vešta\w*[^.\n]{0,40}(utvrdi\w*|potvrdi\w*)", o, re.I) is None,
}


def oceni(o):
    return {n: bool(f(o)) for n, f in MERILA.items()}


if sys.argv[1] == "--oceni":
    d = json.load(open(sys.argv[2], encoding="utf-8"))
    tot = ok = 0
    for x in d["N"]:
        m = oceni(x["odgovor"]); tot += len(m); ok += sum(m.values())
        print(sorted(n for n, v in m.items() if not v))
    print("UKUPNO", ok, "/", tot)
    sys.exit(0)

ENV = os.environ.get("VINDEX_ENV_FILE", ".env")
for red in open(ENV, encoding="utf-8"):
    if red.startswith("OPENAI_API_KEY="):
        os.environ["OPENAI_API_KEY"] = red.split("=", 1)[1].strip().strip('"').strip("'")
from openai import OpenAI  # noqa: E402

p = json.load(open(sys.argv[1], encoding="utf-8"))["N"]["poruka"]
k = OpenAI()
out = {"N": []}
for _ in range(5):
    r = k.chat.completions.create(model="gpt-4o", temperature=0.35, max_tokens=2000,
                                  messages=[{"role": "system", "content": p["system"]}, {"role": "user", "content": p["user"]}])
    o = r.choices[0].message.content
    out["N"].append({"odgovor": o, "merila": oceni(o)})
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("gotovo")
