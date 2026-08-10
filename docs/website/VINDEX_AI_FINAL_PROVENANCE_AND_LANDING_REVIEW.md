# VINDEX AI — FINALNA VERIFIKACIJA POREKLA

Stanje: `4fe22d2a`. Utvrđeno iz koda, bez pokretanja aplikacije i bez izmena.

---

## 1. IZVRŠNI NALAZ

# 🟢 A — API VRAĆA POREKLO

**Backend već šalje izvore klijentu. Frontend ih jednostavno ne prikazuje.**

Ovo je bolji ishod nego što je prethodna misija mogla da potvrdi: nedostaje **samo prikaz**,
ne i funkcionalnost.

## 2. ODGOVOR `/api/pitanje` — dokaz

Lanac: `api.py:2967` → `resp = normalizuj_rezultat(rezultat, credits_remaining=...)` → `return resp`.

U `normalizuj_rezultat` (`api.py`), uz komentar **„RAG confidence signal — šalje se klijentu
radi prikaza"**:

```python
if rezultat.get("confidence"):         resp["confidence"]        = rezultat["confidence"]
if rezultat.get("confidence_detail"):  resp["confidence_detail"] = rezultat["confidence_detail"]
if rezultat.get("izvori"):             resp["izvori"]            = rezultat["izvori"]
```

**Polja koja API vraća:** `odgovor` · `izvori` · `confidence` · `confidence_detail` ·
`credits_remaining`.

**Uslovno:** sva tri polja porekla se dodaju **samo ako ih `rezultat` sadrži**. Da li ih RAG
sloj uvek popunjava — **UNVERIFIED**, ali struktura postoji i namena je eksplicitno navedena.

## 3. STATUS POREKLA

**A — API VRAĆA POREKLO.**

Klasifikacija iz prethodne misije se time precizira sa `UNVERIFIED` na
**`API-AVAILABLE / UI-MISSING`**.

## 4. GDE SE POREKLO GUBI

Ne gubi se u backendu. Gubi se **na poslednjem koraku**:

```
dokument → retrieval → izvori u rezultatu → normalizuj_rezultat → resp["izvori"] → HTTP odgovor
                                                                                        ↓
                                                              frontend PRIMA ali NE PRIKAZUJE
```

`index.html:4025` definiše `<div id="rag-source-info" style="display:none"></div>` — prazan i
hardkodovano skriven. Jedine dve reference u `static/vindex.js` (linije 918 i 7538) **oba puta
ga skrivaju**. Nijedno mesto mu ne dodeljuje sadržaj.

**Prekid je isključivo u prikazu, u jednom fajlu.**

## 5. STREAMING ENDPOINT

`api.py:3128` — **UNVERIFIED.** Nisam stigao da uporedim njegov oblik odgovora sa ne-stream
varijantom. Streaming po prirodi otežava slanje metapodataka uz tok teksta, pa je moguće da se
razlikuje. **Proveriti pre nego što se prikaz uključi**, jer ako UI čita izvore samo iz
ne-stream odgovora, uključivanje neće raditi u stream režimu.

## 6. POSLEDICA — šta ovo menja

| Pre ove misije | Posle |
|---|---|
| „Možda poreklo ne postoji ni na backendu" | **Postoji i šalje se klijentu** |
| „Centralna teza možda nema osnov" | **Teza je tačna, prikaz nedostaje** |
| Procena posla: nepoznata | **Frontend izmena u jednom fajlu** |

Uključivanje prikaza je **mali posao** — ali **nije posao ove misije** i nije urađeno.

## 7. `landing.html` — NIJE PREGLEDAN

**Otvoreno priznanje:** deo misije koji traži forenzički pregled `landing.html` (57 KB,
korenski direktorijum, servira se na `/` preko `api.py:1478`) **nisam sproveo.** Ostao sam bez
raspoloživog konteksta u ovoj sesiji.

**Nisam dao preporuku REBUILD/REUSE/REPLACE/ENHANCE** jer bi ona bez čitanja fajla bila
nagađanje — a preporuka o sudbini postojeće strane je previše skupa da bi se pogodila.

**Šta je potrebno za taj deo:** pročitati `landing.html` u celosti, uporediti svaku tvrdnju sa
`VINDEX_AI_PUBLIC_CLAIMS.md`, oceniti tehnički kvalitet i dati jednu preporuku. To je zaseban,
kratak zadatak.

## 8. PREOSTALI BLOKATORI

| # | Blokator | Veličina |
|---|---|---|
| 1 | Prikaz izvora isključen u UI-ju | mala frontend izmena |
| 2 | Da li stream varijanta vraća izvore | provera, ne izmena |
| 3 | Da li RAG uvek popunjava `izvori` | provera nad sintetičkim predmetom |
| 4 | **`landing.html` nije pregledan** | zaseban zadatak |
| 5 | Sintetički demo predmet za snimke | nije kreiran |
