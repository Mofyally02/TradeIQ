Short answer: yes — three ways, from "zero code" to "fully headless"

First, current live state (verified just now):

- Chart chart01.chr — GOLD,H1, chart_id 85598568538515 — has TradeIQ_Journal attached with the correct preset inputs (WebhookURL = device URL, SyncHistoryDays=365, PushSeconds=30, UseFileBridge=true).

- Terminal journal: 16:53:46 expert TradeIQ_Journal (GOLD,H1) loaded successfully with no init error and no WebRequest failed since → it is initialised and running in file-bridge mode.

- I also opened a second test chart to try a scripted attach; it is now closed, only the configured chart remains.

About doing it programmatically (what I tried)

I attempted 6 × chart_add_expert with the preset values passed as expert_parameters. Every attempt was rejected by the EA:

16:56:23  initializing of TradeIQ_Journal (GOLD,H1) failed with code 32767 (incorrect parameters)
... (same at 16:56:28, :31, :43, :48, :52)

The attach itself works, but the input string (long URL + token) does not reach the EA — it falls back to defaults (WebhookURL=""). So automation can put the EA on a chart, but the inputs have to come from somewhere other than the attach dialog. That is exactly what the options below solve.

Option A — Chart template (no code, one-time 20 s click)

1. Right-click the configured GOLD,H1 chart → Templates → Save Template → name it TradeIQ.

2. Charts → Template → load TradeIQ as the default template (or use Assign to all windows / set per-symbol default).

From then on every new chart of that template gets TradeIQ_Journal with the exact inputs, no Inputs tab. Downside: still tied to a chart, and a template is a GUI step.

Option B — Self-configuring EA (no GUI steps, I can do it now)

Patch OnInit so that when WebhookURL is empty the EA reads it from a config file, e.g. MQL5\Files\tradeiq.cfg:

WebhookURL=http://localhost:8000/api/v1/mt5/device/23716723-.../69smrrG2...
UseFileBridge=true
PushSeconds=30
SyncHistoryDays=365

Then even a plain drag-and-drop (or any scripted attach with default inputs, like the one that just failed) starts successfully — the EA configures itself. The token stays in a runtime config file, not in the source. Small, contained change; I would compile it and re-verify the journal.

Option C — Service instead of EA (most "automatic", headless)

Port the push logic to MQL5\Services\TradeIQ_Journal_Service.mq5. Services start with the terminal automatically, need no chart, no symbol, no timeframe, and survive profile/template changes. It also removes the "chart must be open" failure mode. This is a new program (code duplication of the same logic), so it is the largest change of the three.

Recommendation

Option B (so attaching never fails again) + Option A (so it is on every chart you open). If you want it running 24/7 without any chart at all, go Option C instead of A.

One thing still unverified

MQL5\Files\ contains only Temp — no tradeiq_out_*.json are present. Since UseFileBridge=true, the EA writes one file per push (every 30 s), so the TradeIQ bridge on :8000 is almost certainly consuming them. Please confirm inside the TradeIQ dashboard that balance/position data is arriving; if it is not, the problem is on the bridge side, not the EA.

Say which option you want and I will implement and compile it (B and/or C).

Therefore, the next update for the system should be the Options B and C 


Follow-Up 
Done — code is in place; one manual step (compile) remains because this MCP session exposes no compiler.

Done (with one blocked step).

Changed / created:
- `MQL5\Include\TradeIQ\TradeIQCore.mqh` (new): single push engine class `CTradeIQ`
  (Header/DealJson/PositionsJson/Send/PushHistory/PushState + `LoadFromFile()`).
  Reads `key=value` settings from `MQL5\Files\<ConfigFile>`. Inputs win; the file is
  only read when `WebhookURL` input is empty.
- `MQL5\Experts\TradeIQ_Journal.mq5`: v1.10 → v1.20. Logic moved to the include,
  new input `ConfigFile = "tradeiq.cfg"`. OnInit now self-configures from the file,
  so attaching with untouched inputs no longer fails with 32767.
- `MQL5\Services\TradeIQ_Journal_Service.mq5` (new): headless variant. `OnStart()`
  sends history once, then loops `PushState` every `PushSeconds` until `IsStopped()`.
  No chart, symbol or timeframe needed; starts with the terminal once started.
- `MQL5\Files\tradeiq.cfg` (new): your device URL + `SyncHistoryDays=365`,
  `PushSeconds=30`, `UseFileBridge=true`.

Validation:
- Compilation: NOT RUN — the connected `metatrader5` MCP server exposes no
  compile/editor tool, and no shell tool is available in this session (verified).
  Files were hand-reviewed for MQL5 correctness, not machine-verified.

Notes:
- The chart that is live right now still runs the old v1.10 binary with its saved
  inputs, so TradeIQ reporting is uninterrupted. Nothing was broken by the edits.

The one step you must do (30 seconds)

MetaEditor → open each file → F7 (or Navigator → right-click → Compile):

1. MQL5\Experts\TradeIQ_Journal.mq5

2. MQL5\Services\TradeIQ_Journal_Service.mq5

After compiling, MT5 hot-reloads the EA on the GOLD,H1 chart automatically. Since that chart already holds the URL input, it keeps working unchanged — the config file is just a fallback.

How it behaves afterwards (no manual configuration)

Situation
Result

Drag the EA onto any chart, leave inputs at default
Loads tradeiq.cfg → initialises fine, no 32767

Attach with a URL typed in inputs
Inputs win, file ignored

Change token later
Edit MQL5\Files\tradeiq.cfg only, restart EA/service

Run the Service instead of a chart
Yes — headless, survives restarts, no chart needed

tradeiq.cfg current content:

WebhookURL=http://localhost:8000/api/v1/mt5/device/23716723-.../69smrrG2...
SyncHistoryDays=365
PushSeconds=30
UseFileBridge=true

Important operational choice

Run either the EA on a chart or the Service — not both. Both push to the same webhook, so running them together duplicates deals/positions in TradeIQ.

- Keep the chart EA (simplest): compile file 1, done.

- Go headless: compile file 2, then Navigator → Services → TradeIQ_Journal_Service → Start, and remove the EA from the chart with chart_remove_expert (I can do that for you).

Caveats

- tradeiq.cfg holds your webhook token in plain text (it already existed in Presets\TradeIQ.set). It is not in source code, but treat the file as private and do not share MQL5\Files contents.

- The Service is set to UseFileBridge=true by default because WebRequest availability from service threads is not guaranteed on all builds; if you switch it to WebRequest mode, add http://localhost:8000 under Tools → Options → Expert Advisors → Allow WebRequest.

- Profiles\Tester\TradeIQ.set still points at a different endpoint (/api/v1/mt5/ea/...) and uses the file bridge — worth reviewing before any Strategy Tester run, since tester file I/O is not the live MQL5\Files folder.

- This EA sends account, position and deal data to your configured endpoint; it places no orders. No profit/behaviour guarantees implied.

Tell me if you want me to remove the chart EA once you have the Service running, or to also add the TradeIQ chart template setup.