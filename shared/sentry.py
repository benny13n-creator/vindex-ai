# -*- coding: utf-8 -*-
"""
Sentry capture helper — bezbedan no-op ako sentry-sdk nije instaliran
(lokalni dev/test okruženja) ili nije inicijalizovan (SENTRY_DSN prazan).

Koristiti umesto direktnog `import sentry_sdk` u except blokovima --
izbegava ImportError u okruženjima gde paket nije instaliran (isti
defanzivni obrazac kao api.py::_setup_sentry).
"""


def capture_exception(exc: BaseException) -> None:
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
