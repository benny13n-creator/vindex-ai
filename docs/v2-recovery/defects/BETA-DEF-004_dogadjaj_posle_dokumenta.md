# BETA-DEF-004 — pad upisa događaja posle upisa dokumenta ostavlja dokument trajno bez tvrdnji

**Status:** otvoren, NIJE ispravljen (granica arhitekture). Otkriven u OSB003 Task 3.
**Ozbiljnost:** srednja verovatnoća-niska / uticaj-visok (tih gubitak tvrdnji i Genome osvežavanja za JEDAN dokument).

## Šta se dešava
`routers/smart_intake.py::_finalize_intake_job_core` upisuje `predmet_dokumenti`, pa zatim, zasebnim pozivom,
`emit_durable(NEW_EVIDENCE_REGISTERED)` i `emit_durable(DOCUMENT_ACCEPTED)`. Oba emitovanja su u `try/except` koji samo
loguje upozorenje; `emit_durable` nema sopstveni retry. Ako upis događaja padne (prekid veze sa bazom između dva
upisa):
- finalizacija vraća **200**, dokument postoji i vidljiv je;
- tvrdnje se nikad ne izvlače, Genome i Case Actions se ne osvežavaju;
- ponovljena finalizacija nalazi isti sadržaj u istom predmetu (`vec_obradjen_preskocen`) i događaj **ne šalje ponovo**;
- ne postoji naknadni sweep koji traži dokumente sa tekstom a bez `klasifikovan_at`.
Isti obrazac postoji i u starom uploadu (`api.py`, `predmet_upload_auto_analyze`).

## Dokaz
`tests/test_osb003_lanac.py::test_beta_def_004_pad_upisa_dogadjaja_posle_dokumenta` opisuje sadašnje ponašanje (P).

## Zašto nije ispravljeno noćas
Svaka ispravka menja ugovor ili arhitekturu: (a) atomski upis dokumenta i događaja zahteva novu RPC funkciju/migraciju;
(b) vraćanje greške iz finalizacije menja API odgovor posle već upisanog dokumenta; (c) sweep je nova pozadinska
komponenta. Nijedno nije „minimalna ispravka već specificiranog ponašanja“.

## Najmanji predlog (čeka odobrenje)
U grani `same_case_dup` (ponovljena finalizacija istog sadržaja u istom predmetu): ako postojeći dokument ima tekst a
nema `klasifikovan_at`, ponovo emitovati `NEW_EVIDENCE_REGISTERED` za taj `dokument_id` (posledica je idempotentna
preko `klasifikovan_at`). Uz to, finalizacija treba da vrati `događaji_upisani: false` kada emitovanje padne, da V2 može
da ponudi „Pokušaj ponovo“. Bez migracije.
