# -*- coding: utf-8 -*-
"""MIR001 C2 — STVARAN gpt-4o-mini nad SINTETIČKIM dugim, gustim podneskom (posle GATE-C2, 1. prolaz).

Poziva PRAVI routers.evidence._klasifikuj_ceo_dokument (produkcioni parametri: temperature 0, max_tokens iz koda).
Meri, k/N po upitu (novi = kod; stari = `_CLASSIFY_SYSTEM` sa `a30de1b2`, podmetnut samo u ovom procesu):
  • da li presudna kasna činjenica (priznanje duga, dopis 118/26) PREŽIVI granicu od 20 i bude tvrdnja;
  • da li je produkcioni lokator (`shared.evidence_write.lociraj_tvrdnju`) nalazi u tekstu;
  • udeo lociranih činjenica, prekide (`finish_reason == length`), tokene;
  • i vrstu dokumenta (`tip_dokaza`) za 7 kratkih Golden Case dokumenata, stari naspram novog upita.
Upotreba (iz korena repoa): python -X utf8 docs/v2-execution/MIR001_C2_STVARNI_MODEL.py <stari_upit.txt> <izlaz.json> [N]
Ključ iz .env glavnog repozitorijuma; nikad se ne ispisuje. Samo sintetički podaci."""
import json
import os
import random
import sys

ENV = os.environ.get("VINDEX_ENV_FILE", ".env")
for red in open(ENV, encoding="utf-8"):
    if red.startswith("OPENAI_API_KEY="):
        os.environ["OPENAI_API_KEY"] = red.split("=", 1)[1].strip().strip('"').strip("'")
for _k, _v in (("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "test-only"),
               ("SUPABASE_ANON_KEY", "test-only"), ("SUPABASE_JWT_SECRET", "test-only-jwt-secret-longer-than-32-chars"),
               ("FOUNDER_EMAILS", "founder@test.rs")):   # lažne vrednosti kao u tests/conftest.py — bez pristupa bazi
    os.environ[_k] = _v
sys.path.insert(0, os.getcwd())
import routers.evidence as ev  # noqa: E402
from shared.evidence_write import lociraj_tvrdnju  # noqa: E402
from tests import mir001_golden_case as gc  # noqa: E402

STARI_UPIT = open(sys.argv[1], encoding="utf-8").read()
NOVI_UPIT = ev._CLASSIFY_SYSTEM
N = int(sys.argv[3]) if len(sys.argv) > 3 else 5
PRESUDNA = ("Tuzeni je dopisom br. 118/26 od 03.03.2026. godine pismeno priznao dug prema tuziocu u iznosu od "
            "2.345.678,00 dinara i obavezao se da ga isplati do 31.03.2026. godine.")


def gust_tekst():
    rnd = random.Random(7)
    meseci = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    obrasci = [
        "Tuzilac je fakturom br. {n}/2025 od {d}.{m}.2025. zaracunao isporuku {k} tona profila u iznosu od {a}.000,00 dinara.",
        "Tuzeni je dana {d}.{m}.2025. uplatio {a}.000,00 dinara po fakturi br. {n}/2025, sto se vidi iz izvoda br. {k}.",
        "Otpremnicom br. {n} od {d}.{m}.2025. tuzeni je isporucio {k} tona profila na gradiliste u Zemunu.",
        "Dopisom od {d}.{m}.2025. tuzilac je reklamirao kvalitet {k} tona profila iz otpremnice br. {n}.",
        "Tuzeni je na reklamaciju od {d}.{m}.2025. odgovorio da profili odgovaraju standardu SRPS EN 10025.",
        "Kontrolor kvaliteta tuzioca sacinio je {d}.{m}.2025. zapisnik br. {n} o pregledu isporuke od {k} tona.",
    ]
    redovi = ["PRIVREDNI SUD U BEOGRADU", "TUZBA RADI NAPLATE (SINTETICKI PREDMET)",
              "Tuzilac Gradnja Invest DOO i tuzeni Metal Profil DOO zakljucili su 12.12.2024. Ugovor o isporuci br. 44/2024."]
    i = 0
    while len("\n".join(redovi)) < 16000:
        redovi.append(rnd.choice(obrasci).format(n=100 + i, d=f"{rnd.randint(1, 28):02d}", m=rnd.choice(meseci),
                                                 k=rnd.randint(2, 40), a=rnd.randint(100, 2000)))
        if len("\n".join(redovi)) > 12300 and PRESUDNA not in redovi:
            redovi.append(PRESUDNA)                                     # 4. prozor (11.400–15.400), usred konkurencije
        i += 1
    return "\n".join(redovi + ["Tuzilac, po punomocniku."])


upotreba = []
_pravi = ev._pozovi_evidence_api


def _meri(client, user_msg):
    r = _pravi(client, user_msg)
    upotreba.append({"ulaz": r.usage.prompt_tokens, "izlaz": r.usage.completion_tokens,
                     "prekinut": r.choices[0].finish_reason == "length"})
    return r


ev._pozovi_evidence_api = _meri


def lociran(tekst, c):
    return lociraj_tvrdnju(tekst, c).get("start_offset") is not None


T = gust_tekst()
izlaz = {"duzina": len(T), "pozicija_presudne": T.find(PRESUDNA), "presudna": PRESUDNA, "gust": {}, "golden_tip": {}}
for ime_upita, upit in (("stari_upit", STARI_UPIT), ("novi_upit", NOVI_UPIT)):
    ev._CLASSIFY_SYSTEM = upit
    uzorci = []
    for k in range(N):
        upotreba.clear()
        r = ev._klasifikuj_ceo_dokument("Tuzba.pdf", T)
        cin = r.get("kljucne_cinjenice") or []
        pres = [c for c in cin if "118/26" in c or "2.345.678" in c]
        uzorci.append({"cinjenice": cin, "ekstrakcija": (r.get("ai_tags") or {}).get("_ekstrakcija"), "pozivi": list(upotreba),
                       "presudna_tvrdnja": bool(pres), "presudna_locirana": any(lociran(T, c) for c in pres),
                       "locirano": sum(lociran(T, c) for c in cin), "ukupno": len(cin)})
        u = uzorci[-1]
        print(ime_upita, k, "presudna:", u["presudna_tvrdnja"], "locirana:", u["presudna_locirana"],
              f"locirano {u['locirano']}/{u['ukupno']}", "prekida:", sum(p["prekinut"] for p in u["pozivi"]), flush=True)
    izlaz["gust"][ime_upita] = uzorci
    tipovi = {}
    for dok in gc.DOKUMENTI:
        upotreba.clear()
        r = ev._klasifikuj_dokument(dok["ime"], "\n".join(dok["redovi"]))
        tipovi[dok["oznaka"]] = r.get("tip_dokaza")
    izlaz["golden_tip"][ime_upita] = tipovi
    print(ime_upita, "golden tip:", tipovi, flush=True)
json.dump(izlaz, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("duzina", len(T), "pozicija presudne", izlaz["pozicija_presudne"])
