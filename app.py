import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="BrandStreet", layout="wide", page_icon="📈")

# Connect to Supabase (Reads secrets from Streamlit Cloud)
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 2. SIDEBAR (User Profile) ---
st.sidebar.title("BrandStreet 🐂")

# Simulating Login for MVP (Users just pick their name)
# In a real app, you'd use a password, but this is fine for a prototype
users = supabase.table('profiles').select("*").execute().data
user_map = {u['username']: u for u in users} if users else {}

selected_username = st.sidebar.selectbox("Login as:", options=list(user_map.keys()))

if selected_username:
    current_user = user_map[selected_username]
    st.sidebar.divider()
    st.sidebar.metric("Your Points", f"{current_user['points_balance']:,}")
    st.sidebar.caption(f"Rank: {current_user['rank_title']}")

# --- 3. MAIN DASHBOARD ---
st.title("Marketplace")
st.markdown("Trade reputation on India's top brands.")

# Fetch Live Brand Data
brands_response = supabase.table('brands').select("*").order('bes_score', desc=True).execute()
df = pd.DataFrame(brands_response.data)

# Visual Tweaks
if not df.empty:
    # We display the data as a clean interactive table
    # Users can search and sort this table automatically
    st.dataframe(
        df[['name', 'sector', 'bes_score', 'growth_pop', 'tribe']],
        column_config={
            "name": "Brand",
            "bes_score": st.column_config.ProgressColumn(
                "BES Score", format="%.1f", min_value=0, max_value=100
            ),
            "growth_pop": st.column_config.NumberColumn(
                "Growth (PoP)", format="%.1f%%"
            ),
        },
        use_container_width=True,
        hide_index=True
    )

    # --- 4. STAKING ACTION ---
    st.divider()
    st.subheader("Make a Trade")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        target_brand_name = st.selectbox("Select Brand", options=df['name'].tolist())
    
    with col2:
        stake_amount = st.number_input("Points to Stake", min_value=100, step=100, value=100)
        
    with col3:
        thesis = st.selectbox("Thesis", ["Hype 🚀", "Quality 💎", "Trust 🛡️", "Value 📉"])

    if st.button("Confirm Stake", type="primary"):
        # Logic: 
        # 1. Get Brand ID
        brand_row = df[df['name'] == target_brand_name].iloc[0]
        
        # 2. Check Balance
        if current_user['points_balance'] >= stake_amount:
            # 3. Deduct Points
            new_balance = current_user['points_balance'] - stake_amount
            supabase.table('profiles').update({'points_balance': new_balance}).eq('id', current_user['id']).execute()
            
            # 4. Create Ledger Entry
            supabase.table('ledger').insert({
                "user_id": current_user['id'],
                "brand_id": brand_row['id'],
                "amount_staked": stake_amount,
                "entry_bes": float(brand_row['bes_score']),
                "thesis_tag": thesis
            }).execute()
            
            st.success(f"Success! Staked {stake_amount} on {target_brand_name}. Refreshing...")
            st.rerun()
        else:
            st.error("Insufficient Funds!")

else:
    st.warning("No brands found in database.")
