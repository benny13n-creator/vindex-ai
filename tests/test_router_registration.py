# -*- coding: utf-8 -*-
"""
Registracija rutera — provera da mrtav kod ne moze tiho da se vrati.

vindex_memory.py je uklonjen 2026-07-16 (migracija 075) jer je bio
registrovan u api.py ali ga nista nije pozivalo — nula poziva iz frontenda,
nula poziva iz ostatka backenda. Ovaj test spreci da neko slucajno vrati
import/include_router bez da ozicimo stvaran pozivalac.
"""
import os
import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
    os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
    os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
    os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
    from api import app as _app
    return _app


def test_vindex_memory_router_not_registered(app):
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    memory_paths = {p for p in paths if p.startswith("/api/memory/")}
    assert not memory_paths, (
        f"vindex_memory.py rute su se vratile bez pozivaoca: {memory_paths}. "
        "Vidi migraciju 075 — pre nego sto vratis ovaj router, ozici stvaran "
        "frontend/backend poziv, ne samo registruj ga."
    )


def test_vindex_memory_module_not_importable(app):
    with pytest.raises(ModuleNotFoundError):
        import routers.vindex_memory  # noqa: F401
