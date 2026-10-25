import importlib

import pytest


def load_worker(monkeypatch):
    monkeypatch.setenv("TRADEIQ_API_URL", "http://localhost:8000")
    monkeypatch.setenv("TRADEIQ_ACCOUNT_ID", "account-id")
    monkeypatch.setenv("TRADEIQ_CONNECTOR_TOKEN", "connector-token")
    return importlib.import_module("mt5_worker.worker")


class FakeMetaTrader:
    def __init__(self, login_result=True):
        self.login_result = login_result
        self.login_calls = []

    def login(self, login, **options):
        self.login_calls.append((login, options))
        return self.login_result

    def last_error(self):
        return (-6, "authorization failed")


def stub_credentials(worker, monkeypatch):
    monkeypatch.setattr(
        worker,
        "api_request",
        lambda path, **_: {
            "login": 123456,
            "password": "read-only-password",
            "server": "Broker-MT5",
            "timeout": 60000,
        },
    )


def test_mt5_worker_logs_in_with_saved_credentials(monkeypatch):
    worker = load_worker(monkeypatch)
    stub_credentials(worker, monkeypatch)
    mt5 = FakeMetaTrader()

    assert worker.authenticate_terminal(mt5) == "123456"

    assert mt5.login_calls == [
        (
            123456,
            {"password": "read-only-password", "server": "Broker-MT5", "timeout": 60000},
        )
    ]


def test_mt5_worker_surfaces_login_failure(monkeypatch):
    worker = load_worker(monkeypatch)
    stub_credentials(worker, monkeypatch)
    mt5 = FakeMetaTrader(login_result=False)

    with pytest.raises(RuntimeError, match="authorization failed"):
        worker.authenticate_terminal(mt5)
