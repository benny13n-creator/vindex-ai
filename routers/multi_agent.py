# -*- coding: utf-8 -*-
"""
Multi-Agent Orchestration — 6 specijalizovanih AI agenata.

POST /api/agents/run
Agenti: intake | research | drafting | litigation | billing | deadline
"""
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from shared.rate import limiter
from pydantic import BaseModel
from typing import Optional
from shared.deps import _get_supa, get_current_user, _deduct_credit, _is_founder

logger = logging.getLogger("vindex.multi_agent")
router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── Sistemski promptovi po agentu ───────────────────────────────────────────

_AGENTS: dict = {
    "intake": {
        "naziv": "Intake Agent",
        "ikona": "📥",
        "opis":  "Prima i analizira inicijalne informacije od klijenta",
        "system": """Ti si Intake Agent advokatske kancelarije u Srbiji — specijalizovan za prijem i klasifikaciju novih predmeta.

Na osnovu opisane situacije strukturiraj sledeće:

## 1. TIP PREDMETA
Odredi granu prava i konkretnu vrstu spora:
- Parnično (ZPP, Sl. gl. RS 72/2011): novčano potraživanje, naknada štete, ugovorni spor, poništaj ugovora, smetanje poseda, razvod
- Krivično (ZKP, Sl. gl. RS 72/2011): privatna tužba, oštećeni kao tužilac, krivična prijava
- Radno (Zakon o radu, Sl. gl. RS 24/2005, pročišćen 91/2023): otkaz, mobbing, neisplaćene zarade, diskriminacija
- Upravno (ZUP, Sl. gl. RS 18/2016): žalba na akt organa, ćutanje uprave, poništaj rešenja
- Porodično (Porodični zakon, Sl. gl. RS 18/2005): razvod, izdržavanje, starateljstvo, DP
- Privredno: stečaj (ZOSL Sl. gl. RS 113/2017), privredni spor, korporativno pravo (ZPD Sl. gl. RS 36/2011)
- Nepokretnosti: uknjižba, brisovna tužba, uzurpacija, ZZK (Sl. gl. RS 115/2006)
- Izvršenje (ZOIO, Sl. gl. RS 106/2015)

## 2. STRANKE
Ko je klijent, ko je suprotna strana, jesu li pravna ili fizička lica?

## 3. KLJUČNA PRAVNA PITANJA
Navedi 2-4 konkretna pravna pitanja koja predmet otvara, sa relevantnim zakonskim odredbama.

## 4. HITNOST I ROKOVI
Identifikuj da li postoje prekluzivni rokovi koji ističu (zastarelost, žalbeni rok, rok za tužbu).
- Opšti zastarni rok: 3 god. (čl. 371 ZOO, Sl. gl. RS 29/1978)
- Žalba u parnici: 15 dana (čl. 368 ZPP)
- Radni spor: tužba u roku od 60 dana od dana dostave rešenja o otkazu (čl. 195 ZR)

## 5. POTREBNA DOKUMENTACIJA
Lista dokumenata koji su neophodni za pokretanje postupka.

## 6. PREPORUKA
Prihvatiti / odbiti / zatražiti više informacija — sa jasnim obrazloženjem.
NAPOMENA: Ova analiza je okvirna i ne zamenjuje pravno mišljenje advokata.

Srpski jezik. Jasan, stručan stil.""",
    },
    "research": {
        "naziv": "Research Agent",
        "ikona": "🔍",
        "opis":  "Pretražuje relevantnu sudsku praksu i zakone",
        "system": """Ti si Research Agent — pravni analitičar specijalizovan za srpsko pravo.

DODAJ VREDNOST — ne ponavljaj ono što korisnik već zna:
Ako korisnik u zahtevu ili dokumentu citira član zakona, PROŠIRI taj citat: navedi tačan stav i tačku iz sopstvenog znanja o srpskom pravu. Ako nisi siguran za stav — navedi "čl. X (proveriti stav u aktuelnom tekstu zakona)" — nepotpuno je bolje od izmišljenog. Navedi i propise koje korisnik nije pomenuo a koji su relevantni.

⛔ PRAVILO NULTE TOLERANCIJE — OBAVEZNO PRE SVEGA OSTALOG:
Zabranjeno je navoditi ili izmišljati brojeve sudskih odluka koji nisu eksplicitno prisutni u dostavljenim izvorima iz baze.
Jedna izmišljena odluka (npr. "Rev 420/2016", "Už 1234/2018") = ceo izveštaj postaje beskoristan i štetан advokatima.
Ovo pravilo je apsolutno — nema izuzetaka.

OBAVEZAN FORMAT CITIRANJA PROPISA:
Uvek koristi SKRAĆENICE — nikada pune reči: čl. (ne "Član"), st. (ne "Stav"), t. (ne "Tačka"), Sl. gl. RS (obavezno).
Ispravno: "čl. 205 st. 1 ZUP, Sl. gl. RS 18/2016"
Neispravno: "Član 205, Stav 1" ili "**Član 205**"
Čak i u bullet listama i naslovima: "**čl. 9 st. 1 ZUP** (Načelo efikasnosti)", ne "**Član 9**".

Za dato pravno pitanje pripremi strukturiran istraživački izveštaj:

## 1. PRIMENJIVI PROPISI
Navedi precizne zakonske odredbe. Za svaku odredbu obavezno navedi:
- Tačan broj člana, STAV i TAČKU — uvek "čl. 145 st. 2 ZOO" ili "čl. 145 st. 2 t. 1 ZOO", Sl. gl. RS
- Pun naziv zakona i izvor u Sl. glasniku RS (npr. ZUP, Sl. gl. RS 18/2016)
- Materijalni zakoni (ZOO, ZR, PZ, ZPD, ZZK, ZUP...)
- Procesni zakoni (ZPP, ZKP, ZOIO, ZUSP...)
- Podzakonski akti i uredbe ako su relevantni
- Ustav RS 98/2006 ako je primenjivo

## 2. SUDSKA PRAKSA
Citiraj ISKLJUČIVO odluke i pravne stavove koji se nalaze u dostavljenim izvorima iz baze.

Ako dostavljeni izvori sadrže konkretne odluke:
→ Format: [Sud, broj odluke, godina] — kratki sadržaj pravnog shvatanja

Ako dostavljeni izvori NE sadrže konkretne odluke (čest slučaj):
→ Navedi generalni pravni standard bez broja odluke uz napomenu: "(opšti stav prakse — konkretna odluka nije dostupna u bazi)"
→ Preporuči: "Za konkretne presude pogledati: sudskapraksa.rs, paragraf.rs, ili VKS bazu odluka"

Relevantni sudovi: VKS, Apelacioni sudovi, Privredni apelacioni sud (PAS), Ustavni sud RS, ESLJP.

## 3. PRAVNI STANDARD
Koji je dominantni stav u doktrini i sudskoj praksi? Postoje li suprotna mišljenja ili neujednačena praksa?

## 4. PRAKTIČNA PRIMENA
Kako se teorija primenjuje na konkretan slučaj? Koje odredbe direktno regulišu situaciju?

## 5. RIZICI I NEODREĐENOSTI
Koja pravna pitanja su sporna ili nerazjašnjena u srpskoj praksi? Gde postoji pravna nesigurnost?

Budi precizan. Pogrešna citacija zakona je gora od opštosti. Izmišljena presuda je katastrofa.
Srpski jezik.""",
    },
    "drafting": {
        "naziv": "Drafting Agent",
        "ikona": "✍️",
        "opis":  "Generiše pravne dokumente i podneske",
        "system": """Ti si Drafting Agent — specijalizovan za pisanje pravnih dokumenata i planskih materijala prema srpskim procesnim standardima.

VRSTA ZADATKA — ODREDI PRE SVEGA OSTALOG:
(A) Sudski podnesak ili pravni akt (tužba, žalba, predlog, ugovor, odgovor na tužbu...):
    → Primeni formalne zahteve ispod. Koristiti zaglavlje sa sudom i strankama.
(B) Interni ili planski dokument (plan pripreme, checklist, memo, koraci, savet klijentu...):
    → BEZ formalnog zaglavlja suda i stranaka. Kreni odmah sa sadržajem.
    → Jasna numerisana struktura: konkretni koraci, odgovorno lice, rok za svaki korak.

Prepoznaj tip (B) po rečima: "plan", "priprema za ročište", "checklist", "koraci", "šta treba uraditi", "memo", "savet".
──────────────────────────────────────────────────────────

Pri generisanju svakog dokumenta tipa (A) primenjuj:

### FORMALNI ZAHTEVI (ZPP čl. 98-106):
- Zaglavlje: naziv suda, ime/adresa stranaka, broj predmeta ako postoji
- Predmet podneska jasno naznačen
- Taksativno navedeni dokazi koji se predlažu (čl. 106 st. 1 t. 7 ZPP)
- Vrednost predmeta spora ako je novčana (čl. 33 ZPP)
- Potpis i datum

### VRSTE DOKUMENATA I OSNOV:
- **Tužba**: čl. 192-200 ZPP — tužbeni zahtev mora biti određen i konkretan
- **Žalba na presudu**: čl. 368-384 ZPP — rok 15 dana, žalbeni razlozi čl. 373 ZPP
- **Žalba na rešenje**: čl. 395 ZPP — rok 15 dana
- **Revizija**: čl. 403-415 ZPP — rok 30 dana, vrednosni cenzus čl. 403 st. 3
- **Odgovor na tužbu**: čl. 295-296 ZPP — rok 30 dana
- **Predlog za izvršenje**: ZOIO čl. 35-52 — izvršna isprava, predmet i sredstvo izvršenja
- **Radni spor — tužba**: ZR čl. 195, rok 60 dana od dostave rešenja
- **Ugovor**: odgovarajući tip uz primenu ZOO odredbi o formi i sadržini

### JEZIČKI STANDARD:
Koristiti zvaničnu pravnu terminologiju srpskog prava. Bez kolokvijalnih izraza.

OBAVEZNO upozorenje na kraju svakog dokumenta:
"⚠️ Ovaj nacrt generisala je AI i mora ga pregledati i potpisati ovlašćeni advokat pre podnošenja sudu."

Srpski jezik.""",
    },
    "litigation": {
        "naziv": "Litigation Agent",
        "ikona": "⚔️",
        "opis":  "Napada argumentaciju i pronalazi slabosti",
        "system": """Ti si Litigation Agent — iskusni parničar koji preuzima ulogu protivničkog advokata.

ADAPTIVNI ODGOVOR — PRIMENI PRE SVEGA OSTALOG:
Fokusovano pitanje (npr. "koji dokaz nedostaje?", "šta protivnik može osporavati?", "koja je rokovna slabost?", "šanse na uspeh?"):
→ Odgovori SAMO na to — direktno, kompaktno, bez uvoda i bez nepotrebnih sekcija.

Sveobuhvatno pitanje (npr. "analiziraj predmet", "sve slabosti", "proceni predmet u celini"):
→ Tada koristi sve sekcije ispod.

Kad se pita o spornim činjenicama ili dokazima: analiziraj KONKRETNE navode iz dostavljenog dokumenta (datumi, brojevi isprava, stranke, specifične tvrdnje) — ne daji generičke pravne kategorije. Protivnik napada konkretne navode, ne apstraktne pojmove.

Sekcije ispod su tvoj analitički okvir i znanje — nisu template koji uvek moraš da odštampaš.
──────────────────────────────────────────────────────────

Bez milosti analiziraš argumentaciju i strategiju klijenta:

## 1. PROCESNE SLABOSTI
Identifikuj procesne propuste koji mogu dovesti do odbačaja ili odbijanja:
- Mesna i stvarna nadležnost suda (ZPP čl. 16-54)
- Aktivna i pasivna legitimacija stranaka
- Rokovi — zastarelost, prekluzivni rokovi
- Forma tužbe i urednost podneska (ZPP čl. 101-103)
- Litispendencija ili presuđena stvar (ZPP čl. 208 st. 2)

## 2. MATERIJALNOPRAVNE SLABOSTI
Za svaku od 3-5 identifikovanih slabosti:
- Koji zakonski uslov nije ispunjen?
- Koji dokaz nedostaje?
- Kako će protivnik to iskoristiti?

## 3. TERET DOKAZIVANJA
Ko snosi teret dokaza po konkretnoj odredbi (ZPP čl. 231)?
Šta tačno mora da se dokaže i kako?

## 4. KONTRA-ARGUMENTI
Kako ojačati poziciju klijenta? Koje dokaze pribaviti, koji svedoci su potrebni?

## 5. REALNA PROCENA ISHODA
⛔ ZABRANA: Ne navoditi procentualne šanse (npr. "40%") — bez statističkih temelja svaki procenat je dezinformacija.

Umesto toga, navedi strukturisanu procenu:

**Faktori koji idu u korist klijenta:**
(navedi 2-4 konkretna faktora sa zakonskim osnovom ili dokaznim potencijalom)

**Faktori koji idu protiv klijenta:**
(navedi 2-4 konkretna faktora — nedostajući dokazi, diskreciona ovlašćenja organa, restriktivna sudska praksa)

**Procena rizika:** Nizak / Srednji / Visok
Objasni koji faktori su presudni za ovu ocenu i kako bi analogni predmeti bili rešeni pred VKS ili nadležnim Apelacionim sudom.

## 6. PREPORUKA STRATEGIJE
Sudski postupak / nagodba / alternativno rešavanje (medijacija po ZOM, Sl. gl. RS 55/2014)?
Koji pristup daje klijentu najbolju poziciju?

Budi oštar i realan — klijent mora znati na šta računa.
Srpski jezik.""",
    },
    "billing": {
        "naziv": "Billing Agent",
        "ikona": "💰",
        "opis":  "Saveti o naplati i AKS tarifi",
        "system": """Ti si Billing Agent — specijalizovan za naplatu advokatskih usluga prema Advokatskoj tarifi Srbije.

Primenjuješ Tarifnik o nagradama i naknadama troškova za rad advokata (Sl. gl. RS 56/2025):

### TARIFNI BROJEVI — PREGLED:
- **Tar. br. 1**: Konsultacija i pravni savet — 1 bod (≈ 300 RSD)
- **Tar. br. 7**: Tužba do 450.000 RSD vrednosti spora — 12 bodova
- **Tar. br. 7**: Tužba 450.001-5.000.000 RSD — 20 bodova
- **Tar. br. 9**: Žalba na presudu — 75% nagrade za tužbu
- **Tar. br. 10**: Revizija — 100% nagrade za tužbu
- **Tar. br. 12**: Zastupanje na ročištu (parnica) — 1,5 boda za svaki sat
- **Tar. br. 13**: Odgovor na tužbu — isto kao tužba
- **Tar. br. 16**: Predlog za izvršenje — 50% nagrade za tužbu
- **Tar. br. 18**: Ugovor — 20 bodova
- **Tar. br. 20**: Pravno mišljenje — 10-20 bodova
- **Vrednost boda**: utvrđuje AKS (proverite aktuelnu vrednost)

### ANALIZA PREDMETA:
1. Identifikuj sve procesne radnje koje su preduzete ili planiraju se
2. Za svaku radnju navedi tar. br. i broj bodova
3. Izračunaj ukupnu nagradu i troškove (takse, veštačenje)
4. Identifikuj propuštenu naplatu (radnje urađene a nisu fakturisane)
5. Preporuči strategiju naplate (ugovorena nagrada / tarifa / kombinovano)

### SUDSKE TAKSE:
Primeniti Zakon o sudskim taksama (Sl. gl. RS 28/1994, 53/2010, 27/2011)
- Tužba do 500.000 RSD: taksa 1.500 RSD
- Tužba 500.001-1.000.000 RSD: 2.500 RSD
- Veće vrednosti: po tarifi

Budi konkretan sa iznosima. Srpski jezik.""",
    },
    "deadline": {
        "naziv": "Deadline Agent",
        "ikona": "⏰",
        "opis":  "Prati i upravlja procesnim rokovima",
        "system": """Ti si Deadline Agent — specijalizovan za procesne rokove srpskog prava.

Identifikuješ, objašnjavaš i upravljaš rokovima prema sledećim zakonima:

### PARNIČNI POSTUPAK (ZPP, Sl. gl. RS 72/2011):
- Odgovor na tužbu: 30 dana od dostave (čl. 295 ZPP)
- Prigovor mesne nenadležnosti: pre upuštanja u raspravljanje (čl. 20 ZPP)
- Žalba na presudu: 15 dana od dostave (čl. 368 ZPP)
- Žalba na rešenje: 15 dana od dostave (čl. 395 ZPP)
- Revizija: 30 dana od dostave drugostepene presude (čl. 410 ZPP)
- Povraćaj u pređašnje stanje: 8 dana od prestanka razloga (čl. 111 ZPP), max 6 mes.
- Predlog za ponavljanje postupka: 30 dana od saznanja za razlog (čl. 430 ZPP)

### KRIVIČNI POSTUPAK (ZKP, Sl. gl. RS 72/2011):
- Žalba na presudu: 15 dana od dostave (čl. 434 ZKP)
- Pritvor (trajanje): ročišta na svakih 30 dana (čl. 214 ZKP)
- Privatna tužba: zastarelost 3 meseca od saznanja za delo (čl. 20 ZKP)

### RADNO PRAVO (ZR, Sl. gl. RS 91/2023):
- Tužba za poništaj otkaza: 60 dana od dostave rešenja (čl. 195 ZR)
- Zastarelost potraživanja iz radnog odnosa: 3 godine (čl. 196 ZR)

### UPRAVNI POSTUPAK (ZUP, Sl. gl. RS 18/2016):
- Žalba na prvostepeno rešenje: 15 dana (čl. 147 ZUP), može biti 8 ili 30 po posebnom zakonu
- Ćutanje uprave: žalba nakon 60 dana neodlučivanja (čl. 148 ZUP)
- Upravni spor: tužba u roku 30 dana od dostave konačnog akta (čl. 18 ZUSP)

### OBLIGACIONO PRAVO — ZASTARELOST (ZOO, Sl. gl. RS 29/1978):
- Opšti zastarni rok: 10 godina (čl. 371 ZOO)
- Potraživanja iz ugovora: 3 godine od dospelosti (čl. 372 ZOO)
- Naknada štete: 3 godine od saznanja, aps. 5 godina (čl. 376 ZOO)
- Periodična potraživanja (kirija, alimentacija): 3 godine (čl. 379 ZOO)
- Potraživanja prema državi: 3 godine (čl. 380 ZOO)

### FORMAT IZVEŠTAJA:
Za svaki rok navedi:
1. Naziv roka i zakonska osnova
2. Datum početka računanja
3. Datum isteka (sa tačnim datumom)
4. Posledica propuštanja (gubitak prava / prekluzija / zastarelost)
5. Status: ✅ Na vreme | ⚠️ Upozorenje (<15 dana) | 🔴 Kritično (<7 dana) | ❌ Propušteno

Srpski jezik. Tačnost iznad svega — pogrešan rok može koštati klijenta predmeta.""",
    },
}

_ROUTER_SYSTEM = """Ti si orchestrator advokatskog AI sistema za srpsko pravo.
Na osnovu korisnikovog zahteva izaberi najprikladnijeg agenta.
Vrati SAMO JSON (bez objašnjenja): {"agent": "<id>", "razlog": "<1 rečenica>"}

Agenti i kada ih koristiti:
- intake: prijem novog klijenta, klasifikacija predmeta, analiza situacije, da li prihvatiti predmet
- research: istraživanje zakona i sudske prakse, šta kaže pravo o konkretnom pitanju
- drafting: pisanje tužbe, žalbe, ugovora, podneska, predloga, dopisa
- litigation: analiza slabosti, šanse na uspeh, kontra-argumenti, strategija odbrane
- billing: naplata, AKS tarifa, obračun troškova, propuštena naplata
- deadline: procesni rokovi, zastarelost, kada šta ističe, kalendar rokova"""


class AgentReq(BaseModel):
    agent:      Optional[str] = None  # ako None, auto-select
    task:       str
    predmet_id: Optional[str] = None
    kontekst:   Optional[str] = None


@router.get("/lista")
async def lista_agenata():
    """Vraća listu dostupnih agenata."""
    return {"agenti": [
        {"id": k, "naziv": v["naziv"], "ikona": v["ikona"], "opis": v["opis"]}
        for k, v in _AGENTS.items()
    ]}


@router.post("/run")
@limiter.limit("15/minute")
async def run_agent(req: AgentReq, request: Request, user=Depends(get_current_user)):
    """Pokreće izabrani agent ili automatski bira najprikladniji."""
    supa = _get_supa()
    uid  = user["user_id"]

    # ── Auto-selekcija agenta ────────────────────────────────────────────────
    agent_id = req.agent
    if not agent_id:
        try:
            from openai import OpenAI
            client = OpenAI()
            sel = client.chat.completions.create(
                model="gpt-4o-mini", temperature=0, max_tokens=60,
                messages=[
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user",   "content": req.task},
                ],
            )
            raw = (sel.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
            parsed = json.loads(raw)
            agent_id = parsed.get("agent", "research")
        except Exception as exc:
            logger.warning("[AGENT] auto-select greška: %s", exc)
            agent_id = "research"

    if agent_id not in _AGENTS:
        raise HTTPException(status_code=400, detail=f"Nepoznat agent: {agent_id}")

    agent_cfg = _AGENTS[agent_id]

    # ── Credit check before OpenAI (fail fast) ───────────────────────────────
    _email_early = user.get("email", "")
    if not _is_founder(_email_early):
        try:
            cr = supa.table("user_credits").select("credits_remaining").eq("user_id", uid).execute()
            if cr.data and (cr.data[0].get("credits_remaining") or 0) <= 0:
                raise HTTPException(status_code=402, detail="Nema dovoljno kredita. Dopunite nalog.")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[AGENT] credit-check greška: %s", exc)

    # ── Dohvati kontekst predmeta ────────────────────────────────────────────
    predmet_ctx = ""
    if req.predmet_id:
        try:
            pr = supa.table("predmeti").select(
                "naziv,tip,status,tuzilac,tuzeni,opis"
            ).eq("id", req.predmet_id).eq("user_id", uid).execute()
            if pr.data:
                p = pr.data[0]
                try:
                    dok_res = supa.table("predmet_dokumenti") \
                        .select("id,naziv_fajla,redni_broj,tekst_sadrzaj,velicina_kb") \
                        .eq("predmet_id", req.predmet_id) \
                        .order("redni_broj").limit(10).execute()
                    dok_rows = dok_res.data or []
                    doc_count = len(dok_rows)
                except Exception:
                    dok_rows = []
                    doc_count = 0
                try:
                    rok_data  = supa.table("rocista").select("sud,datum,status") \
                        .eq("predmet_id", req.predmet_id).order("datum").limit(5).execute()
                    rok_count = len(rok_data.data or [])
                    rok_summary = "; ".join([
                        (r.get("sud","?") + "(" + r.get("datum","")[:10] + ")")
                        for r in (rok_data.data or [])[:3]
                    ])
                except Exception:
                    rok_count = 0; rok_summary = ""
                predmet_ctx = (
                    f"\nKontekst predmeta: {p.get('naziv','?')} | Tip: {p.get('tip','?')} | "
                    f"Status: {p.get('status','?')}\n"
                    f"Tužilac: {p.get('tuzilac','?')} | Tuženi: {p.get('tuzeni','?')}\n"
                    f"Dokumenti: {doc_count} | Rokovi: {rok_count}"
                    + (f" ({rok_summary})" if rok_summary else "") + "\n"
                )
                if p.get("opis"):
                    predmet_ctx += f"Opis: {p['opis'][:400]}\n"

                # Injektuj sadrzaj dokumenata predmeta sa metapodacima
                if dok_rows:
                    # Pokusaj da ucitas i Case Genome za dodatni kontekst
                    try:
                        genome_r = supa.table("predmeti").select("case_dna") \
                            .eq("id", req.predmet_id).eq("user_id", uid).execute()
                        genome = (genome_r.data or [{}])[0].get("case_dna") or {}
                    except Exception:
                        genome = {}

                    doc_parts = []
                    for i, dok in enumerate(dok_rows[:5]):
                        rn = dok.get("redni_broj") or (i + 1)
                        naziv = dok.get("naziv_fajla", "dokument")
                        tip = dok.get("tip_dokaza") or ""
                        kb = dok.get("velicina_kb") or ""
                        tekst = (dok.get("tekst_sadrzaj") or "").strip()
                        if tekst:
                            header = f"\n[DOK-{int(rn):02d}: {naziv}"
                            if tip:
                                header += f" | Vrsta: {tip}"
                            if kb:
                                header += f" | {kb}KB"
                            header += "]"
                            doc_parts.append(
                                header + f"\n{tekst[:2500]}"
                                + ("..." if len(tekst) > 2500 else "")
                            )

                    if doc_parts:
                        predmet_ctx += (
                            "\n\nSADRZAJ DOKUMENATA PREDMETA:"
                            + "".join(doc_parts)
                            + "\n[KRAJ DOKUMENATA]\n"
                        )

                    # Dodaj Case Genome sazetak ako postoji
                    if genome and not genome.get("greska"):
                        gi = genome.get("pravna_teorija", {})
                        v = genome.get("verzija", "")
                        v_str = f" v{v}" if v else ""
                        predmet_ctx += f"\nCASE GENOME{v_str} — SINGLE SOURCE OF TRUTH:\n"
                        if gi.get("pravni_identitet"):
                            predmet_ctx += f"  Identitet: {gi['pravni_identitet']}\n"
                        if gi.get("osnov_odgovornosti"):
                            predmet_ctx += f"  Pravni osnov: {gi['osnov_odgovornosti']}\n"
                        if gi.get("uzrocna_veza"):
                            predmet_ctx += f"  Uzrocna veza: {gi['uzrocna_veza']}\n"
                        snaga = genome.get("snaga_predmeta_procent")
                        if snaga is not None:
                            predmet_ctx += f"  Snaga predmeta: {snaga}%\n"
                        sf = genome.get("snaga_faktori") or []
                        if sf:
                            predmet_ctx += "  Faktori snage: " + "; ".join(
                                f"{f.get('uticaj','')}{f.get('faktor','')}"
                                for f in sf[:4]
                            ) + "\n"
                        nt = genome.get("najslabija_tacka") or {}
                        if nt.get("rizik"):
                            predmet_ctx += f"  NAJSLABIJA TACKA [{nt.get('kriticnost','')}%]: {nt['rizik']}\n"
                            if nt.get("preporuka"):
                                predmet_ctx += f"    Preporuka: {nt['preporuka']}\n"
                        strat = genome.get("strategija") or {}
                        if strat.get("primarni_cilj"):
                            predmet_ctx += f"  Primarni cilj: {strat['primarni_cilj']}\n"
                        if strat.get("rezervni_plan"):
                            predmet_ctx += f"  Rezervni plan: {strat['rezervni_plan']}\n"
                        ned = genome.get("nedostaje") or []
                        if ned:
                            predmet_ctx += "  NEDOSTAJUCI DOKAZI: " + "; ".join(
                                f"[{n.get('hitnost','')}] {n.get('dokument','')}"
                                for n in ned[:3]
                            ) + "\n"
                        kontr = genome.get("kontradikcije") or []
                        if kontr:
                            predmet_ctx += f"  KONTRADIKCIJE ({len(kontr)}): " + "; ".join(
                                k.get("opis", "")[:80] for k in kontr[:2]
                            ) + "\n"
                        hm = genome.get("heatmap") or {}
                        if hm:
                            predmet_ctx += "  Heatmap: " + " | ".join(
                                f"{k}={hv}%" for k, hv in hm.items() if isinstance(hv, int)
                            ) + "\n"
                        predmet_ctx += "  NAPOMENA: Analiziraj konkretne dokumente. Ne izmisljaj.\n"
        except Exception as exc:
            logger.debug("[AGENT] predmet ctx greška: %s", exc)

    # ── RAG kontekst za Research + Litigation agenta ──────────────────────────
    rag_ctx = ""
    if agent_id in ("research", "litigation"):
        try:
            import asyncio as _aio
            from app.services.retrieve import retrieve_documents as _rd
            rag_query = (req.task + " " + (req.kontekst or ""))[:800]
            docs_tuple = await _aio.to_thread(_rd, rag_query, 8)
            docs = docs_tuple[0] if isinstance(docs_tuple, tuple) else docs_tuple
            if docs:
                rag_ctx = (
                    "\n\n--- IZVORI IZ PRAVNE BAZE ---\n"
                    "VAŽNO: Ovi izvori su JEDINI osnov za citiranje konkretnih odluka i brojeva presuda.\n"
                    "Ako broj presude nije u ovim izvorima — NE navoditi ga.\n\n"
                )
                for i, d in enumerate(docs[:6], 1):
                    rag_ctx += f"[Izvor {i}]\n{d[:800]}\n\n"
                rag_ctx += "--- KRAJ IZVORA ---\n"
            else:
                rag_ctx = "\n\n[NAPOMENA: Baza nije vratila relevantne izvore za ovaj upit — osloni se na opšte zakonske odredbe, bez navođenja konkretnih odluka.]\n"
        except Exception as _re:
            logger.warning("[AGENT/research] RAG greška: %s", _re)

    # ── Billing kontekst iz DB za Billing agenta ─────────────────────────────
    billing_ctx = ""
    if agent_id == "billing" and req.predmet_id:
        try:
            from datetime import datetime as _dt
            be = supa.table("billing_entries").select(
                "opis,kolicina,jedinica,cena_po_jedinici,ukupno,datum,fakturisano"
            ).eq("predmet_id", req.predmet_id).order("datum", desc=True).limit(30).execute()
            if be.data:
                ukupno_sve = sum(float(r.get("ukupno") or 0) for r in be.data)
                fakturisano = sum(float(r.get("ukupno") or 0) for r in be.data if r.get("fakturisano"))
                nefakturisano = ukupno_sve - fakturisano
                stavke = "\n".join(
                    f"- {r.get('opis','?')} | {r.get('kolicina','?')} {r.get('jedinica','?')} × {r.get('cena_po_jedinici','?')} RSD = {r.get('ukupno','?')} RSD {'[FAKTURISANO]' if r.get('fakturisano') else '[NEFAKTURISANO]'}"
                    for r in be.data[:20]
                )
                billing_ctx = (
                    f"\n\nSTVARNE BILLING STAVKE IZ PREDMETA:\n"
                    f"Ukupno naplaćeno: {ukupno_sve:,.0f} RSD | Fakturisano: {fakturisano:,.0f} RSD | Nefakturisano: {nefakturisano:,.0f} RSD\n"
                    f"{stavke}\n"
                )
        except Exception as _be:
            logger.warning("[AGENT/billing] billing ctx greška: %s", _be)

    # ── Stvarni rokovi iz predmeta za Deadline agenta ─────────────────────
    rokovi_ctx = ""
    if agent_id == "deadline" and req.predmet_id:
        try:
            from datetime import datetime, timezone as _tz
            rok_r = supa.table("rocista").select(
                "sud,datum,status,napomena"
            ).eq("predmet_id", req.predmet_id).order("datum").limit(20).execute()
            now = datetime.now(_tz.utc)
            rokovi_list = []
            for r in (rok_r.data or []):
                dt_str = r.get("datum", "")
                dana = "?"
                try:
                    dt = datetime.fromisoformat((dt_str + "T00:00:00") if len(dt_str) == 10 else dt_str.replace("Z", "+00:00"))
                    dana = (dt - now).days
                except Exception:
                    pass
                status_emoji = "✅" if r.get("status") == "zavrsen" else ("🔴" if isinstance(dana, int) and dana <= 7 else ("⚠️" if isinstance(dana, int) and dana <= 15 else "📅"))
                rokovi_list.append(
                    f"{status_emoji} {r.get('sud','?')} | Datum: {dt_str[:10]} | Dana ostalo: {dana} | Status: {r.get('status','aktivan')}"
                )
            if rokovi_list:
                rokovi_ctx = "\n\nSTVARNI ROKOVI IZ PREDMETA (analizirati ove konkretne rokove):\n" + "\n".join(rokovi_list)
        except Exception as _de:
            logger.warning("[AGENT/deadline] rokovi greška: %s", _de)

    # ── Pozovi agent ─────────────────────────────────────────────────────────
    user_msg = f"{predmet_ctx}{billing_ctx}{rokovi_ctx}{rag_ctx}\n{req.kontekst or ''}\n\nZahtev: {req.task}".strip()

    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.35,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": agent_cfg["system"]},
                {"role": "user",   "content": user_msg},
            ],
        )
        odgovor = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("[AGENT] GPT greška: %s", exc)
        raise HTTPException(status_code=503, detail="AI servis trenutno nedostupan.")

    # ── Credit deduction (founder bypass) ────────────────────────────────────
    import asyncio as _aio2
    email = user.get("email", "")
    if not _is_founder(email):
        await _aio2.to_thread(_deduct_credit, uid, email)

    logger.info("[AGENT] user=%s agent=%s predmet=%s rag=%s", uid[:8], agent_id, req.predmet_id or "-", bool(rag_ctx))

    _NEXT_AGENT = {
        "intake":    "research",
        "research":  "drafting",
        "drafting":  "litigation",
        "litigation": "billing",
        "billing":   "deadline",
        "deadline":  None,
    }

    return {
        "agent":          agent_id,
        "naziv":          agent_cfg["naziv"],
        "ikona":          agent_cfg["ikona"],
        "odgovor":        odgovor,
        "task":           req.task,
        "rag_korišćen":   bool(rag_ctx),
        "suggested_next": _NEXT_AGENT.get(agent_id),
    }


# ── Paralelna analiza — 3 agenta istovremeno ─────────────────────────────────

class ParalelnaReq(BaseModel):
    task:       str
    predmet_id: Optional[str] = None
    agenti:     Optional[list] = None  # npr. ["research","litigation","drafting"]; None = default


@router.post("/run-parallel")
@limiter.limit("5/minute")
async def run_parallel(req: ParalelnaReq, request: Request, user=Depends(get_current_user)):
    """Pokreće 3 agenta istovremeno i vraća konsolidovani izveštaj."""
    import asyncio as _aio
    from openai import AsyncOpenAI

    supa = _get_supa()
    uid  = user["user_id"]
    email = user.get("email", "")

    # Podrazumevani agenti za paralelnu analizu
    agenti_ids = req.agenti or ["research", "litigation", "intake"]
    agenti_ids = [a for a in agenti_ids if a in _AGENTS][:3]
    if not agenti_ids:
        agenti_ids = ["research", "litigation", "intake"]

    # Kredit provera — potrebno N kredita (jedan po agentu)
    n_needed = len(agenti_ids)
    if not _is_founder(email):
        try:
            cr = supa.table("user_credits").select("credits_remaining").eq("user_id", uid).execute()
            curr = (cr.data[0].get("credits_remaining") or 0) if cr.data else 0
            if curr < n_needed:
                raise HTTPException(
                    status_code=402,
                    detail=f"Paralelna analiza zahteva {n_needed} kredita. Trenutno imate {curr}.",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[PARA] credit-check greška: %s", exc)

    # Dohvati kontekst predmeta
    predmet_ctx = ""
    if req.predmet_id:
        try:
            pr = supa.table("predmeti").select(
                "naziv,tip,status,tuzilac,tuzeni,opis"
            ).eq("id", req.predmet_id).eq("user_id", uid).execute()
            if pr.data:
                p = pr.data[0]
                predmet_ctx = (
                    f"\nKontekst predmeta: {p.get('naziv','?')} | Tip: {p.get('tip','?')} | "
                    f"Status: {p.get('status','?')}\n"
                    f"Tužilac: {p.get('tuzilac','?')} | Tuženi: {p.get('tuzeni','?')}\n"
                )
                if p.get("opis"):
                    predmet_ctx += f"Opis: {p['opis'][:400]}\n"
        except Exception as exc:
            logger.debug("[PARA] predmet ctx greška: %s", exc)

    # RAG za research i litigation
    rag_ctx = ""
    if any(a in ("research", "litigation") for a in agenti_ids):
        try:
            from app.services.retrieve import retrieve_documents as _rd
            docs_tuple = await _aio.to_thread(_rd, (req.task + " " + (predmet_ctx or ""))[:800], 8)
            docs = docs_tuple[0] if isinstance(docs_tuple, tuple) else docs_tuple
            if docs:
                rag_ctx = (
                    "\n\n--- IZVORI IZ PRAVNE BAZE ---\n"
                    "VAŽNO: Ovi izvori su JEDINI osnov za citiranje konkretnih odluka i brojeva presuda.\n"
                    "Ako broj presude nije u ovim izvorima — NE navoditi ga.\n\n"
                )
                for i, d in enumerate(docs[:6], 1):
                    rag_ctx += f"[Izvor {i}]\n{d[:800]}\n\n"
                rag_ctx += "--- KRAJ IZVORA ---\n"
            else:
                rag_ctx = "\n\n[NAPOMENA: Baza nije vratila relevantne izvore — osloni se na opšte zakonske odredbe, bez navođenja konkretnih odluka.]\n"
        except Exception as _re:
            logger.warning("[PARA/rag] greška: %s", _re)

    oai = AsyncOpenAI()
    base_msg = f"{predmet_ctx}{rag_ctx}\n\nZahtev: {req.task}".strip()

    async def _pozovi_agenta(agent_id: str) -> dict:
        cfg = _AGENTS[agent_id]
        try:
            resp = await oai.chat.completions.create(
                model="gpt-4o",
                temperature=0.3,
                max_tokens=2000,
                messages=[
                    {"role": "system", "content": cfg["system"]},
                    {"role": "user",   "content": base_msg},
                ],
            )
            return {
                "agent_id": agent_id,
                "naziv":    cfg["naziv"],
                "ikona":    cfg["ikona"],
                "odgovor":  (resp.choices[0].message.content or "").strip(),
                "greska":   None,
            }
        except Exception as exc:
            logger.error("[PARA] agent=%s greška: %s", agent_id, exc)
            return {"agent_id": agent_id, "naziv": cfg["naziv"], "ikona": cfg["ikona"], "odgovor": "", "greska": str(exc)[:80]}

    # Pokreni sve agente istovremeno
    rezultati = await _aio.gather(*[_pozovi_agenta(a) for a in agenti_ids])

    # Oduzmi kredite
    if not _is_founder(email):
        for _ in range(n_needed):
            await _aio.to_thread(_deduct_credit, uid, email)

    logger.info("[PARA] uid=%s agenti=%s predmet=%s", uid[:8], agenti_ids, req.predmet_id or "-")

    return {
        "tip":     "paralelna_analiza",
        "agenti":  agenti_ids,
        "rezultati": list(rezultati),
        "task":    req.task,
    }


# ── Sekvencijalni pipeline — output jednog agenta ide kao input sledećeg ──────

class PipelineReq(BaseModel):
    predmet_id: Optional[str] = None
    opis:       str
    pipeline:   list  # npr. ["intake", "research", "drafting"]


@router.post("/pipeline")
@limiter.limit("3/minute")
async def run_pipeline(req: PipelineReq, request: Request, user=Depends(get_current_user)):
    """Sekvencijalni pipeline: output svakog agenta postaje input sledećeg."""
    import asyncio as _aio
    from fastapi import Request as _Req

    VALID = set(_AGENTS.keys())
    pipeline = [a for a in req.pipeline if a in VALID][:5]  # max 5 koraka
    if not pipeline:
        raise HTTPException(status_code=400, detail="Nevažeći pipeline — navedite validne agente.")

    supa = _get_supa()
    uid   = user["user_id"]
    email = user.get("email", "")

    # Kredit provera
    if not _is_founder(email):
        try:
            cr = supa.table("user_credits").select("credits_remaining").eq("user_id", uid).execute()
            curr = (cr.data[0].get("credits_remaining") or 0) if cr.data else 0
            if curr < len(pipeline):
                raise HTTPException(
                    status_code=402,
                    detail=f"Pipeline zahteva {len(pipeline)} kredita. Trenutno imate {curr}.",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[PIPELINE] credit-check greška: %s", exc)

    results = []
    accumulated_ctx = req.opis

    for step, agent_id in enumerate(pipeline):
        try:
            # Pozovi /run endpoint interno — reuse sva logika (RAG, billing, rokovi ctx)
            inner_req = AgentReq(
                agent=agent_id,
                task=accumulated_ctx,
                predmet_id=req.predmet_id,
                kontekst=f"[Korak {step+1}/{len(pipeline)} pipeline-a]",
            )
            result = await run_agent(inner_req, request, user)
            odgovor = result.get("odgovor", "")
            results.append({
                "korak":      step + 1,
                "agent":      agent_id,
                "naziv":      _AGENTS[agent_id]["naziv"],
                "ikona":      _AGENTS[agent_id]["ikona"],
                "output":     odgovor,
                "rag_korišćen": result.get("rag_korišćen", False),
            })
            # Akumuliraj kontekst za sledeći agent
            accumulated_ctx = (
                f"{req.opis}\n\n"
                f"[{_AGENTS[agent_id]['naziv'].upper()} — PRETHODNI KORAK]:\n{odgovor[:2000]}"
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[PIPELINE] agent=%s korak=%d greška: %s", agent_id, step+1, exc)
            results.append({
                "korak": step + 1, "agent": agent_id,
                "naziv": _AGENTS[agent_id]["naziv"], "ikona": _AGENTS[agent_id]["ikona"],
                "output": f"Greška: {str(exc)[:120]}", "greska": True,
            })
            break  # Zaustavi pipeline na grešci

    logger.info("[PIPELINE] uid=%s pipeline=%s predmet=%s koraci=%d",
                uid[:8], pipeline, req.predmet_id or "-", len(results))

    return {
        "tip":        "pipeline",
        "pipeline":   pipeline,
        "predmet_id": req.predmet_id,
        "koraci":     len(results),
        "rezultati":  results,
    }
