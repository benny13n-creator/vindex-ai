# -*- coding: utf-8 -*-
"""MIR001 C2 — STVARAN gpt-4o-mini nad SINTETIČKIM dugim podneskom: da li pravi model, kada mu server pošalje kasni
prozor, izdvaja presudnu kasnu činjenicu. Poziva PRAVI routers.evidence._klasifikuj_ceo_dokument (i, radi poređenja,
stari put = jedan izvod od 1.500 znakova). Ključ iz .env glavnog repozitorijuma, nikad se ne ispisuje."""
import json
import os
import sys

ENV = os.environ.get("VINDEX_ENV_FILE", ".env")
for red in open(ENV, encoding="utf-8"):
    if red.startswith("OPENAI_API_KEY="):
        os.environ["OPENAI_API_KEY"] = red.split("=", 1)[1].strip().strip('"').strip("'")
for _k, _v in (("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "test-only"),
               ("SUPABASE_ANON_KEY", "test-only"), ("SUPABASE_JWT_SECRET", "test-only-jwt-secret-longer-than-32-chars"),
               ("FOUNDER_EMAILS", "founder@test.rs")):   # lažne vrednosti kao u tests/conftest.py — bez pristupa bazi
    os.environ[_k] = _v
sys.path.insert(0, r"C:\vindex-miroslav")
os.chdir(r"C:\vindex-miroslav")
import routers.evidence as ev  # noqa: E402

PAR = [
    "Tuzilac Gradnja Invest DOO iz Beograda i tuzeni Metal Profil DOO iz Novog Sada zakljucili su dana 12.12.2024. godine Ugovor o isporuci celicnih profila br. 44/2024.",
    "Ugovorom je predvidjeno da tuzeni isporuci 120 tona profila u tri ture, a da tuzilac plati cenu u roku od 30 dana od svake isporuke.",
    "Prva tura isporucena je 15.01.2025. godine i tuzilac ju je platio u celosti, sto tuzeni ne spori.",
    "Druga tura isporucena je sa zakasnjenjem od 19 dana, o cemu je sacinjen zapisnik o primopredaji koji su potpisali ovlasceni predstavnici obe strane.",
    "Tuzilac je u vise navrata usmeno i pisanim putem ukazivao tuzenom na neispunjenje ugovornih obaveza i trazio izjasnjenje.",
    "Tuzeni se na dopise nije izjasnio u ostavljenom roku, niti je predlozio novi plan isporuke ili sporazumno resenje.",
    "Treca tura nikada nije isporucena, iako je tuzilac za nju avansno uplatio deo cene, sto se vidi iz izvoda sa racuna.",
    "Tuzilac je zbog izostanka isporuke morao da nabavi profile od drugog dobavljaca po visoj ceni, cime mu je nastala steta.",
    "Visina stete bice precizirana nakon vestacenja, a tuzilac za sada postavlja zahtev u iznosu koji odgovara razlici u ceni.",
    "Ugovorom je ugovorena nadleznost Privrednog suda u Beogradu za sve sporove koji proisteknu iz ovog ugovornog odnosa.",
    "Tuzilac predlaze da sud izvede dokaz citanjem ugovora, zapisnika o primopredaji, dopisa stranaka i izvoda sa racuna.",
    "Tuzilac predlaze i saslusanje zakonskog zastupnika tuzioca i zakonskog zastupnika tuzenog o okolnostima izvrsenja ugovora.",
]
KASNA = ("Odlucno je da je tuzeni dopisom br. 118/26 od 03.03.2026. godine pismeno i bezuslovno priznao dug prema tuziocu "
         "u iznosu od 2.345.678,00 dinara, sa obavezom da ga isplati do 31.03.2026. godine, sto nije ucinio.")


PAR += [
    "Dana 20.02.2025. godine tuzilac je tuzenom uputio prvu opomenu preporucenom posiljkom, koju je tuzeni primio 24.02.2025.",
    "Tuzeni je dopisom od 10.03.2025. naveo da kasni zbog problema sa sopstvenim dobavljacem sirovine iz inostranstva.",
    "Stranke su 02.04.2025. odrzale sastanak u prostorijama tuzioca, o cemu postoji beleska koju je sacinio tuzilac.",
    "Na sastanku je tuzeni obecao da ce trecu turu isporuciti najkasnije do 30.06.2025. godine.",
    "Tuzilac je 15.07.2025. tuzenom uputio drugu opomenu sa naknadnim rokom od 15 dana za ispunjenje obaveze.",
    "Tuzeni u naknadnom roku nije isporucio robu niti je vratio primljeni avans od 1.200.000,00 dinara.",
    "Tuzilac je 05.09.2025. izjavio da raskida ugovor u delu koji se odnosi na trecu turu, zbog neispunjenja.",
    "Zamenski dobavljac Celik Trade DOO isporucio je tuziocu 40 tona profila po ceni vecoj za 18 odsto od ugovorene.",
    "Tuzilac je 20.11.2025. pokusao vansudsko poravnanje posredstvom Privredne komore Srbije, ali tuzeni nije pristupio.",
    "Medijacija zakazana za 15.12.2025. obustavljena je jer se tuzeni nije odazvao pozivu medijatora.",
    "Tuzilac je 10.01.2026. od tuzenog zatrazio izvod otvorenih stavki radi uskladjivanja medjusobnih potrazivanja.",
    "Tuzeni je izvod otvorenih stavki dostavio 25.01.2026., bez primedbi na iskazano dugovanje.",
    "Tuzilac je 10.02.2026. angazovao advokata radi naplate potrazivanja i pokretanja sudskog postupka.",
    "Advokat tuzioca je 20.02.2026. uputio tuzenom opomenu pred utuzenje sa rokom od osam dana.",
    "Kvalitet isporucenih profila iz prve i druge ture nije bio sporan i tuzilac ih je ugradio u objekat u Zemunu.",
    "Objekat u Zemunu gradi se po gradjevinskoj dozvoli br. ROP-BGD-1234-CPI-2/2024 izdatoj od Gradske uprave.",
    "Zbog kasnjenja profila tuzilac je kasnio sa izvodjenjem radova prema investitoru Zemun Park DOO.",
    "Investitor je tuziocu zaracunao ugovornu kaznu od 450.000,00 dinara fakturom od 30.09.2025. godine.",
    "Tuzilac je ugovornu kaznu platio investitoru 15.10.2025., sto ce dokazati izvodom sa racuna.",
    "Tuzilac smatra da je ugovorna kazna direktna posledica docnje tuzenog i trazi njenu naknadu kao stetu.",
    "Ugovorom izmedju stranaka nije ugovorena ugovorna kazna za docnju, vec samo pravo na naknadu stete.",
    "Tuzeni je u dopisu od 10.03.2025. sam priznao da kasni, ali je kasnjenje pripisao visoj sili.",
    "Tuzilac osporava da je rec o visoj sili jer je problem sa dobavljacem bio predvidiv i otklonjiv.",
    "Tuzeni nije obavestio tuzioca o nastupanju vise sile u roku propisanom clanom 9 ugovora.",
    "Tuzilac je pre podnosenja tuzbe proverio bonitet tuzenog i utvrdio da racun tuzenog nije blokiran.",
    "Vrednost predmeta spora tuzilac oznacava na iznos od 3.995.678,00 dinara.",
    "Tuzilac je platio sudsku taksu na tuzbu, sto dokazuje priloženim nalogom za uplatu.",
    "Tuzilac predlaze da sud odredi privremenu meru zabrane raspolaganja sredstvima tuzenog do iznosa duga.",
]


def tekst():
    t = []
    for p in PAR:
        if len("\n".join(t)) >= 5200:
            break
        t.append(p)
    return "PRIVREDNI SUD U BEOGRADU\nTUZBA (SINTETICKI PREDMET)\n" + "\n".join(t) + "\n" + KASNA + "\nTuzilac, po punomocniku."


T = tekst()
poz = " ".join(T.split()).find("Odlucno je da je tuzeni")
upotreba = []
_pravi = ev._pozovi_evidence_api


def _meri(client, user_msg):
    r = _pravi(client, user_msg)
    upotreba.append([r.usage.prompt_tokens, r.usage.completion_tokens])
    return r


ev._pozovi_evidence_api = _meri
izlaz = {"duzina": len(T), "pozicija_kasne": poz, "novi_put": [], "stari_put": []}
for k in range(5):
    upotreba.clear()
    r = ev._klasifikuj_ceo_dokument("Tuzba.pdf", T)
    izlaz["novi_put"].append({"cinjenice": r.get("kljucne_cinjenice"), "ekstrakcija": r["ai_tags"].get("_ekstrakcija"),
                              "tokeni": list(upotreba),
                              "kasna_izdvojena": any(("2.345.678" in c or "118/26" in c) for c in r.get("kljucne_cinjenice") or [])})
    upotreba.clear()
    s = ev._klasifikuj_dokument("Tuzba.pdf", T[:1500])
    izlaz["stari_put"].append({"cinjenice": s.get("kljucne_cinjenice"), "tokeni": list(upotreba),
                               "kasna_izdvojena": any("2.345.678" in c or "118/26" in c for c in s.get("kljucne_cinjenice") or [])})
    print(k, "novi:", izlaz["novi_put"][-1]["kasna_izdvojena"], "stari:", izlaz["stari_put"][-1]["kasna_izdvojena"], flush=True)
json.dump(izlaz, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("duzina", len(T), "pozicija", poz)
