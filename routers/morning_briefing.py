# -*- coding: utf-8 -*-
"""
Vindex AI — routers/morning_briefing.py

Daily Morning Briefing: personalizovani AI jutarnji izveštaj za svakog advokata.
Šalje se automatski u 8:00 ili na zahtev.

Program Omega, Sprint 004 (2026-08-06) — Unified Legal Workspace: ovaj modul
OSTAJE kao email/narativni digest kanal (genuinski drugačiji distribucioni
kanal od in-app pregleda — GPT tekst poslat na mejl), ali NIJE kanonski
operativni pogled. Kanonski, deterministički, sourced odgovor na "šta
advokat treba danas da radi" je `GET /api/workspace` (Responsibility Matrix:
"postaje podmodul" — docs/omega/UNIFIED_WORKSPACE_ARCHITECTURE.md).

Endpoints:
  GET  /api/briefing/daily          — generiši briefing za trenutnog korisnika (on-demand)
  POST /api/briefing/cron           — admin endpoint, šalje svim korisnicima (poziva cron)
  POST /api/briefing/send-email     — pošalji briefing emailom
  GET  /api/briefing/history        — prethodnih 7 dana briefinga
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from shared.case_context import build_case_context
from shared.case_readiness import top_open_action
from shared import rokovi as _rokovi_domen
from shared.attention_priority import canonical_sort_key
# FAZA 6.4.2: jutarnji brifing odlazi EMAIL-om -- ista kanonska kapija kao
# ostali izlazi. Rok bez ljudske potvrde ne ulazi u poruku.
from shared.rokovi import filtriraj_izvrsive as _filtriraj_izvrsive
from shared.rok_potvrda import potvrdjeni_ids as _potvrdjeni_ids

logger = logging.getLogger("vindex.morning_briefing")
router = APIRouter(tags=["morning-briefing"])


@llm_retry
def _pozovi_briefing_sync_api(client, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return client.chat.completions.create(**kwargs)


@llm_retry
async def _pozovi_briefing_async_api(client, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return await client.chat.completions.create(**kwargs)

_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
_SMTP_PASS = os.getenv("EMAIL_SMTP_PASS", "")
_FROM_ADDR = os.getenv("EMAIL_FROM", "") or _SMTP_USER

_MESECI_SR = {
    "January": "januara", "February": "februara", "March": "marta",
    "April": "aprila", "May": "maja", "June": "juna",
    "July": "jula", "August": "avgusta", "September": "septembra",
    "October": "oktobra", "November": "novembra", "December": "decembra",
}
_DANI_SR = {
    "Monday": "Ponedeljak", "Tuesday": "Utorak", "Wednesday": "Sreda",
    "Thursday": "Četvrtak", "Friday": "Petak", "Saturday": "Subota", "Sunday": "Nedelja",
}


def _danas_sr(d: date) -> str:
    s = d.strftime("%A, %d. %B %Y.")
    for en, sr in {**_DANI_SR, **_MESECI_SR}.items():
        s = s.replace(en, sr)
    return s


# ─── Generisanje briefinga ─────────────────────────────────────────────────────

async def _generiši_briefing(uid: str, supa) -> dict:
    """
    Generiše kompletan personalizovani jutarnji briefing za advokata.
    Paralelno dohvata sve podatke, zatim AI sintetiše.
    """
    danas   = date.today()
    za_7    = danas + timedelta(days=7)
    # BLACKSWAN-CRIT-002 fix (Operation Black Swan, Mission 001, Scenario 15): this
    # briefing only ever queried `.gte(danas)` -- a lawyer returning after any absence
    # (30 days is this mission's own named scenario) got a briefing that silently omits
    # every deadline that passed while they were away, identical to those deadlines never
    # having existed. Bounded to 90 days back (not unbounded) so a genuinely ancient,
    # long-resolved rociste doesn't clutter every future briefing forever.
    pre_90 = danas - timedelta(days=90)

    # B-U-001 (2026-08-21): `return_exceptions=True` je OBAVEZAN deo ugovora ovog
    # `gather`-a, ne kozmetika. Bez njega pad JEDNOG izvora rusi ceo brifing u
    # HTTP 500 -- sto je i bio dokazani produkcioni kvar. Ali izolacija sama po
    # sebi nije dovoljna: rezultat palog izvora NE SME da izgleda kao dokazano
    # prazno stanje, pa svaki izvor nosi svoju zastavicu dostupnosti (v. `_izvor`).
    predmeti_r, rokovi_r, rocista_r, rokovi_propusteni_r, rocista_propustena_r = await asyncio.gather(
        asyncio.to_thread(
            # B-U-001: `stranka` i `protivnik` NE POSTOJE u produkcionoj semi
            # (sondirano direktno nad bazom: 42703 za obe, kao i za `stranke`,
            # `klijent`, `klijent_id`). Kanonski nosioci identiteta strana su
            # `tuzilac`/`tuzeni` -- jedine „party" kolone koje kanonski write
            # path `PATCH /api/predmeti` prihvata i sanitizuje (api.py:4358).
            # Pogresna imena su ovde stajala od uvodjenja brifinga (c86f525e,
            # 2026-06-28), pa `/api/briefing/daily` nikada nije radio na
            # produkciji; nijedan test to nije uhvatio jer svi mock-uju Supabase.
            lambda: supa.table("predmeti")
                .select("id, naziv, status, tuzilac, tuzeni, updated_at")
                .eq("user_id", uid)
                .in_("status", ["aktivan", "u_toku", "pending"])
                .order("updated_at", desc=True)
                .limit(20)
                .execute()
        ),
        # BETA-DEADLINE-DOMAIN-001: `rokovi` je tabela bez ijednog pisca i bez
        # postojanja u produkciji. Kanonski izvor je `predmet_hronologija`.
        _rokovi_domen.rokovi_za_korisnika(supa, uid, od=danas, do=za_7, limit=100),
        asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, vreme, predmet_id, status")
                .eq("user_id", uid)
                .gte("datum", danas.isoformat())
                .lte("datum", za_7.isoformat())
                .order("datum")
                .execute()
        ),
        # Propusteni rokovi (BLACKSWAN-CRIT-002 putanja) -- isti kanonski izvor.
        _rokovi_domen.rokovi_za_korisnika(
            supa, uid, od=pre_90, do=danas - timedelta(days=1), limit=20),
        asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, vreme, predmet_id, status")
                .eq("user_id", uid)
                .eq("status", "zakazano")
                .gte("datum", pre_90.isoformat())
                .lt("datum", danas.isoformat())
                .order("datum", desc=True)
                .limit(20)
                .execute()
        ),
        return_exceptions=True,
    )

    def _izvor(rez, ime: str) -> tuple[list, bool]:
        """FAILED != EMPTY. Vraca (redovi, dostupno).

        `dostupno=False` znaci da upit NIJE izvrsen do kraja -- praznina koju
        vraca tada NIJE dokaz da podataka nema, i nijedna recenica brifinga ne
        sme da je tako protumaci.
        """
        if isinstance(rez, BaseException):
            logger.warning("[MORNING_BRIEFING] izvor %s nije procitan (%s: %s)",
                           ime, type(rez).__name__, rez)
            return [], False
        return (rez.data or []), True

    def _izvor_rokova(rez, ime: str) -> tuple[list, bool]:
        """Domen rokova je vec fail-closed (`.uspeh`); ovde se dodatno hvata i
        slucaj da sam poziv domena baci, posto `gather` sada vraca izuzetke."""
        if isinstance(rez, BaseException):
            logger.warning("[MORNING_BRIEFING] izvor %s nije procitan (%s: %s)",
                           ime, type(rez).__name__, rez)
            return [], False
        if not rez.uspeh:
            return [], False
        return [r.kao_dict() for r in rez.rokovi], True

    predmeti, predmeti_dostupni = _izvor(predmeti_r, "predmeti")
    rocista, _rocista_ok = _izvor(rocista_r, "rocista")
    rocista_propustena, _rocista_prop_ok = _izvor(rocista_propustena_r, "rocista_propustena")

    # Neuspeh citanja rokova NE postaje prazan brifing. `_generisi_briefing`
    # nema try oko `gather`-a, pa bi ranije 500 srusio ceo brifing; sada se
    # razlika prenosi kao stanje i brifing to izricito kaze.
    rokovi, _rokovi_ok = _izvor_rokova(rokovi_r, "rokovi")
    rokovi_propusteni, _rokovi_prop_ok = _izvor_rokova(rokovi_propusteni_r, "rokovi_propusteni")
    rokovi_dostupni = _rokovi_ok and _rokovi_prop_ok
    # Ista logika kao kod rokova: brifing cita rocista DVAPUT (predstojeca +
    # propustena). Pad bilo kog citanja znaci da odsustvo rocista nije dokazano.
    rocista_dostupna = _rocista_ok and _rocista_prop_ok

    def _dani_do(datum_str: str) -> int:
        try:
            return (date.fromisoformat(str(datum_str)[:10]) - danas).days
        except Exception:
            return 999

    # INV: brifing je izvrsiv izlaz. Nepotvrdjen rok se ne prikazuje kao obaveza,
    # bez obzira na `vaznost` i na to ko ga je proizveo. Isti gejt kao email/SMS.
    _potv = _potvrdjeni_ids([r.get("id") for r in rokovi] +
                            [r.get("id") for r in rokovi_propusteni])
    rokovi            = _filtriraj_izvrsive(rokovi, _potv)
    rokovi_propusteni = _filtriraj_izvrsive(rokovi_propusteni, _potv)

    rokovi_hitni    = [r for r in rokovi if _dani_do(r["datum"]) <= 2]
    rokovi_uskoro   = [r for r in rokovi if 2 < _dani_do(r["datum"]) <= 7]
    rocista_danas   = [r for r in rocista if str(r.get("datum", ""))[:10] == danas.isoformat()]
    rocista_sedmica = [r for r in rocista if str(r.get("datum", ""))[:10] != danas.isoformat()]

    # Program Tau, Master Sprint 003 (2026-08-06): initialized here (not
    # inside `if predmeti:` below) so it's always defined even for a
    # zero-case user -- an honest empty list, not a NameError or a GPT guess
    # filling the gap.
    _kanonske_akcije = []
    # B-U-001: prazna lista akcija je dokaz odsustva SAMO ako je svaki kontekst
    # predmeta stvarno izgradjen. Pocinje kao `predmeti_dostupni`: ako lista
    # predmeta nije procitana, ni akcije nisu.
    _akcije_dostupne = predmeti_dostupni

    # ── AI kontekst ────────────────────────────────────────────────────────────
    parts = []
    # BLACKSWAN-CRIT-002: surfaced FIRST, most urgent -- a lawyer returning after any
    # absence needs to see what was missed before anything upcoming.
    if rokovi_propusteni or rocista_propustena:
        propusteno_linije = (
            [f"- Rok: {r.get('naziv','Rok')} — bio je {r['datum']}" for r in rokovi_propusteni] +
            [f"- Ročište u {r.get('sud','N/A')} — bilo je {r.get('datum','')}" for r in rocista_propustena]
        )
        parts.append(
            f"⚠ PROPUŠTENI ROKOVI/ROČIŠTA ({len(propusteno_linije)}):\n" + "\n".join(propusteno_linije)
        )
    if rocista_danas:
        parts.append(
            f"ROČIŠTA DANAS ({len(rocista_danas)}):\n" +
            "\n".join(
                f"- Ročište u {r.get('sud','N/A')} — {r.get('datum','')} {(r.get('vreme') or '')[:5]}"
                for r in rocista_danas
            )
        )
    if rokovi_hitni:
        parts.append(
            f"HITNI ROKOVI (ističu za 0-2 dana) ({len(rokovi_hitni)}):\n" +
            "\n".join(f"- {r.get('naziv','Rok')} — {r['datum']}" for r in rokovi_hitni)
        )
    if rokovi_uskoro:
        parts.append(
            f"ROKOVI OVE NEDELJE ({len(rokovi_uskoro)}):\n" +
            "\n".join(f"- {r.get('naziv','Rok')} — {r['datum']}" for r in rokovi_uskoro)
        )
    if not rokovi_dostupni:
        # BETA-DEADLINE-DOMAIN-001: bez ovoga model dobija odsustvo rokova kao
        # cinjenicu i napise „miran dan" advokatu koji ima rok sutra.
        parts.append(
            "ROKOVI: NEPOZNATO — rokovi nisu pročitani iz baze. NE tvrdi da "
            "rokova nema, NE nazivaj dan mirnim, i izričito upozori advokata "
            "da proveri rokove ručno."
        )
    if not rocista_dostupna:
        # B-U-001: ista invarijanta kao za rokove. Rociste je vremenski
        # najkriticnija stavka u brifingu -- odsustvo iz palog upita ne sme
        # da postane tvrdnja da rocista nema.
        parts.append(
            "ROČIŠTA: NEPOZNATO — ročišta nisu pročitana iz baze. NE tvrdi da "
            "ročišta nema, NE nazivaj dan mirnim, i izričito upozori advokata "
            "da proveri ročišta ručno."
        )
    if not predmeti_dostupni:
        parts.append(
            "PREDMETI: NEPOZNATO — lista predmeta nije pročitana iz baze. NE "
            "tvrdi da predmeta ni otvorenih akcija nema."
        )

    if predmeti:
        # Program Tau, Master Sprint 002 (2026-08-06): CONTEXT_BUILDER_REGISTRY.md
        # found this function had ZERO access to case_dna/predmet_dokumenti/
        # predmet_dokazi/case_actions -- the daily briefing's GPT call named
        # cases with no readiness/open-action signal at all. Enriched here via
        # build_case_context(..., include_documents=False) -- the lightweight
        # mode, since this loops over multiple cases and document text isn't
        # needed for a status line (Phase 6's own cost-control mandate).
        # Bounded to the same 10 cases already displayed below, not all 20
        # fetched, to keep the added query cost proportionate.
        #
        # NOTE (scope boundary, see docs/tau/AI_ENTRY_POINT_MIGRATION_REPORT.md):
        # this closes the CONTEXT gap only. Whether GPT should still be the one
        # authoring "Danas zahteva pažnju" at all is a decision-boundary
        # question (TAU-003, Program Tau Master Sprint 001's own debt
        # register), deliberately out of THIS sprint's scope.
        _prikazani = predmeti[:10]
        _readiness_rezultati = await asyncio.gather(
            *[build_case_context(p["id"], uid, supa, include_documents=False) for p in _prikazani],
            return_exceptions=True,
        )
        _readiness_by_id = {}
        for _p, _r in zip(_prikazani, _readiness_rezultati):
            if isinstance(_r, Exception) or _r.get("error"):
                # B-U-001: pad izgradnje konteksta je do sada nestajao bez traga,
                # a „Nema otvorenih akcija" se izvodi iz PRAZNE liste akcija --
                # dakle pao upit je davao tvrdnju o odsustvu obaveza.
                # OGRANICENJE (otvoren rizik, v. izvestaj): ovo hvata samo pad
                # CELOG `build_case_context`. Pad pojedinacnog upita UNUTAR
                # njega `shared/case_context.py::_safe` i dalje pretvara u `[]`
                # bez signala; to je zaseban modul i van opsega B-U-001.
                _akcije_dostupne = False
                continue
            _readiness_by_id[_p["id"]] = _r.get("readiness", {}).get("value", {})
            _open_actions = ((_r.get("active_actions") or {}).get("value")) or []
            _top = top_open_action(_open_actions)
            if _top:
                _kanonske_akcije.append({
                    "predmet_naziv": _p.get("naziv", "Predmet"),
                    "razlog": _top.get("razlog") or "",
                    "prioritet": _top.get("prioritet"),
                    "rok": _top.get("rok"),
                })

        def _stranke_labela(p: dict) -> str:
            """B-U-001: isti prikaz kao ranije (`stranka: ...`), ali iz kolona
            koje u produkciji STVARNO postoje. Bez izvedenih zakljucaka: ako
            nijedna strana nije uneta, ostaje `N/A` kao i do sada."""
            _tuzilac = (p.get("tuzilac") or "").strip()
            _tuzeni = (p.get("tuzeni") or "").strip()
            if _tuzilac and _tuzeni:
                return f"{_tuzilac} protiv {_tuzeni}"
            return _tuzilac or _tuzeni or "N/A"

        def _linija_predmeta(p: dict) -> str:
            base = f"- {p.get('naziv','Predmet')} | stranka: {_stranke_labela(p)}"
            r = _readiness_by_id.get(p.get("id"))
            if r and r.get("status"):
                base += f" | readiness: {r['status']}"
            return base

        parts.append(
            f"AKTIVNI PREDMETI ({len(predmeti)}):\n" +
            "\n".join(_linija_predmeta(p) for p in _prikazani)
        )

        # Program Tau, Master Sprint 003 (2026-08-06) -- "Canonical AI Decision
        # Boundary". AI_DECISION_SURFACE_MAP.md found "Danas zahteva pažnju"/
        # "Preporuka za danas" were embedded in ONE unparsed GPT free-text
        # completion with zero post-processing -- the readiness annotation
        # Tau 002 added sat in the prompt as decoration, never enforced. This
        # closes TAU-003: rank every case's own top open action by the same
        # canonical order Sigma 005 uses across the whole platform
        # (shared/attention_priority.py), take the top 4 -- GPT is told to
        # PHRASE this exact list below, not decide it (see the narrowed
        # prompt and the structural assembly after the GPT call).
        _kanonske_akcije.sort(key=lambda a: (canonical_sort_key(a.get("prioritet")), a.get("rok") or "9999-99-99"))
    if rocista_sedmica:
        parts.append(
            f"ROČIŠTA OVE NEDELJE ({len(rocista_sedmica)}):\n" +
            "\n".join(
                f"- Ročište ({r.get('sud','N/A')}) — {r.get('datum','')}"
                for r in rocista_sedmica[:5]
            )
        )

    context = "\n\n".join(parts) if parts else "Nema hitnih stavki za danas."

    # Program Tau, Master Sprint 003 (2026-08-06) -- "Canonical AI Decision
    # Boundary", closes TAU-003. AI_DECISION_SURFACE_MAP.md found "Danas
    # zahteva pažnju"/"Ključni rok"/"Preporuka za danas" were entirely
    # GPT-invented, embedded in one unparsed free-text completion with zero
    # post-processing. Built HERE, deterministically, from the same canonical
    # sources every other migrated module in this program reads -- GPT is no
    # longer asked to decide any of this, only to phrase ONE opening
    # sentence. This is a structural fix (GPT's own output literally cannot
    # reach these 3 sections), not a prompt-instruction request GPT could
    # ignore.
    if _kanonske_akcije:
        _danas_zahteva_paznju = "\n".join(
            f"- {a['predmet_naziv']}: {a['razlog']}" + (f" (rok: {a['rok']})" if a.get("rok") else "")
            for a in _kanonske_akcije[:4]
        )
    elif not _akcije_dostupne:
        # B-U-001: prazna lista akcija je izvedena iz liste predmeta I iz
        # konteksta svakog predmeta. Ako bilo koje od to dvoje nije procitano,
        # „nema otvorenih akcija" je tvrdnja bez pokrica -- ista klasa kao
        # DRIFT-002/003 kod rokova.
        _danas_zahteva_paznju = ("Predmeti nisu pročitani iz baze — ne mogu potvrditi "
                                 "da otvorenih akcija nema. Proverite ih ručno.")
    else:
        _danas_zahteva_paznju = "Nema otvorenih akcija u Case Actions ni za jedan predmet."

    _kljucni_rok_kandidat = (rocista_danas[:1] or rokovi_hitni[:1] or rokovi_uskoro[:1] or [None])[0]
    if _kljucni_rok_kandidat and _kljucni_rok_kandidat in rocista_danas:
        _kljucni_rok = f"Ročište danas u {_kljucni_rok_kandidat.get('sud','N/A')} — {_kljucni_rok_kandidat.get('datum','')} {(_kljucni_rok_kandidat.get('vreme') or '')[:5]}. Pripremi se pre polaska."
    elif _kljucni_rok_kandidat:
        _kljucni_rok = f"{_kljucni_rok_kandidat.get('naziv','Rok')} — {_kljucni_rok_kandidat.get('datum','')}. Ne odlaži pripremu."
    elif not (rokovi_dostupni and rocista_dostupna):
        # DRIFT-002/003 (klasa E): ovo polje je ranije izvođeno samo iz praznine
        # liste, pa je pao upit davao tvrdnju o odsustvu rokova — uz istovremeno
        # upozorenje da rokovi nisu dostupni. B-U-001 dodaje ročišta: i
        # `_kljucni_rok_kandidat` se bira iz `rocista_danas`.
        _kljucni_rok = ("Rokovi/ročišta nisu pročitani iz baze — ne mogu potvrditi da ih nema. "
                        "Proverite ih ručno pre nego što planirate dan.")
    else:
        _kljucni_rok = "Nema hitnih rokova u narednih 7 dana."

    _preporuka_za_danas = (
        f"{_kanonske_akcije[0]['predmet_naziv']}: {_kanonske_akcije[0]['razlog']}"
        if _kanonske_akcije else
        "Nema otvorene akcije sa najvišim prioritetom trenutno -- iskoristi vreme za pregled predmeta bez otvorenih obaveza."
    )

    ai_prompt = f"""Ti si lični AI asistent advokata. Danas je {_danas_sr(danas)}.

Na osnovu sledećih podataka iz sistema, napiši JEDNU rečenicu za otvaranje jutarnjeg briefinga --
kakav dan predstoji (mirno/zauzeto/kritično), na osnovu broja i prioriteta stavki ispod.

{context}

NAJVAŽNIJE: ne predlaži akcije, rokove niti preporuke -- to je već određeno od strane sistema i biće
dodato posle tvog odgovora. Tvoj JEDINI zadatak je jedna rečenica tona/uvoda.

Vrati SAMO tu jednu rečenicu, bez markdown formatiranja, bez uvodnih fraza. Ekavica."""

    # CI-RED-003 (2026-08-08): this call had no failure path. GPT contributes
    # exactly ONE opening sentence -- every other section of the briefing
    # (_danas_zahteva_paznju, _kljucni_rok, _preporuka_za_danas, all statistics
    # and the propušteni-rokovi list) is already fully computed above and needs
    # no AI at all. Yet an OpenAI outage, a rate limit surviving @llm_retry's 3
    # attempts, or an expired key propagated straight out of _generiši_briefing
    # and 500'd the entire morning briefing -- the lawyer lost the missed-
    # deadline warning, which is the one part of this screen that is
    # time-critical, because a decorative sentence could not be written.
    #
    # Degrade to a deterministic opening instead. Same rule GPT is being asked
    # to apply, computed from the counts we already have.
    _otvaranje = ""
    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(
            module_name="morning_briefing", operation_name="daily_briefing",
            knowledge_sources=[p.get("id") for p in predmeti],
        ):
            ai_resp = await asyncio.to_thread(
                _pozovi_briefing_sync_api,
                oai,
                model="gpt-4o",
                messages=[{"role": "user", "content": ai_prompt}],
                max_tokens=100,
                temperature=0.4,
            )
        _otvaranje = (ai_resp.choices[0].message.content or "").strip().strip('"')
    except Exception as _ai_exc:
        logger.warning(
            "[MORNING_BRIEFING] AI uvodna rečenica nedostupna (%s) — briefing se isporučuje bez nje.",
            _ai_exc,
        )

    if not _otvaranje:
        _n_propusteno = len(rokovi_propusteni) + len(rocista_propustena)
        if _n_propusteno:
            _otvaranje = f"Imate {_n_propusteno} propušten{'u stavku' if _n_propusteno == 1 else 'ih stavki'} — pregledajte ih pre svega ostalog."
        elif rocista_danas:
            _otvaranje = f"Danas vas čeka {len(rocista_danas)} ročište — dan je zauzet."
        elif rokovi_hitni:
            _otvaranje = f"Nema ročišta danas, ali {len(rokovi_hitni)} rok(ova) ističe uskoro."
        elif not (rokovi_dostupni and rocista_dostupna and _akcije_dostupne):
            # B-U-001: „miran dan" sme da se izgovori samo ako su SVI izvori
            # koji bi ga mogli opovrgnuti stvarno pročitani.
            _nedostupni = ", ".join(_ime for _ime, _ok in (
                ("rokovi", rokovi_dostupni), ("ročišta", rocista_dostupna),
                ("predmeti", _akcije_dostupne)) if not _ok)
            _otvaranje = (f"⚠ Sledeći izvori trenutno nisu dostupni: {_nedostupni} — njihovo "
                          "odsustvo u ovom brifingu NE znači da obaveza nema. Proverite ih ručno.")
        else:
            _otvaranje = "Nema hitnih obaveza za danas — miran dan."

    ai_tekst = f"""**Dobro jutro.** {_otvaranje}

**Danas zahteva pažnju:**
{_danas_zahteva_paznju}

**Ključni rok:**
{_kljucni_rok}

**Preporuka za danas:**
{_preporuka_za_danas}"""

    # Mission Ledger (2026-08-03) — Audit Link Completion: trajan audit trag,
    # correlation_id automatski nasleđen iz current request context (isti id
    # kao AI Provenance red za ovaj poziv, v. case_context iznad).
    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(action="briefing_generisan", user_id=uid, resource_type="briefing"))

    return {
        "datum": danas.isoformat(),
        "ai_briefing": ai_tekst,
        # Prazna lista rokova je istina SAMO kad je ovo `True`.
        "rokovi_dostupni": rokovi_dostupni,
        # B-U-001: isto pravilo za preostala dva izvora. Aditivna polja --
        # postojeci potrosaci koji ih ne citaju rade nepromenjeno.
        # `statistike.rocista_*` i `statistike.aktivnih_predmeta` su dokaz
        # odsustva SAMO kad je odgovarajuca zastavica `True`.
        "rocista_dostupna": rocista_dostupna,
        "predmeti_dostupni": predmeti_dostupni,
        # `False` znaci da „Nema otvorenih akcija" NIJE dokazano. Pokriva pad
        # liste predmeta i pad izgradnje konteksta; NE pokriva tih pad
        # pojedinacnog upita unutar `shared/case_context.py` (otvoren rizik).
        "akcije_dostupne": _akcije_dostupne,
        "statistike": {
            "aktivnih_predmeta":  len(predmeti),
            "rokova_ove_nedelje": len(rokovi),
            "rokova_hitnih":      len(rokovi_hitni),
            "rocista_danas":      len(rocista_danas),
            "rocista_sedmica":    len(rocista_sedmica),
            # BLACKSWAN-CRIT-002: propušteni (missed, last 90 days) -- previously not
            # queried at all, silently invisible to a lawyer returning after an absence.
            "rokova_propustenih":  len(rokovi_propusteni),
            "rocista_propustenih": len(rocista_propustena),
        },
        "rokovi_hitni":  [{"naziv": r.get("naziv"), "datum": r["datum"]} for r in rokovi_hitni],
        "rokovi_propusteni": [{"naziv": r.get("naziv"), "datum": r["datum"]} for r in rokovi_propusteni],
        "rocista_danas": [
            {"naziv": f"Ročište - {r.get('sud','')}", "vreme": f"{r.get('datum','')} {(r.get('vreme') or '')[:5]}", "sud": r.get("sud")}
            for r in rocista_danas
        ],
        "rocista_propustena": [
            {"naziv": f"Ročište - {r.get('sud','')}", "datum": r.get("datum"), "sud": r.get("sud")}
            for r in rocista_propustena
        ],
        "generisano_u": datetime.now(timezone.utc).isoformat(),
    }


# ─── Email ─────────────────────────────────────────────────────────────────────

def _briefing_email_html(briefing: dict, ime: str = "Advokate") -> str:
    datum_prikaz = briefing.get("datum", "")
    ai_tekst     = briefing.get("ai_briefing", "")
    stat         = briefing.get("statistike", {})

    ai_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ai_tekst)
    ai_html = ai_html.replace("\n", "<br>")

    rokovi_hitni = briefing.get("rokovi_hitni", [])
    rocista_d    = briefing.get("rocista_danas", [])

    rokovi_html = ""
    if rokovi_hitni:
        items = "".join(
            f'<li style="color:#ef4444;margin:4px 0;"><strong>{r["naziv"]}</strong> — {r["datum"]}</li>'
            for r in rokovi_hitni
        )
        rokovi_html = (
            '<div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);'
            'border-radius:8px;padding:12px 16px;margin:16px 0;">'
            '<strong style="color:#ef4444;">⚠️ Hitni rokovi</strong>'
            f'<ul style="margin:8px 0 0;padding-left:20px;">{items}</ul></div>'
        )

    rocista_html = ""
    if rocista_d:
        items = "".join(
            f'<li style="color:#00d4ff;margin:4px 0;"><strong>{r["naziv"]}</strong>'
            f' u {r["vreme"][-5:] if len(r.get("vreme",""))>=5 else r.get("vreme","")}</li>'
            for r in rocista_d
        )
        rocista_html = (
            '<div style="background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.2);'
            'border-radius:8px;padding:12px 16px;margin:16px 0;">'
            '<strong style="color:#00d4ff;">⚖️ Ročišta danas</strong>'
            f'<ul style="margin:8px 0 0;padding-left:20px;">{items}</ul></div>'
        )

    hitni_color = "#ef4444" if stat.get("rokova_hitnih", 0) > 0 else "#22c55e"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#060e1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:600px;margin:24px auto;background:#0a1628;border:1px solid #1e3a5f;border-radius:16px;overflow:hidden;">

  <div style="background:linear-gradient(135deg,#0f2035,#0a1628);padding:28px 32px;border-bottom:1px solid #1e3a5f;">
    <div style="display:flex;align-items:center;gap:12px;">
      <div style="font-size:28px;">⚖️</div>
      <div>
        <div style="font-size:20px;font-weight:800;color:#fff;">Vindex AI</div>
        <div style="font-size:13px;color:#64748b;">Jutarnji izveštaj · {datum_prikaz}</div>
      </div>
    </div>
  </div>

  <div style="display:flex;background:#0d1e2e;padding:16px 32px;gap:24px;border-bottom:1px solid #1e293b;">
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:#00d4ff;">{stat.get('aktivnih_predmeta',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Aktivnih predmeta</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:{hitni_color};">{stat.get('rokova_hitnih',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Hitnih rokova</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:#f59e0b;">{stat.get('rocista_danas',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Ročišta danas</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:#a78bfa;">{stat.get('rokova_ove_nedelje',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Rokova ove nedelje</div>
    </div>
  </div>

  <div style="padding:28px 32px;">
    {rokovi_html}
    {rocista_html}
    <div style="background:#0d1e2e;border:1px solid #1e293b;border-radius:10px;padding:20px 24px;margin:16px 0;">
      <div style="font-size:12px;color:#00d4ff;font-weight:700;letter-spacing:0.08em;margin-bottom:12px;">✦ AI ANALIZA</div>
      <div style="font-size:14px;color:#e2e8f0;line-height:1.7;">{ai_html}</div>
    </div>
  </div>

  <div style="padding:20px 32px;border-top:1px solid #1e293b;text-align:center;">
    <a href="https://vindex-ai.onrender.com/app"
       style="display:inline-block;background:#00d4ff;color:#000;font-weight:700;font-size:14px;
              padding:12px 28px;border-radius:10px;text-decoration:none;">
      Otvori Vindex →
    </a>
    <div style="margin-top:12px;font-size:11px;color:#374151;">
      Vindex AI · Automatski jutarnji izveštaj
    </div>
  </div>

</div>
</body></html>"""


def _smtp_send(msg: MIMEMultipart, to_email: str) -> None:
    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(_SMTP_USER, _SMTP_PASS)
        smtp.sendmail(_FROM_ADDR, [to_email], msg.as_bytes())


async def _pošalji_briefing_email(to_email: str, briefing: dict, ime: str = "") -> bool:
    if not _SMTP_HOST or not to_email:
        return False

    html  = _briefing_email_html(briefing, ime)
    datum = briefing.get("datum", "")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Vindex jutarnji izveštaj — {datum}"
        msg["From"]    = f"Vindex AI <{_FROM_ADDR}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html", "utf-8"))
        await asyncio.to_thread(_smtp_send, msg, to_email)
        return True
    except Exception as e:
        logger.error("Briefing email greška za %s: %s", to_email, e)
        return False


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/briefing/daily")
@limiter.limit("10/minute")
async def get_daily_briefing(
    request: Request,
    user: dict = Depends(PermissionService.require("morning_briefing")),
):
    """Generiši i vrati personalizovani jutarnji briefing (on-demand)."""
    uid  = user["user_id"]
    supa = _get_supa()

    briefing = await _generiši_briefing(uid, supa)

    await UsageService.consume(uid, user.get("email", ""), "morning_briefing")

    try:
        await asyncio.to_thread(
            lambda: supa.table("briefing_istorija").insert({
                "user_id":     uid,
                "datum":       briefing["datum"],
                "ai_briefing": briefing["ai_briefing"],
                "statistike":  briefing["statistike"],
            }).execute()
        )
    except Exception:
        pass

    return briefing


@router.post("/api/briefing/send-email")
@limiter.limit("3/hour")
async def send_briefing_email(
    request: Request,
    user: dict = Depends(PermissionService.require("morning_briefing")),
):
    """Pošalji briefing emailom na adresu korisnika."""
    uid        = user["user_id"]
    user_email = user.get("email", "")

    if not user_email:
        raise HTTPException(status_code=400, detail="Email adresa nije podešena na nalogu.")

    supa     = _get_supa()
    briefing = await _generiši_briefing(uid, supa)
    sent     = await _pošalji_briefing_email(user_email, briefing)

    await UsageService.consume(uid, user_email, "morning_briefing")

    return {"ok": sent, "email": user_email, "datum": briefing["datum"]}


@router.post("/api/briefing/cron")
async def briefing_cron(request: Request):
    """
    Poziva se iz eksternog cron servisa svako jutro u 8:00 (Beograd = 06:00 UTC).
    Zaštićen BRIEFING_CRON_SECRET header-om.

    Podešavanje (cron-job.org ili Render Cron):
      URL:      POST https://vindex-ai.onrender.com/api/briefing/cron
      Header:   X-Cron-Secret: {BRIEFING_CRON_SECRET}
      Schedule: 0 6 * * 1-5   (radni dani)
    """
    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret    = request.headers.get("X-Cron-Secret", "")

    # Fail CLOSED: ako promenljiva nije podešena na serveru, endpoint mora
    # ostati zaključan (ne "otvoren za sve") — ranije bi prazan cron_secret
    # tiho preskočio proveru.
    if not cron_secret or x_secret != cron_secret:
        raise HTTPException(status_code=403, detail="Neovlašćen pristup.")

    supa = _get_supa()

    try:
        korisnici_r = await asyncio.to_thread(
            lambda: supa.table("profiles")
                .select("id, email")
                .not_.is_("email", "null")
                .limit(500)
                .execute()
        )
        korisnici = korisnici_r.data or []
    except Exception as e:
        logger.error("Cron: greška pri dohvatanju korisnika: %s", e)
        return {"ok": False, "error": str(e)}

    poslato = 0
    greske  = 0

    # LAMBDA008-PERF-003 fix: was a strictly sequential for-loop (up to 500 users,
    # each 1 GPT call + SMTP send + an explicit 0.5s sleep) invoked directly by the
    # external cron caller with NO internal timeout wrapper at all -- unlike
    # workers/background_agents.py's own asyncio.wait_for(600s) cap, a stall here had
    # no guardrail. Bounded concurrency (same idiom as that module's own fix) plus an
    # outer timeout so a slow run degrades to "processed what it could in the window"
    # instead of an unbounded-duration cron call.
    _briefing_sem = asyncio.Semaphore(int(os.getenv("BRIEFING_CRON_CONCURRENCY", "5")))
    _counts = {"poslato": 0, "greske": 0}

    async def _process_one(k: dict) -> None:
        uid   = k.get("id")
        email = k.get("email", "")
        ime   = k.get("ime") or k.get("email", "").split("@")[0] or "Advokate"
        if not uid or not email:
            return
        async with _briefing_sem:
            try:
                briefing = await _generiši_briefing(uid, supa)
                sent     = await _pošalji_briefing_email(email, briefing, ime)
                if sent:
                    _counts["poslato"] += 1
                else:
                    _counts["greske"] += 1
            except Exception as e:
                logger.error("Cron briefing greška za %s: %s", email, e)
                _counts["greske"] += 1

    try:
        await asyncio.wait_for(
            asyncio.gather(*(_process_one(k) for k in korisnici), return_exceptions=True),
            timeout=540,
        )
    except asyncio.TimeoutError:
        logger.error("Briefing cron: dostignut 540s limit, obrada prekinuta sa nekim korisnicima neobrađenim.")

    poslato, greske = _counts["poslato"], _counts["greske"]
    logger.info("Briefing cron završen: %d poslato, %d grešaka", poslato, greske)
    return {"ok": True, "poslato": poslato, "greske": greske, "ukupno": len(korisnici)}


@router.get("/api/briefing/history")
async def get_briefing_history(
    user: dict = Depends(get_current_user),
    limit: int = 7,
):
    """Prethodnih N dana briefinga (max 30)."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("briefing_istorija")
                .select("datum, ai_briefing, statistike, created_at")
                .eq("user_id", uid)
                .order("datum", desc=True)
                .limit(min(limit, 30))
                .execute()
        )
        return {"history": r.data or []}
    except Exception:
        return {"history": []}


# ─── Nightly Intelligence Run ──────────────────────────────────────────────────

async def _generiši_alerts_za_korisnika(uid: str, supa) -> list[dict]:
    """
    Skenira predmete, rokove i ročišta za korisnika i generiše listu proactive alertova.
    """
    danas   = date.today()
    za_3    = (danas + timedelta(days=3)).isoformat()
    za_7    = (danas + timedelta(days=7)).isoformat()
    za_48h  = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    pre_30  = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    alerts: list[dict] = []

    try:
        predmeti_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id, naziv, updated_at")
                .eq("user_id", uid)
                .in_("status", ["aktivan", "u_toku", "pending"])
                .execute()
        )
        predmeti = predmeti_r.data or []
    except Exception:
        return []

    predmeti_map = {p["id"]: p for p in predmeti}
    pred_ids = list(predmeti_map.keys())
    if not pred_ids:
        return []

    # Rokovi koji ističu za <= 3 dana (hitni)
    try:
        rok_r = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, predmet_id")
                .in_("predmet_id", pred_ids[:30])
                .gte("datum", danas.isoformat())
                .lte("datum", za_3)
                .execute()
        )
        for r in (rok_r.data or []):
            p = predmeti_map.get(r.get("predmet_id", ""), {})
            alerts.append({
                "tip":        "rok_kritican",
                "naslov":     f"Hitno rociste — {r.get('sud', 'Rociste')}",
                "opis":       f"Rociste {r.get('datum', '')[:10]} · Predmet: {p.get('naziv', '')}",
                "urgentnost": "hitna",
                "predmet_id": r.get("predmet_id"),
            })
    except Exception as e:
        logger.debug("[NIGHTLY] rokovi_hitni greška: %s", e)

    # Rokovi 4-7 dana (visoka urgentnost)
    try:
        rok_r2 = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, predmet_id")
                .in_("predmet_id", pred_ids[:30])
                .gt("datum", za_3)
                .lte("datum", za_7)
                .execute()
        )
        for r in (rok_r2.data or []):
            p = predmeti_map.get(r.get("predmet_id", ""), {})
            alerts.append({
                "tip":        "rok_uskoro",
                "naslov":     f"Rociste uskoro — {r.get('sud', 'Rociste')}",
                "opis":       f"Rociste {r.get('datum', '')[:10]} · Predmet: {p.get('naziv', '')}",
                "urgentnost": "visoka",
                "predmet_id": r.get("predmet_id"),
            })
    except Exception as e:
        logger.debug("[NIGHTLY] rokovi_uskoro greška: %s", e)

    # Ročišta u narednih 48h
    try:
        roc_r = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, datum, sud, predmet_id")
                .eq("user_id", uid)
                .gte("datum", danas.isoformat())
                .lte("datum", za_48h[:10])
                .execute()
        )
        for r in (roc_r.data or []):
            p = predmeti_map.get(r.get("predmet_id", ""), {})
            alerts.append({
                "tip":        "rociste_sutra",
                "naslov":     f"Ročište — {r.get('sud', 'Sud')}",
                "opis":       f"Zakazano {r.get('datum', '')[:10]} · Predmet: {p.get('naziv', '')}",
                "urgentnost": "hitna",
                "predmet_id": r.get("predmet_id"),
            })
    except Exception as e:
        logger.debug("[NIGHTLY] rocista greška: %s", e)

    # Predmeti neaktivni 30+ dana
    try:
        for p in predmeti:
            upd = p.get("updated_at") or ""
            if upd and upd < pre_30:
                alerts.append({
                    "tip":        "predmet_neaktivan",
                    "naslov":     f"Neaktivan predmet — {p.get('naziv', '')}",
                    "opis":       "Predmet nije ažuriran više od 30 dana.",
                    "urgentnost": "normalna",
                    "predmet_id": p.get("id"),
                })
    except Exception as e:
        logger.debug("[NIGHTLY] neaktivni greška: %s", e)

    return alerts


async def _ai_prioritizacija_alertova(alerts: list[dict], ime: str) -> str:
    """GPT-4o-mini: kratka prioritizovana lista najvažnijih alertova."""
    if not alerts:
        return ""
    hitni   = [a for a in alerts if a["urgentnost"] == "hitna"]
    visoki  = [a for a in alerts if a["urgentnost"] == "visoka"]
    linije  = []
    for a in (hitni + visoki)[:8]:
        linije.append(f"- [{a['urgentnost'].upper()}] {a['naslov']}: {a['opis']}")
    if not linije:
        return ""

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    try:
        resp = await asyncio.to_thread(
            _pozovi_briefing_sync_api,
            oai,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                f"Ti si AI asistent advokata {ime}. Na osnovu sledecih upozorenja "
                f"napiši kratku prioritizovanu preporuku (max 150 reči, ekavica):\n\n"
                + "\n".join(linije)
            )}],
            max_tokens=250,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[NIGHTLY] AI prioritizacija greška: %s", e)
        return "\n".join(linije[:3])


def _nightly_email_html(alerts: list[dict], ai_tekst: str, ime: str) -> str:
    hitni_count = sum(1 for a in alerts if a["urgentnost"] == "hitna")
    alert_html = "".join(
        f'<div style="padding:8px 0;border-bottom:1px solid #1e293b;">'
        f'<span style="color:{"#ef4444" if a["urgentnost"]=="hitna" else "#f59e0b" if a["urgentnost"]=="visoka" else "#64748b"};font-weight:700;">'
        f'[{a["urgentnost"].upper()}]</span> '
        f'<strong style="color:#e2e8f0;">{a["naslov"]}</strong>'
        f'<div style="color:#94a3b8;font-size:12px;">{a["opis"]}</div>'
        f'</div>'
        for a in alerts[:10]
    )
    ai_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ai_tekst or "").replace("\n", "<br>")
    return f"""<!DOCTYPE html><html><body style="background:#060e1a;font-family:sans-serif;">
<div style="max-width:600px;margin:24px auto;background:#0a1628;border:1px solid #1e3a5f;border-radius:16px;overflow:hidden;">
  <div style="padding:24px 32px;border-bottom:1px solid #1e3a5f;">
    <div style="font-size:18px;font-weight:800;color:#fff;">⚡ Vindex — Noćni izveštaj</div>
    <div style="color:#64748b;font-size:13px;">Automatska analiza · {date.today().isoformat()}</div>
  </div>
  <div style="padding:20px 32px;">
    <div style="background:rgba(239,68,68,0.1);border-radius:8px;padding:12px 16px;margin-bottom:16px;">
      <strong style="color:#ef4444;">Hitnih upozorenja: {hitni_count}</strong> · Ukupno: {len(alerts)}
    </div>
    {alert_html}
    {"<div style='margin-top:16px;padding:16px;background:#0d1e2e;border-radius:8px;color:#e2e8f0;font-size:14px;line-height:1.6;'>" + ai_html + "</div>" if ai_html else ""}
  </div>
  <div style="padding:16px 32px;border-top:1px solid #1e293b;text-align:center;">
    <a href="https://vindex-ai.onrender.com/app" style="background:#00d4ff;color:#000;font-weight:700;padding:10px 24px;border-radius:8px;text-decoration:none;">Otvori Vindex →</a>
  </div>
</div></body></html>"""


@router.post("/api/briefing/nightly-intelligence")
async def nightly_intelligence_run(request: Request):
    """
    Nightly Intelligence Run — 02:00 Beograd (00:00 UTC).
    Skenira sve predmete, kreira proactive alerts, šalje email svakom korisniku koji ima hitna upozorenja.

    Podešavanje cron-job.org:
      URL:      POST https://vindex-ai.onrender.com/api/briefing/nightly-intelligence
      Header:   X-Cron-Secret: {BRIEFING_CRON_SECRET}
      Schedule: 0 0 * * *   (svake noći u ponoć UTC = 02:00 Beograd)
    """
    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret    = request.headers.get("X-Cron-Secret", "")
    # Fail CLOSED: prazan cron_secret vise ne otvara endpoint za sve.
    if not cron_secret or x_secret != cron_secret:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=403, detail="Neovlašćen pristup.")

    supa = _get_supa()

    try:
        korisnici_r = await asyncio.to_thread(
            lambda: supa.table("profiles")
                .select("id, email")
                .not_.is_("email", "null")
                .limit(500)
                .execute()
        )
        korisnici = korisnici_r.data or []
    except Exception as e:
        logger.error("[NIGHTLY] Greška pri dohvatanju korisnika: %s", e)
        return {"ok": False, "error": str(e)}

    ukupno_alertova = 0
    emailova        = 0

    for k in korisnici:
        uid   = k.get("id")
        email = k.get("email", "")
        ime   = k.get("ime") or k.get("email", "").split("@")[0] or "Advokate"
        if not uid:
            continue

        try:
            alerts = await _generiši_alerts_za_korisnika(uid, supa)
            if not alerts:
                continue

            ai_tekst = await _ai_prioritizacija_alertova(alerts, ime)

            # Upiši alerts u bazu -- Project Phoenix's own retry+durable-audit
            # pattern (2026-08-03, this loop's original fix for the "one
            # shared try/except, DEBUG-only log, zero retries" silent-loss
            # bug) is now the canonical shared/proactive_alerts.py behavior
            # itself (Program Alpha, 2026-08-04) -- every proactive_alerts
            # call site gets it, not just this one.
            from shared.proactive_alerts import create_proactive_alert
            for a in alerts:
                if await create_proactive_alert(
                    supa,
                    user_id=uid,
                    predmet_id=a.get("predmet_id"),
                    tip=a["tip"],
                    naslov=a["naslov"],
                    opis=a["opis"],
                    urgentnost=a["urgentnost"],
                ):
                    ukupno_alertova += 1

            # Pošalji email ako ima SMTP
            hitni_alerts = [a for a in alerts if a["urgentnost"] == "hitna"]
            if hitni_alerts and _SMTP_HOST and email:
                try:
                    html = _nightly_email_html(alerts, ai_tekst, ime)
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"Vindex — Noćni izveštaj ({len(hitni_alerts)} hitnih)"
                    msg["From"]    = f"Vindex AI <{_FROM_ADDR}>"
                    msg["To"]      = email
                    msg.attach(MIMEText(html, "html", "utf-8"))
                    await asyncio.to_thread(_smtp_send, msg, email)
                    emailova += 1
                except Exception as e:
                    logger.error("[NIGHTLY] Email greška za %s: %s", email, e)

        except Exception as e:
            logger.error("[NIGHTLY] Greška za korisnika %s: %s", uid, e)

        await asyncio.sleep(0.3)

    logger.info("[NIGHTLY] Završen: %d korisnika, %d alertova, %d emailova",
                len(korisnici), ukupno_alertova, emailova)
    return {"ok": True, "korisnika": len(korisnici), "alertova": ukupno_alertova, "emailova": emailova}


# ─── Proactive Alerts endpoints ───────────────────────────────────────────────

@router.get("/api/briefing/alerts")
@limiter.limit("30/minute")
async def get_proactive_alerts(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dohvata nepročitane proactive alerts za trenutnog korisnika."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .select("id, tip, naslov, opis, urgentnost, predmet_id, created_at")
                .eq("user_id", uid)
                .eq("procitana", False)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
        )
        alerts = r.data or []
    except Exception:
        alerts = []

    hitnih = sum(1 for a in alerts if a.get("urgentnost") == "hitna")
    return {"alerts": alerts, "ukupno": len(alerts), "hitnih": hitnih}


@router.patch("/api/briefing/alerts/{alert_id}/procitana")
async def mark_alert_read(
    alert_id: str,
    user: dict = Depends(get_current_user),
):
    """Označi alert kao pročitan."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .update({"procitana": True})
                .eq("id", alert_id)
                .eq("user_id", uid)
                .execute()
        )
    except Exception as e:
        logger.debug("[ALERTS] Mark read greška: %s", e)

    return {"ok": True}


@router.get("/api/briefing/urgency-stats")
@limiter.limit("30/minute")
async def get_urgency_stats(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Statistika nepročitanih alertova za UI badge."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .select("urgentnost")
                .eq("user_id", uid)
                .eq("procitana", False)
                .execute()
        )
        rows = r.data or []
    except Exception:
        rows = []

    hitnih   = sum(1 for a in rows if a.get("urgentnost") == "hitna")
    visokih  = sum(1 for a in rows if a.get("urgentnost") == "visoka")
    normalnih = sum(1 for a in rows if a.get("urgentnost") == "normalna")

    return {
        "hitnih":             hitnih,
        "visokih":            visokih,
        "normalnih":          normalnih,
        "ukupno_neprocitanih": len(rows),
    }


# ─── Today Focus — Single Pane of Glass ──────────────────────────────────────
# "Šta danas treba da uradim i zašto?"
# Jedan endpoint koji sakriva svu složenost i daje JEDNU akciju.

@router.get("/today-focus")
@limiter.limit("20/minute")
async def today_focus(
    request: Request,
    user: dict = Depends(PermissionService.require("morning_briefing")),
):
    """
    Centralni dnevni fokus — agregira sve u jedan odgovor.
    Advokat otvori app i vidi tačno šta je najvažnije danas.
    GPT poziv se kešira 5 minuta da se ne troši na svaki UI refresh.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    now  = datetime.now(timezone.utc)
    today_iso  = now.date().isoformat()
    in_3d_iso  = (now.date() + timedelta(days=3)).isoformat()
    in_7d_iso  = (now.date() + timedelta(days=7)).isoformat()
    week_ago   = (now - timedelta(days=7)).isoformat()

    # ── Cache: ako je briefing_istorija svežija od 5 min, vrati keširano ──────
    try:
        cached_r = await asyncio.to_thread(
            lambda: supa.table("briefing_istorija")
                .select("ai_briefing,statistike,created_at")
                .eq("user_id", uid)
                .eq("datum", today_iso)
                .limit(1)
                .execute()
        )
        rows = cached_r.data or []
        if rows:
            row = rows[0]
            ts_str = row.get("created_at") or ""
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if (now - ts).total_seconds() < 300:  # 5 minuta
                    cached = row.get("statistike") or {}
                    return {
                        **cached,
                        "ai_poruka":      row.get("ai_briefing", ""),
                        "iz_kesa":        True,
                        "poslednji_refresh": ts_str,
                    }
    except Exception:
        pass

    # ── Korak 1: Aktivni predmeti (za cross-ref) ─────────────────────────────
    pred_map: dict[str, str] = {}
    try:
        pr = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv")
                .eq("user_id", uid)
                .neq("status", "zatvoren")
                .limit(100)
                .execute()
        )
        for p in (pr.data or []):
            pred_map[p["id"]] = p.get("naziv", "")
        aktivnih_predmeta = len(pred_map)
    except Exception:
        aktivnih_predmeta = 0

    # ── Korak 2: Hitni rokovi ≤3 dana ────────────────────────────────────────
    # BETA-DEADLINE-DOMAIN-001. Ovde je bio `except Exception: pass` nad
    # tabelom koja ne postoji -- `/today-focus` je SVAKI put tvrdio da hitnih
    # rokova nema. Kanonski sloj razliku „prazno" / „nisam mogao" nosi u stanju.
    hitni_rokovi: list[dict] = []
    _rez_rokovi = await _rokovi_domen.rokovi_za_korisnika(
        supa, uid, od=date.fromisoformat(today_iso),
        do=date.fromisoformat(in_3d_iso), limit=10)
    rokovi_dostupni = _rez_rokovi.uspeh
    for r in _rez_rokovi.rokovi:
        hitni_rokovi.append({
            "predmet_naziv": pred_map.get(r.predmet_id, ""),
            "rok_naziv":     r.naslov,
            "datum":         r.datum.isoformat(),
            "dana_do":       r.dana_do,
            "urgentnost":    "hitno" if r.dana_do <= 1 else "uskoro",
        })

    # ── Korak 3: Ročišta ove nedelje ─────────────────────────────────────────
    rocista_nedelja: list[dict] = []
    try:
        rocr = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("predmet_id,datum,vreme,sud")
                .eq("user_id", uid)
                .gte("datum", today_iso)
                .lte("datum", in_7d_iso)
                .order("datum")
                .limit(5)
                .execute()
        )
        for r in (rocr.data or []):
            rocista_nedelja.append({
                "predmet_naziv": pred_map.get(r.get("predmet_id", ""), ""),
                "naziv":         r.get("sud", ""),
                "datum":         r.get("datum", ""),
                "sud":           r.get("sud", ""),
            })
    except Exception:
        pass

    # ── Korak 4: Predmeti bez aktivnosti 7+ dana ─────────────────────────────
    zapostavljeni: list[dict] = []
    try:
        zr = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv,tip,updated_at")
                .eq("user_id", uid)
                .neq("status", "zatvoren")
                .lt("updated_at", week_ago)
                .order("updated_at")
                .limit(3)
                .execute()
        )
        for p in (zr.data or []):
            zapostavljeni.append({
                "predmet_id":  p.get("id", ""),
                "naziv":       p.get("naziv", ""),
                "tip":         p.get("tip", ""),
                "poslednja_aktivnost": (p.get("updated_at") or "")[:10],
            })
    except Exception:
        pass

    # ── Korak 5: Lekcije na čekanju (predlog_ai → partner potvrđuje) ─────────
    lekcije_na_cekanju: list[dict] = []
    try:
        lr = await asyncio.to_thread(
            lambda: supa.table("lessons_learned")
                .select("id,lecija,kategorija,vaznost,broj_predmeta")
                .eq("user_id", uid)
                .eq("status_lekcije", "predlog_ai")
                .eq("zastarela", False)
                .order("vaznost", desc=True)
                .limit(3)
                .execute()
        )
        lekcije_na_cekanju = lr.data or []
    except Exception:
        pass

    # ── Korak 6: Neprocitani hitni alertovi ──────────────────────────────────
    hitni_alertovi: list[dict] = []
    try:
        ar = await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .select("id,naslov,opis,urgentnost,created_at")
                .eq("user_id", uid)
                .eq("procitana", False)
                .eq("urgentnost", "hitna")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
        )
        hitni_alertovi = ar.data or []
    except Exception:
        pass

    # ── Korak 7: AI sinteza — JEDNA najvažnija akcija ────────────────────────
    ai_poruka = ""
    try:
        rokovi_txt = "; ".join(
            f"{r['predmet_naziv']} ({r['rok_naziv']}, {r['dana_do']}d)"
            for r in hitni_rokovi[:3]
        ) or ("nema" if rokovi_dostupni else "NEPOZNATO — nisu pročitani iz baze")
        rocista_txt = "; ".join(
            f"{r['predmet_naziv']} {r['datum']} {r['sud']}"
            for r in rocista_nedelja[:3]
        ) or "nema"

        context = (
            f"Advokat ima:\n"
            f"- {len(hitni_rokovi)} hitnih rokova u sledeca 3 dana\n"
            f"- {len(rocista_nedelja)} rocista ove nedelje\n"
            f"- {len(zapostavljeni)} predmeta bez aktivnosti 7+ dana\n"
            f"- {len(lekcije_na_cekanju)} lekcija koje cekaju potvrdu\n"
            f"- {len(hitni_alertovi)} neprocitanih hitnih upozorenja\n\n"
            f"Hitni rokovi: {rokovi_txt}\n"
            f"Rocista: {rocista_txt}"
        )

        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await _pozovi_briefing_async_api(
            oai,
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=120,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si licni AI asistent advokata. Daj mu personalizovanu jutarnju poruku. "
                        "Budi konkretan i direktan. Maksimalno 3 recenice. "
                        "Fokus na NAJKRITIČNIJU stvar danas — izaberi JEDNU najvazniju akciju. "
                        "Ekavica strogo — nikada ijekavica."
                    ),
                },
                {"role": "user", "content": context},
            ],
        )
        ai_poruka = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[TODAY_FOCUS] GPT greška: %s", e)
        if hitni_rokovi:
            r0 = hitni_rokovi[0]
            ai_poruka = (
                f"Prioritet danas: rok '{r0['rok_naziv']}' u predmetu "
                f"'{r0['predmet_naziv']}' istice za {r0['dana_do']} dan(a)."
            )
        elif rocista_nedelja:
            r0 = rocista_nedelja[0]
            ai_poruka = f"Imate rociste u sudu '{r0.get('sud', '')}' dana {r0.get('datum', '')}. Pripremite se."
        elif not rokovi_dostupni:
            ai_poruka = ("Rokovi trenutno nisu dostupni — odsustvo rokova ovde NE "
                         "znaci da ih nema. Proverite ih rucno.")
        else:
            ai_poruka = "Nema hitnih rokova ni rocista. Dobar dan za stratesko planiranje."

    # ── Statistika ────────────────────────────────────────────────────────────
    statistika = {
        "aktivnih_predmeta":   aktivnih_predmeta,
        "rokova_ove_nedelje":  len(hitni_rokovi),
        "rocista_ove_nedelje": len(rocista_nedelja),
        "lekcija_na_cekanju":  len(lekcije_na_cekanju),
        "hitnih_alertova":     len(hitni_alertovi),
    }

    payload = {
        "datum":                today_iso,
        "ai_poruka":            ai_poruka,
        "hitni_rokovi":         hitni_rokovi,
        "rokovi_dostupni":      rokovi_dostupni,
        "rocista_nedelja":      rocista_nedelja,
        "zapostavljeni_predmeti": zapostavljeni,
        "lekcije_na_cekanju":   lekcije_na_cekanju,
        "hitni_alertovi":       hitni_alertovi,
        "statistika":           statistika,
        "iz_kesa":              False,
        "poslednji_refresh":    now.isoformat(),
    }

    # ── Keširanje u briefing_istorija ─────────────────────────────────────────
    try:
        await asyncio.to_thread(
            lambda: supa.table("briefing_istorija").upsert({
                "user_id":    uid,
                "datum":      today_iso,
                "ai_briefing": ai_poruka,
                "statistike": payload,
            }, on_conflict="user_id,datum").execute()
        )
    except Exception as e:
        logger.debug("[TODAY_FOCUS] cache upsert greška: %s", e)

    await UsageService.consume(uid, user.get("email", ""), "morning_briefing")

    return payload
