"""NS007 — jutarnji demo za foundera (< 7 minuta): „VINDEX JE RADIO PRE NEGO ŠTO JE ADVOKAT PITAO."

Pokretanje:  python tests/ns007_demo.py            → priča korak po korak (test podaci, lažna baza, 0 mrežnih poziva)
             python tests/ns007_demo.py --json     → plus STVARNI odgovori ruta (za snimke: frontend-v2-ng/tests/ns007-demo.mjs)

Sve ide kroz PRAVU rutu `POST /api/cron/autonomy` (isti put kojim bi je okidao Render Cron), kanonski radnik, pravi
planeri i izvršioci. Zamenjen je SAMO provajder modela (na granici OpenAI SDK-a — broji se svaki poziv) i Pinecone
indeks korpusa odluka. Predmet: Marko Petrović protiv „Gradnja Invest" DOO (izmišljen radni spor).
"""
import asyncio
import json
import os
import re
import sys
import types
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns007"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

import tests.ns007_fake as f7  # noqa: E402
from tests import ns006_realni_predmet as rp  # noqa: E402
from tests import ns007_korpus as kor  # noqa: E402

TAJNA = "demo-tajna-" + "x" * 32
SPOLJNE_TABELE = {"notifications", "email_log", "viber_log", "staging_memory", "case_actions", "predmeti",
                  "predmet_dokazi", "rocista", "agent_recommendations", "billing_entries", "fakture"}


class _Odgovor:
    def __init__(self, sadrzaj):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=sadrzaj))]


def _provajder(pozivi):
    class Klijent:
        def __init__(self, *a, **kw):
            async def create(**kw2):
                tekst = kw2["messages"][-1]["content"]
                pozivi.append("praksa" if "SPORNA PITANJA PREDMETA:" in tekst else "ročište")
                if "SPORNA PITANJA PREDMETA:" in tekst:
                    k = re.findall(r"\[(ffff[^\]]+)\]", tekst)[0]
                    return _Odgovor(json.dumps({"klasifikacija": "u_prilog", "uticaj": [{"tekst": "Odluka daje prednost datumu iz dostavnice — "
                                    "podupire tvrdnju klijenta o kasnijem uručenju.", "refs": [k], "izvod": "dan uručenja utvrđen u dostavnici "
                                    "ima prednost nad datumom navedenim u samom rešenju"}], "pitanja": [{"tekst": "Da li je dostavnica potpisana "
                                    "lično od klijenta?", "refs": [k]}], "razmotriti_argument": {"da": True, "razlog": "Rok za tužbu vezati za "
                                    "datum iz dostavnice."}}, ensure_ascii=False))
                ids = re.findall(r"\[([0-9a-f-]{36})\]", tekst)
                kontr = next((i for i in ids if i.startswith("ffff")), ids[1])
                return _Odgovor(json.dumps({"pitanja": [{"tekst": "Proveriti koji je datum uručenja tačan pre ročišta.", "refs": [kontr]}],
                                            "beleske": [{"tekst": "Poneti original dostavnice na ročište.", "refs": [ids[1]]}]}, ensure_ascii=False))
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    return Klijent


def pokreni(stampaj=print, izvoz=False) -> dict:
    mp = pytest.MonkeyPatch()
    st = {"pozivi": [], "koraci": {}}
    try:
        danas = date.today()
        t = rp.tabele(danas=danas)
        t["rocista"][0].update(datum=(danas + timedelta(days=1)).isoformat(), sudnica="12")
        t["agent_recommendations"] = []
        t.setdefault("kancelarija_clanovi", [])
        k, baza = f7.pripremi(mp, t)
        kor.postavi(mp)
        from services.agent_tasks import hearing_prep as hp, precedents_radar as pr
        import workers.background_agents as ba
        import routers.autonomy as ra
        import openai
        mp.setattr(ba, "_agent_modules", lambda: [hp, pr])
        mp.setattr(openai, "AsyncOpenAI", _provajder(st["pozivi"]))
        mp.setenv("AUTONOMY_CRON_SECRET", TAJNA)
        mp.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "20")
        sat = {"n": 3}
        mp.setattr(ra, "_sada", lambda: datetime.combine(danas, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=sat["n"]))
        H = f7.zaglavlje("A")

        def ciklus():
            r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA}).json()
            sat["n"] += 1
            return r

        def spoljni_upisi(od):
            return sorted({z["tabela"] for z in baza.dnevnik[od:] if z["radnja"] in ("insert", "update", "upsert", "delete")} & SPOLJNE_TABELE)

        stampaj("VINDEX NS007 — DEMO: DOK SPAVATE")
        stampaj("Predmet: Marko Petrović protiv „Gradnja Invest“ DOO (test podaci)\n")
        roc = baza.tabele["rocista"][0]
        stampaj(f"1. PREDMET: ročište SUTRA ({roc['datum']} u {roc['vreme']}, {roc['sud']}).")
        pre = k.get("/api/workspace", headers=H).json()
        st["koraci"]["pre"] = len(pre["vindex_je_pripremio"])
        stampaj(f"2. Danas pre ciklusa — „Vindex je pripremio“: {st['koraci']['pre']} stavki. Advokat ništa ne traži.\n")

        stampaj("3. NOĆ: raspoređivač okida POST /api/cron/autonomy (ista ruta kao budući Render Cron).")
        od = len(baza.dnevnik)
        c1 = ciklus()
        st["koraci"]["c1"] = c1
        stampaj(f"   ciklus {c1['prozor']}: planirano {c1['sazetak']['planirano']}, spremno {c1['sazetak']['spremno']}, "
                f"poziva modela {len(st['pozivi'])}")
        posle = k.get("/api/workspace", headers=H).json()["vindex_je_pripremio"]
        hp_rad = next(x for x in posle if x["tip"] == "HEARING_PREP")
        st["koraci"]["hp_id"] = hp_rad["id"]
        stampaj(f"4. Vindex je SAM pripremio: „{hp_rad['naslov']}“")
        stampaj(f"5. Danas — „Vindex je pripremio“ ({len(posle)}): zašto — {hp_rad['razlog']}")
        d = k.get(f"/api/autonomy/work-items/{hp_rad['id']}", headers=H).json()
        st["koraci"]["hp_detalj"] = d
        c = d["content_json"]
        stampaj("6. OTVOREN BRIEF:")
        stampaj(f"     ročište (iz evidencije): {c['rociste']['datum']} {c['rociste']['vreme']}, {c['rociste']['sud']}, sudnica {c['rociste']['sudnica']}")
        for f in c["kljucne_cinjenice"][:3]:
            stampaj(f"     • {f['tekst']}  [{f['poreklo']}; izvor: {f['dokument_naziv'] or '—'}]")
        for x in c["ai"]["pitanja"]:
            stampaj(f"     ? {x['tekst']}  [Analiza (AI) — nije utvrđena činjenica]")
        stampaj(f"7. IZVORI: {len(d['source_refs'])} referenci iz baze (ročište, tvrdnje, dokumenti, protivrečnost, Genome v{c['predmet']['genome_verzija']}).")

        pozivi_pre = len(st["pozivi"])
        c2 = ciklus()
        st["koraci"]["c2"] = c2
        st["koraci"]["drugi_pozivi"] = len(st["pozivi"]) - pozivi_pre
        stampaj(f"\n8. Isti ciklus ponovo ({c2['prozor']}): planirano {c2['sazetak']['planirano']}, duplikata {c2['sazetak']['duplikata']}.")
        stampaj(f"9. Nov proizvod: NE. Nova naplata modela: {st['koraci']['drugi_pozivi']}.")

        od_odluke = len(baza.dnevnik)
        r = k.post(f"/api/autonomy/work-items/{hp_rad['id']}/accept", headers=H).json()
        st["koraci"]["prihvatanje"] = r
        st["koraci"]["spoljni_posle_odluke"] = spoljni_upisi(od_odluke)
        stampaj(f"\n10. Advokat PRIHVATA: status {r['status']}.")
        stampaj(f"11. Spoljni efekti: {st['koraci']['spoljni_posle_odluke'] or 'nijedan'} — nema mejla, podneska, poruke klijentu, "
                f"izmene predmeta ni promocije u memoriju znanja.")

        stampaj("\n12. Precedents Radar je pronašao novu odluku (preporuka).")
        baza.tabele["agent_recommendations"].append({
            "id": "dddd0001-0000-4000-8000-000000000001", "user_id": "uid-A", "predmet_id": rp.PA, "agent_type": "precedents_radar",
            "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"odnos": "podupire", "obrazlozenje": "Odluka o dostavi rešenja o otkazu.",
                        "odluka": {"decision_number": kor.ODLUKA, "court": "Vrhovni sud", "date": "2023-05-10"}}})
        baza.tabele["agent_recommendations"].append({
            "id": "dddd0002-0000-4000-8000-000000000002", "user_id": "uid-A", "predmet_id": rp.PA, "agent_type": "precedents_radar",
            "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"odnos": "osporava", "obrazlozenje": "x", "odluka": {"decision_number": "Rev 7777/2024", "court": "Vrhovni sud"}}})
        c3 = ciklus()
        st["koraci"]["c3"] = c3
        pi = next(x for x in k.get("/api/workspace", headers=H).json()["vindex_je_pripremio"] if x["tip"] == "PRECEDENT_IMPACT")
        st["koraci"]["pi_id"] = pi["id"]
        dpi = k.get(f"/api/autonomy/work-items/{pi['id']}", headers=H).json()
        st["koraci"]["pi_detalj"] = dpi
        z = dpi["content_json"]["izvor"]
        stampaj(f"13. Ciklus {c3['prozor']}: spremno {c3['sazetak']['spremno']} (proverena odluka); izmišljena „Rev 7777/2024“ → nijedan proizvod.")
        stampaj(f"14. Analiza uticaja: „{pi['naslov']}“ — {dpi['content_json']['ai']['uticaj'][0]['tekst']}")
        stampaj(f"15. TAČAN IZVOR: {z['broj']}, {z['sud']}, {z['datum']} — proveren u bazi odluka; izvod: "
                f"„{dpi['content_json']['ai']['uticaj'][0]['izvod_iz_odluke']}“")
        st["koraci"]["svi_radovi"] = [(x["work_type"], x["status"], x["trigger_ref"]) for x in baza.tabele["autonomy_work_items"]]
        st["koraci"]["spoljni_ukupno"] = spoljni_upisi(od)
        stampaj(f"\nUKUPNO: {len(st['pozivi'])} poziva modela za 2 pripremljena rada; spoljni efekti: {st['koraci']['spoljni_ukupno'] or 'nijedan'}.")
        stampaj("VINDEX JE RADIO PRE NEGO ŠTO JE ADVOKAT PITAO — i ništa nije izašlo napolje bez njegove odluke.")

        if izvoz:
            out = {"PA": rp.PA, "PB": rp.PB, "odgovori": {}}
            hp_id, pi_id = st["koraci"]["hp_id"], st["koraci"]["pi_id"]
            for ko in ("A", "B"):
                for put in ("/api/workspace", "/api/autonomy/work-items"):
                    r_ = k.get(put, headers=f7.zaglavlje(ko))
                    out["odgovori"][f"{ko}|GET|{put}"] = {"status": r_.status_code, "telo": r_.json()}
            for wid in (hp_id, pi_id):
                r_ = k.get(f"/api/autonomy/work-items/{wid}", headers=H)
                out["odgovori"][f"A|GET|/api/autonomy/work-items/{wid}"] = {"status": r_.status_code, "telo": r_.json()}
            r_ = k.get(f"/api/autonomy/work-items?matter_id={rp.PA}", headers=H)
            out["odgovori"][f"A|GET|/api/autonomy/work-items?matter_id={rp.PA}"] = {"status": r_.status_code, "telo": r_.json()}
            for put in (f"/api/predmeti/{rp.PA}/genome-v2/promene", f"/api/case-actions/predmeti/{rp.PA}"):
                r_ = k.get(put, headers=H)
                out["odgovori"][f"A|GET|{put}"] = {"status": r_.status_code, "telo": r_.json()}
            out["radovi"] = {"HEARING_PREP": hp_id, "PRECEDENT_IMPACT": pi_id}
            st["izvoz"] = out
        return st
    finally:
        f7.ocisti()
        mp.undo()


if __name__ == "__main__":
    izvoz = "--json" in sys.argv
    rez = pokreni(stampaj=(lambda *a: print(*a, file=sys.stderr)) if izvoz else print, izvoz=izvoz)
    if izvoz:
        print("@@" + json.dumps(rez["izvoz"], ensure_ascii=False, default=str))
