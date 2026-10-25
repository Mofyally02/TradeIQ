import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("tradeiq.mt5_worker")


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


API_URL = setting("TRADEIQ_API_URL").rstrip("/")
ACCOUNT_ID = setting("TRADEIQ_ACCOUNT_ID")
CONNECTOR_TOKEN = setting("TRADEIQ_CONNECTOR_TOKEN")
POLL_SECONDS = int(setting("TRADEIQ_POLL_SECONDS", "10"))
HISTORY_DAYS = int(setting("TRADEIQ_HISTORY_DAYS", "365"))
TERMINAL_PATH = os.environ.get("MT5_TERMINAL_PATH")
API_ORIGIN = urlparse(API_URL)
if API_ORIGIN.scheme != "https" and API_ORIGIN.hostname not in {"localhost", "127.0.0.1"}:
    raise RuntimeError("TRADEIQ_API_URL must use HTTPS except for local development")
if API_ORIGIN.username or API_ORIGIN.password or not API_ORIGIN.hostname:
    raise RuntimeError("TRADEIQ_API_URL must be a valid origin without embedded credentials")
if POLL_SECONDS < 1 or HISTORY_DAYS < 1 or HISTORY_DAYS > 3650:
    raise RuntimeError("Worker poll interval and history window are outside supported bounds")


def api_request(path: str, method: str = "GET", payload: dict | None = None) -> dict | None:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_URL}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {CONNECTOR_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status == 204 or response.status == 202:
                return None
            response_body = response.read()
    except HTTPError as error:
        response_body = error.read()
        raise RuntimeError(
            "TradeIQ API returned HTTP "
            f"{error.code}: {response_body.decode('utf-8', errors='replace')}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"TradeIQ API is unavailable: {error.reason}") from error
    return json.loads(response_body) if response_body else None


def mt5_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def mt5_direction(value: int, mt5) -> str:
    if value in (mt5.ORDER_TYPE_BUY, mt5.DEAL_TYPE_BUY, mt5.POSITION_TYPE_BUY):
        return "Long"
    if value in (mt5.ORDER_TYPE_SELL, mt5.DEAL_TYPE_SELL, mt5.POSITION_TYPE_SELL):
        return "Short"
    raise RuntimeError(f"Unsupported MT5 direction value: {value}")


def mt5_entry_type(value: int, mt5) -> str:
    entry_types = {
        mt5.DEAL_ENTRY_IN: "in",
        mt5.DEAL_ENTRY_OUT: "out",
        mt5.DEAL_ENTRY_INOUT: "inout",
        mt5.DEAL_ENTRY_OUT_BY: "out_by",
    }
    if value not in entry_types:
        raise RuntimeError(f"Unsupported MT5 deal entry value: {value}")
    return entry_types[value]


def authenticate_terminal(mt5) -> str:
    """Fetch the saved credentials and call mt5.login(login, password=, server=, timeout=)."""
    creds = api_request(f"/api/v1/connectors/mt5/accounts/{ACCOUNT_ID}/credentials")
    if not creds:
        raise RuntimeError("TradeIQ returned no MT5 credentials")
    if not mt5.login(
        int(creds["login"]),
        password=creds["password"],
        server=creds["server"],
        timeout=int(creds["timeout"]),
    ):
        raise RuntimeError(
            f"Could not log in to MT5 account {creds['login']} on {creds['server']}: "
            f"{mt5.last_error()}"
        )
    return str(creds["login"])


def collect_account_data(mt5, sync_run_id: str, expected_login: str) -> dict:
    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError(f"MT5 account information unavailable: {mt5.last_error()}")
    if str(account_info.login) != expected_login:
        raise RuntimeError("The active MT5 terminal login does not match the saved account")

    end = datetime.now(UTC)
    start = end - timedelta(days=HISTORY_DAYS)
    order_history = mt5.history_orders_get(start, end)
    if order_history is None:
        raise RuntimeError(f"MT5 order history unavailable: {mt5.last_error()}")
    deal_history = mt5.history_deals_get(start, end)
    if deal_history is None:
        raise RuntimeError(f"MT5 deal history unavailable: {mt5.last_error()}")
    positions = mt5.positions_get()
    if positions is None:
        raise RuntimeError(f"MT5 positions unavailable: {mt5.last_error()}")

    orders = [
        {
            "external_order_id": str(item.ticket),
            "order_type": str(item.type),
            "volume": float(item.volume_initial),
            "price": float(item.price_open) if item.price_open else None,
            "stop_loss": float(item.sl) if item.sl else None,
            "take_profit": float(item.tp) if item.tp else None,
            "state": str(item.state),
            "occurred_at": mt5_timestamp(item.time_setup),
        }
        for item in order_history
    ]
    trade_deals = [
        item
        for item in deal_history
        if item.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
    ]
    deals = [
        {
            "external_deal_id": str(item.ticket),
            "position_identifier": str(item.position_id) if item.position_id else None,
            "external_order_id": str(item.order) if item.order else None,
            "entry_type": mt5_entry_type(item.entry, mt5),
            "symbol": item.symbol,
            "direction": mt5_direction(item.type, mt5),
            "volume": float(item.volume),
            "price": float(item.price),
            "pnl": float(item.profit),
            "commission": float(item.commission),
            "swap": float(item.swap),
            "occurred_at": mt5_timestamp(item.time),
        }
        for item in trade_deals
    ]
    observed_at = end.isoformat()
    current_positions = [
        {
            "external_position_id": str(item.ticket),
            "position_identifier": str(item.identifier),
            "symbol": item.symbol,
            "direction": mt5_direction(item.type, mt5),
            "volume": float(item.volume),
            "entry_price": float(item.price_open),
            "current_price": float(item.price_current),
            "stop_loss": float(item.sl) if item.sl else None,
            "take_profit": float(item.tp) if item.tp else None,
            "floating_pnl": float(item.profit),
            "state": "open",
            "observed_at": observed_at,
        }
        for item in positions
    ]
    return {
        "sync_run_id": sync_run_id,
        "external_account_id": str(account_info.login),
        "orders": orders,
        "deals": deals,
        "positions": current_positions,
        "snapshot": {
            "balance": float(account_info.balance),
            "equity": float(account_info.equity),
            "margin": float(account_info.margin),
            "free_margin": float(account_info.margin_free),
            "observed_at": observed_at,
        },
    }


def run() -> None:
    if os.name != "nt":
        raise RuntimeError("The MetaTrader5 terminal worker must run on Windows")
    try:
        import MetaTrader5 as mt5
    except ImportError as error:
        raise RuntimeError(
            "Install the optional MT5 worker dependency with: pip install -e '.[mt5-worker]'"
        ) from error

    initialized = mt5.initialize(path=TERMINAL_PATH) if TERMINAL_PATH else mt5.initialize()
    if not initialized:
        raise RuntimeError(f"Could not connect to the MT5 terminal: {mt5.last_error()}")
    try:
        while True:
            sync_run_id: str | None = None
            try:
                sync_request = api_request(
                    f"/api/v1/connectors/mt5/accounts/{ACCOUNT_ID}/sync-request"
                )
                if sync_request:
                    sync_run_id = sync_request["sync_run_id"]
                    login = authenticate_terminal(mt5)
                    payload = collect_account_data(mt5, sync_run_id, login)
                    result = api_request(
                        f"/api/v1/connectors/mt5/accounts/{ACCOUNT_ID}/sync",
                        method="POST",
                        payload=payload,
                    )
                    logger.info("Sync completed: %s", result)
            except (HTTPError, RuntimeError, URLError, ValueError, KeyError) as error:
                logger.exception("MT5 sync cycle failed")
                if sync_run_id is not None:
                    try:
                        api_request(
                            f"/api/v1/connectors/mt5/accounts/{ACCOUNT_ID}/sync-failure",
                            method="POST",
                            payload={"sync_run_id": sync_run_id, "error": str(error)[:2000]},
                        )
                    except RuntimeError:
                        logger.exception("Could not report the MT5 sync failure to TradeIQ")
                    sync_run_id = None
            time.sleep(POLL_SECONDS)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
