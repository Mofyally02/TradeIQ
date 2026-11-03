"""Generates the one-click TradeIQ installers (macOS / Windows) for a single account."""
import re
from pathlib import Path

EA_DIR = Path(__file__).resolve().parents[2] / "ea"

MAC_TEMPLATE = r"""#!/bin/bash
# TradeIQ one-click setup for __NAME__
set -e
URL='__URL__'
BASE='__BASE__'
ORIGIN='__ORIGIN__'
PREFIX="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5"
DATA="$PREFIX/drive_c/Program Files/MetaTrader 5"
WINE="/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine"
echo "TradeIQ setup"
if [ ! -d "$DATA" ] || [ ! -x "$WINE" ]; then
  echo "MetaTrader 5 was not found. Install it from the MetaQuotes site, open it once, log in, then run this file again."
  read -n 1 -s -r -p "Press any key to close"; exit 1
fi
if ! curl --connect-timeout 5 --retry 2 -fsS "$ORIGIN/readyz" >/dev/null; then
  echo "TradeIQ API is not reachable at $ORIGIN. If MT5 is on another computer or VM, localhost points to that machine. Set PUBLIC_API_URL to an address reachable from MT5 and run setup again."
  read -n 1 -s -r -p "Press any key to close"; exit 1
fi
command -v python3 >/dev/null || { echo "python3 is required (run: xcode-select --install)"; exit 1; }
echo "1/5 Closing MetaTrader 5..."
osascript -e 'quit app "MetaTrader 5"' >/dev/null 2>&1 || true
for pid in $(pgrep -f "terminal64.exe" || true); do kill "$pid" 2>/dev/null || true; done
sleep 8
echo "2/5 Installing the TradeIQ Expert Advisor..."
mkdir -p "$DATA/MQL5/Experts" "$DATA/MQL5/Files" "$DATA/MQL5/Presets" "$DATA/config"
curl -fsSL "$BASE/ea.mq5" -o "$DATA/MQL5/Experts/TradeIQ_Journal.mq5"
export WINEPREFIX="$PREFIX"
cd "$DATA"
"$WINE" metaeditor64.exe /compile:"MQL5\\Experts\\TradeIQ_Journal.mq5" /log:"tradeiq_compile.log" >/dev/null 2>&1 || true
if [ ! -f "$DATA/MQL5/Experts/TradeIQ_Journal.ex5" ]; then
  echo "The Expert Advisor did not compile. See $DATA/tradeiq_compile.log"
  read -n 1 -s -r -p "Press any key to close"; exit 1
fi
echo "3/5 Writing your connection settings..."
utf16() { { printf '\xff\xfe'; iconv -f UTF-8 -t UTF-16LE; } > "$1"; }
printf 'WebhookURL=%s\r\nSyncHistoryDays=365\r\nPushSeconds=30\r\nUseFileBridge=true\r\n' "$URL" | utf16 "$DATA/MQL5/Presets/TradeIQ.set"
printf '__COMMON_SH__[Experts]\r\nAllowLiveTrading=1\r\nEnabled=1\r\nAccount=0\r\nProfile=0\r\n[StartUp]\r\nExpert=TradeIQ_Journal\r\nExpertParameters=TradeIQ.set\r\nSymbol=EURUSD\r\nPeriod=H1\r\n' | utf16 "$DATA/config/tradeiq_start.ini"
python3 - "$DATA" "$URL" <<'TRADEIQ_ATTACH_PY'
__ATTACH_PY__
TRADEIQ_ATTACH_PY
echo "4/5 Starting the background sync service..."
mkdir -p "$HOME/.tradeiq"
curl -fsSL "$BASE/bridge.py" -o "$HOME/.tradeiq/bridge.py"
PLIST="$HOME/Library/LaunchAgents/com.tradeiq.bridge.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.tradeiq.bridge</string>
<key>ProgramArguments</key><array><string>$(command -v python3)</string><string>$HOME/.tradeiq/bridge.py</string><string>$DATA/MQL5/Files</string><string>$URL</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>$HOME/.tradeiq/bridge.log</string><key>StandardErrorPath</key><string>$HOME/.tradeiq/bridge.log</string>
</dict></plist>
PLISTEOF
chmod 600 "$PLIST"
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
echo "5/5 Reopening MetaTrader 5 with TradeIQ attached (it will now reattach by itself every time)..."
nohup "$WINE" terminal64.exe /config:"C:\\Program Files\\MetaTrader 5\\config\\tradeiq_start.ini" >/dev/null 2>&1 &
echo "Done. Return to TradeIQ - connection status should update within seconds; history continues importing in the background."
sleep 3
"""

WINDOWS_TEMPLATE = r"""@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((Get-Content -LiteralPath '%~f0' -Raw) -split '#PSBEGIN#')[1]"
pause
exit /b
#PSBEGIN#
$ErrorActionPreference = 'Stop'
$Url = '__URL__'; $Base = '__BASE__'; $Origin = '__ORIGIN__'
Write-Host 'TradeIQ setup for __NAME__'
try { Invoke-WebRequest "$Origin/readyz" -TimeoutSec 5 -UseBasicParsing | Out-Null }
catch { Write-Host "TradeIQ API is not reachable at $Origin. If MT5 is on another computer or VM, localhost points to that machine. Set PUBLIC_API_URL to an address reachable from MT5 and run setup again."; exit 1 }
$origin = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal\*\origin.txt" -ErrorAction SilentlyContinue | Where-Object {
  $p = (Get-Content $_.FullName -Raw).Trim([char]0xFEFF).Trim(); Test-Path (Join-Path $p 'terminal64.exe') } | Select-Object -First 1
if (-not $origin) { Write-Host 'MetaTrader 5 was not found. Install it, open it once and log in, then run this file again.'; exit 1 }
$Install = (Get-Content $origin.FullName -Raw).Trim([char]0xFEFF).Trim()
$Data = Split-Path $origin.FullName
Write-Host '1/5 Closing MetaTrader 5...'
Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 4
Write-Host '2/5 Installing the TradeIQ Expert Advisor...'
New-Item -ItemType Directory -Force "$Data\MQL5\Experts","$Data\MQL5\Files","$Data\MQL5\Presets","$Data\config" | Out-Null
Invoke-WebRequest "$Base/ea.mq5" -OutFile "$Data\MQL5\Experts\TradeIQ_Journal.mq5"
& "$Install\metaeditor64.exe" "/compile:$Data\MQL5\Experts\TradeIQ_Journal.mq5" "/log:$Data\tradeiq_compile.log" | Out-Null
if (-not (Test-Path "$Data\MQL5\Experts\TradeIQ_Journal.ex5")) { Write-Host "The Expert Advisor did not compile. See $Data\tradeiq_compile.log"; exit 1 }
Write-Host '3/5 Writing your connection settings...'
"WebhookURL=$Url`r`nSyncHistoryDays=365`r`nPushSeconds=30`r`nUseFileBridge=true`r`n" | Out-File -Encoding Unicode "$Data\MQL5\Presets\TradeIQ.set"
"__COMMON_PS__[Experts]`r`nAllowLiveTrading=1`r`nEnabled=1`r`nAccount=0`r`nProfile=0`r`n[StartUp]`r`nExpert=TradeIQ_Journal`r`nExpertParameters=TradeIQ.set`r`nSymbol=EURUSD`r`nPeriod=H1`r`n" | Out-File -Encoding Unicode "$Data\config\tradeiq_start.ini"
$profile = 'Default'
$common = "$Data\config\common.ini"
if (Test-Path $common) { $m = [regex]::Match((Get-Content $common -Raw), '(?m)^ProfileLast=(.+)$'); if ($m.Success) { $profile = $m.Groups[1].Value.Trim() } }
$block = "<expert>`r`n<inputs>`r`nWebhookURL=$Url`r`nSyncHistoryDays=365`r`nPushSeconds=30`r`nUseFileBridge=true`r`n</inputs>`r`nname=TradeIQ_Journal`r`npath=Experts\TradeIQ_Journal.ex5`r`nexpertmode=5`r`n</expert>`r`n"
$charts = @(Get-ChildItem "$Data\MQL5\Profiles\Charts\$profile\*.chr" -ErrorAction SilentlyContinue)
$texts = @{}; foreach ($c in $charts) { $texts[$c.FullName] = [IO.File]::ReadAllText($c.FullName) }
$ours = $charts | Where-Object { $texts[$_.FullName] -match 'TradeIQ_Journal\.ex5' } | Select-Object -First 1
$free = @($charts | Where-Object { $texts[$_.FullName] -notmatch '<expert>' })
if ($ours) { $t = [regex]::Replace($texts[$ours.FullName], '(?s)<expert>(?:(?!</expert>).)*?TradeIQ_Journal\.ex5.*?</expert>\r?\n?', { param($x) $block }, 1); [IO.File]::WriteAllText($ours.FullName, $t, [Text.Encoding]::Unicode) }
elseif ($free.Count -gt 0) {
  $pick = $free | Where-Object { $texts[$_.FullName] -match 'symbol=EURUSD' } | Select-Object -First 1; if (-not $pick) { $pick = $free[0] }
  $t = $texts[$pick.FullName].Replace("<chart>`r`n", "<chart>`r`n$block"); [IO.File]::WriteAllText($pick.FullName, $t, [Text.Encoding]::Unicode)
}
if (Test-Path $common) {
  $t = Get-Content $common -Raw
  foreach ($k in 'Account', 'Profile') { $t = [regex]::Replace($t, "(?m)^$k=.*$", "$k=0") }
  [IO.File]::WriteAllText($common, $t, [Text.Encoding]::Unicode)
}
Write-Host '4/5 Starting the background sync service...'
$dir = "$env:USERPROFILE\.tradeiq"; New-Item -ItemType Directory -Force $dir | Out-Null
$bridge = @'
param($Folder, $Url)
$Log = Join-Path $env:USERPROFILE '.tradeiq\bridge.log'
while ($true) {
  foreach ($f in Get-ChildItem -LiteralPath $Folder -Filter 'tradeiq_out_*.json' | Sort-Object Name) {
    try {
      Invoke-WebRequest -Uri $Url -Method Post -ContentType 'application/json' -Body ([IO.File]::ReadAllBytes($f.FullName)) -UseBasicParsing | Out-Null
      Add-Content -LiteralPath $Log -Value "$(Get-Date -Format o) delivered $($f.Name)"
      Remove-Item -LiteralPath $f.FullName
    } catch {
      $code = 0; if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
      Add-Content -LiteralPath $Log -Value "$(Get-Date -Format o) failed $($f.Name) HTTP=$code error_type=$($_.Exception.GetType().Name)"
      if ($code -ge 400 -and $code -lt 500) { Remove-Item -LiteralPath $f.FullName } else { break }
    }
  }
  Start-Sleep 2
}
'@
Set-Content -Path "$dir\bridge.ps1" -Value $bridge
$args2 = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$dir\bridge.ps1`" -Folder `"$Data\MQL5\Files`" -Url `"$Url`""
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*tradeiq*bridge.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Unregister-ScheduledTask -TaskName 'TradeIQ Bridge' -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName 'TradeIQ Bridge' -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $args2) -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Force | Out-Null
Start-ScheduledTask -TaskName 'TradeIQ Bridge'
Write-Host '5/5 Reopening MetaTrader 5 with TradeIQ attached (it will now reattach by itself every time)...'
Start-Process "$Install\terminal64.exe" "/config:`"$Data\config\tradeiq_start.ini`""
Write-Host 'Done. Return to TradeIQ - connection status should update within seconds; history continues importing in the background.'
"""


def _clean(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9 ._\-]", "", value or "")


def render_installer(os_name: str, *, name: str, url: str, base: str, origin: str, login: str | None, server: str | None) -> tuple[str, str, str]:
    template, filename = (
        (WINDOWS_TEMPLATE, "TradeIQ-Setup.bat") if os_name == "windows" else (MAC_TEMPLATE, "TradeIQ-Setup.command")
    )
    login_c, server_c = _clean(login), _clean(server)
    common_sh = f"[Common]\\r\\nLogin={login_c}\\r\\nServer={server_c}\\r\\n" if login_c else ""
    common_ps = f"[Common]`r`nLogin={login_c}`r`nServer={server_c}`r`n" if login_c else ""
    attach_py = (EA_DIR / "attach_ea.py").read_text(encoding="utf-8")
    body = (
        template.replace("__ATTACH_PY__", attach_py)
        .replace("__COMMON_SH__", common_sh)
        .replace("__COMMON_PS__", common_ps)
        .replace("__NAME__", _clean(name))
        .replace("__URL__", url)
        .replace("__BASE__", base)
        .replace("__ORIGIN__", origin)
    )
    if os_name == "windows":
        body = body.replace("\r\n", "\n").replace("\n", "\r\n")
    return body, filename, "application/octet-stream"
