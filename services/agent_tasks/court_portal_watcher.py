# -*- coding: utf-8 -*-
"""
Vindex AI — services/agent_tasks/court_portal_watcher.py

KORAK B: Autonomni "Background" Action Agenti (2026-07-24)

Analizira NOVE promene koje je routers/portal_monitoring.py već otkrio i
upisao u portal_status_log (portal.sud.rs praćenje statusa predmeta), i za
svaku:
  1. Prepoznaje da li tekst statusa liči na novu presudu/rešenje/odluku
     (keyword heuristika — v. _IZGLEDA_KAO_ODLUKA_RE).
  2. Računa procesni rok (žalba) preko VEĆ POSTOJEĆE logike u
     routers/zastarelost.py (PROCESNI_ROKOVI/_radni_dani_add/
     _srpski_praznici) -- ne izmišlja sopstvenu pravnu matematiku.
  3. Best-effort priprema inicijalni nacrt reakcije preko
     drafting.router.generate_draft (isti /api/nacrt "quick" put koji
     shared/voice_tools.py koristi) -- ako generisanje ne uspe, preporuka
     se svejedno kreira, samo bez nacrta (agent nikad ne sme da izgubi
     signal o promeni zbog toga što je LLM korak otkazao).
  4. Upisuje agent_recommendations red (migracija 082), dedup_key
     sprečava da se ista promena ponovo prijavi sutra.

Agent NIKAD ne piše u predmete/portal_status_log — samo čita odatle i piše
ISKLJUČIVO u agent_recommendations (predlog, ne akcija -- HITL ostaje na
routers/agent_notifications.py).
"""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from shared.llm_retry import llm_retry
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.agent_tasks.court_portal_watcher")

AGENT_TYPE = "court_portal_watcher"

_LOOKBACK_HOURS = 24  # poklapa se sa dnevnim cron ciklusom (/api/cron/daily)

_IZGLEDA_KAO_ODLUKA_RE = re.compile(
    r"\b(presud[ae]|rešenj[ea]|resenj[ea]|odluk[ae]|zaključ[ae]k|zakljucak)\b",
    re.IGNORECASE,
)


def _tip_roka_za_predmet(oblast_prava: str) -> str:
    """Vraća PROCESNI_ROKOVI ključ za žalbu -- gruba heuristika po oblast_prava
    (krivično vs. sve ostalo tretirano kao parnično). Za bilo šta preciznije
    (upravni, prekršajni postupak) potreban je ručni pregled advokata --
    agent to nikad ne tvrdi sa sigurnošću, samo predlaže."""
    if "krivič" in (oblast_prava or "").lower() or "krivic" in (oblast_prava or "").lower():
        return "zalba_kz"
    return "zalba_zpp"


def _izracunaj_rok(tip_roka: str, datum_pocetka: date) -> Optional[date]:
    """Replicira logiku routers/zastarelost.py::izracunaj_procesni_rok (HTTP
    handler, nije čist funkcijski poziv -- ovde se reuse-uju samo podaci/
    helperi: PROCESNI_ROKOVI, _radni_dani_add, _srpski_praznici)."""
    try:
        from routers.zastarelost import PROCESNI_ROKOVI, _radni_dani_add, _srpski_praznici
    except ImportError:
        return None

    rok_info = PROCESNI_ROKOVI.get(tip_roka)
    if not rok_info:
        return None

    if rok_info["tip"] == "radni":
        datum_isteka = _radni_dani_add(datum_pocetka, rok_info["dani"], False)
    else:
        datum_isteka = datum_pocetka + timedelta(days=rok_info["dani"])

    praznici = _srpski_praznici(datum_isteka.year)
    while datum_isteka.weekday() >= 5 or datum_isteka in praznici:
        datum_isteka += timedelta(days=1)
    return datum_isteka


@llm_retry
def _pozovi_nacrt_api(vrsta: str, opis: str, user_id: str) -> dict:
    """CELINA-stil @llm_retry wrapper -- generate_draft interno već ima
    @llm_retry na _call_openai, ali ovde eksplicitno oko celog poziva radi
    dosledno praćenje istog obrasca traženog za sve agent LLM pozive."""
    from drafting.router import generate_draft
    return generate_draft(vrsta, opis, user_id)


async def _pripremi_nacrt(tip_roka: str, opis_situacije: str, user_id: str) -> Optional[str]:
    vrsta_mapa = {"zalba_zpp": "zalba", "zalba_kz": "zalba"}
    vrsta = vrsta_mapa.get(tip_roka)
    if not vrsta:
        return None
    try:
        rezultat = await asyncio.to_thread(_pozovi_nacrt_api, vrsta, opis_situacije, user_id)
        if rezultat.get("status") == "success":
            return rezultat.get("data")
        return None
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[COURT_PORTAL_WATCHER] nacrt generisanje neuspešno: %s", e)
        return None


async def run(user_id: str, supa) -> dict:
    """Pokreće agenta za JEDNOG korisnika. Vraća {"obradjeno": int,
    "preporuke_kreirane": int, "greske": int}. Nikad ne baca -- pozivalac
    (workers/background_agents.py) ovo tretira kao jedan izolovan modul."""
    obradjeno = 0
    preporuke = 0
    greske = 0

    since_iso = (datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)).isoformat()

    try:
        log_r = await asyncio.to_thread(
            lambda: supa.table("portal_status_log")
                .select("praceni_predmet_id,new_status,status_tekst,status_datum,created_at")
                .eq("user_id", user_id)
                .not_.is_("status_tekst", "null")
                .gte("created_at", since_iso)
                .execute()
        )
        promene = log_r.data or []
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[COURT_PORTAL_WATCHER] portal_status_log upit neuspešan uid=%.8s: %s", user_id[:8], e)
        return {"obradjeno": 0, "preporuke_kreirane": 0, "greske": 1}

    if not promene:
        return {"obradjeno": 0, "preporuke_kreirane": 0, "greske": 0}

    pp_ids = list({p["praceni_predmet_id"] for p in promene if p.get("praceni_predmet_id")})
    try:
        pp_r = await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti")
                .select("id,predmet_id,naziv,broj_predmeta,sud_naziv")
                .in_("id", pp_ids)
                .eq("user_id", user_id)  # vlasništvo -- ne obrađuj tuđe praceni_predmeti čak i ako bi id procurio
                .execute()
        )
        pp_map = {pp["id"]: pp for pp in (pp_r.data or [])}
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[COURT_PORTAL_WATCHER] praceni_predmeti upit neuspešan uid=%.8s: %s", user_id[:8], e)
        return {"obradjeno": 0, "preporuke_kreirane": 0, "greske": 1}

    for promena in promene:
        obradjeno += 1
        try:
            pp = pp_map.get(promena.get("praceni_predmet_id"))
            if not pp:
                continue  # ne pripada ovom korisniku ili je izbrisan -- preskoči tiho

            status_tekst = (promena.get("status_tekst") or "").strip()
            status_datum_str = promena.get("status_datum") or date.today().isoformat()
            dedup_key = f"portal:{pp['id']}:{status_datum_str}"

            predmet_id = pp.get("predmet_id")
            oblast_prava = ""
            if predmet_id:
                try:
                    pred_r = await asyncio.to_thread(
                        lambda: supa.table("predmeti")
                            .select("oblast_prava")
                            .eq("id", predmet_id)
                            .eq("user_id", user_id)
                            .maybe_single()
                            .execute()
                    )
                    oblast_prava = (pred_r.data or {}).get("oblast_prava", "") if pred_r.data else ""
                except Exception:
                    pass

            izgleda_kao_odluka = bool(_IZGLEDA_KAO_ODLUKA_RE.search(status_tekst))
            rok_info: dict = {}
            nacrt_tekst: Optional[str] = None

            if izgleda_kao_odluka:
                try:
                    datum_pocetka = date.fromisoformat(status_datum_str)
                except ValueError:
                    datum_pocetka = date.today()
                tip_roka = _tip_roka_za_predmet(oblast_prava)
                rok = _izracunaj_rok(tip_roka, datum_pocetka)
                if rok:
                    rok_info = {
                        "tip_roka": tip_roka,
                        "datum_pocetka": datum_pocetka.isoformat(),
                        "datum_isteka": rok.isoformat(),
                        "dana_do_isteka": (rok - date.today()).days,
                        "hitno": (rok - date.today()).days <= 7,
                    }
                opis_situacije = (
                    f"Predmet {pp.get('naziv', '')} ({pp.get('broj_predmeta', '')}), "
                    f"sud {pp.get('sud_naziv', '')}. Nova objava na portalu: {status_tekst}. "
                    f"Pripremi inicijalni nacrt reakcije."
                )
                nacrt_tekst = await _pripremi_nacrt(tip_roka, opis_situacije, user_id)

            naslov = f"Nova objava: {pp.get('naziv', 'predmet')} — {status_tekst[:80]}"
            opis = (
                f"Portal.sud.rs promena statusa {status_datum_str} za predmet "
                f"{pp.get('broj_predmeta', '')} ({pp.get('sud_naziv', '')})."
            )
            payload = {
                "praceni_predmet_id": pp["id"],
                "status_tekst": status_tekst,
                "status_datum": status_datum_str,
                "izgleda_kao_odluka": izgleda_kao_odluka,
                "rok": rok_info,
                "nacrt_reakcije": nacrt_tekst,
            }

            try:
                await asyncio.to_thread(
                    lambda: supa.table("agent_recommendations").insert({
                        "user_id":    user_id,
                        "predmet_id": predmet_id,
                        "agent_type": AGENT_TYPE,
                        "naslov":     naslov,
                        "opis":       opis,
                        "payload":    payload,
                        "dedup_key":  dedup_key,
                    }).execute()
                )
                preporuke += 1
            except Exception as e:
                # Unique-violation na (user_id, dedup_key) je OČEKIVANO
                # (već prijavljeno prethodnog dana) -- nije greška.
                if "duplicate key" not in str(e).lower() and "23505" not in str(e):
                    _sentry_capture(e)
                    logger.warning("[COURT_PORTAL_WATCHER] insert preporuke neuspešan: %s", e)
                    greske += 1

        except Exception as e:
            _sentry_capture(e)
            logger.warning("[COURT_PORTAL_WATCHER] obrada promene neuspešna uid=%.8s: %s", user_id[:8], e)
            greske += 1

    return {"obradjeno": obradjeno, "preporuke_kreirane": preporuke, "greske": greske}
