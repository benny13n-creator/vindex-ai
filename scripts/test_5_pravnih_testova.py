#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — 5 brutalnih pravnih testova za advokata

Kreira realnu srpsku upravnu tužbu, uploaduje je i pušta kroz 5 pitanja.
Svaki odgovor se scoruje po konkretnim pravnim indikatorima.

Pokretanje:
    python scripts/test_5_pravnih_testova.py --email benny13.n@gmail.com --password <lozinka>
    python scripts/test_5_pravnih_testova.py --token <jwt>
    python scripts/test_5_pravnih_testova.py --token <jwt> --url http://localhost:8000

Izlaz: konzola + scripts/test_5_izvestaj.json
"""

import argparse
import json
import re
import sys
import time
from io import BytesIO
from datetime import date, timedelta

import requests

# ── Konfiguracija ─────────────────────────────────────────────────────────────
BASE_URL_DEFAULT = "https://vindex-ai.onrender.com"

# ── Realna srpska upravna tužba ───────────────────────────────────────────────
TUZBA_TEKST = """\
UPRAVNOM SUDU U BEOGRADU
Odeljenje za upravne sporove

TUŽILAC: Marija Nikolić, JMBG 2703985715023
adresa: Beograd, Ustanička 117/4, 11000 Beograd
zastupnik po punomoćju: Advokat Dragan Popović, Beograd

TUŽENI: Republički geodetski zavod — Služba za katastar nepokretnosti Beograd
adresa: Beograd, Bulevar vojvode Mišića 39

VREDNOST PREDMETA SPORA: Spor se ne ceni u novcu — prava na nepokretnosti

TUŽBA
za poništaj konačnog upravnog akta

I. PREDMET TUŽBE

Tužbom se osporava zakonitost Rešenja Republičkog geodetskog zavoda, Službe za katastar
nepokretnosti Beograd, br. RGZ-952-14-2134/2024-2 od 12.02.2024. godine (u daljem tekstu:
"pobijano rešenje"), kojim je odbijen zahtev tužioca za upis prava svojine na katastarskim
parcelama br. 2341/1 i 2341/2, KO Voždovac, površine 412 m² i 308 m².

II. POBIJANO REŠENJE

Rešenjem od 12.02.2024. godine RGZ je odbio zahtev tužioca za uknjižbu prava svojine uz
obrazloženje da predloženi dokazi — ugovor o kupoprodaji overan pred javnim beležnikom
br. OV-4521/2023 od 14.11.2023. i rešenje o nasleđivanju Op. br. 1123/2019 Opštinskog suda
u Beogradu — "ne pružaju potpuno dokazni osnov za upis, jer nije priložena dokumentacija
kojom se dokazuje pravni kontinuitet od zadnjeg upisanog vlasnika."

Tužilac se žalbom obratio Ministarstvu građevinarstva, saobraćaja i infrastrukture.
Drugostepenim rešenjem Ministarstva br. 351-04-00217/2024-05 od 30.03.2024. godine žalba
je odbijena uz potvrdu prvostepenog obrazloženja.

Konačni akt je dostavljen tužiocu 15.04.2024. godine. Tužba se podnosi 13.05.2024. godine,
u roku od 30 dana propisanom čl. 18 Zakona o upravnim sporovima.

III. PRAVNI OSNOV

Tužilac zasniva tužbu na sledećim pravnim osnovama:

1. Povreda čl. 205 ZUP (Sl. gl. RS 18/2016) — organ nije naveo koji tačno dokazi nedostaju
   i nije pozvao tužioca da otkloni formalne nedostatke u postupku.

2. Povreda načela efikasnosti i ekonomičnosti iz čl. 9 ZUP — rešenje je doneto bez prethodnog
   obaveštenja tužiocu o razlozima za odbijanje, čime je tužilac sprečen da blagovremeno
   dopuni zahtev.

3. Povreda odredbi Zakona o postupku upisa u katastar nepokretnosti i vodova
   (Sl. gl. RS 41/2018, 95/2018, 31/2019) — čl. 16 obavezuje katastar da pozove podnosioca
   da dopuni zahtev pre donošenja odbijajućeg rešenja.

4. Netačno i nepotpuno utvrđeno činjenično stanje — organ je zanemario notarski ugovor kao
   punovažni pravni osnov za sticanje svojine u smislu čl. 20 Zakona o osnovama
   svojinskopravnih odnosa (Sl. gl. RS 115/2005).

IV. PREDLOG DOKAZA

1. Ugovor o kupoprodaji OV-4521/2023 od 14.11.2023. (overeno kod javnog beležnika)
2. Rešenje o nasleđivanju Op. br. 1123/2019
3. Posedovni list parcela 2341/1 i 2341/2 KO Voždovac
4. Izvod iz matice umrlih za prethodnog vlasnika
5. Prvostepeno rešenje RGZ br. RGZ-952-14-2134/2024-2
6. Drugostepeno rešenje Ministarstva br. 351-04-00217/2024-05
7. Dokaz o dostavljanju konačnog akta
8. Saglasnost između parcela — geodetski snimak iz 2021. godine

V. TUŽBENI ZAHTEV

Na osnovu napred iznetih razloga, tužilac predlaže da Upravni sud u Beogradu donese sledeću:

P R E S U D U

1. PONIŠTAVA SE Rešenje RGZ br. RGZ-952-14-2134/2024-2 od 12.02.2024. i
   Rešenje Ministarstva br. 351-04-00217/2024-05 od 30.03.2024. kao nezakonita.

2. OBAVEZUJE SE tuženi organ da u roku od 30 dana od pravnosnažnosti presude
   donese novo rešenje u skladu sa pravnim shvatanjem suda.

3. TUŽENI snosi troškove postupka.

U Beogradu, 13.05.2024. godine

                                        Punomoćnik tužioca
                                        Advokat Dragan Popović

PRILOG: Punomoćje, dokumentacija iz tačke IV tužbe (kopije)
"""

# ── 5 pitanja sa agentima i indikatorima kvaliteta ───────────────────────────
TESTOVI = [
    {
        "br":     1,
        "naziv":  "Procesne slabosti",
        "pitanje": "Koje su procesne slabosti ove upravne tužbe? Navedi konkretne procesne nedostatke prema ZUP i ZUSP.",
        "agent":  "litigation",
        "kljucne_reci": [
            "rok", "nadležnost", "legitimacija", "zastarelost", "obrazloženje",
            "žalba", "ZUP", "ZUSP", "postupak", "odbačaj",
        ],
        "zabranjene_reci": ["40%", "50%", "70%", "80%"],
        "min_duzina": 400,
        "opis_skor": "Traži: konkretne procesne nedostatke, ZUP/ZUSP reference, rokove",
    },
    {
        "br":     2,
        "naziv":  "Nedostajući dokaz",
        "pitanje": "Koji dokaz najviše nedostaje u ovom predmetu i zašto je kritičan za ishod spora?",
        "agent":  "litigation",
        "kljucne_reci": [
            "dokaz", "isprava", "kontinuitet", "vlasnik", "upis", "katastar",
            "ugovor", "rešenje", "izvod", "nedostaje",
        ],
        "zabranjene_reci": ["40%", "50%", "70%"],
        "min_duzina": 300,
        "opis_skor": "Traži: specifičan dokaz, objašnjenje zašto je kritičan, kako ga pribaviti",
    },
    {
        "br":     3,
        "naziv":  "Sporne činjenice",
        "pitanje": "Koje činjenice protivnik može najlakše osporavati i kako će to učiniti na ročištu?",
        "agent":  "litigation",
        "kljucne_reci": [
            "osporiti", "osporava", "sporno", "teret", "dokazati", "protivnik",
            "organ", "tvrditi", "pravni kontinuitet", "svojina",
        ],
        "zabranjene_reci": [],
        "min_duzina": 350,
        "opis_skor": "Traži: konkretne sporne tačke, taktiku protivnika, kako ih preduprediti",
    },
    {
        "br":     4,
        "naziv":  "ZUP članovi",
        "pitanje": "Koji članovi ZUP-a su najrelevantniji za ovaj upravni spor? Za svaki član navedi tačan stav i objasni kako se primenjuje na konkretan slučaj.",
        "agent":  "research",
        "kljucne_reci": [
            "čl.", "ZUP", "st.", "Sl. gl.", "načelo", "organ", "rešenje",
            "postupak", "stranka", "pravni lek",
        ],
        "zabranjene_reci": [],
        "min_duzina": 400,
        "opis_skor": "Mora imati: precizne članove sa stavovima (čl. X st. Y ZUP), primenu na slučaj",
        "specijalni_check": "clan_stav",  # proveravamo pattern čl. N st. M
    },
    {
        "br":     5,
        "naziv":  "Plan pripreme za ročište",
        "pitanje": "Napravi konkretan plan pripreme za ročište korak po korak — šta uraditi, kojim redosledom i do kog roka.",
        "agent":  "drafting",
        "kljucne_reci": [
            "ročište", "rok", "dan", "priprema", "dokaz", "svedok",
            "podnesak", "sud", "predlog", "tuženi",
        ],
        "zabranjene_reci": [],
        "min_duzina": 400,
        "opis_skor": "Traži: numerisane korake, konkretne rokove, akcije sa odgovornošću",
    },
]

# ── Boje za konzolu ───────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def c(boja, tekst): return f"{boja}{tekst}{RESET}"


# ── Auth ──────────────────────────────────────────────────────────────────────
def login(email: str, password: str, base_url: str) -> str:
    import os
    from pathlib import Path
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
    from supabase import create_client
    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    r = supa.auth.sign_in_with_password({"email": email, "password": password})
    token = r.session.access_token
    print(c(GREEN, f"[AUTH] Login OK — token: {token[:25]}..."))
    return token


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Kreiranje DOCX u memoriji ─────────────────────────────────────────────────
def napravi_docx(tekst: str) -> BytesIO:
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    doc.core_properties.author = "Vindex AI Test"
    doc.core_properties.title = "Upravna tužba — test dokument"
    for para in tekst.strip().split("\n"):
        p = doc.add_paragraph(para)
        p.style.font.size = Pt(11)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ── Upload dokumenta ──────────────────────────────────────────────────────────
def upload_dokument(token: str, base_url: str) -> str:
    print(f"\n{c(CYAN, '─'*60)}")
    print(c(BOLD, "UPLOAD: Kreiranje i slanje upravne tužbe..."))
    docx_buf = napravi_docx(TUZBA_TEKST)
    resp = requests.post(
        f"{base_url}/api/dokument/upload",
        headers=hdr(token),
        files={"file": ("upravna_tuzba_test.docx",
                        docx_buf,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        timeout=60,
    )
    if resp.status_code != 200:
        print(c(RED, f"[UPLOAD] GREŠKA {resp.status_code}: {resp.text[:300]}"))
        sys.exit(1)
    d = resp.json()
    session_id = d["session_id"]
    print(c(GREEN, f"[UPLOAD] OK — session_id: {session_id}"))
    print(f"         chunks: {d.get('chunk_count')}, expires: {d.get('expires_at','?')[:19]}")
    return session_id


# ── Pokretanje agenta sa kontekstom ──────────────────────────────────────────
def pokreni_agenta(token: str, base_url: str, agent_id: str, pitanje: str, kontekst: str) -> str:
    payload = {
        "agent":   agent_id,
        "task":    pitanje,
        "kontekst": kontekst[:3000],
    }
    resp = requests.post(
        f"{base_url}/api/agents/run",
        headers={**hdr(token), "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    if resp.status_code != 200:
        return f"[GREŠKA AGENTA {resp.status_code}] {resp.text[:200]}"
    return resp.json().get("odgovor", "")


# ── Scorovanje odgovora ───────────────────────────────────────────────────────
def skoriraj(odgovor: str, test: dict) -> dict:
    odgovor_l = odgovor.lower()
    pogodaka = sum(1 for k in test["kljucne_reci"] if k.lower() in odgovor_l)
    ukupno_kljucnih = len(test["kljucne_reci"])

    zabranjene_nadj = [z for z in test["zabranjene_reci"] if z in odgovor]
    kazna = len(zabranjene_nadj) * 2

    duzina_ok = len(odgovor) >= test["min_duzina"]

    # Specijalni check: da li ima "čl. N st. M" pattern
    clan_stav_ok = True
    if test.get("specijalni_check") == "clan_stav":
        # Traži pattern poput "čl. 9 st. 1" ili "čl. 205" makar
        matches = re.findall(r"čl\.\s*\d+", odgovor)
        matches_sa_stavom = re.findall(r"čl\.\s*\d+\s+st\.\s*\d+", odgovor)
        clan_stav_ok = len(matches) >= 2  # bar 2 konkretna člana
        stav_preciznost = len(matches_sa_stavom)
    else:
        stav_preciznost = 0

    # Skor 0-10
    kljucni_skor = min(10, round((pogodaka / ukupno_kljucnih) * 10)) if ukupno_kljucnih else 0
    skor = max(0, kljucni_skor - kazna)
    if duzina_ok:
        skor = min(10, skor + 1)
    if test.get("specijalni_check") == "clan_stav" and clan_stav_ok:
        skor = min(10, skor + 1)

    return {
        "skor":             skor,
        "kljucne_pogodene": pogodaka,
        "kljucne_ukupno":   ukupno_kljucnih,
        "zabranjene":       zabranjene_nadj,
        "duzina_ok":        duzina_ok,
        "duzina_znakova":   len(odgovor),
        "clan_stav_count":  stav_preciznost if test.get("specijalni_check") else None,
    }


def skor_boja(skor: int) -> str:
    if skor >= 8: return GREEN
    if skor >= 5: return YELLOW
    return RED


def skor_ocena(skor: int) -> str:
    if skor >= 9: return "ODLIČNO"
    if skor >= 7: return "DOBRO"
    if skor >= 5: return "PRIHVATLJIVO"
    if skor >= 3: return "SLABO"
    return "NEPRIHVATLJIVO"


# ── Pokretanje testova ────────────────────────────────────────────────────────
def run(token: str, base_url: str):
    print(f"\n{'═'*65}")
    print(c(BOLD, "  VINDEX AI — 5 BRUTALNIH PRAVNIH TESTOVA"))
    print(f"  BASE: {base_url}")
    print(f"  Datum: {date.today().isoformat()}")
    print('═'*65)

    # Upload dokumenta
    session_id = upload_dokument(token, base_url)

    # Pripremi kontekst (ceo tekst tužbe za agente)
    kontekst_dokument = (
        "DOKUMENT ZA ANALIZU — Upravna tužba:\n\n" + TUZBA_TEKST[:3000]
    )

    rezultati = []
    ukupan_skor = 0

    for test in TESTOVI:
        print(f"\n{'─'*65}")
        print(c(BOLD, f"  TEST {test['br']}/5 — {test['naziv'].upper()}"))
        print(f"  Pitanje: {test['pitanje'][:100]}...")
        print(f"  Agent: {test['agent']} | {test['opis_skor']}")
        print()

        start = time.time()
        odgovor = pokreni_agenta(token, base_url, test["agent"], test["pitanje"], kontekst_dokument)
        trajanje = round(time.time() - start, 1)

        sc = skoriraj(odgovor, test)
        ukupan_skor += sc["skor"]

        boja = skor_boja(sc["skor"])
        ocena = skor_ocena(sc["skor"])

        # Prikaz odgovora (prvo 800 znakova)
        print(c(CYAN, "  ODGOVOR:"))
        for linija in odgovor[:900].split("\n"):
            print(f"  {linija}")
        if len(odgovor) > 900:
            print(f"  ... [{len(odgovor)-900} znakova više]")

        # Skor
        skor_txt = "SKOR: {}/10 — {}".format(sc["skor"], ocena)
        print(f"\n  {c(boja, skor_txt)}")
        print(f"  Ključne reči: {sc['kljucne_pogodene']}/{sc['kljucne_ukupno']} | "
              f"Dužina: {sc['duzina_znakova']} zn. ({'OK' if sc['duzina_ok'] else 'KRATKO'})")
        if sc["zabranjene"]:
            print(c(RED, f"  ⚠ UPOZORENJE — izmišljeni procenti: {sc['zabranjene']}"))
        if sc.get("clan_stav_count") is not None:
            if sc["clan_stav_count"] >= 2:
                print(c(GREEN, f"  ✓ Precizni citati sa stavom: {sc['clan_stav_count']} pronađenih"))
            elif sc["clan_stav_count"] >= 1:
                print(c(YELLOW, f"  ~ Delimično precizni citati: {sc['clan_stav_count']} sa stavom"))
            else:
                print(c(RED, "  ✗ Nema preciznih citata čl. N st. M — samo opšti brojevi"))
        print(f"  Vreme odgovora: {trajanje}s")

        rezultati.append({
            "test_br":   test["br"],
            "naziv":     test["naziv"],
            "agent":     test["agent"],
            "pitanje":   test["pitanje"],
            "odgovor":   odgovor,
            "skor":      sc["skor"],
            "ocena":     ocena,
            "detalji":   sc,
            "trajanje_s": trajanje,
        })

    # ── Finalni izveštaj ──────────────────────────────────────────────────────
    prosek = round(ukupan_skor / len(TESTOVI), 1)
    print(f"\n{'═'*65}")
    print(c(BOLD, "  FINALNI IZVEŠTAJ"))
    print('═'*65)
    for r in rezultati:
        b = skor_boja(r["skor"])
        print(f"  Test {r['test_br']}: {r['naziv']:<28} {c(b, str(r['skor'])+'/10')} — {r['ocena']}")

    print('─'*65)
    prosek_boja = skor_boja(int(prosek))
    print(c(BOLD, f"  PROSEČAN SKOR: {c(prosek_boja, str(prosek)+'/10')}"))
    print()
    if prosek >= 7.5:
        print(c(GREEN, "  ✓ SISTEM SPREMAN ZA SASTANAK SA ADVOKATOM"))
    elif prosek >= 5.5:
        print(c(YELLOW, "  ~ POTREBNA POBOLJŠANJA — prihvatljivo ali ne odlično"))
    else:
        print(c(RED, "  ✗ SISTEM NIJE SPREMAN — videti slabe testove"))
    print()

    # Snimi JSON izveštaj
    izvestaj_path = "scripts/test_5_izvestaj.json"
    with open(izvestaj_path, "w", encoding="utf-8") as f:
        json.dump({
            "datum":       date.today().isoformat(),
            "base_url":    base_url,
            "session_id":  session_id,
            "prosek_skor": prosek,
            "testovi":     rezultati,
        }, f, ensure_ascii=False, indent=2)
    print(c(CYAN, f"  Izveštaj snimljen: {izvestaj_path}"))
    print('═'*65)

    return prosek >= 5.5


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vindex AI — 5 pravnih testova")
    parser.add_argument("--email",    default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--token",    default="")
    parser.add_argument("--url",      default=BASE_URL_DEFAULT)
    args = parser.parse_args()

    if args.token:
        token = args.token
    elif args.email and args.password:
        token = login(args.email, args.password, args.url)
    else:
        print(c(RED, "Greška: navedi --token ILI --email + --password"))
        sys.exit(1)

    ok = run(token, args.url)
    sys.exit(0 if ok else 1)
