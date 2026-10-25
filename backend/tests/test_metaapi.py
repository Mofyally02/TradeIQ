import asyncio
from datetime import UTC, datetime

from app.services import metaapi
from tests.test_platform_features import make_account, register


def test_connect_requires_server_token(client, monkeypatch):
    register(client)
    account_id = make_account(client)["id"]
    monkeypatch.setattr(metaapi.get_settings(), "metaapi_token", None)
    response = client.post(
        f"/api/v1/accounts/{account_id}/metaapi/connect",
        json={"login": 1, "password": "p", "server": "S"},
    )
    assert response.status_code == 503
    assert "METAAPI_TOKEN" in response.json()["detail"]


def test_build_payload_maps_provider_data_for_ingestion():
    from uuid import uuid4

    from app.schemas import MT5SyncPayload

    now = datetime.now(UTC)
    data = metaapi.build_payload(
        uuid4(),
        {"login": 123, "balance": 1000, "equity": 1010, "margin": 5, "freeMargin": 995},
        [{"id": "9", "type": "POSITION_TYPE_BUY", "symbol": "EURUSD", "volume": 0.1,
          "openPrice": 1.1, "currentPrice": 1.2, "profit": 10}],
        [
            {"id": "1", "type": "DEAL_TYPE_BUY", "entryType": "DEAL_ENTRY_IN", "symbol": "EURUSD",
             "volume": 0.1, "price": 1.1, "profit": 0, "time": now, "positionId": "9"},
            {"id": "2", "type": "DEAL_TYPE_BALANCE", "profit": 1000, "time": now},
        ],
        [],
        now,
    )
    payload = MT5SyncPayload.model_validate(data)
    assert payload.external_account_id == "123"
    assert len(payload.deals) == 1 and payload.deals[0].entry_type == "in"
    assert payload.positions[0].direction == "Long"
    assert payload.snapshot.balance == 1000


def test_run_sync_imports_balance_positions_and_history(client, test_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(metaapi, "SessionLocal", SessionLocal)
    from app.platform_models import AccountConnection, AccountSnapshot, MT5Deal

    register(client)
    account_id = make_account(client)["id"]
    with SessionLocal() as db:
        connection = db.get(AccountConnection, account_id)
        connection.provider_account_id = "prov-1"
        connection.connector_type = "metaapi"
        db.commit()
    now = datetime.now(UTC)

    async def fake_fetch(provider_id, run_id, start):
        return metaapi.build_payload(
            run_id,
            {"login": 123456, "balance": 5000, "equity": 5100},
            [],
            [{"id": "1", "type": "DEAL_TYPE_BUY", "entryType": "DEAL_ENTRY_IN",
              "symbol": "XAUUSD", "volume": 1, "price": 2000, "time": now, "positionId": "7"}],
            [],
            now,
        )

    monkeypatch.setattr(metaapi, "fetch_from_provider", fake_fetch)
    asyncio.run(metaapi.run_sync(account_id))
    with SessionLocal() as db:
        assert db.get(AccountConnection, account_id).status == "connected"
        assert db.query(MT5Deal).count() == 1
        assert db.query(AccountSnapshot).one().balance == 5000


def test_delete_account_removes_it(client):
    register(client)
    account_id = make_account(client)["id"]
    assert client.delete(f"/api/v1/accounts/{account_id}").status_code == 204
    assert client.get(f"/api/v1/accounts/{account_id}/status").status_code == 404
    assert client.delete(f"/api/v1/accounts/{account_id}").status_code == 404
