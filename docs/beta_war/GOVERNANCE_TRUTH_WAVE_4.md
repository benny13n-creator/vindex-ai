# GOVERNANCE TRUTH WAVE 4 — RUNTIME INTEGRITY

---

## EXECUTIVE VERDICT

## 🟡 **YELLOW**

Centralno pitanje sprinta — *„može li zahtev zaobići governance a da sistem to ne zna?"* — imalo je
do sinoć odgovor **DA**, i to ne hipotetički. Ta rupa je zatvorena: sistem sada **zna** i **objavljuje**
da li su kontrole žive.

Ne GREEN, jer dve produkcione putanje i dalje **mogu** zaobići firewall (raw WSS voice, Cohere SDK) —
sada eksplicitno enumerisane umesto pretpostavljene. Ne RED, jer nijedna od njih nije bez ijedne
kontrole i nijedna nije nevidljiva.

---

## BASELINE → FINAL

| | Pre | Posle |
|---|---|---|
| HEAD | `280d9226` | v. commit ispod |
| Testovi | 4138 / 1 / 0 | **4146 passed / 1 skipped / 0 failed** |
| Stablo | čisto | čisto |

Baseline je **verifikovan iznova**, ne preuzet iz izveštaja Wave 3.

---

## GLAVNI NALAZ — zastavica koja je lagala

`shared/ai_client.py` je na neuspeh uvoza SDK klasa radio:

```python
except Exception as exc:
    logger.error("... guard NIJE aktivan: %s", exc)
    _guard_patched = True     # <- tvrdi da je patch primenjen
    return
```

Posledica, merena a ne pretpostavljena:

- aplikacija se podigne **bez ijednog prompt guard-a** (83 chat putanje),
- **bez Response Firewall-a** (91 putanja, uveden u Wave 3),
- bez provenance-a i bez timeout-a,
- a jedina promenljiva koja opisuje stanje tvrdi da je sve u redu.

Wave 2 je izmerio da tu zastavicu **niko ne čita** van internog idempotency check-a. Dakle: nijedan
health check, nijedan endpoint, nijedan operater to nije mogao da razlikuje od ispravnog stanja.

Jedna promenljiva nosila je dve različite tvrdnje: *„pokušano"* i *„aktivno"*.

### Popravka

| Simbol | Značenje |
|---|---|
| `_guard_patched` | „ne pokušavaj ponovo" — idempotencija, nepromenjeno |
| `_guard_active` | **NOVO** — kontrole se stvarno izvršavaju |
| `_guard_failure_reason` | **NOVO** — razlog, jer „nije aktivno" bez razloga se ne dijagnostikuje |
| `governance_status()` | jedina javna tvrdnja |
| `/api/version.governance` | izlaže je spolja |

Izlaganje ide kroz `/api/version`, koji **već postoji** zbog P0-A i već je namenjen tvrdnjama o
identitetu ovog build-a. Nema novog endpointa i nema novog mehanizma.

Izmereno:

```
PRE  patch-a:  {'attempted': False, 'active': False, 'failure_reason': None}
POSLE patch-a: {'attempted': True,  'active': True,  'failure_reason': None}
```

---

## BYPASS INVENTORY

| ID | Fajl:linija | Razlog | Scenario | Severity | Status |
|---|---|---|---|---|---|
| BP-01 | `services/voice_orchestrator.py:242` | sirov WebSocket, ne prolazi kroz OpenAI SDK | privilegovani govor ide provajderu bez guard-a i bez `ai_forensics` reda | **HIGH** | OTVOREN — v. odluku o voice-u |
| BP-02 | `app/services/retrieve.py:1265` | drugi SDK (cohere) | `query` sa činjenicama predmeta odlazi trećem provajderu bez traga | MEDIUM | **LATENTAN** — paket nije u `requirements.txt`; zaključano testom |
| BP-03 | embeddings / audio | nemaju chat oblik | Response Firewall V1 ih ne pokriva | LOW | **NAMERNA GRANICA**, zaključana testom |

**Ovo je enumeracija, ne procena.** Tačno tri klase, svaka sa fajlom i linijom.

---

## VOICE — ODLUKA

Misija je tražila A ili B, bez trećeg. **Odluka: B — voice je isključen iz beta obima, a kapija to
fizički garantuje.**

Osnov, sve izmereno u Wave 2/3:

1. `minimum_plan='professional'` (`migrations/064:136`), a podrazumevana tarifa nove registracije je
   `basic` (`migrations/063:30`; `api.py:2498` ne postavlja `subscription_type`).
2. WS kanal je u Wave 2 dobio **tarifnu proveru koja je nedostajala** — do tada je `basic` korisnik
   imao pun pristup kanalu koji mu je na HTTP-u vraćao 403.
3. Kapija je **fail-closed**: greška pri čitanju profila zatvara kanal.
4. Kill-switch (`aktivno=false`) stoji **iznad** tarife i blokira i foundera.

Instrumentacija sirovog WSS kanala **nije rađena** i to je svesna odluka, ne propust: uvela bi
governance u kanal koji beta korisnici ne mogu ni otvoriti. Ako voice ikad uđe u betu, BP-01 postaje
P0 i mora se zatvoriti pre toga.

---

## MUTATION EVIDENCE

| Mutacija | Očekivano | Stvarno | Test |
|---|---|---|---|
| neuspeh patch-a prijavljen kao uspeh (stara rupa) | pad | **2 testa FAILED** | `test_c`, `test_ng_zastavice_nisu_ista_promenljiva` |
| `/api/version` ne objavljuje status | pad | **1 test FAILED** | `test_e` |

Uz mutacije iz Wave 3 koje i dalje važe (uklonjen poziv firewall-a, `BLOCK`→`ALLOW`, progutana
greška), ukupno **7 mutacija, sve obaraju očekivane testove.**

---

## GREŠKA KOJU JE OVAJ SPRINT SAM PROIZVEO I UHVATIO

Prva verzija `svez_modul` fixture-a resetovala je samo zastavice. Pošto je `_patch_prompt_guard`
idempotentan preko `_guard_patched`, ponovni poziv je patch-ovao **već patch-ovane klase**:
`_orig_create` je postao već-obavijen `_guarded_create`, a wrapper se ugnezdio u samog sebe.

Efekat se prelio na kasnije testove u istoj sesiji i **oborio dva nevezana testa** u
`tests/test_uploaded_doc_api.py`, koji su do tada bili zeleni.

To je tačno ono na šta misija upozorava — *„global state bez fixture cleanup-a"*. Fixture sada snima
i vraća zastavice, sačuvane originale i same metode na SDK klasama. Provereno u oba redosleda
izvršavanja.

Nalaz nije sakriven jer je bio moj.

---

## REGRESSION

**4146 passed / 1 skipped / 0 failed.** Razlika +8 u odnosu na 4138: osam novih testova životnog
ciklusa patch-a. Nijedan test nije deaktiviran, nijedan timeout povećan.

---

## PRODUCTION-UNVERIFIED

| Šta | Zašto |
|---|---|
| `/api/version` u produkciji | traži deploy; `governance.active` i `commit` mogu se potvrditi tek tada |
| Da li je `voice.aktivno` u produkcionoj bazi `true` | registry je admin-editabilan; migracija nije dokaz trenutnog stanja |
| Ponašanje firewall-a pod opterećenjem | provere su čitanja iz memorije, ali latencija nije merena |

---

## REMAINING RISKS

**P0** — nijedan otvoren.

**P1**
- BP-01: voice raw WSS može zaobići firewall. Prihvatljivo **samo dok je voice van bete.**
- Semantička provera izlaza pokriva 2 od 93 putanje. Halucinacija koja je validan JSON prolazi.
- `ESCALATE` degradacije se samo loguju — ne ulaze u `ai_forensics` ni `audit_immutable`.
- Embeddings grana patch-a nema ulazni guard ni timeout.

**P2**
- `security/data_classification.py` — nula importera.
- `tests/test_ai_fabric_governance.py:91` — lažno-pozitivan test (mock-uje `sanitize_prompt` koji u
  produkciji ne postoji).
- `secrets.json` nije u `.gitignore` (fajl ne postoji).

---

## OWNER ACTIONS

1. Deploy, pa `GET /api/version` → potvrditi `commit` i `governance.active: true`.
2. Potvrditi u bazi da je `voice.aktivno` u željenom stanju za betu.
3. Odluka koju ja ne donosim: da li neuspeh patch-a treba da **obori podizanje aplikacije** umesto da
   je samo prijavljen. To je kompromis između dostupnosti i upravljanosti — jednolinijska izmena, ali
   poslovna odluka.

---

## FINAL RECOMMENDATION

Sledeći potez nije novi governance sloj nego **produkciona verifikacija**: dok `/api/version` ne
potvrdi `commit` i `governance.active` na živom sistemu, sve tvrdnje ovog i prethodna tri sprinta
važe za repozitorijum, ne za ono što advokat koristi.
