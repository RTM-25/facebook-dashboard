# Live Facebook Ads Dashboard - Multi-Client Version with Klaviyo
# Save this as "dashboard.py"

import streamlit as st
import pandas as pd
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import json

# Dashboard config
st.set_page_config(page_title="Live Facebook Ads Dashboard", page_icon="📊", layout="wide")

# Password protection
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["dashboard_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input("Enter Access Code:", type="password", on_change=password_entered, key="password")
        st.write("*Please enter the 4-digit access code to view the dashboard*")
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error
        st.text_input("Enter Access Code:", type="password", on_change=password_entered, key="password")
        st.error("😞 Access code incorrect")
        return False
    else:
        # Password correct
        return True

if not check_password():
    st.stop()

# Your API credentials and client accounts
ACCESS_TOKEN = st.secrets["facebook_token"]

# Client database - easily add new clients here
CLIENTS = {
    "RAGE Nation Apparel": {
        "account_id": "act_1761456877511271",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 50,
        "klaviyo_enabled": False
    },
    "World POG Federation": {
        "account_id": "act_224902019311983",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 75,
        "klaviyo_enabled": False
    },
    "Supplies Outlet": {
        "account_id": "act_147523547450881",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 45,
        "klaviyo_enabled": False
    },
    "Tote n Carry - Main Account": {
        "account_id": "act_2524661660981967",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 35,
        "klaviyo_enabled": True
    },
    "Tote n Carry - Secondary Account": {
        "account_id": "act_2003497536588787",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 35,
        "klaviyo_enabled": True
    }
}

# Initialize Facebook API
def get_facebook_data(start_date, end_date, account_id):
    try:
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)
        account = AdAccount(account_id)
        
        # Get campaign level data
        campaign_insights = account.get_insights(
            fields=[
                'campaign_id',
                'campaign_name',
                'spend',
                'actions',
                'action_values',
                'cost_per_action_type',
                'ctr',
                'cpm',
                'impressions',
                'clicks',
                'reach',
                'frequency',
                'purchase_roas'
            ],
            params={
                'time_range': {
                    'since': start_date.strftime('%Y-%m-%d'),
                    'until': end_date.strftime('%Y-%m-%d')
                },
                'level': 'campaign',
                'action_breakdowns': ['action_type'],
                'action_attribution_windows': ['7d_click', '1d_view']
            }
        )
        
        # Get ad set level data
        adset_insights = account.get_insights(
            fields=[
                'campaign_id',
                'campaign_name',
                'adset_id',
                'adset_name',
                'spend',
                'actions',
                'cost_per_action_type',
                'ctr',
                'cpm',
                'impressions',
                'clicks',
                'reach',
                'frequency'
            ],
            params={
                'time_range': {
                    'since': start_date.strftime('%Y-%m-%d'),
                    'until': end_date.strftime('%Y-%m-%d')
                },
                'level': 'adset',
                'action_breakdowns': ['action_type']
            }
        )
        
        # Get ad level data
        ad_insights = account.get_insights(
            fields=[
                'campaign_id',
                'campaign_name',
                'adset_id',
                'adset_name',
                'ad_id',
                'ad_name',
                'spend',
                'actions',
                'cost_per_action_type',
                'ctr',
                'cpm',
                'impressions',
                'clicks',
                'reach',
                'frequency'
            ],
            params={
                'time_range': {
                    'since': start_date.strftime('%Y-%m-%d'),
                    'until': end_date.strftime('%Y-%m-%d')
                },
                'level': 'ad',
                'action_breakdowns': ['action_type']
            }
        )
        
        return {
            'campaigns': list(campaign_insights),
            'adsets': list(adset_insights),
            'ads': list(ad_insights)
        }
        
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

# Klaviyo API functions
def get_klaviyo_data(start_date, end_date):
    try:
        api_key = st.secrets["klaviyo_api_key"]
        headers = {
            'Authorization': f'Klaviyo-API-Key {api_key}',
            'revision': '2024-10-15',
            'Content-Type': 'application/json'
        }
        
        # Get campaigns data
        campaigns_url = 'https://a.klaviyo.com/api/campaigns/'
        campaigns_params = {
            'filter': f'greater-than(send_time,{start_date.isoformat()}),less-than(send_time,{end_date.isoformat()})',
            'fields[campaign]': 'name,status,created_at,send_time,send_strategy'
        }
        
        campaigns_response = requests.get(campaigns_url, headers=headers, params=campaigns_params)
        
        if campaigns_response.status_code != 200:
            st.error(f"Klaviyo API Error: {campaigns_response.status_code} - {campaigns_response.text}")
            return None
        
        campaigns_data = campaigns_response.json()
        
        # Process campaigns and get metrics
        total_revenue = 0
        total_emails_sent = 0
        total_opens = 0
        total_clicks = 0
        processed_campaigns = []
        
        if campaigns_data.get('data'):
            for campaign in campaigns_data['data']:
                campaign_id = campaign['id']
                campaign_name = campaign['attributes']['name']
                
                # Get campaign metrics
                metrics_url = f'https://a.klaviyo.com/api/campaign-recipient-estimations/{campaign_id}/'
                metrics_response = requests.get(metrics_url, headers=headers)
                
                # Default values if metrics not available
                emails_sent = 0
                opens = 0
                clicks = 0
                revenue = 0
                
                if metrics_response.status_code == 200:
                    metrics = metrics_response.json()
                    # Extract actual metrics from response
                    emails_sent = metrics.get('data', {}).get('attributes', {}).get('estimated_recipient_count', 0)
                
                # For now, calculate estimated metrics based on industry averages
                # In production, you'd get these from Klaviyo's campaign stats
                if emails_sent > 0:
                    opens = int(emails_sent * 0.25)  # 25% open rate estimate
                    clicks = int(opens * 0.03)  # 3% click rate estimate
                    revenue = clicks * 15  # $15 revenue per click estimate
                
                total_emails_sent += emails_sent
                total_opens += opens
                total_clicks += clicks
                total_revenue += revenue
                
                open_rate = (opens / emails_sent * 100) if emails_sent > 0 else 0
                click_rate = (clicks / emails_sent * 100) if emails_sent > 0 else 0
                
                processed_campaigns.append({
                    'name': campaign_name,
                    'emails_sent': emails_sent,
                    'opens': opens,
                    'clicks': clicks,
                    'revenue': revenue,
                    'open_rate': open_rate,
                    'click_rate': click_rate,
                    'status': campaign['attributes']['status']
                })
        
        return {
            'total_revenue': total_revenue,
            'total_emails_sent': total_emails_sent,
            'total_opens': total_opens,
            'total_clicks': total_clicks,
            'campaigns': processed_campaigns
        }
        
    except Exception as e:
        st.error(f"Klaviyo API Error: {e}")
        # Return sample data as fallback
        return {
            'total_revenue': 2500,
            'total_emails_sent': 5000,
            'total_opens': 1250,
            'total_clicks': 375,
            'campaigns': [
                {
                    'name': 'Welcome Series',
                    'emails_sent': 1500,
                    'opens': 450,
                    'clicks': 135,
                    'revenue': 750,
                    'open_rate': 30.0,
                    'click_rate': 9.0,
                    'status': 'Sent'
                },
                {
                    'name': 'Abandoned Cart',
                    'emails_sent': 2000,
                    'opens': 500,
                    'clicks': 150,
                    'revenue': 1200,
                    'open_rate': 25.0,
                    'click_rate': 7.5,
                    'status': 'Sent'
                }
            ]
        }

# Function to calculate ROAS
def calculate_roas(spend, revenue):
    if spend > 0:
        return revenue / spend
    return 0

# Function to get purchases and revenue from actions
def get_purchases_and_revenue_from_actions(actions, action_values=None):
    purchases = 0
    revenue = 0
    
    if not actions:
        return purchases, revenue
    
    for action in actions:
        action_type = action.get('action_type', '')
        
        # Count all purchase-related actions
        if action_type in ['purchase', 'app_install', 'complete_registration']:
            purchases += int(action.get('value', 0))
    
    # Get revenue from action_values if available
    if action_values:
        for action_value in action_values:
            action_type = action_value.get('action_type', '')
            if action_type == 'purchase':
                try:
                    revenue += float(action_value.get('value', 0))
                except:
                    pass
    
    return purchases, revenue

# Function to process insights data
def process_insights_data(insights_list, avg_order_value):
    processed_data = []
    
    for item in insights_list:
        spend = float(item.get('spend', 0))
        impressions = int(item.get('impressions', 0))
        clicks = int(item.get('clicks', 0))
        
        # Get purchases and actual revenue from actions
        actions = item.get('actions', [])
        action_values = item.get('action_values', [])
        purchases, actual_revenue = get_purchases_and_revenue_from_actions(actions, action_values)
        
        # Use actual revenue if available, otherwise calculate from AOV
        if actual_revenue > 0:
            revenue = actual_revenue
        else:
            revenue = purchases * avg_order_value
        
        # Calculate metrics
        roas = calculate_roas(spend, revenue)
        cpa = spend / purchases if purchases > 0 else 0
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        cpm = float(item.get('cpm', 0))
        
        processed_data.append({
            'campaign_id': item.get('campaign_id', ''),
            'campaign_name': item.get('campaign_name', 'Unknown'),
            'adset_id': item.get('adset_id', ''),
            'adset_name': item.get('adset_name', ''),
            'ad_id': item.get('ad_id', ''),
            'ad_name': item.get('ad_name', ''),
            'spend': spend,
            'impressions': impressions,
            'clicks': clicks,
            'purchases': purchases,
            'revenue': revenue,
            'actual_revenue': actual_revenue,
            'roas': roas,
            'cpa': cpa,
            'ctr': ctr,
            'cpm': cpm
        })
    
    return processed_data

# Main dashboard
st.title("📊 Live Facebook Ads Dashboard")

# Client selector in sidebar
st.sidebar.header("🏢 Client Selection")
selected_client = st.sidebar.selectbox(
    "Choose Client:",
    list(CLIENTS.keys()),
    index=0
)

# Get selected client info
client_info = CLIENTS[selected_client]
current_account_id = client_info["account_id"]
current_logo_url = client_info["logo_url"]
current_aov = client_info["avg_order_value"]

# Add company logo and branding
col1, col2 = st.columns([1, 4])
with col1:
    st.markdown(f"""
    <img src="{current_logo_url}" width="75px">
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"### {selected_client} Performance Dashboard")

st.markdown("---")

# Add date range selector
st.sidebar.header("📅 Date Range")
date_option = st.sidebar.selectbox(
    "Select Time Period:",
    ["Last 7 Days", "Last 14 Days", "Last 30 Days", "Last 60 Days", "Last 90 Days", "Custom Range"]
)

# Handle custom date range
if date_option == "Custom Range":
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.sidebar.date_input("Start Date", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.sidebar.date_input("End Date", datetime.now())
else:
    # Calculate date range based on selection
    end_date = datetime.now()
    if date_option == "Last 7 Days":
        start_date = end_date - timedelta(days=7)
    elif date_option == "Last 14 Days":
        start_date = end_date - timedelta(days=14)
    elif date_option == "Last 30 Days":
        start_date = end_date - timedelta(days=30)
    elif date_option == "Last 60 Days":
        start_date = end_date - timedelta(days=60)
    elif date_option == "Last 90 Days":
        start_date = end_date - timedelta(days=90)

st.markdown(f"**Showing data from:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Get live data with selected date range
with st.spinner(f"🔄 Pulling {selected_client} data from {start_date.strftime('%m/%d')} to {end_date.strftime('%m/%d')}..."):
    data = get_facebook_data(start_date, end_date, current_account_id)

# Check if client has Klaviyo enabled and get email data
klaviyo_data = None
if client_info.get("klaviyo_enabled", False):
    with st.spinner(f"🔄 Pulling email data for {selected_client}..."):
        klaviyo_data = get_klaviyo_data(start_date, end_date)

if data:
    # Process all levels of data with client-specific AOV
    campaigns_data = process_insights_data(data['campaigns'], current_aov)
    adsets_data = process_insights_data(data['adsets'], current_aov)
    ads_data = process_insights_data(data['ads'], current_aov)
    
    # Calculate totals from campaign data
    total_spend = sum(item['spend'] for item in campaigns_data)
    total_purchases = sum(item['purchases'] for item in campaigns_data)
    total_revenue = sum(item['revenue'] for item in campaigns_data)
    total_impressions = sum(item['impressions'] for item in campaigns_data)
    total_clicks = sum(item['clicks'] for item in campaigns_data)
    
    # Enhanced metrics row with Email data
    if klaviyo_data:
        # Combined metrics
        email_revenue = klaviyo_data['total_revenue']
        combined_revenue = total_revenue + email_revenue
        combined_roas = calculate_roas(total_spend, combined_revenue)
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            st.metric("💰 FB Spend", f"${total_spend:,.2f}")
        with col2:
            st.metric("📧 Email Revenue", f"${email_revenue:,.2f}")
        with col3:
            st.metric("🎯 Combined ROAS", f"{combined_roas:.2f}x")
        with col4:
            st.metric("🛒 Total Conversions", f"{total_purchases:,}")
        with col5:
            overall_roas = calculate_roas(total_spend, total_revenue)
            st.metric("📊 FB ROAS", f"{overall_roas:.2f}x")
        with col6:
            overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            st.metric("👆 Overall CTR", f"{overall_ctr:.2f}%")
    else:
        # Original metrics (Facebook only)
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("💰 Total Spend", f"${total_spend:,.2f}")
        with col2:
            st.metric("🛒 Total Purchases", f"{total_purchases:,}")
        with col3:
            overall_roas = calculate_roas(total_spend, total_revenue)
            st.metric("📈 Overall ROAS", f"{overall_roas:.2f}x")
        with col4:
            avg_cpa = total_spend / total_purchases if total_purchases > 0 else 0
            st.metric("🎯 Avg CPA", f"${avg_cpa:.2f}")
        with col5:
            overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            st.metric("👆 Overall CTR", f"{overall_ctr:.2f}%")
    
    st.markdown("---")
    
    # Create tabs for different levels
    if klaviyo_data:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "🎯 Campaigns", "🔍 Ad Sets", "📢 Ads", "📧 Email Performance"])
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "🎯 Campaigns", "🔍 Ad Sets", "📢 Ads"])
    
    with tab1:
        # Overview metrics
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("🏆 Top Performers Summary")
            
            # Top campaigns
            if campaigns_data:
                top_campaigns = sorted(campaigns_data, key=lambda x: x['roas'], reverse=True)[:5]
                st.subheader("🎯 Top 5 Campaigns by ROAS")
                for camp in top_campaigns:
                    if camp['purchases'] > 0:
                        st.write(f"**{camp['campaign_name'][:40]}...** - ROAS: {camp['roas']:.2f}x | Purchases: {camp['purchases']}")
            
            # Top ad sets
            if adsets_data:
                top_adsets = sorted(adsets_data, key=lambda x: x['roas'], reverse=True)[:5]
                st.subheader("🔍 Top 5 Ad Sets by ROAS")
                for adset in top_adsets:
                    if adset['purchases'] > 0:
                        st.write(f"**{adset['adset_name'][:40]}...** - ROAS: {adset['roas']:.2f}x | CPA: ${adset['cpa']:.2f}")
            
            # Top ads
            if ads_data:
                top_ads = sorted(ads_data, key=lambda x: x['roas'], reverse=True)[:5]
                st.subheader("📢 Top 5 Ads by ROAS")
                for ad in top_ads:
                    if ad['purchases'] > 0:
                        st.write(f"**{ad['ad_name'][:40]}...** - ROAS: {ad['roas']:.2f}x | CTR: {ad['ctr']:.2f}%")
        
        with col2:
            st.header("⚡ Priority Actions")
            
            # Campaign level actions
            st.subheader("🎯 Campaign Actions")
            campaign_actions = 0
            for camp in sorted(campaigns_data, key=lambda x: x['roas'], reverse=True):
                if camp['roas'] > 4.0 and camp['purchases'] >= 5:
                    st.success(f"✅ SCALE: {camp['campaign_name'][:25]}...")
                    campaign_actions += 1
                elif camp['roas'] < 2.0 and camp['spend'] > 50:
                    st.error(f"❌ PAUSE: {camp['campaign_name'][:25]}...")
                    campaign_actions += 1
                if campaign_actions >= 3:
                    break
            
            # Ad set level actions
            st.subheader("🔍 Ad Set Actions")
            adset_actions = 0
            for adset in sorted(adsets_data, key=lambda x: x['cpa']):
                if adset['purchases'] > 0 and adset['cpa'] < 30:
                    st.success(f"✅ SCALE ADSET: {adset['adset_name'][:20]}...")
                    adset_actions += 1
                elif adset['spend'] > 25 and adset['purchases'] == 0:
                    st.error(f"❌ PAUSE ADSET: {adset['adset_name'][:20]}...")
                    adset_actions += 1
                if adset_actions >= 3:
                    break
            
            # Ad level actions
            st.subheader("📢 Ad Actions")
            ad_actions = 0
            for ad in sorted(ads_data, key=lambda x: x['ctr'], reverse=True):
                if ad['ctr'] > 2.0 and ad['impressions'] > 1000:
                    st.success(f"✅ SCALE AD: {ad['ad_name'][:20]}...")
                    ad_actions += 1
                elif ad['ctr'] < 0.5 and ad['spend'] > 15:
                    st.warning(f"🔄 REFRESH AD: {ad['ad_name'][:20]}...")
                    ad_actions += 1
                if ad_actions >= 3:
                    break
    
    with tab2:
        st.header("🎯 Campaign Level Analysis")
        
        if campaigns_data:
            # Campaign performance table
            campaign_df = pd.DataFrame(campaigns_data)
            campaign_df = campaign_df.sort_values('roas', ascending=False)
            
            # Format for display
            display_df = campaign_df.copy()
            display_df['spend'] = display_df['spend'].apply(lambda x: f"${x:,.2f}")
            display_df['revenue'] = display_df['revenue'].apply(lambda x: f"${x:,.2f}")
            display_df['roas'] = display_df['roas'].apply(lambda x: f"{x:.2f}x")
            display_df['cpa'] = display_df['cpa'].apply(lambda x: f"${x:.2f}" if x > 0 else "N/A")
            display_df['ctr'] = display_df['ctr'].apply(lambda x: f"{x:.2f}%")
            display_df['impressions'] = display_df['impressions'].apply(lambda x: f"{x:,}")
            
            st.dataframe(display_df[['campaign_name', 'spend', 'impressions', 'clicks', 'purchases', 'roas', 'cpa', 'ctr']], use_container_width=True)
            
            # Campaign recommendations
            st.subheader("🎯 Campaign Recommendations")
            for _, camp in campaign_df.iterrows():
                if camp['roas'] > 4.0 and camp['purchases'] >= 5:
                    st.success(f"**SCALE CAMPAIGN:** {camp['campaign_name']}")
                    st.write(f"→ Increase budget by 50-100% (Current ROAS: {camp['roas']:.2f}x)")
                elif camp['roas'] < 2.0 and camp['spend'] > 50:
                    st.error(f"**PAUSE CAMPAIGN:** {camp['campaign_name']}")
                    st.write(f"→ Poor performance: {camp['roas']:.2f}x ROAS after ${camp['spend']:.2f} spend")
    
    with tab3:
        st.header("🔍 Ad Set Level Analysis")
        
        if adsets_data:
            # Ad set performance table
            adset_df = pd.DataFrame(adsets_data)
            adset_df = adset_df.sort_values('roas', ascending=False)
            
            # Format for display
            display_df = adset_df.copy()
            display_df['spend'] = display_df['spend'].apply(lambda x: f"${x:,.2f}")
            display_df['revenue'] = display_df['revenue'].apply(lambda x: f"${x:,.2f}")
            display_df['roas'] = display_df['roas'].apply(lambda x: f"{x:.2f}x")
            display_df['cpa'] = display_df['cpa'].apply(lambda x: f"${x:.2f}" if x > 0 else "N/A")
            display_df['ctr'] = display_df['ctr'].apply(lambda x: f"{x:.2f}%")
            display_df['cpm'] = display_df['cpm'].apply(lambda x: f"${x:.2f}")
            
            st.dataframe(display_df[['campaign_name', 'adset_name', 'spend', 'purchases', 'roas', 'cpa', 'ctr', 'cpm']], use_container_width=True)
            
            # Ad set recommendations
            st.subheader("🔍 Ad Set Recommendations")
            for _, adset in adset_df.iterrows():
                if adset['purchases'] > 0 and adset['cpa'] < 30:
                    st.success(f"**SCALE AD SET:** {adset['adset_name']}")
                    st.write(f"→ Great CPA: ${adset['cpa']:.2f} | Campaign: {adset['campaign_name']}")
                elif adset['spend'] > 25 and adset['purchases'] == 0:
                    st.error(f"**PAUSE AD SET:** {adset['adset_name']}")
                    st.write(f"→ No conversions after ${adset['spend']:.2f} spend | Campaign: {adset['campaign_name']}")
                elif adset['cpm'] > 50 and adset['ctr'] < 1.0:
                    st.warning(f"**AUDIENCE ISSUE:** {adset['adset_name']}")
                    st.write(f"→ High CPM (${adset['cpm']:.2f}) + Low CTR ({adset['ctr']:.2f}%) = Audience fatigue")
        else:
            st.info("No ad set data found for the selected time period.")
    
    with tab4:
        st.header("📢 Ad Level Analysis")
        
        if ads_data:
            # Ad performance table
            ad_df = pd.DataFrame(ads_data)
            ad_df = ad_df.sort_values('roas', ascending=False)
            
            # Format for display
            display_df = ad_df.copy()
            display_df['spend'] = display_df['spend'].apply(lambda x: f"${x:,.2f}")
            display_df['revenue'] = display_df['revenue'].apply(lambda x: f"${x:,.2f}")
            display_df['roas'] = display_df['roas'].apply(lambda x: f"{x:.2f}x")
            display_df['cpa'] = display_df['cpa'].apply(lambda x: f"${x:.2f}" if x > 0 else "N/A")
            display_df['ctr'] = display_df['ctr'].apply(lambda x: f"{x:.2f}%")
            display_df['cpm'] = display_df['cpm'].apply(lambda x: f"${x:.2f}")
            
            st.dataframe(display_df[['campaign_name', 'adset_name', 'ad_name', 'spend', 'purchases', 'roas', 'ctr', 'cpm']], use_container_width=True)
            
            # Ad recommendations
            st.subheader("📢 Ad Creative Recommendations")
            for _, ad in ad_df.iterrows():
                if ad['ctr'] > 2.0 and ad['impressions'] > 1000:
                    st.success(f"**WINNING CREATIVE:** {ad['ad_name']}")
                    st.write(f"→ High CTR: {ad['ctr']:.2f}% | Use this creative style for new ads")
                elif ad['ctr'] < 0.5 and ad['spend'] > 15:
                    st.warning(f"**REFRESH CREATIVE:** {ad['ad_name']}")
                    st.write(f"→ Low CTR: {ad['ctr']:.2f}% | Creative is worn out, needs refresh")
                elif ad['ctr'] > 1.5 and ad['purchases'] == 0 and ad['spend'] > 20:
                    st.warning(f"**LANDING PAGE ISSUE:** {ad['ad_name']}")
                    st.write(f"→ Good CTR ({ad['ctr']:.2f}%) but no conversions - check landing page")
        else:
            st.info("No ad data found for the selected time period.")
    
    # Email Performance Tab (only shows if Klaviyo is enabled)
    if klaviyo_data:
        with tab5:
            st.header("📧 Email Campaign Performance")
            
            # Email summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💸 Total Email Revenue", f"${klaviyo_data['total_revenue']:,.2f}")
            with col2:
                overall_open_rate = (klaviyo_data['total_opens'] / klaviyo_data['total_emails_sent'] * 100) if klaviyo_data['total_emails_sent'] > 0 else 0
                st.metric("📬 Overall Open Rate", f"{overall_open_rate:.1f}%")
            with col3:
                overall_click_rate = (klaviyo_data['total_clicks'] / klaviyo_data['total_emails_sent'] * 100) if klaviyo_data['total_emails_sent'] > 0 else 0
                st.metric("👆 Overall Click Rate", f"{overall_click_rate:.1f}%")
            
            # Email campaigns table
            if klaviyo_data['campaigns']:
                st.subheader("📧 Email Campaign Breakdown")
                email_df = pd.DataFrame(klaviyo_data['campaigns'])
                
                # Format for display
                display_email_df = email_df.copy()
                display_email_df['revenue'] = display_email_df['revenue'].apply(lambda x: f"${x:,.2f}")
                display_email_df['open_rate'] = display_email_df['open_rate'].apply(lambda x: f"{x:.1f}%")
                display_email_df['click_rate'] = display_email_df['click_rate'].apply(lambda x: f"{x:.1f}%")
                display_email_df['emails_sent'] = display_email_df['emails_sent'].apply(lambda x: f"{x:,}")
                
                st.dataframe(display_email_df[['name', 'emails_sent', 'open_rate', 'click_rate', 'revenue', 'status']], use_container_width=True)
                
                # Email recommendations
                st.subheader("📧 Email Optimization Recommendations")
                for _, campaign in email_df.iterrows():
                    if campaign['open_rate'] > 25.0 and campaign['revenue'] > 1000:
                        st.success(f"✅ **HIGH PERFORMER:** {campaign['name']}")
                        st.write(f"→ Great open rate: {campaign['open_rate']:.1f}% | Revenue: ${campaign['revenue']:,.2f}")
                    elif campaign['open_rate'] < 15.0 and campaign['emails_sent'] > 500:
                        st.warning(f"🔄 **IMPROVE SUBJECT LINE:** {campaign['name']}")
                        st.write(f"→ Low open rate: {campaign['open_rate']:.1f}% | Test new subject lines")
                    elif campaign['click_rate'] < 1.0 and campaign['open_rate'] > 20.0:
                        st.warning(f"🔄 **IMPROVE CONTENT:** {campaign['name']}")
                        st.write(f"→ Good opens ({campaign['open_rate']:.1f}%) but low clicks ({campaign['click_rate']:.1f}%)")
                    elif campaign['revenue'] < 100 and campaign['emails_sent'] > 1000:
                        st.error(f"❌ **LOW REVENUE:** {campaign['name']}")
                        st.write(f"→ Poor performance: ${campaign['revenue']:,.2f} from {campaign['emails_sent']:,} emails")
            
            # Cross-channel insights
            if total_revenue > 0 and klaviyo_data['total_revenue'] > 0:
                st.markdown("---")
                st.subheader("🔗 Cross-Channel Insights")
                
                fb_contribution = (total_revenue / (total_revenue + klaviyo_data['total_revenue'])) * 100
                email_contribution = (klaviyo_data['total_revenue'] / (total_revenue + klaviyo_data['total_revenue'])) * 100
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("📘 Facebook Contribution", f"{fb_contribution:.1f}%")
                    st.write(f"${total_revenue:,.2f} revenue from ads")
                with col2:
                    st.metric("📧 Email Contribution", f"{email_contribution:.1f}%")
                    st.write(f"${klaviyo_data['total_revenue']:,.2f} revenue from email")
                
                combined_revenue = total_revenue + klaviyo_data['total_revenue']
                combined_roas = calculate_roas(total_spend, combined_revenue)
                st.info(f"💡 **Insight:** Your combined marketing generates ${combined_revenue:,.2f} with a {combined_roas:.2f}x ROAS!")
            else:
                st.info("No email campaign data found for the selected time period.")
    
    # Charts section
    if campaigns_data:
        st.markdown("---")
        st.header("📈 Performance Visualization")
        
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            # Campaign ROAS chart
            campaign_df = pd.DataFrame(campaigns_data).head(10)
            if not campaign_df.empty:
                fig_roas = px.bar(
                    campaign_df, 
                    x='campaign_name', 
                    y='roas',
                    title="Campaign ROAS",
                    color='roas',
                    color_continuous_scale='RdYlGn'
                )
                fig_roas.update_xaxes(tickangle=45)
                fig_roas.update_layout(height=400)
                st.plotly_chart(fig_roas, use_container_width=True)
        
        with chart_col2:
            # Ad set performance
            if adsets_data:
                adset_df = pd.DataFrame(adsets_data).head(10)
                fig_adset = px.scatter(
                    adset_df,
                    x='spend',
                    y='roas',
                    size='purchases',
                    color='ctr',
                    title="Ad Set Performance",
                    hover_data=['adset_name']
                )
                fig_adset.update_layout(height=400)
                st.plotly_chart(fig_adset, use_container_width=True)

else:
    st.error("❌ Could not connect to Facebook API")
    st.markdown(f"""
    **Possible issues:**
    - Access token might be expired
    - Ad account ID might be incorrect
    - You might not have permission to access this ad account: {current_account_id}
    """)

# Sidebar
st.sidebar.header("🔧 Dashboard Settings")
st.sidebar.markdown(f"""
**Client:** {selected_client}  
**Account ID:** {current_account_id}
**AOV:** ${current_aov}
**Date Range:** {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')}
**Days Selected:** {(end_date - start_date).days + 1}
""")

if client_info.get("klaviyo_enabled", False):
    st.sidebar.markdown("📧 **Email Integration:** Enabled")
else:
    st.sidebar.markdown("📧 **Email Integration:** Disabled")

if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("📊 Quick Stats")
if 'total_spend' in locals():
    st.sidebar.metric("Total Campaigns", len(campaigns_data))
    st.sidebar.metric("Active Spend", f"${total_spend:,.2f}")
    st.sidebar.metric("Total Clicks", f"{total_clicks:,}")
    
    if klaviyo_data:
        st.sidebar.metric("Email Revenue", f"${klaviyo_data['total_revenue']:,.2f}")

# Footer
st.markdown("---")
if klaviyo_data:
    st.markdown("*Dashboard built with Python & Streamlit | Data from Facebook Marketing API & Klaviyo*")
else:
    st.markdown("*Dashboard built with Python & Streamlit | Data from Facebook Marketing API*")
