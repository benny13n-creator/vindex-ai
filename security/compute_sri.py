#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — security/compute_sri.py

Generiše Subresource Integrity (SRI) hasheve za CDN skripte.

Pokrenuti jednom pri svakoj promeni CDN verzije:
  python security/compute_sri.py

Izlaz: integrity="" atributi koji se dodaju u index.html

Referenca: https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
"""

import base64
import hashlib
import sys
import urllib.request

CDN_RESOURCES = [
    {
        "name": "@emailjs/browser",
        "url":  "https://cdn.jsdelivr.net/npm/@emailjs/browser@4.4.1/dist/email.min.js",
        "type": "script",
    },
    {
        "name": "html2pdf.js",
        "url":  "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js",
        "type": "script",
    },
    {
        "name": "Font Awesome CSS",
        "url":  "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css",
        "type": "stylesheet",
    },
    {
        "name": "Lucide Icons",
        "url":  "https://unpkg.com/lucide@0.469.0/dist/umd/lucide.min.js",
        "type": "script",
    },
]


def compute_sri(url: str, algorithm: str = "sha384") -> str:
    """Preuzima URL i računa SRI hash."""
    print(f"  Preuzimanje: {url[:80]}...")
    req = urllib.request.Request(url, headers={"User-Agent": "VindexAI-SRI-Checker/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()

    h = hashlib.new(algorithm)
    h.update(content)
    digest = base64.b64encode(h.digest()).decode("ascii")
    return f"{algorithm}-{digest}"


def main():
    print("=" * 70)
    print("Vindex AI — SRI Hash Generator")
    print("=" * 70)
    print()

    results = []
    errors = []

    for resource in CDN_RESOURCES:
        print(f"[{resource['type'].upper()}] {resource['name']}")
        try:
            sri = compute_sri(resource["url"])
            results.append((resource, sri))
            print(f"  integrity=\"{sri}\"")
            print()
        except Exception as e:
            errors.append((resource["name"], str(e)))
            print(f"  GREŠKA: {e}")
            print()

    if results:
        print("=" * 70)
        print("HTML atributi za index.html:")
        print("=" * 70)
        for resource, sri in results:
            tag_type = resource["type"]
            url = resource["url"]
            if tag_type == "script":
                print(f'<script src="{url}"')
                print(f'        integrity="{sri}"')
                print(f'        crossorigin="anonymous"')
                print(f'        referrerpolicy="no-referrer"')
                print(f'        defer></script>')
            else:
                print(f'<link rel="stylesheet" href="{url}"')
                print(f'      integrity="{sri}"')
                print(f'      crossorigin="anonymous"')
                print(f'      referrerpolicy="no-referrer"/>')
            print()

    if errors:
        print("GREŠKE:")
        for name, err in errors:
            print(f"  {name}: {err}")
        sys.exit(1)

    print("Svi hashevi su uspešno izračunati.")
    print("Kopirajte atribute u index.html.")


if __name__ == "__main__":
    main()
