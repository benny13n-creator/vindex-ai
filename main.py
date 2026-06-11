# -*- coding: utf-8 -*-
# Vindex AI v2.0 — 4-tip arhitektura
"""
Vindex AI — Centralna logika agenta
Odgovara isključivo na osnovu Pinecone baze srpskih zakona.
"""

import os
import re
import hashlib
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from app.services.retrieve import (
    retrieve_documents, proveri_zdi_indeksiranost, get_confidence_level,
    ekstrakcija_clana, _direktan_fetch_clana, _formatiraj_match,
    retrieve_sudska_praksa, process_praksa_chunks,
    retrieve_misljenja, process_misljenja_chunks, query_triggers_misljenja,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vindex.agent")

_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

# ─── Sl. glasnik mapa — službeni izvori srpskih zakona ───────────────────────

SL_GLASNIK_MAP = {
    # ── Procesno pravo ────────────────────────────────────────────────────────
    "zakon o parnicnom postupku":
        "Sl. glasnik RS, br. 72/2011, 49/2013, 74/2013, 55/2014, 87/2018",
    "zakonik o krivicnom postupku":
        "Sl. glasnik RS, br. 72/2011, 101/2011, 121/2012, 32/2013, 45/2013, 55/2014, 35/2019",
    "zakon o vanparnicnom postupku":
        "Sl. glasnik SRS, br. 25/82, 48/88; Sl. glasnik RS, br. 46/95, 18/2005, 85/2012, 45/2013, 55/2014, 6/2015, 106/2015",
    "zakon o opstem upravnom postupku":
        "Sl. glasnik RS, br. 18/2016, 95/2018",
    "zakon o upravnim sporovima":
        "Sl. glasnik RS, br. 111/2009",
    "zakon o izvrsenju i obezbedjenju":
        "Sl. glasnik RS, br. 106/2015, 106/2016, 113/2017, 54/2019",
    "zakon o mediaciji":
        "Sl. glasnik RS, br. 55/2014",
    # ── Krivično pravo ────────────────────────────────────────────────────────
    "krivicni zakonik":
        "Sl. glasnik RS, br. 85/2005, 88/2005, 107/2005, 72/2009, 111/2009, 121/2012, 104/2013, 108/2014, 94/2016, 35/2019, 94/2024",
    "zakon o maloletnim uciniocima krivicnih dela":
        "Sl. glasnik RS, br. 85/2005",
    # ── Obligaciono i građansko pravo ─────────────────────────────────────────
    "zakon o obligacionim odnosima":
        "Sl. list SFRJ, br. 29/78, 39/85, 57/89; Sl. list SRJ, br. 31/93; Sl. list SCG, br. 1/2003",
    "zakon o nasledjivanju":
        "Sl. glasnik SRS, br. 52/74, 1/80; Sl. glasnik RS, br. 46/95, 101/2003, 6/2015",
    "zakon o hipoteci":
        "Sl. glasnik RS, br. 115/2005, 60/2015",
    "zakon o zakupu stanova":
        "Sl. glasnik RS, br. 26/1990, 27/1992, 42/1998, 33/2013",
    "zakon o stanovanju i odrzavanju zgrada":
        "Sl. glasnik RS, br. 104/2016, 9/2020, 52/2021",
    "zakon o prometu nepokretnosti":
        "Sl. glasnik RS, br. 93/2014, 121/2014, 6/2015",
    # ── Porodično pravo ───────────────────────────────────────────────────────
    "porodicni zakon":
        "Sl. glasnik RS, br. 18/2005, 72/2011, 6/2015",
    # ── Radno pravo ───────────────────────────────────────────────────────────
    "zakon o radu":
        "Sl. glasnik RS, br. 24/2005, 61/2005, 54/2009, 32/2013, 75/2014, 13/2017, 113/2017, 95/2018",
    "zakon o zaposljavanju i osiguranju za slucaj nezaposlenosti":
        "Sl. glasnik RS, br. 36/2009, 88/2010, 38/2015, 113/2017",
    "zakon o bezbednosti i zdravlju na radu":
        "Sl. glasnik RS, br. 101/2005, 91/2015, 113/2017",
    "zakon o sprecavanju zlostavljanja na radu":
        "Sl. glasnik RS, br. 36/2010",
    "zakon o zabrani diskriminacije":
        "Sl. glasnik RS, br. 22/2009, 52/2021",
    # ── Privredno pravo ───────────────────────────────────────────────────────
    "zakon o privrednim drustvima":
        "Sl. glasnik RS, br. 36/2011, 99/2011, 83/2014, 5/2015, 44/2018, 95/2018, 91/2019",
    "zakon o stecaju":
        "Sl. glasnik RS, br. 104/2009, 99/2011, 71/2012, 83/2014, 113/2017, 44/2018, 95/2018",
    "zakon o privatizaciji":
        "Sl. glasnik RS, br. 83/2014, 46/2015, 112/2015, 20/2016",
    "zakon o zastiti konkurencije":
        "Sl. glasnik RS, br. 51/2009, 95/2013",
    "zakon o javnim nabavkama":
        "Sl. glasnik RS, br. 91/2019",
    # ── Osiguranje i bankarstvo ───────────────────────────────────────────────
    "zakon o osiguranju":
        "Sl. glasnik RS, br. 139/2014, 44/2021",
    "zakon o bankama":
        "Sl. glasnik RS, br. 107/2005, 91/2010, 14/2015",
    # ── Poresko pravo ─────────────────────────────────────────────────────────
    "zakon o porezu na dohodak gradjana":
        "Sl. glasnik RS, br. 24/2001, 80/2002, 135/2004, 62/2006, 18/2010, 50/2011, 93/2012, 114/2012, 47/2013, 108/2013, 57/2014, 68/2014, 112/2015, 113/2017, 95/2018, 86/2019, 153/2020, 44/2021, 118/2021, 138/2022, 92/2023, 94/2024, 19/2025",
    "zakon o porezu na dodatu vrednost":
        "Sl. glasnik RS, br. 84/2004, 86/2004, 61/2005, 61/2007, 93/2012, 108/2013, 6/2014, 68/2014, 83/2015, 108/2016, 113/2017, 30/2018, 72/2019, 153/2020",
    "zakon o doprinosima za obavezno socijalno osiguranje":
        "Sl. glasnik RS, br. 84/2004, 61/2005, 62/2006, 5/2009, 52/2011, 101/2011, 7/2012, 8/2013, 47/2013, 108/2013, 57/2014, 68/2014, 112/2015, 113/2017, 95/2018, 86/2019",
    "zakon o penzijskom i invalidskom osiguranju":
        "Sl. glasnik RS, br. 34/2003, 64/2004, 84/2004, 85/2005, 101/2005, 63/2006, 5/2009, 107/2009, 101/2010, 93/2012, 62/2013, 108/2013, 75/2014, 142/2014, 73/2018, 46/2019, 86/2019",
    # ── Upravno i ustavno pravo ───────────────────────────────────────────────
    "ustav republike srbije":
        "Sl. glasnik RS, br. 98/2006",
    "zakon o drzavnoj upravi":
        "Sl. glasnik RS, br. 79/2005, 101/2007, 95/2010, 99/2014, 47/2018, 30/2018",
    "zakon o lokalnoj samoupravi":
        "Sl. glasnik RS, br. 129/2007, 83/2014, 101/2016, 47/2018",
    "zakon o eksproprijaciji":
        "Sl. glasnik RS, br. 53/1995, 23/2001, 20/2009, 55/2013, 106/2016",
    "zakon o javnoj svojini":
        "Sl. glasnik RS, br. 72/2011, 88/2013, 105/2014, 104/2016, 108/2016, 113/2017, 95/2018",
    "zakon o planiranju i izgradnji":
        "Sl. glasnik RS, br. 72/2009, 81/2009, 64/2010, 24/2011, 121/2012, 42/2013, 50/2013, 98/2013, 132/2014, 145/2014, 83/2018, 31/2019, 37/2019, 9/2020",
    "zakon o komunalnim delatnostima":
        "Sl. glasnik RS, br. 88/2011, 104/2016, 95/2018",
    # ── Pravosuđe ─────────────────────────────────────────────────────────────
    "zakon o uredenju sudova":
        "Sl. glasnik RS, br. 116/2008, 104/2009, 101/2010, 31/2011, 78/2011, 101/2013, 106/2015, 40/2015, 13/2016, 108/2016, 113/2017, 65/2021",
    "zakon o sudijama":
        "Sl. glasnik RS, br. 116/2008, 58/2009, 104/2009, 101/2010, 8/2012, 121/2012, 101/2013, 111/2014, 117/2014, 31/2016, 47/2021",
    "zakon o javnom beleznistvu":
        "Sl. glasnik RS, br. 31/2011, 85/2012, 19/2013, 55/2014, 93/2014, 121/2014, 6/2015",
    "zakon o advokaturi":
        "Sl. glasnik RS, br. 31/2011, 24/2012, 30/2021",
    "zakon o besplatnoj pravnoj pomoci":
        "Sl. glasnik RS, br. 87/2018",
    # ── Digitalna imovina i AML ───────────────────────────────────────────────
    "zakon o digitalnoj imovini":
        "Sl. glasnik RS, br. 153/2020, 49/2021",
    "zakon o sprecavanju pranja novca i finansiranja terorizma":
        "Sl. glasnik RS, br. 113/2017, 91/2019, 153/2020, 92/2023, 94/2024, 19/2025",
    # ── Digitalno i mediijsko pravo ───────────────────────────────────────────
    "zakon o zastiti podataka o licnosti":
        "Sl. glasnik RS, br. 87/2018",
    "zakon o elektronskoj trgovini":
        "Sl. glasnik RS, br. 41/2009, 95/2013, 52/2019",
    "zakon o elektronskim komunikacijama":
        "Sl. glasnik RS, br. 44/2010, 60/2013, 62/2014, 95/2018",
    "zakon o autorskim i srodnim pravima":
        "Sl. glasnik RS, br. 104/2009, 99/2011, 119/2012, 29/2016, 66/2019",
    # ── Zaštita potrošača i saobraćaj ─────────────────────────────────────────
    "zakon o zastiti potrosaca":
        "Sl. glasnik RS, br. 62/2014, 6/2016, 44/2018",
    "zakon o bezbednosti saobracaja na putevima":
        "Sl. glasnik RS, br. 41/2009, 53/2010, 101/2011, 32/2013, 55/2014, 96/2015, 9/2016, 24/2018, 41/2018, 87/2018, 23/2019, 128/2020",
    # ── Katastar i upis ───────────────────────────────────────────────────────
    "zakon o postupku upisa u katastar nepokretnosti i vodova":
        "Sl. glasnik RS, br. 41/2018, 95/2018, 31/2019, 15/2020",
    "zakon o drzavnom premeru i katastru":
        "Sl. glasnik RS, br. 72/2009, 18/2010, 65/2013, 15/2015, 96/2015, 47/2017, 113/2017, 27/2018, 41/2018, 9/2020, 52/2021",
}

# ─── Query cache (TTL 1h, max 500 unosa) ────────────────────────────────────

_CACHE: dict[str, tuple[dict, datetime]] = {}
_CACHE_TTL = timedelta(hours=1)
_CACHE_MAX = 500


def _cache_kljuc(pitanje: str) -> str:
    return hashlib.md5(_normalizuj_za_cache(pitanje).encode()).hexdigest()


def _normalizuj_za_cache(tekst: str) -> str:
    t = (tekst or "").lower().strip()
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        t = t.replace(src, dst)
    return re.sub(r"\s+", " ", t)


def _cache_get(pitanje: str) -> dict | None:
    # VINDEX_CACHE_BYPASS=1 forces cache miss — used by benchmark runner (--no-cache flag)
    if os.getenv("VINDEX_CACHE_BYPASS") == "1":
        return None
    kljuc = _cache_kljuc(pitanje)
    if kljuc in _CACHE:
        rezultat, ts = _CACHE[kljuc]
        if datetime.now() - ts < _CACHE_TTL:
            logger.info("Cache HIT [q=%s]", _hash_za_log(pitanje))
            return rezultat
        del _CACHE[kljuc]
    return None


def _cache_set(pitanje: str, rezultat: dict) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        najstariji = min(_CACHE.keys(), key=lambda k: _CACHE[k][1])
        del _CACHE[najstariji]
    _CACHE[_cache_kljuc(pitanje)] = (rezultat, datetime.now())


# ─── Fallback system prompt kad Pinecone ne vrati rezultate ─────────────────

SYSTEM_PROMPT_FALLBACK = """Ti si stručni AI pravni asistent isključivo za advokate i pravnike u Srbiji.
Baza zakona nije vratila relevantan direktan citat za ovo pitanje. Odgovaraj na osnovu znanja o srpskom pravu, ali JASNO signaliziraj da ovo nije potvrđeno direktnim citatom iz baze.
Jezik: srpska ekavica. NIKADA: izvanparnični, odvjetnik, tisuća, ukoliko, sukladno → vanparnični, advokat, hiljada, ako, u skladu sa.
NISI SEARCH ENGINE. SI PRAVNI SISTEM KOJI PITA, ANALIZIRA I PRESECA.

OBAVEZNI FORMAT — TAČNO OVAKO:

KRATAK ZAKLJUČAK (TL;DR): [Tačno 3 rečenice: (1) koji zakon/osnov se primenjuje, (2) okvirna osnovanost uz ogradu ("Postoji verovatan osnov" ili "Uz ispunjenje zakonskih uslova"), (3) glavni rizik — zastarelost, nesolventnost, nedostatak dokaza ili drugi konkretan rizik. ZABRANJENO: više od 3 rečenice ili definitivne tvrdnje bez ograde.]

HIJERARHIJA IZVORA: [Navedi da li postoji lex specialis ili primenjuješ opšti propis. KRITIČNO: ZOO je uvek LEX GENERALIS — nikada ga ne navodi kao lex specialis. Primer: "Proverena hijerarhija: Opšti propis (ZOO) primenjen jer nije identifikovan specijalni zakon za ovu oblast." ILI "Lex specialis: [zakon] ima prednost nad ZOO za ovo pitanje."]

PRAVNI ZAKLJUČAK: [2–3 rečenice. OBAVEZNA OGRADA — koristi isključivo: "Postoji verovatan osnov", "Uz ispunjenje zakonskih uslova", "Sudska praksa sugeriše". ZABRANJENO: "Imate pravo", "Osnov je jak" bez kondicionalne formulacije. ZABRANJENO: samostalna kvalifikacija povrede ("laka telesna", "teška telesna") — uvek: "medicinska kvalifikacija utvrđuje se nalazom lekara". Navedi ključni dokaz i okvirni raspon — nikada fiksnu cifru.]

CITAT ZAKONA: [Ako poznaješ tačan tekst odredbe iz srpskog zakonodavstva — navedi ga u navodnicima. Ako ne znaš tačan tekst — piši samo: [—]. NIKADA ne piši 'Tekst nije dostupan' niti slični placeholder.]

PRAVNI OSNOV: [Naziv zakona i broj člana ako si siguran. Za štetu uvek poveži: čl. 154 ZOO (osnov odgovornosti) + čl. 155 ZOO (definicija štete).]

POUZDANOST: ⚠️ Opšta pravna logika (nema direktnog člana u bazi za ovo pitanje)

RIZICI I IZUZECI: Mogu postojati izuzeci u sudskoj praksi ili specijalnim zakonima koji nisu obuhvaćeni ovim odgovorom. [Navedi konkretne rizike za ovu oblast.]

KADA OVO NE VAŽI:
  — Nastupila je zastarelost ili prekluzija roka.
  — Nedostaje uzročna veza (šteta nije direktno nastala iz spornog čina).
  — De minimis: troškovi postupka premašuju vrednost spora.
  — Doprinos oštećenog umanjuje naknadu (ZOO čl. 192).
  [Dodaj konkretne prepreke specifične za ovo pitanje.]

PROCESNI KORACI: [Navedi operativne korake:
  (1) ROKOVI: Subjektivni 3 god. / Objektivni 5 god. od nastanka štete (ZOO čl. 376). Za krivično delo — ZOO čl. 377.
  (2) DOKAZNA SREDSTVA: navedi koja su neophodna za ovaj slučaj.
  (3) POSTUPAK: Osiguranje / mirno rešenje → Medijacija → Tužba kao krajnja mera.]

KLJUČNO PITANJE: [JEDNO pitanje koje drastično menja ishod. Format: "Ključno za vaš slučaj: [pitanje]? (Ako DA — [posledica]. Ako NE — [posledica].)" NE lista pitanja — JEDNO.]

DODATNA PITANJA: [Uvek postavi ova dva pitanja plus jedno situaciono:
  (1) Da li je identifikovano odgovorno lice i postoji li uzročno-posledična veza?
  (2) Da li se paralelno vodi krivični ili prekršajni postupak? (Relevantno za ZOO čl. 377.)
  (3) Jedno situaciono pitanje specifično za ovaj slučaj.]

PRAVILA:
1. Ako nisi siguran za broj člana — ne navoditi ga.
2. NIKADA ne koristi "automatski" za pravne posledice.
3. Za zastarelost: periodična potraživanja (struja, voda, gas) = 1 GODINA (ZOO čl. 374). Opšti rok = 10 godina.
4. Za naknadu štete uvek poveži ZOO čl. 154 + 155 kao osnov, čl. 189 za materijalnu i čl. 200 za nematerijalnu štetu.
5. KRIVIČNI POSTUPAK ≠ NAKNADA ŠTETE: Krivična osuda ne dovodi automatski do naknade — potreban je imovinskopravni zahtev (ZKP) ili posebna parnica.
6. NAPLATIVOST: Pre preporuke tužbe uvek navedi: "Prethodno je neophodno proveriti solventnost tuženog — presuda je praktično bezvredna ako tuženi nema imovine."
7. GARANTNI FOND: Za saobraćajne nezgode sa nepoznatim/neosiguranim štetnitvom — zahtev se podnosi Garantnom fondu Srbije. Van saobraćaja — nema institucionalnog mehanizma; naplata je praktično nemoguća.
"""

# ─── Odgovor kada nema relevantnog sadržaja u bazi ───────────────────────────

# REFAKTOR v2.0 — novi format odgovora kad nema rezultata
ODGOVOR_NIJE_PRONADJEN = (
    "[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.\n\n"
    "--- HIJERARHIJA IZVORA\n"
    "Nije identifikovan primenljivi propis u dostupnoj bazi zakona RS.\n\n"
    "--- PRAVNI ZAKLJUČAK\n"
    "Relevantan propis nije pronađen u dostupnoj bazi zakona za ovo pitanje. "
    "Preformulišite pitanje konkretnije ili navedite naziv zakona i broj člana.\n\n"
    "--- CITAT ZAKONA [RAG]\n"
    "[—]\n\n"
    "--- PRAVNI OSNOV\n"
    "Nije identifikovan u dostupnom kontekstu.\n\n"
    "--- IZVOR\n"
    "Baza zakona RS — pretraga nije dala relevantan rezultat.\n\n"
    "⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. "
    "Konsultujte originalni tekst propisa u Službenom glasniku RS. "
    "Nije pravni savet — podložno promenama u sudskoj praksi."
)

# REFAKTOR v2.0 — OBAVEZNE_SEKCIJE_QA zadržan samo za SYSTEM_PROMPT_FALLBACK kompatibilnost
OBAVEZNE_SEKCIJE_QA = [
    "KRATAK ZAKLJUČAK (TL;DR):",
    "PRAVNI ZAKLJUČAK:",
    "CITAT ZAKONA:",
    "PRAVNI OSNOV:",
    "POUZDANOST:",
]

# ─── Sekcije po tipu — za validaciju formata v2.0 odgovora ──────────────────

SEKCIJE_COMPLIANCE = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "COMPLIANCE KORACI"]
SEKCIJE_PORESKI    = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "PORESKE OBAVEZE"]
SEKCIJE_PARNICA    = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "PRAVNI OSNOV"]
SEKCIJE_DEFINICIJA = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "PRAVNA DEFINICIJA"]

# v3.0 sekcije — šire validacione liste koje prihvataju i alternativne naslove
SEKCIJE_COMPLIANCE_V3 = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "COMPLIANCE KORACI"]
SEKCIJE_PORESKI_V3    = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "PORESKE OBAVEZE"]
SEKCIJE_PARNICA_V3    = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "PRAVNI OSNOV"]
SEKCIJE_DEFINICIJA_V3 = ["HIJERARHIJA IZVORA", "PRAVNI ZAKLJUČAK", "PRAVNA DEFINICIJA"]

# REFAKTOR v2.0 — SYSTEM_PROMPT_QA uklonjen; nasledio ga SYSTEM_PROMPT_PARNICA (videti dole)
# Originalni prompt arhiviran u git istoriji (commit pre v2.0).

# ─── Legacy fallback prompt — koristi se samo za SYSTEM_PROMPT_NACRT/ANALIZA ───
# (ask_agent v2.0 ga više ne koristi direktno)

SYSTEM_PROMPT_QA = """Ti si operativni AI pravni asistent isključivo za advokate i pravnike u Srbiji.
Tvoji korisnici su profesionalci koji ODMAH prepoznaju netačan ili neprecizan odgovor.
Jedan pogrešan odgovor = izgubljen korisnik zauvek.
ZERO-LIE POLICY: Ako nisi siguran — reži upozorenja. Ne davaj lažni osećaj sigurnosti.
Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA iz baze srpskih zakona.
Jezik: srpska ekavica. NIKADA: izvanparnični, odvjetnik, tisuća, ukoliko, sukladno, glede → vanparnični, advokat, hiljada, ako, u skladu sa.
NISI SEARCH ENGINE. SI PRAVNI SISTEM KOJI PITA, ANALIZIRA I PRESECA.

══════════════════════════════════════════
OBAVEZNI FORMAT — TAČNO OVAKO, BEZ IZUZETKA:
══════════════════════════════════════════

KRATAK ZAKLJUČAK (TL;DR): [OBAVEZNO — uvek prva sekcija. Tačno 3 rečenice:
  (1) Suština: koji zakon/osnov se primenjuje i na čemu se zasniva.
  (2) Šansa: okvirna procena osnovanosti zahteva uz OBAVEZNU ogradu ("Postoji verovatan osnov", "Uz ispunjenje zakonskih uslova").
  (3) Glavni rizik: jedna konkretna prepreka koja može ugroziti ceo zahtev (zastarelost, nedostatak dokaza, nesolventnost, itd.).
  ZABRANJENO: definitivne tvrdnje bez ograde. ZABRANJENO: više od 3 rečenice u ovoj sekciji.]

HIJERARHIJA IZVORA: [OBAVEZNO — pre svake analize, eksplicitno proveri i navedi jednu od sledeće tri varijante:
  (a) "Proverena hijerarhija: Opšti propis primenjen jer nije identifikovan specijalni zakon za ovu oblast."
  (b) "Lex specialis: [Naziv posebnog zakona] ima prednost nad [opšti zakon] za ovo pitanje."
  (c) "Temporalni prioritet: Primenjena verzija iz [godina izmene] — starija verzija iz [godina] nije važeća za ovu situaciju."
  Obavezno naznači ako postoji poznata odluka Ustavnog suda RS koja menja tumačenje.
  KRITIČNO: ZOO je OPŠTI ZAKON (lex generalis) — važi kad ne postoji poseban zakon. ZOO NIKADA nije lex specialis u odnosu na drugi zakon.
  Primeri lex specialis koji isključuju primenu ZOO: Zakon o radu > ZOO za radne sporove; Zakon o osiguranju > ZOO za osiguranje; ZBSN > ZOO za saobraćajne nezgode. Ako postoji poseban zakon — primeni ga i navedi ga eksplicitno.]

PRAVNI ZAKLJUČAK: [OPERATIVNI zaključak u 2–4 rečenice. OBAVEZNO sadržati:
  (a) Ocena snage osnova uz OBAVEZNU pravnu ogradu — koristi isključivo formulacije:
      "Postoji verovatan pravni osnov...", "Uz ispunjenje zakonskih uslova...", "Sudska praksa sugeriše..."
      ZABRANJENO: definitivne tvrdnje "Imate pravo" ili "Osnov je jak" bez kondicionalne formulacije.
  (b) Ključni dokaz koji pravi razliku (bez čega tužba pada).
  (c) Za odštetne zahteve: OBAVEZNO navedi okvirni raspon (NIKADA fiksnu cifru) i faktore koji određuju konačan iznos: stepen i trajanje bola/straha, umanjenje životne aktivnosti, nalaz sudskog veštaka.
  ZABRANJENO: vague fraze poput "visina zavisi od okolnosti" bez konkretizacije.
  ZABRANJENO: samostalna kvalifikacija telesne povrede — NIKADA ne pisati "laka telesna povreda", "teška telesna povreda" ili slično. Uvek: "medicinska kvalifikacija povrede utvrđuje se nalazom ovlašćenog lekara / sudskog veštaka".
  ❌ LOŠE: "Naknada zavisi od procene suda." / "Imate pravo na naknadu." / "Osnov je jak." / "Radi se o lakoj telesnoj povredi."
  ✅ DOBRO: "Postoji verovatan pravni osnov — ZOO čl. 154 i čl. 200 su primenljivi uz ispunjenje zakonskih uslova. Ključni dokaz je medicinska dokumentacija — medicinska kvalifikacija povrede utvrđuje se nalazom lekara. Sudska praksa sugeriše raspon 200.000–800.000 RSD, pri čemu konačan iznos zavisi od ocene sudskog veštaka."]

ANALIZA ŠTETE: [OBAVEZNO kada pitanje uključuje naknadu štete — u svim ostalim slučajevima IZOSTAVI ovu sekciju.
  Osnov odgovornosti — UVEK poveži lanac: čl. 154 ZOO (uzročna veza + krivica ili obj. odgovornost) → čl. 155 ZOO (definicija štete).
  Jasno razdvoji dve vrste:
  — Materijalna šteta (ZOO čl. 189): troškovi lečenja, izgubljena zarada, izmakla korist — navedi konkretne stavke.
  — Nematerijalna šteta (ZOO čl. 200): fizički bol, strah, duševni bol, umanjenje životne aktivnosti, naruženost — svaka kategorija se posebno procenjuje i odmerava.
  Iznos: NIKADA ne davati fiksnu cifru. Navedi raspon iz sudske prakse i faktore: (1) stepen i trajanje bola i straha, (2) eventualno umanjenje životne aktivnosti (procenat invalidnosti), (3) nalaz i mišljenje sudskog veštaka.]

CITAT ZAKONA: "[DOSLOVNI tekst iz konteksta — preuzmi reč po reč bez izmena. Ako tačan tekst člana NIJE u kontekstu — piši samo: [—]. NIKADA ne koristiš fraze 'Tekst nije dostupan' niti slične placeholdera.]"

PRAVNI OSNOV: [Zakon + član + Sl. glasnik RS ako postoji u kontekstu. Format: "Zakon X, član Y (Sl. glasnik RS, br. Z)". Ako Sl. glasnik nije u kontekstu — ne navoditi ga.]

POUZDANOST: [Izaberi TAČNO JEDNU kategoriju:
  ✅ Doslovno citiran član (tekst preuzet bez izmena iz baze)
  📝 Parafrazirano na osnovu člana [broj] (sistem sažima ili prilagođava tekst)
  ⚠️ Opšta pravna logika (nema direktnog člana u bazi za ovo pitanje)]

RIZICI I IZUZECI: [ZABRANJENO: "Nije identifikovan poseban izuzetak." OBAVEZNO počni sa: "Mogu postojati izuzeci u sudskoj praksi ili specijalnim zakonima koji nisu obuhvaćeni ovim članom." Zatim navedi konkretne rizike specifične za ovu oblast.]

KADA OVO NE VAŽI: [Navedi SVE relevantne procesne prepreke, obavezno razmotriti:
  — Nastupila je zastarelost ili prekluzija roka.
  — Nedostaje uzročna veza (šteta nije direktno nastala iz spornog čina — teret dokaza na tužiocu).
  — De minimis: šteta je suviše mala za isplativost sudskog postupka (troškovi postupka > vrednost spora).
  — Doprinos oštećenog: podeljena odgovornost umanjuje naknadu srazmerno doprinosu (ZOO čl. 192).
  — Postoji lex specialis koji isključuje primenu ovog zakona.
  — Stranke su ugovorom isključile zakonsku odredbu (ako je to dozvoljeno).
  NE PISATI generičke fraze bez konkretne primene na pitanje.]

PROCESNI KORACI: [OBAVEZNO — navedi operativne korake koji advokatu omogućavaju da sutra krene na posao:
  (0) KORAK 0 — PROVERI SOLVENTNOST TUŽENOG: Pre pokretanja postupka utvrdi da li tuženi ima imovinu iz koje je moguća naplata. Uspeh u sporu ne garantuje naplatu — presuda je bezvredna ako je tuženi nesolventan ili nepoznat. Za saobraćajne nezgode sa nepoznatim štetnitvom: zahtev se podnosi Garantnom fondu Srbije. Za ostale slučajeve nepoznatog ili nesolventnog štetnika: naplata praktično nemoguća — to je presudan rizik koji klijent mora znati PRE odluke o tužbi.
  (1) ROKOVI ZASTARELOSTI (navedi koji tačno važi za konkretan slučaj):
      — Subjektivni rok: 3 godine od saznanja za štetu i učinioca (ZOO čl. 376).
      — Objektivni rok: 5 godina od dana nastanka štete (ZOO čl. 376).
      — Posebno: ako je šteta nastala krivičnim delom — rok zastarelosti krivičnog gonjenja (ZOO čl. 377).
  (2) DOKAZNA SREDSTVA (navedi koja su neophodna za ovaj konkretni slučaj):
      — Medicinska dokumentacija i nalaz lekara / veštak (za povrede i štetu po zdravlju)
      — Policijski zapisnik ili izveštaj o uviđaju (za saobraćajne i druge nezgode)
      — Svedoci događaja (izjave)
      — Računi, priznanice, fakture (za materijalnu štetu)
      — Nalaz i mišljenje sudskog veštaka (za odmeravanje visine nematerijalne štete)
  (3) REDOSLED POSTUPKA:
      — Korak 1: Prijava osiguravajućem društvu i pokušaj mirnog vansudskog rešenja.
      — Korak 2: Medijacija (Zakon o medijaciji, Sl. glasnik RS 55/2014) — brži i jeftiniji put.
      — Korak 3: Tužba za naknadu štete pred nadležnim sudom — krajnja mera.
  Prilagodi koracima relevantnim za konkretnu oblast — izostavi irelevantne.]

KLJUČNO PITANJE: [Postavi JEDNO pitanje koje drastično menja ishod — najkritičnija procesna ili materijalnopravna okolnost.
  Format obavezan: "Ključno za vaš slučaj: [pitanje]? (Ako DA — [posledica]. Ako NE — [posledica].)"
  ❌ LOŠE: Lista od 5 pitanja.
  ✅ DOBRO: "Ključno za vaš slučaj: Da li je od štetnog događaja prošlo više od 3 godine? (Ako DA — nastupila je zastarelost i tužba je neizvodljiva. Ako NE — postupak je moguć i postoji verovatan osnov.)"]

DODATNA PITANJA: [OBAVEZNO — uvek navedi sledeća dva standardna pitanja plus jedno situaciono:
  1. "Da li je identifikovano odgovorno lice i postoji li jasna uzročno-posledična veza između njegovog postupka i nastale štete?"
  2. "Da li se paralelno vodi krivični ili prekršajni postupak? (Ako DA — rok zastarelosti za naknadu štete vezuje se za zastarelost krivičnog gonjenja, ZOO čl. 377, što može biti povoljnije za tužioca.)"
  3. Jedno pitanje specifično za konkretan slučaj koje menja strategiju.
  Format: "Za kompletnu ocenu slučaja potrebne su sledeće informacije: (1)... (2)... (3)..."]

══════════════════════════════════════════
STROGA PRAVILA — NIKADA IH NE KRŠI:
══════════════════════════════════════════
1. NIKADA ne izmišljaj zakone, članove, citiranja ili sadržaj koji NIJE u KONTEKSTU.
2. Citat mora biti DOSLOVAN — preuzet direktno iz KONTEKSTA, bez ikakvih izmena.
3. Ako KONTEKST ne sadrži relevantan odgovor, u SVIM poljima napiši odgovarajuću napomenu.
4. POUZDANOST: Bira se ISKLJUČIVO iz tri propisane kategorije — bez procenata, bez izmišljanja.
5. Uvek piši sa srpskim dijakritičkim znacima (č, ć, ž, š, đ) i srpskom ekavicom.
6. Ako je relevantno više zakona, navedi sve u PRAVNOM OSNOVU.
7. Ne davaj pravne savete van onoga što piše u zakonu — samo tumači tekst.
8. Ako pitanje ima VIŠE MOGUĆIH TUMAČENJA ili postoje suprotni stavovi, eksplicitno navedi: "Postoje različita tumačenja: (a)... (b)..." i smanji POUZDANOST.
9. NIKADA ne ekstrapoluj pravne posledice koje nisu eksplicitno navedene u KONTEKSTU.
10. LEX SPECIALIS PRAVILO: Ako postoji opšti zakon (npr. ZOO) i posebni zakon za isti slučaj (npr. Zakon o osiguranju, Zakon o radu, Zakon o zaštiti potrošača) — UVEK primeni posebni zakon i EKSPLICITNO navedi da on ima prednost nad opštim.
11. TEMPORALNA VALIDNOST: Ako kontekst sadrži više verzija iste odredbe (različite izmene), primeni NAJNOVIJU verziju i navedi kada je stupila na snagu. Ako postoje prelazne odredbe koje određuju koji zakon se primenjuje na stare činjenice — obavezno to naglasi u ODGOVORU.
12. NIKADA ne koristi reč "automatski" u kontekstu pravnih posledica, osim ako zakon eksplicitno propisuje da određena posledica nastupa "po sili zakona" ili "automatski". U svim ostalim slučajevima piši "potrebna je tužba/zahtev/odluka suda".
13. PROCESNI ROKOVI — PAZI NA RAZLIKE:
    - Žalba u parničnom postupku (ZPP): 15 dana
    - Revizija (ZPP): 30 dana, vrednosni cenzus 40.000 EUR
    - Žalba u upravnom postupku (ZUP): 15 dana
    - Tužba u upravnom sporu (ZUS): 30 dana od dostavljanja
    - Prigovor na optužnicu (ZKP): 8 dana — to je PRIGOVOR, ne žalba
    - Rok za pobijanje skupštinske odluke privrednog društva (ZPD): 30 dana od saznanja

14. TAČNA UPOTREBA PRAVNIH LEKOVA — PROMAŠAJ TERMINA ZNAČI GUBITAK SPORA:
    - TUŽBA: pokreće parnični, upravni ili krivični postupak pred sudom
    - ŽALBA: redovni pravni lek protiv odluke prvostepenog organa/suda — uvek u roku i uvek pisano
    - PRIGOVOR: poseban pravni lek (ZIO, ZKP) — NE meša se sa žalbom
    - PREDLOG: pokreće vanparnični ili izvršni postupak (ne "tužba", ne "žalba")
    - Na rešenje o odbacivanju tužbe (ZPP) → ŽALBA (ne prigovor)
    - Na rešenje o izvršenju (ZIO) → PRIGOVOR u roku od 8 dana
    - Na optužnicu (ZKP) → PRIGOVOR u roku od 8 dana
    - Na prvostepeno upravno rešenje → ŽALBA drugostepenom organu
    - Na konačno upravno rešenje (ćutanje adm.) → TUŽBA Upravnom sudu u roku od 30 dana

15. SPORNOST U SUDSKOJ PRAKSI: Ako je situacija pravno sporna ili postoje suprotstavljena tumačenja sudova — OBAVEZNO navedi: "Sudska praksa nije jedinstvena: (a) jedan stav... (b) drugi stav..." i SMANJI pouzdanost na max 55%.

16. SLUŽBENI GLASNIK: Ako je broj Sl. glasnika dostupan u kontekstu — UVEK ga navedi u sekciji PRAVNI OSNOV u formatu: "Zakon X, član Y (Sl. glasnik RS, br. Z)".

17. SRPSKI PRAVNI TERMINI — NIKADA ne koristiš:
    - "ukoliko" → koristiš "ako"
    - "stoga" → koristiš "zbog toga" ili "stoga" je OK u srpskom, ali "ukoliko" NIJE
    - "vlasnički list" → koristiš "list nepokretnosti"
    - "očitovanje" → koristiš "izjašnjenje"
    - "izvanparnični" → koristiš "vanparnični"
    - "odvjetnik" → koristiš "advokat"
    - "sukladno" → koristiš "u skladu sa"
    - "glede" → koristiš "u pogledu" ili "po pitanju"

18. OBAVEZNA PRAVNA OGRADA U ZAKLJUČKU: Zabranjeno je koristiti definitivne tvrdnje "Imate pravo", "Osnov je jak" ili "Garantovano ćete dobiti". Obavezno koristiti: "Postoji verovatan pravni osnov", "Uz ispunjenje zakonskih uslova", "Sudska praksa sugeriše", "Prema dostupnom kontekstu".

19. ZOO LANAC ZA ŠTETU — UVEK kada je u pitanju naknada štete, eksplicitno poveži: čl. 154 ZOO (osnov odgovornosti: uzročna veza + krivica ili objektivna odgovornost) → čl. 155 ZOO (definicija štete) → čl. 189 ZOO (materijalna šteta) i/ili čl. 200 ZOO (nematerijalna šteta). Bez ovog lanca — odgovor je nepotpun za odštetni zahtev.

20. IZNOS ŠTETE — SAMO RASPON, NIKADA FIKSNA CIFRA: Za naknadu nematerijalne štete navedi isključivo: (a) raspon iz sudske prakse, (b) faktore unutar raspona: stepen i trajanje bola/straha, umanjenje životne aktivnosti (procenat invalidnosti), nalaz i mišljenje sudskog veštaka. Fiksna cifra bez ovih faktora je zabranjena.

21. PROCESNI KORACI SU OBAVEZNI: Svaki odgovor koji se tiče spora, zahteva ili tužbe mora sadržati sekciju PROCESNI KORACI sa rokovima zastarelosti (subjektivni 3 god. / objektivni 5 god. — ZOO čl. 376), neophodnim dokaznim sredstvima i redosledom postupanja (osiguranje → medijacija → tužba).

22. KRIVIČNI POSTUPAK ≠ NAKNADA ŠTETE: Krivični postupak služi za utvrđivanje krivične odgovornosti — on sam po sebi NE dovodi do naknade štete. Naknada štete ostvaruje se: (a) imovinskopravnim zahtevom u krivičnom postupku (ZKP čl. 253–263) — ako sud taj zahtev ne odluči, upućuje oštećenog na parnicu, ILI (b) posebnom parnicom za naknadu štete. ZABRANJENO tvrditi da krivična osuda automatski dovodi do naknade štete.

23. NAPLATIVOST PRESUDE — OBAVEZNO UPOZORENJE: Uspeh u sudskom sporu ne garantuje naplatu. Ako je tuženi fizičko lice bez imovine ili privredno društvo u stečaju/likvidaciji — presuda je praktično nenaplatva. Pre preporuke tužbe UVEK navedi: "Prethodno je neophodno proveriti solventnost tuženog i postojanje imovine pogodne za izvršenje."

24. GARANTNI FOND — NEPOZNAT ŠTETNIK: Za saobraćajne nezgode gde je štetnik nepoznat ili neosiduran vozač — zahtev za naknadu štete podnosi se GARANTNOM FONDU SRBIJE (Zakon o obaveznom osiguranju u saobraćaju). Za ostale slučajeve nepoznatog štetnika (van saobraćaja) — nema institucionalnog mehanizma naplate; oštećeni praktično nema mogućnost naplate, što je presudan rizik koji mora biti eksplicitno naveden.

══════════════════════════════════════════
KRITIČNE PRAVNE GREŠKE — NIKADA NE SMEŠ TVRDITI:
══════════════════════════════════════════

[ZASTARELOST — ZOO čl. 360–393]
❌ ZABRANJENA TVRDNJA: "Opomena/dopis/email/pismo/poziv prekida zastarelost"
✅ TAČNO: Zastarelost prekida JEDINO: (1) tužba ili pokretanje izvršenja, (2) pisano priznanje duga od strane DUŽNIKA.
✅ IZUZETAK — OVO PREKIDA: Vansudsko poravnanje potpisano od strane dužnika = pisano priznanje = prekida zastarelost.
❌ ZABRANJENA TVRDNJA: "Komunalne usluge zastarevaju za 3 godine"
✅ TAČNO: Periodična potraživanja (struja, voda, gas, telefon, kirija) zastarevaju za 1 GODINU (ZOO čl. 374).

[OTKAZ UGOVORA O RADU — Zakon o radu]
❌ ZABRANJENA TVRDNJA: Otkaz se može dati usmeno
✅ TAČNO: Rešenje o otkazu mora biti u pisanoj formi (čl. 185 ZOR) i uručeno zaposlenom.

[IZDRŽAVANJE — Porodični zakon]
❌ ZABRANJENA TVRDNJA: "Alimentacija/izdržavanje automatski prestaje" kada se promene okolnosti
✅ TAČNO: Izdržavanje ne prestaje automatski. Potrebna je tužba za izmenu ili prestanak (PZ čl. 162). Sud donosi novu odluku.

[NAKNADA ŠTETE — ZOO]
❌ ZABRANJENA TVRDNJA: Emotivna ili moralna podrška sama po sebi daje pravo na naknadu
✅ TAČNO: Nematerijalna šteta zahteva utvrđivanje konkretne povrede ličnog dobra (čl. 200 ZOO).

[HIPOTEKA]
❌ ZABRANJENA TVRDNJA: Hipotekarni poverilac mora podneti tužbu za naplatu
✅ TAČNO: Zakon o hipoteci dozvoljava vansudsku naplatu — hipoteka je izvršna isprava (čl. 26).

[POBIJANJE SKUPŠTINSKE ODLUKE]
❌ ZABRANJENA TVRDNJA: Rok za pobijanje je 6 meseci
✅ TAČNO: Rok je 30 dana od dana saznanja, a NAJKASNIJE 6 meseci od donošenja (ZPD čl. 376). Oba roka su prekluzivna.

[OPŠTE PRAVILO]
Ako kontekst ne sadrži eksplicitnu potvrdu za tvrdnju — ne tvrditi. Bolje "kontekst ne pokriva ovaj aspekt" nego netačna informacija.

══════════════════════════════════════════
KADA NEMA ODGOVORA — koristi TAČNO ovaj format:
══════════════════════════════════════════
PRAVNI OSNOV: Nije pronađen u bazi podataka
ODGOVOR: U dostavljenoj bazi zakona nema direktno primenljive odredbe za ovo pitanje.
CITAT IZ ZAKONA: "Nije dostupno"
PRAVNA POSLEDICA: Nije moguće utvrditi bez odgovarajuće zakonske osnove u bazi.
POUZDANOST: 0% — Odredba nije pronađena u dostupnoj bazi zakona."""

SYSTEM_PROMPT_NACRT = """Ti si stručni AI pravni asistent za advokate u Srbiji.
Generišeš nacrte pravnih dokumenata na osnovu dostavljenih činjenica.

OBAVEZNI FORMAT ODGOVORA:

PRAVNI OSNOV: [zakoni i članovi koji se primenjuju na ovu vrstu dokumenta]

NACRT:
[potpuni tekst nacrta dokumenta — formalni pravni stil, srpska pravna terminologija]
[nepoznate podatke označi sa [PODATAK_KOJI_TREBA_POPUNITI]]

NAPOMENA: Ovaj nacrt je generisan uz pomoć AI i mora biti pregledan i potvrđen od strane ovlašćenog advokata pre upotrebe.

PRAVILA:
1. Koristi formalni pravni stil i srpsku pravnu terminologiju.
2. Uvek piši sa srpskim dijakritičkim znacima (č, ć, ž, š, đ).
3. Nacrt mora biti u skladu sa važećim srpskim zakonodavstvom.
4. Ne izmišljaj činjenice koje nisu navedene u pitanju."""

SYSTEM_PROMPT_ANALIZA = """Ti si iskusan pravni saradnik za advokate u Srbiji.
Analiziraš pravne dokumente, predmete i situacije.
Odgovaraš ISKLJUČIVO na osnovu važećeg srpskog prava.
Ne izmišljaš članove zakona — ako nisi siguran, kažeš to.

OBAVEZNI FORMAT — odgovori u TAČNO ovom redosledu sa TAČNO ovim naslovima:

## IZVRŠNI REZIME
Procena uspeha: [VISOKA / SREDNJA / NISKA]
Raspon: [X-Y%]
Pouzdanost procene: [Z%]
Najjači argument: [jedna rečenica]
Najveći rizik: [jedna rečenica]
Ključni dokaz: [koji dokaz odlučuje predmet]
Sledeći korak: [šta advokat radi sutra ujutru]

## PRAVNI OSNOV
[Koji zakoni i članovi se primenjuju. Navedi tačne članove.]

## ANALIZA PREDMETA
[Detaljna analiza — argumenti, činjenice, procesni status]

## CRVENE ZASTAVICE
[Svaka zastavica počinje sa 🚨 i mora biti konkretan, udarni one-liner]
🚨 [Konkretna opasnost koja zahteva hitnu pažnju]
🚨 [Ako nema zastavica — napiši: Nema kritičnih zastavica]

## DOKAZ KOJI MENJA SVE
Ako se dokaže [X]: uspeh raste sa [A%] na [B%]
Ako protivnik dostavi [Y]: uspeh pada sa [A%] na [C%]
[Identifikuj jednu ključnu činjenicu koja može preokrenuti ishod]

## SLABOSTI I RIZICI
[Gde može da se izgubi, procesne zamke, rokovi koji ističu]

## STRATEGIJA I PREPORUKE
[Konkretni koraci, šta pripremiti, kako nastupiti]

## HRONOLOGIJA
[Ako se mogu izvući datumi iz dokumenta — navedi kao timeline]
[Format: DD.MM.YYYY — Događaj]
[Ako nema datuma — izostavi ovu sekciju]

VAŽNO ZA PROCENU USPEHA:
- NIKAD ne daj jedan broj (ne "83%")
- Uvek daj raspon (npr. "55-70%")
- Uvek daj pouzdanost procene (koliko si siguran u procenu)
- VISOKA = raspon 70-90%, SREDNJA = 45-70%, NISKA = ispod 45%
- Procena mora biti zasnovana na navedenim činjenicama, ne na pretpostavkama

VAŽNO ZA CRVENE ZASTAVICE:
- Svaka zastavica je konkretan problem, ne generička napomena
- Loše: "Nedostaje dokumentacija"
- Dobro: "🚨 Ne postoji dokaz da je otkaz uručen tužiocu"
- Loše: "Rok može biti problem"
- Dobro: "🚨 Rok za žalbu ističe za 8 dana — hitno podneti"

PRAVILA:
1. Uvek piši sa srpskim dijakritičkim znacima (č, ć, ž, š, đ).
2. Ako dostavljeni tekst nije pravne prirode, jasno to naglasi.
3. Na kraju dodaj: "Analiza je generisana uz pomoć AI i mora biti proverena od strane ovlašćenog advokata." """

# ─── Interne pomoćne funkcije ────────────────────────────────────────────────

def _normalizuj(tekst: str) -> str:
    """Uklanja dijakritike i pretvara u mala slova — za interno poređenje."""
    tekst = (tekst or "").lower()
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        tekst = tekst.replace(src, dst)
    return tekst


def _filtriraj_kontekst(docs: list[str]) -> list[str]:
    """Odbacuje prazne i prekratke dokumente."""
    return [d for d in docs if len(d.strip()) > 50]


def _ima_obavezne_sekcije(odgovor: str, sekcije: list[str] | None = None) -> bool:
    """Proveri da li odgovor sadrži sve obavezne sekcije."""
    proveri = sekcije if sekcije is not None else OBAVEZNE_SEKCIJE_QA
    return all(s in odgovor for s in proveri)


# Framework citations baked into PARNICA/FALLBACK prompt templates.
# These are cited as structural legal framework in EVERY relevant response by instruction —
# they may not be in RAG context for every query type.
# Guard v2.0 must NOT fire on these to avoid false-positive blocks.
_FRAMEWORK_CLANOVI_EXEMPT: frozenset[str] = frozenset([
    "154", "155",   # ZOO osnov odgovornosti za štetu (PARNICA ANALIZA ŠTETE template)
    "189", "200",   # ZOO materijalna + nematerijalna šteta (PARNICA ANALIZA ŠTETE template)
    "192",          # ZOO doprinos oštećenog — PARNICA RIZICI section
    "374",          # ZOO periodična potraživanja (1 god.) — PARNICA PRIMARY RULES
    "376", "377",   # ZOO zastarelost — hardcoded in PARNICA PROCESNI KORACI
])


def _proveri_halucinaciju(odgovor: str, docs: list[str]) -> tuple[bool, str]:
    """
    Anti-hallucination guard v2.0 — strict per-article.
    Vraća (validan, razlog).

    Logika v2.0:
    - "nije pronađen u bazi" markeri → uvek validan (early return)
    - Kontekst < 3 docs ili < 500 chars → skip (tanki kontekst ne kažnjava)
    - Iz odgovora se izvlače SVI citirani brojevi članova
    - Izvačeni koji su u _FRAMEWORK_CLANOVI_EXEMPT (ZOO strukturni template) → preskačemo
    - SVAKI preostali citiran clan MORA biti prisutan u kontekstu
    - Ako bar JEDAN nije → False + lista fabricated
    v1 razlika: v1 puštao ako bar 1 bio u kontekstu → fabricated ostali prolazili
    """
    # Early return — odgovor koji eksplicitno signalizira nedostatak podataka je uvek validan
    markeri_nije_pronadjeno = [
        "nije pronađen u bazi",
        "nema direktno primenljive",
        "nije dostupno",
        "0% —",
    ]
    odgovor_lower = odgovor.lower()
    if any(m in odgovor_lower for m in markeri_nije_pronadjeno):
        return True, "ok"

    kontekst = " ".join(docs)
    kontekst_norm = _normalizuj(kontekst)

    # Skip ako kontekst prekratak — v1 vektori/pogrešni zakoni ne smeju blokirati
    if len(docs) < 3 or len(kontekst) < 500:
        logger.info("[HALUCINACIJA_SKIP] Kontekst prekratak (%d docs, %d chars) — preskačem", len(docs), len(kontekst))
        return True, "ok"

    # 1) Strict per-article check
    citirani_raw = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", odgovor)

    # Deduplicate while preserving order
    vidjeni: set[str] = set()
    citirani_unique: list[str] = []
    for c in citirani_raw:
        if c not in vidjeni:
            vidjeni.add(c)
            citirani_unique.append(c)

    # Remove framework template citations (always present in prompts, not from RAG)
    za_provjeru = [c for c in citirani_unique if c not in _FRAMEWORK_CLANOVI_EXEMPT]

    if za_provjeru:
        fabrikovani: list[str] = []
        for clan in za_provjeru:
            clan_norm = _normalizuj(clan)
            pattern = rf"lan\s+{re.escape(clan_norm)}(?!\d)"
            if not re.search(pattern, kontekst_norm):
                fabrikovani.append(clan)

        if fabrikovani:
            logger.warning(
                "HALUCINACIJA v2.0: %d/%d citiranih članova nije u kontekstu: %s",
                len(fabrikovani), len(za_provjeru), fabrikovani[:5],
            )
            clanovi_str = ", ".join(f"Član {c}" for c in fabrikovani[:5])
            return False, f"{clanovi_str} — citiran ali nije u dostavljenom kontekstu"

    # 2) Citat check — samo kad nema nijednog citiranog broja člana
    if not citirani_unique:
        match_citat = re.search(r'CITAT IZ ZAKONA:\s*"([^"]{20,})"', odgovor)
        if match_citat:
            citat_raw = match_citat.group(1)
            citat_norm = _normalizuj(citat_raw)[:50].strip()
            if citat_norm and citat_norm not in kontekst_norm:
                logger.warning("HALUCINACIJA: citat nije pronađen u kontekstu: %s...", citat_norm[:30])
                return False, "Citat nije pronađen u dostavljenom kontekstu"

    return True, "ok"


# ─── T6: Praksa citation extractor ──────────────────────────────────────────

def _extract_praksa_citations(data: dict) -> list[tuple[str, str]]:
    """
    Extract (sud, broj_odluke) pairs from LLM JSON output's sudska_praksa array.
    Used by hallucination guard to verify citations against provided praksa_context.
    """
    praksa_array = data.get("sudska_praksa", [])
    if not isinstance(praksa_array, list):
        return []
    result = []
    for item in praksa_array:
        if isinstance(item, dict):
            sud = (item.get("sud") or "").strip()
            dn  = (item.get("broj_odluke") or "").strip()
            if dn and len(dn) >= 3:          # ignore trivially empty/short strings
                result.append((sud, dn))
    return result


# ─── Semantic relevance check (Anti topic-drift) ─────────────────────────────

_TOPIC_KEYWORDS: list[tuple[list[str], list[str]]] = [
    # (query keywords, article-content keywords that MUST appear for match)
    (["kradj", "kradjom", "kradje"],          ["kradj", "prisvaj", "oduzm"]),
    (["razbojn"],                             ["razbojn", "sil", "pretnjom"]),
    (["ubistvo", "ubojstv"],                  ["ubojstv", "ubistv", "lisi", "zivot"]),
    (["silovanje", "polni"],                  ["polni", "silov", "seksualni"]),
    (["nasilje u porodici"],                  ["porodic", "nasilj", "clan"]),
    (["droga", "narkotik", "opojn"],          ["droga", "narkotik", "opojn", "supstanc"]),
    (["prevara krivicn", "utaja krivicn"],     ["prevara", "utaj", "obmanjiv"]),
    (["zastita potrosac"],                    ["potrosac", "potrosacki"]),
    (["radno pravo", "otkaz", "zaposleni"],   ["rad", "zaposleni", "otkaz"]),
]


def _proveri_tematsku_relevantnost(pitanje: str, odgovor: str, docs: list[str]) -> tuple[bool, str]:
    """
    Detects topic-drift: question is about X but cited article is about Y.
    Only fires when the mismatch is clear-cut (e.g., theft query → weapons article).

    Returns (ok, reason). Returns False only when confident mismatch detected.
    """
    q_norm = _normalizuj(pitanje)
    kontekst_norm = _normalizuj(" ".join(docs))

    # Find the primary cited article number in the response
    citirani = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", odgovor)
    if not citirani:
        return True, "ok"

    for q_terms, content_terms in _TOPIC_KEYWORDS:
        # Does the query match this topic?
        if not any(t in q_norm for t in q_terms):
            continue

        # Query IS about this topic — verify the cited articles' content has these terms
        for clan_num in citirani[:2]:
            clan_norm = _normalizuj(clan_num)
            # Extract article text from context (up to 800 chars)
            pat = rf"lan\s+{re.escape(clan_norm)}\b(.{{0,800}}?)(?:lan\s+\d|\Z)"
            m = re.search(pat, kontekst_norm, re.DOTALL)
            if m:
                article_text = m.group(0)
                if any(t in article_text for t in content_terms):
                    return True, "ok"  # at least one cited article is topically correct

        # No cited article matched the topic
        logger.warning(
            "[TOPIC_DRIFT] Pitanje o '%s' ali citirani članovi %s nisu o toj temi",
            q_terms[0], citirani[:2],
        )
        return False, f"Odgovor citira tematski nesrodne članove ({', '.join(['Član ' + c for c in citirani[:2]])})"

    return True, "ok"


# ─── Poznate kritične pravne greške — pattern → ispravka ─────────────────────
#
# Svaki unos: (regex_pattern, korekcija)
# Pattern se primenjuje na normalizovani (bez dijakritika, lowercase) odgovor.
# Ako se pogodi → odgovor se odbacuje i vraća se siguran fallback.

ZABRANJENE_GRESKE: list[tuple[str, str]] = [
    # Zastarelost: opomena / dopis / email ne prekida zastarelost
    (
        r"opomen\w*\s+\w{0,15}\s*prekid",
        "Opomena ne prekida zastarelost (ZOO čl. 388–393). "
        "Zastarelost se prekida samo: tužbom/izvršenjem ili pisanim priznavanjem duga od strane dužnika.",
    ),
    (
        r"slanj\w+\s+opomen\w*\s+\w{0,15}\s*(zastarel|rok)",
        "Slanje opomene nema pravno dejstvo na tok roka zastarelosti prema ZOO.",
    ),
    (
        r"opomen\w*\s+\w{0,20}\s*(zaustav|suspenduj|sprecav|odlag)\w*\s+zastarel",
        "Opomena ne zadržava niti suspenduje zastarelost prema ZOO.",
    ),
    (
        r"(dopis|email|pismo|poziv|obavestenj)\w*\s+\w{0,20}\s*prekid\w*\s+zastarel",
        "Dopis/email/pismo/poziv ne prekida zastarelost (ZOO čl. 388–393).",
    ),
    # Otkaz: usmeni otkaz nije validan
    (
        r"usmen\w+\s+\w{0,10}\s*otka[zž]",
        "Otkaz ugovora o radu mora biti u pisanoj formi (čl. 185 ZOR). Usmeni otkaz nije pravno validan.",
    ),
    # Alimentacija ne prestaje automatski
    (
        r"aliment\w*\s+\w{0,15}\s*automatsk\w*\s*(prestaj|gasi|ukida)",
        "Izdržavanje ne prestaje automatski (PZ čl. 162). Potrebna je tužba za izmenu ili prestanak izdržavanja.",
    ),
    (
        r"izdrzavanj\w*\s+\w{0,15}\s*automatsk\w*\s*(prestaj|gasi|ukida)",
        "Izdržavanje ne prestaje automatski (PZ čl. 162). Potrebna je tužba za izmenu ili prestanak izdržavanja.",
    ),
    # Komunalne usluge — rok je 1 godina, ne 3
    (
        r"komunaln\w*\s+\w{0,20}\s*(tri|3)\s*(god|mesec|rok|godin)\w*\s*(zastarel|zastarev)",
        "Potraživanja za komunalne i slične periodične usluge zastarevaju za 1 godinu (ZOO čl. 374), ne za 3 godine.",
    ),
    # Pobijanje skupštinske odluke — 30 dana, ne 6 meseci
    (
        r"pobijanj\w*\s+\w{0,20}\s*skupstin\w*\s+\w{0,20}\s*(sest|6)\s*(mesec|god)\w*",
        "Rok za pobijanje odluke skupštine privrednog društva je 30 dana od saznanja, a najkasnije 6 meseci od donošenja (ZPD čl. 376) — prekluzivni rok od 30 dana se ne sme izostaviti.",
    ),
    # Žalba na optužnicu — to je PRIGOVOR, ne žalba
    (
        r"zalb\w*\s+\w{0,15}\s*na\s+optuznic",
        "Na optužnicu se ne podnosi žalba već PRIGOVOR u roku od 8 dana od dostavljanja (ZKP čl. 335).",
    ),
    # Hrvatska terminologija — samo stvarno hrvatske reči, ne srpske kolokvijalnosti
    (
        r"\b(izvanparnicn|odvjetnik|tisuc|glede|sukladno)\b",
        "Odgovor sadrži hrvatsku pravnu terminologiju (izvanparnični/odvjetnik/tisuća/glede/sukladno). Koristiti: vanparnični, advokat, hiljada, u skladu sa.",
    ),
    # Hipoteka — ne ide tužbom nego direktno izvršenjem
    (
        r"hipoteka\w*\s+\w{0,20}\s*(mora|treba|potrebno)\s+\w{0,15}\s*tuzb",
        "Hipotekarni poverilac NE mora podneti tužbu — Zakon o hipoteci (čl. 26) dozvoljava vansudsku naplatu direktnim izvršenjem na osnovu hipoteke kao izvršne isprave.",
    ),
    # Definitvne tvrdnje bez pravne ograde — visok rizik od pogrešnog savetovanja
    (
        r"\bimate\s+(pravo|garantovano|sigurno)\b",
        "Zabranjene definitivne tvrdnje bez pravne ograde ('imate pravo', 'garantovano'). "
        "Koristiti: 'postoji verovatan osnov', 'uz ispunjenje zakonskih uslova', 'sudska praksa sugeriše'.",
    ),
    (
        r"\b(garantovano|sigurno)\s+\w{0,10}\s*(dobij|naplatit|uspet|izvi)\w+",
        "Zabranjeno garantovati ishod sudskog postupka. "
        "Koristiti: 'uz ispunjenje zakonskih uslova postoji osnov' umesto 'garantovano ćete dobiti'.",
    ),
]


def _verifikuj_pravne_greske(odgovor: str) -> tuple[bool, str]:
    """
    Skenira odgovor za poznate pravne greške.
    Vraća (validan, opis_greske).
    Greška se detektuje na normalizovanom tekstu (bez dijakritika).
    """
    # "Nije pronađeno" odgovori su uvek bezbedni
    if "nije pronadjen u bazi" in _normalizuj(odgovor) or "0% —" in odgovor:
        return True, "ok"

    tekst_norm = _normalizuj(odgovor)
    for pattern, opis in ZABRANJENE_GRESKE:
        if re.search(pattern, tekst_norm):
            logger.error("PRAVNA GREŠKA DETEKTOVANA | pattern='%s' | %s", pattern, opis)
            return False, opis
    return True, "ok"


# ─── Fallback za detektovanu pravnu grešku ───────────────────────────────────

def _srpski_termini(odgovor: str) -> str:
    """Zamenjuje kolokvijalnosti srpskim pravnim terminima (bez blokiranja)."""
    zamene = [
        (r"\bukoliko\b", "ako"),
        (r"\bstoga\b", "zbog toga"),
        (r"\bkako bi\b", "da bi"),
        (r"\bradi čega\b", "zbog čega"),
        (r"\bvlasnički list\b", "list nepokretnosti"),
        (r"\bočitovanje\b", "izjašnjenje"),
        (r"\bočitovanj\b", "izjašnjenj"),
    ]
    for pattern, zamena in zamene:
        odgovor = re.sub(pattern, zamena, odgovor, flags=re.IGNORECASE)
    return odgovor


# ─── PII Stripping — GDPR/ZZPL sloj pre slanja na externe API-je ────────────
#
# Primenjuje se na svaki tekst koji napušta server (OpenAI, Pinecone embeddings).
# Ne primenjuje se na odgovore koji se vraćaju korisniku.
#
# Pokriva: JMBG, PIB, broj pasoša/lične karte, telefon (SRB format),
# broj bankovnog računa (18 cifara), broj sudskog predmeta, email adrese,
# IBAN (RS format), matični broj (8 cifara).

_PII_ZAMENE: list[tuple[re.Pattern, str]] = [
    # JMBG: 13 cifara (može biti odvojen crticom na poz. 7)
    (re.compile(r"\b\d{7}[-]?\d{6}\b"), "[JMBG-MASKED]"),
    # PIB: 9 cifara (Serbian tax ID) — word boundary
    (re.compile(r"\bPIB[:\s]*\d{9}\b", re.IGNORECASE), "[PIB-MASKED]"),
    (re.compile(r"\b\d{9}\b(?=\s*(pib|poreski))", re.IGNORECASE), "[PIB-MASKED]"),
    # Matični broj: 8 cifara (samo kad eksplicitno označen)
    (re.compile(r"\b(MB|matični\s+broj)[:\s]*\d{8}\b", re.IGNORECASE), "[MB-MASKED]"),
    # Broj lične karte: 9 cifara ili format XXX123456
    (re.compile(r"\b(LK|lična\s+karta|broj\s+lk)[:\s]*[A-Z]{0,3}\d{6,9}\b", re.IGNORECASE), "[LK-MASKED]"),
    # Broj pasoša: slovo + 7-8 cifara
    (re.compile(r"\b[A-Z]{1,2}\d{7,8}\b"), "[PASOS-MASKED]"),
    # Telefon SRB: 06x, 01x, +381, 00381
    (re.compile(r"\b(\+381|00381|0)(6[0-9]|1[0-9]|2[0-9]|3[0-9])[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b"), "[TEL-MASKED]"),
    # IBAN (RS + opšti)
    (re.compile(r"\bRS\d{2}\s?\d{3}\s?\d{13}\s?\d{2}\b"), "[IBAN-MASKED]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[\s]?([A-Z0-9]{4}[\s]?){4,7}[A-Z0-9]{1,4}\b"), "[IBAN-MASKED]"),
    # Broj tekućeg računa: 18 cifara (srpski format XXX-XXXXXXXXXXXXXXX-XX)
    (re.compile(r"\b\d{3}[-]?\d{13,15}[-]?\d{2}\b"), "[RACUN-MASKED]"),
    # Broj sudskog predmeta: P. 123/2024, K. 45/23, Gž. 12/2024, itd.
    (re.compile(r"\b(P|K|Kž|Gž|Rev|Už|R|Su|I|Iv|Porodica|Porodicni|Pp|Pž|Up)\s*\.?\s*\d{1,6}\s*/\s*\d{2,4}\b", re.IGNORECASE), "[PREDMET-MASKED]"),
    # Email adrese
    (re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"), "[EMAIL-MASKED]"),
    # Adrese: ulica + broj (heuristika — smanjuje false positive)
    (re.compile(r"\b(ulica|ul\.|bulevar|blvd\.|trg|put\s)\s+[A-ZŠĐČĆŽ][a-zšđčćž]+\s+\d+[a-zA-Z]?\b", re.IGNORECASE), "[ADRESA-MASKED]"),
]


def _skini_pii(tekst: str) -> str:
    """
    Maskira lične podatke pre slanja na eksterni API.
    GDPR čl. 4(1), ZZPL čl. 4(1) — pseudonimizacija kao tehnička mera zaštite.
    """
    if not tekst:
        return tekst
    for pattern, zamena in _PII_ZAMENE:
        tekst = pattern.sub(zamena, tekst)
    return tekst


def _hash_za_log(tekst: str) -> str:
    """SHA-256 hash prvog dela pitanja — za logging bez curenja sadržaja."""
    return hashlib.sha256((tekst or "")[:200].encode()).hexdigest()[:16]


def _odgovor_pravna_greska(opis: str) -> str:
    return (
        f"PRAVNI OSNOV: Nije moguće dati siguran odgovor na osnovu dostupnog konteksta\n\n"
        f"ODGOVOR: Sistem je detektovao potencijalnu pravnu grešku u odgovoru i odbio ga iz predostrožnosti.\n\n"
        f"NAPOMENA SISTEMA: {opis}\n\n"
        f"CITAT IZ ZAKONA: \"Nije primenljivo\"\n\n"
        f"PRAVNA POSLEDICA: Nije moguće utvrditi bez verifikovanog zakonskog osnova.\n\n"
        f"POUZDANOST: 0% — Odgovor odbijen zbog detektovane pravne neispravnosti."
        + DISCLAIMER
    )


def _izvuci_zakone_iz_docs(docs: list[str]) -> list[str]:
    """Parsira nazive zakona iz formatiranih dokumenata (ZAKON: linija)."""
    zakoni = []
    vidjeni: set[str] = set()
    for doc in docs:
        m = re.search(r"ZAKON:\s*(.+)", doc)
        if m:
            zakon = m.group(1).strip()
            kljuc = zakon.lower()
            if kljuc not in vidjeni:
                vidjeni.add(kljuc)
                zakoni.append(zakon)
    return zakoni


def _dodaj_izvor(odgovor: str, docs: list[str]) -> str:
    """Pronalazi Sl. glasnik referencu iz konteksta i dodaje SLUŽBENI IZVOR: sekciju."""
    zakoni = _izvuci_zakone_iz_docs(docs)
    if not zakoni:
        return odgovor
    reference = []
    for zakon in zakoni:
        zakon_norm = _normalizuj(zakon)
        for kljuc, glasnik in SL_GLASNIK_MAP.items():
            if kljuc in zakon_norm:
                reference.append(f"{zakon} ({glasnik})")
                break
    if not reference:
        return odgovor
    return odgovor + "\n\nSLUŽBENI IZVOR: " + " | ".join(reference)


def _ogranici_pouzdanost(odgovor: str) -> str:
    """Osigurava da procenat u NAPOMENI O POUZDANOSTI nije viši od 85%."""
    idx = odgovor.find("POUZDANOST:")
    if idx == -1:
        return odgovor

    def _cap(m: re.Match) -> str:
        broj = int(m.group(1))
        return f"{min(broj, 85)}%"

    pre  = odgovor[:idx]
    deo  = odgovor[idx:]
    deo  = re.sub(r"\b(\d{1,3})%", _cap, deo)
    return pre + deo


def _dodaj_disclaimer(odgovor: str) -> str:
    return odgovor + DISCLAIMER


def _ukloni_nedostupan_tekst(odgovor: str) -> str:
    """
    Post-processing zaštita: zamenjuje sve varijante 'nije dostupan/pronađen'
    u CITAT ZAKONA / CITAT sekciji sa neutralnim markerom.
    """
    _NEDOSTUPAN_MARKER = "CITAT ZAKONA: [—] Direktan tekst člana nije pronađen u bazi — pogledajte Pravni osnov za reference."

    # Varijanta 1: CITAT ZAKONA: "...placeholder tekst..."  (u navodnicima)
    odgovor = re.sub(
        r'(?:📖\s*)?CITAT ZAKONA:\s*"[^"]*(?:'
        r'tekst nije dostupan|nije dostupan u bazi|nije dostupan|'
        r'nije pronađen u bazi|nije pronadjen u bazi|'
        r'tekst clana nije|proverite važeći propis|proverite vazeci propis'
        r')[^"]*"',
        _NEDOSTUPAN_MARKER,
        odgovor,
        flags=re.IGNORECASE,
    )

    # Varijanta 2: CITAT ZAKONA: placeholder bez navodnika (do kraja reda)
    odgovor = re.sub(
        r'(?:📖\s*)?CITAT ZAKONA:\s*(?:'
        r'Tekst (?:člana )?nije dostupan|tekst nije dostupan|'
        r'Nije dostupan u bazi|nije pronađen u bazi|nije pronadjen u bazi|'
        r'Nije dostupan[^\.:\n]*'
        r')[^\n]*',
        _NEDOSTUPAN_MARKER,
        odgovor,
        flags=re.IGNORECASE,
    )

    # Varijanta 3: placeholder unutar linije CITAT ZAKONA (mešani sadržaj)
    odgovor = re.sub(
        r'((?:📖\s*)?CITAT ZAKONA:\s*)[^\n]*(?:'
        r'tekst nije dostupan|nije dostupan u bazi|nije dostupan|'
        r'nije pronađen|nije pronadjen|proverite važeći|proverite vazeci'
        r')[^\n]*',
        _NEDOSTUPAN_MARKER,
        odgovor,
        flags=re.IGNORECASE,
    )

    return odgovor


# ═══════════════════════════════════════════════════════════════════════════════
# REFAKTOR v2.0 — Klasifikator i 4 izolovana system prompta
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Klasifikator v2.0 — trigger liste ───────────────────────────────────────

# REFAKTOR v2.0 — novi klasifikator, vraća uppercase: "COMPLIANCE","PORESKI","PARNICA","DEFINICIJA"

_KZ_OVERRIDE_TRIGGERS = [
    "krivicni zakonik", "krivicno delo", "krivicna prijava", "krivicna odgovornost",
    "kazna za krađu", "kazna za kradju", "kazna za razbojnistvo", "kazna za ubistvo",
    "kradja", "kradju", "razbojnistvo", "razbojnistva", "razbojnicka kradja",
    "ubistvo", "ubojstvo", "umorstvo",
    "silovanje", "nasilje u porodici", "nasilje u braku",
    "opojne droge", "narkotici", "narkotik", "droge",
    "iznuda", "ucena", "pronevera", "prevara krivicna", "falsifikovanje",
    "nuzna odbrana", "krajnja nuzda",
    "uslovni otpust", "uslovna osuda", "zatvorska kazna", "kazna zatvora",
    "izricanje kazne", "olaksavajuce okolnosti", "otezavajuce okolnosti",
    "krivicna sankcija", "vaspitna mera",
    "krivicno pravo",
]

_COMPLIANCE_TRIGGERS = [
    "aml", "kyc", "pranje novca", "pranja novca", "exchange", "platforma",
    "licenc", "registracij", "dozvol", "nadzor", "komisija za hartije",
    "narodna banka", "obveznik", "dubinska analiza", "finansiranje terorizma",
    "sprecavanj",         # sprečavanje pranja novca
    "izda token", "izdavanje tokena", "token", "ico", "sto",
    "digitalna imovina i registr", "pruzalac usluga",
    "crypto firma", "kripto firma", "zspnft", "compliance",
]

_PORESKI_TRIGGERS = [
    "porez", "oporeziv", "oporezovanj", "oporezuj", "poresk", "pdv",
    "doprinosi", "prijava prihoda", "poreska obaveza", "kapitalna dobit",
    "prihod od", "prihodi od", "placanje u", "prima kao placanje",
    "uplata u kripto", "usdt", "btc", "eth", "bitcoin", "ethereum",
    "softverske usluge i plac", "faktura u kripto", "kripto kao prihod",
    "oporezuje se", "kako se oporezuje", "da li je oporezivo",
    "prijava poreza", "poreska stopa", "porez na prihod",
    "porez na imovinu", "porez na dobit", "kapitalni dobitak",
    "akciza", "fiskalni",
]

_PARNICA_TRIGGERS = [
    "tuzba", "tuziti", "tuzim", "tuzio", "naknada stete", "naknadu stete",
    "steta", "stete", "stetu", "pravo na naknadu",
    "odgovornost", "parnica", "tuzilac", "tuzeni", "presuda",
    "izvrsenje", "zastarelost", "rok za tuzbu", "medijacija",
    "vansudsko", "osiguranje i steta", "saobracajna nezgoda",
    "povreda", "povreden", "pretucen", "polomljen", "telesna",
    "otkaz", "radno pravo spor", "imovinskopravni",
    "prvostepen", "drugostepen", "revizij", "zalba na presudu",
    # KZ — krivičnopravna pitanja → PARNICA (gpt-4o, 2500 tokens)
    "krivicno delo", "krivicnih dela", "krivicna dela", "krivicna prijava",
    "krivicna odgovornost", "krivicna sankcija", "krivicno gonjenje",
    "krivicnog zakonika", "krivicni zakonik", "krivicnom zakoniku",
    "kazna zatvora", "kazna za", "zatvorska kazna", "novcan kazna kz",
    "kradja", "kradjom", "kradje", "teski oblik kradje",
    "razbojnistvo", "razbojnicka kradja",
    "prevara krivicn", "utaja krivicn",
    "iznuda", "ucena krivicn",
    "ubistvo", "ubojstv", "telesna povreda krivicn",
    "nasilje u porodici", "seksualno nasilje", "silovanje",
    "droga krivicn", "opojne droge", "narkotik",
    "pranje novca krivicn", "organizovani kriminal",
    "krivicno gonjenje", "krivicna prijava policiji",
    "zastara krivicnog", "zastarelost krivicnog",
    "uslovna osuda", "uslovni otpust",
    "maloletan ucini", "maloletni ucinioc",
    "recidiviz", "povratnik",
    # Zabrana konkurencije → ZR/161-162 spor je radno-pravni, ne definitivan
    "konkurentsk",          # "konkurentski rad", "zabrana konkurentskog" → ZR spor
    "zabrana konkurencije", # explicit competition clause dispute term
    "konkurencij",          # "zabranu/zabrane/zabrani konkurencije" — sve padeške forme
    # Civil/commercial law instruments — prevent DEFINICIJA path overflow (Commit 5)
    "zalog",
    "zaloga",
    "stečaj",
    "stecaj",
    "hipoteka",
    "jemstv",       # root: jemstvo, jemstva, jemstven — all surety forms
    "garancij",     # root: garancija, garancije, garancijama — all guarantee forms
    "bankars",      # root: bankarska, bankarske, bankarsku — all banking adj. forms
]

_DEFINICIJA_TRIGGERS = [
    "sta je ", "sto je ", "kako funkcionise", "koji zakon",
    "definicij", "objasni", "kada vazi", "koje su razlike",
    "kako se zove", "pojasni", "sta znaci", "sta se smatra",
    "koja je razlika", "sta podrazumeva",
]


_KZ_OVERRIDE_TRIGGERS = [
    "krivicno delo", "krivicna dela", "krivicnih dela",
    "krivicna prijava", "krivicna odgovornost", "krivicno gonjenje",
    "krivicnog zakonika", "krivicni zakonik", "krivicnom zakoniku",
    "krivicna sankcija", "kazna zatvora",
]

# ─── Word-boundary matching config (v2.2) ────────────────────────────────────
# Mehanički fix za substring mine: trigger koji je cela reč se više ne poklapa
# kao deo nepovezane reči (npr. "sto" ne sme da hvata "stopa").
#
# PUNA GRANICA \bterm\b — skraćenice i anglizmi koji NE inflektiraju.
# KRITIČNO: "sto" MORA biti \bsto\b; \bsto (samo leading) i dalje hvata "stopa"
# jer "stopa" počinje na granici reči.
_WB_FULL: frozenset[str] = frozenset([
    "sto", "aml", "kyc", "pdv", "btc", "eth", "usdt", "ico",
    "bitcoin", "ethereum", "compliance", "exchange", "zspnft",
])

# LEADING GRANICA \bpattern — srpske reči koje se dekliniraju.
# Vrednost je regex pattern direktno za re.search().
# Koren može biti kraći od trigera (npr. "telesna" → r"\btelesn") da bi
# padežni oblici prolazili a lažni prefiksi (netelesna) bili blokirani.
# SPORNO trigeri (dozvol, sprecavanj, obveznik, doprinosi, prihod od,
# prihodi od, placanje u, odgovornost, povreda, zastarelost, izvrsenje,
# revizij, kazna za) NISU ovde — njihov problem je semantički, rešava se
# zasebno (Korak 3).
_WB_LEADING: dict[str, str] = {
    # --- COMPLIANCE ---
    "nadzor":       r"\bnadzor",
    "platforma":    r"\bplatform",
    "token":        r"\btoken",
    # --- PORESKI ---
    "akciza":       r"\bakciz",
    "fiskalni":     r"\bfiskaln",
    # --- PARNICA ---
    "tuzba":        r"\btuzb",
    "parnica":      r"\bparnic",
    "presuda":      r"\bpresud",
    "steta":        r"\bstet",
    "stete":        r"\bstet",
    "stetu":        r"\bstet",
    "otkaz":        r"\botkaz",
    "telesna":      r"\btelesn",
    "medijacija":   r"\bmedijacij",
    "iznuda":       r"\biznud",
    "kradja":       r"\bkradj",
    "kradjom":      r"\bkradj",
    "kradje":       r"\bkradj",
    "ubistvo":      r"\bubistv",
    "silovanje":    r"\bsilovan",
    "razbojnistvo": r"\brazbojnistv",
    "recidiviz":    r"\brecidiviz",
    # --- DEFINICIJA ---
    "sto je ":      r"\bsto je ",   # "isto je " ne sme da pali
}


def _match_trigger(term: str, q: str) -> bool:
    """Matchuje trigger u normalizovanom upitu koristeći odgovarajući oblik granice.

    - _WB_FULL    → re.search(r'\\bterm\\b', q) — skraćenice, bez infleksije
    - _WB_LEADING → re.search(pattern, q)       — srpske reči, padežni oblici prolaze
    - ostalo      → term in q                   — koreni, fraze, SPORNO (neizmenjeno)
    """
    t = _normalizuj(term)
    if t in _WB_FULL:
        return bool(re.search(r"\b" + re.escape(t) + r"\b", q))
    pat = _WB_LEADING.get(t)
    if pat is not None:
        return bool(re.search(pat, q))
    return t in q


def klasifikuj_pitanje(query: str) -> str:
    """
    REFAKTOR v2.2 — Klasifikuje upit u jedan od 4 tipa.
    Prioritet: KZ-override > COMPLIANCE > PORESKI > PARNICA > DEFINICIJA.

    KZ-override fires first so "krivično delo poreske utaje" routes to PARNICA
    (gpt-4o) instead of being stolen by PORESKI triggers.

    Compound condition (v2.1): PORESKI trigger se ignoriše ako upit istovremeno
    sadrži PARNICA trigger — radno-pravni kontekst ima prednost nad opštim poreskim
    rečima (npr. "doprinosi pri otkazu" → PARNICA, ne PORESKI).

    Word-boundary matching (v2.2): koristi _match_trigger() umesto čistog substring
    poređenja. Skraćenice dobijaju \bterm\b; srpske celo-rečne forme dobijaju \bterm
    (leading boundary, slobodan kraj — padežni oblici prolaze). Koreni i fraze
    ostaju substring. SPORNO trigeri netaknuti (Korak 3).

    Vraća uppercase string: "COMPLIANCE", "PORESKI", "PARNICA", "DEFINICIJA".
    """
    q = _normalizuj(query)
    logging.info("Klasifikacija: '%s' → ...", query[:50])

    # KZ override — mora biti pre PORESKI/COMPLIANCE da bi "krivično delo X" uvek → PARNICA
    for term in _KZ_OVERRIDE_TRIGGERS:
        if _match_trigger(term, q):
            logging.info("Klasifikacija: '%s' → PARNICA [KZ override: %s]", query[:50], term)
            return "PARNICA"

    for term in _COMPLIANCE_TRIGGERS:
        if _match_trigger(term, q):
            logging.info("Klasifikacija: '%s' → COMPLIANCE (trigger: %s)", query[:50], term)
            return "COMPLIANCE"

    for term in _PORESKI_TRIGGERS:
        if _match_trigger(term, q):
            # Compound condition (v2.1): radno-pravni kontekst ima prednost —
            # ako upit sadrži i parnični trigger, pusti PARNICA petlju da obradi
            if any(_match_trigger(pt, q) for pt in _PARNICA_TRIGGERS):
                break
            logging.info("Klasifikacija: '%s' → PORESKI (trigger: %s)", query[:50], term)
            return "PORESKI"

    for term in _PARNICA_TRIGGERS:
        if _match_trigger(term, q):
            logging.info("Klasifikacija: '%s' → PARNICA (trigger: %s)", query[:50], term)
            return "PARNICA"

    for term in _DEFINICIJA_TRIGGERS:
        if _match_trigger(term, q):
            logging.info("Klasifikacija: '%s' → DEFINICIJA (trigger: %s)", query[:50], term)
            return "DEFINICIJA"

    logging.info("Klasifikacija: '%s' → DEFINICIJA (default)", query[:50])
    return "DEFINICIJA"


# ─── 4 izolovana system prompta v2.0 ─────────────────────────────────────────

SYSTEM_PROMPT_COMPLIANCE = """Ti si Vindex AI — profesionalni AML/compliance sistem za pravo Republike Srbije.
Korisnici su advokati, compliance oficiri i finansijski regulatori koji proveravaju
svaki tvoj zaključak. Jedna netačnost = gubitak poverenja zauvek.

HIJERARHIJA IZVORA — NEPROMENJIVO PRAVILO (lex specialis):
PRIMARNI — ZSPNFT (Sl. glasnik RS br. 113/2017, 91/2019, 153/2020, 92/2023, 94/2024, 19/2025):
→ Definiše AML obaveze, KYC procedure, STR prijave, sankcije. ZSPNFT je lex specialis.
SEKUNDARNI — ZDI (Sl. glasnik RS br. 153/2020, 49/2021):
→ ISKLJUČIVO za definisanje ko je VASP subjekt (čl. 2 ZDI). Nikada primarni za AML.
TERCIJERNI — ZOO: NE PRIMENJUJE SE za AML/Compliance.

KORAK 1 — IDENTIFIKACIJA SUBJEKTA:
A) TIP ENTITETA: Domaće pravno lice → direktna primena ZSPNFT + ZDI |
   Strano pravno lice → KORAK 2 (ekstrateritorijalnost) |
   Fizičko lice → ograničen obim (ZSPNFT čl. 4) |
   Neregistrovani subjekt → ZDI čl. 147
B) VASP KVALIFIKACIJA (čl. 2 ZDI): razmena DI/fiat, prenos DI, čuvanje DI →
   AKO DA → obveznik po čl. 4 ZSPNFT

KORAK 2 — DECISION TREE: EKSTRATERITORIJALNOST (samo strani subjekti):
GRANA A — AKTIVNO CILJANJE (marketing/sajt na srpskom, RSD plaćanje, srpski uslovi) →
   Subjekt je OBVEZNIK. Tretman kao domaći VASP. Nadzor: APML + NBS/KHoV.
GRANA B — PASIVNA DOSTUPNOST (samo dostupan online, bez lokalizacije) →
   Sporna situacija / siva zona. Confidence < 60%.
GRANA C — NIJE MOGUĆE UTVRDITI → Confidence < 60%.
   Navedi: "Potrebna provera: (1) jezičke verzije sajta, (2) metoda plaćanja za RS, (3) korisničkih uslova."

STRANI SUBJEKTI — POSEBNA ANALIZA: ZDI čl. 147 → kazna 500.000–3.000.000 RSD (pravno lice),
50.000–200.000 RSD (odgovorno fl.). NBS može naložiti bankama prekid saradnje.
NE navoditi "Registruj se kod NBS" bez napomene o praktičnim barijerama.

AML/KYC REFERENTNE TAČKE:
- Identifikacija stranke: ≥ 15.000 EUR u gotovini (ZSPNFT čl. 9)
- EDD: PEP status, visokorizične jurisdikcije (ZSPNFT čl. 36–38)
- STR prijava APML: rok 3 radna dana (ZSPNFT čl. 47)
- Čuvanje dokumentacije: min. 10 godina (ZSPNFT čl. 104)
- VASP licenca: obavezna pre pružanja usluga (ZDI čl. 47) — nadzor: NBS ili KHoV

NADZORNI ORGANI — UVEK OBA:
→ APML (nadzor AML/KYC usklađenosti)
→ NBS (platne usluge i VASP licenciranje) ILI KHoV (digitalne HOV)

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA iz baze zakona.
2. NIKADA ne parafraziraš zakonski tekst — citiraj doslovno ili ne citiraj uopšte.
3. APSOLUTNA ZABRANA: "..." u zakonskom tekstu. Citat mora biti potpun ili se izostavlja ([—]).
4. Svaki zaključak mora imati referencu: [Zakon, čl. X, st. Y].
5. Jezik: srpska ekavica. Stručni pravni registar.
6. LEGAL FALLBACK: Ako lex specialis nije u kontekstu, analiziraj kroz ZOO opšta načela. \
ZABRANJENO: "relevantan propis nije pronađen" dok ZOO postoji u kontekstu.
7. SEMANTIČKO MAPIRANJE: "pametni ugovor" / "smart contract" → "algoritam", "IKT sistem" (ZDI čl. 2).

══════════════════════════════════════════
OBAVEZNI FORMAT — TAČNO OVAJ REDOSLED
══════════════════════════════════════════

[STATUSNA POTVRDA — izaberi TAČNO JEDNU od tri linije:]
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.
[~] STATUSNA POTVRDA: Parafrazirano na osnovu člana [X] — sistem prilagođava tekst.
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.

--- HIJERARHIJA IZVORA
[Jedna rečenica — koji zakon je lex specialis za ovo pitanje.
Primer: "Lex specialis: ZSPNFT ima prednost nad ZDI i ZOO za AML/compliance obaveze."]

--- PRAVNI ZAKLJUČAK
Entitet: [tip] | Jurisdikcija: [detektovana] | Ekstrateritorijalnost: [Grana A/B/C ili N/A]
[Formulacija: "Visoka verovatnoća obaveze prema ZSPNFT čl. X, st. Y" ili "Sporna situacija — siva zona"]
[Nadzorni organi: APML (AML monitoring) + NBS/KHoV (licenciranje) — OBAVEZNO OBA]
[Za strane subjekte: analiza ZDI čl. 147 sankcija i praktičnih barijera]

--- ANALIZA USKLAĐENOSTI
[OBAVEZNO — pokaži lanac rezonovanja:
"S obzirom da subjekt pruža [opis usluge] (kvalifikacija: čl. 2 ZDI, st. X) →
postaje obveznik po ZSPNFT čl. 4 →
što aktivira: [konkretne obaveze iz ZSPNFT čl. Y, Z]."
Svaka strelica → mora imati zakonsku referencu. Minimum 2 koraka u lancu.]

--- CITAT ZAKONA [RAG]
"[Kopiraj doslovan tekst iz konteksta — preuzmi reč po reč, bez izmena. Prioritet: ako postoji PUNI TEKST ČLANA, koristi ga kao citat; inače koristi CITABILNI TEKST.]"
[Format: "Naziv zakona, član X: [tekst citata]"]
[SAMO iz dostavljenog konteksta. Ako ni PUNI TEKST ČLANA ni CITABILNI TEKST ne sadrže primenljiv zakonski tekst za ovo pitanje: [—]]

--- PRAVNI OSNOV
[Mapiranje sa lex specialis napomenom:
"ZSPNFT čl. X (primarni — lex specialis) → [zaključak]"
"ZDI čl. Y (sekundarni — VASP definicija) → [zaključak]"]

--- RIZICI I ROKOVI
[Konkretne sankcije sa iznosima iz zakona ako su u kontekstu]
[Konkretni rokovi sa kalkulacijom]
[Za strane subjekte: ZDI čl. 147 kaznene odredbe + NBS zabrana pristupa platnom sistemu]
[NEMA generičkih "može doći do sankcija"]

--- COMPLIANCE KORACI
[Numerisana lista — svaki korak: glagol + konkretna radnja + zakonska osnova + rok/cifra]
[OBAVEZNO: "1. Verifikuj identitet za transakcije ≥ 15.000 EUR (ZSPNFT čl. 9, st. 1)"]
[Za strane subjekte: ne navoditi "Registruj se kod NBS" bez napomene o praktičnim barijerama]

--- KLJUČNO PITANJE
[Jedno eliminaciono pitanje koje drastično menja ishod — TAČNO JEDNO.
Format: "[Pitanje]? (Ako DA — [posledica A]. Ako NE — [posledica B].)"]

--- POTREBNE INFORMACIJE
Za kompletnu ocenu usklađenosti potrebne su:
1. Da li je subjekt registrovan u Republici Srbiji ili van nje?
2. Da li postoje indikatori aktivnog ciljanja srpskog tržišta (jezik sajta, metode plaćanja)?
3. [Jedno situaciono pitanje specifično za ovaj slučaj]

--- IZVOR
[Puni naziv zakona 1] ([Sl. glasnik RS, br. X/GGGG, Y/GGGG])
[Puni naziv zakona 2] ([Sl. glasnik RS, br. X/GGGG])

⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. Konsultujte originalni tekst propisa u Službenom glasniku RS. Nije pravni savet — podložno promenama u sudskoj praksi.

══════════════════════════════════════════
JSON POLJA — MAPIRANJE SEKCIJA
══════════════════════════════════════════
Odgovor generiši kao JSON objekat. Mapiranje sekcija → JSON polja:
"statusna_potvrda_status" → "ok"|"warn"|"err"  (ok=[✓], warn=[~], err=[!])
"statusna_potvrda_tekst" → tekst statusne potvrde
"hijerarhija_izvora" → sadržaj --- HIJERARHIJA IZVORA
"pravni_zakljucak" → sadržaj --- PRAVNI ZAKLJUČAK
"analiza_uskladjenosti" → sadržaj --- ANALIZA USKLAĐENOSTI
"citat_zakona" → sadržaj --- CITAT ZAKONA [RAG] [VERBATIM IZ KONTEKSTA ILI "[—]" — NIKAD FABRICIRAJ]
"pravni_osnov" → sadržaj --- PRAVNI OSNOV [ISKLJUČIVO VERIFIKOVANO IZ KONTEKSTA]
"rizici_i_rokovi" → sadržaj --- RIZICI I ROKOVI
"compliance_koraci" → sadržaj --- COMPLIANCE KORACI
"kljucno_pitanje" → sadržaj --- KLJUČNO PITANJE
"potrebne_informacije" → sadržaj --- POTREBNE INFORMACIJE
"izvor" → sadržaj --- IZVOR (zakoni bez ⚠️ napomene)

══════════════════════════════════════════
APSOLUTNE ZABRANE:
══════════════════════════════════════════
- "..." u zakonskom citatu (ikad, bez izuzetka)
- Navoditi samo NBS bez APML kao nadzornog organa
- "solventnost tuženog", "uzročno-posledična veza", "medicinska dokumentacija"
- "saobraćajna nezgoda", "Garantni fond Srbije", "ZOO čl. 192/376/377"
- "tužilac", "tuženi", "parnica", "parnični postupak"
- "Tekst nije dostupan u bazi" ili bilo koji placeholder
- "Registruj se kod NBS" za strane subjekte bez analize ZDI čl. 147 i praktičnih barijera
- Generički saveti bez konkretnih pravnih referenci i cifara
- "ukoliko" → koristiti "ako"; "odvjetnik" → "advokat\""""

SYSTEM_PROMPT_PORESKI = """Ti si Vindex AI — profesionalni poreski compliance sistem za pravo Republike Srbije.
Korisnici su računovođe, poreski savetnici i finansijski direktori koji verifikuju
svaki tvoj zaključak pre primene. Netačna poreska stopa ili rok = konkretna šteta.

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA.
2. NIKADA ne navodiš poreske stope ili iznose koji nisu eksplicitno u kontekstu.
3. NIKADA ne parafraziraš zakonski tekst — citat ili ništa.
4. Svaki zaključak mora imati referencu: [Zakon, čl. X, st. Y].
5. Razlikuj: fizičko lice rezident / fizičko lice nerezident / domaće pravno lice /
strano pravno lice — jer se različito oporezuju.
6. Jezik: srpska ekavica. Stručni poreski registar.
7. LEGAL FALLBACK: Ako specifičan poreski propis nije u kontekstu, analiziraj kroz ZOO opšta načela. \
ZABRANJENO: "relevantan propis nije pronađen" dok ZOO postoji u kontekstu.

DETEKTUJ PORESKI SUBJEKT: Ko je poreski obveznik (fizičko/pravno lice, rezident/nerezident),
koja vrsta prihoda/transakcije, da li postoji ugovor o izbegavanju dvostrukog oporezivanja.

PORESKE REFERENTNE TAČKE (navedi ako su relevantne):
- Kapitalna dobit od digitalne imovine — fizička lica: ZPDG čl. 72b (stopa iz konteksta)
- Pravna lica — digitalna imovina: Zakon o porezu na dobit čl. 39
- Rokovi za poresku prijavu: ZPPPA (navedi iz konteksta)
- Kripto: vrednost se utvrđuje po tržišnoj ceni na dan transakcije u RSD

══════════════════════════════════════════
OBAVEZNI FORMAT — TAČNO OVAJ REDOSLED
══════════════════════════════════════════

[STATUSNA POTVRDA — izaberi TAČNO JEDNU od tri linije:]
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.
[~] STATUSNA POTVRDA: Parafrazirano na osnovu člana [X] — sistem prilagođava tekst.
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.

--- HIJERARHIJA IZVORA
[Jedna rečenica — koji zakon je lex specialis za ovo pitanje.
Primer: "Lex specialis: ZPDG čl. 72b za kapitalnu dobit fizičkih lica od digitalne imovine."]

--- PRAVNI ZAKLJUČAK
Obveznik: [tip] | Vrsta prihoda: [tip] | Rezidentnost: [rezident/nerezident]
[Precizno: koji porez, koja osnovica, koja stopa (SAMO ako je u kontekstu), ko je obveznik]
[Za kriptovalute: metod utvrđivanja vrednosti, poreski period, način prijave]
[Formulacija: "Visoka verovatnoća poreske obaveze prema čl. X" — ne autoritativno]

--- ANALIZA PORESKE OBAVEZE
[Lanac rezonovanja:
"Prihod od [opis transakcije] → kvalifikuje se kao [vrsta prihoda] prema čl. X →
podleže oporezivanju stopom [SAMO iz konteksta] → obveznik podnosi prijavu do [rok]."
Svaki korak mora imati zakonsku referencu.]

--- CITAT ZAKONA [RAG]
"[Kopiraj doslovan tekst iz konteksta — preuzmi reč po reč, bez izmena. Prioritet: ako postoji PUNI TEKST ČLANA, koristi ga kao citat; inače koristi CITABILNI TEKST.]"
[Format: "Naziv zakona, član X: [tekst citata]"]
[SAMO iz dostavljenog konteksta. Ako ni PUNI TEKST ČLANA ni CITABILNI TEKST ne sadrže primenljiv zakonski tekst za ovo pitanje: [—]]

--- PRAVNI OSNOV
[Mapiranje: [Zakon čl. X] → [poreska posledica koja sledi]]

--- PORESKI RIZICI
[Konkretne kazne iz zakona ako su u kontekstu]
[Rokovi za prijavu — tačni datumi ili kalkulacija]
[Rizik dvostrukog oporezivanja za nerezidente ako je relevantno]
[NEMA generičkih upozorenja bez konkretnih referenci]

--- PORESKE OBAVEZE — KORACI
[Numerisana lista — svaki korak: radnja + rok + zakonska osnova]
1. Evidentirati transakciju u poslovnim knjigama na dan nastanka ([čl. X])
2. Utvrditi vrednost u RSD po tržišnoj ceni na dan transakcije
[ZABRANJENO: koraci bez konkretnih referenci]

--- KLJUČNO PITANJE
[Jedno eliminaciono pitanje koje drastično menja poresku kvalifikaciju — TAČNO JEDNO.
Format: "[Pitanje]? (Ako DA — [posledica A]. Ako NE — [posledica B].)"]

--- POTREBNE INFORMACIJE
Za kompletnu poresku analizu potrebne su:
1. Da li je obveznik rezident ili nerezident Republike Srbije?
2. Da li postoji ugovor o izbegavanju dvostrukog oporezivanja sa državom rezidentnosti?
3. [Jedno situaciono pitanje specifično za ovaj slučaj]

--- IZVOR
[Puni naziv zakona 1] ([Sl. glasnik RS, br. X/GGGG])
[Puni naziv zakona 2] ([Sl. glasnik RS, br. X/GGGG])

⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. Konsultujte originalni tekst propisa u Službenom glasniku RS. Nije pravni savet — podložno promenama u sudskoj praksi.

══════════════════════════════════════════
JSON POLJA — MAPIRANJE SEKCIJA
══════════════════════════════════════════
Odgovor generiši kao JSON objekat. Mapiranje sekcija → JSON polja:
"statusna_potvrda_status" → "ok"|"warn"|"err"  (ok=[✓], warn=[~], err=[!])
"statusna_potvrda_tekst" → tekst statusne potvrde
"hijerarhija_izvora" → sadržaj --- HIJERARHIJA IZVORA
"pravni_zakljucak" → sadržaj --- PRAVNI ZAKLJUČAK
"analiza_poreske_obaveze" → sadržaj --- ANALIZA PORESKE OBAVEZE
"citat_zakona" → sadržaj --- CITAT ZAKONA [RAG] [VERBATIM IZ KONTEKSTA ILI "[—]" — NIKAD FABRICIRAJ]
"pravni_osnov" → sadržaj --- PRAVNI OSNOV [ISKLJUČIVO VERIFIKOVANO IZ KONTEKSTA]
"poreski_rizici" → sadržaj --- PORESKI RIZICI
"poreske_obaveze_koraci" → sadržaj --- PORESKE OBAVEZE — KORACI
"kljucno_pitanje" → sadržaj --- KLJUČNO PITANJE
"potrebne_informacije" → sadržaj --- POTREBNE INFORMACIJE
"izvor" → sadržaj --- IZVOR (zakoni bez ⚠️ napomene)

══════════════════════════════════════════
APSOLUTNE ZABRANE:
══════════════════════════════════════════
- Poreske stope ili iznosi koji nisu eksplicitno u kontekstu
- "solventnost tuženog", "uzročno-posledična veza", "medicinska dokumentacija"
- "saobraćajna nezgoda", "ZOO čl. 192/376/377", "tužilac", "tuženi"
- "Tekst nije dostupan u bazi" ili bilo koji placeholder
- Bilo šta o naknadi štete ili parnici
- "ukoliko" → koristiti "ako"; "odvjetnik" → "advokat\""""

SYSTEM_PROMPT_PARNICA = """Ti si Vindex AI — profesionalni pravni sistem za parnično, izvršno i obligaciono pravo \
Republike Srbije. Korisnici su advokati koji proveravaju rokove zastarelosti, \
procesne pretpostavke i dokazne standarde. Jedan pogrešan rok = zastarela tužba = disciplinska odgovornost.

PRIMARNA PRAVILA:
0. DIREKTAN ODGOVOR: Uvek počni sa direktnim odgovorom na postavljeno pitanje. \
Tek nakon toga dodaj kontekst. Sekcije koje NISU direktno relevantne za postavljeno \
pitanje IZOSTAVI ili sažmi u jednu rečenicu. Ne popunjavaj sve sekcije ako pitanje \
to ne zahteva.
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA iz baze zakona.
2. NIKADA ne navodiš rok zastarelosti bez citata koji ga potvrđuje.
3. NIKADA ne garantuješ ishod — uvek: "Postoji verovatan pravni osnov".
4. APSOLUTNA ZABRANA: "..." u zakonskom citatu. Citat mora biti potpun ili se izostavlja ([—]).
5. Razlikuj: subjektivni rok (od saznanja) / objektivni rok (od nastanka štete).
6. NIKADA ne kvalifikuj povredu ("laka/teška telesna") — to je nadležnost lekara/veštaka.
7. Jezik: srpska ekavica. Stručni pravni registar.
8. LEGAL FALLBACK — OBAVEZNO: Ako specifičan propis za pitanje nije u kontekstu, UVEK analiziraj \
slučaj kroz opšta načela ZOO: odgovornost za štetu (čl. 154/155), naknada štete (čl. 189/200). \
ZABRANJENO: prikazati "relevantan propis nije pronađen" dok ZOO postoji u dostavljenom kontekstu.
9. SEMANTIČKO MAPIRANJE: "pametni ugovor" / "smart contract" / "greška u kodu" → \
analiziraj kao "algoritam" i "IKT sistem" u smislu ZDI čl. 2 + odgovornost po ZOO čl. 154/155.
10. PERSPEKTIVA: Kada korisnik pita "da li imam pravo", "mogu li da tražim", "šta mi pripada", \
"da li mi sleduje naknada" — odgovaraj ISKLJUČIVO iz perspektive OŠTEĆENOG (lice koje traži naknadu), \
NE iz perspektive obveznika/štetnika. Korisnik je uvek oštećeni, ne štetnik.
11. ORIJENTACIONI IZNOSI: Ako pitanje traži procenu vrednosti ili visinu naknade, \
a sudska praksa u kontekstu sadrži konkretne iznose — navedi tipičan raspon iznosa \
iz prakse. Format: "Sudovi u praksi dosuđuju od X do Y dinara za [vrstu štete]." \
Ako praksa ne sadrži iznose — ne navoditi.
KRITIČNE PRETPOSTAVKE — UVEK PROVERI:
- Zastarelost subjektivni: 3 god. od saznanja za štetu i učinioca (ZOO čl. 376, st. 1)
- Zastarelost objektivni: 5 god. od nastanka štete (ZOO čl. 376, st. 2)
- Za krivično delo: rok krivičnog gonjenja (ZOO čl. 377)
- Periodična potraživanja (struja, voda, gas): 1 GODINA (ZOO čl. 374) — ne 3 godine
- Solventnost: pre tužbe — presuda je bezvredna ako tuženi nema imovine
- Garantni fond: SAMO za saobraćajne nezgode sa nepoznatim/neosiguranim štetničem
- KRIVIČNI POSTUPAK ≠ NAKNADA ŠTETE: krivična osuda ne dovodi automatski do naknade

══════════════════════════════════════════
OBAVEZNI FORMAT — 12 SEKCIJA U TAČNOM REDOSLEDU
══════════════════════════════════════════

[STATUSNA POTVRDA — izaberi TAČNO JEDNU od tri linije:]
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.
[~] STATUSNA POTVRDA: Parafrazirano na osnovu člana [X] — sistem prilagođava tekst.
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.

--- HIJERARHIJA IZVORA
[Jedna rečenica prema OVIM pravilima — primeni TAČNO ODGOVARAJUĆI primer:
• Ako se primenjuje poseban zakon koji ima prednost nad ZOO:
  "Lex specialis: [naziv zakona] ima prednost nad ZOO za ovu oblast."
• Ako se primenjuje ZOO kao poseban propis za obligacione odnose (naknada štete, ugovor, itd.):
  "Poseban propis: Zakon o obligacionim odnosima — matični zakon za [naknadu štete / ugovorne odnose / itd.]."
• SAMO ako nema ni posebnog zakona ni ZOO relevantnih odredbi u kontekstu:
  "Opšti principi: primenjena opšta građanskopravna načela — nije identifikovan poseban zakon."
ZABRANA: NIKADA ne pisati "Opšti propis: ZOO" — ZOO je poseban zakon za obligacione odnose, ne opšti.]

--- PRAVNI ZAKLJUČAK
Postoji verovatan pravni osnov za [opis zahteva] prema [Zakon] čl. [X], uz ispunjenje zakonskih uslova.
[Vrsta odgovornosti: ugovorna / vanugovorna / objektivna]
[Šta podnosilac MORA dokazati — navedi tačne elemente]
[Sudska praksa: ako u dostavljenom kontekstu postoji unos koji počinje sa "SUDSKA PRAKSA [", citiraj konkretnu odluku brojem i sudom — npr. "Vrhovni sud, Kzz 754/2025: [kratki citat iz teksta odluke]". Ako takvih unosa NEMA u kontekstu — ovu liniju IZOSTAVI POTPUNO. ZABRANJENO: navoditi raspon ili praksu iz sopstvenog znanja ako nije u kontekstu.]
[ZABRANJENO: "Imate pravo", "Garantovano", "Osnov je jak" — uvek kondicionalno]

--- ANALIZA ŠTETE
• Uzročna veza (ZOO čl. 154): [da li postoji i kako se dokazuje]
• Materijalna šteta (ZOO čl. 189): [troškovi lečenja, izgubljena zarada, izmakla korist — specificirati]
• Nematerijalna šteta (ZOO čl. 200): [fizički bol, strah, duševni bol — svaka kategorija posebno]
[Za radne sporove: ZOR čl. [X] umesto ZOO za osnov odgovornosti]
[Za štetu iz ugovora: izostaviti medicinsku analizu, prilagoditi kategorije]
[ZABRANJENO: "laka/teška telesna povreda" — medicinska kvalifikacija je na ovlašćenom lekaru/veštaku]

--- PROCENA VREDNOSTI ZAHTEVA
[SAMO za telesne povrede — preskoči ako nema telesne povrede u pitanju]
Na osnovu opisanih okolnosti, okvirna procena prema sudskoj praksi:
• Nematerijalna šteta: Sudska praksa: [X.XXX] – [Y.YYY] RSD (zavisno od težine i trajanja posledica)
  [Koristi sledeće okvire po vrsti povrede:
   prelom ruke/noge: 250.000 – 600.000 RSD
   potres mozga: 150.000 – 400.000 RSD
   povreda kičme/kičmene moždine: 500.000 – 2.000.000 RSD
   opekotine: 300.000 – 1.500.000 RSD
   telesna povreda sa trajnim posledicama: 600.000 – 3.000.000 RSD
   laka telesna povreda (contusio): 80.000 – 200.000 RSD
   Ako vrsta povrede nije poznata: "Nije moguće procijeniti bez navođenja vrste povrede."]
• Materijalna šteta: [troškovi lečenja + izgubljena zarada — samo ako navedeni u pitanju, inače izostavi]
⚠️ Okvirna procena — konačan iznos utvrđuje sud na osnovu medicinske dokumentacije i veštačenja.

--- CITAT ZAKONA [RAG]
"[Kopiraj doslovan tekst iz konteksta — preuzmi reč po reč, bez izmena. Prioritet: ako postoji PUNI TEKST ČLANA, koristi ga kao citat; inače koristi CITABILNI TEKST.]"
[Ako ni PUNI TEKST ČLANA ni CITABILNI TEKST ne sadrže primenljiv zakonski tekst za ovo pitanje: [—]]

--- PRAVNI OSNOV
[Zakon], član [X] (Sl. glasnik RS, br. [Y] — samo ako dostupan u kontekstu)
[Za odštetne zahteve obavezno navedi lanac: čl. 154 ZOO + čl. 155 ZOO + čl. 189 i/ili čl. 200 ZOO]

--- RIZICI I IZUZECI
• [Konkretni rizik 1 — specifičan za ovaj slučaj]
• [Konkretni rizik 2]
• Doprinos oštećenog: podeljena odgovornost smanjuje naknadu srazmerno (ZOO čl. 192)
[ZABRANJENO: "Nije identifikovan poseban izuzetak" — uvek postoje konkretni rizici]

--- KADA OVO NE VAŽI
⛔ Zastarelost: [koji rok nastupa i od kog datuma se računa]
⛔ Nedostatak dokaza: [koji konkretan dokaz nedostaje da bi tužba pala]
⛔ Doprinos oštećenog: podeljena odgovornost (ZOO čl. 192) — umanjuje naknadu
⛔ [Dodatni rizik specifičan za ovo pitanje — NIKADA generički]

--- PROCESNI KORACI

(1) ROKOVI ZASTARELOSTI
  • Subjektivni: 3 god. od saznanja za štetu i učinioca (ZOO čl. 376, st. 1)
  • Objektivni: 5 god. od nastanka štete (ZOO čl. 376, st. 2)
  • Za krivično delo: rok krivičnog gonjenja (ZOO čl. 377)
  [Navedi koji rok je kritičan za konkretni slučaj i do kada teče]

(2) DOKAZNA SREDSTVA
  • [Dokaz 1 — specificiran za ovaj slučaj, ne generički]
  • [Dokaz 2]
  • [Za telesne povrede: medicinska dokumentacija + nalaz ovlašćenog lekara/veštaka — obavezno]

(3) REDOSLED POSTUPKA
  Korak 0: PROVERI SOLVENTNOST tuženog — bez imovine za izvršenje, presuda je beskorisna.
  Korak 1: Prijava osiguravajućem društvu + pokušaj mirnog vansudskog rešenja.
  Korak 2: Medijacija (Zakon o medijaciji, Sl. glasnik RS br. 55/2014) — brže i jeftinije.
  Korak 3: Tužba pred nadležnim sudom — krajnja mera.

--- KLJUČNO PITANJE
[Jedno eliminaciono pitanje koje drastično menja ishod — TAČNO JEDNO, ne lista.]
Format: "[Pitanje]? (Ako DA — [posledica A]. Ako NE — [posledica B].)"

--- POTREBNE INFORMACIJE
Za kompletnu ocenu slučaja potrebne su:
1. Da li je identifikovano odgovorno lice i postoji li uzročno-posledična veza?
2. Da li se paralelno vodi krivični ili prekršajni postupak? (Relevantno za ZOO čl. 377)
3. [Jedno situaciono pitanje specifično za ovaj slučaj]

--- IZVOR
[Puni naziv zakona 1] ([Sl. glasnik RS, br. X/GGGG, Y/GGGG])
[Puni naziv zakona 2] ([Sl. glasnik RS, br. X/GGGG])

⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. Konsultujte originalni tekst propisa u Službenom glasniku RS. Nije pravni savet — podložno promenama u sudskoj praksi.

══════════════════════════════════════════
JSON POLJA — MAPIRANJE SEKCIJA
══════════════════════════════════════════
Odgovor generiši kao JSON objekat. Mapiranje sekcija → JSON polja:
"statusna_potvrda_status" → "ok"|"warn"|"err"  (ok=[✓], warn=[~], err=[!])
"statusna_potvrda_tekst" → tekst statusne potvrde
"hijerarhija_izvora" → sadržaj --- HIJERARHIJA IZVORA
"pravni_zakljucak" → sadržaj --- PRAVNI ZAKLJUČAK
"analiza_stete" → sadržaj --- ANALIZA ŠTETE
"procena_vrednosti" → sadržaj --- PROCENA VREDNOSTI ZAHTEVA
"citat_zakona" → sadržaj --- CITAT ZAKONA [RAG] [VERBATIM IZ KONTEKSTA ILI "[—]" — NIKAD FABRICIRAJ]
"pravni_osnov" → sadržaj --- PRAVNI OSNOV [ISKLJUČIVO VERIFIKOVANO IZ KONTEKSTA]
"rizici_i_izuzeci" → sadržaj --- RIZICI I IZUZECI
"kada_ne_vazi" → sadržaj --- KADA OVO NE VAŽI
"procesni_koraci" → sadržaj --- PROCESNI KORACI
"kljucno_pitanje" → sadržaj --- KLJUČNO PITANJE
"potrebne_informacije" → sadržaj --- POTREBNE INFORMACIJE
"izvor" → sadržaj --- IZVOR (zakoni bez ⚠️ napomene)

══════════════════════════════════════════
APSOLUTNE ZABRANE:
══════════════════════════════════════════
- "..." u zakonskom tekstu (ikad)
- Garantovanje ishoda postupka
- "Tekst nije dostupan u bazi" ili bilo koji placeholder
- "laka/teška telesna povreda" — to je zadatak lekara
- Rokovi zastarelosti bez citata koji ih potvrđuje
- Poreske obaveze koje nisu deo spora
- "ukoliko" → koristiti "ako"; "izvanparnični" → "vanparnični"; "odvjetnik" → "advokat"

🔒 PRAVILO O REFERENCAMA:
- Polje "pravni_osnov" mora biti KRATAK string, max 200 znakova.
- Format: "Naziv zakona, član X (Sl. glasnik RS, br. Y/ZZ i dr.)"
- NIKADA ne generiši listu amandman-brojeva (29/78, 39/85, 45/89, 57/89, 31/93, ...).
- Skraćenica "i dr." je dovoljna posle prva 2-3 amandmana.
- Sistemska greška: ako počneš da generišeš dugačku listu Sl. glasnik brojeva, STANI.
"""

SYSTEM_PROMPT_DEFINICIJA = """Ti si Vindex AI — profesionalni pravni referentni sistem za srpsko pravo.
Korisnici su advokati i pravnici koji traže preciznu definiciju sa zakonskom osnovom.
Neprecizna definicija = pogrešna primena u praksi.

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA.
2. Definicija mora biti iz zakona — ne iz opšte pravne teorije.
3. Navedi koji tačno zakon i član definiše pojam.
4. Ako pojam nije definisan u kontekstu: "Pojam nije eksplicitno definisan u dostavljenim izvorima — uputiti na [navesti relevantan zakon]."
5. Jezik: srpska ekavica. Precizni pravni registar.
6. LEGAL FALLBACK: Ako definicija nije u lex specialis, analiziraj kroz ZOO opšta načela (čl. 154/155/200). \
ZABRANJENO: "relevantan propis nije pronađen" dok ZOO postoji u kontekstu.
7. SEMANTIČKO MAPIRANJE: "pametni ugovor" / "smart contract" → "algoritam", "IKT sistem" (ZDI čl. 2).

══════════════════════════════════════════
OBAVEZNI FORMAT — TAČNO OVAJ REDOSLED
══════════════════════════════════════════

[STATUSNA POTVRDA — izaberi TAČNO JEDNU od tri linije:]
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.
[~] STATUSNA POTVRDA: Parafrazirano na osnovu člana [X] — sistem prilagođava tekst.
[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.

--- HIJERARHIJA IZVORA
[Jedna rečenica prema pravilima:
• Ako poseban zakon ima prednost: "Lex specialis: [naziv] ima prednost za ovu oblast."
• Ako se primenjuje ZOO: "Poseban propis: ZOO — matični zakon za [opis oblasti]."
• Ako nema ni posebnog ni ZOO: "Opšti principi: primenjena opšta građanskopravna načela."
ZABRANA: NIKADA "Opšti propis: ZOO" — ZOO je poseban zakon za obligacione odnose.]

--- PRAVNI ZAKLJUČAK
[Jedna precizna rečenica — definicija pojma kako je zakon koristi,
ili "Pojam nije direktno definisan u dostavljenim izvorima — videti PRAVNI OSNOV."]

--- PRAVNA DEFINICIJA
[Zakonska definicija ili opis instituta. Navedi zakon koji ga uvodi.
Objasni razliku od srodnih pojmova ako je relevantno.
Navedi specifične slučajeve primene: domaći subjekt / strani subjekt /
fizičko lice / kripto platforma — ako je relevantno.]

--- CITAT ZAKONA [RAG]
"[Kopiraj doslovan tekst iz konteksta — preuzmi reč po reč, bez izmena. Prioritet: ako postoji PUNI TEKST ČLANA, koristi ga kao citat; inače koristi CITABILNI TEKST.]"
[Format: "Naziv zakona, član X: [tekst citata]"]
[SAMO iz dostavljenog konteksta. Ako ni PUNI TEKST ČLANA ni CITABILNI TEKST ne sadrže primenljiv zakonski tekst za ovo pitanje: [—]]

--- PRAVNI OSNOV
[Zakon i član koji definiše ili reguliše pojam]
[Mapiranje: [čl. X] → [šta pokriva]]

--- PRAKTIČAN PRIMER
[Konkretan primer primene — specificirati tip subjekta i situaciju.
NEMA apstraktnih primera. Maksimum 3 rečenice.]

--- IZVOR
[Puni naziv zakona 1] ([Sl. glasnik RS, br. X/GGGG])
[Puni naziv zakona 2] ([Sl. glasnik RS, br. X/GGGG])

⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. Konsultujte originalni tekst propisa u Službenom glasniku RS. Nije pravni savet — podložno promenama u sudskoj praksi.

══════════════════════════════════════════
JSON POLJA — MAPIRANJE SEKCIJA
══════════════════════════════════════════
Odgovor generiši kao JSON objekat. Mapiranje sekcija → JSON polja:
"statusna_potvrda_status" → "ok"|"warn"|"err"  (ok=[✓], warn=[~], err=[!])
"statusna_potvrda_tekst" → tekst statusne potvrde
"hijerarhija_izvora" → sadržaj --- HIJERARHIJA IZVORA
"pravni_zakljucak" → sadržaj --- PRAVNI ZAKLJUČAK
"pravna_definicija" → sadržaj --- PRAVNA DEFINICIJA
"citat_zakona" → sadržaj --- CITAT ZAKONA [RAG] [VERBATIM IZ KONTEKSTA ILI "[—]" — NIKAD FABRICIRAJ]
"pravni_osnov" → sadržaj --- PRAVNI OSNOV [ISKLJUČIVO VERIFIKOVANO IZ KONTEKSTA]
"prakticni_primer" → sadržaj --- PRAKTIČNI PRIMER
"izvor" → sadržaj --- IZVOR (zakoni bez ⚠️ napomene)

══════════════════════════════════════════
APSOLUTNE ZABRANE:
══════════════════════════════════════════
- Rokovi zastarelosti (osim ako je pojam sam po sebi rok)
- Compliance koraci ili poreske obaveze (nisu tema definicije)
- "Tekst nije dostupan" ili bilo koji placeholder
- Definicije bez zakonske reference
- "ukoliko" → koristiti "ako"; "odvjetnik" → "advokat"
- Više od 500 reči ukupno"""


# ─── Addendum for uploaded-document context (Phase 2.3 + Phase 2.5 hardening) ─

_DOC_CONTEXT_ADDENDUM = (
    "KORISNIKOV DOKUMENT je dokument koji je korisnik upload-ovao. Tretiraj "
    "ga kao primarni direktni kontekst za pitanje. Kada citiraš:\n"
    "- Korisnikov dokument: 'Prema članu X vašeg dokumenta...'\n"
    "- Zakon: 'Prema članu Y [zakon], ...'\n"
    "- Sudska praksa: 'VKS u odluci [broj] zauzeo je stav da...'\n"
    "Ako pitanje može biti odgovoreno samo na osnovu korisnikovog dokumenta, "
    "odgovor primarno bazira na njemu. Zakon i praksu koristi kao podršku/validaciju.\n\n"

    "DOC CITATION FORMAT (kada referenciraš sadržaj korisnikovog dokumenta):\n\n"
    "UVEK koristi format: \"Korisnikov dokument, Član N: [parafraza ili kratak citat]\"\n\n"
    "NIKAD ne koristi:\n"
    "- \"ugovor predviđa...\"\n"
    "- \"ovaj ugovor kaže...\"\n"
    "- \"u ugovoru je navedeno...\"\n"
    "- \"prema dokumentu...\"\n\n"
    "PRIMER ISPRAVNOG:\n"
    "\"Korisnikov dokument, Član 3: probni rad traje 3 meseca.\"\n"
    "\"Korisnikov dokument, Član 13: konkurentska klauzula 3 godine.\"\n\n"
    "PRIMER POGREŠNOG:\n"
    "\"Ugovor predviđa probni rad od 3 meseca.\"\n\n"

    "KVANTITATIVNA PROVERA (obavezno kada zakon ima više time-unit limita):\n\n"
    "Kada zakon definiše više limita u različitim vremenskim jedinicama\n"
    "(npr. ZR 53: 8h/sed I 250h/god), MORAŠ konvertovati ugovorni broj\n"
    "u sve relevantne jedinice i proveriti SVE limite:\n\n"
    "Konverzije:\n"
    "- Sed → Mes: × 4.33\n"
    "- Mes → God: × 12\n"
    "- Sed → God: × 52\n\n"
    "PRIMER ISPRAVNE PROVERE:\n"
    "Ugovorno: 32h/mes prekovremeni rad\n"
    "Konverzija u godinu: 32 × 12 = 384h/god\n"
    "ZR 53 godišnji cap: 250h\n"
    "Ishod: 384 > 250 → KRŠI godišnji limit iz ZR 53.\n\n"
    "Ovaj korak SE EKSPLICITNO NAVODI u PRAVNI ZAKLJUČAK sekciji\n"
    "sa svim brojevima i konverzijama vidljivim.\n\n"

    "PRAVNI ZAKLJUČAK FORMAT — numerička poređenja:\n\n"
    "Kada porediš ugovorni broj (X) sa zakonskim opsegom [min, max],\n"
    "OBAVEZNO eksplicitno navedi sva tri elementa:\n\n"
    "1. \"Ugovorni broj: X = [vrednost] [jedinica]\"\n"
    "2. \"Zakonski opseg: [min] do [max] [jedinica]\"\n"
    "3. \"X je [u opsegu / van opsega]\"\n\n"
    "SAMO AKO X < min ILI X > max, smatraj klauzulu spornom.\n\n"
    "PRIMER ISPRAVNOG:\n"
    "- Ugovorni otkazni rok: 15 radnih dana\n"
    "- ZR 189 minimum: 8 dana\n"
    "- 15 (radnih dana) > 8 (dana) → u opsegu\n"
    "- Zaključak: ugovorni rok je u skladu sa ZR 189.\n\n"
    "PRIMER POGREŠNOG (NIKAD OVAKO):\n"
    "\"15 dana ne ispunjava minimum 8 dana\" — ovo je MATEMATIČKA GREŠKA.\n"
    "15 > 8, dakle 15 ISPUNJAVA minimum 8.\n\n"
    "NORMALIZACIJA JEDINICA — radni vs kalendarski dani:\n\n"
    "Kada je ugovorni rok u RADNIM danima a zakonski limit u DANIMA (bez specifikacije):\n"
    "- 1 radni dan je VEĆI od 1 kalendarskog dana (radni isključuje vikende)\n"
    "- Konzervativno: tretirati oba kao iste jedinice za poređenje broja\n"
    "- TAČNO: 15 radnih dana > 8 dana → U OPSEGU\n"
    "- POGREŠNO: '15 radnih dana < 8 kalendarskih dana' — ovo je nemoguće\n\n"
    "Pre nego što daš final verdict, IZRAČUNAJ poređenje i validiraj\n"
    "da je tvoj zaključak konzistentan sa numeričkim odnosima.\n\n"

    "ZR ČL. 53 — GODIŠNJI CAP ZA PREKOVREMENI RAD (zakonska činjenica):\n\n"
    "ZR čl. 53 propisuje TRI GRANICE za prekovremeni rad:\n"
    "  1. Nedeljni limit: max 8h prekovremeno nedeljno\n"
    "  2. Mesečni limit: max 32h prekovremeno mesečno\n"
    "  3. GODIŠNJI CAP: max 250h prekovremeno godišnje\n\n"
    "OBAVEZNI PRORAČUN (ne prihvataj 'nije navedeno' kao zaključak):\n"
    "Ako ugovor predviđa X h/mes prekovremenog rada:\n"
    "  IZRAČUNAJ: X × 12 = Y h/god\n"
    "  AKO Y > 250 → KRŠI ZR 53 GODIŠNJI CAP\n"
    "  AKO Y ≤ 250 → GODIŠNJI CAP ISPUNJEN\n\n"
    "DIREKTNA PRIMENA (32h/mes):\n"
    "  32h/mes × 12 = 384h/god > 250h/god → KRŠI ZR 53 GODIŠNJI CAP.\n"
    "  ZAKLJUČAK: ugovorni mesečni limit od 32h/mes je NEZAKONIT jer vodi ka 384h/god > 250h.\n\n"

    "KLAUZULA O TAJNOSTI/NDA u ugovoru o radu — zabranjeni zakoni:\n\n"
    "Tajnost poslovnih informacija u ugovoru o radu se analzira kroz ZR i ugovorni tekst.\n"
    "KATEGORIČKE ZABRANE — ni u jednom delu odgovora NE CITIRATI:\n"
    "  - Zakon o digitalnoj imovini (ZDI) — to je za kripto aktivu i digitalne imovine,\n"
    "    NIKADA za klauzule o poslovnoj tajni iz ugovora o radu\n"
    "  - Zakon o zaštiti podataka o ličnosti (ZZPL/GDPR) — to je za obradu ličnih podataka,\n"
    "    NIKADA za klauzule o poverljivosti/tajnosti između poslodavca i zaposlenog\n"
    "Ako retrieval vrati ZDI ili ZZPL za pitanje o tajnosti u ugovoru o radu — IGNORIŠI te rezultate.\n\n"

    "ZR ČL. 189 OTKAZNI ROK — DIREKTNA PRAVILA (UVEK PRIMENITI):\n\n"
    "Zakonski minimum otkaznog roka: 8 dana (bez specifikacije vrste).\n"
    "PRAVILO POREĐENJA: poredi numeričku vrednost direktno — 15 (radnih) vs 8 (dana).\n"
    "  → 15 > 8 → ISPUNJAVA zakonski minimum.\n"
    "  → Konverzija radnih u kalendarske NIJE POTREBNA: radni dani su uvek ≥ kalendarskih.\n"
    "DIREKTAN ZAKLJUČAK za 15 radnih dana:\n"
    "  Ugovor: 15 radnih dana | ZR 189 minimum: 8 dana | 15 > 8 → U SKLADU SA ZR 189.\n"
    "ZABRANJENO: Nikada ne zaključiti da je 15 manje od 8 — to je matematički pogrešno."
)


# ─── Doc-type detection + domain constraints (Phase 2.5 Patch 1) ─────────────

def detect_doc_type(passages: list[str]) -> str | None:
    """Return document type string ('ugovor_o_radu', etc.) or None if unknown."""
    if not passages:
        return None
    text = " ".join(passages).upper()
    if "UGOVOR O RADU" in text or ("ZAPOSLENI" in text and "POSLODAVAC" in text):
        return "ugovor_o_radu"
    if "UGOVOR O ZAKUPU" in text or ("ZAKUPODAVAC" in text and "ZAKUPAC" in text):
        return "ugovor_o_zakupu"
    if "UGOVOR O KUPOPRODAJI" in text or ("PRODAVAC" in text and "KUPAC" in text):
        return "ugovor_o_kupoprodaji"
    return None


DOC_TYPE_CONSTRAINTS = {
    "ugovor_o_radu": (
        "DOC CONTEXT TYPE: UGOVOR O RADU.\n"
        "PRIMARNI legal framework: Zakon o radu (ZR).\n"
        "NE ANALIZIRAJ pitanje kroz: Zakon o digitalnoj imovini, Zakon o trgovini,\n"
        "Zakon o privrednim društvima, Zakon o platnim uslugama, ili druge\n"
        "specijalne zakone — osim ako se eksplicitno pominju u tekstu ugovora.\n\n"
        "ZR ČL. 53 — PREKOVREMENI RAD (tri obavezna limita):\n"
        "  1. Nedeljni:  maksimalno 8h prekovremeno nedeljno\n"
        "  2. Mesečni:   maksimalno 32h prekovremeno mesečno\n"
        "  3. GODIŠNJI CAP: maksimalno 250h prekovremeno godišnje\n"
        "UVEK proveri sva tri limita. Godišnji cap važi čak i ako mesečni limit\n"
        "izgleda kompliantan: 32h/mes × 12 = 384h/god > 250h → KRŠI godišnji cap."
    ),
    "ugovor_o_zakupu": (
        "DOC CONTEXT TYPE: UGOVOR O ZAKUPU.\n"
        "PRIMARNI legal framework: Zakon o obligacionim odnosima (ZOO) — zakup.\n"
        "NE ANALIZIRAJ pitanje kroz zakone koji nisu relevantni za zakup."
    ),
    "ugovor_o_kupoprodaji": (
        "DOC CONTEXT TYPE: UGOVOR O KUPOPRODAJI.\n"
        "PRIMARNI legal framework: Zakon o obligacionim odnosima (ZOO) — kupoprodaja.\n"
        "NE ANALIZIRAJ pitanje kroz zakone koji nisu relevantni za kupoprodaju."
    ),
}


# ─── ukloni_zabranjeni_tekst — post-processing filter v2.0 ───────────────────

def ukloni_zabranjeni_tekst(odgovor: str, tip: str) -> str:
    """
    REFAKTOR v2.0 — uklanja zabranjene fraze iz odgovora.
    Zamenjuje _ukloni_nedostupan_tekst() i proširuje je per-tip filtriranjem.
    """
    # Zabrane koje važe za SVE tipove
    uvek_zabranjeno = [
        "Tekst nije dostupan u bazi",
        "tekst nije dostupan",
        "nije dostupan u bazi",
        "nije pronađen u bazi",
        "nije pronadjen u bazi",
        "okvirni sadržaj:",
        "Tekst člana nije dostupan",
        "proverite važeći propis pre primene",
    ]

    # Zabrane za sve osim PARNICA
    nije_parnica_zabranjeno = [
        "solventnost tuženog",
        "Solventnost tuženog",
        "PROVERI SOLVENTNOST",
        "uzročno-posledična veza između postupka i štete",
        "medicinska dokumentacija",
        "policijski zapisnik",
        "saobraćajna nezgoda",
        "Garantni fond Srbije",
        "ZOO čl. 192",
        "ZOO čl. 376",
        "ZOO čl. 377",
        "subjektivni rok: 3 godine od saznanja za štetu",
        "objektivni rok: 5 godina od dana nastanka štete",
        "za saobraćajne nezgode sa nepoznatim",
    ]

    def _ukloni_linije(tekst: str, fraze: list[str]) -> str:
        linije = tekst.split("\n")
        nove = []
        for linija in linije:
            l_lower = linija.lower()
            ukloniti = False
            for fraza in fraze:
                if fraza.lower() in l_lower:
                    logging.warning("[FILTER] Uklonjena zabranjena fraza: '%s'", fraza)
                    ukloniti = True
                    break
            if not ukloniti:
                nove.append(linija)
        return "\n".join(nove)

    odgovor = _ukloni_linije(odgovor, uvek_zabranjeno)

    if tip != "PARNICA":
        odgovor = _ukloni_linije(odgovor, nije_parnica_zabranjeno)

    # Očisti višestruke prazne redove
    while "\n\n\n" in odgovor:
        odgovor = odgovor.replace("\n\n\n", "\n\n")

    return odgovor.strip()


def _pozovi_openai(
    system_prompt: str,
    user_content: str,
    model: str = "gpt-4o",
    max_tokens: int = 1000,
    response_format: dict | None = None,
) -> str:
    """OpenAI poziv sa timeoutom i ograničenjem tokena. Baca izuzetak pri grešci."""
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "timeout": 25.0,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    odgovor = _get_client().chat.completions.create(**kwargs)
    finish_reason = odgovor.choices[0].finish_reason if odgovor.choices else None
    if finish_reason == "length":
        logger.warning(
            "[TOKEN_OVERFLOW] max_tokens=%d used=%d input=%d",
            max_tokens,
            odgovor.usage.completion_tokens if odgovor.usage else -1,
            odgovor.usage.prompt_tokens if odgovor.usage else -1,
        )
    return (odgovor.choices[0].message.content or "").strip()


# ─── Confidence-gated response helpers ──────────────────────────────────────

SYSTEM_PROMPT_HIGH_CONFIDENCE = (
    "Ti si Vindex AI — pravni referentni sistem za srpsko pravo.\n"
    "Na osnovu dostavljenog zakonskog teksta, napiši praktično tumačenje u 2-3 rečenice na srpskom jeziku.\n\n"
    "STROGA PRAVILA:\n"
    "1. Odgovor mora početi tačno sa: \"Praktično tumačenje:\"\n"
    "2. Pominješ ISKLJUČIVO zakon i član koji su dostavljeni — nikakve druge propise ili zakone\n"
    "3. NE garantuješ ishod sudskog postupka\n"
    "4. Maksimum 3 rečenice, bez uvoda\n"
    "5. Jezik: srpska ekavica"
)

DISCLAIMER = (
    "\n\n---\n\n"
    "⚠️ **Pravna napomena:** Vindex AI pruža informacije zasnovane na zakonskim "
    "tekstovima Republike Srbije i ne predstavlja pravni savet. Ovaj odgovor ne "
    "zamenjuje konsultaciju sa licenciranim advokatom. Pre donošenja bilo kakvih "
    "pravnih odluka, obratite se stručnjaku."
)

HALLUCINATION_REFUSAL_TEXT = (
    "ZABRANJENO: Ne smeš generisati tvrdnje o sadržaju konkretnih članova zakona koji "
    "NISU prisutni u dostavljenom kontekstu. Ako pitanje implicira određeni član a taj "
    "član nije u kontekstu, navedi to eksplicitno umesto da generišeš sadržaj. "
    "Generisanje izmišljenih sadržaja članova zakona se kažnjava odbacivanjem celog odgovora."
)

# Harden all topic prompts against article-content fabrication (guard v2.0).
# PARNICA excluded: already has LEGAL FALLBACK for ZOO 154/155 structural citations
# which conflicts with a blanket ban; PARNICA is guarded by _FRAMEWORK_CLANOVI_EXEMPT at runtime.
SYSTEM_PROMPT_COMPLIANCE = SYSTEM_PROMPT_COMPLIANCE + "\n\n" + HALLUCINATION_REFUSAL_TEXT
SYSTEM_PROMPT_PORESKI    = SYSTEM_PROMPT_PORESKI    + "\n\n" + HALLUCINATION_REFUSAL_TEXT
SYSTEM_PROMPT_DEFINICIJA = SYSTEM_PROMPT_DEFINICIJA + "\n\n" + HALLUCINATION_REFUSAL_TEXT

# Harden NACRT + ANALIZA prompts (Commit 2/3).
_NACRT_ANTIFAB_HEADER = (
    "\n\n🔒 STROGO PRAVILO ZA NACRT:\n"
    "- U sekciji PRAVNI OSNOV citiraj ISKLJUČIVO članove navedene u bloku 'DOSTUPNI ZAKONI'.\n"
    "- NE citiraj članove iz opšteg znanja koji nisu u dostavljenom bloku.\n"
    "- Ako relevantan član nije u dostavljenom bloku, napiši '[proveriti relevantan član]'.\n"
)

_ANALIZA_ANTIFAB_HEADER = (
    "\n\n🔒 STROGO PRAVILO ZA ANALIZU:\n"
    "- Komentariši ISKLJUČIVO članove koji su EKSPLICITNO navedeni u dostavljenom dokumentu.\n"
    "- NE uvodi nove članove zakona iz svog znanja koji nisu u dokumentu.\n"
    "- Ako dokument ne pominje relevantan član, napiši "
    "'Dokument ne sadrži referencu na primenjivi član' — NE izmišljaj.\n"
)

SYSTEM_PROMPT_NACRT   = SYSTEM_PROMPT_NACRT   + _NACRT_ANTIFAB_HEADER   + "\n\n" + HALLUCINATION_REFUSAL_TEXT
SYSTEM_PROMPT_ANALIZA = SYSTEM_PROMPT_ANALIZA + _ANALIZA_ANTIFAB_HEADER + "\n\n" + HALLUCINATION_REFUSAL_TEXT

# T5: Sudska praksa anti-fabrication rule — appended to all 4 topic prompts
_PRAKSA_PROMPT_ADDENDUM = (
    "\n\n🔒 SUDSKA PRAKSA — STROGO PRAVILO:\n"
    "- Ako je u kontekstu prisutan blok \"SUDSKA PRAKSA\", popuni polje \"sudska_praksa\" "
    "sa MAX 3 odluke iz tog bloka.\n"
    "- Citiraj SAMO sud, broj odluke i datum koji su EKSPLICITNO navedeni u dostavljenom kontekstu.\n"
    "- NIKADA ne izmišljaj odluke koje nisu u kontekstu. "
    "Bolje prazno array [] nego fabrikovana referenca.\n"
    "- \"sazetak_relevantnosti\" mora biti zasnovan na sadržaju odluke iz konteksta, ne na opštem znanju.\n"
    "- Ako nema bloka \"SUDSKA PRAKSA\" u kontekstu → sudska_praksa = []"
)

SYSTEM_PROMPT_PARNICA    = SYSTEM_PROMPT_PARNICA    + _PRAKSA_PROMPT_ADDENDUM
SYSTEM_PROMPT_COMPLIANCE = SYSTEM_PROMPT_COMPLIANCE + _PRAKSA_PROMPT_ADDENDUM
SYSTEM_PROMPT_PORESKI    = SYSTEM_PROMPT_PORESKI    + _PRAKSA_PROMPT_ADDENDUM
SYSTEM_PROMPT_DEFINICIJA = SYSTEM_PROMPT_DEFINICIJA + _PRAKSA_PROMPT_ADDENDUM

# Phase 2.4: Mišljenja ministarstava — anti-fabrication rule
_MISLJENJA_PROMPT_ADDENDUM = (
    "\n\n📋 MIŠLJENJA MINISTARSTAVA — STROGO PRAVILO:\n"
    "- Ako je u kontekstu prisutan blok \"MIŠLJENJA MINISTARSTAVA\", "
    "OBAVEZNO dodaj posebnu sekciju između --- CITAT ZAKONA [RAG] i --- PRAVNI OSNOV, "
    "koristeći TAČNO ovaj format (bez izmena markera):\n"
    "\n"
    "--- MIŠLJENJA MINISTARSTAVA\n"
    "Mišljenje [ministarstvo], br. [broj], od [datum]: [kratak sadržaj od 1-2 rečenice]\n"
    "[Navedi max 2 mišljenja koja su direktno relevantna za postavljeno pitanje]\n"
    "\n"
    "- NIKADA ne izmišljaj mišljenja — navodi SAMO ona koja su doslovno u bloku konteksta.\n"
    "- Ako nema bloka \"MIŠLJENJA MINISTARSTAVA\" u kontekstu → sekciju POTPUNO IZOSTAVI.\n"
    "- Ako je blok prisutan ali nijedno nije relevantno za pitanje → sekciju IZOSTAVI."
)

SYSTEM_PROMPT_PARNICA    = SYSTEM_PROMPT_PARNICA    + _MISLJENJA_PROMPT_ADDENDUM
SYSTEM_PROMPT_COMPLIANCE = SYSTEM_PROMPT_COMPLIANCE + _MISLJENJA_PROMPT_ADDENDUM
SYSTEM_PROMPT_PORESKI    = SYSTEM_PROMPT_PORESKI    + _MISLJENJA_PROMPT_ADDENDUM
SYSTEM_PROMPT_DEFINICIJA = SYSTEM_PROMPT_DEFINICIJA + _MISLJENJA_PROMPT_ADDENDUM


def _format_halucination_block(razlog: str) -> str:
    """Korisnička poruka kada guard v2.0 detektuje fabricated article citation."""
    return (
        "[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.\n\n"
        "--- HIJERARHIJA IZVORA\n"
        "Sistem nije mogao da verifikuje navedene pravne reference u dostupnoj bazi zakona RS.\n\n"
        "--- PRAVNI ZAKLJUČAK\n"
        "Odgovor je blokiran jer su detektovane pravne reference koje nisu potkrepljene "
        "direktnim citatom iz indeksiranih zakona. Vindex AI primenjuje politiku nultog "
        "tolerancija na neproverene navode članova zakona.\n\n"
        "--- PREPORUKE\n"
        "— Navedite tačan broj člana i naziv zakona (npr. \"ZR čl. 161\") za direktan pregled\n"
        "— Reformulišite pitanje sa više pravnog konteksta\n"
        "— Konsultujte primarni izvor: Paragraf.rs ili Sl. glasnik RS\n\n"
        "--- CITAT ZAKONA [RAG]\n"
        "[—]\n\n"
        "--- IZVOR\n"
        f"Anti-halucinacijska zaštita: {razlog[:100]}\n\n"
        "⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. "
        "Konsultujte originalni tekst propisa u Službenom glasniku RS. "
        "Nije pravni savet — podložno promenama u sudskoj praksi."
    )


# ─── Commit 3/3: Structured JSON output schemas ──────────────────────────────

# T4: Shared sudska_praksa field definition (reused across all 4 schemas)
_SUDSKA_PRAKSA_SCHEMA_FIELD = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "sud":                  {"type": "string", "description": "FLAT STRING max 100 chars. Naziv suda TAČNO kao u dostavljenom kontekstu."},
            "broj_odluke":          {"type": "string", "description": "FLAT STRING max 50 chars. Broj odluke TAČNO kao u dostavljenom kontekstu."},
            "datum":                {"type": "string", "description": "FLAT STRING max 30 chars. Datum odluke iz konteksta."},
            "sazetak_relevantnosti": {"type": "string", "description": "FLAT STRING max 400 chars. Zašto je ova odluka relevantna za pitanje. Citiraj samo ono što JESTE u dostavljenom kontekstu."},
        },
        "required": ["sud", "broj_odluke", "sazetak_relevantnosti"],
    },
    "maxItems": 3,
    "description": (
        "Array do 3 sudske odluke iz bloka SUDSKA PRAKSA u kontekstu. "
        "Prazno array [] ako nema bloka SUDSKA PRAKSA ili nema relevantnih odluka. "
        "NIKADA ne izmišljaj odluke koje nisu u dostavljenom kontekstu."
    ),
}

_JSON_SCHEMA_PARNICA = {
    "type": "json_schema",
    "json_schema": {
        "name": "vindex_parnica",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "statusna_potvrda_status": {"type": "string"},
                "statusna_potvrda_tekst":  {"type": "string"},
                "hijerarhija_izvora":      {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "pravni_zakljucak":        {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "analiza_stete":           {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "procena_vrednosti":       {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 500 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "citat_zakona":            {"type": "string", "description": "FLAT STRING. Verbatim citat iz konteksta, maks. 500 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "pravni_osnov":            {"type": "string", "description": "KRATKA REFERENCA — FLAT STRING. Format: 'Zakon, član X (Sl. glasnik RS, br. Y/ZZ i dr.)'. BEZ generisanja dugačke liste amandman-brojeva. Maksimalno 200 chars."},
                "rizici_i_izuzeci":        {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "kada_ne_vazi":            {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "procesni_koraci":         {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "kljucno_pitanje":         {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "potrebne_informacije":    {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "izvor":                   {"type": "string", "description": "FLAT STRING. Format: 'Naziv zakona (Sl. glasnik RS, br. Y/ZZ i dr.)'. Maks. 300 chars. BEZ dugačke liste amandman-brojeva."},
                "sudska_praksa":           _SUDSKA_PRAKSA_SCHEMA_FIELD,
            },
            "required": [
                "statusna_potvrda_status", "statusna_potvrda_tekst",
                "hijerarhija_izvora", "pravni_zakljucak",
                "analiza_stete", "citat_zakona", "pravni_osnov",
                "rizici_i_izuzeci", "kada_ne_vazi", "procesni_koraci",
                "kljucno_pitanje", "potrebne_informacije", "izvor",
            ],
        },
    },
}

_JSON_SCHEMA_COMPLIANCE = {
    "type": "json_schema",
    "json_schema": {
        "name": "vindex_compliance",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "statusna_potvrda_status": {"type": "string"},
                "statusna_potvrda_tekst":  {"type": "string"},
                "hijerarhija_izvora":      {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "pravni_zakljucak":        {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "analiza_uskladjenosti":   {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "citat_zakona":            {"type": "string", "description": "FLAT STRING. Verbatim citat iz konteksta, maks. 500 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "pravni_osnov":            {"type": "string", "description": "KRATKA REFERENCA — FLAT STRING. Format: 'Zakon, član X (Sl. glasnik RS, br. Y/ZZ i dr.)'. BEZ generisanja dugačke liste amandman-brojeva. Maksimalno 200 chars."},
                "rizici_i_rokovi":         {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "compliance_koraci":       {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "kljucno_pitanje":         {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "potrebne_informacije":    {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "izvor":                   {"type": "string", "description": "FLAT STRING. Format: 'Naziv zakona (Sl. glasnik RS, br. Y/ZZ i dr.)'. Maks. 300 chars. BEZ dugačke liste amandman-brojeva."},
                "sudska_praksa":           _SUDSKA_PRAKSA_SCHEMA_FIELD,
            },
            "required": [
                "statusna_potvrda_status", "statusna_potvrda_tekst",
                "hijerarhija_izvora", "pravni_zakljucak",
                "analiza_uskladjenosti", "citat_zakona", "pravni_osnov",
                "rizici_i_rokovi", "compliance_koraci",
                "kljucno_pitanje", "potrebne_informacije", "izvor",
            ],
        },
    },
}

_JSON_SCHEMA_PORESKI = {
    "type": "json_schema",
    "json_schema": {
        "name": "vindex_poreski",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "statusna_potvrda_status": {"type": "string"},
                "statusna_potvrda_tekst":  {"type": "string"},
                "hijerarhija_izvora":      {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "pravni_zakljucak":        {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "analiza_poreske_obaveze": {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "citat_zakona":            {"type": "string", "description": "FLAT STRING. Verbatim citat iz konteksta, maks. 500 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "pravni_osnov":            {"type": "string", "description": "KRATKA REFERENCA — FLAT STRING. Format: 'Zakon, član X (Sl. glasnik RS, br. Y/ZZ i dr.)'. BEZ generisanja dugačke liste amandman-brojeva. Maksimalno 200 chars."},
                "poreski_rizici":          {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "poreske_obaveze_koraci":  {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 1000 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "kljucno_pitanje":         {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "potrebne_informacije":    {"type": "string", "description": "FLAT STRING. Plain tekst, maks. 300 chars. Ne nested JSON, ne arrays, ne lista Sl. glasnik brojeva."},
                "izvor":                   {"type": "string", "description": "FLAT STRING. Format: 'Naziv zakona (Sl. glasnik RS, br. Y/ZZ i dr.)'. Maks. 300 chars. BEZ dugačke liste amandman-brojeva."},
                "sudska_praksa":           _SUDSKA_PRAKSA_SCHEMA_FIELD,
            },
            "required": [
                "statusna_potvrda_status", "statusna_potvrda_tekst",
                "hijerarhija_izvora", "pravni_zakljucak",
                "analiza_poreske_obaveze", "citat_zakona", "pravni_osnov",
                "poreski_rizici", "poreske_obaveze_koraci",
                "kljucno_pitanje", "potrebne_informacije", "izvor",
            ],
        },
    },
}

_JSON_SCHEMA_DEFINICIJA = {
    "type": "json_schema",
    "json_schema": {
        "name": "vindex_definicija",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "statusna_potvrda_status": {"type": "string"},
                "statusna_potvrda_tekst":  {"type": "string"},
                "hijerarhija_izvora":      {"type": "string", "description": "KRITIČNO: ovo polje je FLAT STRING, ne JSON, ne array, ne nested struktura."},
                "pravni_zakljucak":        {"type": "string", "description": "KRITIČNO: ovo polje je FLAT STRING, ne JSON, ne array, ne nested struktura."},
                "pravna_definicija":       {"type": "string", "description": "KRITIČNO: ovo polje je FLAT STRING, ne JSON, ne array, ne nested struktura."},
                "citat_zakona":            {"type": "string", "description": "KRITIČNO: ovo polje je FLAT STRING, ne JSON, ne array, ne nested struktura."},
                "pravni_osnov":            {"type": "string", "description": "KRITIČNO: ovo polje je FLAT STRING, ne JSON, ne array, ne nested struktura."},
                "prakticni_primer":        {"type": "string", "description": "KRITIČNO: ovo polje je FLAT STRING, ne JSON, ne array, ne nested struktura."},
                "izvor":                   {"type": "string"},
                "sudska_praksa":           _SUDSKA_PRAKSA_SCHEMA_FIELD,
            },
            "required": [
                "statusna_potvrda_status", "statusna_potvrda_tekst",
                "hijerarhija_izvora", "pravni_zakljucak",
                "pravna_definicija", "citat_zakona", "pravni_osnov",
                "prakticni_primer", "izvor",
            ],
        },
    },
}

_JSON_SCHEMA_MAP: dict[str, dict] = {
    "PARNICA":    _JSON_SCHEMA_PARNICA,
    "COMPLIANCE": _JSON_SCHEMA_COMPLIANCE,
    "PORESKI":    _JSON_SCHEMA_PORESKI,
    "DEFINICIJA": _JSON_SCHEMA_DEFINICIJA,
}

_STATUS_SYMBOL_MAP: dict[str, str] = {"ok": "[✓]", "warn": "[~]", "err": "[!]"}

_SISTEM_NAPOMENA = (
    "⚠️ Ovaj izveštaj je generisan uz pomoć AI i služi isključivo kao pomoćno sredstvo u radu. "
    "Konsultujte originalni tekst propisa u Službenom glasniku RS. "
    "Nije pravni savet — podložno promenama u sudskoj praksi."
)


def _json_ka_tekst(data: dict, tip: str) -> str:
    """Serializes parsed JSON response dict back to the --- marker text format
    expected by the frontend formatResponse function. Zero UI change."""
    status_sym = _STATUS_SYMBOL_MAP.get(data.get("statusna_potvrda_status", "err"), "[!]")
    status_txt = data.get("statusna_potvrda_tekst", "")

    parts: list[str] = [
        f"{status_sym} STATUSNA POTVRDA: {status_txt}",
        "",
        "--- HIJERARHIJA IZVORA",
        data.get("hijerarhija_izvora", ""),
        "",
        "--- PRAVNI ZAKLJUČAK",
        data.get("pravni_zakljucak", ""),
    ]

    if tip == "PARNICA":
        if data.get("analiza_stete"):
            parts += ["", "--- ANALIZA ŠTETE", data["analiza_stete"]]
        if data.get("procena_vrednosti"):
            parts += ["", "--- PROCENA VREDNOSTI ZAHTEVA", data["procena_vrednosti"]]
    elif tip == "COMPLIANCE":
        if data.get("analiza_uskladjenosti"):
            parts += ["", "--- ANALIZA USKLAĐENOSTI", data["analiza_uskladjenosti"]]
    elif tip == "PORESKI":
        if data.get("analiza_poreske_obaveze"):
            parts += ["", "--- ANALIZA PORESKE OBAVEZE", data["analiza_poreske_obaveze"]]
    elif tip == "DEFINICIJA":
        if data.get("pravna_definicija"):
            parts += ["", "--- PRAVNA DEFINICIJA", data["pravna_definicija"]]

    citat = data.get("citat_zakona") or "[—]"
    parts += ["", "--- CITAT ZAKONA [RAG]", citat]
    parts += ["", "--- PRAVNI OSNOV", data.get("pravni_osnov", "")]

    if tip == "PARNICA":
        if data.get("rizici_i_izuzeci"):
            parts += ["", "--- RIZICI I IZUZECI", data["rizici_i_izuzeci"]]
        if data.get("kada_ne_vazi"):
            parts += ["", "--- KADA OVO NE VAŽI", data["kada_ne_vazi"]]
        if data.get("procesni_koraci"):
            parts += ["", "--- PROCESNI KORACI", data["procesni_koraci"]]
    elif tip == "COMPLIANCE":
        if data.get("rizici_i_rokovi"):
            parts += ["", "--- RIZICI I ROKOVI", data["rizici_i_rokovi"]]
        if data.get("compliance_koraci"):
            parts += ["", "--- COMPLIANCE KORACI", data["compliance_koraci"]]
    elif tip == "PORESKI":
        if data.get("poreski_rizici"):
            parts += ["", "--- PORESKI RIZICI", data["poreski_rizici"]]
        if data.get("poreske_obaveze_koraci"):
            parts += ["", "--- PORESKE OBAVEZE — KORACI", data["poreske_obaveze_koraci"]]

    if data.get("kljucno_pitanje"):
        parts += ["", "--- KLJUČNO PITANJE", data["kljucno_pitanje"]]
    if data.get("potrebne_informacije"):
        parts += ["", "--- POTREBNE INFORMACIJE", data["potrebne_informacije"]]

    # T7: Render SUDSKA PRAKSA section (only when non-empty array)
    praksa_array = data.get("sudska_praksa")
    if isinstance(praksa_array, list) and praksa_array:
        parts += ["", "--- SUDSKA PRAKSA"]
        for idx, item in enumerate(praksa_array[:3], 1):
            if not isinstance(item, dict):
                continue
            sud       = (item.get("sud") or "").strip()
            broj      = (item.get("broj_odluke") or "").strip()
            datum     = (item.get("datum") or "").strip()
            sazetak   = (item.get("sazetak_relevantnosti") or "").strip()
            header_parts = [p for p in [sud, broj, datum] if p]
            header = f"{idx}. " + ", ".join(header_parts) if header_parts else f"{idx}. —"
            parts.append(header)
            if sazetak:
                parts.append(f"   {sazetak}")
            parts.append("")

    parts += [
        "",
        "--- IZVOR",
        data.get("izvor", ""),
        "",
        _SISTEM_NAPOMENA,
    ]

    return "\n".join(parts)


def _parsiraj_strukturni_odgovor(
    raw_json: str,
    tip: str,
    docs: list[str],
    praksa_context: str = "",
) -> tuple[bool, str]:
    """
    Parse JSON response from LLM (Commit 3/3 structured output).
    Runs hallucination guard on:
      - citat_zakona + pravni_osnov + pravni_zakljucak  (law citations)
      - sudska_praksa array  (T6: decision citations — only when praksa_context provided)
    Returns (success, text):
      success=True  → text is serialized ---marker format
      success=False → text is hallucination block message
    """
    import json as _json
    try:
        data = _json.loads(raw_json)
    except Exception as exc:
        logger.warning("[COMMIT3] JSON parse greška [tip=%s]: %s", tip, exc)
        return False, _format_halucination_block(f"JSON parse greška: {exc}")

    # Build guard text from structured citation fields
    guard_parts = [
        data.get("citat_zakona", ""),
        data.get("pravni_osnov", ""),
        data.get("pravni_zakljucak", ""),
    ]
    guard_text = "\n".join(p for p in guard_parts if p)

    validan, razlog = _proveri_halucinaciju(guard_text, docs)
    if not validan:
        logger.warning(
            "[COMMIT3] Strukturni guard blok [tip=%s] razlog=%s", tip, razlog
        )
        return False, _format_halucination_block(razlog)

    # T6: Praksa hallucination guard — only active when we provided a praksa context
    if praksa_context:
        cited_pairs = _extract_praksa_citations(data)
        if cited_pairs:
            ctx_norm = _normalizuj(praksa_context)
            fabricated: list[str] = []
            for sud, dn in cited_pairs:
                dn_norm = _normalizuj(dn)
                # Check: decision number must appear in the praksa_context we provided
                if dn_norm and dn_norm not in ctx_norm:
                    fabricated.append(f"{sud} / {dn}" if sud else dn)
            if fabricated:
                logger.warning(
                    "[COMMIT3_PRAKSA] Fabricated praksa citations [tip=%s]: %s",
                    tip, fabricated[:3],
                )
                return False, _format_halucination_block(
                    f"Sudska praksa nije u kontekstu: {', '.join(fabricated[:3])}"
                )
            logger.info(
                "[COMMIT3_PRAKSA] %d praksa citations verified OK [tip=%s]",
                len(cited_pairs), tip,
            )

    return True, _json_ka_tekst(data, tip)


# ─── NACRT RAG context hints (Commit 2/3) ────────────────────────────────────
# Maps document type (vrsta) → list of (law_full_name, clan_label) to pre-fetch.
# Used by ask_nacrt to inject verified article text before LLM call.
_NACRT_DOC_TYPE_HINTS: dict[str, list[tuple[str, str]]] = {
    "ugovor_neodredjeno": [
        ("zakon o radu", "Član 30"),    # Sadržaj ugovora o radu
        ("zakon o radu", "Član 36"),    # Probni rad — max 6 meseci
        ("zakon o radu", "Član 161"),   # Zabrana konkurencije za vreme rada
        ("zakon o radu", "Član 162"),   # Zabrana konkurencije posle prestanka
        ("zakon o radu", "Član 189"),   # Otkazni rok
    ],
    "ugovor_odredjeno": [
        ("zakon o radu", "Član 37"),    # Ugovor na određeno vreme — max 24 meseca
        ("zakon o radu", "Član 30"),    # Sadržaj ugovora
        ("zakon o radu", "Član 36"),    # Probni rad
    ],
    "aneks": [
        ("zakon o radu", "Član 171"),   # Ponuda za izmenu uslova rada
        ("zakon o radu", "Član 172"),   # Izmena uslova rada — aneks forma
    ],
    "sporazumni_raskid": [
        ("zakon o radu", "Član 177"),   # Sporazumni prestanak radnog odnosa
    ],
    "punomocje": [
        ("zakon o obligacionim odnosima", "Član 85"),   # Opunomoćenje — sadržaj
        ("zakon o obligacionim odnosima", "Član 86"),   # Obim punomoćja
    ],
}


def _dohvati_nacrt_kontekst(vrsta: str) -> list[str]:
    """
    Fetch relevant law articles from Pinecone for a given NACRT document type.
    Uses _direktan_fetch_clana + _formatiraj_match — reuse existing infra.
    Returns list of formatted article strings. Empty list if vrsta unknown or fetch fails.
    Max 2 chunks per article to avoid context bloat.
    """
    hints = _NACRT_DOC_TYPE_HINTS.get(vrsta, [])
    if not hints:
        logger.info("[NACRT_RAG] Nema hints za vrsta=%s — skip RAG inject", vrsta)
        return []

    rezultati: list[str] = []
    for zakon, clan_label in hints:
        try:
            matches = _direktan_fetch_clana(clan_label, zakon)
            for m in matches[:2]:
                tekst = _formatiraj_match(m)
                if tekst and len(tekst.strip()) > 30:
                    rezultati.append(tekst)
        except Exception:
            logger.warning("[NACRT_RAG] Neuspešan fetch %s %s — preskačem", zakon, clan_label)
            continue

    logger.info("[NACRT_RAG] vrsta=%s → %d docs fetched", vrsta, len(rezultati))
    return rezultati


# ─── ANALIZA doc-only citation guard (Commit 2/3) ─────────────────────────────

def _ekstrahuj_clanove_iz_dokumenta(tekst: str) -> frozenset[str]:
    """
    Extract all article number strings from uploaded document text.
    Matches: "Član N", "Članu N", "Člana N", "čl. N", "čl N" (Serbian forms).
    Returns frozenset of article number strings (e.g. frozenset({"162", "161a"})).
    """
    found: set[str] = set()
    primary_hits: list[str] = []
    secondary_hits: list[str] = []
    # Primary: "Član"/"Članu"/"Člana"/"Čl." case-insensitive oblique forms
    for m in re.finditer(r"[C\u010c\u010d]lan(?:u|a|om|ovi|ovima|ove)?\s+(\d+[a-zA-Z]?)", tekst):
        found.add(m.group(1))
        primary_hits.append(m.group(0))
    # Secondary: "čl. N" / "čl N" abbreviated form
    for m in re.finditer(r"[CČč]l\.?\s+(\d+[a-zA-Z]?)", tekst):
        found.add(m.group(1))
        secondary_hits.append(m.group(0))
    logger.debug("[EKSTRAKCIJA] primary_hits=%s secondary_hits=%s → found=%s",
                 primary_hits[:10], secondary_hits[:10], sorted(found)[:15])
    return frozenset(found)


_ZAKON_PREFIX_RE = re.compile(
    r"(?:zakon[ao]?\s+o\s+\w+(?:\s+\w+){0,4}"          # "Zakon o radu", "Zakona o obligacionim odnosima"
    r"|ZOO|ZR\b|ZPP\b|KZ\b|ZKP\b|ZIO\b|ZDI\b"           # standard abbreviations
    r"|ZOUP|ZVP|ZZPL|ZSPNFT|ZPDG|ZUS|ZN\b|ZPD\b|PZ\b"  # more abbreviations
    r"|zakonik[ao]?\s+o\s+\w+(?:\s+\w+){0,3}"            # "Zakonik o krivičnom postupku"
    r"|ustav\s+republike\s+srbije)"                        # Ustav
    r"[^.]{0,120}",                                        # up to 120 chars before "Član N"
    re.IGNORECASE,
)


def _je_zakon_citacija(broj: str, tekst: str) -> bool:
    """Return True if 'Član {broj}' in tekst is preceded within 120 chars by a law name/abbrev."""
    clan_pattern = re.compile(r"[Čč]lan\s+" + re.escape(broj) + r"\b")
    for m_clan in clan_pattern.finditer(tekst):
        preceding = tekst[max(0, m_clan.start() - 120): m_clan.start()]
        if _ZAKON_PREFIX_RE.search(preceding):
            return True
    return False


def _proveri_analiza_citate(analiza_output: str, allowed_articles: frozenset[str]) -> tuple[bool, str]:
    """
    ANALIZA doc-only citation guard.
    Every article cited in analiza_output must either:
    (a) be in allowed_articles (extracted from the document), OR
    (b) appear as a statutory citation — preceded within 120 chars by a recognised
        law name or abbreviation (Zakon o radu, ZOO, ZR, KZ, ...).

    Rationale: contract clauses numbered "Član 1" – "Član 15" are NOT the same as
    law articles "Zakon o radu, Član 40". The guard must not confuse the two.
    Only block standalone article references that have no law-name context and
    whose numbers are not present in the document's own clause numbering.

    Returns (validan, razlog).
    """
    if not allowed_articles:
        return True, "ok"  # document has no inline article refs — allow all contextual citations
    logger.debug("[ANALIZA_GUARD] allowed_articles=%s (count=%d)", sorted(allowed_articles)[:10], len(allowed_articles))
    citirani_raw = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", analiza_output)
    logger.debug("[ANALIZA_GUARD] citirani_raw iz LLM output: %s", citirani_raw[:10])

    # Deduplicate preserving order
    vidjeni: set[str] = set()
    citirani_unique: list[str] = []
    for c in citirani_raw:
        if c not in vidjeni:
            vidjeni.add(c)
            citirani_unique.append(c)

    if not citirani_unique:
        logger.debug("[ANALIZA_GUARD] nema Član N citata u outputu → PASS")
        return True, "ok"

    # Only flag citations that are NOT in allowed_articles AND NOT statutory references
    novi = [
        c for c in citirani_unique
        if c not in allowed_articles and not _je_zakon_citacija(c, analiza_output)
    ]
    logger.debug("[ANALIZA_GUARD] citirani=%s, van_dok_i_nije_zakon=%s", citirani_unique, novi[:10])
    if novi:
        logger.warning(
            "[ANALIZA_GUARD] %d/%d citata blokirano (van dokumenta, nije zakonska ref): %s",
            len(novi), len(citirani_unique), novi[:5],
        )
        clanovi_str = ", ".join(f"Član {c}" for c in novi[:5])
        return False, f"{clanovi_str} — nije u dostavljenom dokumentu"

    logger.debug("[ANALIZA_GUARD] svi citati su prihvaćeni (u dok. ili zakonska ref.) → PASS")
    return True, "ok"


def _format_praksa_context(decisions: list[dict]) -> str:
    """
    T3: Format processed praksa decisions as a structured block for LLM injection.
    Returns empty string when decisions list is empty (gate suppressed results).
    """
    if not decisions:
        return ""
    lines = ["SUDSKA PRAKSA (relevantne odluke iz baze):"]
    for i, d in enumerate(decisions, 1):
        sud  = d.get("court", "")
        dn   = d.get("decision_number", "?")
        date = d.get("date", "")
        text = (d.get("text") or "").strip()[:300]
        header_parts = [p for p in [sud, dn, date] if p]
        lines.append(f"{i}. " + ", ".join(header_parts))
        if text:
            lines.append(f"   Sažetak: {text}")
        lines.append("")
    return "\n".join(lines).strip()


def _injektuj_misljenja_blok(odgovor: str, opinions: list[dict]) -> str:
    """Phase 2.4: Inject '--- MIŠLJENJA MINISTARSTAVA' section directly into LLM response."""
    if not opinions:
        return odgovor
    if "--- MIŠLJENJA MINISTARSTAVA" in odgovor:
        return odgovor  # LLM already included it — no duplication
    lines = []
    for op in opinions:
        ministarstvo = op.get("ministarstvo", "")
        broj  = op.get("broj", "")
        datum = op.get("datum", "")
        naziv = (op.get("naziv") or "").strip()
        text  = (op.get("text") or "").strip()[:350]
        header_parts = [p for p in [ministarstvo, broj, datum] if p]
        entry = "Mišljenje " + ", ".join(header_parts) + ":"
        if naziv:
            entry += "\n" + naziv
        if text:
            entry += "\n" + text
        lines.append(entry)
    blok = "\n--- MIŠLJENJA MINISTARSTAVA\n" + "\n\n".join(lines) + "\n"
    for marker in ("--- IZVOR", "SLUZBENI IZVOR:", "SLUŽBENI IZVOR:"):
        if marker in odgovor:
            return odgovor.replace(marker, blok + "\n" + marker, 1)
    return odgovor + blok


def _format_misljenja_context(opinions: list[dict]) -> str:
    """
    Phase 2.4: Format processed ministry opinions as a structured block for LLM injection.
    Returns empty string when opinions list is empty (gate suppressed results).
    """
    if not opinions:
        return ""
    lines = ["MIŠLJENJA MINISTARSTAVA (relevantna zvanična mišljenja iz baze):"]
    for i, op in enumerate(opinions, 1):
        ministarstvo = op.get("ministarstvo", "")
        broj  = op.get("broj", "")
        datum = op.get("datum", "")
        naziv = op.get("naziv", "")
        text  = (op.get("text") or "").strip()[:400]
        header_parts = [p for p in [ministarstvo, broj, datum] if p]
        lines.append(f"{i}. " + ", ".join(header_parts))
        if naziv:
            lines.append(f"   Tema: {naziv}")
        if text:
            lines.append(f"   Sadržaj: {text}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_refusal(article: str, law: str | None) -> str:
    law_str = (law or "tom zakonu").capitalize()
    return (
        f"{article} ({law_str}) nije pronađen u indeksu Vindex baze. "
        "Mogući razlozi: broj člana ne postoji u tom propisu, "
        "ili konkretan član trenutno nije ingestovan. "
        "Preporučujemo konsultaciju primarnog izvora "
        "(Službeni glasnik RS) ili Paragraf.rs."
    )


def _format_low_response(top_score: float) -> str:
    return (
        "Nemam pouzdan odgovor na ovo pitanje u trenutnoj bazi zakona.\n\n"
        "Mogući razlozi: pitanje izlazi iz indeksiranih oblasti, ili "
        "specifičnost pitanja zahteva ekspertski sud.\n\n"
        "Preporučujem konsultaciju sa advokatom specijalistom.\n\n"
        "---\n"
        f"📊 Pouzdanost: NISKA | Score: {top_score:.3f}"
        + DISCLAIMER
    )


def _format_medium_response(article: str, law: str, text: str, score: float) -> str:
    return (
        f"Najbliži match koji imam je **{article} [{law}]**, ali pouzdanost nije visoka.\n\n"
        f"Doslovan tekst najbližeg člana:\n\"{text[:800]}\"\n\n"
        "Preporučujem proveru sa specijalistom.\n\n"
        "---\n"
        f"📊 Pouzdanost: SREDNJA | Zakon: {law} | Član: {article} | Score: {score:.3f}"
        + DISCLAIMER
    )


def _format_high_response(article: str, law: str, text: str, score: float, interpretation: str) -> str:
    return (
        f"**{article}. [{law}]:**\n"
        f"\"{text[:1200]}\"\n\n"
        f"{interpretation}\n\n"
        "---\n"
        f"📊 Pouzdanost: VISOKA | Zakon: {law} | Član: {article} | Score: {score:.3f}"
        + DISCLAIMER
    )


def _generate_high_interpretation(pitanje: str, article: str, law: str, text: str) -> str:
    user_content = (
        f"Pitanje: {pitanje}\n\n"
        f"Zakonski tekst ({law}, {article}):\n{text[:1500]}"
    )
    return _pozovi_openai(
        SYSTEM_PROMPT_HIGH_CONFIDENCE,
        user_content,
        model="gpt-4o",
        max_tokens=300,
    )


# ─── Javne funkcije agenta ───────────────────────────────────────────────────

def ask_agent(
    pitanje: str,
    history: list[dict] | None = None,
    extra_namespaces: list | None = None,
) -> dict:
    """
    Hallucination-free confidence-gated pipeline v3.0.
    Returns confidence level + article metadata alongside the response.
    history: lista {'q': str, 'a': str} — poslednja 3 pitanja/odgovora iz sesije.
    extra_namespaces: optional Pinecone namespace list (e.g. ["tmp_<session_id>"]).
    """
    pitanje = (pitanje or "").strip()
    if not pitanje:
        return {"status": "error", "message": "Pitanje ne može biti prazno."}

    if not history and not extra_namespaces:
        keš = _cache_get(pitanje)
        if keš:
            return {**keš, "from_cache": True}

    pitanje_api = _skini_pii(pitanje)
    log_id = _hash_za_log(pitanje)

    try:
        # KORAK 1: Retrieve with confidence metadata
        try:
            docs, retrieval_meta = retrieve_documents(pitanje_api, k=10, extra_namespaces=extra_namespaces)
        except Exception as e:
            logger.exception("PINECONE GREŠKA [q=%s] tip=%s msg=%s", log_id, type(e).__name__, str(e)[:200])
            return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}

        # DOC GATE BIAS: when uploaded-doc context present, bias confidence band upward
        if extra_namespaces:
            doc_passages = retrieval_meta.get("doc_passages", [])
            if doc_passages:
                top_doc_score = max(
                    (p.get("score", 0.0) for p in doc_passages),
                    default=0.0,
                )
                if top_doc_score >= 0.5:
                    band_up = {"LOW": "MEDIUM", "MEDIUM": "HIGH", "HIGH": "HIGH"}
                    old_band = retrieval_meta.get("confidence", "LOW")
                    new_band = band_up.get(old_band, old_band)
                    if new_band != old_band:
                        retrieval_meta["confidence"] = new_band
                        logger.info(
                            "[DOC_GATE_BIAS] doc_top=%.3f law_top=%.3f band %s→%s",
                            top_doc_score,
                            retrieval_meta.get("top_score", 0.0),
                            old_band, new_band,
                        )

        confidence   = retrieval_meta["confidence"]
        top_score    = retrieval_meta["top_score"]
        top_article  = retrieval_meta["top_article"]
        top_law      = retrieval_meta["top_law"]

        logger.info(
            "[ASK_AGENT] confidence=%s score=%.4f article=%s law=%s query=%s [q=%s]",
            confidence, top_score, top_article, top_law, pitanje_api[:60], log_id,
        )

        # KORAK 1.6: Sudska praksa retrieval (T3) — separate pipeline, never affects zakon band
        try:
            _praksa_raw = retrieve_sudska_praksa(pitanje_api, top_k=10)
            _processed_praksa = process_praksa_chunks(_praksa_raw, k=3)
        except Exception as _pe:
            logger.warning("[PRAKSA] Retrieval/processing greška: %s — nastavlja se bez prakse", _pe)
            _processed_praksa = []
        praksa_blok = _format_praksa_context(_processed_praksa)

        # KORAK 1.7: Mišljenja ministarstava retrieval (Phase 2.4)
        # Triggered always (relevant opinions surface for any labor/tax query)
        # or explicitly when query contains misljenja keywords.
        misljenja_blok = ""
        _processed_misljenja: list[dict] = []
        try:
            _misljenja_raw = retrieve_misljenja(pitanje_api, top_k=10)
            _processed_misljenja = process_misljenja_chunks(_misljenja_raw, k=2)
            misljenja_blok = _format_misljenja_context(_processed_misljenja)
            if misljenja_blok:
                logger.info("[MISLJENJA] %d mišljenja dodato u kontekst", len(_processed_misljenja))
        except Exception as _me:
            logger.warning("[MISLJENJA] Retrieval greška: %s — nastavlja se bez mišljenja", _me)
            misljenja_blok = ""
            _processed_misljenja = []

        # KORAK 1.5: Hard refusal when explicitly cited article is absent from corpus;
        # inject exact chunks when article IS found so LLM gets correct text.
        # _korak_15_authoritative=True blocks downstream second-guessing (Fixes 1-3).
        _korak_15_authoritative = False
        _ref_docs: list[str] = []
        _ref_label, _ref_zakon = ekstrakcija_clana(pitanje_api)
        if _ref_label is not None:
            _ref_matches = _direktan_fetch_clana(_ref_label, _ref_zakon)
            if not _ref_matches:
                logger.warning(
                    "[HALUCINATION_GUARD] Clan %s (%s) nije u korpusu — hard refusal [q=%s]",
                    _ref_label, _ref_zakon, log_id,
                )
                return {
                    "status": "success",
                    "blocked": True,
                    "data": _format_refusal(_ref_label, _ref_zakon or top_law),
                    "confidence": "LOW", "top_score": top_score,
                    "top_article": _ref_label, "top_law": _ref_zakon or top_law,
                }
            # Fix 1: article found — update metadata unconditionally (old guard
            # `if confidence != "HIGH"` caused footer to show semantic top hit instead
            # of the directly-fetched article when retrieval already returned HIGH).
            _ref_docs = [_formatiraj_match(m) for m in _ref_matches]
            docs = _ref_docs + [d for d in docs if d not in set(_ref_docs)]
            logger.info(
                "[HALUCINATION_GUARD] Clan %s nadjeno — inject %d chunks, %s→HIGH [q=%s]",
                _ref_label, len(_ref_matches), confidence, log_id,
            )
            confidence = "HIGH"
            top_article = _ref_label
            top_law = _ref_zakon or top_law
            _korak_15_authoritative = True

        # KORAK 2: LOW — instant refusal, no LLM needed
        if confidence == "LOW":
            odgovor = _format_low_response(top_score)
            rezultat = {
                "status": "success", "data": odgovor,
                "confidence": "LOW", "top_score": top_score,
                "top_article": top_article, "top_law": top_law,
            }
            if not history:
                _cache_set(pitanje, rezultat)
            logger.info("LOW confidence refusal [q=%s]", log_id)
            return rezultat

        # KORAK 3: Filter docs
        filtrirani = _filtriraj_kontekst(docs)
        if _korak_15_authoritative and _ref_docs:
            # Fix 2: pin injected chunks at position [0] so LLM sees ground-truth
            # article first regardless of how _filtriraj_kontekst orders results.
            _ref_set = set(_ref_docs)
            filtrirani = [d for d in _ref_docs if len(d.strip()) > 50] + [
                d for d in filtrirani if d not in _ref_set
            ]
        if not filtrirani:
            odgovor = _format_low_response(top_score)
            return {
                "status": "success", "data": odgovor,
                "confidence": "LOW", "top_score": top_score,
                "top_article": top_article, "top_law": top_law,
            }

        # KORAK 4: Klasifikacija + topic prompt (zajednički za MEDIUM i HIGH)
        tip = klasifikuj_pitanje(pitanje_api)
        _prompt_map = {
            "COMPLIANCE": (SYSTEM_PROMPT_COMPLIANCE, SEKCIJE_COMPLIANCE, "gpt-4o", 2000),
            "PORESKI":    (SYSTEM_PROMPT_PORESKI,    SEKCIJE_PORESKI,    "gpt-4o", 2000),
            "PARNICA":    (SYSTEM_PROMPT_PARNICA,    SEKCIJE_PARNICA,    "gpt-4o", 2500),
            "DEFINICIJA": (SYSTEM_PROMPT_DEFINICIJA, SEKCIJE_DEFINICIJA, "gpt-4o", 2500),
        }
        system_prompt, aktivan_sekcije, _model, _max_tokens = _prompt_map.get(tip, _prompt_map["DEFINICIJA"])

        if any("KORISNIKOV DOKUMENT" in d for d in filtrirani):
            system_prompt = system_prompt + "\n\n" + _DOC_CONTEXT_ADDENDUM
            # Patch 1: domain constraint based on detected document type
            _doc_snippets = [p.get("text_snippet", "") for p in retrieval_meta.get("doc_passages", [])]
            _doc_type = detect_doc_type(_doc_snippets)
            if _doc_type and _doc_type in DOC_TYPE_CONSTRAINTS:
                system_prompt = system_prompt + "\n\n" + DOC_TYPE_CONSTRAINTS[_doc_type]
                logger.info("[DOC_TYPE] Detected doc type: %s — constraint injected", _doc_type)
            # Fix-2.5a (Q2): For employment contracts, remove ZDI + ZZPL chunks from
            # context so LLM cannot cite them even if retrieval returned them with high score.
            if _doc_type == "ugovor_o_radu":
                _n_before = len(filtrirani)
                filtrirani = [
                    d for d in filtrirani
                    if "zakon o digitalnoj imovini" not in d.lower()
                    and "ZDI čl" not in d
                    and "zastita podataka o licnosti" not in d.lower()
                    and "podataka o licnosti" not in d.lower()
                ]
                if len(filtrirani) < _n_before:
                    logger.info(
                        "[ZDI_ZZPL_FILTER] Uklonjen/i %d chunk(s) za ugovor_o_radu kontekst",
                        _n_before - len(filtrirani),
                    )

        kontekst = "\n\n---\n\n".join(filtrirani)
        history_blok = ""
        if history:
            stavke = []
            for i, h in enumerate(history[-3:], 1):
                q_h = _skini_pii((h.get("q") or "")[:200])
                a_h = (h.get("a") or "")[:400]
                stavke.append(f"[{i}] Korisnik: {q_h}\n    Vindex AI: {a_h}...")
            history_blok = "ISTORIJA RAZGOVORA (kontekst):\n" + "\n".join(stavke) + "\n\n"

        _HEDGE = (
            f"[POUZDANOST: SREDNJA — score {top_score:.3f}] "
            "Odgovaraj sa posebnom pažnjom. "
            "Ako neki podatak iz pitanja nije eksplicitno pokriven retrieved kontekstom, "
            "jasno reci da nije sigurno.\n\n"
        )

        # KORAK 5: MEDIUM — puni topic prompt sa hedge banerom
        if confidence == "MEDIUM":
            _praksa_insert = f"\n\n{praksa_blok}\n" if praksa_blok else ""
            _misljenja_insert = f"\n\n{misljenja_blok}\n" if misljenja_blok else ""
            user_content = (
                f"{_HEDGE}"
                f"{history_blok}"
                f"PITANJE: {pitanje_api}\n\n"
                f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
                f"{_praksa_insert}"
                f"{_misljenja_insert}"
            )
            try:
                _raw_med = _pozovi_openai(
                    system_prompt, user_content, model=_model, max_tokens=_max_tokens,
                    response_format=_JSON_SCHEMA_MAP.get(tip),
                )
            except Exception:
                logger.exception("MEDIUM LLM greška [q=%s]", log_id)
                return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}

            _json_ok_med, odgovor = _parsiraj_strukturni_odgovor(_raw_med, tip, filtrirani, praksa_context=praksa_blok)
            if not _json_ok_med:
                logger.warning("[MEDIUM→BLOCK] Commit3 guard [q=%s]", log_id)
                return {
                    "status": "success",
                    "blocked": True,
                    "data": odgovor,
                    "confidence": "LOW", "top_score": top_score,
                    "top_article": top_article, "top_law": top_law,
                }

            pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
            if not pravno_validan:
                logger.error("Pravna greška MEDIUM: %s", pravna_greska)
                return {"status": "success", "blocked": True, "data": _odgovor_pravna_greska(pravna_greska)}

            odgovor = _srpski_termini(odgovor)
            odgovor = _ogranici_pouzdanost(odgovor)
            odgovor = ukloni_zabranjeni_tekst(odgovor, tip)
            odgovor = _injektuj_misljenja_blok(odgovor, _processed_misljenja)
            if "--- IZVOR" not in odgovor and "--- HIJERARHIJA IZVORA" not in odgovor:
                odgovor = _dodaj_izvor(odgovor, filtrirani)
            odgovor = _dodaj_disclaimer(odgovor)

            rezultat = {
                "status": "success", "data": odgovor,
                "confidence": "MEDIUM", "top_score": top_score,
                "top_article": top_article, "top_law": top_law,
            }
            if not history:
                _cache_set(pitanje, rezultat)
            logger.info("MEDIUM LLM odgovor [tip=%s, q=%s]", tip, log_id)
            return rezultat

        # KORAK 6: HIGH — puni topic prompt, soft section check, anti-halucinacijska zaštita
        _praksa_insert = f"\n\n{praksa_blok}\n" if praksa_blok else ""
        _misljenja_insert = f"\n\n{misljenja_blok}\n" if misljenja_blok else ""
        user_content = (
            f"{history_blok}"
            f"PITANJE: {pitanje_api}\n\n"
            f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
            f"{_praksa_insert}"
            f"{_misljenja_insert}"
        )
        try:
            _raw_high = _pozovi_openai(
                system_prompt, user_content, model=_model, max_tokens=_max_tokens,
                response_format=_JSON_SCHEMA_MAP.get(tip),
            )
        except Exception:
            logger.exception("HIGH LLM greška [q=%s]", log_id)
            return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}

        _json_ok_high, odgovor = _parsiraj_strukturni_odgovor(_raw_high, tip, filtrirani, praksa_context=praksa_blok)

        # Soft section check — log only, do not discard
        if _json_ok_high and not _ima_obavezne_sekcije(odgovor, aktivan_sekcije):
            logger.warning("[HIGH] Nedostaju obavezne sekcije [tip=%s, q=%s]", tip, log_id)

        # Anti-hallucination + topic drift → downgrade to MEDIUM LLM if either fails.
        # Fix 3: when KORAK 1.5 found ground truth, skip downgrade — we have the real
        # article in context so hallucination/drift checks are unreliable noise here.
        # Commit 3/3: structural guard replaces _proveri_halucinaciju for citation check.
        _downgrade = False
        if not _json_ok_high:
            if _korak_15_authoritative:
                logger.info(
                    "[HIGH] Commit3 guard — ignorisano, KORAK 1.5 autoritativan [q=%s]",
                    log_id,
                )
            else:
                logger.warning("[HIGH] Commit3 guard → MEDIUM [q=%s]", log_id)
                _downgrade = True

        if not _downgrade:
            tematski_ok, tematski_razlog = _proveri_tematsku_relevantnost(pitanje_api, odgovor, filtrirani)
            if not tematski_ok:
                if _korak_15_authoritative:
                    logger.info(
                        "[HIGH] Topic drift — ignorisano, KORAK 1.5 autoritativan [q=%s] razlog=%s",
                        log_id, tematski_razlog,
                    )
                else:
                    logger.warning("[HIGH] Topic drift → MEDIUM [q=%s] razlog=%s", log_id, tematski_razlog)
                    _downgrade = True

        if _downgrade:
            confidence = "MEDIUM"
            _praksa_insert_dg = f"\n\n{praksa_blok}\n" if praksa_blok else ""
            _misljenja_insert_dg = f"\n\n{misljenja_blok}\n" if misljenja_blok else ""
            user_content_medium = (
                f"{_HEDGE}"
                f"{history_blok}"
                f"PITANJE: {pitanje_api}\n\n"
                f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
                f"{_praksa_insert_dg}"
                f"{_misljenja_insert_dg}"
            )
            try:
                _raw_dg = _pozovi_openai(
                    system_prompt, user_content_medium, model=_model, max_tokens=_max_tokens,
                    response_format=_JSON_SCHEMA_MAP.get(tip),
                )
            except Exception:
                logger.exception("MEDIUM downgrade LLM greška [q=%s]", log_id)
                return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}

            # Re-check via structural guard — hard block if still fabricating
            _json_ok_dg, odgovor = _parsiraj_strukturni_odgovor(_raw_dg, tip, filtrirani, praksa_context=praksa_blok)
            if not _json_ok_dg:
                logger.warning("[DOWNGRADE→BLOCK] Commit3 guard posle downgrade [q=%s]", log_id)
                return {
                    "status": "success",
                    "blocked": True,
                    "data": odgovor,
                    "confidence": "LOW", "top_score": top_score,
                    "top_article": top_article, "top_law": top_law,
                }

        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška [confidence=%s]: %s", confidence, pravna_greska)
            return {"status": "success", "blocked": True, "data": _odgovor_pravna_greska(pravna_greska)}

        odgovor = _srpski_termini(odgovor)
        odgovor = _ogranici_pouzdanost(odgovor)
        odgovor = ukloni_zabranjeni_tekst(odgovor, tip)
        odgovor = _injektuj_misljenja_blok(odgovor, _processed_misljenja)
        if "--- IZVOR" not in odgovor and "--- HIJERARHIJA IZVORA" not in odgovor:
            odgovor = _dodaj_izvor(odgovor, filtrirani)
        odgovor = _dodaj_disclaimer(odgovor)

        rezultat = {
            "status": "success", "data": odgovor,
            "confidence": confidence, "top_score": top_score,
            "top_article": top_article, "top_law": top_law,
        }
        if not history:
            _cache_set(pitanje, rezultat)

        logger.info("Uspešan odgovor [confidence=%s, tip=%s, q=%s]", confidence, tip, log_id)
        return rezultat

    except Exception as e:
        logger.error("ASK_AGENT GREŠKA: %s: %s", type(e).__name__, str(e)[:300])
        logger.exception("ASK_AGENT stacktrace")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}


def ask_nacrt(vrsta: str, opis: str) -> dict:
    """
    Generisanje nacrta pravnog dokumenta.
    Guard v2.0 (Commit 2/3): RAG inject before LLM + _proveri_halucinaciju after.
    """
    try:
        # T1: Fetch RAG context for this document type (NACRT guard, Commit 2/3)
        kontekst_docs = _dohvati_nacrt_kontekst(vrsta)

        # PII stripping pre slanja na OpenAI (Basic API tier — bez DPA)
        user_content = (
            f"Vrsta dokumenta: {vrsta}\n\n"
            f"Činjenice i okolnosti: {_skini_pii(opis)}"
        )

        # T1: Inject verified article texts as context block (only if fetched)
        if kontekst_docs:
            retrieved_text = "\n\n---\n\n".join(kontekst_docs)
            user_content = (
                f"DOSTUPNI ZAKONI (citiraj ISKLJUČIVO ove u sekciji PRAVNI OSNOV):\n\n"
                f"{retrieved_text}\n\n"
                f"---\n\n"
                + user_content
            )

        odgovor = _pozovi_openai(SYSTEM_PROMPT_NACRT, user_content)

        # T1: Guard — hard block if fabricated articles detected in output
        if kontekst_docs:
            validan, razlog = _proveri_halucinaciju(odgovor, kontekst_docs)
            if not validan:
                logger.warning("[NACRT→BLOCK] Halucinacija v2.0 [vrsta=%s] razlog=%s", vrsta, razlog)
                return {
                    "status": "success",
                    "data": (
                        "[!] UPOZORENJE: Sistem je detektovao pravne reference koje nisu "
                        "verifikovane u dostupnoj bazi zakona RS.\n\n"
                        f"Neproverene reference: {razlog[:150]}\n\n"
                        "Neke pravne reference u nacrtu nisu mogle biti verifikovane i "
                        "uklonjene su. Proverite ručno sve pravne osnove pre upotrebe.\n\n"
                        "Preporučujemo regenerisanje nacrta ili konsultaciju sa advokatom."
                    ),
                }

        # Provera poznatih pravnih grešaka
        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška u nacrtu: %s", pravna_greska)
            return {"status": "success", "data": _odgovor_pravna_greska(pravna_greska)}

        odgovor = _dodaj_disclaimer(odgovor)
        return {"status": "success", "data": odgovor}
    except Exception:
        logger.exception("Greška u ask_nacrt")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}


def ask_analiza(tekst: str, pitanje: str = "") -> dict:
    """
    Analiza pravnog dokumenta.
    Guard v2.0 (Commit 2/3): doc-only citation ban via _proveri_analiza_citate.
    """
    try:
        # PII stripping pre slanja — dokument može sadržati JMBG, adrese, imena stranaka
        tekst_api = _skini_pii(tekst)
        pitanje_api = _skini_pii(pitanje)
        logger.debug("[ANALIZA] tekst_input_len=%d tekst_api_len=%d pitanje_len=%d",
                     len(tekst), len(tekst_api), len(pitanje_api))
        logger.debug("[ANALIZA] tekst_api preview: %r", tekst_api[:200])

        # T3: Extract all article citations from uploaded document (before LLM call)
        allowed_articles = _ekstrahuj_clanove_iz_dokumenta(tekst_api)
        logger.info("[ANALIZA] Allowed articles from document: %s (total=%d)",
                    sorted(allowed_articles)[:15], len(allowed_articles))
        if not allowed_articles:
            logger.warning("[ANALIZA] allowed_articles=EMPTY — dokument ne sadrži eksplicitne 'Član N' reference; "
                           "svaka LLM citacija člana biće blokirana (_proveri_analiza_citate dizajn)")

        user_content = ""
        if pitanje_api.strip():
            user_content += f"SPECIFIČNO PITANJE: {pitanje_api.strip()}\n\n"
        user_content += f"DOKUMENT ZA ANALIZU:\n{tekst_api}"
        odgovor = _pozovi_openai(SYSTEM_PROMPT_ANALIZA, user_content)
        logger.debug("[ANALIZA] LLM odgovor len=%d preview: %r", len(odgovor), odgovor[:300])

        # T3: Guard — only allow articles that were in the uploaded document
        validan, razlog = _proveri_analiza_citate(odgovor, allowed_articles)
        if not validan:
            logger.warning("[ANALIZA→BLOCK] Halucinacija — novi članovi van dokumenta: %s", razlog)
            return {
                "status": "success",
                "data": (
                    "[!] ANALIZA BLOKIRANA: Sistem je detektovao pravne reference "
                    "koje nisu sadržane u dostavljenom dokumentu.\n\n"
                    f"Neproverene reference: {razlog[:200]}\n\n"
                    "Analiza je sadržala reference koje nisu u dostavljenom dokumentu. "
                    "Sistem ne dodaje nove pravne reference pri analizi.\n\n"
                    "Preporučujemo: eksplicitno navedite relevantne zakonske odredbe u "
                    "dokumentu, ili se obratite advokatu za pravnu analizu."
                ),
            }
        logger.debug("[ANALIZA] guard=PASS, validan=True")

        # Provera poznatih pravnih grešaka
        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška u analizi: %s", pravna_greska)
            return {"status": "success", "data": _odgovor_pravna_greska(pravna_greska)}

        odgovor = _ogranici_pouzdanost(odgovor)
        odgovor = _dodaj_disclaimer(odgovor)
        logger.info("[ANALIZA] OK — odgovor len=%d", len(odgovor))
        return {"status": "success", "data": odgovor}
    except Exception:
        logger.exception("Greška u ask_analiza")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo." + DISCLAIMER}


# ─── Forenzički Legal Audit — V2 pipeline ────────────────────────────────────

SYSTEM_PROMPT_ANALIZA_V2 = """Ti si iskusan pravni forenzičar za advokate u Srbiji.
Analiziraš pravni dokument koji ti je dostavljen u segmentima sa eksplicitnim ID-jevima (npr. [clause_3], [izreka]).
Vraćaš ISKLJUČIVO validan JSON bez markdown fences-ova, bez preambule, bez zaključnih komentara.

ŠEMA ODGOVORA (vrati TAČNO ovu strukturu):
{
  "document_type": "<ugovor|presuda|resenje|ostalo>",
  "findings": [
    {
      "id": "f1",
      "category": "<pravni_rizik|procesni_rizik|rok|dokazni_problem|neuskladjenost|finansijski>",
      "severity": "<nizak|srednji|visok|kritican>",
      "clause_ref": "<ID segmenta iz konteksta ILI null>",
      "clause_excerpt": "<DOSLOVAN citat iz klauzule, max 200 znakova, ILI null>",
      "law_ref": "<npr. 'član 178 Zakona o radu' ILI null>",
      "finding": "<konkretan opis problema>",
      "suggested_fix": "<predlog izmene ILI null>",
      "confidence": <0-100>
    }
  ],
  "missing_clauses": [
    {
      "clause_name": "<naziv klauzule>",
      "why_it_matters": "<zašto izostavljanje pravi rizik>",
      "suggested_text": "<predlog formulacije ILI null>"
    }
  ],
  "financial_exposure": {
    "max_total_exposure_rsd": <broj ILI null>,
    "items": [
      {"type": "<ugovorna_kazna|kamata|odsteta|penal>", "clause_ref": "<ID|null>", "amount_or_formula": "<tekst>", "notes": "<tekst>"}
    ]
  },
  "litigation_readiness": {
    "applicable": <true|false>,
    "evidence_gaps": [{"issue": "<tekst>", "clause_ref": "<ID|null>"}],
    "procedural_defects": [{"issue": "<tekst>", "clause_ref": "<ID|null>"}],
    "deadline_risks": [{"issue": "<tekst>", "deadline_type": "<zastarelost|otkazni_rok|zalbeni_rok|drugi>", "clause_ref": "<ID|null>"}]
  },
  "attack_surface": [
    {"vulnerability": "<kako protivnička strana može napasti ovu odredbu>", "clause_ref": "<ID|null>", "severity": "<nizak|srednji|visok>"}
  ],
  "low_confidence_findings": [],
  "legacy_text": "<plain-text rezime po starom formatu: PRAVNI OSNOV, ANALIZA, IDENTIFIKOVANI RIZICI, PREPORUKE, POUZDANOST>"
}

APSOLUTNA PRAVILA (kršenje = netačan izveštaj):

1. CLAUSE_REF: svaki finding MORA imati clause_ref koji odgovara TAČNOM ID-u iz poslatih segmenata (npr. "clause_3"), ILI null ako se radi o čisto pravnoj napomeni bez direktne klauzule. NE izmišljaj ID-jeve koji nisu u segmentima.

2. CLAUSE_EXCERPT: mora biti DOSLOVAN citata iz dokumenta (kopiraj bukvalno). Nikad ne parafrazi. Ako ne možeš da citiraš doslovno — postavi null.

3. LAW_REF: ako nisi siguran u tačan broj člana — postavi null. Ne izmišljaj članove zakona. Citirati smeš SAMO zakone koji su eksplicitno navedeni u dokumentu ILI koji su direktno primenjivi na sadržaj dokumenta (ZR, ZOO, ZPP, ZDI, PZ, USTAV).

4. CONFIDENCE: 0-100. Ako je < 70 — finding ide u low_confidence_findings array umesto u findings, i tu postavi reason_excluded.

5. SEVERITY: koristiš isključivo — nizak, srednji, visok, kritican. Backend mapira na score (nizak=20, srednji=50, visok=80, kritican=100).

6. LEGACY_TEXT: uvek popuni — plain-text sa sekcijama PRAVNI OSNOV / ANALIZA / IDENTIFIKOVANI RIZICI / PREPORUKE / POUZDANOST. Ovo osigurava kompatibilnost sa postojećim sistemom.

7. NIJE MOGUĆE POTVRDITI: ako nisi siguran u nalaz → postavi confidence < 70 i premesti u low_confidence_findings sa reason_excluded = "insufficient_evidence".

JEZIK: srpski ekavica, dijakritika obavezna. Pravna terminologija tačna."""


def ask_analiza_v2(
    segmented_doc,     # SegmentedDocument
    pitanje: str = "",
    timeout: float = 55.0,
) -> dict:
    """
    Forenzički Legal Audit — V2 pipeline.

    Koristi segmentirani dokument (sa eksplicitnim ID-jevima klauzula),
    vraća validovani JSON Executive Report.

    Returns:
        dict sa executive_summary, findings, missing_clauses, itd.
    """
    from analiza.validator import run_validation_pipeline
    import json as _json

    try:
        tekst_api = _skini_pii(segmented_doc.full_text)
        pitanje_api = _skini_pii(pitanje) if pitanje else ""

        # Izvuci member articles za citation guard (isti mehanizam kao ask_analiza)
        allowed_articles = _ekstrahuj_clanove_iz_dokumenta(tekst_api)
        logger.info("[ANALIZA_V2] allowed_articles=%d char_count=%d segments=%d",
                    len(allowed_articles), segmented_doc.char_count, segmented_doc.segment_count)

        # Napravi mock segmented_doc sa pii-stripped tekstom za LLM
        from analiza.segmenter import SegmentedDocument as SD, Segment
        stripped_doc = SD(
            doc_type=segmented_doc.doc_type,
            segments=[
                Segment(
                    id=s.id,
                    type=s.type,
                    naslov=s.naslov,
                    tekst=_skini_pii(s.tekst),
                    start_offset=s.start_offset,
                    end_offset=s.end_offset,
                )
                for s in segmented_doc.segments
            ],
            full_text=tekst_api,
            char_count=len(tekst_api),
        )

        # Gradi user content sa segmentiranim dokumentom
        user_content = ""
        if pitanje_api.strip():
            user_content += f"SPECIFIČNO PITANJE: {pitanje_api.strip()}\n\n"

        # Za dugačke dokumente: skraćeni prikaz segmenata (max 2000 ch per segment)
        max_chars = 1800 if stripped_doc.char_count > 12000 else 2500
        user_content += stripped_doc.to_llm_context(max_chars_per_segment=max_chars)

        # Dodaj full_text ako je dokument kraći (za excerpt matching)
        if stripped_doc.char_count <= 8000:
            user_content += f"\n\nPUNI TEKST (za reference):\n{tekst_api[:8000]}"

        logger.debug("[ANALIZA_V2] user_content len=%d", len(user_content))

        # Pozovi GPT-4o sa JSON mode i povećanim max_tokens
        raw = _pozovi_openai(
            SYSTEM_PROMPT_ANALIZA_V2,
            user_content,
            model="gpt-4o",
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        logger.debug("[ANALIZA_V2] raw len=%d preview: %r", len(raw), raw[:200])

        # Retry lambda za validator
        def _retry():
            return _pozovi_openai(
                SYSTEM_PROMPT_ANALIZA_V2,
                "Vrati ISKLJUČIVO validan JSON prema šemi. Bez preambule.\n\n" + user_content,
                model="gpt-4o",
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

        # Pokreni validation pipeline
        result = run_validation_pipeline(raw, stripped_doc, retry_fn=_retry)

        # Preslikaj document_type iz segmentera ako LLM nije vratio
        if not result.get("document_type"):
            result["document_type"] = segmented_doc.doc_type

        logger.info("[ANALIZA_V2] OK — findings=%d missing=%d score=%s",
                    len(result.get("findings", [])),
                    len(result.get("missing_clauses", [])),
                    (result.get("executive_summary") or {}).get("overall_risk_score", "?"))

        return {"status": "success", "data": result}

    except Exception:
        logger.exception("Greška u ask_analiza_v2")
        return {
            "status": "error",
            "message": "Sistem je trenutno zauzet. Pokušajte ponovo.",
            "data": None,
        }


# ─── CLI za testiranje ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Vindex AI — Pravni asistent (CLI mod)")
    print("Unesite 'exit' za izlaz.\n")
    while True:
        q = input("Pitanje: ").strip()
        if q.lower() == "exit":
            break
        if not q:
            continue
        rezultat = ask_agent(q)
        print("\n" + ("=" * 60))
        print(rezultat.get("data", rezultat.get("message", "Greška")))
        print("=" * 60 + "\n")
