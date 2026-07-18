# -*- coding: utf-8 -*-
"""
Vindex AI — Case Genome (Single Source of Truth)

Centralni zivi model predmeta. SVE ostale AI funkcije citaju Genome pre analize.
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
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.usage import UsageService
from services.event_bus import EventType

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
  "snaga_predmeta_procent": 65,
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
    "preporuka": "Konkretna akcija koja bi popravila ovu slabost"
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
- snaga_predmeta_procent = 0-100 (50 = neutralno, 75+ = jaka, <35 = slaba)
- snaga_faktori: min 3 faktora, max 8. SVAKI sa realnim uticajem (+ili-). Zbir treba da objasni snaga_predmeta_procent.
- heatmap: svaka dimenzija 0-100. 0=nema podataka, 50=delimicno, 95=odlicno dokumentovano.
- dokazi_rang: sortiraj od najjaceg do najslabijeg. Ukljuci SVE dokumente iz predmeta.
  zvezdice = round(snaga_score/20), min 1, max 5.
- najslabija_tacka.kriticnost = 0-100 (100 = moze da unisti predmet).
- strategija.scenariji: min 2, max 5 realnih scenarija.
- nedostaje: samo ono sto ZAISTA nedostaje za dokazivanje. Prazna lista ako su svi kljucni dokazi prisutni.
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

async def _extract_genome(docs: list[dict]) -> dict:
    """GPT-4o ekstrakcija Case Genome iz liste dokumenata."""
    if not docs:
        return {}

    parts = []
    for dok in docs[:8]:
        rn = dok.get("redni_broj") or "?"
        naziv = dok.get("naziv_fajla", "dokument")
        tip = dok.get("tip_dokaza") or ""
        kb = dok.get("velicina_kb") or ""
        tekst = (dok.get("tekst_sadrzaj") or "").strip()
        if not tekst:
            continue
        rn_fmt = f"{int(rn):02d}" if str(rn).isdigit() else "?"
        header = f"[DOK-{rn_fmt}: {naziv}"
        if tip:
            header += f" | Vrsta: {tip}"
        if kb:
            header += f" | {kb}KB"
        header += "]"
        parts.append(f"{header}\n{tekst[:4500]}")

    if not parts:
        return {"greska": "Nijedan dokument nema tekst za analizu"}

    combined = "\n\n".join(parts)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _GENOME_SYSTEM},
                {"role": "user", "content": f"Dokumenti predmeta ({len(parts)} dokumenata):\n\n{combined}"},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        result = json.loads(raw)
        result["_genome_docs_count"] = len(parts)
        return result
    except Exception as exc:
        logger.warning("[GENOME] Ekstrakcija greška: %s", exc)
        return {"greska": str(exc)}


def _compute_delta(old_g: dict, new_g: dict) -> dict:
    """Poredi stari i novi Genome. Vraca delta objekat za generisanje inteligentnog alerta."""
    if not old_g or old_g.get("greska") or not new_g or new_g.get("greska"):
        return {}

    stara_snaga = old_g.get("snaga_predmeta_procent") or 0
    nova_snaga  = new_g.get("snaga_predmeta_procent") or 0

    stari_kontr = {(k.get("opis") or "")[:60] for k in (old_g.get("kontradikcije") or [])}
    novi_kontr  = {(k.get("opis") or "")[:60] for k in (new_g.get("kontradikcije") or [])}

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


async def _emit_genome_event(
    supa, predmet_id: str, uid: str, genome: dict, trigger: str,
    prev_verzija: Optional[int] = None,
) -> str:
    """Upisuje GenomeUpdated event u durable outbox ('events' tabela) — Faza 1.1,
    90-dnevni plan 2026-07-18. Zove se SAMO posle uspesnog upisa case_dna kolone.

    Namerno ne zove services.event_bus.emit()/bus.publish() — dispatch_pending_events()
    ce sam procitati ovaj red iz 'events' i pokrenuti handlere kad-tad; direktan
    emit() ovde bi izazvao da se isti handler pokrene dvaput (odmah in-memory i
    ponovo pri dispatch-u). Greska u upisu eventa NIKAD ne sme da obori glavni
    zahtev — isti princip kao _save_genome_history iznad.

    correlation_id (Faza 1.2): generise se ovde, ne u bazi — Event dataclass u
    services/event_bus.py ne nosi DB-generisani 'events.id' kroz dispatch, pa se
    korelacija između outbox eventa i audit_immutable zapisa (1.2) pravi ovde,
    jednom, i deli se u oba payload-a preko istog stringa. Vraca korelacioni ID
    (koristan pozivaocu za logovanje/debug, nije obavezan da se koristi).
    """
    correlation_id = str(uuid.uuid4())
    try:
        await asyncio.to_thread(
            lambda: supa.table("events").insert({
                "event_type": EventType.GENOME_UPDATED.value,
                "user_id": uid,
                "predmet_id": predmet_id,
                "payload": {
                    "verzija": genome.get("verzija"),
                    "prev_verzija": prev_verzija,
                    "snaga_predmeta_procent": genome.get("snaga_predmeta_procent"),
                    "trigger": trigger,
                    "correlation_id": correlation_id,
                },
            }).execute()
        )
    except Exception as exc:
        logger.warning("[GENOME] Event emit greška (nije kritično): %s", exc)
    return correlation_id


async def _run_genome_background(
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

        dok_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id,naziv_fajla,redni_broj,tekst_sadrzaj,velicina_kb")
                .eq("predmet_id", predmet_id)
                .order("redni_broj")
                .limit(10).execute()
        )
        docs = [d for d in (dok_res.data or []) if (d.get("tekst_sadrzaj") or "").strip()]
        if not docs:
            return

        genome = await _extract_genome(docs)

        # Auto-versioning
        genome["verzija"] = stari_verzija + 1

        # Snimi stari u istoriju
        await _save_genome_history(supa, predmet_id, uid, stari_genome, trigger)

        await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .update({"case_dna": genome})
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .execute()
        )

        await _emit_genome_event(supa, predmet_id, uid, genome, trigger, prev_verzija=stari_verzija)

        # Genome Intelligence Delta — pametni alert sa svim promenama
        delta_obj = _compute_delta(stari_genome, genome)
        if _delta_significant(delta_obj):
            verzija = genome.get("verzija", 1)
            tekst = _delta_alert_text(delta_obj, verzija, trigger)
            snaga_d = abs(delta_obj.get("snaga_delta", 0))
            hitnost = "hitan" if snaga_d >= 15 or delta_obj.get("kontr_nove", 0) > 1 else "normalan"
            try:
                await asyncio.to_thread(
                    lambda: supa.table("proactive_alerts").insert({
                        "user_id": uid,
                        "predmet_id": predmet_id,
                        "tekst_alerta": tekst,
                        "tip_alerta": "genome_change",
                        "hitnost": hitnost,
                        "procitana": False,
                    }).execute()
                )
            except Exception as ae:
                logger.warning("[GENOME] Alert insert greška: %s", ae)

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
async def refresh_case_dna(predmet_id: str, user=Depends(PermissionService.require("case_dna"))):
    """Regenerise Case Genome iz svih dokumenata predmeta."""
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
        dok_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id,naziv_fajla,redni_broj,tekst_sadrzaj,velicina_kb")
                .eq("predmet_id", predmet_id)
                .order("redni_broj")
                .limit(10).execute()
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

    genome = await _extract_genome(docs)

    if not genome.get("greska"):
        await UsageService.consume(uid, user.get("email", ""), "case_dna")

    # Auto-versioning
    nova_verzija = stari_verzija + 1
    genome["verzija"] = nova_verzija

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
        await _emit_genome_event(supa, predmet_id, uid, genome, "manual_refresh", prev_verzija=stari_verzija)

    # Genome Intelligence Delta — pametni alert + response
    novi_procent = genome.get("snaga_predmeta_procent")
    delta_obj = _compute_delta(stari_genome, genome)
    alert_msg = None
    if _delta_significant(delta_obj):
        alert_msg = _delta_alert_text(delta_obj, nova_verzija, "manual_refresh")
        snaga_d = abs(delta_obj.get("snaga_delta", 0))
        hitnost = "hitan" if snaga_d >= 15 or delta_obj.get("kontr_nove", 0) > 1 else "normalan"
        try:
            await asyncio.to_thread(
                lambda: supa.table("proactive_alerts").insert({
                    "user_id": uid, "predmet_id": predmet_id,
                    "tekst_alerta": alert_msg,
                    "tip_alerta": "genome_change",
                    "hitnost": hitnost,
                    "procitana": False,
                }).execute()
            )
        except Exception:
            pass

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


@router.post("/{predmet_id}/case-dna/compare")
async def compare_docs(predmet_id: str, req: CompareDoksReq, user=Depends(PermissionService.require("case_dna"))):
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
        parts.append(f"{header}\n{tekst[:5000]}")

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _COMPARE_SYSTEM},
                {"role": "user", "content": f"Uporedjujem:\n\n{parts[0]}\n\n---\n\n{parts[1]}"},
            ],
        )
        analiza = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:
        raise HTTPException(500, f"AI analiza greška: {exc}")

    await UsageService.consume(uid, user.get("email", ""), "case_dna")

    return {
        "predmet_id": predmet_id,
        "dok_1": f"DOK-{n1:02d}: {docs[0].get('naziv_fajla','')}",
        "dok_2": f"DOK-{n2:02d}: {docs[1].get('naziv_fajla','')}",
        "analiza": analiza,
    }
