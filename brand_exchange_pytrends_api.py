import os
import json
import pandas as pd
import gspread
import time
import random
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from pytrends.request import TrendReq
from supabase import create_client, Client

# --- 1. SETUP & AUTHENTICATION ---
print("--- Starting BrandStreet Engine ---")

# Google Sheets Auth
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
json_creds = os.environ['GCP_CREDENTIALS']
creds_dict = json.loads(json_creds)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)

# Supabase Auth
supa_url = os.environ['SUPABASE_URL']
supa_key = os.environ['SUPABASE_KEY']
supabase: Client = create_client(supa_url, supa_key)

# Configuration
SHEET_NAME = "BrandStreet_Seed_Data"
ANCHOR_KEYWORD = "Nifty 50"

# --- 2. READ SHEET DATA ---
try:
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
    raw_data = worksheet.get_all_records()
    df = pd.DataFrame(raw_data)
    
    if df.empty:
        print("Sheet is empty. Exiting.")
        exit()
        
    print(f"Loaded {len(df)} brands from Sheet.")
    
except Exception as e:
    print(f"Error reading sheet: {e}")
    exit()

# --- 3. FETCH ENGINE (Google Trends) ---
pytrends = TrendReq(hl='en-IN', tz=330)

def get_growth_metrics(keywords):
    metrics_map = {}
    
    # Batching to avoid rate limits
    chunk_size = 4
    chunks = [keywords[i:i + chunk_size] for i in range(0, len(keywords), chunk_size)]
    
    print(f"Fetching data for {len(keywords)} brands...")
    
    for i, batch in enumerate(chunks):
        query_list = list(set([ANCHOR_KEYWORD] + batch))
        
        try:
            # Fetch 12 Months (Weekly Data)
            pytrends.build_payload(query_list, cat=0, timeframe='today 12-m', geo='IN', gprop='')
            data = pytrends.interest_over_time()
            
            if data.empty: continue
            
            # Normalize against Anchor
            data[ANCHOR_KEYWORD] = data[ANCHOR_KEYWORD].replace(0, 1)
            
            for kw in batch:
                if kw in data.columns:
                    norm_series = (data[kw] / data[ANCHOR_KEYWORD]) * 50
                    
                    # Logic: Ensure we have enough data
                    if len(norm_series) >= 52:
                        curr = norm_series.iloc[-2:].mean()
                        prev = norm_series.iloc[-4:-2].mean()
                        yoy_val = norm_series.iloc[:2].mean()
                        
                        pop = ((curr - prev) / prev) * 100 if prev > 0 else 0
                        yoy = ((curr - yoy_val) / yoy_val) * 100 if yoy_val > 0 else 0
                        
                        metrics_map[kw] = {"Volume": round(curr, 2), "PoP": round(pop, 2), "YoY": round(yoy, 2)}
                    else:
                        metrics_map[kw] = {"Volume": 0, "PoP": 0, "YoY": 0}
                        
        except Exception as e:
            print(f"Error on batch {i}: {e}")
            time.sleep(60)
            
        time.sleep(random.randint(5, 10))
        
    return metrics_map

# Run the Fetch
keywords_list = df['Google Keyword'].tolist()
results = get_growth_metrics(keywords_list)

# --- 4. UPDATE GOOGLE SHEET & SUPABASE ---
print("\n--- Syncing Data ---")

# Prepare Sheet Update
headers = worksheet.row_values(1)
try:
    col_vol = headers.index("Volume (14-Day Avg)") + 1
    col_pop = headers.index("Growth PoP %") + 1
    col_yoy = headers.index("Growth YoY %") + 1
    col_time = headers.index("Last Updated") + 1
except ValueError:
    print("Error: Columns missing in Sheet.")
    exit()

sheet_updates = []
supabase_upserts = []
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

for index, row in df.iterrows():
    kw = row['Google Keyword']
    row_num = index + 2
    
    if kw in results:
        data = results[kw]
        
        # A. Prepare Sheet Batch Update
        sheet_updates.append({'range': gspread.utils.rowcol_to_a1(row_num, col_vol), 'values': [[data['Volume']]]})
        sheet_updates.append({'range': gspread.utils.rowcol_to_a1(row_num, col_pop), 'values': [[data['PoP']]]})
        sheet_updates.append({'range': gspread.utils.rowcol_to_a1(row_num, col_yoy), 'values': [[data['YoY']]]})
        sheet_updates.append({'range': gspread.utils.rowcol_to_a1(row_num, col_time), 'values': [[timestamp]]})
        
        # B. Calculate BES (Replicating Sheet Formula in Python)
        # Formula: (Volume * 0.4) + (PoP * 0.3) + (YoY * 0.1) + 50
        # We cap BES at 0-100 range logically, though technically it can go higher
        raw_bes = (data['Volume'] * 0.4) + (data['PoP'] * 0.3) + (data['YoY'] * 0.1) + 50
        final_bes = round(raw_bes, 2)
        
        # C. Prepare Supabase Upsert Payload
        # We map Sheet Columns -> Supabase Columns
        supabase_upserts.append({
            "google_keyword": kw,         # The Unique ID
            "name": row['Brand Name'],    # Updates name if you changed it in Sheet
            "tribe": row['Tribe'],
            "sector": row['Sector'],
            "volume": data['Volume'],
            "growth_pop": data['PoP'],
            "growth_yoy": data['YoY'],
            "bes_score": final_bes,
            "last_updated": datetime.now().isoformat()
        })

# Execute Sheet Update
if sheet_updates:
    worksheet.batch_update(sheet_updates)
    print(f"Sheet: Updated {len(results)} rows.")

# Execute Supabase Upsert
if supabase_upserts:
    try:
        # .upsert() inserts new rows OR updates existing ones based on the Primary/Unique key
        # We ensure 'google_keyword' is set as Unique in Supabase for this to work perfectly
        response = supabase.table('brands').upsert(supabase_upserts, on_conflict="google_keyword").execute()
        print(f"Supabase: Synced {len(supabase_upserts)} brands.")
    except Exception as e:
        print(f"Supabase Error: {e}")

print("--- Job Complete ---")
