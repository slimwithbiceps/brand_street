import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
import time

# --- 1. CONFIG & STYLE ---
st.set_page_config(page_title="BrandStreet", page_icon="📈", layout="wide")
st.markdown("""
    <style>
    .stMetric { background-color: #1E1E1E; padding: 10px; border-radius: 8px; border: 1px solid #333; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1.1rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE CONNECT ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 3. SIDEBAR (USER) ---
st.sidebar.title("BrandStreet 🐂")
current_user = None

try:
    users = supabase.table('profiles').select("*").execute().data
    if users:
        user_options = {u['email']: u for u in users}
        selected_email = st.sidebar.selectbox("Login as:", list(user_options.keys()))
        if selected_email:
            current_user = user_options[selected_email]
            st.sidebar.divider()
            st.sidebar.metric("Your Balance", f"{current_user['points_balance']:,}")
            st.sidebar.caption(f"Rank: {current_user.get('rank_title', 'Analyst')}")
            if st.sidebar.button("🔄 Refresh"):
                st.cache_data.clear()
                st.rerun()
except:
    st.sidebar.warning("DB Connection Error")

# --- 4. MAIN APP ---
if current_user:
    tab1, tab2, tab3 = st.tabs(["🏛️ Live Market", "💼 Portfolio", "🏆 Leaderboard"])

    # === TAB 1: THE MARKET ===
    with tab1:
        # A. FETCH DATA
        response = supabase.table('brands').select("*").order('bes_score', desc=True).execute()
        df = pd.DataFrame(response.data)

        if df.empty:
            st.warning("⚠️ Market is empty! Run your Python Data Engine to seed the database.")
        else:
            # B. MARKET MAP (THE CHART)
            st.subheader("Market Map")
            # Treemap: Size = Market Cap (simulated by Volume), Color = BES Score
            fig = px.treemap(
                df, 
                path=[px.Constant("India"), 'sector', 'name'], 
                values='bes_score',
                color='growth_pop',
                color_continuous_scale='RdYlGn',
                color_continuous_midpoint=0,
                hover_data=['bes_score', 'tribe'],
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

            st.divider()

            # C. TRADING DESK
            st.subheader("Trading Desk")
            
            c1, c2 = st.columns([1, 2])
            
            with c1:
                # Brand Selector
                selected_brand_name = st.selectbox("Select Asset", df['name'].tolist())
                brand_data = df[df['name'] == selected_brand_name].iloc[0]
                
                # Show Brand Vitals
                st.metric("BES Score", f"{brand_data['bes_score']}", delta=f"{brand_data['growth_pop']}%")
                st.caption(f"Sector: {brand_data['sector']} | Tribe: {brand_data['tribe']}")

            with c2:
                # Buy / Sell Toggle
                action = st.radio("Action", ["Buy (Stake)", "Sell (Liquidate)"], horizontal=True)
                
                if "Buy" in action:
                    # BUY LOGIC
                    amount = st.number_input("Amount to Stake", min_value=100, step=100)
                    thesis = st.selectbox("Why?", ["Hype 🚀", "Quality 💎", "Trust 🛡️", "Value 📉"])
                    
                    if st.button("Confirm Stake", type="primary"):
                        if current_user['points_balance'] >= amount:
                            # 1. Update Ledger
                            supabase.table('ledger').insert({
                                "user_id": current_user['id'],
                                "brand_id": brand_data['id'],
                                "amount_staked": amount,
                                "entry_bes": float(brand_data['bes_score']),
                                "thesis_tag": thesis,
                                "status": "ACTIVE"
                            }).execute()
                            # 2. Update Balance
                            new_bal = current_user['points_balance'] - amount
                            supabase.table('profiles').update({'points_balance': new_bal}).eq('id', current_user['id']).execute()
                            st.success(f"Staked {amount} on {selected_brand_name}!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Insufficient funds!")
                
                else:
                    # SELL LOGIC
                    # 1. Check Holdings
                    holdings = supabase.table('ledger').select("*").eq('user_id', current_user['id']).eq('brand_id', brand_data['id']).eq('status', 'ACTIVE').execute().data
                    total_invested = sum([h['amount_staked'] for h in holdings])
                    
                    st.info(f"You currently have **{total_invested} points** staked in {selected_brand_name}.")
                    
                    if total_invested > 0:
                        sell_amount = st.number_input("Amount to Sell", min_value=0, max_value=total_invested, step=100)
                        
                        if st.button("Confirm Sell"):
                            # Logic: We credit the user back. 
                            # MVP Simplification: We don't partial-close specific rows yet, we just credit user and mark latest rows as CLOSED.
                            
                            # 1. Credit User
                            # In real game, we apply Profit/Loss formula here. 
                            # MVP: You get back exactly what you put in (or +10% if BES is higher)
                            # Let's keep it simple: Return Principal.
                            refund = sell_amount 
                            new_bal = current_user['points_balance'] + refund
                            supabase.table('profiles').update({'points_balance': new_bal}).eq('id', current_user['id']).execute()
                            
                            # 2. Update Ledger (Mark as Closed)
                            # This is complex in SQL, so for MVP we insert a 'SELL' record
                            supabase.table('ledger').insert({
                                "user_id": current_user['id'],
                                "brand_id": brand_data['id'],
                                "amount_staked": -sell_amount, # Negative to show sell
                                "entry_bes": float(brand_data['bes_score']),
                                "thesis_tag": "CASH_OUT",
                                "status": "CLOSED"
                            }).execute()
                            
                            st.success(f"Sold {sell_amount}! Points refunded.")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.warning("You don't own any of this asset.")

    # === TAB 2: PORTFOLIO ===
    with tab2:
        st.header("Your Portfolio")
        ledger = supabase.table('ledger').select("*, brands(name)").eq('user_id', current_user['id']).order('created_at', desc=True).execute().data
        
        if ledger:
            df_l = pd.DataFrame(ledger)
            df_l['Brand'] = df_l['brands'].apply(lambda x: x['name'])
            # Color code Buy vs Sell
            st.dataframe(df_l[['created_at', 'Brand', 'amount_staked', 'thesis_tag', 'entry_bes']], use_container_width=True)
        else:
            st.info("No trades yet.")

else:
    st.warning("Please login via the sidebar.")
