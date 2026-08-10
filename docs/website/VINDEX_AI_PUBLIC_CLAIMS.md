# VINDEX AI — DOZVOLJENE I ZABRANJENE JAVNE TVRDNJE

Stanje: `b29ffb6f`. Svaka tvrdnja sa dokazom iz repozitorijuma.
Ovaj fajl je obavezujući za sajt, brošuru i svaku javnu komunikaciju.

## ODOBRENE TVRDNJE — smeju se koristiti doslovno

| Tvrdnja | Dokaz |
|---|---|
| „Svako polje konteksta predmeta nosi oznaku iz kog dokumenta potiče." | `shared/case_context.py::context_field(value, source, owner, refresh)` |
| „Radnje u sistemu beleže se u evidenciju koja se ne može naknadno izmeniti ni obrisati." | `audit_immutable`: SHA-256 lanac, `UNIQUE(prev_hash)`, `BEFORE UPDATE OR DELETE` triger |
| „Za svaki AI poziv beleži se koji model je korišćen i u okviru kog predmeta." | `shared/ai_provenance.py`, `ai_forensics` |
| „Sadržaj upita i odgovora ne upisuje se u tu evidenciju." | `ai_fabric._audit`; test 7 u `test_ai_fabric_governance.py` |
| „Pripadnost svakog zapisa proverava se u samoj operaciji nad bazom." | vlasnički predikat unutar mutacije; V49–V58 |
| „Prava unutar kancelarije razdvojena su po ulogama." | `routers/kancelarija.py::_require_firma_admin` → HTTP 403 |
| „Unos više dokumenata odjednom, prepoznavanje teksta, automatska klasifikacija." | `routers/intake.py`, `smart_intake.py`, `evidence.py` |
| „Original dokumenta se čuva." | soft-delete (`deleted_at`), Storage putanja |
| „Semantička pretraga po sadržaju umesto po ključnoj reči." | Pinecone, `app/services/retrieve.py` |
| „Prepoznavanje rokova iz teksta dokumenata." | `services/case_pipeline.py::_step_ekstrakcija_rokova` |
| „Model je komponenta koju platforma koristi, a ne sam proizvod." | arhitektura `shared/ai_fabric.py` |

## USLOVNE TVRDNJE — samo uz navedenu ogradu

| Tvrdnja | Obavezna ograda |
|---|---|
| „Sloj za rad sa više dobavljača AI modela." | **mora** stajati: „implementirano; nijedna funkcija još ne ide kroz taj sloj" |
| „Uočavanje protivrečnosti između dokumenata." | „mehanizam postoji; kvalitet nije meren nad stvarnim predmetima" |
| „Izrada nacrta podnesaka." | „nacrt je polazna tačka, ne gotov podnesak" |
| „Procena rizika predmeta." | „pomoć u proceni, ne pravni savet" |
| „Više nezavisnih bezbednosnih provera." | **unutrašnjih** — nikad implicirati reviziju treće strane |
| „Testovi se izvršavaju nad svakom izmenom." | ne navoditi broj testova kao prodajni argument |

## ZABRANJENE TVRDNJE — nikada, ni u kom obliku

| Zabranjeno | Zašto |
|---|---|
| bilo koji procenat tačnosti AI-ja | nikad izmeren |
| „štedi X sati / X% vremena" | nema merenja |
| „koristimo GPT, Claude i Gemini" | produkcija koristi **jednog** dobavljača |
| „automatski bira najbolji model" | nije implementirano |
| „Vindex ima sopstveni AI model" | netačno |
| „unakrsna provera između modela" | postoji samo ugovor, bez implementacije |
| „GDPR usklađeni" / „sertifikovani" | mehanizmi postoje, nezavisne potvrde nema |
| „potpuno bezbedno" / „100% sigurno" | neodrživo |
| „vaši podaci se ne koriste za treniranje" | zavisi od ugovora sa dobavljačem — neprovereno |
| „eliminiše ljudsku grešku" | suprotno pozicioniranju |
| korisnici, klijenti, partneri, preporuke | ne postoje |
| bilo šta o kvalitetu OCR-a | nije testirano nad stvarnim dokumentima |
| bilo šta o brzini / latenciji | nije mereno |
| pominjanje cene | u repozitorijumu više neusaglašenih varijanti |
