# -*- coding: utf-8 -*-
"""
GDPR Data Export — korisnik preuzima svoje zapise iz tabela navedenih u README-u.
GET /api/export/complete → ZIP sa JSON fajlovima (bez originalnih fajlova dokumenata).
"""
import io
import json
import logging
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.data_export")
router = APIRouter(prefix="/api/export", tags=["export"])

_README = """VINDEX AI — Export podataka
Datum: {datum}
Korisnik: {email}

Sadržaj:
  predmeti.json       — svi predmeti
  klijenti.json       — svi klijenti
  billing.json        — sve stavke naplate
  dokumenti.json      — metadata dokumenata (bez fajlova); polje tekst_sadrzaj,
                        gde postoji, je izvučeni tekst — nije original
  beleske.json        — beleške uz predmete
  rocista.json        — ročišta
  hronologija.json    — automatski generisana hronologija
  komentari.json      — komentari uz predmete

Napomena: Fajlovi dokumenata (PDF, DOCX...) nisu uključeni u ovaj export.
Za preuzimanje fajlova kontaktirajte: support@vindex.ai

Prava: Imate pravo na prenosivost podataka prema ZZPL čl. 36 i GDPR čl. 20.
"""


class ExportIncomplete(Exception):
    """One or more tables could not be read for a portability export.

    S4-4 (2026-08-09). _fetch swallowed every read error into [], and the
    endpoint shipped the ZIP regardless. So a transient database error meant the
    data subject received an export that was MISSING ENTIRE TABLES, labelled by
    its own README as a complete ZZPL čl. 36 / GDPR čl. 20 portability export.

    An incomplete export presented as complete is worse than no export: the
    recipient has no way to know what is absent, and completeness is the entire
    point of the right being exercised. Fail instead, and name the tables.
    """


#: PostgREST/Supabase `max-rows` (podrazumevano 1000): odgovor bez straničenja
#: se TIHO seče na tu granicu. Strana ne sme biti veća od nje.
_STRANA = 1000


def _kljuc_redosleda(order: str):
    """Redosled u izvozu kao ranije `order(<kolona>)` (rastuće, NULL na kraju),
    sa `id` kao stabilnim razbijačem nerešenog."""
    def k(r):
        v = r.get(order)
        return (v is None, "" if v is None else str(v), str(r.get("id")))
    return k


async def _fetch(supa, table: str, uid: str, order: str = "created_at",
                 errors: list | None = None) -> list:
    """Svi redovi korisnika iz tabele, po stranama.

    C1-F1 (Night Sprint II): jedan upit bez opsega PostgREST seče na `max-rows`
    (1000) bez ikakve greške -- izvoz je bio „uspešan" i nepotpun. Čita se po
    ključu (`id > poslednji`, `order(id)`), ne po offsetu: brisanje reda
    između dve strane ne može da pomeri i preskoči neki drugi red. Petlja se
    prekida tek na PRAZNOJ strani, ne na „kratkoj" -- tako ni niži `max-rows`
    od `_STRANA` ne može tiho da odseče ostatak. Pad bilo koje strane je pad
    cele tabele (izvoz se odbija, `data_export_failed`).
    """
    try:
        out: list = []
        poslednji = None
        while True:
            q = supa.table(table).select("*").eq("user_id", uid)
            if poslednji is not None:
                q = q.gt("id", poslednji)
            strana = q.order("id").limit(_STRANA).execute().data or []
            if not strana:
                break
            novi = strana[-1].get("id")
            if novi is None or novi == poslednji:
                raise RuntimeError("straničenje ne napreduje")
            out.extend(strana)
            poslednji = novi
        out.sort(key=_kljuc_redosleda(order))
        return out
    except Exception as e:
        # Samo klasa izuzetka: tekst greške baze može da nosi vrednost iz reda.
        logger.error("[EXPORT] %s greška (%s) — export je NEPOTPUN", table, type(e).__name__)
        if errors is not None:
            errors.append(table)
        return []


@router.get("/complete")
async def export_complete(user=Depends(get_current_user)):
    """
    Exportuje korisnikove zapise iz 8 tabela navedenih u README-u kao ZIP sa
    JSON fajlovima. Originalni fajlovi dokumenata NISU ukljuceni (README to kaze).
    GDPR čl. 20 — pravo na prenosivost podataka.
    """
    from shared.audit_immutable import log_action as _imm_log
    from shared.bg import spawn as _spawn_bg

    uid  = user["user_id"]
    email = user.get("email", uid)
    now  = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")

    # NS001 — kolona za sortiranje mora postojati na TOJ tabeli, inače
    # PostgREST odbija ceo upit (42703), `_fetch` je upiše u `_failed`, i ZIP se
    # odbacuje. `klijenti` i `predmet_komentari` nemaju `created_at` nego
    # `kreirano` -- mereno sondom `select(<kolona>)&limit=0` nad produkcijskom
    # bazom i potvrdjeno stvarnim pozivom: `GET /api/export/complete` je vraćao
    # HTTP 503 "podaci iz sledećih tabela nisu mogli da se pročitaju: klijenti,
    # predmet_komentari". Dakle prenosivost podataka (ZZPL čl. 36 / GDPR čl. 20)
    # nije radila ni za jednog korisnika.
    # C1-F1: kolona se vise ne salje PostgREST-u (upit ide po `id`); koristi se
    # samo za redosled u izvozu (`_kljuc_redosleda`).
    tables = [
        ("predmeti",          "predmeti.json",     "created_at"),
        ("klijenti",          "klijenti.json",     "kreirano"),
        ("billing_entries",   "billing.json",      "created_at"),
        ("predmet_dokumenti", "dokumenti.json",    "created_at"),
        ("predmet_beleske",   "beleske.json",      "created_at"),
        ("rocista",           "rocista.json",      "datum"),
        ("predmet_hronologija","hronologija.json", "datum_iso"),
        ("predmet_komentari", "komentari.json",    "kreirano"),
    ]

    # C1 (Night Sprint II): faze izvoza se beleze istinito. Server moze da
    # dokaze najvise fazu 3 (arhiva napravljena i predata odgovoru); da je
    # klijent primio ceo odgovor server NE moze da dokaze, pa to nijedan zapis
    # ni poruka ne tvrde. Neuspeh u bilo kojoj fazi ostavlja
    # `data_export_failed` (nikad `data_export`) -- samo faza, imena tabela i
    # klasa izuzetka; nikad sadrzaj arhive, tekst izuzetka ni email.
    def _neuspeh(faza: str, **dodatno) -> None:
        meta = {"format": "zip", "stage": faza, "archive_sent": False}
        meta.update(dodatno)
        _spawn_bg(_imm_log(
            "data_export_failed",
            user_id=uid,
            resource_type="all_user_data",
            metadata=meta,
        ), name="data_export_failed_audit")

    # Faza 1 -> 2: klijent baze. Pad ovde znaci da nijedna tabela nije procitana.
    try:
        supa = _get_supa()
    except Exception as e:
        logger.error("[EXPORT] baza nedostupna (%s) -- izvoz NIJE napravljen", type(e).__name__)
        _neuspeh("pre_retrieval", error_class=type(e).__name__)
        raise HTTPException(
            status_code=503,
            detail="Izvoz nije napravljen i nije vam poslat. Pokušajte ponovo za koji minut.",
        )

    # Faze 2 i 3, tabela po tabela: u memoriji je istovremeno samo jedna
    # tabela (kao JSON) i ZIP -- ne svih 8. ZIP se salje tek ako je SVAKA
    # tabela procitana do kraja; inace se odbacuje.
    _failed: list[str] = []
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            readme = _README.format(datum=now.replace("T", " "), email=email)
            zf.writestr("README.txt", readme)
            for table, fname, order in tables:
                data = await _fetch(supa, table, uid, order, errors=_failed)
                if _failed:
                    continue  # arhiva se ionako odbacuje; samo se imenuju sve pale tabele
                zf.writestr(fname, json.dumps(data, ensure_ascii=False, indent=2, default=str))
                del data
    except Exception as e:
        logger.error("[EXPORT] pravljenje arhive palo (%s) -- izvoz NIJE poslat", type(e).__name__)
        _neuspeh("serialization", error_class=type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail="Izvoz nije napravljen i nije vam poslat. Pokušajte ponovo.",
        )

    # S4-4: never hand the data subject a partial archive that calls itself
    # complete. The ZIP is discarded rather than shipped.
    if _failed:
        _neuspeh("retrieval", failed_tables=list(_failed))
        raise HTTPException(
            status_code=503,
            detail=(
                "Export nije kompletan — podaci iz sledećih tabela nisu mogli da se "
                f"pročitaju: {', '.join(_failed)}. Nepotpun export vam nije poslat "
                "jer bi izgledao kao potpun. Pokušajte ponovo za koji minut."
            ),
        )

    # N04: audit se upisuje tek POSLE uspeha. Ranije je `data_export` pisan pre
    # citanja tabela, pa je i odbijen (503) izvoz ostajao u nepromenjivom logu
    # kao izvrsen izvoz -- suprotno static/security.html §14.2 („Svaki kompletan
    # izvoz upisuje se ..."). `spawn` drzi referencu na zadatak (S1-1).
    # C1: zapis tvrdi samo fazu 3 -- isporuka klijentu nije serverski dokaziva.
    _spawn_bg(_imm_log(
        "data_export",
        user_id=uid,
        resource_type="all_user_data",
        metadata={
            "email": email,
            "format": "zip",
            "stage": "archive_generated",
            "delivery": "not_verified_by_server",
        },
    ), name="data_export_audit")

    buf.seek(0)
    filename = f"vindex-export-{now}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
