from pathlib import Path

import pytest

from shared.db import connect, load_config

PROJECT = Path(__file__).resolve().parents[1]
DB = PROJECT / "data" / "fulfilment.duckdb"


@pytest.fixture(scope="session")
def cfg():
    return load_config(PROJECT)


@pytest.fixture(scope="session")
def con(cfg):
    if not DB.exists():
        pytest.fail(f"{DB} not found: run `python pipeline.py build` first")
    c = connect(DB, read_only=True)
    yield c
    c.close()


def scalar(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


def pytest_configure(config):
    config.addinivalue_line("markers", "outputs: checks on rendered reports (run after the report stage)")
