"""Makes TradeIQ survive every MetaTrader 5 restart and account switch.

Run while MT5 is closed:  python attach_ea.py <MT5 data folder> <webhook url>

1. Stores the Expert Advisor in the saved chart profile, so it loads whenever MT5 is opened
   normally (the one-time /config start-up only attaches it for a single launch).
2. Turns off MT5's "disable automatic trading when the account/profile changes" options, which
   otherwise switch the EA off each time the trader logs into another account.
"""
import re
import sys
from pathlib import Path

EA_PATH = r"Experts\TradeIQ_Journal.ex5"
CRLF = "\r\n"


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    return raw.decode("utf-8-sig"), "utf-8"


def write_text(path: Path, text: str, encoding: str) -> None:
    path.write_bytes(("\ufeff" + text).encode("utf-16-le") if encoding == "utf-16" else text.encode("utf-8"))


def set_ini_values(text: str, section: str, values: dict[str, str]) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == f"[{section.lower()}]"), None)
    if start is None:
        return CRLF.join([*lines, f"[{section}]", *(f"{k}={v}" for k, v in values.items())]) + CRLF
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    pending = dict(values)
    for i in range(start + 1, end):
        key = lines[i].split("=", 1)[0].strip()
        if "=" in lines[i] and key in pending:
            lines[i] = f"{key}={pending.pop(key)}"
    lines[end:end] = [f"{k}={v}" for k, v in pending.items()]
    return CRLF.join(lines) + CRLF


def expert_block(url: str) -> str:
    return CRLF.join(
        [
            "<expert>",
            "<inputs>",
            f"WebhookURL={url}",
            "SyncHistoryDays=365",
            "PushSeconds=30",
            "UseFileBridge=true",
            "</inputs>",
            "name=TradeIQ_Journal",
            f"path={EA_PATH}",
            "expertmode=5",
            "</expert>",
            "",
        ]
    )


def strip_expert(text: str) -> str:
    return re.sub(r"<expert>.*?</expert>\r?\n?", "", text, flags=re.S)


def attach_to_profile(data: Path, url: str) -> str:
    common = data / "config" / "common.ini"
    profile = "Default"
    if common.exists():
        match = re.search(r"^ProfileLast=(.+)$", read_text(common)[0], re.M)
        profile = match.group(1).strip() if match else profile
    charts = sorted((data / "MQL5" / "Profiles" / "Charts" / profile).glob("*.chr"))
    if not charts:
        return "no saved charts; the start-up attach will be used"
    loaded = {path: read_text(path) for path in charts}
    for path, (text, encoding) in loaded.items():
        if "TradeIQ_Journal.ex5" in text:
            write_text(path, _replace_ours(text, url), encoding)
            return f"updated {path.name}"
    free = [item for item in loaded.items() if "<expert>" not in item[1][0]]
    if not free:
        return "every chart already runs another Expert Advisor"
    path, (text, encoding) = next((i for i in free if "symbol=EURUSD" in i[1][0]), free[0])
    marker = "<chart>" + CRLF
    if marker not in text:
        return f"unexpected chart format in {path.name}"
    write_text(path, text.replace(marker, marker + expert_block(url), 1), encoding)
    return f"attached to {path.name}"


def _replace_ours(text: str, url: str) -> str:
    return re.sub(
        r"<expert>(?:(?!</expert>).)*?TradeIQ_Journal\.ex5.*?</expert>\r?\n?",
        lambda _: expert_block(url),
        text,
        count=1,
        flags=re.S,
    )


def keep_algo_trading_on(data: Path) -> None:
    common = data / "config" / "common.ini"
    text, encoding = read_text(common) if common.exists() else ("", "utf-16")
    write_text(common, set_ini_values(text, "Experts", {"Enabled": "1", "Account": "0", "Profile": "0"}), encoding)


def main() -> None:
    data, url = Path(sys.argv[1]), sys.argv[2]
    keep_algo_trading_on(data)
    print("TradeIQ:", attach_to_profile(data, url))


if __name__ == "__main__":
    main()
