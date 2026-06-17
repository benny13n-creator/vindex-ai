# -*- coding: utf-8 -*-
"""
Phase 3.6 — ICS / iCalendar export za rokove.
Generiše validan RFC 5545 .ics fajl sa VALARM podsetnicima.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone


def _esc(s: str) -> str:
    """RFC 5545 content-line escaping."""
    return (
        s.replace("\\", "\\\\")
         .replace(";", "\\;")
         .replace(",", "\\,")
         .replace("\n", "\\n")
         .replace("\r", "")
    )


def _vevent(naslov: str, datum: date, opis: str, dtstamp: str) -> list[str]:
    datum_str = datum.strftime("%Y%m%d")
    uid = str(uuid.uuid4())
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}@vindex.ai",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{datum_str}",
        f"DTEND;VALUE=DATE:{datum_str}",
        f"SUMMARY:{_esc(naslov)}",
        f"DESCRIPTION:{_esc(opis)}",
        "LOCATION:Vindex AI",
        "BEGIN:VALARM",
        "TRIGGER:-P7D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_esc('Podsetnik: ' + naslov + ' — 7 dana')}",
        "END:VALARM",
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_esc('HITNO: ' + naslov + ' ističe SUTRA')}",
        "END:VALARM",
        "END:VEVENT",
    ]


def generiši_ics_event(naslov: str, datum: date, opis: str = "") -> str:
    """Generiše .ics string za jedan event sa VALARM -7d i -1d."""
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Vindex AI//RS",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        *_vevent(naslov, datum, opis, dtstamp),
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


def generiši_ics_multi(eventi: list[dict]) -> str:
    """
    Generiše jedan .ics fajl sa više VEVENT blokova.
    eventi = [{"naslov": str, "datum": date, "opis": str}, ...]
    """
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Vindex AI//RS",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for e in eventi:
        lines.extend(_vevent(e["naslov"], e["datum"], e.get("opis", ""), dtstamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
