# -*- coding: utf-8 -*-
"""
Vindex AI — shared/contradiction_identity.py

Program Sigma, Master Sprint 002 (2026-08-06) — "Autonomous Evidence & Timeline
Reconstruction Engine". ONE canonical stable-identity function for a Genome-extracted
contradiction (`case_dna.kontradikcije[]` item), used by BOTH consumers that need to
recognize "is this the SAME contradiction as before" across independent Genome
refreshes — `routers/case_dna.py::_compute_delta` and
`services/case_evolution.py::_compute_target_actions`'s own Rule 3
(`RAZRESITI_KONTRADIKCIJU`). One shared function, not two independent patches — this
sprint's own founding principle ("nije dozvoljeno pravljenje paralelnih algoritama").

## The bug this closes

Both consumers previously derived identity (a `set()` membership key in `_compute_delta`,
a `case_actions.dedupe_key` in Rule 3) from the contradiction's own free-text `opis` field
— GPT-generated prose describing what the contradiction IS, re-extracted fresh on every
Genome refresh (not a diff of the model's own prior output). Any rephrasing of the
IDENTICAL underlying contradiction between 2 refreshes produced a different `opis` string,
which:
  - made `_compute_delta` report a false "1 eliminated + 1 new" churn (SIGMA-002, Sprint 001
    Architectural Debt Register), and
  - made Rule 3's own reconcile loop (`_consequence_refresh_case_actions`) see the old
    `dedupe_key` as gone (closes that `RAZRESITI_KONTRADIKCIJU` action) and the new
    `dedupe_key` as new (creates a fresh one) — a LIVE functional bug, not just an alert-
    accuracy gap: the SAME open action would flicker closed+reopened across every Genome
    refresh, confirmed by direct code reading this sprint (`services/case_evolution.py`'s
    own `_stable_key("kontradikcija", opis, loc1, loc2)` — `opis` was part of the hash).

## The fix

Genome's own extraction prompt ALREADY REQUIRES every contradiction to carry a
`lokacija_1`/`lokacija_2` source citation (`routers/case_dna.py`'s own extraction prompt,
"DOK-XX str.Y" format) — formulaic document+page references, not free prose. As long as the
SAME 2 source locations are still in conflict, these citations are stable across refreshes
even when GPT phrases the surrounding `opis` differently. Identity is therefore anchored on
`(lokacija_1, lokacija_2)` (order-independent — GPT is not guaranteed to always cite them in
the same order), falling back to `opis` only when NEITHER location is present (a defensive
edge case Genome's own prompt is not supposed to produce, but not assumed impossible).

This does NOT touch the GPT extraction prompt/contract at all — only how the ALREADY-
extracted fields are used for downstream identity matching. Safe, deterministic, no live
model-behavior change.
"""
from __future__ import annotations

import hashlib


def contradiction_identity(k: dict) -> tuple[str, str]:
    """Returns a stable, order-independent (a, b) identity tuple for one
    `case_dna.kontradikcije[]` item. Two dicts describing the same underlying
    contradiction (same 2 source locations) produce the same tuple, regardless of
    how differently `opis` is worded between calls."""
    loc1 = (k.get("lokacija_1") or "").strip()
    loc2 = (k.get("lokacija_2") or "").strip()
    if loc1 or loc2:
        return tuple(sorted((loc1, loc2)))
    # Defensive fallback -- Genome's own prompt requires locations, but never
    # assume upstream data is always well-formed. Falls back to the free-text
    # opis (the pre-fix behavior) only for this edge case, not the common path.
    return ((k.get("opis") or "").strip(), "")


def contradiction_dedupe_key(k: dict) -> str:
    """The `case_actions.dedupe_key` for a RAZRESITI_KONTRADIKCIJU action --
    same identity as `contradiction_identity`, hashed to match every other
    `_stable_key`-derived dedupe_key's own 24-char hex shape
    (services/case_evolution.py)."""
    a, b = contradiction_identity(k)
    return hashlib.sha256(f"kontradikcija|{a}|{b}".encode("utf-8")).hexdigest()[:24]


_VALID_TEZINE = ("kriticna", "vazna", "manja")


def normalize_tezina(raw) -> str:
    """Operation Single Brain (2026-08-07), AI Boundary gap #1-2: `tezina` is a raw
    GPT classification (Genome's extraction prompt asks for exactly "kriticna|vazna|
    manja") that TWO independent consumers each mapped onward with their own silent
    "unrecognized -> middle bucket" default (`services/case_evolution.py`'s Rule 3 ->
    case_actions.prioritet, `shared/gap_engine.py` -> Gap.pouzdanost) -- neither
    validated the raw string was actually one of the 3 values GPT was asked for before
    trusting it. A GPT paraphrase or synonym for "kriticna" (e.g. "ozbiljna",
    "vrlo vazna") would silently fall through BOTH mappings to the neutral/medium
    bucket, keeping a genuinely critical contradiction out of BLOCKED readiness
    (shared/case_readiness.py requires prioritet=="high" for that path) and out of
    the "visoka" confidence gap bucket -- invisibly, not loudly.

    One canonical normalizer, used by every consumer: unrecognized input is treated
    as "kriticna" (the most conservative bucket, not the middle one) -- for a legal
    risk signal, under-flagging is the worse failure mode than over-flagging.

    Also tolerates a non-string `raw` (Phase 4 adversarial testing found `(raw or "").
    strip()` crashes outright if GPT's JSON ever puts a bare number/bool/list where a
    string was asked for -- not hypothetical for un-schema-enforced JSON output)."""
    if not isinstance(raw, str):
        return "kriticna"
    t = raw.strip().lower()
    return t if t in _VALID_TEZINE else "kriticna"


# ═══════════════════════════════════════════════════════════════════════════
# A016.7 (§9) — IDENTITET PO TVRDNJAMA, za `_compute_delta`
#
# Izmereno pre izmene: tri RAZLIČITE sporne tačke nad istim parom lokacija
# (`DOK-01 str.3` / `DOK-02 str.7`) davale su `kontr_nove = 1` umesto 3, i
# `kontr_eliminisane = 1` umesto 3. Uzrok nije bug u računanju nego preuzak
# identitet: par lokacija kaže GDE je spor, ne KOJI je spor. Jedna strana
# dokumenta lako nosi i iznos, i datum, i potpisnika.
#
# A014 je Genome-u dao `claim_refs` — reference na konkretne tvrdnje
# (`predmet_dokazi.id`), a ne na stranice. Tek to razlikuje tri spora na istoj
# strani. Zajedno sa `relation_type` to je ISTI ključ koji baza već drži
# kanonskim (`idx_contradiction_open_per_issue_relation`).
#
# SIGMA-002 se NE vraća: preformulisan `opis` nad istim tvrdnjama daje isti
# identitet, jer `opis` u ključ ne ulazi. To je i izmereno kao kontrola.
# ═══════════════════════════════════════════════════════════════════════════


def contradiction_identity_claims(k: dict):
    """Identitet izveden iz `claim_refs` + `relation_type`, ili `None`.

    `None` znači „ova stavka nema upotrebljive reference na tvrdnje" — NIJE
    greška i NIJE povod za izmišljanje zamene. Pozivalac tada bira šemu za CELO
    poređenje (vidi `_compute_delta`), umesto da meša dve šeme unutar istog
    skupa."""
    refs = k.get("claim_refs")
    if not isinstance(refs, (list, tuple)):
        return None
    ocisceni = sorted({str(r).strip() for r in refs if str(r or "").strip()})
    if len(ocisceni) < 2:
        # Jedna tvrdnja nije spor — isti prag koji `shared/issue_v2.py`
        # (`MIN_TVRDNJI`) već drži kanonskim.
        return None
    rel = (k.get("relation_type") or "").strip()
    return (rel, tuple(ocisceni))


def identitet_seme_po_tvrdnjama(*liste) -> bool:
    """Da li SVE stavke iz SVIH prosleđenih lista nose upotrebljive `claim_refs`.

    Namerno „sve, ili nijedna": Genome snimci napravljeni pre A014 nemaju
    `claim_refs`. Kad bi se dve šeme mešale unutar jednog poređenja, prvi refresh
    posle A014 prijavio bi svaku staru kontradikciju kao nestalu, a svaku novu
    kao nastalu — lažna promena od koje bi advokat dobio uzbunu bez ijedne
    stvarne izmene u predmetu. Ovako je prelaz nevidljiv.

    Prazna lista NE ulaže veto — ona ne donosi nijednu stavku, pa ni mogućnost
    mešanja. (Izmereno: dok je i prazna strana vetovala, poređenje „0 -> 3" je
    padalo natrag na identitet po lokacijama i vraćalo 1 umesto 3.)"""
    sve = [k for lst in liste for k in (lst or [])]
    return bool(sve) and all(contradiction_identity_claims(k) is not None for k in sve)


def kljucevi(stavke) -> list:
    """`[(relation_type, frozenset(claim_refs), original_dict), ...]`, sortirano.

    Determinističko sortiranje nije kozmetika: bez njega bi isti ulaz u drugom
    redosledu mogao dati drugo uparivanje, pa i drugi broj novih."""
    out = []
    for k in stavke or []:
        ident = contradiction_identity_claims(k)
        if ident is not None:
            out.append((ident[0], frozenset(ident[1]), k))
    return sorted(out, key=lambda t: (t[0], sorted(t[1])))


def uporedi_kontradikcije(stare, nove) -> tuple[int, int]:
    """Vraća `(broj_novih, broj_eliminisanih)` između dva Genome snimka.

    ## Zašto uparivanje, a ne razlika skupova

    Mandat A016.7 §9 traži dve stvari koje set-jednakost ne može istovremeno:

      - tri RAZLIČITE sporne tačke nad istim parom dokumenata = 3 NOVE;
      - postojeća sporna tačka PROŠIRENA dodatnim članom = ISTA, ne „1 nova + 1
        nestala".

    Po jednakosti skupova `{1,2}` i `{1,2,7}` su dva različita ključa, pa bi
    dodavanje trećeg dokaza postojećem sporu izgledalo kao da je stari spor
    nestao a novi se pojavio — tačno lažna promena koju A005 već jednom platio.

    Pravilo sadržavanja se ovde NE uvodi: `shared/issue_v2.py::razresi_kontinuitet`
    ga već drži kanonskim (A008). Ovo je isto pravilo primenjeno na dva snimka
    umesto na snimak i bazu — jedan koncept, jedan vlasnik.

    Uparivanje je jedan-na-jedan i determinističko (sortirano), da isti ulaz uvek
    da isti broj. Preklapanje koje NIJE sadržavanje (`{1,2}` vs `{2,3}`) se ne
    upa­ruje — to je dvosmislenost koju domen šalje na ljudski pregled, pa se ovde
    broji kao promena, a ne prećutno spaja."""
    razdvojeno = razdvoji_kontradikcije(stare, nove)
    return len(razdvojeno["nove"]), len(razdvojeno["eliminisane"])


def razdvoji_kontradikcije(stare, nove) -> dict:
    """Isto uparivanje kao `uporedi_kontradikcije`, ali vraća STAVKE.

    Postoji zato što je brojanje i biranje stavki jedan te isti posao. Dok su
    bili razdvojeni, `services/case_evolution.py` je broj računao razlikom
    dužina (`len(posle) - pre_broj`), a stavke birao pozicijom
    (`kontradikcije_posle[-N:]`) — dve nezavisne pretpostavke, obe pogrešne:
    razlika dužina prikazuje „2 nestale + 3 nove" kao 1 novu, a pozicija
    pretpostavlja da GPT nove uvek dopisuje na kraj i ne premešta ostale.

    Vraća `{"nove": [...], "eliminisane": [...]}` — originalne dict-ove, ne
    ključeve, da pozivalac ne mora da ih traži unazad."""
    st, nv = kljucevi(stare), kljucevi(nove)
    upareno_staro = [False] * len(st)
    nove_stavke = []
    for j, (rel_n, skup_n, _orig_n) in enumerate(nv):
        nasao = False
        for i, (rel_s, skup_s, _orig_s) in enumerate(st):
            if upareno_staro[i] or rel_s != rel_n:
                continue
            if skup_s <= skup_n or skup_n <= skup_s:
                upareno_staro[i] = True
                nasao = True
                break
        if not nasao:
            nove_stavke.append(nv[j][2])

    return {
        "nove": nove_stavke,
        "eliminisane": [st[i][2] for i, u in enumerate(upareno_staro) if not u],
    }


def nove_kontradikcije_za_briefing(prethodne, posle, pre_broj: int) -> tuple[int, list]:
    """`(broj_novih, stavke)` za dnevni/branju briefing.

    Postoji da bi odluka „koja je šema i koje su stavke nove" imala JEDNOG
    vlasnika. Dok je živela unutar `services/case_evolution.py`, bila je
    nemerljiva bez pune simulacije te posledice — pa je i regresija u njoj
    prolazila nezapaženo (mutacija M14 je preživela sve testove).

    `prethodne is None` znači „nema sa čim porediti" (prvi Genome, ili istorija
    nečitljiva) — tada se pada na stari put sa `pre_broj`, jer izmišljati
    poređenje koje ne postoji je gore od priznanja da ga nema."""
    posle = list(posle or [])
    if prethodne is not None and identitet_seme_po_tvrdnjama(prethodne, posle):
        razd = razdvoji_kontradikcije(prethodne, posle)
        return len(razd["nove"]), razd["nove"]
    broj = max(0, len(posle) - int(pre_broj or 0))
    return broj, (posle[-broj:] if broj else [])
