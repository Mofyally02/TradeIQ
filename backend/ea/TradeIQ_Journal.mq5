//+------------------------------------------------------------------+
//| TradeIQ_Journal.mq5                                              |
//| Pushes balance, open positions and closed deals to TradeIQ.      |
//+------------------------------------------------------------------+
#property copyright "TradeIQ"
#property version   "1.12"
#property strict

input string WebhookURL      = "";   // Full webhook URL shown in TradeIQ
input int    SyncHistoryDays = 365;  // History imported on first attach
input int    PushSeconds     = 30;   // How often balance/positions are pushed
input bool   UseFileBridge   = false; // Write files for the local bridge instead of using WebRequest

int g_seq = 0;

datetime g_lastDealTime = 0;
bool     g_historyDone  = false;
long     g_login        = 0;
string   g_terminal_id  = "";
int      g_last_error   = 0;
int      g_last_http    = 0;
string   g_last_result  = "Starting";

string Esc(string t);

string TerminalId()
{
   string key = "TradeIQ.TerminalId";
   if(!GlobalVariableCheck(key))
   {
      double value = (double)TimeLocal() * 100000.0 + (double)(GetTickCount() % 100000);
      GlobalVariableSet(key, value);
   }
   return IntegerToString((long)GlobalVariableGet(key));
}

void ShowStatus(int errorCode, int httpStatus, string result)
{
   g_last_error = errorCode;
   g_last_http = httpStatus;
   g_last_result = result;
   Comment("TradeIQ Journal 1.12\nTerminal: ", g_terminal_id,
           "\nAccount: ", IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)),
           "\nLast push: ", result,
           "\nMT5 error: ", IntegerToString(errorCode),
           " · HTTP: ", IntegerToString(httpStatus));
}

string DiagnosticsJson()
{
   return "\"diagnostics\":{\"ea_version\":\"1.12\",\"terminal_id\":\"" + Esc(g_terminal_id) +
          "\",\"login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) +
          ",\"last_error_code\":" + IntegerToString(g_last_error) +
          ",\"http_status\":" + IntegerToString(g_last_http) +
          ",\"last_result\":\"" + Esc(g_last_result) + "\"}";
}

//+------------------------------------------------------------------+
int OnInit()
{
   g_terminal_id = TerminalId();
   ShowStatus(0, 0, "Starting");
   if(!UseFileBridge && StringLen(WebhookURL) < 20)
   {
      Print("TradeIQ: set the WebhookURL input.");
      ShowStatus(0, 0, "Webhook URL is missing");
      return INIT_PARAMETERS_INCORRECT;
   }
   EventSetTimer(PushSeconds);
   PushState(false);
   PushHistory();
   PushState(true);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   PushState(true);
   if(!g_historyDone) { PushHistory(); PushState(true); }
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) PushState(true);
}

//+------------------------------------------------------------------+
string Esc(string t)
{
   StringReplace(t, "\\", "\\\\");
   StringReplace(t, "\"", "\\\"");
   StringReplace(t, "\n", " ");
   StringReplace(t, "\r", " ");
   return t;
}

string Header()
{
   long offset = (long)(TimeTradeServer() - TimeGMT());
   return "{\"account\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) +
          ",\"server\":\"" + Esc(AccountInfoString(ACCOUNT_SERVER)) + "\"" +
          ",\"currency\":\"" + Esc(AccountInfoString(ACCOUNT_CURRENCY)) + "\"" +
          ",\"name\":\"" + Esc(AccountInfoString(ACCOUNT_NAME)) + "\"" +
          ",\"server_offset\":" + IntegerToString(offset) +
          ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) +
          ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) +
          ",\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) +
          ",\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) +
          "," + DiagnosticsJson();
}

string DealJson(ulong t)
{
   long type = HistoryDealGetInteger(t, DEAL_TYPE);
   if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) return "";
   string sym = HistoryDealGetString(t, DEAL_SYMBOL);
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   long entry = HistoryDealGetInteger(t, DEAL_ENTRY);
   string e = entry == DEAL_ENTRY_IN ? "in" : entry == DEAL_ENTRY_OUT ? "out" :
              entry == DEAL_ENTRY_INOUT ? "inout" : "out_by";
   return "{\"ticket\":" + IntegerToString(t) +
          ",\"position_id\":" + IntegerToString(HistoryDealGetInteger(t, DEAL_POSITION_ID)) +
          ",\"order\":" + IntegerToString(HistoryDealGetInteger(t, DEAL_ORDER)) +
          ",\"symbol\":\"" + Esc(sym) + "\"" +
          ",\"type\":\"" + (type == DEAL_TYPE_BUY ? "buy" : "sell") + "\"" +
          ",\"entry\":\"" + e + "\"" +
          ",\"volume\":" + DoubleToString(HistoryDealGetDouble(t, DEAL_VOLUME), 2) +
          ",\"price\":" + DoubleToString(HistoryDealGetDouble(t, DEAL_PRICE), digits) +
          ",\"profit\":" + DoubleToString(HistoryDealGetDouble(t, DEAL_PROFIT), 2) +
          ",\"commission\":" + DoubleToString(HistoryDealGetDouble(t, DEAL_COMMISSION), 2) +
          ",\"swap\":" + DoubleToString(HistoryDealGetDouble(t, DEAL_SWAP), 2) +
          ",\"time\":" + IntegerToString(HistoryDealGetInteger(t, DEAL_TIME)) + "}";
}

string PositionsJson()
{
   string j = "[";
   bool first = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      if(!first) j += ",";
      first = false;
      j += "{\"ticket\":" + IntegerToString(t) +
           ",\"position_id\":" + IntegerToString(PositionGetInteger(POSITION_IDENTIFIER)) +
           ",\"symbol\":\"" + Esc(sym) + "\"" +
           ",\"type\":\"" + (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "buy" : "sell") + "\"" +
           ",\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) +
           ",\"open_price\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), digits) +
           ",\"current_price\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_CURRENT), digits) +
           ",\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), digits) +
           ",\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), digits) +
           ",\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + "}";
   }
   return j + "]";
}

//+------------------------------------------------------------------+
bool Send(string json)
{
   if(UseFileBridge)
   {
      string name = StringFormat("tradeiq_out_%I64d_%06d.json", (long)TimeLocal(), g_seq++);
      int h = FileOpen(name, FILE_WRITE | FILE_TXT | FILE_ANSI);
      if(h == INVALID_HANDLE)
      {
         int errorCode = GetLastError();
         Print("TradeIQ: cannot write ", name, " (MT5 error ", errorCode, ")");
         ShowStatus(errorCode, 0, "Could not queue data for the bridge");
         return false;
      }
      FileWriteString(h, json);
      FileClose(h);
      ShowStatus(0, 0, "Queued for local bridge");
      return true;
   }
   char post[], reply[];
   string hdr = "Content-Type: application/json\r\n", rhdr;
   StringToCharArray(json, post, 0, StringLen(json), CP_UTF8);
   int code = WebRequest("POST", WebhookURL, hdr, 8000, post, reply, rhdr);
   if(code == -1)
   {
      int errorCode = GetLastError();
      string hint = errorCode == 4014
         ? "URL blocked; add the exact API origin to MT5 WebRequest allow-list"
         : errorCode >= 5200 && errorCode <= 5203
            ? StringFormat("Network request failed (MT5 error %d)", errorCode)
            : StringFormat("WebRequest failed (MT5 error %d)", errorCode);
      Print("TradeIQ: ", hint, ". Check the configured API address and MT5 WebRequest allow-list.");
      ShowStatus(errorCode, -1, hint);
      return false;
   }
   if(code != 200)
   {
      string hint = code == 401 || code == 403 ? "Authentication rejected; update EA setup"
         : code == 409 ? "Account login mismatch; check the active MT5 account"
         : StringFormat("API returned HTTP %d", code);
      Print("TradeIQ: ", hint, ". HTTP ", code);
      ShowStatus(0, code, hint);
      return false;
   }
   ShowStatus(0, 200, "Heartbeat accepted by TradeIQ");
   return true;
}

// First attach: send past deals in batches (no "positions" key, so nothing is closed).
void PushHistory()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(login != g_login) { g_login = login; g_historyDone = false; g_lastDealTime = 0; }
   if(g_historyDone) return;
   datetime from = TimeCurrent() - (datetime)SyncHistoryDays * 86400;
   if(!HistorySelect(from, TimeCurrent() + 86400)) return;
   int total = HistoryDealsTotal();
   string batch = "";
   int count = 0;
   bool ok = true;
   for(int i = 0; i < total && ok; i++)
   {
      string d = DealJson(HistoryDealGetTicket(i));
      if(d == "") continue;
      batch += (count > 0 ? "," : "") + d;
      count++;
      if(count == 200)
      {
         ok = Send(Header() + ",\"deals\":[" + batch + "]}");
         batch = ""; count = 0;
      }
   }
   if(ok && count > 0) ok = Send(Header() + ",\"deals\":[" + batch + "]}");
   if(ok) { g_historyDone = true; g_lastDealTime = TimeCurrent(); }
}

// Regular push: account, every open position, and deals since the last push.
void PushState(bool withDeals)
{
   if(AccountInfoInteger(ACCOUNT_LOGIN) != g_login) g_historyDone = false;
   string deals = "";
   datetime now = TimeCurrent();
   if(withDeals && g_historyDone && HistorySelect(g_lastDealTime - 120, now + 86400))
   {
      int count = 0;
      for(int i = 0; i < HistoryDealsTotal() && count < 200; i++)
      {
         string d = DealJson(HistoryDealGetTicket(i));
         if(d == "") continue;
         deals += (count > 0 ? "," : "") + d;
         count++;
      }
   }
   string json = Header() + ",\"positions\":" + PositionsJson() + ",\"deals\":[" + deals + "]}";
   if(Send(json)) g_lastDealTime = now;
}
