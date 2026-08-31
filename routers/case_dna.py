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
# A002: isti regex koji `_validate_kontradikcije_lokacije` koristi za validaciju
# DOK-NN oznaka. Uvozi se umesto da se prepiše — dva izraza za isti pojam bi
# značila dva vlasnika istog pravila.
from shared.genome_validator import _DOK_PATTERN
from shared.contradiction_identity import (contradiction_identity,
                                            uporedi_kontradikcije,
                                            identitet_seme_po_tvrdnjama)
# A014: katalog referenci na tvrdnje. Uvozi se, ne prepisuje — jedan vlasnik
# pravila o tome sta model sme da referise.
from shared.claim_catalog import MAKS_TVRDNJI as _MAKS_TVRDNJI, napravi_katalog, redovi_za_prompt
from services.v2_observation import upisi_v2_opazanje
from services.v2_contradiction_persistence import (
    V2PackageRejected, V2StaleObservation)

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
    {"naziv": "Rok zastarelosti/zalbeni rok/sl.", "datum": "YYYY-MM-DD ili null", "opis": "Posledica propustanja", "status": "aktivan|prosao|nepoznat", "lokacija": "DOK-XX str.Y -- iz KOG dokumenta rok potice; prazan string ako rok ne potice iz jednog konkretnog dokumenta"}
  ],
  "kontradikcije": [
    {"issue_label": "Kratak naziv JEDNE sporne tacke (npr. 'razlika u datumu prestanka')", "claim_refs": ["CLAIM-001", "CLAIM-004"], "relation_type": "cinjenica_cinjenica", "opis": "Tacno sta se kosi (citati ako moguce)", "lokacija_1": "DOK-01 str.X ili opis", "lokacija_2": "DOK-02 str.Y ili opis", "tezina": "kriticna|vazna|manja"},
    {"issue_label": "DRUGA, nezavisna sporna tacka - zaseban zapis, ne spajati sa gornjim", "claim_refs": ["CLAIM-002", "CLAIM-005"], "relation_type": "cinjenica_norma", "opis": "...", "lokacija_1": "DOK-01 str.X", "lokacija_2": "DOK-03 str.Y", "tezina": "vazna"}
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
- kontradikcije: LISTA je, i broj stavki NIJE ogranicen. Vrati SVAKU nezavisnu
  spornu tacku kao ZASEBAN objekat u toj listi. Prazna lista je ispravna ako
  predmet nema kontradikciju - ne izmisljaj je da bi lista bila puna.
  ZABRANJENO je spojiti dve sporne tacke u jedan zapis samo zato sto dele isti
  dokument, istu stranu, istu lokaciju ili isti pravni kontekst. Primer: ako se
  dokumenti ne slazu i oko DATUMA prestanka i oko IZNOSA duga, to su DVE
  kontradikcije, ne jedna. Zapis oblika "postoje razlike izmedju dokumenata" je
  NEISPRAVAN - svaka stavka mora imenovati JEDNU spornu tacku.
  Dve tvrdnje iz ISTOG dokumenta koje se medjusobno kose su takodje
  kontradikcija (npr. dva svedoka u istom zapisniku) - navedi ih kao zaseban
  zapis, sa oba lokatora unutar tog dokumenta.
- kontradikcije.claim_refs: OBAVEZNO polje. Navedi oznake CLAIM-NNN iz sekcije
  EVIDENCE VAULT koje su STVARNI ucesnici te sporne tacke. Dozvoljene su ISKLJUCIVO
  oznake koje su ti date u toj sekciji — NIKAD ne izmisljaj oznaku, ne pisi UUID,
  ne pisi naziv dokumenta. Ako sekcija EVIDENCE VAULT nije data ili u njoj nema
  tvrdnji koje se stvarno kose, vrati praznu listu kontradikcija; prazna lista je
  ISPRAVNA, izmisljena referenca NIJE.
  Jedna kontradikcija sme imati VISE OD DVE reference: ako se tri tvrdnje
  medjusobno iskljucuju oko istog pitanja (npr. tri razlicita datuma istog
  dogadjaja), to je JEDNA sporna tacka sa TRI reference, a NE tri sporne tacke.
  Najmanji broj referenci je dve.
- kontradikcije.relation_type: tacno jedna od dve vrednosti.
  "cinjenica_cinjenica" = dve cinjenicne tvrdnje se kose medjusobno.
  "cinjenica_norma" = cinjenicna tvrdnja se kosi sa pravnom normom/propisom.
  Nikad ne izvodi ovu vrednost iz dokumenta, labele, lokacije ni tezine.
- kontradikcije.issue_label: naziv JEDNE sporne tacke. Naziv NIJE identitet —
  dve sporne tacke sa istim nazivom a razlicitim claim_refs ostaju DVE.
  Dodavanje novog dokumenta NE spaja postojece razlicite sporne tacke.
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
    ignorise. Nikad ne baca — advisory kontekst, ne sme oboriti ekstrakciju.

    A014 (2026-08-30): dodati su `id`/`predmet_id`/`deleted_at` — bez `id`
    tvrdnja nije mogla da dobije referencu, pa kontradikcija nije mogla da
    nosi `claim_refs` (v. shared/claim_catalog.py). Dodat je i `.order("id")`:
    `.limit()` bez `order` ne garantuje ISTI podskup u dva uzastopna refresh-a,
    pa bi ista tvrdnja mogla da dobije razlicitu oznaku — ili da nestane iz
    kataloga izmedju dva poziva."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_dokazi")
                .select("id,predmet_id,tvrdnja,kategorija,pravni_element,deleted_at")
                .eq("predmet_id", predmet_id)
                .is_("deleted_at", "null")
                .order("id")
                .limit(_MAKS_TVRDNJI)
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
    predmet_id: Optional[str] = None,
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
    ostaje isto kao pre (priblizno, iz already-limited liste).

    predmet_id (A014): opseg kataloga referenci na tvrdnje. Prosledjuje se
    EKSPLICITNO -- prva verzija ga je zakljucivala iz `dokazi[i]["predmet_id"]`,
    pa je pozivalac koji taj kljuc ne salje TIHO gubio ceo EVIDENCE VAULT blok.
    Opseg se ne pogadja iz podataka. Bez `predmet_id` blok se i dalje salje, u
    anonimnom obliku od pre A014 -- kontekst nikad ne nestaje, nestaju samo
    oznake, pa kontradikcija ne moze da nosi `claim_refs` i bude odbijena
    nizvodno (fail-closed), umesto da ovde tiho oslabi prompt."""
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

    # A014: tvrdnje vise nisu anonimni redovi nego IMENOVANE reference — ali
    # SAMO kada je poznat opseg (`predmet_id`). Katalog je deterministican i
    # predmet-scoped (shared/claim_catalog.py), pa ga pozivalac koji
    # materijalizuje kontradikcije rekonstruise istim pozivom nad istom listom
    # `dokazi` — nista se ne prenosi kroz stanje.
    #
    # Bez `predmet_id` blok se NE gubi nego se salje u obliku od pre A014.
    # Tiho izbacivanje bi vratilo forenzicki nalaz od 2026-07-22 ("Genome nikad
    # ne cita predmet_dokazi"), i to bez ijednog signala.
    if dokazi:
        katalog = napravi_katalog(dokazi, predmet_id) if predmet_id else {}
        if katalog:
            zaglavlje = (
                "\n\n[EVIDENCE VAULT — već klasifikovane ključne činjenice iz ovih dokumenata. "
                "Koristi kao dodatni kontekst; ne izmišljaj nove ako se ne poklapaju sa tekstom. "
                "OZNAKE CLAIM-NNN su JEDINE dozvoljene vrednosti za kontradikcije[].claim_refs]\n"
            )
            dokazi_lines = redovi_za_prompt(katalog, dokazi)
        else:
            zaglavlje = (
                "\n\n[EVIDENCE VAULT — već klasifikovane ključne činjenice iz ovih dokumenata, "
                "koristi kao dodatni kontekst, ne izmišljaj nove ako se ne poklapaju sa tekstom]\n"
            )
            dokazi_lines = []
            for d in dokazi[:_MAKS_TVRDNJI]:
                tvrdnja = (d.get("tvrdnja") or "").strip()
                if not tvrdnja:
                    continue
                elm = f" [{d.get('pravni_element')}]" if d.get("pravni_element") else ""
                dokazi_lines.append(f"- {tvrdnja}{elm}")
        if dokazi_lines:
            combined += zaglavlje + "\n".join(dokazi_lines)

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
        # Operation Single Brain, Mission 002 (Team 3 finding): heatmap and dokazi_rang[].
        # snaga_score were never clamped -- only the headline snaga_predmeta_procent/
        # kriticnost/genome_kompletnost fields got this discipline in prior missions, the
        # exact "guarded the headline, missed the sibling field" pattern the platform has
        # hit repeatedly. Rendered raw at static/vindex.js:17368-17370 (heatmap bars +
        # literal "N%" text) and :17383-17636 (dokazi_rang's raw snaga_score, also used to
        # filter "weak evidence" at <70 -- only the DERIVED star rating was separately
        # clamped 1-5, not the underlying number this filter reads).
        _hm = result.get("heatmap")
        if isinstance(_hm, dict):
            for _k, _v in list(_hm.items()):
                try:
                    _hm[_k] = max(0, min(100, int(_v)))
                except (TypeError, ValueError):
                    _hm[_k] = 0
        # ── A001: KANONSKI IDENTITET DOKUMENTA U `dokazi_rang` ──────────────
        # Genome je do sada dokument identifikovao ISKLJUČIVO imenom fajla
        # (`naziv`), koje LLM prepisuje iz zaglavlja. Ime fajla nije identitet:
        # menja se pri preimenovanju, a dva dokumenta istog predmeta smeju da
        # se zovu isto. Zato se ovde svakoj stavci dodaje `dokument_id` —
        # stvarni `predmet_dokumenti.id`, izveden DETERMINISTIČKI iz `docs`,
        # nikad od strane LLM-a.
        #
        # Pravilo poklapanja je NAMERNO isto kao u
        # shared/genome_validator.py::_validate_dokazi_rang (strip + lower),
        # da bi rezolucija i validacija govorile o istom pojmu. Nema fuzzy
        # poklapanja, nema „najbližeg" dokumenta.
        #
        # FAIL-CLOSED: ako ime ne pogađa nijedan dokument ILI pogađa više njih
        # (isti naziv fajla u istom predmetu), `dokument_id` ostaje None.
        # Nerazrešeno je tačan podatak; izmišljena veza nije.
        _po_nazivu: dict[str, list[str]] = {}
        for _doc in (docs or []):
            _kljuc = (_doc.get("naziv_fajla") or "").strip().lower()
            _did = _doc.get("id")
            if _kljuc and _did:
                _po_nazivu.setdefault(_kljuc, []).append(_did)

        for _d in (result.get("dokazi_rang") or []):
            if not isinstance(_d, dict):
                continue
            if "snaga_score" in _d:
                try:
                    _d["snaga_score"] = max(0, min(100, int(_d["snaga_score"])))
                except (TypeError, ValueError):
                    _d["snaga_score"] = 0
            _kandidati = _po_nazivu.get((_d.get("naziv") or "").strip().lower(), [])
            _d["dokument_id"] = _kandidati[0] if len(_kandidati) == 1 else None

        # ── A002: KANONSKI IDENTITET DOKUMENTA U `kontradikcije` ────────────
        # `lokacija_1`/`lokacija_2` su oblika "DOK-NN str.Y". `DOK-NN` NIJE
        # LLM izmišljotina nego oznaka izvedena iz stvarne kolone
        # `predmet_dokumenti.redni_broj`, koju migracija 106 čuva UNIQUE
        # indeksom nad (predmet_id, redni_broj). Zato je rezolucija ovde
        # jača nego kod `dokazi_rang`: jedinstvenost garantuje baza, ne
        # konvencija imenovanja fajlova.
        #
        # `_DOK_PATTERN` se UVOZI iz shared/genome_validator.py umesto da se
        # ovde ponovo napiše -- isti regex mora da važi i za validaciju i za
        # rezoluciju. Dva zasebna izraza za isti pojam su tačno obrazac koji
        # ovaj repo zabranjuje (jedan koncept = jedan vlasnik).
        #
        # `lokacija_1`/`lokacija_2` se NE DIRAJU: one su i prikaz i ulaz u
        # shared/contradiction_identity.py::contradiction_identity, čiji heš
        # završava u `case_actions.dedupe_key`. Identitet kontradikcije
        # ostaje nepromenjen; ovde se dodaje SAMO referenca na dokument.
        _po_rednom: dict[int, list[str]] = {}
        for _doc in (docs or []):
            _rb, _did = _doc.get("redni_broj"), _doc.get("id")
            if _did and str(_rb or "").isdigit():
                _po_rednom.setdefault(int(_rb), []).append(_did)

        for _k in (result.get("kontradikcije") or []):
            if not isinstance(_k, dict):
                continue
            for _polje, _cilj in (("lokacija_1", "dokument_id_1"),
                                  ("lokacija_2", "dokument_id_2")):
                _m = _DOK_PATTERN.search(_k.get(_polje) or "")
                _kand = _po_rednom.get(int(_m.group(1)), []) if _m else []
                # FAIL-CLOSED: bez DOK-NN oznake, nepoznat broj ili više
                # kandidata -> None. Nikad `_kand[0]`.
                _k[_cilj] = _kand[0] if len(_kand) == 1 else None

        # ── B8: KANONSKI IZVOR ROKA ─────────────────────────────────────────
        # Rok je do sada zavrsavao u `predmet_hronologija` bez ijedne reference
        # na dokument iz kog potice -- advokat je video "Rok za zalbu: 15 dana"
        # i nije mogao da dodje do resenja koje ga je pokrenulo.
        #
        # Ne uvodi se NOV identitet: koristi se ISTI `_po_rednom` i ISTI
        # `_DOK_PATTERN` koje A002 vec gradi dva bloka iznad. `DOK-NN` je
        # izveden iz `predmet_dokumenti.redni_broj`, koji migracija 106 cuva
        # UNIQUE indeksom -- jedinstvenost garantuje baza, ne konvencija.
        #
        # FAIL-CLOSED, isto kao A002: bez oznake, nepoznat broj ili vise
        # kandidata -> `None`. Nerazresen izvor je tacan podatak; izmisljena
        # veza nije. `lokacija` se NE dira -- ostaje i prikaz i ulaz.
        for _r in (result.get("rokovi_kriticni") or []):
            if not isinstance(_r, dict):
                continue
            _m = _DOK_PATTERN.search(_r.get("lokacija") or "")
            _kand = _po_rednom.get(int(_m.group(1)), []) if _m else []
            _r["dokument_id"] = _kand[0] if len(_kand) == 1 else None
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

    # A016.7 §9 -- identitet po TVRDNJAMA kad ga obe strane nose, inace stari
    # identitet po lokacijama. Sema se bira JEDNOM za celo poredjenje, ne po
    # stavci: mesanje bi na prvom refresh-u posle A014 prijavilo laznu promenu.
    _stare_k = old_g.get("kontradikcije") or []
    _nove_k  = new_g.get("kontradikcije") or []
    if identitet_seme_po_tvrdnjama(_stare_k, _nove_k):
        # Identitet po tvrdnjama + pravilo sadrzavanja (A008). Broji se
        # uparivanjem, ne razlikom skupova -- vidi `uporedi_kontradikcije`.
        _kontr_nove, _kontr_elim = uporedi_kontradikcije(_stare_k, _nove_k)
    else:
        # Stari put, netaknut: snimci pre A014 nemaju `claim_refs`.
        stari_kontr = {contradiction_identity(k) for k in _stare_k}
        novi_kontr  = {contradiction_identity(k) for k in _nove_k}
        _kontr_nove = len(novi_kontr - stari_kontr)
        _kontr_elim = len(stari_kontr - novi_kontr)

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
        "kontr_eliminisane":    _kontr_elim,
        "kontr_nove":           _kontr_nove,
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
        # BLK-2.1 — Genome refresh je pozadinski zadatak koji finalize pokrece
        # 3s kasnije; ako advokat u medjuvremenu obrise predmet, ovaj upis je
        # tacno onaj koji ostavlja orphan. Guard je isti kao u emit_durable.
        from services.event_bus import predmet_prima_dogadjaje as _prima
        if not await _prima(supa, _row.get("predmet_id")):
            logger.info("[GENOME] Event nije upisan — predmet se brise ili je obrisan.")
            return correlation_id
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
    # B8: `dokument_id` -> `naziv_fajla`, da hronologija prikaze STVARNO ime
    # dokumenta iz kog rok potice. Cita se opsegom predmeta; nerazresen rok
    # ostaje bez naziva (None), nikad sa pogodjenim.
    _dok_nazivi: dict[str, str] = {}
    try:
        _dr = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").select("id,naziv_fajla")
                .eq("predmet_id", predmet_id).execute()
        )
        _dok_nazivi = {d["id"]: d.get("naziv_fajla") or "" for d in (_dr.data or [])}
    except Exception as exc:
        logger.warning("[GENOME] Sync rokovi — citanje dokumenata: %s", exc)
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
        # B8: naziv dokumenta se izvodi iz razresenog `dokument_id`, ne iz teksta
        # koji je model napisao. Kolona `dokument_naziv` vec postoji, pa ovaj deo
        # NE trazi migraciju. Puni `dokument_id` u hronologiji ceka migraciju 126.
        _dok_naziv = _dok_nazivi.get(r.get("dokument_id")) if r.get("dokument_id") else None
        dogadjaj = f"{naziv}: {(r.get('opis') or '').strip()}"[:200] if r.get("opis") else naziv[:200]
        if (dogadjaj, datum) in postojeci:
            continue
        try:
            await asyncio.to_thread(lambda dg=dogadjaj, dt=datum, dn=_dok_naziv: supa.table("predmet_hronologija").insert({
                "predmet_id": predmet_id,
                "user_id":    uid,
                "dogadjaj":   dg,
                "datum":      dt,
                "datum_iso":  dt,
                "vaznost":    "kritičan",
                "akter":      "Genome (AI)",
                "dokument_naziv": dn,
            }).execute())
            upisano += 1
        except Exception as exc:
            logger.warning("[GENOME] Sync rokovi — insert greška: %s", exc)
    return upisano


_genome_refresh_inflight: set = set()
_genome_refresh_rerun: set = set()
# Program Phoenix, Mission 012 (LIVINGSYS-DEBT-045): a SEPARATE dict from
# _genome_refresh_inflight (which stays a plain set -- routers/case_dna.py's
# own refresh_case_dna endpoint below also reads/writes it directly, as a
# reject-if-busy guard, and must not be touched here). Only _run_genome_
# background's own coalesced (early-return) callers wait on this.
_genome_refresh_done_event: dict = {}
# Program Phoenix, Mission 012 (LIVINGSYS-DEBT-045): module-level (not inlined)
# so tests can patch it to a short value to deterministically exercise the
# timeout-fallback path without a real 120s wait.
_GENOME_COALESCE_WAIT_TIMEOUT = 120.0


async def _run_genome_background(
    predmet_id: str, uid: str, stari_procent: Optional[int] = None,
    trigger: str = "upload_trigger", event_id: Optional[str] = None,
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
    documented here as a real limitation, not claimed as a complete fix.

    Program Phoenix, Mission 012 (LIVINGSYS-DEBT-045): a coalesced
    (early-return) caller used to return near-instantly, before the
    in-flight run's own rerun loop had actually finished covering its
    trigger. services/case_evolution.py::_consequence_genome_refresh reads
    case_dna.verzija immediately after this function returns to verify the
    refresh really happened -- for a coalesced caller reading THAT early,
    verzija was frequently still unchanged, so a genuinely-in-progress
    refresh was misreported as a failed one (root cause of up to 3
    redundant refreshes for 2 concurrent uploads: 2 real GPT-cost runs plus
    a 3rd wasted retry from the false failure). A coalesced caller now
    waits for the in-flight run's completion event before returning, so
    every caller's own downstream verification observes genuinely
    completed work -- BOUNDED (120s: the single-call GPT timeout below is
    60s, this covers one full retry/backoff cycle plus margin), never an
    unbounded wait. Without this bound, a coalesced caller used to return
    instantly regardless of how long the in-flight run took; making it wait
    without a cap would mean one hung/slow underlying GPT call now also
    blocks every OTHER concurrent trigger for the same case instead of
    just its own -- a strictly worse failure mode than the one being fixed.
    On timeout, falls back to the pre-mission behavior (return without
    waiting further) rather than raising."""
    # A016.7 (§6) -- `event_id` je identitet KONKRETNOG run-a, prosledjen aditivno
    # do persistence sloja. Dva merena ogranicenja koja ovaj parametar NE resava i
    # koja se zato ne smeju predstaviti kao resena:
    #
    #   (1) COALESCING GA ODBACUJE. Grana odmah ispod: drugi triger za isti predmet
    #       se sazima u vec pokrenuti run. Njegov `event_id` nestaje, a opazanje
    #       koje ga pokriva nosi TUDJI event_id. Identitet run-a je zato identitet
    #       IZVRSENOG opazanja, ne identitet svakog povoda za njega.
    #   (2) RERUN PETLJA GA PONAVLJA. Petlja nize poziva _do_genome_refresh vise
    #       puta sa ISTIM `event_id`, pa jedan event moze proizvesti N opazanja.
    #
    # Posledica za A016.7 §6 ("razlikovati retry istog run-a od novog run-a sa istim
    # sadrzajem"): na ovom sloju to jos NIJE moguce. Vidi i migraciju 124 -- ni baza
    # ne pamti `event_id`, jer bi to trazilo drugu kolonu (§5 dozvoljava samo jednu).
    if predmet_id in _genome_refresh_inflight:
        _genome_refresh_rerun.add(predmet_id)
        _done_event = _genome_refresh_done_event.get(predmet_id)
        if _done_event is not None:
            try:
                await asyncio.wait_for(_done_event.wait(), timeout=_GENOME_COALESCE_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(
                    "[GENOME] coalesced caller timed out waiting for in-flight refresh predmet=%s",
                    predmet_id,
                )
        return
    _genome_refresh_inflight.add(predmet_id)
    _my_event = asyncio.Event()
    _genome_refresh_done_event[predmet_id] = _my_event
    try:
        while True:
            _genome_refresh_rerun.discard(predmet_id)
            await _do_genome_refresh(predmet_id, uid, stari_procent, trigger,
                                     event_id=event_id)
            if predmet_id not in _genome_refresh_rerun:
                break
    finally:
        _genome_refresh_inflight.discard(predmet_id)
        _genome_refresh_rerun.discard(predmet_id)
        _genome_refresh_done_event.pop(predmet_id, None)
        _my_event.set()


async def _do_genome_refresh(
    predmet_id: str, uid: str, stari_procent: Optional[int] = None,
    trigger: str = "upload_trigger", event_id: Optional[str] = None,
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
            genome = await _extract_genome(docs, dokazi=dokazi_ctx, ukupno_u_predmetu=ukupno_dokumenata, predmet_id=predmet_id)
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

        # ── A017: V2 OPAZANJE IDE PRVO ───────────────────────────────────────
        # Namerno PRE `_sync_rokovi_to_hronologija`, `_save_genome_history` i
        # upisa `case_dna`. Sve tri linije ispod PISU. Kad bi V2 isao posle njih,
        # neuspeh V2 paketa ostavio bi hronologiju, istoriju i `case_dna` upisane
        # a V2 sliku praznu -- tacno stanje koje A017 par.2 zabranjuje
        # ("Python ima nove Genome rezultate ali V2 persistence nije uspeo").
        #
        # Ovde se NISTA ne hvata. Izuzetak putuje do spoljnog `except` ove
        # funkcije, koji ga loguje i vraca se BEZ ijednog upisa -- pa `verzija`
        # ostaje nepromenjena, a `services/case_evolution.py::
        # _consequence_genome_refresh` to vec tretira kao neuspeh posledice i
        # prepusta event bus-u retry/dead-letter. To je POSTOJECI kanonski
        # mehanizam, ne novo stanje.
        _v2 = await upisi_v2_opazanje(
            predmet_id=predmet_id, user_id=uid, genome=genome,
            dokazi=dokazi_ctx, event_id=event_id)
        logger.info("[A017] V2 opazanje upisano predmet=%s kandidata=%d odbijeno=%d "
                    "kompletno=%s v_obs=%s", predmet_id, _v2["kandidata"],
                    _v2["odbijeno"], _v2["kompletno"], _v2["observation_version"])

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
    except (V2StaleObservation, V2PackageRejected) as _v2_odbijeno:
        # ── A017.1 (G5): ODBIJENO OPAZANJE NE SME DA PRODJE KAO USPEH ────────
        # Izmereno pre popravke (4/6 kolizija): gubitnik trke dobije `55000`,
        # V2 mu NE upise nista, `case_dna` ostane nepromenjen -- ali njegova
        # posledica (`services/case_evolution.py::_consequence_genome_refresh`)
        # uporedjuje verziju PRE i POSLE, a POBEDNIK ju je u medjuvremenu
        # pomerio. Posledica zato vidi promenu i vraca USPEH za opazanje koje
        # nikad nije postalo kanonsko.
        #
        # Zato se ova dva izuzetka PROPAGIRAJU umesto da se progutaju. Time se
        # ne uvodi novo stanje: posledica pada, Event Bus je oznaci `failed` i
        # primeni svoj vec dokazani retry/dead-letter -- POSTOJECI kanonski
        # mehanizam (isti kojim se resava i `verzija unchanged`).
        #
        # Kanonsko stanje POBEDNIKA ostaje netaknuto: do ovog mesta se stize sa
        # NULA upisa (V2 ide pre `_sync_rokovi_to_hronologija`,
        # `_save_genome_history` i upisa `case_dna`), pa odbijeni refresh nema
        # sta da ponisti.
        #
        # Genericki kvarovi (mreza, RPC, neocekivano) NAMERNO ostaju na starom
        # ugovoru ispod -- njih pokriva provera `verzija unchanged`, i njihova
        # semantika nije predmet ovog sprinta.
        logger.warning(
            "[GENOME] refresh predmet=%s ODBIJEN (%s) -- opazanje NIJE kanonsko, "
            "posledica se prijavljuje kao neuspeh: %s",
            predmet_id, type(_v2_odbijeno).__name__, _v2_odbijeno)
        raise
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
        # Final Beta Gate F4 (MEDIUM): case_dna had no ai_generated marker in
        # its JSON response, unlike digital_twin/court_predictor/hearing_cc/
        # cio since Phoenix Closure's LIVINGSYS-DEBT-025. At the response
        # level (not inside `genome` itself, which is the exact dict persisted
        # to predmeti.case_dna -- adding fields there would pollute the
        # stored column).
        "ai_generated": bool(genome and not genome.get("greska")),
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
        genome = await _extract_genome(docs, dokazi=dokazi_ctx, ukupno_u_predmetu=ukupno_dokumenata, predmet_id=predmet_id)

    # Final Beta Gate F2 (HIGH): this MANUAL refresh path used to lack the
    # same guard _run_genome_background already has (see the long comment on
    # that function, Program Lambda Cert 004 + its own Phase 6 key-presence
    # hardening) -- a GPT extraction failure returns a bare {"greska": ...}
    # signal, and this endpoint used to write THAT over the live case_dna
    # column regardless (a JSON-column .update() is a full-value REPLACE),
    # silently wiping the whole Genome while still reporting
    # "case_dna_persisted": true with a success toast. Same key-presence
    # check as the background path, applied here for the first time.
    if "greska" in genome:
        logger.warning(
            "[GENOME] manual refresh predmet=%s NEUSPEŠAN -- postojeći case_dna (v%s) OSTAJE NEPROMENJEN: %s",
            predmet_id, stari_verzija, genome.get("greska"),
        )
        return {
            "predmet_id": predmet_id,
            "predmet_naziv": pred_check.data.get("naziv"),
            "case_dna": stari_genome,
            "docs_analizirano": len(docs),
            "snaga_procent": stari_procent,
            "verzija": stari_verzija,
            "intelligence_delta": None,
            "snaga_promena": None,
            "case_dna_persisted": False,
            "poruka": (
                f"Case Genome osvežavanje nije uspelo (greška u AI ekstrakciji) -- "
                f"prikazan je prethodni sačuvani Genome (v{stari_verzija}). Pokušajte ponovo."
            ),
        }

    await UsageService.consume(uid, user.get("email", ""), "case_dna")

    # Auto-versioning
    nova_verzija = stari_verzija + 1
    genome["verzija"] = nova_verzija

    # Faza 1.3 — Genome Verification Layer (advisory, non-blocking, nula GPT poziva)
    genome["_verifikacija"] = verify_genome(genome, docs)
    genome["_analiza_osnov"] = await _compute_analiza_osnov(supa, predmet_id, docs)

    # ── A017: V2 OPAZANJE IDE PRVO (isti kanonski ulaz kao pozadinski put) ────
    # Rucni refresh je DRUGI proizvodjac Genome opazanja. Da V2 nije uvezan i
    # ovde, advokat bi rucnim refresh-om dobio novi `case_dna` bez V2 slike, pa
    # bi Rule 3 projektovao iz zastarelog V2 stanja.
    #
    # Neuspeh se NE prikazuje kao uspeh, ali se ni ne uvodi novo stanje: koristi
    # se POSTOJECI `case_dna_persisted=False` odgovor (Singular Intelligence,
    # 2026-08-07) koji vec znaci "izracunato je, ali NIJE sacuvano". Advokat
    # vidi tacno onu poruku koju bi video i da je pao upis u bazu.
    _v2_ok = True
    try:
        _v2 = await upisi_v2_opazanje(
            predmet_id=predmet_id, user_id=uid, genome=genome,
            dokazi=dokazi_ctx, event_id=None)
        logger.info("[A017] V2 opazanje upisano (manual) predmet=%s kandidata=%d "
                    "odbijeno=%d kompletno=%s", predmet_id, _v2["kandidata"],
                    _v2["odbijeno"], _v2["kompletno"])
    except Exception as _v2_exc:
        logger.warning("[A017] V2 opazanje NEUSPESNO (manual) predmet=%s: %s -- "
                       "case_dna se NE upisuje", predmet_id, _v2_exc)
        _v2_ok = False

    if not _v2_ok:
        return {
            "predmet_id": predmet_id,
            "predmet_naziv": pred_check.data.get("naziv"),
            "case_dna": stari_genome,
            "docs_analizirano": len(docs),
            "snaga_procent": stari_genome.get("snaga_predmeta_procent") if isinstance(stari_genome, dict) else None,
            "verzija": stari_verzija,
            "intelligence_delta": None,
            "snaga_promena": None,
            "case_dna_persisted": False,
            "poruka": (
                f"Case Genome v{nova_verzija} je izracunat ali NIJE sacuvan zbog greske u bazi -- "
                f"prikazan je prethodni sacuvani Genome (v{stari_verzija}). Pokusajte ponovo."
            ),
        }

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

    logger.info("[GENOME] refresh predmet=%s docs=%d snaga=%s%% v%s update_ok=%s",
                predmet_id, len(docs), novi_procent, nova_verzija, _update_ok)

    # Operation Singular Intelligence (2026-08-07), Database Reality Team finding: this response
    # used to be built from the NEW `genome` dict and a "regenerisan" success message
    # UNCONDITIONALLY, even when the `predmeti.case_dna` UPDATE above failed (_update_ok=False).
    # A lawyer would see the new Genome and a success toast, then reload and find the OLD
    # (unchanged) genome with no error ever surfaced -- the response lied about what was actually
    # persisted. Now honestly reflects the real DB state: on failure, returns the genome that is
    # ACTUALLY still in predmeti.case_dna (stari_genome) with an explicit failure signal, not the
    # unsaved new one.
    if not _update_ok:
        return {
            "predmet_id": predmet_id,
            "predmet_naziv": pred_check.data.get("naziv"),
            "case_dna": stari_genome,
            "docs_analizirano": len(docs),
            "snaga_procent": stari_genome.get("snaga_predmeta_procent") if isinstance(stari_genome, dict) else None,
            "verzija": stari_verzija,
            "intelligence_delta": None,
            "snaga_promena": None,
            "case_dna_persisted": False,
            "poruka": (
                f"Case Genome v{nova_verzija} je izračunat ali NIJE sačuvan zbog greške u bazi -- "
                f"prikazan je prethodni sačuvani Genome (v{stari_verzija}). Pokušajte ponovo."
            ),
        }

    return {
        "predmet_id": predmet_id,
        "predmet_naziv": pred_check.data.get("naziv"),
        "case_dna": genome,
        "docs_analizirano": len(docs),
        "snaga_procent": novi_procent,
        "verzija": nova_verzija,
        "intelligence_delta": delta_obj if delta_obj else None,
        "snaga_promena": alert_msg,
        "case_dna_persisted": True,
        "poruka": f"Case Genome v{nova_verzija} regenerisan iz {len(docs)} dokumenata.",
        "ai_generated": True,
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
