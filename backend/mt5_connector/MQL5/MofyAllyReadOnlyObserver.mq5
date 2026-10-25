#property strict
#property version   "1.00"
#property description "Observation-only MT5 connector for MofyAlly EDGE"

input string ApiBaseUrl = "https://api.example.com";
input string AccountId = "";
input string ConnectorToken = "";
input int PollSeconds = 10;
input int HistoryDays = 365;

const int MAX_HISTORY_RECORDS = 10000;
const int MAX_POSITIONS = 1000;
const int REQUEST_TIMEOUT_MS = 30000;

string TrimTrailingSlash(string value)
{
   while(StringLen(value) > 0 && StringSubstr(value, StringLen(value) - 1, 1) == "/")
      value = StringSubstr(value, 0, StringLen(value) - 1);
   return value;
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   StringReplace(value, "\t", "\\t");
   return value;
}

string JsonNumber(double value)
{
   return StringFormat("%.8f", value);
}

string JsonNullableNumber(double value)
{
   if(value == 0.0)
      return "null";
   return JsonNumber(value);
}

string UtcIso(datetime server_time)
{
   datetime utc_time = server_time - (TimeCurrent() - TimeGMT());
   MqlDateTime parts;
   TimeToStruct(utc_time, parts);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                       parts.year, parts.mon, parts.day,
                       parts.hour, parts.min, parts.sec);
}

bool ApiRequest(string method, string path, string body, string &response_body, int &status_code)
{
   string headers = "Authorization: Bearer " + ConnectorToken + "\r\n"
                    + "Content-Type: application/json\r\n";
   string response_headers;
   char request_data[];
   char response_data[];
   if(StringLen(body) > 0)
   {
      int count = StringToCharArray(body, request_data, 0, WHOLE_ARRAY, CP_UTF8);
      if(count > 0)
         ArrayResize(request_data, count - 1);
   }

   ResetLastError();
   status_code = WebRequest(method,
                            TrimTrailingSlash(ApiBaseUrl) + path,
                            headers,
                            REQUEST_TIMEOUT_MS,
                            request_data,
                            response_data,
                            response_headers);
   if(status_code == -1)
   {
      PrintFormat("TradeIQ API request failed (%d). Check the URL allow-list and terminal connection.",
                  GetLastError());
      return false;
   }
   response_body = CharArrayToString(response_data, 0, WHOLE_ARRAY, CP_UTF8);
   if(status_code < 200 || status_code >= 300)
   {
      PrintFormat("TradeIQ API returned HTTP %d: %s", status_code, response_body);
      return false;
   }
   return true;
}

string SyncRunIdFromResponse(string response)
{
   string key = "\"sync_run_id\"";
   int key_pos = StringFind(response, key);
   if(key_pos < 0)
      return "";
   int colon_pos = StringFind(response, ":", key_pos + StringLen(key));
   if(colon_pos < 0)
      return "";
   int first_quote = StringFind(response, "\"", colon_pos + 1);
   if(first_quote < 0)
      return "";
   int second_quote = StringFind(response, "\"", first_quote + 1);
   if(second_quote < 0)
      return "";
   return StringSubstr(response, first_quote + 1, second_quote - first_quote - 1);
}

string DealEntryName(long entry)
{
   if(entry == DEAL_ENTRY_IN)
      return "in";
   if(entry == DEAL_ENTRY_OUT)
      return "out";
   if(entry == DEAL_ENTRY_INOUT)
      return "inout";
   if(entry == DEAL_ENTRY_OUT_BY)
      return "out_by";
   return "";
}

string DirectionName(long direction)
{
   if(direction == POSITION_TYPE_BUY || direction == DEAL_TYPE_BUY)
      return "Long";
   return "Short";
}

bool BuildOrders(string &json)
{
   int total = HistoryOrdersTotal();
   if(total > MAX_HISTORY_RECORDS)
   {
      Print("MT5 order history exceeds the API batch limit; narrow HistoryDays before syncing.");
      return false;
   }

   json = "[";
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryOrderGetTicket(i);
      if(ticket == 0)
         continue;
      if(StringLen(json) > 1)
         json += ",";

      long order_type = HistoryOrderGetInteger(ticket, ORDER_TYPE);
      long state = HistoryOrderGetInteger(ticket, ORDER_STATE);
      json += "{\"external_order_id\":\"" + (string)ticket + "\","
              + "\"order_type\":\"" + (string)order_type + "\","
              + "\"volume\":" + JsonNumber(HistoryOrderGetDouble(ticket, ORDER_VOLUME_INITIAL)) + ","
              + "\"price\":" + JsonNullableNumber(HistoryOrderGetDouble(ticket, ORDER_PRICE_OPEN)) + ","
              + "\"stop_loss\":" + JsonNullableNumber(HistoryOrderGetDouble(ticket, ORDER_SL)) + ","
              + "\"take_profit\":" + JsonNullableNumber(HistoryOrderGetDouble(ticket, ORDER_TP)) + ","
              + "\"state\":\"" + (string)state + "\","
              + "\"occurred_at\":\"" + UtcIso((datetime)HistoryOrderGetInteger(ticket, ORDER_TIME_SETUP)) + "\"}";
   }
   json += "]";
   return true;
}

bool BuildDeals(string &json)
{
   int total = HistoryDealsTotal();
   if(total > MAX_HISTORY_RECORDS)
   {
      Print("MT5 deal history exceeds the API batch limit; narrow HistoryDays before syncing.");
      return false;
   }

   json = "[";
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      long type = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL)
         continue;
      string entry_type = DealEntryName(HistoryDealGetInteger(ticket, DEAL_ENTRY));
      if(entry_type == "")
      {
         PrintFormat("Unsupported MT5 deal entry type for deal %I64u.", ticket);
         return false;
      }
      if(StringLen(json) > 1)
         json += ",";

      long position_id = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      long order_id = HistoryDealGetInteger(ticket, DEAL_ORDER);
      string symbol = JsonEscape(HistoryDealGetString(ticket, DEAL_SYMBOL));
      json += "{\"external_deal_id\":\"" + (string)ticket + "\","
              + "\"position_identifier\":" + (position_id > 0 ? "\"" + (string)position_id + "\"" : "null") + ","
              + "\"external_order_id\":" + (order_id > 0 ? "\"" + (string)order_id + "\"" : "null") + ","
              + "\"entry_type\":\"" + entry_type + "\","
              + "\"symbol\":\"" + symbol + "\","
              + "\"direction\":\"" + DirectionName(type) + "\","
              + "\"volume\":" + JsonNumber(HistoryDealGetDouble(ticket, DEAL_VOLUME)) + ","
              + "\"price\":" + JsonNumber(HistoryDealGetDouble(ticket, DEAL_PRICE)) + ","
              + "\"pnl\":" + JsonNumber(HistoryDealGetDouble(ticket, DEAL_PROFIT)) + ","
              + "\"commission\":" + JsonNumber(HistoryDealGetDouble(ticket, DEAL_COMMISSION)) + ","
              + "\"swap\":" + JsonNumber(HistoryDealGetDouble(ticket, DEAL_SWAP)) + ","
              + "\"occurred_at\":\"" + UtcIso((datetime)HistoryDealGetInteger(ticket, DEAL_TIME)) + "\"}";
   }
   json += "]";
   return true;
}

bool BuildPositions(string &json)
{
   int total = PositionsTotal();
   if(total > MAX_POSITIONS)
   {
      Print("Open position count exceeds the API batch limit.");
      return false;
   }

   json = "[";
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(StringLen(json) > 1)
         json += ",";
      string symbol = JsonEscape(PositionGetString(POSITION_SYMBOL));
      long position_id = PositionGetInteger(POSITION_IDENTIFIER);
      json += "{\"external_position_id\":\"" + (string)ticket + "\","
              + "\"position_identifier\":\"" + (string)position_id + "\","
              + "\"symbol\":\"" + symbol + "\","
              + "\"direction\":\"" + DirectionName(PositionGetInteger(POSITION_TYPE)) + "\","
              + "\"volume\":" + JsonNumber(PositionGetDouble(POSITION_VOLUME)) + ","
              + "\"entry_price\":" + JsonNumber(PositionGetDouble(POSITION_PRICE_OPEN)) + ","
              + "\"current_price\":" + JsonNumber(PositionGetDouble(POSITION_PRICE_CURRENT)) + ","
              + "\"stop_loss\":" + JsonNullableNumber(PositionGetDouble(POSITION_SL)) + ","
              + "\"take_profit\":" + JsonNullableNumber(PositionGetDouble(POSITION_TP)) + ","
              + "\"floating_pnl\":" + JsonNumber(PositionGetDouble(POSITION_PROFIT)) + ","
              + "\"state\":\"open\","
              + "\"observed_at\":\"" + UtcIso(TimeCurrent()) + "\"}";
   }
   json += "]";
   return true;
}

bool BuildSyncPayload(string sync_run_id, string &payload)
{
   datetime end_time = TimeCurrent();
   datetime start_time = end_time - (datetime)(HistoryDays * 86400);
   if(!HistorySelect(start_time, end_time))
   {
      PrintFormat("Could not select MT5 history: %d", GetLastError());
      return false;
   }

   string orders;
   string deals;
   string positions;
   if(!BuildOrders(orders) || !BuildDeals(deals) || !BuildPositions(positions))
      return false;

   string observed_at = UtcIso(end_time);
   payload = "{\"sync_run_id\":\"" + JsonEscape(sync_run_id) + "\","
             + "\"external_account_id\":\"" + (string)AccountInfoInteger(ACCOUNT_LOGIN) + "\","
             + "\"orders\":" + orders + ","
             + "\"deals\":" + deals + ","
             + "\"positions\":" + positions + ","
             + "\"snapshot\":{"
             + "\"balance\":" + JsonNumber(AccountInfoDouble(ACCOUNT_BALANCE)) + ","
             + "\"equity\":" + JsonNumber(AccountInfoDouble(ACCOUNT_EQUITY)) + ","
             + "\"margin\":" + JsonNumber(AccountInfoDouble(ACCOUNT_MARGIN)) + ","
             + "\"free_margin\":" + JsonNumber(AccountInfoDouble(ACCOUNT_MARGIN_FREE)) + ","
             + "\"observed_at\":\"" + observed_at + "\"}}";
   return true;
}

void ReportSyncFailure(string sync_run_id, string message)
{
   string response;
   int status_code;
   string body = "{\"sync_run_id\":\"" + JsonEscape(sync_run_id)
                 + "\",\"error\":\"" + JsonEscape(message) + "\"}";
   ApiRequest("POST",
              "/api/v1/connectors/mt5/accounts/" + AccountId + "/sync-failure",
              body,
              response,
              status_code);
}

void ProcessSyncRequest()
{
   string response;
   int status_code;
   string path = "/api/v1/connectors/mt5/accounts/" + AccountId + "/sync-request";
   if(!ApiRequest("GET", path, "", response, status_code))
      return;

   string sync_run_id = SyncRunIdFromResponse(response);
   if(sync_run_id == "")
      return;

   string payload;
   if(!BuildSyncPayload(sync_run_id, payload))
   {
      ReportSyncFailure(sync_run_id, "Could not collect a complete MT5 history snapshot.");
      return;
   }

   if(!ApiRequest("POST",
                  "/api/v1/connectors/mt5/accounts/" + AccountId + "/sync",
                  payload,
                  response,
                  status_code))
   {
      ReportSyncFailure(sync_run_id, "The MT5 sync payload could not be accepted by the API.");
      return;
   }
   PrintFormat("MT5 sync completed: %s", sync_run_id);
}

int OnInit()
{
   if(StringLen(AccountId) == 0 || StringLen(ConnectorToken) == 0)
   {
      Print("AccountId and ConnectorToken must be configured.");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(PollSeconds < 5 || HistoryDays < 1 || HistoryDays > 3650)
   {
      Print("PollSeconds must be at least 5 and HistoryDays must be between 1 and 3650.");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(!EventSetTimer(PollSeconds))
   {
      PrintFormat("Could not start the MT5 polling timer: %d", GetLastError());
      return INIT_FAILED;
   }
   Print("MofyAlly EDGE MT5 observer started in read-only mode.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ProcessSyncRequest();
}

void OnTick()
{
}
