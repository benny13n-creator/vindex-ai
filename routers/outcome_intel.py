# -*- coding: utf-8 -*-
"""
Outcome Intelligence — statistička analiza ishoda predmeta kancelarije.

GET /api/outcome-intel/predmeti/{predmet_id}
Analizira sve zatvorene predmete istog tipa i vraća statističke uvide.
"U 82% uspešnih radnih sporova postojala je pisana komunikacija poslodavca."
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.outcome_intel")
router = APIRouter(prefix="/api/outcome-intel", tags=["outcome_intel"])

_OUTCOME_SYSTEM = """Ti si pravni analitičar koji analizira obrasce pobeda i poraza iz zatvorenih predmeta advokatske kancelarije u Srbiji.

Na osnovu datih podataka izluči konkretne uvide o tome šta razlikuje pobede od poraza.
FORMAT (tačno ovako, u ovom redosledu):

📊 STATISTIKA KANCELARIJE
[Cifre: win rate %, broj predmeta, prosečna vrednost. Bez uvoda.]

🏆 FAKTORI USPEHA (prisutni u pobedama, odsutni u porazima)
[2-3 konkretna faktora sa procentima — npr. "Pisana komunikacija prisutna u 85% pobeda"]

⚠️ FAKTORI RIZIKA (prisutni u porazima)
[1-2 faktora sa procentima]

💡 PREPORUKA ZA OVAJ PREDMET
[1 konkretna akcija zasnovana na istoriji — šta da se osigura ili pribavi]

Budi konkretan sa brojevima. Srpski jezik. Bez generalizacija. Max 200 reči ukupno."""


@router.get("/predmeti/{predmet_id}")
async def get_outcome_intel(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    # Ownership + tekući predmet
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,opis"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]
    tip = predmet.get("tip") or "ostalo"

    # Svi predmeti istog tipa
    svi_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,created_at,opis"
        ).eq("user_id", uid).eq("tip", tip).execute()
    )
    svi = svi_r.data or []

    if len(svi) <= 1:
        return {
            "analiza": (
                f"📊 STATISTIKA KANCELARIJE\n"
                f"Tip '{tip}': {len(svi)} predmet(a) ukupno — premalo podataka za statističku analizu.\n\n"
                "💡 PREPORUKA\n"
                "Outcome Intelligence se aktivira kada kancelarija ima ≥2 predmeta istog tipa, "
                "od kojih je bar jedan zatvoren sa ishodom. "
                "Zatvarajte predmete kroz Hronologiju → 'Predmet zatvoren' kako bi sistem učio."
            ),
            "ukupno_predmeta": len(svi),
            "isti_tip": 0,
            "tip": tip,
            "win_rate": None,
        }

    zatvoreni_statusi = {"zatvoren", "arhiviran", "uspesno", "neuspesno"}
    zatvoreni = [p for p in svi if p.get("status") in zatvoreni_statusi]
    aktivni   = [p for p in svi if p.get("status") not in zatvoreni_statusi]

    # ── Dohvati ishod iz hronologije za svaki zatvoren predmet ───────────────
    _POBEDA_KW = {"pobeda", "nagodba", "poravnanje", "uspeh", "uspesno", "uspešno", "prihvacena", "prihvaćena"}
    _PORAZ_KW  = {"poraz", "odbacena", "odbijen", "izgubio", "neuspesno", "neuspešno", "odbijen"}

    def _klasifikuj_ishod(ishod_str: str) -> str:
        """Fleksibilna klasifikacija — radi i kad tekst nije tačan."""
        low = (ishod_str or "").lower().strip()
        for kw in _POBEDA_KW:
            if kw in low:
                return "pobeda"
        for kw in _PORAZ_KW:
            if kw in low:
                return "poraz"
        return "nepoznato"

    ishod_map: dict[str, str] = {}
    if zatvoreni:
        try:
            zids = [p["id"] for p in zatvoreni[:30]]
            hr = await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").select(
                    "predmet_id,dogadjaj"
                ).in_("predmet_id", zids).ilike("dogadjaj", "%zatvoren%").execute()
            )
            for h in (hr.data or []):
                pid = h.get("predmet_id","")
                dog = h.get("dogadjaj","")
                if "Ishod:" in dog and pid not in ishod_map:
                    raw_ishod = dog.split("Ishod:", 1)[1].strip()
                    ishod_map[pid] = _klasifikuj_ishod(raw_ishod)
                elif pid not in ishod_map:
                    ishod_map[pid] = _klasifikuj_ishod(dog)
        except Exception as exc:
            logger.debug("[OUTCOME] hronologija greška: %s", exc)

    # Dopuni iz status polja predmeta ako hronologija nema ishod
    for p in zatvoreni:
        pid = p["id"]
        if ishod_map.get(pid) in (None, "nepoznato"):
            st = (p.get("status") or "").lower()
            if st in ("uspesno", "uspešno"):
                ishod_map[pid] = "pobeda"
            elif st in ("neuspesno", "neuspešno"):
                ishod_map[pid] = "poraz"

    pobede = [p for p in zatvoreni if ishod_map.get(p["id"]) == "pobeda"]
    porazi = [p for p in zatvoreni if ishod_map.get(p["id"]) == "poraz"]
    win_rate = round(len(pobede) / max(1, len(pobede) + len(porazi)) * 100) if (pobede or porazi) else None

    # ── Dokument korelacija po ishodu — batch upiti ───────────────────────────
    win_ids  = [p["id"] for p in pobede]
    lose_ids = [p["id"] for p in porazi]
    all_ids  = [p["id"] for p in zatvoreni]

    async def _get_dok_tipovi_batch(predmet_ids: list) -> dict:
        if not predmet_ids:
            return {}
        pattern: dict = {}
        try:
            dk = await asyncio.to_thread(
                lambda: supa.table("predmet_dokumenti").select("predmet_id")
                    .in_("predmet_id", predmet_ids[:15])
                    .execute()
            )
            for d in (dk.data or []):
                pid = d.get("predmet_id")
                if pid:
                    pattern[pid] = pattern.get(pid, 0) + 1
        except Exception:
            pass
        return pattern

    win_docs, lose_docs, all_docs = await asyncio.gather(
        _get_dok_tipovi_batch(win_ids),
        _get_dok_tipovi_batch(lose_ids),
        _get_dok_tipovi_batch(all_ids),
        return_exceptions=False,
    )

    # ── Billing prosek — batch upit ───────────────────────────────────────────
    billing_avg = []
    billing_ids = [zp["id"] for zp in zatvoreni[:10]]
    if billing_ids:
        try:
            be_all = await asyncio.to_thread(
                lambda: supa.table("billing_entries").select("predmet_id,iznos")
                    .in_("predmet_id", billing_ids)
                    .execute()
            )
            totals_by_pid: dict[str, float] = {}
            for e in (be_all.data or []):
                pid = e.get("predmet_id", "")
                totals_by_pid[pid] = totals_by_pid.get(pid, 0.0) + float(e.get("iznos", 0))
            billing_avg = [v for v in totals_by_pid.values() if v > 0]
        except Exception:
            pass
    avg_vrednost = int(sum(billing_avg) / len(billing_avg)) if billing_avg else 0

    sorted_docs = sorted(all_docs.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── GPT kontekst ──────────────────────────────────────────────────────────
    ctx = f"""Tip predmeta: {tip}
Ukupno predmeta: {len(svi)} (aktivnih: {len(aktivni)}, zatvorenih: {len(zatvoreni)})
Pobede: {len(pobede)} | Porazi: {len(porazi)} | Win rate: {win_rate if win_rate is not None else 'N/A'}%
Prosečna fakturisana vrednost: {avg_vrednost:,} RSD
"""
    if win_docs:
        ctx += "\nDokumenti prisutni u POBEDAMA (top 5):\n"
        for dt, cnt in sorted(win_docs.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = int(cnt / max(1, len(pobede)) * 100)
            ctx += f"  - {dt}: {pct}% pobeda\n"
    if lose_docs:
        ctx += "\nDokumenti prisutni u PORAZIMA (top 5):\n"
        for dt, cnt in sorted(lose_docs.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = int(cnt / max(1, len(porazi)) * 100)
            ctx += f"  - {dt}: {pct}% poraza\n"
    if not win_docs and not lose_docs and sorted_docs:
        ctx += "\nDokumenti u svim predmetima (top 5):\n"
        for dt, cnt in sorted_docs:
            ctx += f"  - {dt}: {int(cnt/max(1,len(zatvoreni))*100)}% predmeta\n"

    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.25,
            max_tokens=500,
            messages=[
                {"role": "system", "content": _OUTCOME_SYSTEM},
                {"role": "user",   "content": ctx},
            ],
        )
        analiza = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("[OUTCOME] GPT greška: %s", exc)
        linija = [f"📊 STATISTIKA KANCELARIJE"]
        linija.append(f"Tip '{tip}': {len(zatvoreni)} zatvorenih, win rate {win_rate if win_rate is not None else '?'}%")
        if avg_vrednost:
            linija.append(f"Prosečna vrednost: {avg_vrednost:,} RSD")
        if win_docs:
            top_win = sorted(win_docs.items(), key=lambda x: x[1], reverse=True)[0]
            linija.append(f"\n🏆 FAKTORI USPEHA\n'{top_win[0]}' prisutan u {int(top_win[1]/max(1,len(pobede))*100)}% pobeda")
        linija.append(f"\n💡 PREPORUKA\nOsigurajte ključne dokumente od prvog dana predmeta.")
        analiza = "\n".join(linija)

    return {
        "analiza":         analiza,
        "ukupno_predmeta": len(svi),
        "zatvoreni":       len(zatvoreni),
        "aktivni":         len(aktivni),
        "pobede":          len(pobede),
        "porazi":          len(porazi),
        "win_rate":        win_rate,
        "isti_tip":        len(svi) - 1,
        "tip":             tip,
        "avg_vrednost":    avg_vrednost,
        "top_dokumenti":   sorted_docs,
    }
