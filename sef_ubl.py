# -*- coding: utf-8 -*-
"""
Vindex AI — sef_ubl.py

UBL 2.1 XML generator za srpski SEF (Sistem E-Faktura).
CustomizationID: urn:cen.eu:en16931:2017#compliant#urn:efaktura.mfin.gov.rs:1.0

Nema eksternih zavisnosti — koristi xml.sax.saxutils za escapovanje.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from xml.sax.saxutils import escape as _esc


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def _pdv_kategorija(pdv_stopa: float) -> str:
    """
    S = standardna stopa (20% ili 10%)
    E = oslobođeno PDV-a (paušalci, advokati koji nisu PDV obveznici)
    O = van dometa PDV-a
    """
    if pdv_stopa > 0:
        return "S"
    return "E"


def generiši_ubl_xml(
    faktura: dict,
    entries: list[dict],
    seller_pib: str,
    seller_naziv: str,
    seller_adresa: str = "",
    seller_mesto: str  = "Beograd",
    rok_placanja_dana: int = 30,
) -> bytes:
    """
    Generiše validan UBL 2.1 XML za SEF e-faktura sistem.

    Args:
        faktura:  dict iz tabele `fakture` (broj_fakture, datum_fakture, iznosi, klijent_*)
        entries:  lista dict iz tabele `billing_entries` (opis, iznos_rsd, datum)
        seller_*: podaci o advokatu / kancelariji
        rok_placanja_dana: rok plaćanja u danima od datuma fakture (default 30)

    Returns:
        UTF-8 encoded UBL XML bytes
    """
    broj        = faktura.get("broj_fakture", "000/0000")
    datum_str   = faktura.get("datum_fakture") or date.today().isoformat()
    try:
        datum_obj = date.fromisoformat(datum_str[:10])
    except ValueError:
        datum_obj = date.today()
    due_date = (datum_obj + timedelta(days=rok_placanja_dana)).isoformat()

    iznos_bez   = float(faktura.get("iznos_bez_pdv") or 0)
    pdv_iznos   = float(faktura.get("pdv_iznos") or 0)
    iznos_sa    = float(faktura.get("iznos_sa_pdv") or iznos_bez)
    pdv_stopa   = (pdv_iznos / iznos_bez * 100) if iznos_bez else 0.0
    pdv_kat     = _pdv_kategorija(pdv_stopa)

    buyer_pib   = (faktura.get("klijent_pib") or "").strip()
    buyer_naziv = _esc(faktura.get("klijent_naziv") or "")
    buyer_adresa = _esc(faktura.get("klijent_adresa") or "")

    # Lines
    lines_xml = ""
    for i, e in enumerate(entries, 1):
        iznos_e = float(e.get("iznos_rsd") or 0)
        opis_e  = _esc((e.get("opis") or "Pravna usluga")[:200])
        datum_e = e.get("datum") or datum_str
        lines_xml += f"""
  <cac:InvoiceLine>
    <cbc:ID>{i}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RSD">{_fmt(iznos_e)}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Description>{opis_e}</cbc:Description>
      <cbc:Name>Pravna usluga</cbc:Name>
      <cac:ClassifiedTaxCategory>
        <cbc:ID>{pdv_kat}</cbc:ID>
        <cbc:Percent>{_fmt(pdv_stopa)}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="RSD">{_fmt(iznos_e)}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>"""

    # Buyer block
    buyer_pib_el = f"""
      <cac:PartyIdentification>
        <cbc:ID schemeID="9948">{_esc(buyer_pib)}</cbc:ID>
      </cac:PartyIdentification>""" if buyer_pib else ""

    buyer_adresa_el = f"""
      <cac:PostalAddress>
        <cbc:StreetName>{buyer_adresa}</cbc:StreetName>
        <cac:Country><cbc:IdentificationCode>RS</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>""" if buyer_adresa else ""

    seller_adresa_el = f"""
      <cac:PostalAddress>
        <cbc:StreetName>{_esc(seller_adresa)}</cbc:StreetName>
        <cbc:CityName>{_esc(seller_mesto)}</cbc:CityName>
        <cac:Country><cbc:IdentificationCode>RS</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>""" if seller_adresa else f"""
      <cac:PostalAddress>
        <cbc:CityName>{_esc(seller_mesto)}</cbc:CityName>
        <cac:Country><cbc:IdentificationCode>RS</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:efaktura.mfin.gov.rs:1.0</cbc:CustomizationID>
  <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
  <cbc:ID>{_esc(broj)}</cbc:ID>
  <cbc:IssueDate>{datum_str[:10]}</cbc:IssueDate>
  <cbc:DueDate>{due_date}</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>RSD</cbc:DocumentCurrencyCode>

  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="9948">{_esc(seller_pib)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{_esc(seller_naziv)}</cbc:Name>
      </cac:PartyName>{seller_adresa_el}
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{_esc(seller_pib)}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{_esc(seller_naziv)}</cbc:RegistrationName>
        <cbc:CompanyID>{_esc(seller_pib)}</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>

  <cac:AccountingCustomerParty>
    <cac:Party>{buyer_pib_el}
      <cac:PartyName>
        <cbc:Name>{buyer_naziv}</cbc:Name>
      </cac:PartyName>{buyer_adresa_el}
    </cac:Party>
  </cac:AccountingCustomerParty>

  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="RSD">{_fmt(pdv_iznos)}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="RSD">{_fmt(iznos_bez)}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="RSD">{_fmt(pdv_iznos)}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:ID>{pdv_kat}</cbc:ID>
        <cbc:Percent>{_fmt(pdv_stopa)}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>

  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="RSD">{_fmt(iznos_bez)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="RSD">{_fmt(iznos_bez)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="RSD">{_fmt(iznos_sa)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="RSD">{_fmt(iznos_sa)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
{lines_xml}
</Invoice>
"""
    return xml.encode("utf-8")
