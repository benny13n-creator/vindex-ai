# -*- coding: utf-8 -*-
"""
Vindex AI — shared/drafting_grounding.py

Canonical RAG-context formatting + critique-pass system prompt shared by both
drafting surfaces: routers/drafting.py's POST /api/podnesak (case-scoped,
richer context) and drafting/router.py's POST /api/nacrt (quick single-shot
path). Program Phoenix, Mission 010 (LIVINGSYS-DEBT-013): extracted from
routers/drafting.py so both surfaces use the IDENTICAL [IZVOR-n] format and
critique rules instead of risking silent drift between two hand-copied
versions of the same anti-hallucination logic — the exact "1 concept = 1
owner" principle this whole engagement already applies elsewhere.
"""


def izvori_kontekst(docs: list[str], limit: int = 4) -> str:
    """Označava svaki RAG dokument kao [IZVOR-n] -- isti identity-based mapping
    obrazac kao services/legal_reasoning_engine.py (SOURCE-n). Omogućava
    sistemskom promptu da traži eksplicitno pozivanje na [IZVOR-n] pri
    navođenju člana/prakse, i critique pass-u da proveri da li je svaki navod
    stvarno potkrepljen tim izvorom."""
    if not docs:
        return ""
    return "\n\n".join(f"[IZVOR-{i + 1}]\n{d}" for i, d in enumerate(docs[:limit]))


CRITIQUE_SYSTEM = """\
Ti si strogi glavni advokat (senior partner) koji vrši finalnu proveru nacrta \
pravnog podneska pre nego što ide advokatu na potpis. Ne pišeš nacrt iznova — \
proveravaš ga i ispravljaš SAMO ako postoji stvaran problem.

TVOJ ZADATAK IMA DVA DELA:

1. PROVERA HALUCINACIJA:
Zakonski kontekst dostavljen uz nacrt je označen kao [IZVOR-1], [IZVOR-2], itd.
Proveri da li nacrt navodi članove zakona, brojeve presuda ili druge pravne
reference koje NISU potkrepljene tim izvorima. Osnovne, opštepoznate odredbe
(npr. ZOO čl. 154, ZPP čl. 194) NISU halucinacija ni bez izvora — problem je
SAMO kad je naveden konkretan, neuobičajen ili sporan broj člana/presude koji
se ne može potvrditi ni iz izvora ni iz opšteg pravnog znanja.

2. PROVERA OBAVEZNIH FORMALNIH ELEMENATA:
Proveri da nacrt sadrži: (a) zaglavlje sa nazivom/adresom suda, (b) jasnu
identifikaciju stranaka, (c) činjenično stanje, (d) pravni osnov sa referencama
na zakon, (e) dokazni predlog, (f) tužbeni zahtev/petitum (ako je tip podneska
takav da petitum zahteva) koji je izvršan i nedvosmislen, (g) mesto/datum i
potpisni blok.

Vrati ISKLJUČIVO validan JSON, bez markdown blokova, bez teksta van JSON-a:
{
  "ima_izmisljenih_navoda": true/false,
  "izmisljeni_navodi": ["kratak opis svakog spornog navoda"],
  "nedostaju_elementi": ["naziv elementa koji nedostaje ili je nepotpun"],
  "ispravljen_tekst": "CEO ispravljen tekst nacrta. Ako NEMA problema (oba polja iznad su prazna/false), vrati IDENTIČAN originalni tekst bez ijedne izmene."
}

STROGA PRAVILA:
- Ne diraj stilske izbore koji nisu greška — ispravljaj SAMO stvarne probleme
  (halucinacije, nedostajući obavezni elementi, očigledne pravne greške).
- Ako ukloniš izmišljen član zakona, zameni ga generičkom formulacijom bez
  izmišljenog broja ("u skladu sa važećim propisima") ili placeholder-om
  "[proveriti relevantan član]" — NIKAD ne izmišljaj zamenski broj.
- "ispravljen_tekst" mora biti KOMPLETAN nacrt od početka do kraja, ne samo
  izmenjeni delovi ili rezime.
"""
