# -*- coding: utf-8 -*-
"""
Vindex AI — 100-Question Full Test Suite
Usage:
  python run_test_100q.py           # normal run (cache enabled)
  python run_test_100q.py --no-cache  # bypass in-memory cache
"""
import sys, re, os, time, argparse
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--no-cache", action="store_true")
_args, _ = _parser.parse_known_args()
if _args.no_cache:
    os.environ["VINDEX_CACHE_BYPASS"] = "1"
    print("[RUNNER] --no-cache: live retrieval")

sys.path.insert(0, str(Path(__file__).parent))

from app.services.retrieve import _prepoznaj_zakon, _semanticka_pretraga, retrieve_documents
from main import ask_agent

OUT = Path(__file__).parent / "docs" / "VINDEX_100Q_TEST.md"
OUT.parent.mkdir(parents=True, exist_ok=True)

CAT_NAMES = {
    "KAT1": "Krivično pravo — imovinski delikti",
    "KAT2": "Krivično pravo — ostalo",
    "KAT3": "Obligaciono pravo (ZOO)",
    "KAT4": "Radno pravo",
    "KAT5": "Porodično pravo i nasleđivanje",
    "KAT6": "Privredno pravo",
    "KAT7": "Procesno pravo (ZPP)",
    "KAT8": "Zabrana konkurencije",
}

QUESTIONS = [
    # KAT1 — Krivično / imovinski (15)
    ("Koja je kazna za osnovnu krađu?", "KZ", "203", "KAT1"),
    ("Koja je kazna za tešku krađu?", "KZ", "204", "KAT1"),
    ("Šta je razbojništvo i koja je kazna?", "KZ", "206", "KAT1"),
    ("Šta je razbojnička krađa?", "KZ", "205", "KAT1"),
    ("Koja je kazna za prevaru?", "KZ", "208", "KAT1"),
    ("Šta je pronevera i koja je kazna?", "KZ", "364", "KAT1"),
    ("Koja je kazna za utaju poreza?", "KZ", "229", "KAT1"),
    ("Šta je iznuda i koja je kazna?", "KZ", "214", "KAT1"),
    ("Koja je kazna za falsifikovanje isprave?", "KZ", "355", "KAT1"),
    ("Šta je zelenaštvo?", "KZ", "216", "KAT1"),
    ("Koja je kazna za neovlašćeno korišćenje tuđeg vozila?", "KZ", "213", "KAT1"),
    ("Koja je kazna za uništenje tuđe imovine?", "KZ", "212", "KAT1"),
    ("Šta je pranje novca?", "KZ", "231", "KAT1"),
    ("Koja je kazna za utaju?", "KZ", "210", "KAT1"),
    ("Šta je sitna krađa?", "KZ", "203", "KAT1"),

    # KAT2 — Krivično / ostalo (10)
    ("Koja je kazna za vožnju u pijanom stanju?", "KZ", "289", "KAT2"),
    ("Koja je kazna za tešku telesnu povredu?", "KZ", "122", "KAT2"),
    ("Šta je krivično delo nasilja u porodici?", "KZ", "194", "KAT2"),
    ("Koja je kazna za nedozvoljeno držanje oružja?", "KZ", "348", "KAT2"),
    ("Šta je krivično delo primanja mita?", "KZ", "367", "KAT2"),
    ("Koja je kazna za davanje lažnog iskaza?", "KZ", "335", "KAT2"),
    ("Šta je krivično delo uznemiravanja?", "KZ", "138", "KAT2"),
    ("Koja je kazna za trgovinu ljudima?", "KZ", "388", "KAT2"),
    ("Šta je nužna odbrana?", "KZ", "19", "KAT2"),
    ("Koja je kazna za zapuštanje deteta?", "KZ", "193", "KAT2"),

    # KAT3 — Obligaciono pravo / ZOO (15)
    ("Koji je opšti rok zastarelosti po ZOO?", "ZOO", "371", "KAT3"),
    ("Šta je ugovorna odgovornost za štetu?", "ZOO", "262", "KAT3"),
    ("Kada nastaje pravo na raskid ugovora?", "ZOO", "124", "KAT3"),
    ("Šta je viša sila u obligacionom pravu?", "ZOO", "263", "KAT3"),
    ("Koja je kamata za docnju?", "ZOO", "277", "KAT3"),
    ("Kada se može tražiti poništaj ugovora zbog prevare?", "ZOO", "65", "KAT3"),
    ("Šta je cesija i kako se vrši?", "ZOO", "436", "KAT3"),
    ("Koja su prava kupca kod materijalnih nedostataka?", "ZOO", "488", "KAT3"),
    ("Šta je prekomerno oštećenje?", "ZOO", "139", "KAT3"),
    ("Kada nastaje obaveza naknade štete?", "ZOO", "154", "KAT3"),
    ("Šta je solidarna odgovornost?", "ZOO", "414", "KAT3"),
    ("Koji je rok zastarelosti za naknadu štete?", "ZOO", "376", "KAT3"),
    ("Šta je ugovor o zakupu?", "ZOO", "567", "KAT3"),
    ("Kada se može tražiti vraćanje datog bez osnova?", "ZOO", "210", "KAT3"),
    ("Šta je ugovor o jemstvu?", "ZOO", "997", "KAT3"),

    # KAT4 — Radno pravo (20)
    ("Koji je maksimalni otkazni rok po Zakonu o radu?", "ZR", "189", "KAT4"),
    ("Kada poslodavac može dati otkaz bez otkaznog roka?", "ZR", "179", "KAT4"),
    ("Koliko dana godišnjeg odmora ima zaposleni?", "ZR", "68", "KAT4"),
    ("Šta je mobbing i kako se dokazuje?", "ZR", "21", "KAT4"),
    ("Koja je maksimalna dužina radnog vremena?", "ZR", "50", "KAT4"),
    ("Kada se isplaćuje otpremnina?", "ZR", "119", "KAT4"),
    ("Šta su prava zaposlene žene za vreme trudnoće?", "ZR", "94", "KAT4"),
    ("Koji je rok za sudsku zaštitu kod nezakonitog otkaza?", "ZR", "195", "KAT4"),
    ("Šta je zabrana konkurencije?", "ZR", "161", "KAT4"),
    ("Kada poslodavac može uvesti prekovremeni rad?", "ZR", "53", "KAT4"),
    ("Koja su prava zaposlenog kod povrede na radu?", "ZR", "33", "KAT4"),
    ("Koji su razlozi za otkaz ugovora o radu?", "ZR", "179", "KAT4"),
    ("Šta je minimalac i kako se određuje?", "ZR", "112", "KAT4"),
    ("Koja su prava zaposlenog na bolovanju?", "ZR", "77", "KAT4"),
    ("Kada se može tražiti vraćanje na posao?", "ZR", "191", "KAT4"),
    ("Šta je kolektivni ugovor?", "ZR", "253", "KAT4"),
    ("Koja su prava sindikalnog predstavnika?", "ZR", "188", "KAT4"),
    ("Šta je probni rad i koliko traje?", "ZR", "36", "KAT4"),
    ("Kada zaposleni ima pravo na jubilarnu nagradu?", "ZR", "118", "KAT4"),
    ("Šta je disciplinska odgovornost zaposlenog?", "ZR", "179", "KAT4"),

    # KAT5 — Porodično i nasledno pravo (15)
    ("Koji su zakonski naslednici prvog naslednog reda?", "ZN", "9", "KAT5"),
    ("Šta je nužni deo u naslednom pravu?", "ZN", "39", "KAT5"),
    ("Kada se može poništiti testament?", "ZN", "80", "KAT5"),
    ("Šta je zajednička imovina supružnika?", "PZ", "171", "KAT5"),
    ("Kada se može tražiti razvod braka?", "PZ", "41", "KAT5"),
    ("Koja su prava deteta nakon razvoda?", "PZ", "61", "KAT5"),
    ("Šta je alimentacija i kako se određuje?", "PZ", "160", "KAT5"),
    ("Ko može biti staratelj?", "PZ", "127", "KAT5"),
    ("Šta je posvojenje i koji su uslovi?", "PZ", "89", "KAT5"),
    ("Koji je rok za prihvatanje nasleđa?", "ZN", "213", "KAT5"),
    ("Šta je odricanje od nasleđa?", "ZN", "216", "KAT5"),
    ("Kada dete može tražiti izdržavanje od roditelja?", "PZ", "154", "KAT5"),
    ("Šta je bračni ugovor?", "PZ", "187", "KAT5"),
    ("Kako se deli zajednička imovina pri razvodu?", "PZ", "177", "KAT5"),
    ("Šta je pravo preče kupovine između suvlasnika?", "ZOO", "194", "KAT5"),

    # KAT6 — Privredno pravo (10)
    ("Koji su osnivački akti DOO?", "ZPD", "139", "KAT6"),
    ("Šta je odgovornost direktora DOO?", "ZPD", "61", "KAT6"),
    ("Šta je postupak likvidacije DOO?", "ZPD", "524", "KAT6"),
    ("Koja su prava manjinskih akcionara?", "ZPD", "276", "KAT6"),
    ("Šta je stečajni postupak?", "ZS", "1", "KAT6"),
    ("Kada se otvara stečaj?", "ZS", "11", "KAT6"),
    ("Šta su razlučni poverioci?", "ZS", "56", "KAT6"),
    ("Koja je odgovornost osnivača DOO?", "ZPD", "18", "KAT6"),
    ("Šta je preduzetnik i koja je njegova odgovornost?", "ZPD", "83", "KAT6"),
    ("Kada nastaje obaveza revizije finansijskih izveštaja?", "ZPD", "369", "KAT6"),

    # KAT7 — Procesno pravo / ZPP (10)
    ("Koji je opšti rok za žalbu?", "ZPP", "373", "KAT7"),
    ("Kada nastaje pravosnažnost presude?", "ZPP", "364", "KAT7"),
    ("Šta je vanredna revizija?", "ZPP", "404", "KAT7"),
    ("Koji su uslovi za određivanje privremene mere?", "ZIO", "435", "KAT7"),
    ("Šta je predlog za ponavljanje postupka?", "ZPP", "426", "KAT7"),
    ("Ko snosi troškove parničnog postupka?", "ZPP", "153", "KAT7"),
    ("Šta je tužba za utvrđenje?", "ZPP", "194", "KAT7"),
    ("Kada se može tražiti obezbeđenje dokaza?", "ZPP", "274", "KAT7"),
    ("Šta je izvršna isprava?", "ZIO", "23", "KAT7"),
    ("Šta je litispendencija?", "ZPP", "298", "KAT7"),

    # KAT8 — Zabrana konkurencije (5)
    ("Koja je maksimalna dužina zabrane konkurencije?", "ZR", "161", "KAT8"),
    ("Kada zaposleni može da radi kod konkurenta?", "ZR", "161", "KAT8"),
    ("Šta je nelojalna konkurencija?", "ZZK", "1", "KAT8"),
    ("Koja je naknada za zabranu konkurencije?", "ZR", "161", "KAT8"),
    ("Šta je poslovna tajna?", "ZPD", "51", "KAT8"),
]


def _get_top3_raw(query: str) -> list[dict]:
    zakon = _prepoznaj_zakon(query)
    matches = _semanticka_pretraga(query, k=10, filter_zakon=zakon)
    if len(matches) < 3 and zakon:
        extra = _semanticka_pretraga(query, k=5, filter_zakon=None)
        seen = {m.id for m in matches}
        for m in extra:
            if m.id not in seen:
                matches.append(m)
    results = []
    for m in matches[:3]:
        meta = m.metadata or {}
        results.append({
            "law":     meta.get("law", "?"),
            "article": meta.get("article", "?"),
            "score":   round(m.score, 4),
            "text":    (meta.get("text") or "")[:100],
        })
    return results


def _extract_cited_article(response: str) -> str:
    m = re.search(r"[Čč]lan\s+(\d+[a-zA-Z]?)", response)
    return f"Član {m.group(1)}" if m else "—"


def _self_eval(result: dict, top3: list[dict], exp_law: str, exp_art: str | None) -> tuple[str, str]:
    confidence  = result.get("confidence", "UNKNOWN")
    top_article = result.get("top_article", "")
    response    = result.get("data", "")

    if confidence == "LOW":
        return "✅", f"LOW: pouzdan odmah odbio (score={result.get('top_score',0):.3f})"
    if confidence == "MEDIUM":
        if exp_art is None:
            return "⚠️", f"MEDIUM: hedged | meta-član: {top_article}"
        return "⚠️", f"MEDIUM: hedged | meta-član: {top_article} | očekivano: Član {exp_art}"
    if confidence == "HIGH":
        if exp_art is None:
            return "✅", f"HIGH: citiran {top_article}"
        art_m = re.search(r"(\d+[a-zA-Z]?)", top_article or "")
        meta_art = art_m.group(1) if art_m else ""
        cited_in_resp = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", response)
        if exp_art == meta_art or exp_art in cited_in_resp:
            return "✅", f"HIGH: tačan član {exp_art} citiran"
        return "❌", f"HIGH + POGREŠAN ČLAN: meta={top_article} citiran={cited_in_resp} očekivano=Član {exp_art}"
    return "⚠️", f"Nepoznata pouzdanost ({confidence})"


def run_tests():
    lines = []
    lines.append("# VINDEX 100Q TEST\n\n")
    cache_mode = "BYPASS" if os.getenv("VINDEX_CACHE_BYPASS") == "1" else "enabled"
    lines.append(f"Datum: {time.strftime('%Y-%m-%d')} | Cache: {cache_mode}\n\n---\n\n")

    results_by_cat: dict[str, list] = {}
    all_evals: list[str] = []
    problems: list[dict] = []

    total = len(QUESTIONS)
    for i, (q, exp_law, exp_art, cat) in enumerate(QUESTIONS, 1):
        print(f"[{i:02d}/{total}] {q[:70]}", flush=True)
        t0 = time.perf_counter()

        try:
            top3 = _get_top3_raw(q)
        except Exception as e:
            top3 = [{"law": "ERR", "article": "—", "score": 0, "text": str(e)[:80]}]

        try:
            result = ask_agent(q)
            response = result.get("data", result.get("message", "ERROR"))
        except Exception as e:
            result = {"data": f"[Greška: {e}]", "confidence": "ERROR"}
            response = result["data"]

        elapsed = time.perf_counter() - t0
        confidence_meta = result.get("confidence", "UNKNOWN")
        top_score_meta  = result.get("top_score", 0.0)
        top_art_meta    = result.get("top_article", "—")
        top_law_meta    = result.get("top_law", "—")
        ev, reason = _self_eval(result, top3, exp_law, exp_art)

        all_evals.append(ev)
        results_by_cat.setdefault(cat, []).append(ev)
        if ev in ("❌", "⚠️"):
            problems.append({"n": i, "q": q, "ev": ev, "reason": reason,
                             "cat": cat, "cited": top_art_meta, "exp": f"Član {exp_art}" if exp_art else "?"})

        lines.append(f"## Q{i}. {q}\n\n")
        lines.append(f"**Pouzdanost:** {confidence_meta} | **Score:** {top_score_meta:.4f} | **Vreme:** {elapsed:.1f}s\n\n")
        lines.append(f"**Meta:** `{top_law_meta}` | `{top_art_meta}`\n\n")
        resp_preview = response[:400].replace("\n", "  \n") if response else "—"
        lines.append(f"**Response:**\n\n```\n{resp_preview}\n```\n\n")
        lines.append(f"**Eval:** {ev} — {reason}\n\n---\n\n")

        print(f"  → {ev} | {confidence_meta} | score={top_score_meta:.3f} | {elapsed:.1f}s")
        time.sleep(0.5)

    tacno    = all_evals.count("✅")
    delim    = all_evals.count("⚠️")
    pogresno = all_evals.count("❌")

    lines.append("# SUMMARY\n\n")
    lines.append(f"**Ukupno:** {total} | ✅ {tacno} | ⚠️ {delim} | ❌ {pogresno}\n\n")
    lines.append(f"**Uspešnost:** {tacno/total*100:.1f}%\n\n")
    lines.append(f"**Halucinacije:** {'0 ✅' if pogresno == 0 else f'{pogresno} ❌'}\n\n")

    lines.append("## Po kategorijama\n\n")
    lines.append("| Kategorija | ✅ | ⚠️ | ❌ |\n|---|---|---|---|\n")
    for cat, evals in results_by_cat.items():
        t = evals.count("✅"); d = evals.count("⚠️"); p = evals.count("❌")
        lines.append(f"| {CAT_NAMES.get(cat, cat)} | {t} | {d} | {p} |\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"\n✅ Rezultati: {OUT}")
    print(f"FINAL: {tacno} USPEH | {delim} MEDIUM | {pogresno} KRITICNE GRESKE")


if __name__ == "__main__":
    run_tests()