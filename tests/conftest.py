import pytest

from nabiz.app import create_app
from nabiz.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def client(db):
    app = create_app(db, token="")
    app.testing = True
    return app.test_client()
