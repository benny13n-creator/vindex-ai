# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/ingest_ofac_sdn.py

F14: OFAC sankcije screening (Faza 3) — izvlači adrese digitalne imovine sa
zvanične OFAC SDN (Specially Designated Nationals) liste u lokalni JSON lookup.

Izvor (zvaničan, preuzet direktno — ne parafraziran):
  https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML
  (OFAC-ova nova Sanctions List Service platforma, lansirana 6. maja 2024;
  stari URL treasury.gov/ofac/downloads/... i stari XML namespace
  "http://www.un.org/sanctions/1.0" su deprecated od 7. maja 2024 —
  vidi ofac.treasury.gov/recent-actions/20240507_44)

XML namespace (verifikovan direktnim čitanjem fajla):
  https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML

Struktura (SDN Advanced XML data model):
  sdn:ReferenceValueSets/sdn:FeatureTypeValues/sdn:FeatureType — definiše ID
    za svaki tip "feature", uključujući "Digital Currency Address - XBT",
    "Digital Currency Address - ETH", itd. (po asset kodu).
  sdn:DistinctParties/sdn:DistinctParty/sdn:Profile/sdn:Feature — sadrži
    FeatureTypeID atribut; ako se poklapa sa "Digital Currency Address - *"
    ID-jem, sdn:FeatureVersion/sdn:VersionDetail text je sama adresa.
  Ime entiteta: Profile/Identity/Alias sa primary="true" → NamePartGroups.
  Program: Profile/Identity/../SanctionsEntry/SanctionsMeasure ili
    Profile atribut — mapira se preko ReferenceValueSets/SanctionsProgramValues.

Ovo je ČISTO deterministička ekstrakcija — nema AI poziva. Rezultat je statički
JSON lookup fajl (adresa u lowercase → {ime, programi, uid}) koji screening
endpoint učitava u memoriju.

Run: python scripts/ingest_ofac_sdn.py --input <putanja do sdn_advanced.xml>
     python scripts/ingest_ofac_sdn.py --download   (preuzima sveži fajl, ~125MB)

Osvežavanje: OFAC SDN lista se menja u realnom vremenu (dodaju/uklanjaju se
entiteti). Ovaj skript treba pokrenuti periodično (npr. nedeljno cron) da
podaci ne zastare — v1 je ručno pokretanje.
"""
import argparse
import json
import logging
import os
import sys
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_ofac_sdn")

NS = {"sdn": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"}
SOURCE_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ofac_crypto_addresses.json")

# Asset kodovi koje OFAC koristi u "Digital Currency Address - <KOD>" feature type-ovima
# (verifikovano: XBT=Bitcoin, ETH, XMR, LTC, ZEC, DASH, BTG, ETC, BSV, BCH, XVG,
# USDT, XRP, ARB, BSC, USDC, TRX, SOL — vidi FAQ 594 i recent-actions 20240507_44)
_ASSET_KOD_NAZIV = {
    "XBT": "Bitcoin", "ETH": "Ethereum", "XMR": "Monero", "LTC": "Litecoin",
    "ZEC": "Zcash", "DASH": "Dash", "BTG": "Bitcoin Gold", "ETC": "Ethereum Classic",
    "BSV": "Bitcoin SV", "BCH": "Bitcoin Cash", "XVG": "Verge", "USDT": "Tether",
    "XRP": "XRP", "ARB": "Arbitrum", "BSC": "BNB Smart Chain", "USDC": "USD Coin",
    "TRX": "Tron", "SOL": "Solana",
}


def _download(dest: str):
    import requests
    log.info("Preuzimam %s (~125MB, ovo traje nekoliko minuta)...", SOURCE_URL)
    r = requests.get(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=300, stream=True)
    r.raise_for_status()
    total = 0
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            total += len(chunk)
    log.info("Preuzeto %.1f MB → %s", total / 1024 / 1024, dest)


def _feature_type_ids(root) -> dict:
    """Vraća {FeatureTypeID: 'XBT'|'ETH'|...} za sve 'Digital Currency Address - <KOD>' tipove."""
    ids = {}
    for ft in root.findall(".//sdn:ReferenceValueSets/sdn:FeatureTypeValues/sdn:FeatureType", NS):
        text = (ft.text or "").strip()
        if text.startswith("Digital Currency Address - "):
            kod = text.replace("Digital Currency Address - ", "").strip()
            ids[ft.get("ID")] = kod
    return ids


def _sanctions_program_map(root) -> dict:
    """Vraća {ProfileID: [naziv programa, ...]}.

    VAŽNO (verifikovano direktnim čitanjem realnog XML-a, ne pretpostavka):
    SanctionsEntry elementi NISU ugnježdeni unutar DistinctParty/Profile — žive
    u posebnoj top-level sekciji na kraju dokumenta, povezani preko
    SanctionsEntry[@ProfileID] → Profile[@ID]. Naziv programa (npr. "CUBA") je
    slobodan tekst u SanctionsMeasure/Comment, i to samo za mere sa
    SanctionsTypeID="1" (referentna vrednost "Program" — SanctionsTypeID="1705"
    je npr. "Block", što NIJE naziv programa).
    """
    out: dict = {}
    for entry in root.findall(".//sdn:SanctionsEntry", NS):
        profile_id = entry.get("ProfileID")
        if not profile_id:
            continue
        for measure in entry.findall("sdn:SanctionsMeasure", NS):
            if measure.get("SanctionsTypeID") != "1":
                continue
            comment = measure.find("sdn:Comment", NS)
            naziv = (comment.text or "").strip() if comment is not None and comment.text else ""
            if naziv:
                out.setdefault(profile_id, []).append(naziv)
    return {pid: sorted(set(programi)) for pid, programi in out.items()}


def _primary_name(profile) -> str:
    """Alias sa Primary='true' → DocumentedName sa DocNameStatusID='1' ("Primary Latin"),
    ili prvi dostupan ako nema latiničnog. Ne spaja više DocumentedName varijanti
    (npr. ćirilicu/kinseki zajedno sa latinicom) u isti string."""
    identity = profile.find("sdn:Identity", NS)
    if identity is None:
        return "Nepoznat entitet"
    aliases = identity.findall("sdn:Alias", NS)
    chosen_alias = None
    for a in aliases:
        if a.get("Primary") == "true":
            chosen_alias = a
            break
    if chosen_alias is None and aliases:
        chosen_alias = aliases[0]
    if chosen_alias is None:
        return "Nepoznat entitet"

    names = chosen_alias.findall("sdn:DocumentedName", NS)
    chosen_name = None
    for n in names:
        if n.get("DocNameStatusID") == "1":
            chosen_name = n
            break
    if chosen_name is None and names:
        chosen_name = names[0]
    if chosen_name is None:
        return "Nepoznat entitet"

    parts = []
    for dp in chosen_name.findall("sdn:DocumentedNamePart/sdn:NamePartValue", NS):
        if dp.text:
            parts.append(dp.text.strip())
    return " ".join(parts) if parts else "Nepoznat entitet"


def _programs_for_profile(profile_id: str, program_map: dict) -> list:
    return program_map.get(profile_id, [])


def parse(xml_path: str) -> dict:
    log.info("Parsiram %s (može potrajati zbog veličine fajla)...", xml_path)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    ft_ids = _feature_type_ids(root)
    log.info("Pronađeno %d 'Digital Currency Address' feature tipova: %s", len(ft_ids), sorted(ft_ids.values()))
    if not ft_ids:
        raise RuntimeError("Nijedan 'Digital Currency Address' FeatureType nije pronađen — proveri XML namespace/strukturu.")

    program_map = _sanctions_program_map(root)
    log.info("Pronađeno programskih veza za %d profila.", len(program_map))

    lookup = {}
    parties = root.findall(".//sdn:DistinctParties/sdn:DistinctParty", NS)
    log.info("Skeniram %d DistinctParty zapisa...", len(parties))

    for party in parties:
        profile = party.find("sdn:Profile", NS)
        if profile is None:
            continue
        features = profile.findall("sdn:Feature", NS)
        crypto_features = [f for f in features if f.get("FeatureTypeID") in ft_ids]
        if not crypto_features:
            continue

        naziv = _primary_name(profile)
        programi = _programs_for_profile(profile.get("ID", ""), program_map)
        uid = party.get("FixedRef", "")

        for feat in crypto_features:
            kod = ft_ids[feat.get("FeatureTypeID")]
            for vd in feat.findall(".//sdn:VersionDetail", NS):
                adresa = (vd.text or "").strip()
                if not adresa:
                    continue
                lookup[adresa.lower()] = {
                    "adresa_originalna": adresa,
                    "asset": kod,
                    "asset_naziv": _ASSET_KOD_NAZIV.get(kod, kod),
                    "entitet": naziv,
                    "programi": programi,
                    "ofac_uid": uid,
                }

    log.info("Ekstraktovano %d jedinstvenih adresa digitalne imovine.", len(lookup))
    return lookup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="Putanja do već preuzetog sdn_advanced.xml")
    ap.add_argument("--download", action="store_true", help="Preuzmi sveži fajl sa OFAC servera")
    args = ap.parse_args()

    if args.download:
        tmp_path = os.path.join(os.path.dirname(OUTPUT_PATH), "_sdn_advanced_tmp.xml")
        _download(tmp_path)
        xml_path = tmp_path
    elif args.input:
        xml_path = args.input
    else:
        log.error("Moraš proslediti --input <putanja> ili --download.")
        sys.exit(1)

    lookup = parse(xml_path)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    out = {
        "izvor": "OFAC SDN Advanced List (sanctionslistservice.ofac.treas.gov)",
        "napomena": "Zvanična, javna lista Kancelarije za kontrolu strane imovine (OFAC), Ministarstvo finansija SAD.",
        "broj_adresa": len(lookup),
        "adrese": lookup,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    log.info("Sačuvano → %s (%d adresa)", OUTPUT_PATH, len(lookup))

    if args.download and os.path.exists(tmp_path):
        os.remove(tmp_path)
        log.info("Privremeni XML fajl obrisan.")


if __name__ == "__main__":
    main()
