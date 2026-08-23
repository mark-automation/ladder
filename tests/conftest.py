import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = os.path.join(tempfile.mkdtemp(prefix="ladder-test-"), "test.db")
os.environ["LADDER_DB"] = TMP          # MUST precede importing main/db

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    import db as dbm
    conn = dbm.connect()
    dbm.init_db(conn)
    import seed as S
    S.seed(conn)
    import main
    main.conn = conn
    with TestClient(main.app) as c:
        yield c
    conn.close()


@pytest.fixture()
def api(client):
    return client
