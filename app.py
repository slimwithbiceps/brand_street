import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
import time

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="BrandStreet", page_icon="📈", layout="wide")

# Custom CSS to make it look like a pro fintech app
st.markdown("""
    <style>
    .stMetric {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    .stButton>button {
        width: 100%;
        background-color: #00E676;
        color: black;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONNECT TO DATABASE ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 3. SIDEBAR (LOGIN & PROFILE) ---
st.sidebar.title("BrandStreet 🐂")
st.sidebar.markdown("The NASDAQ of Culture")

# MVP LOGIN SYSTEM (Select User)
# In V2, we will implement Email/Password. For now, we list users from DB.
try:
    users_response = supabase.table('profiles').select("*").execute()
    users = users_response.data
    user_options = {u['email']: u for u in users} if users else {}
    
    selected_email = st.sidebar.selectbox("Simulate Login:", options=list(user_options.keys()))
    
    if selected_email:
        current_user = user_options[selected_email]
        st.sidebar.divider()
        st.sidebar.markdown(f"**Welcome, {current_user.get('username', 'Trader')}**")
        
        # Display Wallet
        st.sidebar.metric(label="Available Points", value=f"{current_user['points_balance']:,}")
        st.sidebar.caption(f"Rank: {current_user.get('rank_title', 'Rookie')}")
        
        # Logout / Reset (Just clears cache for demo)
        if st.sidebar.button("Refresh Data"):
            st.cache_data.clear()
            st.rerun()

except Exception as e:
    st.sidebar.error("Could not connect to User Database.")
    st.sidebar.write(e)
    current_user = None

# --- 4. MAIN TABS ---
if current_user:
    tab1, tab2, tab3 = st.tabs(["🏛️ Marketplace", "💼 My Portfolio", "🏆 Leaderboard"])

    # === TAB 1: MARKETPLACE ===
    with tab1:
        st.header("Live Market")
        
        # Fetch Brands
        brands_response = supabase.table('brands').select("*").order('bes_score', desc=True).execute()
        df_brands = pd.DataFrame(brands_response.data)

        if not df_brands.empty:
            # Metric Columns
            col1, col2, col3 = st.columns(3)
            col1.metric("Market Leader", df_brands.iloc[0]['name'], f"{df_brands.iloc[0]['bes_score']}%")
            col2.metric("Top Gainer (PoP)", f"{df_brands.iloc[0]['growth_pop']}%")
            col3.metric("Total Brands listed", len(df_brands))

            st.divider()

            # Interactive Table
            st.subheader("Trade Desk")
            
            # Configure the Table Display
            st.dataframe(
                df_brands[['name', 'sector', 'bes_score', 'growth_pop', 'tribe']],
                column_config={
                    "name": "Brand",
                    "sector": "Sector",
                    "bes_score": st.column_config.ProgressColumn(
                        "BES Score", format="%.1f", min_value=0, max_value=100
                    ),
                    "growth_pop": st.column_config.NumberColumn(
                        "Momentum (PoP)", format="%.1f%%"
                    ),
                    "tribe": "Tribe"
                },
                use_container_width=True,
                height=400
            )

            # --- STAKING WIDGET ---
            with st.container():
                st.markdown("### ⚡ Quick Stake")
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                
                with c1:
                    target_brand = st.selectbox("Select Asset", df_brands['name'].tolist())
                with c2:
                    stake_amount = st.number_input("Points", min_value=100, step=100, value=100)
                with c3:
                    thesis = st.selectbox("Thesis", ["Hype 🚀", "Quality 💎", "Trust 🛡️", "Value 📉"])
                with c4:
                    st.write("") # Spacer
                    st.write("") # Spacer
                    if st.button("Confirm Trade"):
                        # TRADE LOGIC
                        if current_user['points_balance'] >= stake_amount:
                            # 1. Get Brand Data
                            brand_data = df_brands[df_brands['name'] == target_brand].iloc[0]
                            
                            # 2. Insert to Ledger
                            trade_payload = {
                                "user_id": current_user['id'],
                                "brand_id": brand_data['id'],
                                "amount_staked": stake_amount,
                                "entry_bes": float(brand_data['bes_score']),
                                "thesis_tag": thesis
                            }
                            supabase.table('ledger').insert(trade_payload).execute()
                            
                            # 3. Deduct Balance
                            new_bal = current_user['points_balance'] - stake_amount
                            supabase.table('profiles').update({'points_balance': new_bal}).eq('id', current_user['id']).execute()
                            
                            st.success(f"Successfully staked {stake_amount} on {target_brand}!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Insufficient Funds!")

    # === TAB 2: PORTFOLIO ===
    with tab2:
        st.header("Your Holdings")
        
        # Fetch Ledger for this user
        ledger_response = supabase.table('ledger').select("*, brands(name, bes_score)").eq('user_id', current_user['id']).execute()
        
        if ledger_response.data:
            df_ledger = pd.DataFrame(ledger_response.data)
            
            # Flatten the nested 'brands' data
            df_ledger['Brand'] = df_ledger['brands'].apply(lambda x: x['name'])
            df_ledger['Current BES'] = df_ledger['brands'].apply(lambda x: x['bes_score'])
            
            # Calculate P&L (Simple logic: Current BES vs Entry BES)
            df_ledger['P&L %'] = ((df_ledger['Current BES'] - df_ledger['entry_bes']) / df_ledger['entry_bes']) * 100
            
            # Display
            st.dataframe(
                df_ledger[['Brand', 'amount_staked', 'thesis_tag', 'entry_bes', 'Current BES', 'P&L %']],
                column_config={
                    "P&L %": st.column_config.NumberColumn("Yield", format="%.2f%%")
                },
                use_container_width=True
            )
        else:
            st.info("You haven't made any trades yet. Go to the Marketplace!")

    # === TAB 3: LEADERBOARD ===
    with tab3:
        st.header("Top Traders")
        # Simple query fetching top balances
        leaders = supabase.table('profiles').select("username, points_balance, rank_title").order('points_balance', desc=True).limit(10).execute()
        df_leaders = pd.DataFrame(leaders.data)
        st.table(df_leaders)

else:
    st.warning("Please create a user in your Supabase 'profiles' table first to login.")
