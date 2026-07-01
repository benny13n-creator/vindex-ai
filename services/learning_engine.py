# -*- coding: utf-8 -*-
"""
Vindex AI — services/learning_engine.py

Learning Engine: sistem koji uči od posledica AI preporuka.

Svaki put kad AI da preporuku → beleži se u recommendation_log.
Svaki put kad se predmet zatvori → beleži se ishod u outcome_log.
Agregat naučenih obrazaca živi u case_patterns.

Posle godinu dana kancelarija može da čuje:
"Na osnovu 146 vaših predmeta, angažovanje veštaka dovelo je do uspeha u 81 slučaju (55%)."
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.deps import _get_supa

logger = logging.getLogger("vindex.learning_engine")

_VALID_ISHODI = {"pobeda", "poraz", "nagodba", "odustajanje", "u_toku"}
_VALID_TIPOVI = {"strategija", "argument", "preporuka", "sledeca_radnja", "upozorenje"}


class LearningEngine:
    """Singleton servis za Learning Loop — beleži, uči, kalibrira."""

    # ─── Log AI preporuke ─────────────────────────────────────────────────────

    async def log_recommendation(
        self,
        user_id: str,
        predmet_id: Optional[str],
        tip: str,
        tekst: str,
        kontekst: Optional[dict] = None,
    ) -> str:
        """Beleži AI preporuku. Vraća UUID zapisa (koristi se za feedback)."""
        rec_id = str(uuid.uuid4())
        if tip not in _VALID_TIPOVI:
            tip = "preporuka"
        try:
            supa = _get_supa()
            await asyncio.to_thread(
                lambda: supa.table("recommendation_log").insert({
                    "id":         rec_id,
                    "user_id":    user_id,
                    "predmet_id": predmet_id,
                    "tip":        tip,
                    "tekst":      tekst[:5000],
                    "kontekst":   kontekst or {},
                }).execute()
            )
        except Exception as exc:
            logger.warning("[LEARNING] log_recommendation greška: %s", exc)
        return rec_id

    # ─── Feedback na preporuku ────────────────────────────────────────────────

    async def feedback_recommendation(
        self,
        rec_id: str,
        user_id: str,
        prihvacena: bool,
    ) -> None:
        """Korisnik prihvatio ili odbio preporuku. Osnov za merenje AI efikasnosti."""
        try:
            supa = _get_supa()
            await asyncio.to_thread(
                lambda: supa.table("recommendation_log")
                    .update({"prihvacena": prihvacena})
                    .eq("id", rec_id)
                    .eq("user_id", user_id)
                    .execute()
            )
        except Exception as exc:
            logger.warning("[LEARNING] feedback_recommendation greška: %s", exc)

    # ─── Beleži ishod predmeta ────────────────────────────────────────────────

    async def log_outcome(
        self,
        user_id: str,
        predmet_id: str,
        ishod: str,
        presudni_faktori: list[str],
        trajanje_meseci: Optional[int] = None,
        vrednost_spora_rsd: Optional[float] = None,
        komentar: Optional[str] = None,
    ) -> str:
        """
        Beleži ishod predmeta i triggeruje update case_patterns.
        Ovo je najvažniji event u Learning Loop-u.
        """
        if ishod not in _VALID_ISHODI:
            ishod = "u_toku"

        outcome_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            supa = _get_supa()
            await asyncio.to_thread(
                lambda: supa.table("outcome_log").upsert({
                    "id":                 outcome_id,
                    "user_id":            user_id,
                    "predmet_id":         predmet_id,
                    "ishod":              ishod,
                    "presudni_faktori":   presudni_faktori,
                    "trajanje_meseci":    trajanje_meseci,
                    "vrednost_spora_rsd": vrednost_spora_rsd,
                    "komentar":           komentar,
                    "updated_at":         now_iso,
                }, on_conflict="predmet_id").execute()
            )
        except Exception as exc:
            logger.warning("[LEARNING] log_outcome greška: %s", exc)
            return outcome_id

        # Ažuriraj preporuke za ovaj predmet (retroaktivno)
        if ishod in ("pobeda", "poraz"):
            asyncio.create_task(self._mark_recommendations_outcome(
                user_id, predmet_id, ishod == "pobeda"
            ))

        # Ažuriraj case_patterns za tip spora ovog predmeta
        asyncio.create_task(self._update_patterns(user_id, predmet_id, ishod, presudni_faktori))

        return outcome_id

    async def _mark_recommendations_outcome(
        self, user_id: str, predmet_id: str, pozitivan: bool
    ) -> None:
        """Retroaktivno označi sve preporuke ovog predmeta sa ishodom."""
        try:
            supa = _get_supa()
            await asyncio.to_thread(
                lambda: supa.table("recommendation_log")
                    .update({"ishod_pozitivan": pozitivan})
                    .eq("user_id", user_id)
                    .eq("predmet_id", predmet_id)
                    .not_.is_("prihvacena", "null")
                    .execute()
            )
        except Exception as exc:
            logger.warning("[LEARNING] _mark_recommendations_outcome greška: %s", exc)

    async def _update_patterns(
        self,
        user_id: str,
        predmet_id: str,
        ishod: str,
        presudni_faktori: list[str],
    ) -> None:
        """
        Ažurira case_patterns na osnovu novog ishoda.
        Za svaki presudni faktor: pobede++ ili porazi++ u odgovarajućem tipu spora.
        Fire-and-forget — nikad ne propagira grešku.
        """
        if ishod not in ("pobeda", "poraz"):
            return
        if not presudni_faktori:
            return

        try:
            supa = _get_supa()
            # Nađi tip spora predmeta
            pred_r = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("tip")
                    .eq("id", predmet_id)
                    .limit(1)
                    .execute()
            )
            tip_spora = ((pred_r.data or [{}])[0].get("tip") or "ostalo").strip()

            je_pobeda = ishod == "pobeda"

            for faktor in presudni_faktori[:10]:
                faktor = faktor.strip()[:100]
                if not faktor:
                    continue
                try:
                    # Pokušaj upsert: ako postoji red, inkrementiraj; ako ne, kreiraj
                    existing_r = await asyncio.to_thread(
                        lambda f=faktor: supa.table("case_patterns")
                            .select("id,pobede,porazi,ukupno_predmeta")
                            .eq("user_id", user_id)
                            .eq("tip_spora", tip_spora)
                            .eq("faktor", f)
                            .limit(1)
                            .execute()
                    )
                    existing = (existing_r.data or [])

                    now_iso = datetime.now(timezone.utc).isoformat()
                    if existing:
                        row = existing[0]
                        p = row.get("pobede", 0) + (1 if je_pobeda else 0)
                        po = row.get("porazi", 0) + (0 if je_pobeda else 1)
                        uk = row.get("ukupno_predmeta", 0) + 1
                        await asyncio.to_thread(
                            lambda rid=row["id"], pp=p, ppo=po, uk2=uk: supa.table("case_patterns")
                                .update({"pobede": pp, "porazi": ppo,
                                         "ukupno_predmeta": uk2, "updated_at": now_iso})
                                .eq("id", rid)
                                .execute()
                        )
                    else:
                        await asyncio.to_thread(
                            lambda f=faktor, p2=int(je_pobeda), po2=int(not je_pobeda):
                                supa.table("case_patterns").insert({
                                    "user_id":         user_id,
                                    "tip_spora":       tip_spora,
                                    "faktor":          f,
                                    "ukupno_predmeta": 1,
                                    "pobede":          p2,
                                    "porazi":          po2,
                                    "updated_at":      datetime.now(timezone.utc).isoformat(),
                                }).execute()
                        )
                except Exception as fe:
                    logger.debug("[LEARNING] _update_patterns faktor=%s greška: %s", faktor, fe)

        except Exception as exc:
            logger.warning("[LEARNING] _update_patterns greška: %s", exc)

    # ─── Slični predmeti iz kancelarije ──────────────────────────────────────

    async def get_similar_cases(
        self,
        user_id: str,
        predmet_opis: str,
        tip_spora: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Nađi slične zatvorene predmete iz firmine istorije.
        Vraća [{predmet_naziv, tip, ishod, trajanje_meseci, presudni_faktori, komentar}]
        """
        try:
            supa = _get_supa()
            # Dohvati zatvorene predmete za ovaj tip spora
            pred_r = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("id,naziv,tip,opis")
                    .eq("user_id", user_id)
                    .eq("tip", tip_spora)
                    .in_("status", ["zatvoren", "arhiviran", "uspesno", "neuspesno"])
                    .limit(50)
                    .execute()
            )
            predmeti = pred_r.data or []
            if not predmeti:
                return []

            # Nađi ishode za te predmete
            ids = [p["id"] for p in predmeti]
            outcome_r = await asyncio.to_thread(
                lambda: supa.table("outcome_log")
                    .select("predmet_id,ishod,trajanje_meseci,presudni_faktori,komentar")
                    .in_("predmet_id", ids)
                    .execute()
            )
            outcome_map = {o["predmet_id"]: o for o in (outcome_r.data or [])}

            # Keyword similarity (jednostavno — bez vektora)
            kljucne_reci = set(predmet_opis.lower().split())
            result = []
            for p in predmeti:
                if p["id"] not in outcome_map:
                    continue
                opis_lower = (p.get("opis") or "").lower()
                poklapanje = sum(1 for r in kljucne_reci if r in opis_lower and len(r) > 3)
                o = outcome_map[p["id"]]
                result.append({
                    "predmet_naziv":    p.get("naziv", ""),
                    "tip":              p.get("tip", ""),
                    "ishod":            o["ishod"],
                    "trajanje_meseci":  o.get("trajanje_meseci"),
                    "presudni_faktori": o.get("presudni_faktori") or [],
                    "komentar":         o.get("komentar"),
                    "_poklapanje":      poklapanje,
                })

            result.sort(key=lambda x: x["_poklapanje"], reverse=True)
            for r in result:
                r.pop("_poklapanje", None)
            return result[:limit]

        except Exception as exc:
            logger.warning("[LEARNING] get_similar_cases greška: %s", exc)
            return []

    # ─── Confidence data za tip spora ────────────────────────────────────────

    async def get_confidence_data(self, user_id: str, tip_spora: str) -> dict:
        """
        Strukturirani confidence podaci iz kancelarijske istorije.
        Osnov za ConfidenceCalibrator.
        """
        default = {
            "nivo": "nisko",
            "uzoraka_kancelarije": 0,
            "win_rate_kancelarije": None,
            "top_faktori_uspeha": [],
            "top_faktori_poraza": [],
            "faktori_sa_stopama": [],
        }
        try:
            supa = _get_supa()
            patterns_r = await asyncio.to_thread(
                lambda: supa.table("case_patterns")
                    .select("faktor,pobede,porazi,ukupno_predmeta,uspeh_stopa")
                    .eq("user_id", user_id)
                    .eq("tip_spora", tip_spora)
                    .order("ukupno_predmeta", desc=True)
                    .limit(30)
                    .execute()
            )
            patterns = patterns_r.data or []

            if not patterns:
                return default

            ukupno_uzoraka = sum(p.get("ukupno_predmeta", 0) for p in patterns)
            ukupno_pobeda  = sum(p.get("pobede", 0) for p in patterns)
            ukupno_poraza  = sum(p.get("porazi", 0) for p in patterns)
            win_rate = None
            if ukupno_pobeda + ukupno_poraza > 0:
                win_rate = round(ukupno_pobeda / (ukupno_pobeda + ukupno_poraza) * 100, 1)

            faktori_sa_stopama = [
                {
                    "faktor":  p["faktor"],
                    "stopa":   float(p["uspeh_stopa"]) if p.get("uspeh_stopa") is not None else None,
                    "uzoraka": p.get("ukupno_predmeta", 0),
                }
                for p in patterns
                if p.get("uspeh_stopa") is not None
            ]
            faktori_sa_stopama.sort(key=lambda x: (x["stopa"] or 0), reverse=True)

            top_uspeha = [f["faktor"] for f in faktori_sa_stopama if (f["stopa"] or 0) >= 55][:3]
            top_poraza = [f["faktor"] for f in reversed(faktori_sa_stopama)
                          if (f["stopa"] or 100) < 45][:3]

            nivo = "nisko"
            if ukupno_uzoraka >= 10 and win_rate is not None:
                nivo = "visoko" if win_rate >= 60 else "srednje"
            elif ukupno_uzoraka >= 3:
                nivo = "srednje"

            return {
                "nivo":                   nivo,
                "uzoraka_kancelarije":    ukupno_uzoraka,
                "win_rate_kancelarije":   win_rate,
                "top_faktori_uspeha":     top_uspeha,
                "top_faktori_poraza":     top_poraza,
                "faktori_sa_stopama":     faktori_sa_stopama[:10],
            }

        except Exception as exc:
            logger.warning("[LEARNING] get_confidence_data greška: %s", exc)
            return default

    # ─── Statistika efikasnosti AI preporuka ─────────────────────────────────

    async def get_recommendation_stats(
        self,
        user_id: str,
        tip: Optional[str] = None,
    ) -> dict:
        """Statistika efikasnosti AI preporuka za dashboard."""
        default = {
            "ukupno_preporuka": 0,
            "prihvaceno": 0,
            "odbijeno": 0,
            "bez_odgovora": 0,
            "prihvacene_sa_pozitivnim_ishodom": 0,
            "stopa_prihvatanja": None,
            "stopa_uspesnosti_prihvacenih": None,
        }
        try:
            supa = _get_supa()
            q = supa.table("recommendation_log").select(
                "prihvacena,ishod_pozitivan"
            ).eq("user_id", user_id)
            if tip:
                q = q.eq("tip", tip)
            r = await asyncio.to_thread(lambda: q.limit(5000).execute())
            rows = r.data or []

            if not rows:
                return default

            ukupno    = len(rows)
            prihv     = sum(1 for r in rows if r.get("prihvacena") is True)
            odbij     = sum(1 for r in rows if r.get("prihvacena") is False)
            bez_odg   = ukupno - prihv - odbij
            poz_prihv = sum(1 for r in rows
                            if r.get("prihvacena") is True and r.get("ishod_pozitivan") is True)

            stopa_prihv = round(prihv / ukupno * 100, 1) if ukupno > 0 else None
            stopa_usp   = round(poz_prihv / prihv * 100, 1) if prihv > 0 else None

            return {
                "ukupno_preporuka":                ukupno,
                "prihvaceno":                      prihv,
                "odbijeno":                        odbij,
                "bez_odgovora":                    bez_odg,
                "prihvacene_sa_pozitivnim_ishodom": poz_prihv,
                "stopa_prihvatanja":               stopa_prihv,
                "stopa_uspesnosti_prihvacenih":    stopa_usp,
            }

        except Exception as exc:
            logger.warning("[LEARNING] get_recommendation_stats greška: %s", exc)
            return default

    # ─── Lessons Learned (Institucijska memorija) ─────────────────────────────

    async def generate_lessons_learned(
        self,
        user_id: str,
        predmet_id: str,
        ishod: str,
        presudni_faktori: list[str],
        komentar: Optional[str],
        tip_spora: str,
        uzroci: Optional[list[str]] = None,
        kontekst_poraza: Optional[str] = None,
    ) -> list[dict]:
        """GPT-4o-mini generiše 3-5 akcionabilnih lekcija posle zatvaranja predmeta.
        Svaka lekcija nosi epistemic metadata: broj_predmeta, pouzdanost."""
        # Broji koliko sličnih predmeta postoji — osnov za pouzdanost
        broj_predmeta = 1
        period_od_iso: Optional[str] = None
        period_do_iso: Optional[str] = None
        try:
            supa = _get_supa()
            cnt_r = await asyncio.to_thread(
                lambda: supa.table("outcome_log")
                    .select("created_at")
                    .eq("user_id", user_id)
                    .eq("tip_spora", tip_spora)
                    .order("created_at")
                    .execute()
            )
            slicni = cnt_r.data or []
            broj_predmeta = max(len(slicni), 1)
            if slicni:
                period_od_iso = (slicni[0].get("created_at") or "")[:10] or None
                period_do_iso = (slicni[-1].get("created_at") or "")[:10] or None
        except Exception:
            pass

        pouzdanost = "niska" if broj_predmeta < 3 else ("srednja" if broj_predmeta < 8 else "visoka")
        uzorak_info = (
            f"NAPOMENA: Uzorak je mali ({broj_predmeta} predmeta tipa '{tip_spora}'). "
            "Svaku lekciju oznaci kao preliminarnu."
            if broj_predmeta < 3 else
            f"Zasnovano na {broj_predmeta} predmeta tipa '{tip_spora}' (pouzdanost: {pouzdanost})."
        )

        faktori_txt = ", ".join(presudni_faktori[:8]) if presudni_faktori else "—"
        prompt = (
            f"Predmet je zatvoren. Tip spora: {tip_spora}. Ishod: {ishod}.\n"
            f"Presudni faktori: {faktori_txt}\n"
            + (f"Uzroci ishoda: {', '.join(uzroci[:5])}\n" if uzroci else "")
            + (f"Kontekst: {kontekst_poraza[:500]}\n" if kontekst_poraza else "")
            + (f"Komentar advokata: {komentar[:500]}\n" if komentar else "")
            + f"\nKontekst uzorka: {uzorak_info}\n"
            + "\nGeneriši 3-5 konkretnih lekcija koje ce pomoci u buducim predmetima. "
            "Svaka mora biti AKCIONA — sta konkretno uraditi ili izbegavati. "
            "Ako je uzorak mali, svaku lekciju pocni sa 'PRELIMINARNO:'. "
            "Vrati JSON: {\"lekcije\": [{\"lecija\": \"...\", "
            "\"kategorija\": \"strategija|procesna|dokaz|komunikacija|finansijska|ostalo\", "
            "\"vaznost\": 1-5, \"primenjljivo_na\": [\"tip spora...\"]}]}\n"
            "Ekavica. Konkretan i akcioni ton."
        )
        try:
            from openai import OpenAI
            oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = await asyncio.to_thread(
                lambda: oai.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.3,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "Analiziras zatvorene pravne predmete i generises konkretne lekcije. Ekavica strogo. Vracas SAMO JSON."},
                        {"role": "user", "content": prompt},
                    ],
                )
            )
            raw = json.loads(resp.choices[0].message.content or "{}")
            _VALID_KAT = {"strategija", "procesna", "dokaz", "komunikacija", "finansijska", "ostalo"}
            result = []
            for l in (raw.get("lekcije") or [])[:5]:
                if not isinstance(l, dict) or not l.get("lecija"):
                    continue
                kat = l.get("kategorija", "ostalo")
                result.append({
                    "lecija":          str(l["lecija"])[:1000],
                    "kategorija":      kat if kat in _VALID_KAT else "ostalo",
                    "vaznost":         min(max(int(l.get("vaznost", 3)), 1), 5),
                    "primenjljivo_na": [str(x) for x in (l.get("primenjljivo_na") or [])[:5]],
                    "pouzdanost":      pouzdanost,
                    "broj_predmeta":   broj_predmeta,
                    "period_od":       period_od_iso,
                    "period_do":       period_do_iso,
                    "status_lekcije":  "predlog_ai",
                })
            return result
        except Exception as exc:
            logger.warning("[LEARNING] generate_lessons_learned greška: %s", exc)
            return []

    async def save_lessons(
        self,
        user_id: str,
        predmet_id: Optional[str],
        lessons: list[dict],
        tip_spora: str,
    ) -> int:
        """Čuva lekcije u lessons_learned sa epistemic metadata. Vraća broj sačuvanih."""
        if not lessons:
            return 0
        count = 0
        try:
            supa = _get_supa()
            for l in lessons:
                try:
                    await asyncio.to_thread(
                        lambda ll=l: supa.table("lessons_learned").insert({
                            "user_id":         user_id,
                            "predmet_id":      predmet_id,
                            "tip_spora":       tip_spora,
                            "lecija":          ll["lecija"],
                            "kategorija":      ll.get("kategorija", "ostalo"),
                            "vaznost":         ll.get("vaznost", 3),
                            "primenjljivo_na": ll.get("primenjljivo_na", []),
                            "pouzdanost":      ll.get("pouzdanost", "niska"),
                            "broj_predmeta":   ll.get("broj_predmeta", 1),
                            "period_od":       ll.get("period_od"),
                            "period_do":       ll.get("period_do"),
                            "status_lekcije":  ll.get("status_lekcije", "predlog_ai"),
                        }).execute()
                    )
                    count += 1
                except Exception as e:
                    logger.debug("[LEARNING] save_lessons red greška: %s", e)
        except Exception as exc:
            logger.warning("[LEARNING] save_lessons greška: %s", exc)
        return count

    # ─── Counterfactual Learning (što-ako analiza) ────────────────────────────

    async def generate_counterfactual_analysis(
        self,
        user_id: str,
        predmet_id: str,
        hipoteza: str,
        tip_hipoteze: str,
        odgovor: Optional[str] = None,
        komentar: Optional[str] = None,
    ) -> dict:
        """Analizira alternativni ishod: 'Šta bi se desilo da smo prihvatili nagodbu?'"""
        ctx_txt = ""
        try:
            supa = _get_supa()
            pred_r = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("naziv,tip,opis,status")
                    .eq("id", predmet_id)
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
            )
            pred = (pred_r.data or [{}])[0]
            out_r = await asyncio.to_thread(
                lambda: supa.table("outcome_log")
                    .select("ishod,presudni_faktori,trajanje_meseci,komentar,uzroci")
                    .eq("predmet_id", predmet_id)
                    .limit(1)
                    .execute()
            )
            out = (out_r.data or [{}])[0]
            ctx_txt = (
                f"Predmet: {pred.get('naziv','?')} (tip: {pred.get('tip','?')})\n"
                f"Stvarni ishod: {out.get('ishod','nepoznato')}\n"
                f"Presudni faktori: {', '.join(out.get('presudni_faktori') or [])}\n"
                f"Trajanje: {out.get('trajanje_meseci','?')} meseci\n"
                + (f"Uzroci: {', '.join(out.get('uzroci') or [])}\n" if out.get("uzroci") else "")
            )
        except Exception as e:
            logger.debug("[LEARNING] counterfactual context: %s", e)

        prompt = (
            f"Kontekst predmeta:\n{ctx_txt}\n"
            f"Hipoteza (što-ako): {hipoteza}\n"
            + (f"Odgovor advokata: {odgovor}\n" if odgovor else "")
            + (f"Komentar: {komentar}\n" if komentar else "")
            + "Analiziraj: da je hipoteza bila tacna, kako bi se predmet razvio? "
            "Koji faktori bi bili drugaciji? Kakav verovatni ishod?\n"
            "Vrati JSON: {\"analiza\": \"...\", \"verovatni_ishod\": \"...\", "
            "\"faktori_koji_bi_se_promenili\": [...], \"lekcija\": \"...\", "
            "\"procena_verovatnoce\": 0-100}\nEkavica. Konkretan, ne teorijski."
        )

        result: dict = {
            "hipoteza": hipoteza,
            "tip_hipoteze": tip_hipoteze,
            "analiza": "",
            "verovatni_ishod": "",
            "faktori_koji_bi_se_promenili": [],
            "lekcija": "",
            "procena_verovatnoce": None,
        }
        ai_procena_txt = ""
        try:
            from openai import OpenAI
            oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = await asyncio.to_thread(
                lambda: oai.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.3,
                    max_tokens=600,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "Ti si pravni strateg koji analizira alternativne ishode. Ekavica strogo. Vracas SAMO JSON."},
                        {"role": "user", "content": prompt},
                    ],
                )
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            result["analiza"] = parsed.get("analiza", "")
            result["verovatni_ishod"] = parsed.get("verovatni_ishod", "")
            result["faktori_koji_bi_se_promenili"] = parsed.get("faktori_koji_bi_se_promenili", [])
            result["lekcija"] = parsed.get("lekcija", "")
            result["procena_verovatnoce"] = parsed.get("procena_verovatnoce")
            ai_procena_txt = f"{result['analiza']} | {result['verovatni_ishod']}"
        except Exception as exc:
            logger.warning("[LEARNING] counterfactual GPT greška: %s", exc)

        _VALID_TIP = {"nagodba", "strateski", "takticki", "procesni", "ostalo"}
        try:
            supa = _get_supa()
            await asyncio.to_thread(
                lambda: supa.table("counterfactual_log").insert({
                    "user_id":     user_id,
                    "predmet_id":  predmet_id,
                    "hipoteza":    hipoteza[:1000],
                    "tip_hipoteze": tip_hipoteze if tip_hipoteze in _VALID_TIP else "ostalo",
                    "odgovor":     (odgovor or "")[:500],
                    "komentar":    (komentar or "")[:500],
                    "ai_procena":  ai_procena_txt[:2000],
                }).execute()
            )
        except Exception as exc:
            logger.debug("[LEARNING] counterfactual_log insert: %s", exc)

        return result

    # ─── Firm DNA (Organizaciona inteligencija) ───────────────────────────────

    async def extract_firm_dna(self, user_id: str) -> list[dict]:
        """
        Ekstrahuje obrasce ponašanja kancelarije iz istorije zatvorenih predmeta.
        Minimalno 3 zatvorena predmeta da bi ekstrakcija bila smislena.
        """
        try:
            supa = _get_supa()
            pred_r = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("id,naziv,tip,status")
                    .eq("user_id", user_id)
                    .like("status", "zatvoren%")
                    .limit(50)
                    .execute()
            )
            predmeti = pred_r.data or []
            if len(predmeti) < 3:
                return []

            ids = [p["id"] for p in predmeti[:30]]
            out_r = await asyncio.to_thread(
                lambda: supa.table("outcome_log")
                    .select("predmet_id,ishod,presudni_faktori,tip_spora,komentar,uzroci")
                    .in_("predmet_id", ids)
                    .execute()
            )
            outcomes = out_r.data or []
            if len(outcomes) < 3:
                return []

            istorija_txt = ""
            pred_map = {p["id"]: p for p in predmeti}
            for i, o in enumerate(outcomes[:20]):
                pred = pred_map.get(o.get("predmet_id", ""), {})
                faktori = ", ".join(o.get("presudni_faktori") or [])
                uzroci  = ", ".join(o.get("uzroci") or [])
                istorija_txt += (
                    f"\n[{i+1}] {pred.get('naziv','?')[:60]} | tip: {o.get('tip_spora','?')} | "
                    f"ishod: {o.get('ishod','?')} | faktori: {faktori}"
                    + (f" | uzroci: {uzroci}" if uzroci else "")
                )

            prompt = (
                f"Istorija {len(outcomes)} zatvorenih predmeta kancelarije:\n{istorija_txt}\n\n"
                "Ekstrahuj 3-8 obrazaca ponasanja kancelarije (Firm DNA). "
                "Obrazac mora biti ponovljiv, ne jedinstven za jedan predmet.\n"
                "Vrati JSON: {\"obrasci\": [{\"pattern\": \"...\", "
                "\"tip\": \"argument|procesna|komunikacija|taktika|ostalo\", "
                "\"frekvencija\": N, \"primer\": \"...\"}]}\n"
                "Ekavica. Primeri: 'Kancelarija uvek angažuje veštaka u radnim sporovima', "
                "'U porazima obično nedostaje pisana dokumentacija'."
            )

            from openai import OpenAI
            oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = await asyncio.to_thread(
                lambda: oai.chat.completions.create(
                    model="gpt-4o",
                    temperature=0.2,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "Analiziras obrasce advokatske kancelarije. Ekavica strogo. Vracas SAMO JSON."},
                        {"role": "user", "content": prompt},
                    ],
                )
            )
            raw = json.loads(resp.choices[0].message.content or "{}")
            obrasci = raw.get("obrasci") or []

            _VALID_TIP = {"argument", "procesna", "komunikacija", "taktika", "ostalo"}
            today_iso = datetime.now(timezone.utc).date().isoformat()
            saved = []

            # Verzionisanje: stare verzije → aktuelna=FALSE; nova verzija dobija max+1
            try:
                max_r = await asyncio.to_thread(
                    lambda: supa.table("firm_dna")
                        .select("verzija")
                        .eq("user_id", user_id)
                        .eq("aktuelna", True)
                        .order("verzija", desc=True)
                        .limit(1)
                        .execute()
                )
                max_rows = max_r.data or []
                nova_verzija = (max_rows[0].get("verzija") or 0) + 1 if max_rows else 1
                # Arhiviraj stare
                await asyncio.to_thread(
                    lambda: supa.table("firm_dna")
                        .update({"aktuelna": False})
                        .eq("user_id", user_id)
                        .eq("aktuelna", True)
                        .execute()
                )
            except Exception as e:
                logger.debug("[LEARNING] firm_dna verzionisanje: %s", e)
                nova_verzija = 1

            for o in obrasci[:8]:
                if not o.get("pattern"):
                    continue
                pattern = str(o["pattern"])[:500]
                tip = o.get("tip", "ostalo")
                if tip not in _VALID_TIP:
                    tip = "ostalo"
                try:
                    await asyncio.to_thread(
                        lambda p=pattern, t=tip, f=o.get("frekvencija", 1), pr=o.get("primer", ""):
                            supa.table("firm_dna").insert({
                                "user_id":    user_id,
                                "pattern":    p,
                                "tip":        t,
                                "frekvencija": max(int(f), 1),
                                "uzoraka":    len(outcomes),
                                "primer":     str(pr)[:500],
                                "verzija":    nova_verzija,
                                "aktuelna":   True,
                                "verzija_od": today_iso,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }).execute()
                    )
                    saved.append({"pattern": pattern, "tip": tip, "frekvencija": o.get("frekvencija", 1), "verzija": nova_verzija})
                except Exception as e:
                    logger.debug("[LEARNING] firm_dna insert: %s", e)

            return saved
        except Exception as exc:
            logger.warning("[LEARNING] extract_firm_dna greška: %s", exc)
            return []

    # ─── Knowledge Decay (zastarelost preporuka) ──────────────────────────────

    async def check_knowledge_decay(self, user_id: str, lesson_id: str) -> bool:
        """
        Proverava da li je lekcija zastarela:
        - heuristika: starija od 18 meseci
        - RAG provera: postoje li novije presude koje joj protivrece?
        Vraća True ako je zastarela, i automatski je označava u bazi.
        """
        try:
            supa = _get_supa()
            lesson_r = await asyncio.to_thread(
                lambda: supa.table("lessons_learned")
                    .select("id,lecija,kategorija,created_at,zastarela")
                    .eq("id", lesson_id)
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
            )
            lessons = lesson_r.data or []
            if not lessons:
                return False
            lesson = lessons[0]
            if lesson.get("zastarela"):
                return True

            # Dinamički prag po oblasti prava — poresko se menja brže od ustavnog
            _DECAY_DAYS = {
                "poresko": 180, "poreski": 180, "poreski_postupak": 180,
                "radno": 365, "radni": 365,
                "procesno": 365, "gradjansko_procesno": 365,
                "upravno": 365,
                "privredno": 547,
                "obligaciono": 730, "ugovorno": 730,
                "stvarno": 730, "nasledno": 730,
                "ustavno": 1095,
            }
            oblast = (lesson.get("oblast_prava") or lesson.get("tip_spora") or "").lower()
            decay_days = _DECAY_DAYS.get(oblast, 547)  # default: 18 meseci

            is_old = False
            created_str = lesson.get("created_at", "")
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    cutoff  = datetime.now(timezone.utc) - timedelta(days=decay_days)
                    is_old  = created < cutoff
                except Exception:
                    pass

            rag_kontradikcija = False
            lecija_txt = lesson.get("lecija", "")
            if lecija_txt and len(lecija_txt) > 20:
                try:
                    from app.services.retrieve import _pretraga_praksa, _ugradi_query
                    vektor = await asyncio.to_thread(
                        lambda: _ugradi_query(f"Suprotno stanovistu: {lecija_txt[:300]}")
                    )
                    hits = await asyncio.to_thread(
                        lambda: _pretraga_praksa(vektor, top_k=5)
                    )
                    if hits and len(hits) >= 3:
                        rag_kontradikcija = True
                except Exception:
                    pass

            is_stale = is_old or rag_kontradikcija
            if is_stale:
                razlozi = []
                if is_old:              razlozi.append("starija od 18 meseci")
                if rag_kontradikcija:   razlozi.append("postoje novije presude koje joj protivrece")
                try:
                    await asyncio.to_thread(
                        lambda rz=", ".join(razlozi): supa.table("lessons_learned").update({
                            "zastarela":         True,
                            "zastarela_razlog":  rz,
                            "zastarela_at":      datetime.now(timezone.utc).isoformat(),
                        }).eq("id", lesson_id).execute()
                    )
                except Exception as e:
                    logger.debug("[LEARNING] decay update: %s", e)

            return is_stale
        except Exception as exc:
            logger.warning("[LEARNING] check_knowledge_decay greška: %s", exc)
            return False


    async def calculate_impact_report(self, user_id: str) -> dict:
        """
        Meri stvarni uticaj AI sistema na rad kancelarije.
        Metrike: prihvacenost preporuka, potvrdjene lekcije, win rate.
        """
        supa = _get_supa()
        from datetime import datetime, timezone, timedelta

        period_do   = datetime.now(timezone.utc)
        period_od   = period_do - timedelta(days=180)
        period_od_s = period_od.date().isoformat()
        period_do_s = period_do.date().isoformat()

        # Preporuke — prihvacenost
        preporuke_prihvacene = 0
        preporuke_ukupno     = 0
        try:
            r = await asyncio.to_thread(
                lambda: supa.table("recommendation_log")
                    .select("prihvacena")
                    .eq("user_id", user_id)
                    .not_.is_("prihvacena", "null")
                    .gte("created_at", period_od.isoformat())
                    .execute()
            )
            rows = r.data or []
            preporuke_ukupno     = len(rows)
            preporuke_prihvacene = sum(1 for x in rows if x.get("prihvacena"))
        except Exception:
            pass

        # Lekcije — potvrdjene vs ukupno aktivne
        lekcije_potvrdjene = 0
        lekcije_aktivne    = 0
        try:
            r = await asyncio.to_thread(
                lambda: supa.table("lessons_learned")
                    .select("status_lekcije")
                    .eq("user_id", user_id)
                    .eq("zastarela", False)
                    .execute()
            )
            for x in (r.data or []):
                lekcije_aktivne += 1
                if x.get("status_lekcije") == "usvojena_praksa":
                    lekcije_potvrdjene += 1
        except Exception:
            pass

        # Ishodi predmeta — win rate i prosecno trajanje
        predmeta_sa_ishodom  = 0
        pobede               = 0
        trajanja: list[int]  = []
        try:
            r = await asyncio.to_thread(
                lambda: supa.table("outcome_log")
                    .select("ishod,trajanje_meseci")
                    .eq("user_id", user_id)
                    .execute()
            )
            for x in (r.data or []):
                predmeta_sa_ishodom += 1
                if x.get("ishod") == "pobeda":
                    pobede += 1
                t = x.get("trajanje_meseci")
                if t and isinstance(t, (int, float)):
                    trajanja.append(t)
        except Exception:
            pass

        # Kalkulacije
        prihvacenost_pct = (
            round(preporuke_prihvacene / preporuke_ukupno * 100, 1)
            if preporuke_ukupno else None
        )
        win_rate_pct = (
            round(pobede / predmeta_sa_ishodom * 100, 1)
            if predmeta_sa_ishodom else None
        )
        avg_trajanje = (
            round(sum(trajanja) / len(trajanja), 1)
            if trajanja else None
        )

        # Benchmark ocene
        def _ocena_prihvacenosti(p):
            if p is None: return "nedovoljno_podataka"
            if p >= 60:   return "odlicno"
            if p >= 40:   return "dobro"
            return "za_unapredjenje"

        def _ocena_lekcija(potv, ukupno):
            if not ukupno: return "nedovoljno_podataka"
            r = potv / ukupno * 100
            if r >= 50:  return "odlicno"
            if r >= 25:  return "dobro"
            return "za_unapredjenje"

        # Sledeći koraci
        sledeci_koraci = []
        nepotvrdjene = lekcije_aktivne - lekcije_potvrdjene
        if nepotvrdjene > 0:
            sledeci_koraci.append(
                f"Potvrdite preostalih {nepotvrdjene} AI lekcija da biste ih pretvorili u internu praksu"
            )
        if predmeta_sa_ishodom < 5:
            sledeci_koraci.append(
                "Beležite ishode zatvorenih predmeta za tačniji impact report"
            )
        if preporuke_ukupno < 10:
            sledeci_koraci.append(
                "Prihvatite ili odbijte AI preporuke da bi sistem naučio vaše preference"
            )

        # AI uvid (kratak)
        uvid = ""
        delovi = []
        if prihvacenost_pct is not None:
            delovi.append(f"AI preporuke prihvaćene u {prihvacenost_pct}% slučajeva (od {preporuke_ukupno} ocenjenih)")
        if lekcije_aktivne:
            delovi.append(f"{lekcije_potvrdjene}/{lekcije_aktivne} lekcija potvrđeno od strane tima")
        if win_rate_pct is not None:
            delovi.append(f"Win rate: {win_rate_pct}% na {predmeta_sa_ishodom} predmeta")
        uvid = ". ".join(delovi) + "." if delovi else "Nema dovoljno podataka za uvid."

        return {
            "period_od":   period_od_s,
            "period_do":   period_do_s,
            "metrike": {
                "preporuke_prihvacene_procenat": prihvacenost_pct,
                "preporuke_ukupno_ocenjeno":     preporuke_ukupno,
                "lekcije_potvrdjene_n":          lekcije_potvrdjene,
                "lekcije_aktivne_n":             lekcije_aktivne,
                "predmeta_sa_ishodom":           predmeta_sa_ishodom,
                "win_rate_procenat":             win_rate_pct,
                "avg_trajanje_meseci":           avg_trajanje,
            },
            "uvid": uvid,
            "benchmark": {
                "preporuke_prihvacene_ocena": _ocena_prihvacenosti(prihvacenost_pct),
                "lekcije_potvrdjene_ocena":   _ocena_lekcija(lekcije_potvrdjene, lekcije_aktivne),
            },
            "sledeci_koraci": sledeci_koraci,
        }


# ─── Singleton ────────────────────────────────────────────────────────────────
learning = LearningEngine()
