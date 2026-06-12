# vindex_web3 — Blockchain Legal Pipeline Extension

**Status: Extension modul — nije u produkcijskom API-ju**

Ovaj modul implementira Kleros v2 dispute resolution pipeline sa full pravnom analizom
za blockchain događaje. Dizajniran kao standalone servis.

## Šta radi
- `Web3LegalPipeline` — orkestruje sve faze: dispute detection → legal mapping → Kleros package
- `DisputeDetector` — detektuje tipove sporova iz blockchain evenata
- `LegalMapper` — mapira blockchain logiku na srpski pravni okvir (ZOO, ZDI)
- `KlerosAdapter` — generiše Kleros v2 evidence paket za on-chain arbitražu
- `LegalFormatter` — formatira pravne nalaze za human-readable output

## Produkcijska integracija
Produkcijski `/web3/*` endpointi koriste `web3_compliance.py` (jedan fajl, direktne OpenAI pozive).
Ovaj modul je naprednija implementacija sa Kleros integracijom — nije je zamenio.

## Kako integrisati
```python
from vindex_web3 import Web3LegalPipeline, BlockchainEvent
pipeline = Web3LegalPipeline()
result = await pipeline.process(event)
```

Integracija zahteva: zamena `/web3/*` handlera u `api.py` da koristi ovaj pipeline
umesto direktnih `web3_compliance` poziva.
