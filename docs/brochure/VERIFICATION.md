# Verifikaciona tabela — Vindex AI brošura

Svaka činjenična tvrdnja iz brošure sa izvorom i statusom.
Stanje repozitorijuma: `05f7357f`.

## UKLJUČENO — provereno iz izvora

| Tvrdnja u brošuri | Izvor / dokaz | Status |
|---|---|---|
| Unos više dokumenata odjednom | `routers/intake.py` bulk-import (≤100 redova), `routers/smart_intake.py` | VERIFIED |
| Prepoznavanje teksta iz skeniranih fajlova | intake pipeline, `awaiting_review` status za neuspeo OCR | VERIFIED (postoji; kvalitet nije meren) |
| Automatska klasifikacija dokumenta | `routers/evidence.py::klasifikuj_i_sacuvaj`, `reklasifikuj` | VERIFIED |
| Original se čuva | `predmet_dokumenti` + Storage putanja; brisanje je soft-delete (`deleted_at`) | VERIFIED |
| Strukturisan prikaz predmeta sa poreklom polja | `shared/case_context.py::context_field(value, source, owner, refresh)` | VERIFIED |
| Kontekst koristi više modula | 12 modula uvozi `shared.case_context` | VERIFIED |
| Hronologija, stranke, dokazi, rokovi kao povezani podaci | `predmet_dokazi`, `rocista`, `rokovi_lanac`, Case Genome | VERIFIED |
| Semantička pretraga | Pinecone integracija, `app/services/retrieve.py`, namespace po vlasniku | VERIFIED |
| Prepoznavanje rokova i obaveza | `services/case_pipeline.py::_step_ekstrakcija_rokova` | VERIFIED |
| Uočavanje protivrečnosti | Case Evolution / `case_intelligence_refreshed` | VERIFIED |
| Procena rizika | `_step_risk_snapshot`, health score | VERIFIED |
| Nacrti podnesaka vezani za predmet | `routers/drafting.py`, `shared/drafting_grounding.py` | VERIFIED |
| Nepromenljiva evidencija sa kriptografskim otiskom | `audit_immutable`: `prev_hash`/`entry_hash` SHA-256, `UNIQUE(prev_hash)`, `BEFORE UPDATE OR DELETE` triger | VERIFIED (DDL potvrđen upitom nad bazom) |
| 71 registrovana vrsta radnje | `shared/audit_immutable.py::AUDITABLE_ACTIONS` | VERIFIED |
| Poreklo AI odgovora (model, predmet, ID zahteva) | `shared/ai_provenance.py`, `ai_forensics`, `_capture_chat_provenance` | VERIFIED |
| Sadržaj upita/odgovora se ne upisuje u evidenciju | `ai_fabric._audit` metadata bez prompta; test 7 u `test_ai_fabric_governance.py` | VERIFIED |
| Razdvajanje podataka po korisniku/kancelariji | vlasnički predikat unutar same DB operacije; 10 nezavisnih forenzičkih prolaza (V49–V58) bez nalaza cross-tenant pristupa | VERIFIED |
| Uloge unutar kancelarije, odbijanje bez ovlašćenja | `routers/kancelarija.py::_require_firma_admin` → HTTP 403 | VERIFIED |
| Provera ulaznog sadržaja pre slanja modelu | `security/prompt_guard`, `_patch_prompt_guard`, `ai_fabric._govern_request` | VERIFIED |
| Sloj za rad sa više dobavljača postoji | `shared/ai_fabric.py`: kanonski ugovor, 3 priključka, registry, kapija | VERIFIED |
| **Taj sloj nije u produkcionom toku** | 0 produkcijskih poziva kroz `AIGateway` (mereno) | VERIFIED — i tako je i napisano u brošuri |
| Automatizovani testovi nad svakom izmenom | 3893 testa prolazi, 0 padova | VERIFIED |
| Uvodna stranica postoji, pun sajt planiran | `static/` (index, security, dpa, status, ai-disclosure) | VERIFIED |
| Razgovori sa advokatima; kontakt sa Stefanom Gojkovićem | navedeno u zadatku | PREUZETO IZ ZADATKA, označeno kao rani razgovori |

## NAMERNO IZOSTAVLJENO — nije moglo da se dokaže

| Izostavljena tvrdnja | Razlog |
|---|---|
| Tačnost, preciznost, procenat uspešnosti AI-ja | Nikad izmereno. Nijedan izlaz modela nije ocenjen nad stvarnim predmetom. |
| Ušteda vremena, brojevi produktivnosti | Nema merenja. |
| Kvalitet OCR-a i ekstrakcije | Mehanizam postoji, kvalitet nije testiran nad stvarnim dokumentima. |
| Brzina odziva, latencija | Nije mereno. |
| „Više AI modela radi zajedno" | Sloj postoji, ali nijedna funkcija ne ide kroz njega. U brošuri stoji kao „implementirano, nije u produkcionom toku". |
| Unakrsna provera između modela | Postoji samo ugovor; implementacije nema. Naveden kao plan. |
| Usklađenost sa GDPR / sertifikati | Postoje dokumenti i mehanizmi, ali nema nezavisne potvrde. Ne tvrdi se. |
| Korisnici, prihod, partneri, preporuke | Ne postoje. |
| Naplatni sloj kao proveren | 59 testova naplatnog sloja je preskočeno (nedostupna baza). Nije pominjano. |
| Glasovni unos | Postoji ruta, ali nije proveren u ovom prolazu. Izostavljeno. |

## ŠTA BI POBOLJŠALO BROŠURU

1. **Jedan stvarni predmet proveden kroz sistem**, sa sačuvanim izlazima — omogućio bi tvrdnje o kvalitetu umesto o mehanizmima.
2. **Kontakt podaci i pravni podaci firme** — nisu pronađeni u repozitorijumu, pa je poziv na kontakt ostao uopšten.
3. **Ekranski prikazi proizvoda** — brošura je trenutno tipografska; dva-tri prikaza iz aplikacije značajno bi pojačala uverljivost.
4. **Odluka o ceni** — nije pominjana jer u repozitorijumu postoji više neusaglašenih varijanti.
