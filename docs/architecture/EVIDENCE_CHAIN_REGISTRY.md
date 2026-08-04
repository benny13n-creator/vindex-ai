# Evidence Chain Registry — Program Beta (Masterprompt 002)

**Princip:** svaka AI tvrdnja mora imati traceable Evidence Chain nazad do
izvornog dokumenta/podatka. Bilo koja karika koja nedostaje = Critical.
Ovaj registar prati svaki AI-proizvedeni claim tip u platformi, njegov lanac,
i verdikt (Complete / Partial / Broken).

| # | Claim | Lanac | Verdikt | Napomena |
|---|---|---|---|---|
| 1 | Genome `snaga_predmeta_procent` | doc→GPT snaga_faktori→`compute_snaga_score()`→broj | **Complete** | Deterministički, reproducibilan, inputi vidljivi. Referentni obrazac cele misije. |
| 2 | Genome `_verifikacija.odluka` | genome→`verify_genome()` (4 provere)→UI amber-block | **Complete (advisory)** | Backend ne blokira snimanje na `require_review`, ali frontend (`static/vindex.js:17430-17490`) prikazuje ne-kolapsibilan warning block — kombinacija je end-to-end traceable u praksi. |
| 3 | Genome `heatmap` / `najslabija_tacka.kriticnost` | doc→GPT→raw izlaz | **Broken** | Nema deterministic post-processing, nema consistency check. Isti tip defekta koji je `compute_snaga_score` rešio za susedno polje, neprošireno ovde. `[PROGBETA-004]` |
| 4 | Evidence Vault `kljucne_cinjenice` | doc→GPT ekstrakcija→`_lociraj_tvrdnju` grounding→page/paragraf/offset→`snaga`→**UI tooltip** | **Complete za pronađeno (uz uslove), Partial za nepronađeno** | `snaga` sada odražava grounding status (`jaka` samo ako je NAĐENA I dužina tvrdnje u opsegu [20,100] karaktera — Olympus Faza 10 nalaz, AI Grounding + AI Quality Auditor: prekratka tvrdnja moze slucajno poklopiti, preduga tvrdnja ima neproveren "rep" van 100-karakter probe prozora). Olympus Faza 10 nalaz (AI Explainability + Legal Domain Expert): backend-tačan podatak ranije NIJE bio surfacovan u UI (samo obojena tačka, bez tooltip-a) i "jaka" je rizikovala da bude čitana kao opšta pravna dokazna snaga — OBA nalaza adresirana ovom misijom: dodat `title` tooltip (`static/vindex.js`) koji prikazuje stranicu I eksplicitno ograničava značenje ("potvrđuje tačnost citata, ne opštu dokaznu snagu"). |
| 5 | Evidence Vault `tip_dokaza`/`pravni_elementi` | doc→GPT klasifikacija→upis | **Broken** | Nema grounding provere uopšte (za razliku od #4) — model može vratiti tip/element bez osnove u tekstu i ništa to ne hvata. Sistemski kandidat postoji (`_lociraj_tvrdnju`/`quality_gate` princip), nije implementiran ovom misijom — van bounded scope-a, kandidat za budući prolaz. |
| 6 | Compare `koji_je_jaci_dokaz` / `kontradikcije` / `razlike_kljucne` | 2 dok→GPT judgment→raw izlaz | **Bio Broken, sada Partial (implementirano)** | Pre Programa Beta: nula provenance, nula validacije. OD PROGRAM BETA: `case_context()` wrapping + `validate_dok_reference()` (DOK-XX mora postojati medju upoređenim, sada provereno na sva 3 DOK-XX-noseća polja — Olympus Faza 10 nalaz, AI Grounding) + simetričan UI ⚠/✓ signal (Architecture Review nalaz — pozitivna potvrda na `approve`, ne samo upozorenje). `_evidence_check` oblik normalizovan da odgovara `verify_genome()` (soft_flags/provereno_u_ms — Architecture Review). Cela provera je sada u sopstvenom fail-soft try/except (Backend Reliability nalaz — greška ovde ne sme pretvoriti uspešan AI odgovor u lažni 500). Partial (ne Complete) jer se validira samo postojanost dokumenta, ne i sadržajna tačnost tvrdnje. |
| 7 | Strategy Engine 4 procenta uspeha | opis→GPT→raw broj/prosa | **Broken** | Zero backend computation na bilo kojoj od 4 vrednosti. Najozbiljniji Evidence Chain gap u misiji. Sistemski fix dizajniran, implementacija odložena `[PROGBETA-001]`. |
| 8 | Strategy Engine zakonski citati (svih 9 endpointa) | opis→GPT→raw citat u prozi | **Broken** | Zero backend verifikacija protiv indeksiranog korpusa — čisto prompt instrukcija. Rešenje već postoji (`quality_gate`, LRE `SOURCE-n`), nije ožičeno ovde `[PROGBETA-003]`. |
| 9 | `ask_agent` (Copilot) zakonski citati | pitanje→`_direktan_fetch_clana()`→hard-refuse ili inject realan tekst | **Complete** | Najjača karika u platformi — kod-nametnuta, ne prompt-only. Referentni obrazac za #7/#8. |
| 10 | `ai_analiziraj_predmet` task predlozi | DB→`_otkriveni_problemi` (deterministički)→prompt (ne-pregovaranje instrukcija)→task | **Complete za naziv/prioritet, Partial za opis** | `naziv`/`prioritet` su kod-ograničeni; slobodni `opis` tekst nije nezavisno verifikovan protiv injektovanih činjenica (nisko-rizičan — prateći tekst, ne akciona vrednost). |
| 11 | Drafting nacrt — član citati | draft tekst→`_extract_article_citations`→`_verify_citation` protiv korpusa | **Complete** | `quality_gate` proverava SVAKI citat, ne samo prvi (`asyncio.gather` batch). |
| 12 | Drafting nacrt — case-fact tačnost (ime/datum/iznos) | draft tekst→ništa | **Broken** | `_completeness_score` proverava prisustvo keyword kategorije, ne tačnost. Netačan datum bi prošao identično kao tačan. Van bounded scope-a ove misije (nije mehanizam koji već postoji negde drugde spreman za reuse — pravi novi verifikator, Phase 7 kandidat). |
| 13 | RAG retrieval izvori (svi ~15+ pozivaoci) | Pinecone match→`retrieval_meta`→**odbačeno pre `case_context()`** | **Broken (sistemski, ne per-caller)** | Podaci postoje (`izvori`, `score`), cev postoji (`retrieval_query`/`retrieved_context_ids` parametri), nikad se ne povezuju. Potvrđeno 3 nezavisna puta (Alpha + 2 Beta fork-a) isti dan. `[PROGBETA-002]` |
| 14 | Morning Briefing prose sažetak | alert lista→GPT prosa | **Partial** | Nizak rizik (courtesy tekst, ne autoritativan podatak — stvarni alert podaci su odvojeno i ispravno sačuvani preko `create_proactive_alert`), ali nema grounding proveru na slobodnom tekstu. |
| 15 | Copilot akcija handlers (`_handle_akcija_rok` i sl.) | poruka→GPT ekstrakcija (datum+vaznost)→upis u `predmet_hronologija` | **Partial** | Upisano sa `akter: "Copilot (AI)"` kao jedini izvor-marker — ne razlikuje "pročitano doslovno" od "AI zaključilo". `[PROGBETA-005]` |
| 16 | Firm Brain `confidence` (memory_entries) | ljudska potvrda→`_apply_trust`→broj | **Complete** | 100% ljudski-izvor, nikad LLM self-report. Pozitivan kontrolni primer — nije AI odluka uopšte. |

## Sažetak

- **Complete:** 5 (#1, #2 advisory, #9, #11, #16)
- **Partial:** 5 (#4 poboljšano ovom misijom, #6 poboljšano ovom misijom, #10, #14, #15)
- **Broken:** 6 (#3, #5, #7, #8, #12, #13)

**Ova misija je pomerila #4 i #6 iz Broken u Partial/Complete-advisory kroz
implementaciju.** Preostalih 6 Broken karika su dokumentovane, uzrokovane
i sistemski adresirane u dizajnu (§ AI_REASONING_PIPELINE.md), sa
implementacijom odloženom pod eksplicitno obrazloženim `PROGBETA-00X`
stavkama (§ `ARCHITECTURAL_DEBT_REGISTER.md`) gde je bounded-scope
implementacija ove sesije procenjena kao previše rizična da se ubrza (isti
standard kao Program Alpha-in SMTP presedan).

**Napomena posle Olympus Faza 10 governance revizije (2026-08-04):** Evidence
Integrity je otkrila da #4's fix čini prethodno mrtvu granu u
`services/risk_engine.py` (`"Jaka"` → `rizik_score -= 20`) dostupnom po prvi
put, bez backfill-a za postojeće `predmet_dokazi` redove — evidentirano kao
`PROGBETA-006`, namerno ne implementirano ovom misijom (migracija-oblika
posao, van obima 3 canonicalizacije). Svih 10 governance nalaza (9 obaveznih
+ Reliability & Chaos) je pregledano i primenljivi kod-nivo nalazi su
ugrađeni u implementaciju pre zatvaranja misije — vidi `MISSION_BOARD.md`.
