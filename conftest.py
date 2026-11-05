"""
Root conftest: patch DATABASE_URL before app modules are imported.
pytest_configure fires before any test module or conftest is collected,
so the Settings singleton in config.py picks up the test value.
"""

import os


def pytest_configure(config):
    # Force test DB so any system DATABASE_URL never bleeds into tests.
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ.setdefault("POSTGRES_USER", "test")
    os.environ.setdefault("POSTGRES_PASSWORD", "test")
    os.environ.setdefault("POSTGRES_DB", "test")
