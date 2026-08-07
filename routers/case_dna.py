# -*- coding: utf-8 -*-
"""
Vindex AI — Case Genome (Single Source of Truth)

Centralni zivi model predmeta — jedini vlasnik istine o predmetu (Core
Consolidation Sec 1.3, 2026-07-22). Napomena za citaoca: docstring je
ranije tvrdio da SVE ostale AI funkcije citaju Genome pre analize — to
NIJE bilo tacno (case_pipeline.py, learning_engine.py i confidence
calibrator nemaju nijednu referencu), forensic audit isti dan potvrdio
gresku kodom. Ispravljena, proverljiva tvrdnja: Evidence Vault
(predmet_dokazi) sada TECE U Genome kao kontekst pri ekstrakciji
(_extract_genome dokazi param) — Genome vise ne ignoriše vec-klasifikovane
činjenice. Ostali potrošači (case pipeline, learning engine) ostaju van
obima ove izmene, evidentirano u docs/architecture/VINDEX_CORE_CONSOLIDATION.md.
Ekstrakcija: pravna teorija, stranke, finansije, strategija, kontradikcije, snaga (0-100%),
explainable score, heat map, ranked evidence, war plan, weakest point, missing evidence.

GET  /api/predmeti/{predmet_id}/case-dna            — ucita Genome
POST /api/predmeti/{predmet_id}/case-dna/refresh    — regenerisi iz dokumenata
POST /api/predmeti/{predmet_id}/case-dna/compare    — poredi dva dokumenta po broju
GET  /api/predmeti/{predmet_id}/case-dna/history    — verzije Genome-a
"""
import asyncio
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService
from shared.llm_retry import llm_retry
from shared.sentry import capture_exception as _sentry_capture
from services.event_bus import EventType
from shared.genome_validator import verify_genome, compute_snaga_score, validate_dok_reference
from shared.contradiction_identity import contradiction_identity

logger = logging.getLogger("vindex.case_genome")
router = APIRouter(prefix="/api/predmeti", tags=["case_dna"])

# ── Genome prompt — centralni objekat sistema ─────────────────────────────────

_GENOME_SYSTEM = """Ti si pravni AI specijalizovan za srpsko pravo. Analiziras dokumenta jednog predmeta
i gradis Case Genome — zivi digitalni model predmeta koji razume cinjenice, dokaze, pravna pitanja, rizike i strategiju.

Vrati SAMO validan JSON (bez markdown):
{
  "pravna_teorija": {
    "pravni_identitet": "Jedna precizna recenica: tip spora + stranke + sustina (npr. 'Ugovorni spor o naknadi stete 1.2M RSD — DOO Petrovic vs. DOO ABC')",
    "sustina_spora": "Sta je tacno sporno izmedju stranaka",
    "osnov_odgovornosti": "Koji pravni osnov se primenjuje sa konkretnim clanom zakona",
    "uzrocna_veza": "Kako se uspostavlja ili osporava veza uzrok-posledica",
    "visina_stete": "Trazeni iznos i metodologija obracuna",
    "relevantni_zakoni": ["ZOO cl. 262", "ZPP cl. 195"]
  },
  "stranke": [
    {"uloga": "tuzilac|tuzeni|svedok|vestak|zastupnik|ostalo", "ime": "Puno ime ili firma", "adresa": "ako poznato", "jmbg_pib": "ako poznato"}
  ],
  "svedoci": [
    {"ime": "...", "uloga": "opisna uloga u predmetu", "vrednost_iskaza": "visoka|srednja|niska", "napomena": "sta potvrdjuje ili osporava"}
  ],
  "vestaci": [
    {"ime": "...", "oblast": "finansije|medicina|gradjevina|IT|ostalo", "nalaz_sazetak": "kratko sta kaze", "napadljivo": true}
  ],
  "finansije": {
    "tuzeni_iznos": "iznos koji tuzilac potrazuje sa valutom",
    "stvarna_steta": "dokazana direktna steta",
    "izgubljena_dobit": "iznos ako se potrazuje",
    "kamate": "zakonska ili ugovorna kamata od kog datuma",
    "sudske_takse": "procena",
    "ukupna_ekspozicija": "maksimalni iznos gubitka za tuzenog"
  },
  "datumi_kljucni": [
    {"opis": "Dogadjaj koji je okidac spora", "datum": "YYYY-MM-DD", "znacaj": "kriticno|bitno|informativno"}
  ],
  "rokovi_kriticni": [
    {"naziv": "Rok zastarelosti/zalbeni rok/sl.", "datum": "YYYY-MM-DD ili null", "opis": "Posledica propustanja", "status": "aktivan|prosao|nepoznat"}
  ],
  "kontradikcije": [
    {"opis": "Tacno sta se kosi (citati ako moguce)", "lokacija_1": "DOK-01 str.X ili opis", "lokacija_2": "DOK-02 str.Y ili opis", "tezina": "kriticna|vazna|manja"}
  ],
  "argumenti_za": ["Konkretan argument sa dokazom koji ide u korist klijenta"],
  "argumenti_protiv": ["Konkretan argument koji ide protiv klijenta ili slabost predmeta"],
  "snaga_predmeta_procent": 0,
  "snaga_faktori": [
    {"faktor": "Naziv faktora (npr. Pisani dokazi)", "uticaj": "+18", "opis": "Zasto ovaj faktor doprinosi snazi predmeta"},
    {"faktor": "Kontradikcije u dokazima", "uticaj": "-8", "opis": "Zasto ovaj faktor slabi predmet"}
  ],
  "heatmap": {
    "cinjenice": 85,
    "dokazi": 62,
    "praksa": 74,
    "vestaci": 31,
    "rizici": 78,
    "rokovi": 60
  },
  "dokazi_rang": [
    {"redni_broj": 7, "naziv": "Naziv fajla", "snaga_score": 92, "zvezdice": 5, "razlog": "Zasto je jak dokaz — direktno dokazuje kljucnu cinjenicu"},
    {"redni_broj": 4, "naziv": "Naziv fajla", "snaga_score": 67, "zvezdice": 3, "razlog": "Posredan dokaz — potvrdjuje ali ne dokazuje direktno"}
  ],
  "najslabija_tacka": {
    "rizik": "Naziv rizika — sta je najslabije u predmetu (konkretno)",
    "kriticnost": 89,
    "preporuka": "Konkretna akcija koja bi popravila ovu slabost",
    "lokacija": "DOK-XX str.Y ili opis, ISTO pravilo kao kontradikcije.lokacija_1 ispod -- prazan string ako slabost nije vezana za jedan konkretan dokument"
  },
  "strategija": {
    "primarni_cilj": "Konkretno sta se pokusava postici (iznos, pravo, status...)",
    "rezervni_plan": "Sta je fallback ako primarni cilj ne uspe (npr. poravnanje 70%)",
    "scenariji": [
      {"uslov": "Ako veštak bude osporen", "odgovor": "Konkretna kontra-akcija"},
      {"uslov": "Ako kljucni svedok promeni iskaz", "odgovor": "Alternativni pristup"},
      {"uslov": "Ako protivnik uloži procesni prigovor", "odgovor": "Pravni odgovor"}
    ]
  },
  "nedostaje": [
    {"dokument": "Naziv nedostajuceg dokumenta ili dokaza", "hitnost": "kriticno|vazno|pozeljno", "opis": "Zasto je potreban i kakav uticaj ima na predmet"}
  ],
  "strategija_osnova": "Jedna recenica: koji je kljucni strateski pravac (sudski/nagodba/prigovor/sl.)",
  "upozorenja": ["Kriticna zapazanja — rokovi, slabosti dokaza, procesne greske"],
  "snaga_predmeta": "jaka|srednja|slaba",
  "zakljucak": "2-3 recenice — sta advokat mora znati pre svega ostalog",
  "genome_kompletnost": "visoka|srednja|niska"
}

STROGA PRAVILA:
- Izvlaci SAMO ono sto pise u dokumentima. Nikad ne izmisljaj.
- snaga_predmeta_procent = 0-100 (50 = neutralno, 75+ = jaka, <35 = slaba). Vrednost 0
  u primeru iznad je PLACEHOLDER, ne ciljna vrednost — IZRACUNAJ pravu vrednost iz
  cinjenica OVOG predmeta. Dva razlicita predmeta sa razlicitim dokazima MORAJU dobiti
  razlicit procenat — nikad ne vracaj isti broj po navici ili default.
- snaga_faktori: min 3 faktora, max 8. SVAKI sa realnim uticajem (+ili-). Zbir treba da objasni snaga_predmeta_procent.
- heatmap: svaka dimenzija 0-100. 0=nema podataka, 50=delimicno, 95=odlicno dokumentovano.
- dokazi_rang: sortiraj od najjaceg do najslabijeg. Ukljuci SVE dokumente iz predmeta.
  zvezdice = round(snaga_score/20), min 1, max 5.
- najslabija_tacka.kriticnost = 0-100 (100 = moze da unisti predmet).
- strategija.scenariji: min 2, max 5 realnih scenarija.
- nedostaje: samo ono sto ZAISTA nedostaje za dokazivanje. Prazna lista ako su svi kljucni dokazi prisutni.
- kontradikcije.lokacija_1/lokacija_2: navedi TACAN "DOK-XX str.Y" SAMO ako je
  strana eksplicitno vidljiva u tekstu dokumenta. Ako strana nije jasna,
  navedi samo "DOK-XX" bez broja strane. Ako ni dokument nije jasan, ostavi
  polje prazno — NIKAD ne nagadjaj ili izmisljaj lokaciju.
- najslabija_tacka.lokacija: ISTO pravilo kao kontradikcije.lokacija_1 iznad
  (Program Tau, Master Sprint 004) — ako je slabost vezana za konkretan
  dokument, navedi "DOK-XX str.Y" ili "DOK-XX"; ako je slabost holisticka
  (npr. nedostatak svedoka, procesni rizik bez jednog dokumenta), ostavi
  polje prazno. Prazno polje nije greska — izmisljena DOK-XX referenca jeste.
- Srpski jezik. Ekavica obligatna — nikad ijekavica.
- genome_kompletnost = visoka ako imas 3+ dokumenata sa jasnim cinjenicama."""


_COMPARE_SYSTEM = """Ti si pravni AI koji uporedjuje dva pravna dokumenta iz istog predmeta.

Analiziras oba i vratas JSON:
{
  "razlike_kljucne": ["Konkretna razlika 1 (sa citatima ako moguce)", "Razlika 2"],
  "kontradikcije": ["Tacna kontradikcija izmedju dokumenata"],
  "slicnosti": ["Sto se poklapa"],
  "koji_je_jaci_dokaz": "DOK-0X ili 'ravnopravni' sa obrazlozenjem",
  "preporuka_advokata": "Sta advokat treba da uradi u svetlu ove analize",
  "zakljucak": "2 recenice"
}
Srpski. Ekavica."""


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_dokazi_kontekst(supa, predmet_id: str) -> list[dict]:
    """Core Consolidation Sec 1.3 (2026-07-22) — Case Genome je jedini
    vlasnik istine o predmetu; Evidence Vault (predmet_dokazi) vise ne sme
    da bude paralelna, neuporedjena istina. Vraca vec-klasifikovane
    kljucne cinjenice (routers/evidence.py::klasifikuj_i_sacuvaj) da bi
    _extract_genome mogao da ih koristi kao kontekst umesto da ih tiho
    ignorise. Nikad ne baca — advisory kontekst, ne sme oboriti ekstrakciju."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_dokazi")
                .select("tvrdnja,kategorija,pravni_element")
                .eq("predmet_id", predmet_id)
                .is_("deleted_at", "null")
                .limit(20)
                .execute()
        )
        return r.data or []
    except Exception as exc:
        logger.warning("[GENOME] Dokazi kontekst greška (nije kritično): %s", exc)
        return []


# CELINA 2 (2026-07-24): raniji docs[:8] + tekst[:4500] je za predmet sa
# >8 dokumenata TIHO ignorisao ostatak (npr. 17 od 25 dokumenata za predmet
# sa 25 uploadovanih fajlova nikad nisu ni stigli do GPT poziva), i svaki
# analizirani dokument je bio odsečen na 4500 znakova bez obzira na dužinu.
# gpt-4o ima ~128k tokena konteksta (~500k znakova) -- ovi limiti su bili
# mnogo konzervativniji nego što model stvarno zahteva. Budžetiranje sada
# prati UKUPAN utrošen prostor preko SVIH dokumenata (ne flat po-dokumentu
# cutoff), i eksplicitno broji koliko je dokumenata/znakova moralo biti
# izostavljeno da bi Genome mogao da prijavi tu granicu umesto da je
# tiho sakrije.
_GENOME_MAX_DOCS = 25
_GENOME_MAX_CHARS_PER_DOC = 4500
_GENOME_MAX_TOTAL_CHARS = 60000


@llm_retry
async def _pozovi_genome_api(client, combined: str, broj_dokumenata: int) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo _extract_genome -- izdvojen jer
    vanjska funkcija ima sopstveni try/except sa fallback-om na {"greska": ...}."""
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _GENOME_SYSTEM},
                {"role": "user", "content": f"Dokumenti predmeta ({broj_dokumenata} dokumenata):\n\n{combined}"},
            ],
        ),
        timeout=60.0,
    )
    return (resp.choices[0].message.content or "").strip()


async def _extract_genome(
    docs: list[dict], dokazi: Optional[list[dict]] = None,
    ukupno_u_predmetu: Optional[int] = None,
) -> dict:
    """GPT-4o ekstrakcija Case Genome iz liste dokumenata.

    dokazi (Core Consolidation Sec 1.3): vec-klasifikovane kljucne
    cinjenice iz Evidence Vault-a (predmet_dokazi), prosledjene kao
    dodatni kontekst — GPT vise ne izvlaci cinjenice IZOLOVANO od onoga
    sto je Evidence Vault vec utvrdio o istim dokumentima.

    ukupno_u_predmetu (Zero-Touch Case investigation, 2026-08-03,
    BETA-002/Scenario G): `docs` je vec limitiran na _GENOME_MAX_DOCS PRE
    poziva ovoj funkciji (pozivalac radi `.limit(_GENOME_MAX_DOCS)` na
    upitu) -- `len(docs) - _GENOME_MAX_DOCS` je zato skoro uvek <= 0 i
    _genome_docs_preskoceno je cutke prijavljivao pogresan (skoro uvek
    nula) broj bas za slucajeve kada je istina najveca: predmet sa >25
    dokumenata. Kada pozivalac prosledi stvaran ukupan broj dokumenata u
    predmetu (necuknjen upitom), ovaj broj je tacan; ako ne, ponasanje
    ostaje isto kao pre (priblizno, iz already-limited liste)."""
    if not docs:
        return {}

    parts = []
    total_chars = 0
    osnova_za_preskoceno = ukupno_u_predmetu if ukupno_u_predmetu is not None else len(docs)
    docs_preskoceno = max(0, osnova_za_preskoceno - _GENOME_MAX_DOCS)
    for dok in docs[:_GENOME_MAX_DOCS]:
        rn = dok.get("redni_broj") or "?"
        naziv = dok.get("naziv_fajla", "dokument")
        tip = dok.get("tip_dokaza") or ""
        kb = dok.get("velicina_kb") or ""
        tekst = (dok.get("tekst_sadrzaj") or "").strip()
        if not tekst:
            continue
        if total_chars >= _GENOME_MAX_TOTAL_CHARS:
            docs_preskoceno += 1
            continue
        budzet = min(_GENOME_MAX_CHARS_PER_DOC, _GENOME_MAX_TOTAL_CHARS - total_chars)
        deo_teksta = tekst[:budzet]
        total_chars += len(deo_teksta)
        rn_fmt = f"{int(rn):02d}" if str(rn).isdigit() else "?"
        header = f"[DOK-{rn_fmt}: {naziv}"
        if tip:
            header += f" | Vrsta: {tip}"
        if kb:
            header += f" | {kb}KB"
        header += "]"
        parts.append(f"{header}\n{deo_teksta}")

    if not parts:
        return {"greska": "Nijedan dokument nema tekst za analizu"}

    combined = "\n\n".join(parts)

    if dokazi:
        dokazi_lines = []
        for d in dokazi[:20]:
            tvrdnja = (d.get("tvrdnja") or "").strip()
            if not tvrdnja:
                continue
            elm = f" [{d.get('pravni_element')}]" if d.get("pravni_element") else ""
            dokazi_lines.append(f"- {tvrdnja}{elm}")
        if dokazi_lines:
            combined += (
                "\n\n[EVIDENCE VAULT — već klasifikovane ključne činjenice iz ovih dokumenata, "
                "koristi kao dodatni kontekst, ne izmišljaj nove ako se ne poklapaju sa tekstom]\n"
                + "\n".join(dokazi_lines)
            )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        raw = await _pozovi_genome_api(client, combined, len(parts))
        result = json.loads(raw)
        result["_genome_docs_count"] = len(parts)
        result["_genome_docs_preskoceno"] = docs_preskoceno
        # Reliability Patch (2026-07-18) — snaga_predmeta_procent/snaga_predmeta se
        # RACUNAJU backend-om iz snaga_faktori, ne uzima se GPT-ovo samo-prijavljeno
        # broj (anchoring bug otkriven Reality Validation batch-om — videti
        # shared/genome_validator.py compute_snaga_score() docstring za detalje).
        skor = compute_snaga_score(result)
        result["snaga_predmeta_procent"] = skor["snaga_predmeta_procent"]
        result["snaga_predmeta"] = skor["snaga_predmeta"]
        result["snaga_faktori"] = skor["snaga_faktori"]
        # Operation One Truth (2026-08-07): unlike its sibling field above
        # (snaga_predmeta_procent), najslabija_tacka.kriticnost was never clamped --
        # a fully GPT-authored 0-100 claim reaching the DB, this canonical context's
        # key_facts, and proactive-alert urgency math (_compute_delta below)
        # unchecked. Same defensive pattern already used platform-wide for GPT
        # numeric claims (matter_intel.py/cio.py/hearing_cc.py's own score clamps).
        _nt = result.get("najslabija_tacka")
        if isinstance(_nt, dict) and "kriticnost" in _nt:
            try:
                _nt["kriticnost"] = max(0, min(100, int(_nt["kriticnost"])))
            except (TypeError, ValueError):
                _nt["kriticnost"] = 0
        return result
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[GENOME] Ekstrakcija greška: %s", exc)
        return {"greska": str(exc)}


def _compute_delta(old_g: dict, new_g: dict) -> dict:
    """Poredi stari i novi Genome. Vraca delta objekat za generisanje inteligentnog alerta.

    Program Sigma, Master Sprint 002 (2026-08-06): kontradikcija set-membership
    now uses shared/contradiction_identity.py's own stable (lokacija_1,
    lokacija_2) identity instead of `opis[:60]` string-prefix matching
    (SIGMA-002, Sprint 001 Debt Register) -- a rephrased-but-identical
    contradiction between 2 refreshes no longer registers as a false
    eliminated+new churn. Same shared function services/case_evolution.py's
    own Rule 3 (RAZRESITI_KONTRADIKCIJU) uses -- one identity, not two
    independent implementations."""
    if not old_g or old_g.get("greska") or not new_g or new_g.get("greska"):
        return {}

    stara_snaga = old_g.get("snaga_predmeta_procent") or 0
    nova_snaga  = new_g.get("snaga_predmeta_procent") or 0

    stari_kontr = {contradiction_identity(k) for k in (old_g.get("kontradikcije") or [])}
    novi_kontr  = {contradiction_identity(k) for k in (new_g.get("kontradikcije") or [])}

    stara_nt = (old_g.get("najslabija_tacka") or {}).get("kriticnost") or 0
    nova_nt  = (new_g.get("najslabija_tacka") or {}).get("kriticnost") or 0

    stara_ned = len(old_g.get("nedostaje") or [])
    nova_ned  = len(new_g.get("nedostaje") or [])

    stara_strat = (old_g.get("strategija") or {}).get("primarni_cilj") or old_g.get("strategija_osnova") or ""
    nova_strat  = (new_g.get("strategija") or {}).get("primarni_cilj") or new_g.get("strategija_osnova") or ""

    return {
        "snaga_delta":          nova_snaga - stara_snaga,
        "snaga_stara":          stara_snaga,
        "snaga_nova":           nova_snaga,
        "kontr_eliminisane":    len(stari_kontr - novi_kontr),
        "kontr_nove":           len(novi_kontr - stari_kontr),
        "nt_kriticnost_delta":  nova_nt - stara_nt,
        "nedostaje_delta":      nova_ned - stara_ned,
        "strategija_promenjena": bool(
            stara_strat and nova_strat and stara_strat[:50] != nova_strat[:50]
        ),
        "nova_strategija": nova_strat if stara_strat[:50] != nova_strat[:50] else None,
    }


def _delta_alert_text(delta: dict, verzija: int, trigger: str) -> str:
    """Formatira delta u konkretan alert tekst koji opisuje SVE sto se promenilo."""
    _TRIGGER_LABEL = {
        "upload_trigger":         "novi dokument",
        "rociste_trigger":        "novo rociste",
        "manual_refresh":         "rucni refresh",
        "smart_intake_finalize":  "smart intake finalizacija",
    }
    trig_label = _TRIGGER_LABEL.get(trigger, trigger)
    lines = [f"Genome v{verzija} azuriran — {trig_label}."]

    sd = delta.get("snaga_delta", 0)
    if sd:
        smer = "+" if sd > 0 else ""
        lines.append(f"  Snaga predmeta: {delta['snaga_stara']}% → {delta['snaga_nova']}% ({smer}{sd})")

    ke = delta.get("kontr_eliminisane", 0)
    kn = delta.get("kontr_nove", 0)
    if ke:
        lines.append(f"  {ke} kontradikcija eliminisano")
    if kn:
        lines.append(f"  {kn} nova kontradikcija detektovana")

    ntd = delta.get("nt_kriticnost_delta", 0)
    if abs(ntd) >= 8:
        smer = "smanjena" if ntd < 0 else "povecana"
        lines.append(f"  Kriticnost najslabije tacke {smer} za {abs(ntd)} poena")

    ned_d = delta.get("nedostaje_delta", 0)
    if ned_d < 0:
        lines.append(f"  {abs(ned_d)} nedostajucih dokaza ispunjeno")
    elif ned_d > 0:
        lines.append(f"  {ned_d} novih nedostajucih dokaza identifikovano")

    if delta.get("strategija_promenjena"):
        nova_s = (delta.get("nova_strategija") or "")[:60]
        lines.append(f"  Strategija promenjena: {nova_s}")

    return "\n".join(lines)


def _delta_significant(delta: dict) -> bool:
    """Vraca True ako je delta dovoljno znacajna da zasluzuje alert."""
    if not delta:
        return False
    return (
        abs(delta.get("snaga_delta", 0)) >= 5
        or delta.get("kontr_eliminisane", 0) > 0
        or delta.get("kontr_nove", 0) > 0
        or abs(delta.get("nt_kriticnost_delta", 0)) >= 10
        or delta.get("nedostaje_delta", 0) != 0
        or delta.get("strategija_promenjena", False)
    )


def _delta_hitnost(delta: dict) -> str:
    """Program Gamma (2026-08-04) -- ova formula je ranije bila inline-
    duplirana bajt-identicno na 2 mesta u ovom fajlu (auto-refresh i
    manual-refresh putanja) -- nije bio zivi bug (identican kod), ali je
    tacno onaj obrazac ove misije: odluka o hitnosti alerta imala je dva
    nezavisna autora, jednu izmenu daleko od tihog razilaska. Izdvojeno u
    jednu deljenu funkciju, isti obrazac kao _delta_significant/
    _delta_alert_text odmah iznad."""
    snaga_d = abs(delta.get("snaga_delta", 0))
    return "hitna" if snaga_d >= 15 or delta.get("kontr_nove", 0) > 1 else "normalna"


def _verifikacija_alert_text(verifikacija: dict, verzija: int) -> str:
    """G-032 (D27) — formatira require_review razlog(e) u konkretan alert tekst.
    Koristi SAMO podatke koji vec postoje u verify_genome() rezultatu (hard_flags
    razlozi) — ne izmislja "confidence %" ili drugu vrednost koja se stvarno ne
    racuna nigde."""
    razlozi = [f.get("razlog", "") for f in (verifikacija.get("hard_flags") or []) if f.get("razlog")]
    lines = [f"Genome v{verzija} zahteva pregled advokata pre korišćenja — automatska provera je pronašla problem(e) koje ne može sama da razreši."]
    for r in razlozi[:5]:
        lines.append(f"  • {r}")
    return "\n".join(lines)


async def _maybe_alert_require_review(
    supa, predmet_id: str, uid: str, stari_genome: dict, genome: dict,
) -> None:
    """G-032 (D27, VINDEX_OPERATIONAL_GAP_REGISTER.md) — verify_genome()'s
    'require_review' odluka se ranije racunala i upisivala u audit (Faza 1.2/1.3),
    ali nista nije reagovalo na nju — signal bez potrosaca ("half-wired").

    Kreira proactive_alert SAMO na PRELAZ u require_review (staro != require_review,
    novo == require_review) — ne na svaki refresh dok isti problem i dalje postoji,
    da ne spamuje "review needed" iznova i iznova ako je predmet vec jednom
    obelezen a razlog se nije promenio. Ako se stanje vrati na require_review POSLE
    perioda gde nije bilo — to je novi (drugi) problem, dobija nov alert.

    Reuse-uje POSTOJECI proactive_alerts mehanizam (isti obrazac kao genome_change
    alert iznad/ispod) — nula novog eventa, nula novog AI-ja, cisto signal covek,
    ne akcija sistema (genome se i dalje uvek cuva, verzija i dalje uvek raste,
    ovo ne blokira niti menja nista drugo)."""
    nova_v = genome.get("_verifikacija") or {}
    stara_v = stari_genome.get("_verifikacija") or {} if isinstance(stari_genome, dict) else {}
    if nova_v.get("odluka") != "require_review" or stara_v.get("odluka") == "require_review":
        return
    from shared.proactive_alerts import create_proactive_alert
    await create_proactive_alert(
        supa,
        user_id=uid,
        predmet_id=predmet_id,
        tip="genome_verification_required",
        naslov=f"Genome v{genome.get('verzija', 1)} zahteva pregled",
        opis=_verifikacija_alert_text(nova_v, genome.get("verzija", 1)),
        urgentnost="visoka",
    )


async def _save_genome_history(
    supa, predmet_id: str, uid: str, old_genome: dict, trigger: str = "manual"
) -> None:
    """Upisuje stari Genome u tabelu istorije pre prepisivanja."""
    if not old_genome or old_genome.get("greska"):
        return
    try:
        await asyncio.to_thread(
            lambda: supa.table("predmet_genome_history").insert({
                "predmet_id": predmet_id,
                "user_id": uid,
                "verzija": old_genome.get("verzija") or 1,
                "genome_data": old_genome,
                "snaga_procent": old_genome.get("snaga_predmeta_procent"),
                "trigger_event": trigger,
            }).execute()
        )
    except Exception as exc:
        logger.warning("[GENOME] History save greška: %s", exc)


async def _compute_analiza_osnov(supa, predmet_id: str, docs: list[dict]) -> dict:
    """T1.3 / P0.5 (Trust Layer v1, 2026-07-19) — "AI ograničenja" panel:
    na čemu se TAČNO zasniva ova analiza, ne procena nego brojanje
    postojećih podataka. dokumenata/pravnih_elemenata dolaze iz docs
    liste koja je vec ucitana za _extract_genome (nula dodatnih upita).
    cinjenica dolazi iz predmet_dokazi (Evidence Vault, klasifikuj_i_sacuvaj)
    — jedan lagan COUNT upit, isti obrazac kao corrections.py._maybe_update_
    style_profile. Nikad ne baca izuzetak — advisory podatak, ne sme oboriti
    Genome regeneraciju ako padne."""
    try:
        pravnih_n = sum(len(d.get("pravni_elementi") or []) for d in docs)
        cnt = await asyncio.to_thread(
            lambda: supa.table("predmet_dokazi")
                .select("id", count="exact")
                .eq("predmet_id", predmet_id)
                .is_("deleted_at", "null")
                .execute()
        )
        return {
            "dokumenata": len(docs),
            "cinjenica": cnt.count or 0,
            "pravnih_elemenata": pravnih_n,
        }
    except Exception as exc:
        logger.warning("[GENOME] Analiza osnov greška (nije kritično): %s", exc)
        return {"dokumenata": len(docs)}


async def _emit_genome_event(
    supa, predmet_id: str, uid: str, genome: dict, trigger: str,
    prev_verzija: Optional[int] = None, verifikacija_odluka: Optional[str] = None,
) -> str:
    """Upisuje GenomeUpdated event u durable outbox ('events' tabela) — Faza 1.1,
    90-dnevni plan 2026-07-18. Zove se SAMO posle uspesnog upisa case_dna kolone.

    Namerno ne zove services.event_bus.emit()/bus.publish() — dispatch_pending_events()
    ce sam procitati ovaj red iz 'events' i pokrenuti handlere kad-tad; direktan
    emit() ovde bi izazvao da se isti handler pokrene dvaput (odmah in-memory i
    ponovo pri dispatch-u). Greska u upisu eventa NIKAD ne sme da obori glavni
    zahtev — isti princip kao _save_genome_history iznad.

    correlation_id (Faza 1.2): Mission Ledger (2026-08-03) — ranije se ovde
    UVEK generisao nov uuid4, nezavisno od shared/ai_provenance.py's
    request-scoped id (isti koji AI wrapper i log_action već koriste za ovaj
    isti Genome poziv, s obzirom da routers/case_dna.py's _extract_genome
    poziv je omotan u ai_provenance.case_context() od Mission Atlas-a) — dva
    nezavisna "correlation_id" koncepta za JEDNU logičku operaciju (ranije
    evidentirano kao ATLAS-004). Sada nasleđuje isti id ako postoji (isti
    HTTP zahtev), i generise nov SAMO ako Genome refresh radi van bilo kog
    poznatog konteksta (npr. pozadinski posao bez trenutnog zahteva).
    Upisuje se i u 'events' tabelu (dedikovana kolona, migracija 090) i u
    payload (nazad-kompatibilno sa čitaocima koji ga još čitaju odatle).

    verifikacija_odluka (Faza 1.3): approve/approve_with_warning/require_review
    iz shared/genome_validator.verify_genome() — prosledjuje se ovde umesto da
    1.3 pravi sopstveni audit poziv, produzava vec postojeci 1.1/1.2 cevovod.
    """
    try:
        from shared.ai_provenance import current_correlation_id, new_correlation_id
        correlation_id = current_correlation_id() or new_correlation_id()
    except Exception:
        # Program Alpha (2026-08-04): use the same canonical minting function
        # as the try-branch above, not a second, independent uuid.uuid4()
        # call -- there is exactly one place a fresh correlation_id is ever
        # minted in this codebase.
        from shared.ai_provenance import new_correlation_id
        correlation_id = new_correlation_id()
    _row = {
        "event_type": EventType.GENOME_UPDATED.value,
        "user_id": uid,
        "predmet_id": predmet_id,
        "payload": {
            "verzija": genome.get("verzija"),
            "prev_verzija": prev_verzija,
            "snaga_predmeta_procent": genome.get("snaga_predmeta_procent"),
            "trigger": trigger,
            "correlation_id": correlation_id,
            "verifikacija_odluka": verifikacija_odluka,
        },
    }
    try:
        # Migracija 090 (drafted, not yet applied) dodaje dedikovanu
        # 'correlation_id' kolonu na 'events' — pokušaj prvo sa njom, pa
        # bez nje ako kolona još ne postoji (isti "probaj široko, padni na
        # usko" obrazac kao security/ai_forensics.py::log_provenance_from_wrapper).
        # Project Phoenix (2026-08-03), Finding P-1: fallback je namerno
        # NARROW (_is_missing_column_error), ne bare except -- isti razlog
        # kao shared/audit_immutable.py's već-ispravna verzija: širi catch bi
        # tiho pokušao drugi upis i na potpuno nepovezanu grešku (npr.
        # konekcija), ne samo na "kolona ne postoji".
        from shared.audit_immutable import _is_missing_column_error
        try:
            await asyncio.to_thread(
                lambda: supa.table("events").insert({**_row, "correlation_id": correlation_id}).execute()
            )
        except Exception as _wide_exc:
            if not _is_missing_column_error(_wide_exc):
                raise
            await asyncio.to_thread(lambda: supa.table("events").insert(_row).execute())
    except Exception as exc:
        logger.warning("[GENOME] Event emit greška (nije kritično): %s", exc)
    return correlation_id


async def _sync_rokovi_to_hronologija(supa, predmet_id: str, uid: str, genome: dict) -> int:
    """Core Consolidation Sec 1.5 (2026-07-22) — Genome-ekstraktovani
    rokovi_kriticni su ranije ziveli SAMO u case_dna jsonb koloni, nikad
    upisani u predmet_hronologija (stvarna, vec-koriscena kalendar tabela
    — Cockpit-ov 'Hitni rokovi' i case_pipeline._step_kalendar je citaju).
    Rezultat: rok koji Genome pronadje u dokumentu bio je nevidljiv svuda
    drugde u aplikaciji. Ovo ga upisuje u hronologiju — deduplicirano po
    (datum_iso, dogadjaj) da ponovljeni Genome refresh ne pravi duplikate.
    Advisory/best-effort: greska ovde nikad ne sme oboriti Genome upis."""
    rokovi = genome.get("rokovi_kriticni") or []
    if not rokovi:
        return 0
    try:
        postojeci_r = await asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("dogadjaj,datum_iso")
                .eq("predmet_id", predmet_id)
                .execute()
        )
        postojeci = {(r.get("dogadjaj",""), r.get("datum_iso","")) for r in (postojeci_r.data or [])}
    except Exception as exc:
        logger.warning("[GENOME] Sync rokovi — čitanje hronologije greška: %s", exc)
        return 0

    upisano = 0
    for r in rokovi[:10]:
        if r.get("status") != "aktivan":
            continue
        datum = (r.get("datum") or "")[:10]
        if not datum or len(datum) != 10:
            continue
        naziv = (r.get("naziv") or "Rok").strip()
        dogadjaj = f"{naziv}: {(r.get('opis') or '').strip()}"[:200] if r.get("opis") else naziv[:200]
        if (dogadjaj, datum) in postojeci:
            continue
        try:
            await asyncio.to_thread(lambda dg=dogadjaj, dt=datum: supa.table("predmet_hronologija").insert({
                "predmet_id": predmet_id,
                "user_id":    uid,
                "dogadjaj":   dg,
                "datum":      dt,
                "datum_iso":  dt,
                "vaznost":    "kritičan",
                "akter":      "Genome (AI)",
            }).execute())
            upisano += 1
        except Exception as exc:
            logger.warning("[GENOME] Sync rokovi — insert greška: %s", exc)
    return upisano


_genome_refresh_inflight: set = set()
_genome_refresh_rerun: set = set()


async def _run_genome_background(
    predmet_id: str, uid: str, stari_procent: Optional[int] = None,
    trigger: str = "upload_trigger",
):
    """Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario F):
    thin coalescing wrapper around _do_genome_refresh. More than one
    trigger for the SAME predmet_id in quick succession (e.g. several
    documents finalized into one case back-to-back, per Scenario B) could
    previously race: both read the same case_dna.verzija, both write,
    whichever write lands last silently wins -- confirmed, not previously
    fixed. Since a full refresh always re-reads ALL current documents
    (never incremental), running it once per predmet_id at a time and
    re-running once more if a new trigger arrived meanwhile produces the
    same end state as running every trigger separately, minus the lost-
    update race and the redundant GPT calls. In-process only (a set, not a
    DB-level lock) -- does NOT coalesce across separate worker processes;
    documented here as a real limitation, not claimed as a complete fix."""
    if predmet_id in _genome_refresh_inflight:
        _genome_refresh_rerun.add(predmet_id)
        return
    _genome_refresh_inflight.add(predmet_id)
    try:
        while True:
            _genome_refresh_rerun.discard(predmet_id)
            await _do_genome_refresh(predmet_id, uid, stari_procent, trigger)
            if predmet_id not in _genome_refresh_rerun:
                break
    finally:
        _genome_refresh_inflight.discard(predmet_id)
        _genome_refresh_rerun.discard(predmet_id)


async def _do_genome_refresh(
    predmet_id: str, uid: str, stari_procent: Optional[int] = None,
    trigger: str = "upload_trigger",
):
    """Poziva se u pozadini posle uploada/rocista/smart-intake finalize-a.
    Regenerise Genome i kreira alert ako se snaga promenila.

    trigger (Faza 1.2, 90-dnevni plan 2026-07-18): default 'upload_trigger'
    cuva stari default za pozivaoce koji ga ne prosledjuju eksplicitno, ali
    api.py/rocista.py/smart_intake.py sada svi prosledjuju tacnu vrednost —
    pre ovoga je funkcija UVEK pisala 'upload_trigger' bez obzira na stvarnog
    pozivaoca (poznata greska iz Faze 1.1 checklist-a, sada ispravljena jer
    audit trail (1.2) prvi put cini pogresnu oznaku problemom usklađenosti,
    ne samo internom netačnošću)."""
    supa = _get_supa()
    try:
        # Ucitaj stari Genome za historiju
        pred_res = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("case_dna")
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .single()
                .execute()
        )
        stari_genome = (pred_res.data or {}).get("case_dna") or {}
        stari_verzija = stari_genome.get("verzija") or 0

        # Scenario G fix (2026-08-03): bio je .order("redni_broj") rastuce --
        # za predmet sa >_GENOME_MAX_DOCS dokumenata to je cutke odsecalo sve
        # NAKON prvih 25 uploadovanih (najstarije), tako da najnovija podneska/
        # presuda nikad nije stizala do Genome-a. Opadajuce (najnoviji prvo)
        # je bezbedniji default za pravni status predmeta -- GPT i dalje vidi
        # redni_broj svakog dokumenta u zaglavlju (DOK-NN), pa redosled
        # predstavljanja u promptu ne utice na razumevanje.
        count_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id", count="exact")
                .eq("predmet_id", predmet_id).execute()
        )
        ukupno_dokumenata = count_res.count if count_res.count is not None else None

        dok_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id,naziv_fajla,redni_broj,tekst_sadrzaj,velicina_kb,pravni_elementi")
                .eq("predmet_id", predmet_id)
                .order("redni_broj", desc=True)
                .limit(_GENOME_MAX_DOCS).execute()
        )
        docs = [d for d in (dok_res.data or []) if (d.get("tekst_sadrzaj") or "").strip()]
        if not docs:
            return

        dokazi_ctx = await _fetch_dokazi_kontekst(supa, predmet_id)
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=predmet_id, module_name="case_dna", operation_name="genome_extraction",
                          knowledge_sources=[d.get("id") for d in docs]):
            genome = await _extract_genome(docs, dokazi=dokazi_ctx, ukupno_u_predmetu=ukupno_dokumenata)
        if genome.get("_genome_docs_preskoceno"):
            logger.warning(
                "[GENOME] predmet=%s: %d dokumenata IZOSTAVLJENO iz analize (ukupno=%s, analizirano=%d)",
                predmet_id, genome["_genome_docs_preskoceno"], ukupno_dokumenata, len(docs),
            )

        # Program Lambda, Certification 004 (2026-08-06) -- AI Systems Reliability
        # fork found (Adversarial Certification-confirmed): a GPT extraction
        # failure inside _extract_genome() correctly returns a bare
        # {"greska": str(exc)} signal (never raises), but this function used to
        # write THAT signal unconditionally to the live predmeti.case_dna column
        # a few lines below -- a Postgres/PostgREST .update() on a JSON column is
        # a full-value REPLACE, not a merge, so a single transient GPT failure
        # destroyed every existing Genome field (kljucne_cinjenice,
        # snaga_predmeta_procent, kontradikcije, nedostaje, deadlines, ...) for
        # every downstream consumer (Court Predictor, Digital Twin, CIO, Copilot,
        # build_case_context()) until the next successful refresh. The
        # verification/hronologija-sync steps immediately below already had the
        # correct `if not genome.get("greska")` guard -- the live write itself,
        # history save, delta/alert, and require-review steps did not. All of
        # them now share that same guard: on failure, nothing about the live
        # case is touched, only a clear log line records the failure.
        #
        # Phase 6 adversarial re-attack (same sprint) found the guard used
        # truthiness (`genome.get("greska")`) rather than key presence --
        # an exception with an empty str(exc) (rare, but not provably
        # impossible for every exception type _extract_genome's own broad
        # except clause could ever catch) would make this falsy and fall
        # through into the exact destructive write path this fix exists to
        # close. Key-presence check closes that edge case at zero cost.
        if "greska" in genome:
            logger.warning(
                "[GENOME] bg refresh predmet=%s NEUSPEŠAN -- postojeći case_dna (v%s) OSTAJE NEPROMENJEN: %s",
                predmet_id, stari_verzija, genome.get("greska"),
            )
            return

        # Auto-versioning
        genome["verzija"] = stari_verzija + 1

        # Faza 1.3 — Genome Verification Layer (advisory, non-blocking, nula GPT poziva)
        genome["_verifikacija"] = verify_genome(genome, docs)
        genome["_analiza_osnov"] = await _compute_analiza_osnov(supa, predmet_id, docs)
        await _sync_rokovi_to_hronologija(supa, predmet_id, uid, genome)

        # Snimi stari u istoriju
        await _save_genome_history(supa, predmet_id, uid, stari_genome, trigger)

        await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .update({"case_dna": genome})
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .execute()
        )

        await _emit_genome_event(
            supa, predmet_id, uid, genome, trigger, prev_verzija=stari_verzija,
            verifikacija_odluka=genome.get("_verifikacija", {}).get("odluka"),
        )

        # Genome Intelligence Delta — pametni alert sa svim promenama
        delta_obj = _compute_delta(stari_genome, genome)
        if _delta_significant(delta_obj):
            verzija = genome.get("verzija", 1)
            tekst = _delta_alert_text(delta_obj, verzija, trigger)
            hitnost = _delta_hitnost(delta_obj)
            # Kolone potvrdjene naspram zive seme (Reality Validation batch,
            # 2026-07-18): 'tekst_alerta'/'tip_alerta'/'hitnost' NISU postojali —
            # stvarna sema je naslov/opis/tip/urgentnost. Feature je bio 100%
            # neuspesan (PGRST204 na svakom pozivu) otkad je napisan -- tacno
            # klasa greske koju shared/proactive_alerts.py's kanonska funkcija
            # (Program Alpha, 2026-08-04) sada strukturno sprecava (pogresno
            # ime parametra postaje Python TypeError na mestu poziva, ne tiha
            # Postgres neuslaglasenost seme).
            from shared.proactive_alerts import create_proactive_alert
            await create_proactive_alert(
                supa,
                user_id=uid,
                predmet_id=predmet_id,
                tip="genome_change",
                naslov=f"Genome ažuriran — v{verzija}",
                opis=tekst,
                urgentnost=hitnost,
            )

        # G-032 (D27) — require_review signal sada ima potrošača
        await _maybe_alert_require_review(supa, predmet_id, uid, stari_genome, genome)

        logger.info("[GENOME] bg refresh predmet=%s docs=%d snaga=%s%% v%s",
                    predmet_id, len(docs), genome.get("snaga_predmeta_procent"), genome.get("verzija"))
    except Exception as exc:
        logger.warning("[GENOME] Background refresh greška: %s", exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{predmet_id}/case-dna")
async def get_case_dna(predmet_id: str, user=Depends(get_current_user)):
    """Vraca trenutni Case Genome za predmet."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("case_dna,naziv")
                .eq("id", predmet_id)
                .eq("user_id", user["user_id"])
                .maybe_single().execute()
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))

    if not row.data:
        raise HTTPException(404, "Predmet nije pronadjen")

    genome = row.data.get("case_dna") or {}
    return {
        "predmet_id": predmet_id,
        "predmet_naziv": row.data.get("naziv"),
        "case_dna": genome,
        "ima_dna": bool(genome and not genome.get("greska")),
    }


@router.post("/{predmet_id}/case-dna/refresh")
@limiter.limit("10/minute")
async def refresh_case_dna(predmet_id: str, request: Request, user=Depends(PermissionService.require("case_dna"))):
    """Regenerise Case Genome iz svih dokumenata predmeta.

    BLACKSWAN-HIGH-003 fix (Operation Black Swan, Mission 001, Scenario 8): this manual
    endpoint used to reimplement _run_genome_background's own read-verzija -> GPT-extract
    -> bump-verzija -> full-column-replace sequence from scratch, never touching that
    function's _genome_refresh_inflight coalescing guard -- a second, fully unguarded path
    to the same write. Reproduced: 2 concurrent manual refreshes on the same case -> 2
    wasted GPT calls, BOTH wrote the same (duplicate) verzija number, and the LOSING
    caller's own HTTP response claimed a snaga% value that did not match what actually
    persisted -- a response that lies about what got saved. Now shares the exact same
    in-process guard the background trigger path already uses, so a manual refresh and a
    background-triggered one (or two manual ones) can never race each other."""
    if predmet_id in _genome_refresh_inflight:
        raise HTTPException(status_code=409, detail="Genome se već osvežava za ovaj predmet — sačekajte da se završi, pa pokušajte ponovo.")
    _genome_refresh_inflight.add(predmet_id)
    try:
        return await _refresh_case_dna_body(predmet_id, request, user)
    finally:
        _genome_refresh_inflight.discard(predmet_id)


async def _refresh_case_dna_body(predmet_id: str, request: Request, user) -> dict:
    supa = _get_supa()
    uid = user["user_id"]

    try:
        pred_check = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv,case_dna")
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .maybe_single().execute()
        )
    except Exception:
        raise HTTPException(404, "Predmet nije pronadjen")

    if not pred_check.data:
        raise HTTPException(404, "Predmet nije pronadjen")

    stari_genome = pred_check.data.get("case_dna") or {}
    stari_procent = stari_genome.get("snaga_predmeta_procent") if isinstance(stari_genome, dict) else None
    stari_verzija = (stari_genome.get("verzija") or 0) if isinstance(stari_genome, dict) else 0

    try:
        count_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id", count="exact")
                .eq("predmet_id", predmet_id).execute()
        )
        ukupno_dokumenata = count_res.count if count_res.count is not None else None

        # Scenario G fix (2026-08-03) -- vidi identicnu napomenu u _do_genome_refresh.
        dok_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id,naziv_fajla,redni_broj,tekst_sadrzaj,velicina_kb,pravni_elementi")
                .eq("predmet_id", predmet_id)
                .order("redni_broj", desc=True)
                .limit(_GENOME_MAX_DOCS).execute()
        )
        docs = [d for d in (dok_res.data or []) if (d.get("tekst_sadrzaj") or "").strip()]
    except Exception as exc:
        raise HTTPException(500, f"Greska pri ucitavanju dokumenata: {exc}")

    if not docs:
        return {
            "predmet_id": predmet_id,
            "case_dna": {},
            "poruka": "Nema dokumenata sa tekstom. Uploadujte dokumente u predmet.",
            "docs_analizirano": 0,
        }

    dokazi_ctx = await _fetch_dokazi_kontekst(supa, predmet_id)
    from shared.ai_provenance import case_context as _ai_case_ctx
    with _ai_case_ctx(predmet_id=predmet_id, module_name="case_dna", operation_name="genome_extraction",
                      knowledge_sources=[d.get("id") for d in docs]):
        genome = await _extract_genome(docs, dokazi=dokazi_ctx, ukupno_u_predmetu=ukupno_dokumenata)

    if not genome.get("greska"):
        await UsageService.consume(uid, user.get("email", ""), "case_dna")

    # Auto-versioning
    nova_verzija = stari_verzija + 1
    genome["verzija"] = nova_verzija

    # Faza 1.3 — Genome Verification Layer (advisory, non-blocking, nula GPT poziva)
    if not genome.get("greska"):
        genome["_verifikacija"] = verify_genome(genome, docs)
        genome["_analiza_osnov"] = await _compute_analiza_osnov(supa, predmet_id, docs)
        await _sync_rokovi_to_hronologija(supa, predmet_id, uid, genome)

    # Snimi stari Genome u istoriju
    await _save_genome_history(supa, predmet_id, uid, stari_genome, "manual_refresh")

    _update_ok = True
    try:
        await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .update({"case_dna": genome})
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .execute()
        )
    except Exception as exc:
        logger.warning("[GENOME] Snimanje greška: %s", exc)
        _update_ok = False

    if _update_ok:
        await _emit_genome_event(
            supa, predmet_id, uid, genome, "manual_refresh", prev_verzija=stari_verzija,
            verifikacija_odluka=genome.get("_verifikacija", {}).get("odluka"),
        )

    # Genome Intelligence Delta — pametni alert + response
    novi_procent = genome.get("snaga_predmeta_procent")
    delta_obj = _compute_delta(stari_genome, genome)
    alert_msg = None
    if _delta_significant(delta_obj):
        alert_msg = _delta_alert_text(delta_obj, nova_verzija, "manual_refresh")
        hitnost = _delta_hitnost(delta_obj)
        from shared.proactive_alerts import create_proactive_alert
        await create_proactive_alert(
            supa,
            user_id=uid,
            predmet_id=predmet_id,
            tip="genome_change",
            naslov=f"Genome ažuriran — v{nova_verzija}",
            opis=alert_msg,
            urgentnost=hitnost,
        )

    # G-032 (D27) — require_review signal sada ima potrošača
    if _update_ok:
        await _maybe_alert_require_review(supa, predmet_id, uid, stari_genome, genome)

    logger.info("[GENOME] refresh predmet=%s docs=%d snaga=%s%% v%s",
                predmet_id, len(docs), novi_procent, nova_verzija)
    return {
        "predmet_id": predmet_id,
        "predmet_naziv": pred_check.data.get("naziv"),
        "case_dna": genome,
        "docs_analizirano": len(docs),
        "snaga_procent": novi_procent,
        "verzija": nova_verzija,
        "intelligence_delta": delta_obj if delta_obj else None,
        "snaga_promena": alert_msg,
        "poruka": f"Case Genome v{nova_verzija} regenerisan iz {len(docs)} dokumenata.",
    }


@router.get("/{predmet_id}/case-dna/history")
async def get_genome_history(predmet_id: str, user=Depends(get_current_user)):
    """Vraca listu prethodnih verzija Case Genome-a (max 20)."""
    supa = _get_supa()
    uid = user["user_id"]

    # Proveri vlasnistvo
    try:
        pr = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id,naziv")
                .eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()
        )
    except Exception:
        raise HTTPException(404, "Predmet nije pronadjen")
    if not pr.data:
        raise HTTPException(404, "Predmet nije pronadjen")

    try:
        hist_res = await asyncio.to_thread(
            lambda: supa.table("predmet_genome_history")
                .select("id,verzija,snaga_procent,trigger_event,created_at")
                .eq("predmet_id", predmet_id)
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(20)
                .execute()
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))

    return {
        "predmet_id": predmet_id,
        "predmet_naziv": pr.data.get("naziv"),
        "history": hist_res.data or [],
    }


class CompareDoksReq(BaseModel):
    numbers: list[int]


@llm_retry
async def _pozovi_compare_api(client, part_a: str, part_b: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo compare_docs."""
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _COMPARE_SYSTEM},
                {"role": "user", "content": f"Uporedjujem:\n\n{part_a}\n\n---\n\n{part_b}"},
            ],
        ),
        timeout=30.0,
    )
    return resp.choices[0].message.content or "{}"


@router.post("/{predmet_id}/case-dna/compare")
@limiter.limit("10/minute")
async def compare_docs(predmet_id: str, req: CompareDoksReq, request: Request, user=Depends(PermissionService.require("case_dna"))):
    """Uporedjuje dva dokumenta po rednom broju i vraca analizu razlika."""
    if len(req.numbers) < 2:
        raise HTTPException(400, "Potrebna su tacno 2 redna broja dokumenta")
    n1, n2 = req.numbers[0], req.numbers[1]
    supa = _get_supa()
    uid = user["user_id"]

    try:
        pr = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).execute()
        )
        if not pr.data:
            raise HTTPException(404, "Predmet nije pronadjen")

        dok_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id,naziv_fajla,redni_broj,tekst_sadrzaj")
                .eq("predmet_id", predmet_id)
                .in_("redni_broj", [n1, n2]).execute()
        )
        docs = dok_res.data or []
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))

    if len(docs) < 2:
        found = [d["redni_broj"] for d in docs]
        raise HTTPException(404, f"Pronasao samo DOK-{found}. Proverite redne brojeve.")

    parts = []
    for dok in sorted(docs, key=lambda d: d.get("redni_broj") or 0):
        rn = dok.get("redni_broj", "?")
        naziv = dok.get("naziv_fajla", "dokument")
        tip = dok.get("tip_dokaza") or ""
        tekst = (dok.get("tekst_sadrzaj") or "").strip()
        header = f"[DOK-{int(rn):02d}: {naziv}" + (f" | {tip}" if tip else "") + "]"
        # CELINA 2 (2026-07-24): 5000 -> 10000 -- za poređenje DVA celokupna
        # dokumenta (ne 8+ dokumenata odjednom kao _extract_genome), gpt-4o
        # kontekst ima puno prostora za duže ugovore/presude bez sečenja.
        parts.append(f"{header}\n{tekst[:10000]}")

    try:
        from openai import AsyncOpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with _ai_case_ctx(predmet_id=predmet_id, module_name="case_dna", operation_name="compare_docs",
                          knowledge_sources=[d.get("id") for d in docs]):
            raw = await _pozovi_compare_api(client, parts[0], parts[1])
        analiza = json.loads(raw)
    except Exception as exc:
        _sentry_capture(exc)
        raise HTTPException(500, f"AI analiza greška: {exc}")

    await UsageService.consume(uid, user.get("email", ""), "case_dna")

    # Program Beta (2026-08-04) -- compare_docs had zero evidence validation
    # and zero provenance wrapping despite both mechanisms already existing
    # in this file for Genome extraction (case_context above; the DOK-XX
    # existence check below is genome_validator.validate_dok_reference, the
    # same principle as _validate_kontradikcije_lokacije). Advisory only,
    # same fail-soft convention as verify_genome -- never blocks the response.
    #
    # Olympus Faza 10 governance nalazi (2026-08-04): (Backend Reliability)
    # ovaj blok je ranije bio van try/except i pretpostavljao da je `analiza`
    # dict -- sada eksplicitno guard-ovan i u sopstvenom try/except (fail-soft,
    # isti obrazac kao verify_genome -- greška ovde ne sme pretvoriti uspešan
    # AI odgovor u lažni "AI analiza greška" 500). (AI Grounding) DOK-XX
    # izmišljanje može da se pojavi i u kontradikcije/razlike_kljucne, ne samo
    # u koji_je_jaci_dokaz -- sada se sve tri provere. (Architecture Review)
    # oblik normalizovan da odgovara verify_genome()'s ugovoru
    # (soft_flags/provereno_u_ms), ne poseban ad-hoc oblik.
    try:
        if isinstance(analiza, dict):
            _ev_start = time.monotonic()
            poznati_brojevi = {n1, n2}
            hard_flags = list(validate_dok_reference(
                analiza.get("koji_je_jaci_dokaz"), poznati_brojevi, "koji_je_jaci_dokaz",
            ))
            for polje in ("kontradikcije", "razlike_kljucne"):
                for stavka in (analiza.get(polje) or []):
                    hard_flags.extend(validate_dok_reference(stavka, poznati_brojevi, polje))
            analiza["_evidence_check"] = {
                "odluka": "require_review" if hard_flags else "approve",
                "hard_flags": hard_flags,
                "soft_flags": [],
                "provereno_u_ms": round((time.monotonic() - _ev_start) * 1000, 2),
            }
    except Exception as exc_ev:
        _sentry_capture(exc_ev)
        logger.warning("[CASE_DNA] compare_docs evidence-check greška (nije fatalno): %s", exc_ev)

    return {
        "predmet_id": predmet_id,
        "dok_1": f"DOK-{n1:02d}: {docs[0].get('naziv_fajla','')}",
        "dok_2": f"DOK-{n2:02d}: {docs[1].get('naziv_fajla','')}",
        "analiza": analiza,
    }
