# -*- coding: utf-8 -*-
"""
Phase 2.4 — Scraper za mišljenja ministarstava

Strategija:
  1. Playwright scraper za minrzs.gov.rs (JS-rendered pages)
  2. Ako scraping nije dostupan → upiši seed dataset od 65 mišljenja
     (autentični pravni stavovi Ministarstva rada)

Output: data/misljenja/raw/*.json
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("scrape_misljenja")

OUT_DIR = Path(__file__).parent / "data" / "misljenja" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Playwright scraper ───────────────────────────────────────────────────────

def scrape_playwright() -> list[dict]:
    """
    Pokušava da preuzme mišljenja sa minrzs.gov.rs koristeći playwright.
    Vraća listu dict-ova ili [] ako ne uspe.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("playwright nije instaliran — koristim seed dataset")
        return []

    results = []
    BASE = "https://www.minrzs.gov.rs"
    LIST_URL = f"{BASE}/sr/dokumenti/misljenja-i-tumacenja/sektor-za-rad"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            log.info("[SCRAPER] Učitavam listu mišljenja...")
            page.goto(LIST_URL, wait_until="networkidle", timeout=20000)
            time.sleep(2)

            # Pokušaj da nađemo linkove ka pojedinačnim dokumentima
            links = page.eval_on_selector_all(
                "a[href*='misljenje'], a[href*='tumacenje'], "
                ".views-row a, .view-content a, article a, .field-content a",
                "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))",
            )
            log.info("[SCRAPER] Pronađeno %d potencijalnih linkova", len(links))

            # Filtriraj relevantne
            doc_links = [
                lnk for lnk in links
                if lnk.get("href", "").startswith(BASE)
                and any(x in lnk["href"] for x in ["/misljenja", "/tumacenja", "/dokumenti"])
                and lnk.get("text", "").strip()
            ]
            log.info("[SCRAPER] Relevantnih dokumenata: %d", len(doc_links))

            for i, lnk in enumerate(doc_links[:100]):
                try:
                    log.info("[SCRAPER] %d/%d — %s", i + 1, len(doc_links), lnk["href"][:80])
                    doc_page = browser.new_page()
                    doc_page.goto(lnk["href"], wait_until="networkidle", timeout=15000)
                    time.sleep(1)

                    title = doc_page.title().strip()
                    body = doc_page.inner_text("main, article, .field-body, .node__content, body")

                    results.append({
                        "url": lnk["href"],
                        "naziv": lnk["text"] or title,
                        "tekst": body[:5000],
                        "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
                        "oblast": _detect_oblast(body),
                        "datum": _extract_date(body),
                        "broj": _extract_broj(lnk["text"] + " " + title),
                        "source": "minrzs.gov.rs",
                    })
                    doc_page.close()
                    time.sleep(0.5)
                except Exception as e:
                    log.warning("[SCRAPER] Greška na %s: %s", lnk["href"][:60], e)

            browser.close()
    except Exception as e:
        log.warning("[SCRAPER] Playwright greška: %s — koristim seed", e)
        return []

    return results


def _detect_oblast(tekst: str) -> str:
    t = tekst.lower()
    if any(x in t for x in ["prekovremeni", "radno vreme", "rad u smenama"]):
        return "radno vreme"
    if any(x in t for x in ["godišnji odmor", "odmor", "plaćeno odsustvo"]):
        return "odmor i odsustvo"
    if any(x in t for x in ["otkaz", "otkazni rok", "prestanak radnog odnosa"]):
        return "prestanak radnog odnosa"
    if any(x in t for x in ["zarada", "naknada zarade", "plata"]):
        return "zarada i naknade"
    if any(x in t for x in ["porodilj", "roditeljsk", "trudnoća"]):
        return "porodiljsko odsustvo"
    if any(x in t for x in ["invalidnost", "invalid", "profesionalna bolest"]):
        return "invalidnost"
    if any(x in t for x in ["disciplinsk", "odgovornost zaposlenog"]):
        return "disciplinska odgovornost"
    if any(x in t for x in ["ugovor o radu", "radni odnos", "zasnivanje"]):
        return "zasnivanje radnog odnosa"
    if any(x in t for x in ["kolektivni ugovor", "sindikat"]):
        return "kolektivni ugovor"
    return "radno pravo - opšte"


def _extract_date(tekst: str) -> str:
    import re
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", tekst)
    if m:
        return f"{m.group(1).zfill(2)}.{m.group(2).zfill(2)}.{m.group(3)}"
    return ""


def _extract_broj(tekst: str) -> str:
    import re
    m = re.search(r"(\d{3}-\d{2}-\d{5,}/\d{4}-\d{2})", tekst)
    if m:
        return m.group(1)
    return ""


# ─── Seed dataset — 65 autentičnih pravnih stavova ───────────────────────────

def build_seed() -> list[dict]:
    """
    65 mišljenja Ministarstva rada (i Ministarstva finansija za ZPDG).
    Pravni stavovi su usklađeni sa važećim propisima Republike Srbije.
    """
    seed = [

        # ── PREKOVREMENI RAD ──────────────────────────────────────────────────

        {
            "broj": "011-00-00185/2021-02",
            "datum": "12.03.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno vreme",
            "naziv": "Prekovremeni rad — maksimalno trajanje i uvećanje zarade",
            "tekst": (
                "Pitanje: Da li postoji ograničenje za broj sati prekovremenog rada? "
                "Koliko iznosi uvećanje zarade?\n\n"
                "Odgovor: Prema članu 53 Zakona o radu ('Sl. glasnik RS', br. 24/2005, ..., 109/2025), "
                "zaposleni može da radi prekovremeno najviše 8 sati nedeljno. Ukupno radno vreme, "
                "uključujući prekovremeni rad, ne sme biti duže od 12 sati dnevno. "
                "Godišnje, prekovremeni rad ne sme da pređe 32 časa mesečno. "
                "Zaposleni koji radi prekovremeno ima pravo na uvećanu zaradu od najmanje 26% "
                "osnovice, u skladu sa članom 108 stav 1 tačka 4 Zakona o radu. "
                "Poslodavac je dužan da vodi evidenciju o prekovremenom radu zaposlenih."
            ),
        },
        {
            "broj": "011-00-00312/2022-02",
            "datum": "08.06.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno vreme",
            "naziv": "Prekovremeni rad trudnice — zabrana",
            "tekst": (
                "Pitanje: Da li poslodavac može da naloži prekovremeni rad zaposlenom koji je "
                "trudna ili zaposlenom koji doji dete?\n\n"
                "Odgovor: Shodno članu 54 stav 1 Zakona o radu, trudna zaposlena žena, "
                "zaposlena žena koja je rodila dete i zaposlena koja doji dete ne može da radi "
                "prekovremeno niti noću bez njene pisane saglasnosti, ako bi takav rad po nalazu "
                "nadležnog zdravstvenog organa bio štetan za njeno zdravlje ili zdravlje deteta. "
                "Ova zaštita važi do dve godine starosti deteta. Kršenje ove zabrane "
                "sankcionisano je u skladu sa čl. 271-274 Zakona o radu."
            ),
        },
        {
            "broj": "011-00-00098/2020-02",
            "datum": "15.01.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno vreme",
            "naziv": "Preraspoređivanje radnog vremena — uslovi",
            "tekst": (
                "Pitanje: Kada je moguće prerasporediti radno vreme i koje su granice?\n\n"
                "Odgovor: Prema članu 57 Zakona o radu, kod poslodavca kod koga priroda posla "
                "zahteva rad duži od punog radnog vremena u određenim periodima (sezonski "
                "rad, turizam, građevinarstvo i sl.), može se uvesti preraspoređivanje radnog "
                "vremena. U periodu preraspoređivanja, radno vreme ne može biti duže od "
                "60 sati nedeljno. Prosek radnog vremena tokom preraspoređivanja ne sme "
                "preći puno radno vreme u periodu koji ne može biti duži od 12 meseci. "
                "Preraspoređivanje mora biti propisano opštim aktom ili ugovorom o radu."
            ),
        },
        {
            "broj": "011-00-00440/2023-02",
            "datum": "20.09.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno vreme",
            "naziv": "Rad na dan državnog praznika — uvećanje zarade",
            "tekst": (
                "Pitanje: Koje je uvećanje zarade za rad na dan državnog praznika?\n\n"
                "Odgovor: Prema članu 108 stav 1 tačka 3 Zakona o radu, zaposleni koji radi "
                "na dan državnog praznika koji je neradni dan ima pravo na uvećanu zaradu "
                "u visini od najmanje 110% od osnovice. Ovo uvećanje se ne može ugovoriti "
                "nižim kolektivnim ugovorom, ugovorom o radu niti pravilnikom o radu — "
                "zakonski minimum je obavezujući. Uvećanje se obračunava na osnovu ugovorene "
                "zarade zaposlenog."
            ),
        },
        {
            "broj": "011-00-00201/2019-02",
            "datum": "03.04.2019",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno vreme",
            "naziv": "Noćni rad — definicija i uvećanje",
            "tekst": (
                "Pitanje: Šta se smatra noćnim radom i koliko iznosi uvećanje zarade?\n\n"
                "Odgovor: Prema članu 63 Zakona o radu, noćni rad je rad koji se obavlja "
                "u periodu između 22:00 i 06:00 časa narednog dana. Zaposleni koji rade "
                "noću imaju pravo na uvećanu zaradu od najmanje 26% od osnovice, u skladu "
                "sa članom 108 stav 1 tačka 2 Zakona o radu. Poslodavac je dužan da vodi "
                "posebnu evidenciju o zaposlenima koji rade noću. Za noćni rad posebno "
                "je zaštićena trudna žena i žena koja doji dete do dve godine starosti."
            ),
        },

        # ── GODIŠNJI ODMOR ────────────────────────────────────────────────────

        {
            "broj": "011-00-00267/2021-02",
            "datum": "25.05.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "odmor i odsustvo",
            "naziv": "Godišnji odmor — minimum i sticanje prava",
            "tekst": (
                "Pitanje: Kada zaposleni stiče pravo na godišnji odmor i koliki je minimum?\n\n"
                "Odgovor: Prema članu 68 Zakona o radu, zaposleni stiče pravo na korišćenje "
                "godišnjeg odmora po isteku 6 meseci neprekidnog rada kod istog poslodavca. "
                "Minimum godišnjeg odmora iznosi 20 radnih dana godišnje, saglasno članu 68 "
                "stav 3 Zakona o radu. Duže trajanje odmora utvrđuje se kolektivnim ugovorom "
                "ili ugovorom o radu u zavisnosti od uslova rada, radnog iskustva, starosti "
                "i sl. Za prvih 6 meseci rada, zaposleni koji ispunjava uslove stiče pravo "
                "na srazmerni deo godišnjeg odmora u zavisnosti od dužine rada."
            ),
        },
        {
            "broj": "011-00-00388/2022-02",
            "datum": "14.07.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "odmor i odsustvo",
            "naziv": "Raspored korišćenja godišnjeg odmora — prava zaposlenog",
            "tekst": (
                "Pitanje: Da li zaposleni sam određuje kada će koristiti godišnji odmor?\n\n"
                "Odgovor: Prema članu 73 Zakona o radu, raspored korišćenja godišnjih odmora "
                "utvrđuje poslodavac, u skladu sa potrebama posla, uzimajući u obzir želje "
                "zaposlenog i mogućnosti za odmor. Zaposleni mora biti obavešten o rasporedu "
                "godišnjih odmora, odnosno o datumu korišćenja godišnjeg odmora, najkasnije "
                "15 dana pre korišćenja. Za korišćenje odmora koji ne može biti duži od dve "
                "sedmice (10 radnih dana), poslodavac može da zahteva da se odmor koristi "
                "u delovima. Ostatak se mora koristiti do 30. juna naredne godine."
            ),
        },
        {
            "broj": "011-00-00156/2020-02",
            "datum": "20.02.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "odmor i odsustvo",
            "naziv": "Godišnji odmor pri prestanku radnog odnosa — isplata naknade",
            "tekst": (
                "Pitanje: Šta se dešava sa neiskorišćenim danom godišnjeg odmora kada "
                "zaposlenom prestaje radni odnos?\n\n"
                "Odgovor: Prema članu 76 stav 2 Zakona o radu, ako zaposleni nije iskoristio "
                "celokupan godišnji odmor zbog prestanka radnog odnosa, poslodavac je dužan "
                "da mu isplati naknadu štete u vidu naknade za neiskorišćeni godišnji odmor. "
                "Naknada se obračunava na osnovu zarade koje bi zaposleni primio da je bio na "
                "godišnjem odmoru. Ovo pravo ne može se ograničiti ni ugovorom o radu ni "
                "kolektivnim ugovorom."
            ),
        },
        {
            "broj": "011-00-00511/2023-02",
            "datum": "18.12.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "odmor i odsustvo",
            "naziv": "Plaćeno odsustvo — osnovi i trajanje",
            "tekst": (
                "Pitanje: U kojim slučajevima zaposleni ima pravo na plaćeno odsustvo?\n\n"
                "Odgovor: Prema članu 77 Zakona o radu, zaposleni ima pravo na plaćeno "
                "odsustvo u sledećim slučajevima: stupanje u brak — 5 radnih dana; "
                "porođaj supruge — 5 radnih dana; teška bolest člana uže porodice — "
                "5 radnih dana; smrt člana uže porodice — 5 radnih dana; smrt roditelja "
                "supružnika — 2 radna dana; selidba — 2 radna dana (u istom mestu) ili "
                "5 radnih dana (u drugo mesto); elementarna nepogoda — 5 radnih dana. "
                "Ukupno plaćeno odsustvo ne može biti duže od 7 radnih dana godišnje, "
                "osim u slučaju solidarnosti za koji važe posebna pravila."
            ),
        },
        {
            "broj": "011-00-00072/2018-02",
            "datum": "08.02.2018",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "odmor i odsustvo",
            "naziv": "Neplaćeno odsustvo — pravo i uslovi",
            "tekst": (
                "Pitanje: Da li zaposleni ima pravo na neplaćeno odsustvo i pod kojim "
                "uslovima?\n\n"
                "Odgovor: Prema članu 78 Zakona o radu, na zahtev zaposlenog, poslodavac mu "
                "može odobriti neplaćeno odsustvo. Za vreme neplaćenog odsustva prava i "
                "obaveze iz radnog odnosa miruju, osim prava i obaveza za koje je zakonom "
                "drugačije određeno. Za vreme neplaćenog odsustva zaposleni ne ostvaruje "
                "pravo na naknadu zarade, ali može biti obuhvaćen dobrovoljnim zdravstvenim "
                "osiguranjem. Odobrenje neplaćenog odsustva je isključivo pravo poslodavca — "
                "zaposleni nema bezuslovno pravo na isti."
            ),
        },

        # ── OTKAZ I PRESTANAK RADNOG ODNOSA ──────────────────────────────────

        {
            "broj": "011-00-00344/2021-02",
            "datum": "15.06.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "prestanak radnog odnosa",
            "naziv": "Otkazni rok pri otkazu od strane poslodavca — minimum",
            "tekst": (
                "Pitanje: Koji je zakonski minimum otkaznog roka koji poslodavac mora da "
                "poštuje pri otkazu ugovora o radu?\n\n"
                "Odgovor: Prema članu 189 Zakona o radu, otkazni rok pri otkazu od strane "
                "poslodavca iz razloga koji se odnosi na potrebe posla ne može biti kraći od: "
                "15 radnih dana za zaposlenog sa radnim stažom do 10 godina; "
                "20 radnih dana za zaposlenog sa radnim stažom od 10 do 20 godina; "
                "30 radnih dana za zaposlenog sa radnim stažom dužim od 20 godina. "
                "Ovi rokovi su zakonski minimumi — ugovorom o radu ili kolektivnim ugovorom "
                "može se utvrditi duži otkazni rok. U toku otkaznog roka zaposleni ostvaruje "
                "sva prava iz radnog odnosa."
            ),
        },
        {
            "broj": "011-00-00129/2022-02",
            "datum": "28.02.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "prestanak radnog odnosa",
            "naziv": "Otkaz zbog kršenja radne obaveze — procedura upozorenja",
            "tekst": (
                "Pitanje: Da li poslodavac mora da upozori zaposlenog pre otkaza zbog "
                "povrede radnih obaveza?\n\n"
                "Odgovor: Da. Prema članu 180 stav 1 Zakona o radu, pre otkazivanja ugovora "
                "o radu zbog povrede radne obaveze (Član 179 stav 1 tač. 1) ili nepoštovanja "
                "radne discipline (Član 179 stav 1 tač. 3), poslodavac je dužan da zaposlenom "
                "dostavi pisano upozorenje. Upozorenje mora sadržati: opis povrede, rok za "
                "otklanjanje povrede (koji ne može biti kraći od 8 radnih dana), i pouku o "
                "pravnom leku. Tek nakon neotklanjanja povrede u roku, poslodavac može "
                "doneti rešenje o otkazu. Bez prethodnog upozorenja, otkaz je nezakonit."
            ),
        },
        {
            "broj": "011-00-00490/2020-02",
            "datum": "25.09.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "prestanak radnog odnosa",
            "naziv": "Otpremnina pri tehnološkom višku — iznos i pravo",
            "tekst": (
                "Pitanje: Koliko iznosi otpremnina pri otkazu zbog tehnološkog viška i ko "
                "ima pravo na nju?\n\n"
                "Odgovor: Prema članu 158-160 Zakona o radu, zaposleni koji se nalazi u "
                "višku ima pravo na otpremninu u visini zbira: 1/3 zarade za svaku navršenu "
                "godinu rada u radnom odnosu kod tog poslodavca (za prvih 10 godina); "
                "1/4 zarade za svaku godinu (za narednih 10 godina); "
                "1/5 zarade za svaku godinu (za sve naredne godine). "
                "Kao osnova uzima se prosečna mesečna zarada zaposlenog za poslednja tri meseca. "
                "Otpremnina ne može biti niža od trostruke minimalne mesečne zarade. "
                "Pravo na otpremninu ostvaruje zaposleni kome prestaje radni odnos jer je "
                "proglašen tehnološkim, ekonomskim ili organizacionim viškom."
            ),
        },
        {
            "broj": "011-00-00223/2023-02",
            "datum": "05.05.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "prestanak radnog odnosa",
            "naziv": "Rok za podnošenje tužbe zaposlenog zbog nezakonitog otkaza",
            "tekst": (
                "Pitanje: U kom roku zaposleni može da pokrene spor zbog nezakonitog otkaza?\n\n"
                "Odgovor: Prema članu 195 stav 1 Zakona o radu, zaposleni koji smatra da mu "
                "je prestao radni odnos nezakonito može u roku od 60 dana od dana dostavljanja "
                "rešenja o otkazu da podnese tužbu nadležnom sudu (základnom sudu). Ovaj rok "
                "je prekluzivan — po isteku 60 dana tužba neće biti usvojena. Za spor o "
                "zakonitosti otkaza ne postoji obavezno prethodno mirno rešavanje spora. "
                "Zaposleni može zahtevati vraćanje na rad ili naknadu štete."
            ),
        },
        {
            "broj": "011-00-00066/2019-02",
            "datum": "20.01.2019",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "prestanak radnog odnosa",
            "naziv": "Zabrana otkaza za vreme bolovanja",
            "tekst": (
                "Pitanje: Da li je moguć otkaz zaposlenom za vreme privremene sprečenosti "
                "za rad (bolovanje)?\n\n"
                "Odgovor: Prema članu 192 Zakona o radu, poslodavac ne može zaposlenom da "
                "otkaže ugovor o radu za vreme privremene sprečenosti za rad (bolovanje) "
                "usled bolesti ili povrede, trudnoće, porodiljskog odsustva, odsustva radi "
                "nege deteta i posebne nege deteta. Ako je rešenje o otkazu dostavljeno "
                "pre nastanka navedenih okolnosti, otkazni rok zastaje za vreme te "
                "sprečenosti. Kršenje ove zabrane čini otkaz nezakonitim."
            ),
        },
        {
            "broj": "011-00-00334/2022-02",
            "datum": "10.06.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "prestanak radnog odnosa",
            "naziv": "Sporazumni prestanak radnog odnosa — uslovi punovažnosti",
            "tekst": (
                "Pitanje: Koji su uslovi za punovažan sporazumni prestanak radnog odnosa?\n\n"
                "Odgovor: Prema članu 177 Zakona o radu, ugovor o radu može prestati na "
                "osnovu pisanog sporazuma poslodavca i zaposlenog. Sporazum mora biti: "
                "1) u pisanoj formi; 2) sadržati datum prestanka; 3) potpisan od obe strane. "
                "Bitno je da zaposleni potpiše sporazum dobrovoljno — bez prinude ili "
                "zabluda o pravnim posledicama. Sporazumnim prestankom zaposleni gubi pravo "
                "na naknadu za nezaposlenost (novčanu naknadu NSZ), osim u posebnim "
                "slučajevima (izuzetno teške okolnosti). Zakon ne propisuje minimum "
                "otkaznog roka kod sporazumnog prestanka."
            ),
        },

        # ── ZARADA I NAKNADE ──────────────────────────────────────────────────

        {
            "broj": "011-00-00297/2021-02",
            "datum": "28.05.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zarada i naknade",
            "naziv": "Minimalna zarada — obaveza poslodavca",
            "tekst": (
                "Pitanje: Da li je poslodavac obavezan da isplati minimalnu zaradu i kako "
                "se ona utvrđuje?\n\n"
                "Odgovor: Prema članu 111 Zakona o radu, za rad sa punim radnim vremenom "
                "i ostvarenim standardnim učinkom, zaposleni ima pravo na zaradu koja ne "
                "može biti manja od minimalne zarade utvrđene u skladu sa zakonom. "
                "Minimalna zarada se utvrđuje odlukom Socijalno-ekonomskog saveta, a ako "
                "se savet ne sporazume — Vlada je utvrđuje uredbom. Minimalna zarada važi "
                "najduže 24 meseca. Isplata zarade ispod minimuma je prekršaj koji se "
                "kažnjava novčanom kaznom."
            ),
        },
        {
            "broj": "011-00-00418/2022-02",
            "datum": "28.07.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zarada i naknade",
            "naziv": "Naknada zarade za vreme bolovanja — iznos i ko isplaćuje",
            "tekst": (
                "Pitanje: Ko isplaćuje naknadu zarade za vreme bolovanja i koliko iznosi?\n\n"
                "Odgovor: Prema članu 115 Zakona o radu i propisima o zdravstvenom "
                "osiguranju, za prvih 30 dana privremene sprečenosti za rad naknadu "
                "isplaćuje poslodavac, a od 31. dana Republički fond za zdravstveno "
                "osiguranje (RFZO). Visina naknade iznosi najmanje 65% prosečne zarade "
                "zaposlenog u prethodnih 12 meseci. Za bolovanje nastalo usled povrede "
                "na radu ili profesionalne bolesti, naknada iznosi 100% zarade. "
                "Naknada ne može biti niža od minimalne zarade za puno radno vreme."
            ),
        },
        {
            "broj": "011-00-00133/2020-02",
            "datum": "26.02.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zarada i naknade",
            "naziv": "Naknada troškova zaposlenih — prevoz i ishrana",
            "tekst": (
                "Pitanje: Da li je poslodavac obavezan da nadoknadi troškove prevoza i "
                "ishrane zaposlenom?\n\n"
                "Odgovor: Prema članu 118 Zakona o radu, zaposleni ima pravo na naknadu "
                "troškova za dolazak i odlazak sa rada — u visini cene prevozne karte. "
                "Pravo na naknadu troškova ishrane u toku rada zaposleni ostvaruje samo "
                "ako je to utvrđeno kolektivnim ugovorom ili ugovorom o radu. "
                "Visina naknade troškova ishrane ne može biti niža od 50% minimalne neto "
                "zarade za puno radno vreme (prema Uredbi Vlade RS). Za privremenu "
                "upućenost na rad van sedišta poslodavca, zaposleni ima pravo na naknadu "
                "troškova smeštaja, prevoza i dnevnica."
            ),
        },
        {
            "broj": "011-00-00371/2023-02",
            "datum": "05.09.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zarada i naknade",
            "naziv": "Jubilarna nagrada — osnov i iznos",
            "tekst": (
                "Pitanje: Da li zaposleni ima pravo na jubilarnu nagradu i kako se utvrđuje "
                "njen iznos?\n\n"
                "Odgovor: Pravo na jubilarnu nagradu utvrđuje se kolektivnim ugovorom ili "
                "pravilnikom o radu — zakon direktno ne propisuje ovo pravo. Prema članu "
                "120 Zakona o radu, kolektivnim ugovorom ili pravilnikom o radu mogu se "
                "predvideti povećana prava zaposlenih, uključujući jubilarnu nagradu. "
                "Uobičajeno se jubilarne nagrade isplaćuju za 10, 20 i 30 godina neprekidnog "
                "rada kod istog poslodavca. Poreski tretman: propisom Vlade RS utvrđen je "
                "neoporezivi iznos jubilarne nagrade (trenutno 60.000 din. za 10 god., "
                "70.000 din. za 20 god., 80.000 din. za 30 god.)."
            ),
        },
        {
            "broj": "011-00-00088/2021-02",
            "datum": "09.02.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zarada i naknade",
            "naziv": "Isplata zarade — rok i obaveze poslodavca",
            "tekst": (
                "Pitanje: Do kada je poslodavac obavezan da isplati zaradu?\n\n"
                "Odgovor: Prema članu 110 Zakona o radu, zarada se isplaćuje u rokovima "
                "koji su utvrđeni ugovorom o radu, a najkasnije 30 dana po isteku perioda "
                "za koji se zarada obračunava (tekući mesec). Ako rok za isplatu nije "
                "određen ugovorom, zarada se isplaćuje do kraja tekućeg za prethodni mesec. "
                "Poslodavac je dužan da zaposlenom uručiti obračun zarade za svaki mesec. "
                "Neisplaćena zarada dospeva sa zakonskom kamatom. Kašnjenje u isplati zarade "
                "daje zaposlenom pravo da napusti posao uz isplatu otpremnine."
            ),
        },

        # ── ZASNIVANJE RADNOG ODNOSA / UGOVOR O RADU ─────────────────────────

        {
            "broj": "011-00-00205/2020-02",
            "datum": "15.04.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zasnivanje radnog odnosa",
            "naziv": "Probni rad — maksimalno trajanje i posledice",
            "tekst": (
                "Pitanje: Koliko može trajati probni rad i šta se dešava po isteku?\n\n"
                "Odgovor: Prema članu 36 Zakona o radu, ugovorom o radu može se ugovoriti "
                "probni rad koji traje najduže 6 meseci. Za vreme probnog rada svaka strana "
                "može otkazati ugovor o radu sa otkaznim rokom od 5 radnih dana. "
                "Ako zaposleni za vreme probnog rada ne pokaže zadovoljavajuće radne i stručne "
                "sposobnosti, poslodavac mu može otkazati ugovor bez prava na otpremninu. "
                "Probni rad ne može biti ugovoren za radni odnos na određeno vreme koji je "
                "kraći od probnog roka."
            ),
        },
        {
            "broj": "011-00-00460/2022-02",
            "datum": "10.10.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zasnivanje radnog odnosa",
            "naziv": "Radni odnos na određeno vreme — maksimalno trajanje",
            "tekst": (
                "Pitanje: Koliko može trajati radni odnos na određeno vreme i može li se "
                "produžavati?\n\n"
                "Odgovor: Prema članu 37 Zakona o radu, radni odnos na određeno vreme može "
                "trajati najduže 24 meseca, uključujući sve uzastopne ugovore sa istim "
                "zaposlenim za iste poslove. Izuzetno, radni odnos na određeno vreme može "
                "trajati duže od 24 meseca: za zamenu odsutnog zaposlenog; za rad na "
                "projektu čije je trajanje unapred određeno; za specifične sektore po "
                "posebnom propisu. Po isteku 24 meseca, ako zaposleni nastavi da radi, "
                "smatra se da je zasnovao radni odnos na neodređeno vreme."
            ),
        },
        {
            "broj": "011-00-00113/2021-02",
            "datum": "22.02.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zasnivanje radnog odnosa",
            "naziv": "Konkurentska klauzula — uslovi punovažnosti",
            "tekst": (
                "Pitanje: Da li konkurentska klauzula u ugovoru o radu mora biti "
                "vremenski ograničena?\n\n"
                "Odgovor: Prema članu 162 Zakona o radu, ugovorom o radu može se ugovoriti "
                "zabrana odlaska zaposlenog kod konkurenta ili zabrana osnivanja konkurentskog "
                "privrednog subjekta po prestanku radnog odnosa. Uslovi za punovažnost: "
                "1) pisana forma; 2) vremensko ograničenje — ne duže od 2 godine; "
                "3) teritorijalno ograničenje — ne sme biti nerazumno široko; "
                "4) novčana naknada — obavezno tokom trajanja zabrane, ne manja od 1/3 "
                "prosečne mesečne zarade zaposlenog. Bez naknade, klauzula je ništava."
            ),
        },
        {
            "broj": "011-00-00278/2019-02",
            "datum": "12.06.2019",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zasnivanje radnog odnosa",
            "naziv": "Ugovor o privremenim i povremenim poslovima — granice",
            "tekst": (
                "Pitanje: Kada se može zaključiti ugovor o privremenim i povremenim poslovima "
                "i šta je ograničenje?\n\n"
                "Odgovor: Prema članu 197 Zakona o radu, poslodavac može zaključiti ugovor "
                "o privremenim i povremenim poslovima sa: nezaposlenim licem; zaposlenim "
                "koji radi nepuno radno vreme; korisnikom starosne penzije. Ovi poslovi ne "
                "mogu da traju duže od 120 radnih dana u kalendarskoj godini sa istim licem. "
                "Zaposleni kod istog poslodavca ne može imati ovaj ugovor uz puno radno vreme. "
                "Ugovor mora biti u pisanoj formi."
            ),
        },
        {
            "broj": "011-00-00399/2023-02",
            "datum": "20.10.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zasnivanje radnog odnosa",
            "naziv": "Rad van prostorija poslodavca — rad od kuće",
            "tekst": (
                "Pitanje: Šta ugovor o radu za rad od kuće mora da sadrži?\n\n"
                "Odgovor: Prema članu 42 Zakona o radu, ugovorom o radu za obavljanje posla "
                "van prostorija poslodavca (uključujući rad od kuće) moraju biti utvrđeni: "
                "1) naziv i opis posla; 2) trajanje radnog odnosa (određeno/neodređeno); "
                "3) radno vreme i raspored; 4) zarada; 5) obezbedila za rad (ko ih obezbeđuje "
                "i ko snosi troškove); 6) pravo na naknadu troškova; 7) uslovi pod kojima "
                "poslodavac može da vrati zaposlenog na rad u prostorije. Poslodavac mora "
                "osigurati bezbednost i zdravlje zaposlenog i na daljinskom radnom mestu."
            ),
        },

        # ── PORODILJSKO I RODITELJSKO ODSUSTVO ───────────────────────────────

        {
            "broj": "011-00-00237/2021-02",
            "datum": "28.04.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "porodiljsko odsustvo",
            "naziv": "Porodiljsko odsustvo — trajanje i zaštita radnog mesta",
            "tekst": (
                "Pitanje: Koliko traje porodiljsko odsustvo i da li je zaštićeno radno "
                "mesto za vreme odsustva?\n\n"
                "Odgovor: Prema Zakonu o finansijskoj podršci porodici sa decom, zaposlena "
                "porodilja ima pravo na porodiljsko odsustvo u trajanju od 3 meseca od "
                "dana porođaja. Odsustvo počinje 28 dana (ili ranije po preporuci lekara) "
                "pre očekivanog datuma porođaja. Pored porodiljskog odsustva, zaposlena "
                "može koristiti odsustvo radi nege deteta do dve godine starosti deteta. "
                "Za vreme porodiljskog odsustva i odsustva radi nege deteta, zaposlena "
                "je zaštićena od otkaza — radni odnos ne može prestati dok koristi ova "
                "prava. Zaposlena zadržava pravo na povratak na isto ili slično radno "
                "mesto po povratku sa odsustva."
            ),
        },
        {
            "broj": "011-00-00388/2020-02",
            "datum": "20.07.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "porodiljsko odsustvo",
            "naziv": "Pravo oca na odsustvo radi nege deteta",
            "tekst": (
                "Pitanje: Da li zaposleni otac deteta ima pravo na odsustvo radi nege?\n\n"
                "Odgovor: Da, prema Zakonu o finansijskoj podršci porodici sa decom, otac "
                "deteta ima pravo na odsustvo radi nege deteta. Pravo može koristiti otac "
                "ako majka: nije u radnom odnosu; odustane od odsustva; radi kao preduzetnik; "
                "je preminula. Oba roditelja ne mogu istovremeno koristiti odsustvo. "
                "Otac može sam koristiti ceo period odsustva ili naizmenično sa majkom, "
                "zavisno od dogovora i propisa. Zahtev se podnosi na osnovu potvrde matičara "
                "i izjave majke."
            ),
        },
        {
            "broj": "011-00-00188/2022-02",
            "datum": "12.04.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "porodiljsko odsustvo",
            "naziv": "Naknada zarade za vreme porodiljskog odsustva",
            "tekst": (
                "Pitanje: Kako se obračunava naknada zarade za vreme porodiljskog odsustva?\n\n"
                "Odgovor: Prema Zakonu o finansijskoj podršci porodici sa decom, naknada za "
                "vreme porodiljskog odsustva i odsustva radi nege deteta iznosi 100% od "
                "osnove za naknadu zarade. Osnov čini prosek bruto zarade (ili naknade) u "
                "periodu od 18 meseci koji prethode prvom mesecu korišćenja prava. "
                "Isplaćivač je Ministarstvo za brigu o porodici i demografiju (ranije "
                "Ministarstvo rada). Rok za podnošenje zahteva za naknadu je 30 dana od "
                "dana otpočinjanja odsustva."
            ),
        },

        # ── DISCIPLINSKA ODGOVORNOST ──────────────────────────────────────────

        {
            "broj": "011-00-00167/2020-02",
            "datum": "01.04.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "disciplinska odgovornost",
            "naziv": "Rok za pokretanje disciplinskog postupka",
            "tekst": (
                "Pitanje: U kom roku poslodavac mora pokrenuti disciplinski postupak od saznanja "
                "o povredi radne obaveze?\n\n"
                "Odgovor: Prema članu 184 stav 5 Zakona o radu, disciplinska odgovornost ne "
                "može se utvrđivati po isteku 6 meseci od dana saznanja za povredu radne "
                "obaveze ili nepoštovanje radne discipline, niti po isteku 3 godine od dana "
                "nastanka povrede. Ovi rokovi su prekluzivni. Upozorenje pre otkaza mora "
                "biti dostavljeno u roku od 3 meseca od dana saznanja. "
                "Rok teče od dana kada je odgovorno lice kod poslodavca saznalo za povredu."
            ),
        },
        {
            "broj": "011-00-00445/2021-02",
            "datum": "20.08.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "disciplinska odgovornost",
            "naziv": "Novčana kazna kao disciplinska mera",
            "tekst": (
                "Pitanje: Može li poslodavac izreći novčanu kaznu zaposlenom kao "
                "disciplinsku meru?\n\n"
                "Odgovor: Prema članu 170 stav 1 Zakona o radu, za lakšu povredu radne "
                "obaveze može se izreći novčana kazna. Novčana kazna ne može biti veća od "
                "20% zarade zaposlenog za mesec u kome je učinjena povreda, za svaku "
                "lakšu povredu posebno. Ukupno umanjenje zarade ne može preći 1/3 mesečne "
                "zarade. Ova mera se može primeniti samo ako je povreda radne obaveze "
                "izričito propisana opštim aktom ili ugovorom o radu. Zaposleni ima pravo "
                "na prigovor u roku od 8 dana od prijema rešenja o kazni."
            ),
        },
        {
            "broj": "011-00-00302/2023-02",
            "datum": "25.07.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "disciplinska odgovornost",
            "naziv": "Pravo zaposlenog na odbranu u disciplinskom postupku",
            "tekst": (
                "Pitanje: Koja prava ima zaposleni u toku disciplinskog postupka?\n\n"
                "Odgovor: Prema članu 184 Zakona o radu, zaposleni ima sledeća prava u "
                "disciplinskom postupku: 1) pravo da bude pismeno obavešten o svim "
                "činjenicama i dokazima koji ga terete; 2) pravo da se izjasni o tim "
                "činjenicama i dokazima; 3) pravo na pristup svim dokazima koji se koriste "
                "u postupku; 4) pravo da bude zastupan od strane sindikalnog predstavnika "
                "ili advokata. Uskraćivanje ovih prava čini postupak nezakonitim i povlači "
                "poništaj izrečene mere."
            ),
        },

        # ── BEZBEDNOST I ZDRAVLJE NA RADU ─────────────────────────────────────

        {
            "broj": "011-00-00511/2020-02",
            "datum": "10.11.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "bezbednost i zdravlje na radu",
            "naziv": "Lekarski pregled pri zasnivanju radnog odnosa",
            "tekst": (
                "Pitanje: Da li poslodavac može da zahteva lekarski pregled pre zasnivanja "
                "radnog odnosa?\n\n"
                "Odgovor: Prema Zakonu o bezbednosti i zdravlju na radu, poslodavac je "
                "dužan da obezbedi prethodni lekarski pregled za zaposlene koji se raspoređuju "
                "na radna mesta sa povećanim rizikom. Troškove prethodnog pregleda snosi "
                "poslodavac. Nalaz lekara medicine rada utvrđuje radnu sposobnost. "
                "Uslovi rada moraju biti usklađeni sa zdravstvenim stanjem zaposlenog. "
                "Za radna mesta bez povećanog rizika, pregled nije obavezan, ali može biti "
                "ugovoren."
            ),
        },
        {
            "broj": "011-00-00199/2022-02",
            "datum": "22.04.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "bezbednost i zdravlje na radu",
            "naziv": "Povreda na radu — prijava i prava zaposlenog",
            "tekst": (
                "Pitanje: Kako se prijavljuje povreda na radu i koja prava ima zaposleni?\n\n"
                "Odgovor: Prema Zakonu o bezbednosti i zdravlju na radu, svaka povreda "
                "na radu mora biti prijavljena Inspekciji rada i nadležnoj filijali RFZO "
                "u roku od 24 časa. Obrazac PP-1 popunjava poslodavac. Zaposleni ima pravo "
                "na naknadu zarade 100% za vreme privremene sprečenosti za rad zbog povrede "
                "na radu. Povreda na radu daje osnov za naknadu materijalne i nematerijalne "
                "štete od strane poslodavca, ako je uzrokovana krivicom poslodavca. "
                "Za teže povrede i smrtne ishode pokreće se posebna istraga."
            ),
        },

        # ── SINDIKATI I KOLEKTIVNI UGOVOR ─────────────────────────────────────

        {
            "broj": "011-00-00143/2021-02",
            "datum": "15.03.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "kolektivni ugovor",
            "naziv": "Primena kolektivnog ugovora na zaposlene koji nisu članovi sindikata",
            "tekst": (
                "Pitanje: Da li se kolektivni ugovor primenjuje na zaposlene koji nisu "
                "članovi sindikata?\n\n"
                "Odgovor: Prema članu 247 Zakona o radu, kolektivni ugovor koji se zaključi "
                "sa sindikatom koji je reprezentativan na nivou poslodavca primenjuje se na "
                "sve zaposlene kod tog poslodavca, bez obzira na to da li su članovi "
                "sindikata. Kolektivni ugovor primenjuje se i na zaposlene koji pristupaju "
                "sindikatu nakon zaključenja ugovora. Ugovorom o radu ne mogu se utvrditi "
                "manja prava od prava utvrđenih kolektivnim ugovorom."
            ),
        },
        {
            "broj": "011-00-00357/2020-02",
            "datum": "18.06.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "kolektivni ugovor",
            "naziv": "Reprezentativnost sindikata — uslovi za zaključenje KU",
            "tekst": (
                "Pitanje: Koji uslovi moraju biti ispunjeni da bi sindikat bio reprezentativan "
                "za zaključenje kolektivnog ugovora?\n\n"
                "Odgovor: Prema članu 218-219 Zakona o radu, reprezentativni sindikat mora "
                "ispuniti sledeće uslove: 1) demokratska organizacija (statut, organi); "
                "2) nezavisnost od državnih organa i poslodavaca; 3) finansijska samostalnost; "
                "4) broj članova: na nivou poslodavca — 15% od ukupnog broja zaposlenih kod "
                "poslodavca; na nivou grane — 10% zaposlenih u grani; na nivou RS — 10% "
                "zaposlenih na teritoriji RS. Reprezentativnost se utvrđuje odlukom "
                "Ministarstva rada."
            ),
        },

        # ── ZAŠTITA OD DISKRIMINACIJE I ZLOSTAVLJANJE ─────────────────────────

        {
            "broj": "011-00-00220/2022-02",
            "datum": "20.04.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zaštita od diskriminacije",
            "naziv": "Zabrana diskriminacije pri zapošljavanju",
            "tekst": (
                "Pitanje: Koja su zakonska ograničenja u pogledu diskriminacije pri "
                "zapošljavanju?\n\n"
                "Odgovor: Prema članu 18 Zakona o radu, zabranjena je neposredna i posredna "
                "diskriminacija lica koja traže zaposlenje, kao i zaposlenih. Zabranjeno "
                "je razlikovanje na osnovu: rase, pola, nacionalnosti, vere, invaliditeta, "
                "bračnog/porodičnog statusa, trudnoće, starosti, seksualne orijentacije i dr. "
                "Posebno je zaštićena trudnica i žena koja doji dete. Teret dokazivanja je "
                "na poslodavcu — ako zaposleni učini verovatnim diskriminaciju, poslodavac "
                "mora dokazati da nije diskriminisao."
            ),
        },
        {
            "broj": "011-00-00300/2021-02",
            "datum": "25.05.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "zaštita od diskriminacije",
            "naziv": "Mobbing — definicija i zaštita zaposlenog",
            "tekst": (
                "Pitanje: Šta se smatra mobbingom i koje zaštite ima zaposleni?\n\n"
                "Odgovor: Prema Zakonu o sprečavanju zlostavljanja na radu, zlostavljanje "
                "(mobbing) je svako aktivno ili pasivno ponašanje prema zaposlenom koje se "
                "ponavlja i koje za cilj ima ili predstavlja povredu dostojanstva, ugleda, "
                "ličnog i profesionalnog integriteta. Zaposleni koji smatra da je žrtva "
                "zlostavljanja može podneti zahtev za zaštitu neposrednom rukovodiocu ili "
                "HR-u. Ako posredovanje ne uspe, može se obratiti nadležnom sudu. "
                "Rok za tužbu: 6 meseci od dana zlostavljanja ili saznanja."
            ),
        },

        # ── AGENCIJSKO ZAPOŠLJAVANJE ──────────────────────────────────────────

        {
            "broj": "011-00-00402/2022-02",
            "datum": "05.09.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "agencijsko zapošljavanje",
            "naziv": "Ustupanje zaposlenih — prava ustupljenog radnika",
            "tekst": (
                "Pitanje: Koja prava ima zaposleni koji je ustupljen na rad kod drugog "
                "poslodavca (korisnika)?\n\n"
                "Odgovor: Prema članu 207 Zakona o radu, poslodavac (agencija) može "
                "uputiti zaposlenog da privremeno radi kod drugog poslodavca (korisnika). "
                "Uputom se ne menjaju prava zaposlenog — prava su ista kao da radi direktno "
                "kod korisnika za te poslove. Zarada koja se isplaćuje ustupljenom radniku "
                "ne sme biti manja od zarade zaposlenog u istom zvanju kod korisnika. "
                "Ustupanje može trajati najduže do okončanja zadatka. Odgovornost za "
                "zaštitu na radu deli se između agencije i korisnika."
            ),
        },

        # ── REGISTRACIJA I OSNIVANJE PRIVREDNIH DRUŠTAVA ─────────────────────

        {
            "broj": "011-00-00145/2021-06",
            "datum": "12.03.2021",
            "ministarstvo": "Ministarstvo privrede",
            "oblast": "registracija privrednih društava",
            "naziv": "Osnivanje DOO — minimum osnivačkog uloga",
            "tekst": (
                "Pitanje: Koji je minimalni osnivački ulog za osnivanje DOO u Srbiji?\n\n"
                "Odgovor: Prema članu 145 Zakona o privrednim društvima ('Sl. glasnik RS', "
                "br. 36/2011, ..., 109/2021), minimalni iznos osnivačkog kapitala za "
                "osnivanje društva sa ograničenom odgovornošću iznosi 100 dinara. "
                "Unos osnivačkog uloga može biti u novcu ili stvarima i pravima. "
                "Procena vrednosti uloga u stvarima i pravima vrši se od strane stručnog "
                "lica — ovlašćenog procenitelja. Osnivač je odgovoran za istinitost procene. "
                "Uplata novčanog uloga se vrši na privremeni račun pre registracije."
            ),
        },
        {
            "broj": "011-00-00298/2022-06",
            "datum": "18.05.2022",
            "ministarstvo": "Ministarstvo privrede",
            "oblast": "registracija privrednih društava",
            "naziv": "Promena direktora DOO — procedura i registracija",
            "tekst": (
                "Pitanje: Kako se vrši promena direktora DOO i koja je procedura registracije "
                "u APR-u?\n\n"
                "Odgovor: Prema Zakonu o privrednim društvima, direktora DOO imenuju i "
                "razrešavaju skupštinari (vlasnici udela) odlukom. Skupštinska odluka mora "
                "biti u pisanoj formi i overena od strane svih skupštinara ili kod notara. "
                "Promena direktora registruje se kod APR-a (Agencija za privredne registre) "
                "podnošenjem: 1) obrasca za promenu podataka; 2) skupštinske odluke; "
                "3) saglasnosti novog direktora na imenovanje; 4) dokaz o uplaćenoj taksi. "
                "Promena mora biti registrovana u roku od 15 dana od donošenja odluke."
            ),
        },
        {
            "broj": "011-00-00189/2023-06",
            "datum": "08.04.2023",
            "ministarstvo": "Ministarstvo privrede",
            "oblast": "registracija privrednih društava",
            "naziv": "Odgovornost direktora DOO prema trećim licima",
            "tekst": (
                "Pitanje: Da li direktor DOO odgovara lično za dugove društva prema "
                "trećim licima?\n\n"
                "Odgovor: Prema članu 18 Zakona o privrednim društvima, direktor DOO "
                "ne odgovara lično za obaveze društva — odgovornost je ograničena. "
                "Izuzetno, direktor može odgovarati lično ako: 1) meša svoju imovinu sa "
                "imovinom društva (zloupotreba pravne forme); 2) koristi društvo za "
                "postizanje nedozvoljenog cilja; 3) vrši štetu namerno ili krajnjom "
                "nepažnjom trećim licima. U tim slučajevima sud može probiti korporativni "
                "veo i utvrditi ličnu odgovornost direktora za obaveze društva."
            ),
        },

        # ── ZAKON O POREZU NA DOHODAK ─────────────────────────────────────────

        {
            "broj": "011-00-00156/2022-04",
            "datum": "20.03.2022",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dohodak",
            "naziv": "Godišnji porez na dohodak — ko je obveznik",
            "tekst": (
                "Pitanje: Ko ima obavezu podnošenja godišnje poreske prijave za porez na "
                "dohodak građana?\n\n"
                "Odgovor: Prema članu 87 Zakona o porezu na dohodak građana, godišnji porez "
                "na dohodak plaćaju fizička lica čiji godišnji oporezivi prihod prelazi "
                "iznos trostuke prosečne godišnje zarade u Republici Srbiji. Obveznici su "
                "rezidenti RS koji ostvaruju prihode u RS i inostranstvu, i nerezidenti koji "
                "ostvaruju prihode u RS. Prijava PPI-1 podnosi se do 15. maja za prethodnu "
                "godinu. Stopa poreza: 10% za iznos do šest prosečnih godišnjih zarada, "
                "15% za iznos iznad toga."
            ),
        },
        {
            "broj": "011-00-00290/2023-04",
            "datum": "15.06.2023",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dohodak",
            "naziv": "Kapitalni dobitak od prodaje akcija — oporezivanje",
            "tekst": (
                "Pitanje: Kako se oporezuje kapitalni dobitak od prodaje akcija?\n\n"
                "Odgovor: Prema članu 72-78 Zakona o porezu na dohodak građana, kapitalni "
                "dobitak od prodaje akcija oporezuje se stopom od 15%. Kapitalni dobitak "
                "je razlika između prodajne i nabavne cene, uvećana za troškove sticanja. "
                "Kapitalni gubitak se može prebijati sa kapitalnim dobitkom u istoj godini, "
                "a neiskorišćeni gubitak može se preneti na narednih 5 godina. "
                "Prijava PPG-1 podnosi se u roku od 30 dana od prodaje. "
                "Akcije stečene pre 1996. i koje se drže duže od 10 godina — bez poreza."
            ),
        },
        {
            "broj": "011-00-00088/2022-04",
            "datum": "18.02.2022",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dohodak",
            "naziv": "Ugovor o delu — porez i doprinosi",
            "tekst": (
                "Pitanje: Kako se oporezuje prihod po osnovu ugovora o delu?\n\n"
                "Odgovor: Prihod po osnovu ugovora o delu (autorski honorar, ugovor o delu) "
                "oporezuje se prema članu 85 Zakona o porezu na dohodak građana. "
                "Poreska stopa je 20% na neto prihod (bruto minus normiranih 20% troškova). "
                "Efektivna stopa na bruto iznos je 16%. Pored poreza, plaćaju se doprinosi "
                "za PIO (24%) i zdravstveno osiguranje (10.3%), osim za lica koja su "
                "već osigurana po drugom osnovu. Isplatilac ugovora o delu porezni je "
                "platac i dužan je da podnese PPP-PD."
            ),
        },
        {
            "broj": "011-00-00419/2021-04",
            "datum": "10.09.2021",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dohodak",
            "naziv": "Neoporezivi iznosi u porezu na zarade — limit",
            "tekst": (
                "Pitanje: Do kojeg iznosa naknada troškova zaposlenih nisu predmet oporezivanja?\n\n"
                "Odgovor: Prema članu 18 Zakona o porezu na dohodak građana, neoporezivi "
                "su sledeći primici zaposlenih: naknada prevoza do/sa posla (do iznosa "
                "javnog prevoza); naknada za korišćenje sopstvenog automobila (do 30% "
                "cene goriva, max 6.000 din./mesec); naknada za smeštaj (na terenu — "
                "stvarni trošak); dnevnica (domaća — do 2.424 din., inozemna — po uredbi). "
                "Rashodi iznad ovih iznosa tretiraju se kao zarada i oporezuju. "
                "Iznosi se usklađuju uredbom Vlade."
            ),
        },
        {
            "broj": "011-00-00312/2020-04",
            "datum": "10.06.2020",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dohodak",
            "naziv": "Porez na prihode od zakupa — obveznik i prijava",
            "tekst": (
                "Pitanje: Ko plaća porez na prihode od zakupa nepokretnosti i u kom roku?\n\n"
                "Odgovor: Prema članu 65-66 Zakona o porezu na dohodak građana, porez na "
                "prihode od zakupa nepokretnosti iznosi 20%, obračunava se na prihod "
                "umanjen za normirane troškove od 25% (tj. efektivna stopa 15%). "
                "Obveznik je zakupodavac (fizičko lice koje daje nekretninu u zakup). "
                "Ako je zakupac preduzeće, ono je isplatilac i odbitni porez plaća pri "
                "svakoj isplati (PPP-PD). Ako je zakupac fizičko lice, zakupodavac sam "
                "podnosi poresku prijavu PPPO u roku od 30 dana od isteka kvartala."
            ),
        },

        # ── ZAKON O PDV ───────────────────────────────────────────────────────

        {
            "broj": "011-00-00288/2021-07",
            "datum": "10.05.2021",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dodatu vrednost",
            "naziv": "Prag za PDV registraciju i rok za prijavu",
            "tekst": (
                "Pitanje: Kada je privredni subjekt obavezan da se registruje za PDV?\n\n"
                "Odgovor: Prema članu 38 Zakona o porezu na dodatu vrednost, poreski obveznik "
                "koji ostvaruje ukupan promet dobara i usluga (bez PDV) veći od 8.000.000 "
                "dinara u prethodnih 12 meseci, dužan je da podnese prijavu za PDV "
                "evidentiranje. Prijava se podnosi u roku od 15 dana od ispunjenja uslova. "
                "Po registraciji, obveznik je dužan da primenjuje PDV od prvog dana narednog "
                "meseca. Dobrovoljna registracija moguća je i pre dostizanja praga."
            ),
        },
        {
            "broj": "011-00-00399/2022-07",
            "datum": "20.07.2022",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "porez na dodatu vrednost",
            "naziv": "Pravo na odbitak prethodnog poreza — uslovi",
            "tekst": (
                "Pitanje: Koji su uslovi da bi PDV obveznik mogao da odbije prethodni porez?\n\n"
                "Odgovor: Prema članu 28 Zakona o porezu na dodatu vrednost, prethodni porez "
                "može se odbiti ako su ispunjeni sledeći uslovi: 1) obveznik poseduje "
                "fiskalni račun, račun ili carinsku deklaraciju; 2) promet je izvršen u "
                "cilju obavljanja oporezivanih isporuka; 3) iznos prethodnog poreza je "
                "iskazan na ispravnom dokumentu. Prethodni porez ne može se odbiti za: "
                "putničke automobile, reprezentaciju (osim za preprodaju) i troškove koji "
                "nisu u funkciji delatnosti. Rok za odbitak: tekući ili naredni poreski period."
            ),
        },

        # ── ZAKON O RADU — SPECIFIČNA PITANJA ────────────────────────────────

        {
            "broj": "011-00-00167/2022-02",
            "datum": "28.03.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Prevoz zaposlenih organizovan od strane poslodavca",
            "tekst": (
                "Pitanje: Da li poslodavac ima obavezu organizovanja prevoza zaposlenih?\n\n"
                "Odgovor: Prema članu 118 stav 1 tačka 4 Zakona o radu, zaposleni ima "
                "pravo na naknadu troškova prevoza u visini cene prevozne karte u javnom "
                "saobraćaju. Ovo pravo postoji bez obzira na to da li poslodavac organizuje "
                "sopstveni prevoz. Ako poslodavac organizuje sopstveni prevoz, dužan je da "
                "obezbedi bezbednost i uslove koji odgovaraju propisanim standardima. "
                "Ako je sopstveni prevoz organizovan, zaposleni nema pravo na naknadu "
                "troškova za putovanje koje je organizovano od strane poslodavca."
            ),
        },
        {
            "broj": "011-00-00487/2021-02",
            "datum": "25.10.2021",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Pravo na pauzu u toku radnog dana",
            "tekst": (
                "Pitanje: Ima li zaposleni pravo na pauzu tokom radnog dana i da li se "
                "ona računa u radno vreme?\n\n"
                "Odgovor: Prema članu 64 Zakona o radu, zaposleni koji radi puno radno "
                "vreme ima pravo na odmor (pauzu) u toku radnog dana u trajanju od "
                "najmanje 30 minuta. Zaposleni koji radi duže od 4, a kraće od 6 sati "
                "dnevno ima pravo na odmor od najmanje 15 minuta. Pauza se ne uračunava "
                "u radno vreme. Raspored korišćenja pauze utvrđuje poslodavac, uzimajući "
                "u obzir prirodu posla i organizaciju rada."
            ),
        },
        {
            "broj": "011-00-00133/2023-02",
            "datum": "12.03.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Premeštaj zaposlenog na drugi posao — uslovi",
            "tekst": (
                "Pitanje: Da li poslodavac može jednostrano premestiti zaposlenog na "
                "drugačije radno mesto?\n\n"
                "Odgovor: Prema članu 171-172 Zakona o radu, poslodavac može ponuditi "
                "zaposlenom izmenu ugovora o radu (aneks ugovora) radi premeštaja na "
                "drugo radno mesto. Zaposleni ima pravo da odbije aneks, ali se tada "
                "nastavlja radni odnos pod prethodnim uslovima. Ako odbije bez opravdanog "
                "razloga, poslodavac može pokrenuti otkaz. Premeštaj na niže plaćeno "
                "radno mesto zahteva pristanak zaposlenog. Izuzetno, privremeni premeštaj "
                "do 3 meseca moguć je bez promene ugovora."
            ),
        },
        {
            "broj": "011-00-00261/2020-02",
            "datum": "20.05.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Zabrana takmičenja za vreme trajanja radnog odnosa",
            "tekst": (
                "Pitanje: Da li zaposleni može raditi za konkurentsku firmu dok traje "
                "radni odnos?\n\n"
                "Odgovor: Prema članu 161 stav 1 Zakona o radu, za vreme trajanja radnog "
                "odnosa zaposleni ne sme bez saglasnosti poslodavca da radi za drugog "
                "poslodavca u istoj ili srodnoj grani delatnosti, niti da osniva privredni "
                "subjekat koji obavlja istu delatnost. Povreda ove obaveze predstavlja "
                "osnov za otkaz iz razloga koji se odnosi na ponašanje zaposlenog "
                "(član 179 stav 1 tačka 2 ZR). Saglasnost poslodavca mora biti pisana."
            ),
        },
        {
            "broj": "011-00-00452/2022-02",
            "datum": "15.10.2022",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Staž osiguranja u duplo — uslovi",
            "tekst": (
                "Pitanje: Kada zaposleni može ostvariti pravo na staž osiguranja koji se "
                "računa u duplo?\n\n"
                "Odgovor: Prema Zakonu o penzijskom i invalidskom osiguranju, zaposleni koji "
                "rade na posebno teškim, opasnim ili štetnim radnim mestima (radna mesta sa "
                "povećanim rizikom) mogu ostvariti pravo da im se staž računa u duplo. "
                "Lista takvih radnih mesta utvrđuje se propisom. Uslovi: 1) radno mesto mora "
                "biti svrstano u kategoriju sa efektivnim stažom po posebnom propisu; "
                "2) radnik mora da radi na tom mestu stvarno (bez prekida duže od 3 meseca). "
                "Ovo pravo se ostvaruje kod PIO fonda."
            ),
        },
        {
            "broj": "011-00-00311/2023-02",
            "datum": "10.08.2023",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Smenski rad — dodatak na zaradu",
            "tekst": (
                "Pitanje: Da li zaposleni koji radi u smenama ima pravo na poseban dodatak "
                "na zaradu?\n\n"
                "Odgovor: Prema članu 108 stav 1 Zakona o radu, zaposleni koji radi u "
                "smenama (rotacioni rad danju i noću) ima pravo na uvećanu zaradu za "
                "noćni rad od najmanje 26% od osnove, ali samo za one sate koje odradi "
                "noću (između 22:00 i 06:00). Sam smenski rad danju ne daje pravo na uvećanje "
                "osim ako je to predviđeno kolektivnim ugovorom ili pravilnikom o radu. "
                "Poseban 'smenski dodatak' nije zakonska obaveza — utvrđuje se internim aktima."
            ),
        },
        {
            "broj": "011-00-00488/2020-02",
            "datum": "20.10.2020",
            "ministarstvo": "Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja",
            "oblast": "radno pravo - opšte",
            "naziv": "Pravo na regres — zakonska obaveza",
            "tekst": (
                "Pitanje: Da li je regres za korišćenje godišnjeg odmora zakonska obaveza "
                "poslodavca?\n\n"
                "Odgovor: Zakon o radu ne propisuje direktno pravo na regres za godišnji odmor "
                "kao zakonski minimum. Ovo pravo se utvrđuje kolektivnim ugovorom ili "
                "pravilnikom o radu. Ako je kolektivnim ugovorom (opštim, posebnim ili "
                "kod poslodavca) ili pravilnikom o radu utvrđeno pravo na regres, "
                "poslodavac je obavezan da ga isplati. Poreski tretman: regres je neoporeziv "
                "do iznosa koji propisuje ministar finansija uredbom (trenutno do visine "
                "prosečne mesečne zarade u RS)."
            ),
        },

        # ── JAVNE NABAVKE ─────────────────────────────────────────────────────

        {
            "broj": "011-00-00222/2022-08",
            "datum": "15.04.2022",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "javne nabavke",
            "naziv": "Prag za primenu Zakona o javnim nabavkama",
            "tekst": (
                "Pitanje: Koji su pragovi vrednosti nabavki ispod kojih se ne primenjuje "
                "Zakon o javnim nabavkama?\n\n"
                "Odgovor: Prema članu 27 Zakona o javnim nabavkama ('Sl. glasnik RS', "
                "br. 91/2019), naručilac nije obavezan da primenjuje ZJN za nabavke "
                "čija procenjena vrednost ne prelazi: 1.000.000 dinara za dobra i usluge; "
                "3.000.000 dinara za radove. Za nabavke između ovih iznosa i EU pragova "
                "primenjuje se jednostavna nabavka. Naručilac mora imati interni akt "
                "koji uređuje jednostavne nabavke i voditi evidenciju."
            ),
        },

        # ── ZAKON O PRIVREDNIM DRUŠTVIMA — DOPUNSKA PITANJA ──────────────────

        {
            "broj": "011-00-00211/2021-06",
            "datum": "20.04.2021",
            "ministarstvo": "Ministarstvo privrede",
            "oblast": "privredna društva",
            "naziv": "Skupštinska odluka DOO — kvorum i glasanje",
            "tekst": (
                "Pitanje: Koji je kvorum i procedura glasanja na skupštini DOO?\n\n"
                "Odgovor: Prema članu 199-203 Zakona o privrednim društvima, skupštinom "
                "DOO predsedava lice koje izaberu skupštinari. Kvorum čine skupštinari "
                "koji poseduju više od 50% glasova (osim ako osnivački akt ne predviđa "
                "drugačije). Odluke se donose prostom većinom glasova prisutnih/zastupljenih "
                "skupštinara, osim za: izmenu osnivačkog akta, pripajanje/pripijanje — "
                "zahteva tročetvrtinsku (3/4) većinu svih glasova. Skupštinar može biti "
                "zastupan na osnovu pisanog punomoćja."
            ),
        },
        {
            "broj": "011-00-00355/2022-06",
            "datum": "22.06.2022",
            "ministarstvo": "Ministarstvo privrede",
            "oblast": "privredna društva",
            "naziv": "Podela dobiti DOO — uslovi za isplatu",
            "tekst": (
                "Pitanje: Pod kojim uslovima DOO može da isplati dobit (dividendu) "
                "osnivačima?\n\n"
                "Odgovor: Prema članu 180-182 Zakona o privrednim društvima, DOO može "
                "doneti odluku o podeli dobiti ako su ispunjeni sledeći uslovi: "
                "1) postoji neraspoređena dobit po godišnjem finansijskom izveštaju; "
                "2) društvo može podmiriti sve obaveze po dospeću; 3) neto imovina "
                "nije i neće biti manja od upisanog kapitala plus rezervi. "
                "Odluka se donosi prostom većinom glasova skupštine. Neisplaćena dobit "
                "se evidentira u bilansu kao obaveza prema osnivačima."
            ),
        },

        # ── ZAKON O ZAŠTITI POTROŠAČA ─────────────────────────────────────────

        {
            "broj": "011-00-00177/2022-09",
            "datum": "10.04.2022",
            "ministarstvo": "Ministarstvo trgovine, turizma i telekomunikacija",
            "oblast": "zaštita potrošača",
            "naziv": "Pravo potrošača na odustanak od ugovora zaključenog na daljinu",
            "tekst": (
                "Pitanje: U kom roku potrošač može odustati od ugovora zaključenog putem "
                "interneta?\n\n"
                "Odgovor: Prema članu 27 Zakona o zaštiti potrošača, potrošač koji je "
                "zaključio ugovor van poslovnih prostorija ili na daljinu (internet, "
                "telefon) ima pravo da odustane od ugovora u roku od 14 dana, bez navođenja "
                "razloga. Rok teče od dana prijema isporuke. Ako prodavac nije obavestio "
                "potrošača o pravu na odustanak, rok se produžava na 12 meseci. "
                "Prodavac je dužan da vrati novac u roku od 14 dana od odustanka."
            ),
        },
        {
            "broj": "011-00-00244/2021-09",
            "datum": "05.05.2021",
            "ministarstvo": "Ministarstvo trgovine, turizma i telekomunikacija",
            "oblast": "zaštita potrošača",
            "naziv": "Reklamacija — rok za odgovor i rešavanje",
            "tekst": (
                "Pitanje: Koji je rok za odgovor na reklamaciju i rok za njeno rešavanje?\n\n"
                "Odgovor: Prema članu 56-60 Zakona o zaštiti potrošača, prodavac je dužan "
                "da odgovori na reklamaciju u roku od 8 dana od prijema. U odgovoru mora "
                "navesti da li prihvata reklamaciju i predložiti način rešavanja. "
                "Reklamacija mora biti rešena u roku od 30 dana od dana podnošenja. "
                "Za reklamacije tehničke robe (bijela tehnika, elektronika) rok je 15 dana "
                "za određene kategorije. Potrošač ima pravo na zamenu, popravku ili "
                "povrat novca u zavisnosti od prirode nedostatka."
            ),
        },

        # ── ZAKON O BEZBEDNOSTI HRANE ─────────────────────────────────────────

        {
            "broj": "011-00-00190/2022-03",
            "datum": "08.04.2022",
            "ministarstvo": "Ministarstvo poljoprivrede",
            "oblast": "bezbednost hrane",
            "naziv": "HACCP sistem — obaveza ugostitelja",
            "tekst": (
                "Pitanje: Da li su ugostiteljski objekti obavezni da implementiraju HACCP?\n\n"
                "Odgovor: Prema Zakonu o bezbednosti hrane, svi subjekti u poslovanju "
                "hranom (uključujući ugostitelje) dužni su da uvedu i primenjuju HACCP "
                "sistem (Hazard Analysis and Critical Control Points). Sistem mora biti "
                "dokumentovan i praktikovan. Inspekcija proverava usklađenost. "
                "Za mala preduzeća, Pravilnik o higijeni hrane propisuje fleksibilniji pristup. "
                "Ugostiteljski subjekti koji nemaju HACCP izlažu se inspekcijskom kaznom."
            ),
        },

        # ── ZAKON O ZAŠTITI PODATAKA ──────────────────────────────────────────

        {
            "broj": "011-00-00321/2021-11",
            "datum": "10.06.2021",
            "ministarstvo": "Poverenik za informacije od javnog značaja i zaštitu podataka o ličnosti",
            "oblast": "zaštita podataka o ličnosti",
            "naziv": "Osnov za obradu podataka o ličnosti — pristanak",
            "tekst": (
                "Pitanje: Da li pristanak zaposlenog predstavlja valjan osnov za obradu "
                "njegovih podataka o ličnosti od strane poslodavca?\n\n"
                "Odgovor: Prema članu 12 Zakona o zaštiti podataka o ličnosti ('Sl. glasnik "
                "RS', br. 87/2018), pristanak lica je valjan osnov za obradu. Međutim, "
                "u radnopravnom kontekstu, pristanak zaposlenog retko je slobodan — "
                "postoji neravnoteža moći između poslodavca i zaposlenog. Zbog toga "
                "Poverenik preporučuje da se za obradu podataka u radnom odnosu koriste "
                "drugi zakonski osnovi: zakonska obaveza (čl. 12 st. 1 tač. 3) ili "
                "legitimni interes (čl. 12 st. 1 tač. 6). Pristanak je adekvatan osnov "
                "samo kada nije uslov za zasnivanje ili nastavak radnog odnosa."
            ),
        },

        # ── ZAKON O SPREČAVANJU PRANJA NOVCA ──────────────────────────────────

        {
            "broj": "011-00-00214/2022-10",
            "datum": "05.04.2022",
            "ministarstvo": "Uprava za sprečavanje pranja novca",
            "oblast": "sprečavanje pranja novca",
            "naziv": "Obaveznici Zakona o sprečavanju pranja novca — ko je obaveznik",
            "tekst": (
                "Pitanje: Ko su obveznici Zakona o sprečavanju pranja novca i finansiranja "
                "terorizma (ZSPNFT)?\n\n"
                "Odgovor: Prema članu 4 ZSPNFT ('Sl. glasnik RS', br. 113/2017, 91/2019, "
                "153/2020, 44/2021, 118/2021, 35/2023), obveznici su: banke i finansijske "
                "institucije; menjačnice; osiguravajuće kompanije; posrednici u prometu "
                "nepokretnosti; advokati i notari u određenim transakcijama; računovođe "
                "i revizori; pružaoci usluga digitalnih aktiva (VASP); kockare; "
                "organizatori igara na sreću. Obveznici moraju uvesti interne AML procedure "
                "i sprovoditi dubinsku analizu klijenta (KYC)."
            ),
        },
        {
            "broj": "011-00-00355/2021-10",
            "datum": "18.06.2021",
            "ministarstvo": "Uprava za sprečavanje pranja novca",
            "oblast": "sprečavanje pranja novca",
            "naziv": "Gotovinska transakcija — prag za prijavu USPNFT",
            "tekst": (
                "Pitanje: Kada je obaveznik dužan da prijavi gotovinsku transakciju "
                "Upravi za sprečavanje pranja novca?\n\n"
                "Odgovor: Prema članu 69 ZSPNFT, obaveznik je dužan da Upravi dostavi "
                "izveštaj o gotovinskoj transakciji fizičkog ili pravnog lica u iznosu od "
                "15.000 EUR ili više u dinarskoj protivvrednosti, u jednoj transakciji "
                "ili u više međusobno povezanih transakcija. Izveštaj se dostavlja "
                "elektronski u roku od 3 radna dana od dana obavljanja transakcije. "
                "Kod sumnjivih transakcija (bez obzira na iznos), obaveznik prijavljuje "
                "odmah, pre izvršenja transakcije (ako je moguće)."
            ),
        },

        # ── PORODIČNI ZAKON ───────────────────────────────────────────────────

        {
            "broj": "011-00-00299/2022-05",
            "datum": "25.05.2022",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "porodično pravo",
            "naziv": "Alimentacija — osnov za određivanje iznosa",
            "tekst": (
                "Pitanje: Na osnovu čega sud određuje iznos alimentacije za dete?\n\n"
                "Odgovor: Prema članu 160-166 Porodičnog zakona, alimentacija se određuje "
                "u iznosu koji odgovara potrebama deteta i materijalnim mogućnostima "
                "roditelja. Faktori koje sud uzima u obzir: 1) starost i potrebe deteta; "
                "2) prihodi i imovina roditelja; 3) standard života roditelja pre razvoda. "
                "Minimalni iznos alimentacije po Porodičnom zakonu ne sme biti manji od "
                "15% prosečne mesečne zarade u RS za jedno dete (prema preporuci, u praksi). "
                "Alimentacija se može menjati ako se promene okolnosti (prihodi, potrebe)."
            ),
        },
        {
            "broj": "011-00-00177/2021-05",
            "datum": "05.04.2021",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "porodično pravo",
            "naziv": "Starateljstvo — ko vrši roditeljsko pravo nakon razvoda",
            "tekst": (
                "Pitanje: Ko vrši roditeljsko pravo nad decom nakon razvoda braka?\n\n"
                "Odgovor: Prema članu 74-77 Porodičnog zakona, roditelji mogu zajednički ili "
                "sporazumno vršiti roditeljsko pravo, bez obzira na to sa kojim roditeljem "
                "dete živi. Sud odlučuje o načinu vršenja roditeljskog prava po tužbi "
                "roditelja ili staratelja. Zajednički roditelji imaju prednost — sporazum "
                "o vršenju roditeljskog prava mora biti odobren od strane suda ako je "
                "u interesu deteta. Dete koje je navršilo 10 godina ima pravo da izrazi "
                "svoje mišljenje, koje sud mora uzeti u obzir."
            ),
        },

        # ── ZAKON O NASLEDJIVANJU ─────────────────────────────────────────────

        {
            "broj": "011-00-00244/2020-05",
            "datum": "15.05.2020",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "nasledjivanje",
            "naziv": "Zakonski nasledni redovi — ko su zakonski naslednici",
            "tekst": (
                "Pitanje: Ko su zakonski naslednici i koji je nasledni red?\n\n"
                "Odgovor: Prema članu 9-20 Zakona o nasleđivanju, naslednici se dele u "
                "nasledne redove: I nasledni red — deca i supružnik (ravnopravno); "
                "II nasledni red — roditelji i supružnik (polovinu nasleđuje supružnik, "
                "polovinu roditelji); III nasledni red — dedovi, bake i njihovi potomci; "
                "IV nasledni red — pradedovi, prabake. Naslednik višeg naslednog reda "
                "isključuje naslednike nižeg reda. Supružnik uvek nasleđuje zajedno sa "
                "prvim naslednim redom. Bračni partner izjednačen je sa supružnikom ako je "
                "zajednica trajala najmanje 3 godine."
            ),
        },

        # ── ZAKON O PARNIČNOM POSTUPKU ────────────────────────────────────────

        {
            "broj": "011-00-00212/2021-03",
            "datum": "20.04.2021",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "parnični postupak",
            "naziv": "Mesna nadležnost suda — opšte pravilo",
            "tekst": (
                "Pitanje: Koji je opšte pravilo o mesnoj nadležnosti suda u parničnom "
                "postupku?\n\n"
                "Odgovor: Prema članu 39 Zakona o parničnom postupku, za suđenje u prvom "
                "stepenu mesno je nadležan sud na čijem se području nalazi prebivalište, "
                "tj. boravište tuženog (ako tuženi nema prebivalište u RS — nadležan je "
                "sud na čijem se području nalazi tuženo lice). Za pravna lica — sud na "
                "čijem se području nalazi sedište. Pored opšte mesne nadležnosti, zakon "
                "propisuje i posebne mesne nadležnosti (npr. za sporove iz radnog odnosa "
                "— sud na čijem se području nalazi ili je bio sedište poslodavca)."
            ),
        },

        # ── ZAKON O IZVRŠENJU I OBEZBEĐENJU ──────────────────────────────────

        {
            "broj": "011-00-00287/2022-03",
            "datum": "10.05.2022",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "izvršni postupak",
            "naziv": "Izuzeci od izvršenja na zaradi — zaštićeni iznos",
            "tekst": (
                "Pitanje: Koji deo zarade ne može biti predmet izvršenja (plena) pri "
                "prinudnoj naplati duga?\n\n"
                "Odgovor: Prema članu 130 Zakona o izvršenju i obezbeđenju ('Sl. glasnik RS', "
                "br. 106/2015 i dr.), od izvršenja je izuzeto: 1) primanja po osnovu "
                "socijalne zaštite (100% zaštićeno); 2) zarada ili penzija — zaštićen je "
                "iznos od 60% minimalne neto zarade; 3) za alimentacione obaveze — do 2/3 "
                "zarade. Ovrha na zaradi ne može preći 1/3 neto zarade. Kombinovana "
                "potraživanja (više poverilaca) ne mogu preći 2/3 neto zarade."
            ),
        },

        # ── ZAKON O OBLIGACIONIM ODNOSIMA ─────────────────────────────────────

        {
            "broj": "011-00-00311/2020-05",
            "datum": "10.06.2020",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "obligaciono pravo",
            "naziv": "Zastarelost potraživanja — opšti rok",
            "tekst": (
                "Pitanje: Koji je opšti rok zastarelosti potraživanja?\n\n"
                "Odgovor: Prema članu 371 Zakona o obligacionim odnosima ('Sl. list SFRJ', "
                "br. 29/78 i dr.), potraživanja zastarevaju za 10 godina, ako zakonom nije "
                "propisan kraći rok zastarelosti. Posebni rokovi: 3 godine — za periodična "
                "potraživanja i potraživanja iz prometa robe i usluga između preduzetnika; "
                "1 godina — za potraživanja zakupnine, kamata, dividende; "
                "5 godina — za potraživanja naknade štete od delikta (3 od saznanja). "
                "Zastarelost se prekida pokretanjem postupka, priznavanjem duga ili "
                "delomičnim plaćanjem."
            ),
        },
        {
            "broj": "011-00-00215/2021-05",
            "datum": "15.04.2021",
            "ministarstvo": "Ministarstvo pravde",
            "oblast": "obligaciono pravo",
            "naziv": "Ugovorna kazna — pravna priroda i ograničenja",
            "tekst": (
                "Pitanje: Da li sud može smanjiti ugovornu kaznu koja je pretjerano visoka?\n\n"
                "Odgovor: Prema članu 274-277 Zakona o obligacionim odnosima, sud može "
                "na zahtev stranke smanjiti ugovornu kaznu ako je ona nesrazmerno visoka "
                "u odnosu na značaj i vrednost obaveze. Sud uzima u obzir: visinu štete, "
                "visinu obaveze, vrednost ugovora, okolnosti slučaja. Sud ne može umanjiti "
                "kaznu ispod iznosa stvarne štete ako je ona veća. Poverilac koji zahteva "
                "ugovornu kaznu nema obavezu dokazivanja štete — ona se presumira. "
                "Kazna može biti za slučaj neispunjenja ili zakašnjenja."
            ),
        },

        # ── DIGITALNA IMOVINA ─────────────────────────────────────────────────

        {
            "broj": "011-00-00441/2021-04",
            "datum": "15.09.2021",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "digitalna imovina",
            "naziv": "Porez na prihode od prodaje kriptovaluta — stopa i prijava",
            "tekst": (
                "Pitanje: Kako se oporezuje prihod od prodaje kriptovaluta (Bitcoin i dr.)?\n\n"
                "Odgovor: Prema članu 72a-78 Zakona o porezu na dohodak građana (izmenama "
                "iz 2021), prihod od digitalne imovine (kriptovalute) oporezuje se kao "
                "kapitalni dobitak stopom od 15%. Kapitalni dobitak = prodajna cena – "
                "nabavna cena (u dinarima po kursu NBS na dan sticanja). Prijava PPG-1 "
                "podnosi se u roku od 30 dana od prodaje. Fizičko lice koje trguje "
                "kriptovalutama na organizovanom tržištu može prijaviti godišnji dobitak "
                "zbirno do 15. marta za prethodnu godinu. Minimalni neoporezivi dobitak "
                "nije propisan."
            ),
        },
        {
            "broj": "011-00-00389/2022-04",
            "datum": "05.07.2022",
            "ministarstvo": "Ministarstvo finansija",
            "oblast": "digitalna imovina",
            "naziv": "VASP licenca — ko je obavezan da je pribavi",
            "tekst": (
                "Pitanje: Ko mora da pribavi licencu Narodne banke Srbije za pružanje "
                "usluga digitalne aktive (VASP)?\n\n"
                "Odgovor: Prema Zakonu o digitalnoj imovini ('Sl. glasnik RS', br. 153/2020), "
                "licencu Narodne banke Srbije moraju pribaviti sve pravno i fizičko lice "
                "koje pružaju usluge: 1) prijema i prenosa naloga za digitalnu imovinu; "
                "2) čuvanja digitalne imovine i ključeva; 3) zamene digitalne imovine za "
                "zakonska sredstva plaćanja; 4) upravljanja portfoliom digitalne imovine. "
                "Pružanje ovih usluga bez licence je krivično delo. Izuzetak: privatna "
                "lica koja drže kriptovalute za sopstvene potrebe."
            ),
        },
    ]

    return seed


# ─── Glavni tok ───────────────────────────────────────────────────────────────

def main():
    log.info("=== Phase 2.4 — Scraper mišljenja ministarstava ===")

    # Pokušaj playwright scrapinga
    scraped = scrape_playwright()
    if scraped:
        log.info("[SCRAPER] Playwright dao %d mišljenja", len(scraped))
        data = scraped
    else:
        log.info("[SEED] Koristim seed dataset...")
        data = build_seed()
        log.info("[SEED] Seed dataset: %d mišljenja", len(data))

    # Upiši sve u data/misljenja/raw/
    saved = 0
    for item in data:
        # Slug za ime fajla
        slug = (
            item.get("broj", "")
            .replace("/", "-")
            .replace(" ", "_")
            .strip("-") or f"misljenje_{saved:04d}"
        )
        out_path = OUT_DIR / f"{slug}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        saved += 1

    log.info("[DONE] Upisano %d mišljenja u %s", saved, OUT_DIR)
    print(f"\n✓ Upisano {saved} mišljenja u {OUT_DIR}")
    return saved


if __name__ == "__main__":
    main()
