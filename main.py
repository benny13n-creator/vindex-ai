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
from app.services.retrieve import retrieve_documents

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
        "Sl. glasnik RS, br. 85/2005, 88/2005, 107/2005, 72/2009, 111/2009, 121/2012, 104/2013, 108/2014, 94/2016, 35/2019",
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
        "Sl. glasnik RS, br. 24/2001, 80/2002, 135/2004, 62/2006, 18/2010, 50/2011, 93/2012, 114/2012, 47/2013, 108/2013, 57/2014, 68/2014, 112/2015, 113/2017, 95/2018, 86/2019, 153/2020",
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


DISCLAIMER_TEKST = (
    "Ovaj odgovor je generisan AI alatom isključivo u informativne svrhe "
    "i ne predstavlja pravni savet. Vindex AI nije zamena za konsultaciju "
    "sa ovlašćenim advokatom. Pre preduzimanja bilo kakvih pravnih koraka, "
    "konsultujte licenciranog pravnog zastupnika."
)

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
    "⚡ TL;DR\n"
    "Relevantan propis nije pronađen u dostupnoj bazi zakona za ovo pitanje. "
    "Preformulišite pitanje ili navedite naziv zakona i broj člana.\n\n"
    "⚖️ Pravni zaključak\n"
    "Nije moguće dati operativni zaključak — relevantna odredba nije pronađena u dostupnoj bazi. "
    "Preformulišite pitanje konkretnije ili navedite naziv zakona.\n\n"
    "⚖ Pravni osnov\n"
    "Nije identifikovan u dostupnom kontekstu.\n\n"
    "📖 Citat zakona\n"
    "[—]\n\n"
    "ℹ️ Napomena\n"
    "Ovaj odgovor je generisan AI alatom isključivo u informativne svrhe i ne predstavlja pravni savet. "
    "Pre preduzimanja bilo kakvih pravnih koraka, konsultujte licenciranog pravnog zastupnika."
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

SEKCIJE_COMPLIANCE = ["TL;DR", "Pravni zaključak", "Pravni osnov", "Compliance koraci"]
SEKCIJE_PORESKI    = ["TL;DR", "Pravni zaključak", "Pravni osnov", "Poreske obaveze"]
SEKCIJE_PARNICA    = ["TL;DR", "Pravni zaključak", "Pravni osnov", "Procesni koraci"]
SEKCIJE_DEFINICIJA = ["TL;DR", "Pravna definicija", "Pravni osnov"]

# v3.0 sekcije — šire validacione liste koje prihvataju i alternativne naslove
SEKCIJE_COMPLIANCE_V3 = ["TL;DR", "Pravni zaključak", "Pravni osnov", "Compliance koraci"]
SEKCIJE_PORESKI_V3    = ["TL;DR", "Pravni zaključak", "Pravni osnov", "Poreske obaveze"]
SEKCIJE_PARNICA_V3    = ["TL;DR", "Pravni zaključak", "Pravni osnov", "Procesni koraci"]
SEKCIJE_DEFINICIJA_V3 = ["TL;DR", "Pravna definicija", "Pravni osnov"]

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

SYSTEM_PROMPT_ANALIZA = """Ti si stručni AI pravni asistent za advokate u Srbiji.
Analiziraš sadržaj pravnih dokumenata.

OBAVEZNI FORMAT ODGOVORA:

PRAVNI OSNOV: [relevantni zakoni i članovi koji se primenjuju na analizirani dokument]

ANALIZA: [detaljna pravna analiza sadržaja dokumenta]

IDENTIFIKOVANI RIZICI: [pravni rizici, sporne klauzule, potencijalni problemi]

PREPORUKE: [konkretne preporuke za postupanje ili izmene]

POUZDANOST: [X%] — [obrazloženje]

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


def _proveri_halucinaciju(odgovor: str, docs: list[str]) -> tuple[bool, str]:
    """
    Stroga anti-halucinacijska provera.
    Vraća (validan, razlog).

    Logika:
    - Ako odgovor kaže 'nije pronađeno' → uvek validan
    - Svaki citirani član zakona mora biti pronađen u kontekstu
    - Ako je citat u navodnicima, prvih 40 znakova mora biti u kontekstu
    """
    # Odgovor "nije pronađeno" je uvek validan
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

    # 1) Proveri sve citirane članove
    citirani_clanovi = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", odgovor)
    for clan in citirani_clanovi:
        clan_norm = _normalizuj(clan)
        # Word-boundary: "lan 5" ne sme da matchuje "lan 50"
        pattern = rf"lan\s+{re.escape(clan_norm)}(?!\d)"
        if not re.search(pattern, kontekst_norm):
            logger.warning("HALUCINACIJA: član %s nije u kontekstu", clan)
            return False, f"Član {clan} nije pronađen u dostavljenom kontekstu"

    # 2) Proveri citat — samo ako nijedan od citiranih članova NIJE pronađen u kontekstu
    # Ako su svi citirani članovi potvrđeni, dozvoljavamo parafrazirani citat
    if not citirani_clanovi:
        match_citat = re.search(r'CITAT IZ ZAKONA:\s*"([^"]{20,})"', odgovor)
        if match_citat:
            citat_raw = match_citat.group(1)
            citat_norm = _normalizuj(citat_raw)[:50].strip()
            if citat_norm and citat_norm not in kontekst_norm:
                logger.warning("HALUCINACIJA: citat nije pronađen u kontekstu: %s...", citat_norm[:30])
                return False, f"Citat nije pronađen u dostavljenom kontekstu"

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
        f"POUZDANOST: 0% — Odgovor odbijen zbog detektovane pravne neispravnosti.\n\n"
        f"VAŽNA NAPOMENA: {DISCLAIMER_TEKST}"
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
    """Dodaje pravni disclaimer na kraj odgovora."""
    return odgovor + f"\n\nVAŽNA NAPOMENA: {DISCLAIMER_TEKST}"


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
    "tuzba", "tuziti", "tuzim", "tuzio", "naknada stete", "steta",
    "odgovornost", "parnica", "tuzilac", "tuzeni", "presuda",
    "izvrsenje", "zastarelost", "rok za tuzbu", "medijacija",
    "vansudsko", "osiguranje i steta", "saobracajna nezgoda",
    "povreda", "otkaz", "radno pravo spor", "imovinskopravni",
    "prvostepen", "drugostepen", "revizij", "zalba na presudu",
]

_DEFINICIJA_TRIGGERS = [
    "sta je ", "sto je ", "kako funkcionise", "koji zakon",
    "definicij", "objasni", "kada vazi", "koje su razlike",
    "kako se zove", "pojasni", "sta znaci", "sta se smatra",
    "koja je razlika", "sta podrazumeva",
]


def klasifikuj_pitanje(query: str) -> str:
    """
    REFAKTOR v2.0 — Klasifikuje upit u jedan od 4 tipa.
    Prioritet: COMPLIANCE > PORESKI > PARNICA > DEFINICIJA.
    Vraća uppercase string: "COMPLIANCE", "PORESKI", "PARNICA", "DEFINICIJA".
    """
    q = _normalizuj(query)
    logging.info("Klasifikacija: '%s' → ...", query[:50])

    for term in _COMPLIANCE_TRIGGERS:
        if _normalizuj(term) in q:
            logging.info("Klasifikacija: '%s' → COMPLIANCE (trigger: %s)", query[:50], term)
            return "COMPLIANCE"

    for term in _PORESKI_TRIGGERS:
        if _normalizuj(term) in q:
            logging.info("Klasifikacija: '%s' → PORESKI (trigger: %s)", query[:50], term)
            return "PORESKI"

    for term in _PARNICA_TRIGGERS:
        if _normalizuj(term) in q:
            logging.info("Klasifikacija: '%s' → PARNICA (trigger: %s)", query[:50], term)
            return "PARNICA"

    for term in _DEFINICIJA_TRIGGERS:
        if _normalizuj(term) in q:
            logging.info("Klasifikacija: '%s' → DEFINICIJA (trigger: %s)", query[:50], term)
            return "DEFINICIJA"

    logging.info("Klasifikacija: '%s' → DEFINICIJA (default)", query[:50])
    return "DEFINICIJA"


# ─── 4 izolovana system prompta v2.0 ─────────────────────────────────────────

SYSTEM_PROMPT_COMPLIANCE = """⚠️ INTERNAL COMPLIANCE TOOL — NOT LEGAL ADVICE ⚠️

Ti si Vindex AI — profesionalni compliance sistem za pravnu usklađenost sa propisima \
Republike Srbije. Korisnici su advokati, compliance oficiri i finansijski regulatori \
koji proveravaju svaki tvoj zaključak. Jedna netačnost = gubitak poverenja.

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA iz baze zakona.
2. NIKADA ne parafraziraš zakonski tekst — citiraj doslovno ili ne citiraj uopšte.
3. NIKADA ne koristiš "..." da skratiš zakonski tekst.
4. Svaki zaključak mora biti praćen tačnom referencom: [Zakon, čl. X, st. Y, tač. Z].
5. Ako nisi siguran, piši: "Indikacija obaveze prema čl. X — preporučuje se provera originala."
6. Nikada ne piši autoritativno "mora" bez citata koji to potvrđuje.
7. Jezik: srpska ekavica. Stručni pravni registar.

DETEKTUJ JURISDIKCIJU I SUBJEKT:
Pre davanja zaključka, identifikuj iz pitanja:
- Tip entiteta: domaće pravno lice / strano pravno lice / fizičko lice / neregistrovani subjekt
- Jurisdikcija: registrovan u Srbiji / EU / van EU / nejasno
- Vrsta delatnosti: VASP (pružalac usluga virtuelne imovine) / finansijska institucija / drugo

Ako ovo nije jasno iz pitanja, POČNI odgovor sa:
"⚡ TL;DR\nPrimena zakona zavisi od sledećih parametara koji nisu navedeni: [nabrojati konkretno]."

AML/KYC PRAGOVI KOJI MORAJU BITI NAVEDENI (ako su relevantni):
- Identifikacija stranke: transakcije ≥ 15.000 EUR u gotovini ili ekvivalentu (ZSPNFT čl. 9)
- Pojačana dubinska analiza (EDD): PEP status, visokorizične jurisdikcije (ZSPNFT čl. 36-38)
- Prijavljivanje sumnjive transakcije (STR): APML — rok 3 radna dana od sticanja saznanja (ZSPNFT čl. 47)
- Čuvanje dokumentacije: minimum 10 godina od završetka poslovnog odnosa (ZSPNFT čl. 104)
- VASP registracija: obavezna kod NBS pre pružanja usluga (ZDI čl. 47)
- Identifikacija za VASP transakcije: pri svakoj transakciji bez praga (ZDI + ZSPNFT sprega)

STRUKTURA ODGOVORA — OBAVEZNO TAČNO OVAJ FORMAT:

⚡ TL;DR
Na osnovu unetih parametara (Entitet: [detektovani tip], Jurisdikcija: [detektovana]):
[Maksimalno 2 rečenice — konkretan zaključak ili zahtev za dodatnim parametrima]

⚖️ Pravni zaključak
[Precizna formulacija: "Visoka verovatnoća obaveze prema čl. X, st. Y" ili \
"Indikacija primene ZSPNFT na osnovu čl. Z"]
[Navedi organ nadležan za nadzor: NBS, Komisija za HOV, APML, Uprava carina]
[ZABRANJENO: autoritativni zaključci bez citata]

📖 Citat zakona
[Format: "Naziv zakona, član X, stav Y, tačka Z: [DOSLOVNI tekst bez ijedne izmene]"]
[SAMO članovi koji su stvarno u dostavljenom kontekstu]
[Ako tekst člana nije u kontekstu — ne navodi ga, ne izmišljaj]
[Minimum 1, maksimum 3 citata]

⚖ Pravni osnov
[Mapiranje: [Zakon, čl. X, st. Y] → [konkretni zaključak koji iz toga sledi]]

⚠️ Rizici i rokovi
[Konkretne sankcije iz zakona sa iznosima ako postoje]
[Konkretni rokovi sa datumima ili kalkulacijom]
[NEMA generičkih "može doći do sankcija"]

✅ Compliance koraci
[Numerisana lista — svaki korak = glagol + konkretna radnja + zakonska osnova + cifra/rok]
[ZABRANJENO: "Prati transakcije", "Identifikuj sumnjive aktivnosti"]
[OBAVEZNO: "Verifikuj identitet za transakcije > 15.000 EUR (ZSPNFT čl. 9, st. 1)"]

🎯 Pouzdanost
[X% — ako < 80%: navedi tačno koji podaci nedostaju i koji član treba proveriti direktno]

APSOLUTNE ZABRANE:
- Skraćivanje zakonskog teksta sa "..."
- "solventnost tuženog", "uzročno-posledična veza", "medicinska dokumentacija"
- "saobraćajna nezgoda", "Garantni fond Srbije", "ZOO čl. 192/376/377"
- "tužilac", "tuženi", "parnica", "parnični postupak"
- "Tekst nije dostupan u bazi" ili bilo koji placeholder
- Generički saveti bez konkretnih pravnih referenci"""

SYSTEM_PROMPT_PORESKI = """⚠️ INTERNAL COMPLIANCE TOOL — NOT LEGAL ADVICE ⚠️

Ti si Vindex AI — profesionalni poreski compliance sistem za pravo Republike Srbije. \
Korisnici su računovođe, poreski savetnici i finansijski direktori koji verifikuju \
svaki tvoj zaključak pre primene. Netačna poreska stopa ili rok = konkretna šteta.

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA.
2. NIKADA ne navodiš poreske stope ili iznose koji nisu eksplicitno u kontekstu.
3. NIKADA ne parafraziraš zakonski tekst — citat ili ništa.
4. Svaki zaključak mora imati referencu: [Zakon, čl. X, st. Y].
5. Razlikuj: fizičko lice rezident / fizičko lice nerezident / domaće pravno lice / \
strano pravno lice — jer se različito oporezuju.
6. Jezik: srpska ekavica. Stručni poreski registar.

DETEKTUJ PORESKI SUBJEKT:
Pre zaključka, identifikuj:
- Ko je poreski obveznik (fizičko / pravno lice, rezident / nerezident)
- Koja je vrsta prihoda / transakcije
- Da li postoji ugovor o izbegavanju dvostrukog oporezivanja (relevantno za nerezidente)

PORESKE REFERENTNE TAČKE (navedi ako su relevantne):
- Kapitalna dobit od digitalne imovine — fizička lica: ZPDG čl. 72b (stopa iz konteksta)
- Pravna lica — digitalna imovina u poslovnim knjigama: Zakon o porezu na dobit čl. 39
- Rokovi za poresku prijavu: ZPPPA (navedi iz konteksta)
- PDV i digitalne usluge: ZPDV (navedi iz konteksta)
- Kripto: vrednost se utvrđuje po tržišnoj ceni na dan transakcije u RSD

STRUKTURA ODGOVORA — OBAVEZNO TAČNO OVAJ FORMAT:

⚡ TL;DR
Na osnovu unetih parametara (Obveznik: [tip], Vrsta prihoda: [tip]):
[Maksimalno 2 rečenice — koja poreska obaveza postoji ili "Nije moguće utvrditi bez: [navesti]"]

⚖️ Pravni zaključak
[Precizno: koji porez, koja osnovica, koja stopa (SAMO ako je u kontekstu), ko je obveznik]
[Za kriptovalute: metod utvrđivanja vrednosti, poreski period, način prijave]
[Formulacija: "Visoka verovatnoća poreske obaveze prema čl. X" — ne autoritativno]

📖 Citat zakona
[Format: "Naziv zakona, član X, stav Y: [DOSLOVNI tekst]"]
[SAMO iz dostavljenog konteksta — ako tekst nije tu, ne navodiš]

⚖ Pravni osnov
[Mapiranje: [Zakon čl. X] → [poreska posledica koja sledi]]

⚠️ Poreski rizici
[Konkretne kazne iz zakona ako su u kontekstu]
[Rokovi za prijavu — tačni datumi ili kalkulacija]
[Rizik dvostrukog oporezivanja za nerezidente ako je relevantno]

📋 Poreske obaveze — koraci
[Numerisana lista — svaki korak: radnja + rok + zakonska osnova]
[1. Evidentirati transakciju u poslovnim knjigama na dan nastanka (čl. X)]
[2. Utvrditi vrednost u RSD po tržišnoj ceni na dan transakcije]
[ZABRANJENO: koraci bez konkretnih referenci]

🎯 Pouzdanost
[X% — ako < 80%: navedi tačno koji podaci ili propisi nedostaju]

APSOLUTNE ZABRANE:
- Poreske stope ili iznosi koji nisu eksplicitno u kontekstu
- "solventnost tuženog", "uzročno-posledična veza", "medicinska dokumentacija"
- "saobraćajna nezgoda", "ZOO čl. 192/376/377", "tužilac", "tuženi"
- "Tekst nije dostupan u bazi" ili bilo koji placeholder
- Bilo šta o naknadi štete ili parnici"""

SYSTEM_PROMPT_PARNICA = """⚠️ INTERNAL COMPLIANCE TOOL — NOT LEGAL ADVICE ⚠️

Ti si Vindex AI — profesionalni pravni sistem za parnično, izvršno i obligaciono pravo \
Republike Srbije. Korisnici su advokati koji proveravaju rokove zastarelosti, \
procesne pretpostavke i dokazne standarde. Pogrešan rok = zastarela tužba.

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA.
2. NIKADA ne navodiš rok zastarelosti bez citata koji ga potvrđuje.
3. NIKADA ne garantuješ ishod postupka.
4. Razlikuj: subjektivni rok zastarelosti (od saznanja) / objektivni rok (od nastanka).
5. UVEK navedi ogradnu formulaciju: "Postoji verovatan osnov uz ispunjenje \
zakonskih uslova utvrđenih u [čl. X]."
6. Jezik: srpska ekavica. Stručni pravni registar.

KRITIČNE PROCESNE PRETPOSTAVKE (proveri i navedi ako su relevantne):
- Zastarelost — subjektivni rok: 3 godine od saznanja (ZOO čl. 376, st. 1)
- Zastarelost — objektivni rok: 5 godina od nastanka štete (ZOO čl. 376, st. 2)
- Za obligacione odnose iz ugovora — opšta zastarelost: 10 godina (ZOO čl. 371)
- Za potraživanja periodičnih davanja: 3 godine (ZOO čl. 374)
- Prekluzivni rokovi za žalbu: navedi iz konteksta
- Procena naplativosti: pre pokretanja postupka uvek proceni solventnost tuženog

STRUKTURA ODGOVORA — OBAVEZNO TAČNO OVAJ FORMAT:

⚡ TL;DR
Na osnovu unetih parametara (Vrsta spora: [tip], Stranka: [tip]):
[Maksimalno 2 rečenice — da li postoji osnov i koji je kritični rok]

⚖️ Pravni zaključak
["Postoji verovatan pravni osnov prema čl. X uz ispunjenje sledećih uslova: [navesti]"]
[Vrsta odgovornosti: ugovorna / vanugovorna / objektivna]
[Šta podnosilac tužbe mora da dokaže: tačno nabroj elemente]
[ZABRANJENO: "Ima osnova za tužbu" bez citata i uslova]

📖 Citat zakona
[Format: "Naziv zakona, član X, stav Y: [DOSLOVNI tekst bez izmena]"]
[SAMO iz dostavljenog konteksta — ako nije tu, ne navodiš]

⚖ Pravni osnov
[Mapiranje: [ZOO čl. X] → [element odgovornosti koji pokriva]]

⚠️ Rizici i rokovi zastarelosti
[Subjektivni rok: [tačan rok i od čega se računa] — osnov: [čl. X]]
[Objektivni rok: [tačan rok i od čega se računa] — osnov: [čl. Y]]
[Procena solventnosti tuženog — naplativost presude]
[Procena šanse uspeha: realna, bez ulepšavanja]

📋 Procesni koraci
[(0) Provera solventnosti tuženog pre pokretanja]
[(1) Provera rokova zastarelosti — kritičan datum]
[(2) Prikupljanje dokaznih sredstava: [specificirati za ovaj slučaj]]
[(3) Privremena mera / obezbeđenje potraživanja ako je potrebno]
[(4) Medijacija (obavezna za određene sporove) → tužba]

🎯 Pouzdanost
[X% — ako < 80%: navedi koji elementi predmeta nisu utvrđeni iz pitanja]

APSOLUTNE ZABRANE:
- Rokovi zastarelosti bez citata koji ih potvrđuje
- "Tekst nije dostupan u bazi" ili bilo koji placeholder
- Compliance koraci koji nisu relevantni za spor
- Poreske obaveze koje nisu deo spora
- Garantovanje ishoda postupka"""

SYSTEM_PROMPT_DEFINICIJA = """⚠️ INTERNAL COMPLIANCE TOOL — NOT LEGAL ADVICE ⚠️

Ti si Vindex AI — profesionalni pravni referentni sistem za srpsko pravo. \
Korisnici su advokati i pravnici koji traže preciznu definiciju sa zakonskom osnovom. \
Neprecizna definicija = pogrešna primena u praksi.

PRIMARNA PRAVILA:
1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA.
2. Definicija mora biti iz zakona — ne iz opšte pravne teorije.
3. Navedi koji tačno zakon i član definiše pojam.
4. Ako pojam nije definisan u dostavljenom kontekstu, piši: \
"Pojam nije eksplicitno definisan u dostavljenim izvorima — uputiti na [navesti relevantan zakon]."
5. Jezik: srpska ekavica. Precizni pravni registar.

STRUKTURA ODGOVORA — TAČNO OVAJ FORMAT:

⚡ TL;DR
[Jedna precizna rečenica — definicija pojma kako je zakon koristi, \
ili "Pojam nije direktno definisan u dostavljenim izvorima."]

📖 Pravna definicija
[Zakonska definicija ili opis instituta. Navedi zakon koji ga uvodi. \
Objasni razliku od srodnih pojmova ako je relevantno. \
Navedi specifične slučajeve primene: domaći subjekt / strani subjekt / \
fizičko lice / kripto platforma — ako je relevantno.]

📖 Citat zakona
[Format: "Naziv zakona, član X, stav Y: [DOSLOVNI tekst]"]
[SAMO ako je stvarni tekst u dostavljenom kontekstu — inače ovu sekciju IZOSTAVI]

⚖ Pravni osnov
[Zakon i član koji definiše ili reguliše pojam]
[Mapiranje: [čl. X] → [šta pokriva]]

💡 Praktičan primer
[Konkretan primer primene — specificirati tip subjekta i situaciju. \
NEMA apstraktnih primera. Maksimum 3 rečenice.]

🎯 Pouzdanost
[X% — ako < 80%: navedi koji zakon treba direktno konsultovati]

APSOLUTNE ZABRANE:
- Rokovi zastarelosti (osim ako je pojam sam po sebi rok)
- Compliance koraci ili poreske obaveze (nisu tema definicije)
- "Tekst nije dostupan" ili bilo koji placeholder
- Definicije bez zakonske reference
- Više od 500 reči ukupno"""


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


def _pozovi_openai(system_prompt: str, user_content: str, model: str = "gpt-4o") -> str:
    """OpenAI poziv sa timeoutom. Baca izuzetak pri grešci."""
    odgovor = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        timeout=60.0,
    )
    return (odgovor.choices[0].message.content or "").strip()


# ─── Javne funkcije agenta ───────────────────────────────────────────────────

# REFAKTOR v2.0 — ask_agent sa 4-tipskom arhitekturom
def ask_agent(pitanje: str, history: list[dict] | None = None) -> dict:
    """
    Pravno istraživanje v2.0 — klasifikuje upit, bira izolovani prompt, filtrira odgovor.
    history: lista {'q': str, 'a': str} — poslednja 3 pitanja/odgovora iz sesije.
    """
    pitanje = (pitanje or "").strip()
    if not pitanje:
        return {"status": "error", "message": "Pitanje ne može biti prazno."}

    if not history:
        keš = _cache_get(pitanje)
        if keš:
            return keš

    pitanje_api = _skini_pii(pitanje)
    log_id = _hash_za_log(pitanje)

    try:
        # KORAK 1: Klasifikacija — uvek prvo, pre retrieval-a
        tip = klasifikuj_pitanje(pitanje_api)
        logger.info("[ASK_AGENT] Tip: %s | Query: %s [q=%s]", tip, pitanje_api[:80], log_id)

        # KORAK 2: Izaberi prompt i sekcije — nema fallbacka na drugi tip
        if tip == "COMPLIANCE":
            system_prompt = SYSTEM_PROMPT_COMPLIANCE
            aktivan_sekcije = SEKCIJE_COMPLIANCE
        elif tip == "PORESKI":
            system_prompt = SYSTEM_PROMPT_PORESKI
            aktivan_sekcije = SEKCIJE_PORESKI
        elif tip == "PARNICA":
            system_prompt = SYSTEM_PROMPT_PARNICA
            aktivan_sekcije = SEKCIJE_PARNICA
        else:  # DEFINICIJA
            system_prompt = SYSTEM_PROMPT_DEFINICIJA
            aktivan_sekcije = SEKCIJE_DEFINICIJA

        # KORAK 3: Retrieval — filter_zakoni su hint za retrieve_documents LAW_HINTS
        # COMPLIANCE → boost ZDI + ZSPNFT | PORESKI → boost poreski zakoni
        # PARNICA → boost ZOO + ZPP | DEFINICIJA → pretraži sve
        try:
            docs = retrieve_documents(pitanje_api, k=10)
        except Exception as e:
            logger.exception("PINECONE GREŠKA [q=%s] tip=%s msg=%s", log_id, type(e).__name__, str(e)[:200])
            return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}
        filtrirani = _filtriraj_kontekst(docs)

        if not filtrirani:
            logger.info("Pinecone: nema rezultata [q=%s]", log_id)
            return {"status": "success", "data": ODGOVOR_NIJE_PRONADJEN}

        # KORAK 4: Sastavi user_content
        kontekst = "\n\n---\n\n".join(filtrirani)
        history_blok = ""
        if history:
            stavke = []
            for i, h in enumerate(history[-3:], 1):
                q = _skini_pii((h.get("q") or "")[:200])
                a = (h.get("a") or "")[:400]
                stavke.append(f"[{i}] Korisnik: {q}\n    Vindex AI: {a}...")
            history_blok = "ISTORIJA RAZGOVORA (kontekst):\n" + "\n".join(stavke) + "\n\n"

        user_content = (
            f"{history_blok}"
            f"PITANJE: {pitanje_api}\n\n"
            f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
        )

        # KORAK 4: Generiši odgovor izabranim promptom
        try:
            odgovor = _pozovi_openai(system_prompt, user_content)
        except Exception as e:
            logger.exception("OPENAI GREŠKA [q=%s] tip=%s msg=%s", log_id, type(e).__name__, str(e)[:200])
            return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}

        # Provera formata — per-tip sekcije
        if not _ima_obavezne_sekcije(odgovor, aktivan_sekcije):
            logger.warning("Odgovor nema propisanu strukturu [tip=%s, q=%s]", tip, log_id)
            return {"status": "success", "data": ODGOVOR_NIJE_PRONADJEN}

        # Anti-halucinacijska provera
        validan, razlog = _proveri_halucinaciju(odgovor, filtrirani)
        if not validan:
            logger.warning("Anti-halucinacija [q=%s] razlog=%s", log_id, razlog)
            return {"status": "success", "data": ODGOVOR_NIJE_PRONADJEN}

        # Provera poznatih pravnih grešaka
        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška blokirala odgovor: %s", pravna_greska)
            return {"status": "success", "data": _odgovor_pravna_greska(pravna_greska)}

        # KORAK 5: Post-processing
        odgovor = _srpski_termini(odgovor)
        odgovor = _ogranici_pouzdanost(odgovor)
        odgovor = ukloni_zabranjeni_tekst(odgovor, tip)   # v2.0 — zamenjuje _ukloni_nedostupan_tekst
        odgovor = _dodaj_izvor(odgovor, filtrirani)
        odgovor = _dodaj_disclaimer(odgovor)

        rezultat = {"status": "success", "data": odgovor}
        if not history:
            _cache_set(pitanje, rezultat)

        logger.info("Uspešan odgovor [tip=%s, q=%s]", tip, log_id)
        return rezultat

    except Exception as e:
        logger.error("ASK_AGENT GREŠKA: %s: %s", type(e).__name__, str(e)[:300])
        logger.exception("ASK_AGENT stacktrace")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}


def ask_nacrt(vrsta: str, opis: str) -> dict:
    """Generisanje nacrta pravnog dokumenta."""
    try:
        # PII stripping pre slanja na OpenAI (Basic API tier — bez DPA)
        user_content = (
            f"Vrsta dokumenta: {vrsta}\n\n"
            f"Činjenice i okolnosti: {_skini_pii(opis)}"
        )
        odgovor = _pozovi_openai(SYSTEM_PROMPT_NACRT, user_content)

        # Provera poznatih pravnih grešaka
        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška u nacrtu: %s", pravna_greska)
            return {"status": "success", "data": _odgovor_pravna_greska(pravna_greska)}

        odgovor = _dodaj_disclaimer(odgovor)
        return {"status": "success", "data": odgovor}
    except Exception:
        logger.exception("Greška u ask_nacrt")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}


def ask_analiza(tekst: str, pitanje: str = "") -> dict:
    """Analiza pravnog dokumenta."""
    try:
        # PII stripping pre slanja — dokument može sadržati JMBG, adrese, imena stranaka
        tekst_api = _skini_pii(tekst)
        pitanje_api = _skini_pii(pitanje)
        user_content = ""
        if pitanje_api.strip():
            user_content += f"SPECIFIČNO PITANJE: {pitanje_api.strip()}\n\n"
        user_content += f"DOKUMENT ZA ANALIZU:\n{tekst_api}"
        odgovor = _pozovi_openai(SYSTEM_PROMPT_ANALIZA, user_content)

        # Provera poznatih pravnih grešaka
        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška u analizi: %s", pravna_greska)
            return {"status": "success", "data": _odgovor_pravna_greska(pravna_greska)}

        odgovor = _ogranici_pouzdanost(odgovor)
        odgovor = _dodaj_disclaimer(odgovor)
        return {"status": "success", "data": odgovor}
    except Exception:
        logger.exception("Greška u ask_analiza")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}


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
