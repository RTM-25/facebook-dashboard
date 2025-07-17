# Live Facebook Ads Dashboard - Multi-Client Version with Klaviyo
# Save this file as "dashboard.py"

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

# ────────────────────────────────────────────────────────────────
# Dashboard config
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Live Facebook Ads Dashboard",
                   page_icon="📊",
                   layout="wide")

# ────────────────────────────────────────────────────────────────
# Password protection
# ────────────────────────────────────────────────────────────────
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["dashboard_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Enter Access Code:", type="password",
                      on_change=password_entered, key="password")
        st.write("*Please enter the 4-digit access code to view the dashboard*")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Access Code:", type="password",
                      on_change=password_entered, key="password")
        st.error("😞 Access code incorrect")
        return False
    else:
        return True


if not check_password():
    st.stop()

# ────────────────────────────────────────────────────────────────
# API credentials and client accounts
# ────────────────────────────────────────────────────────────────
ACCESS_TOKEN = st.secrets["facebook_token"]

CLIENTS = {
    "RAGE Nation Apparel": {
        "account_id": "act_1761456877511271",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 50,
        "klaviyo_enabled": False,
    },
    "World POG Federation": {
        "account_id": "act_224902019311983",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 75,
        "klaviyo_enabled": False,
    },
    "Supplies Outlet": {
        "account_id": "act_147523547450881",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 45,
        "klaviyo_enabled": False,
    },
    "Tote n Carry - Main Account": {
        "account_id": "act_2524661660981967",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 35,
        "klaviyo_enabled": True,
    },
    "Tote n Carry - Secondary Account": {
        "account_id": "act_2003497536588787",
        "logo_url": "https://i.ibb.co/Wjpyhwn/ZB166-RTM-Logos-11.png",
        "avg_order_value": 35,
        "klaviyo_enabled": True,
    },
}

# ────────────────────────────────────────────────────────────────
# Facebook API helpers
# ────────────────────────────────────────────────────────────────
def get_facebook_data(start_date, end_date, account_id):
    try:
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)
        account = AdAccount(account_id)

        # Campaign-level
        campaign_insights = account.get_insights(
            fields=[
                "campaign_id",
                "campaign_name",
                "spend",
                "actions",
                "action_values",
                "cost_per_action_type",
                "ctr",
                "cpm",
                "impressions",
                "clicks",
                "reach",
                "frequency",
                "purchase_roas",
            ],
            params={
                "time_range": {
                    "since": start_date.strftime("%Y-%m-%d"),
                    "until": end_date.strftime("%Y-%m-%d"),
                },
                "level": "campaign",
                "action_breakdowns": ["action_type"],
                "action_attribution_windows": ["7d_click", "1d_view"],
            },
        )

        # Ad-set-level
        adset_insights = account.get_insights(
            fields=[
                "campaign_id",
                "campaign_name",
                "adset_id",
                "adset_name",
                "spend",
                "actions",
                "cost_per_action_type",
                "ctr",
                "cpm",
                "impressions",
                "clicks",
                "reach",
                "frequency",
            ],
            params={
                "time_range": {
                    "since": start_date.strftime("%Y-%m-%d"),
                    "until": end_date.strftime("%Y-%m-%d"),
                },
                "level": "adset",
                "action_breakdowns": ["action_type"],
            },
        )

        # Ad-level
        ad_insights = account.get_insights(
            fields=[
                "campaign_id",
                "campaign_name",
                "adset_id",
                "adset_name",
                "ad_id",
                "ad_name",
                "spend",
                "actions",
                "cost_per_action_type",
                "ctr",
                "cpm",
                "impressions",
                "clicks",
                "reach",
                "frequency",
            ],
            params={
                "time_range": {
                    "since": start_date.strftime("%Y-%m-%d"),
                    "until": end_date.strftime("%Y-%m-%d"),
                },
                "level": "ad",
                "action_breakdowns": ["action_type"],
            },
        )

        return {
            "campaigns": list(campaign_insights),
            "adsets": list(adset_insights),
            "ads": list(ad_insights),
        }

    except Exception as e:
        st.error(f"API Error: {e}")
        return None


# ────────────────────────────────────────────────────────────────
# Klaviyo helpers  (UPDATED)
# ────────────────────────────────────────────────────────────────
def get_klaviyo_data(start_date, end_date):
    """
    Fetch live email-campaign performance from Klaviyo.

    • Uses ONLY filterable fields (updated_at) plus required channel filter.
    • Filters for EMAIL campaigns with STATUS 'sent'.
    • Retrieves real metrics from the /campaign-metrics endpoint.
    """
    try:
        api_key = st.secrets["klaviyo_api_key"]

        headers = {
            "Authorization": f"Klaviyo-API-Key {api_key}",
            "revision": "2024-10-15",
            "Content-Type": "application/json",
        }

        campaigns_url = "https://a.klaviyo.com/api/campaigns/"

        # Valid filters
        campaigns_params = {
            "filter": (
                f"equals(messages.channel,'email'),"
                f"equals(status,'sent'),"
                f"greater-than(updated_at,{start_date.isoformat()}),"
                f"less-than(updated_at,{end_date.isoformat()})"
            ),
            # we may REQUEST send_time but we cannot filter on it
            "fields[campaign]": "name,status,created_at,send_time,send_strategy",
        }

        campaigns_resp = requests.get(
            campaigns_url, headers=headers, params=campaigns_params
        )

        if campaigns_resp.status_code != 200:
            st.error(
                f"Klaviyo API Error: {campaigns_resp.status_code} - {campaigns_resp.text}"
            )
            return None

        campaigns_json = campaigns_resp.json()

        total_revenue = total_emails_sent = total_opens = total_clicks = 0
        processed_campaigns = []

        for camp in campaigns_json.get("data", []):
            camp_id = camp["id"]
            camp_name = camp["attributes"]["name"]

            # Real-time metrics endpoint
            metrics_url = f"https://a.klaviyo.com/api/campaign-metrics/{camp_id}/"
            metrics_resp = requests.get(metrics_url, headers=headers)

            emails_sent = opens = clicks = revenue = 0
            if metrics_resp.status_code == 200:
                m = metrics_resp.json().get("data", {}).get("attributes", {})
                emails_sent = m.get("emails_sent", 0)
                opens = m.get("opens", 0)
                clicks = m.get("clicks", 0)
                revenue = m.get("revenue", 0)

            total_emails_sent += emails_sent
            total_opens += opens
            total_clicks += clicks
            total_revenue += revenue

            open_rate = (opens / emails_sent * 100) if emails_sent else 0
            click_rate = (clicks / emails_sent * 100) if emails_sent else 0

            processed_campaigns.append(
                {
                    "name": camp_name,
                    "emails_sent": emails_sent,
                    "opens": opens,
                    "clicks": clicks,
                    "revenue": revenue,
                    "open_rate": open_rate,
                    "click_rate": click_rate,
                    "status": camp["attributes"]["status"],
                }
            )

        return {
            "total_revenue": total_revenue,
            "total_emails_sent": total_emails_sent,
            "total_opens": total_opens,
            "total_clicks": total_clicks,
            "campaigns": processed_campaigns,
        }

    except Exception as e:
        st.error(f"Klaviyo API Error: {e}")
        return None


# ────────────────────────────────────────────────────────────────
# Helper functions for metrics processing
# ────────────────────────────────────────────────────────────────
def calculate_roas(spend, revenue):
    return revenue / spend if spend else 0


def get_purchases_and_revenue_from_actions(actions, action_values=None):
    purchases = revenue = 0
    if actions:
        for action in actions:
            atype = action.get("action_type", "")
            if atype in ("purchase", "app_install", "complete_registration"):
                purchases += int(action.get("value", 0))
    if action_values:
        for av in action_values:
            if av.get("action_type") == "purchase":
                try:
                    revenue += float(av.get("value", 0))
                except ValueError:
                    pass
    return purchases, revenue


def process_insights_data(insights_list, avg_order_value):
    processed = []
    for item in insights_list:
        spend = float(item.get("spend", 0))
        impressions = int(item.get("impressions", 0))
        clicks = int(item.get("clicks", 0))
        actions = item.get("actions", [])
        action_values = item.get("action_values", [])
        purchases, actual_rev = get_purchases_and_revenue_from_actions(
            actions, action_values
        )
        revenue = actual_rev if actual_rev else purchases * avg_order_value
        roas = calculate_roas(spend, revenue)
        cpa = spend / purchases if purchases else 0
        ctr = (clicks / impressions * 100) if impressions else 0
        cpm = float(item.get("cpm", 0))

        processed.append(
            {
                "campaign_id": item.get("campaign_id", ""),
                "campaign_name": item.get("campaign_name", "Unknown"),
                "adset_id": item.get("adset_id", ""),
                "adset_name": item.get("adset_name", ""),
                "ad_id": item.get("ad_id", ""),
                "ad_name": item.get("ad_name", ""),
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "purchases": purchases,
                "revenue": revenue,
                "actual_revenue": actual_rev,
                "roas": roas,
                "cpa": cpa,
                "ctr": ctr,
                "cpm": cpm,
            }
        )

    return processed


# ────────────────────────────────────────────────────────────────
# MAIN DASHBOARD
# ────────────────────────────────────────────────────────────────
st.title("📊 Live Facebook Ads Dashboard")

# Sidebar – client selector
st.sidebar.header("🏢 Client Selection")
selected_client = st.sidebar.selectbox("Choose Client:", list(CLIENTS.keys()), index=0)

client_info = CLIENTS[selected_client]
current_account_id = client_info["account_id"]
current_logo_url = client_info["logo_url"]
current_aov = client_info["avg_order_value"]

# Branding
col1, col2 = st.columns([1, 4])
with col1:
    st.markdown(f'<img src="{current_logo_url}" width="75px">', unsafe_allow_html=True)
with col2:
    st.markdown(f"### {selected_client} Performance Dashboard")

st.markdown("---")

# Date range selector
st.sidebar.header("📅 Date Range")
date_option = st.sidebar.selectbox(
    "Select Time Period:",
    ["Last 7 Days", "Last 14 Days", "Last 30 Days", "Last 60 Days", "Last 90 Days", "Custom Range"],
)

if date_option == "Custom Range":
    c1, c2 = st.sidebar.columns(2)
    with c1:
        start_date = st.sidebar.date_input("Start Date", datetime.now() - timedelta(days=30))
    with c2:
        end_date = st.sidebar.date_input("End Date", datetime.now())
else:
    end_date = datetime.now()
    delta_map = {
        "Last 7 Days": 7,
        "Last 14 Days": 14,
        "Last 30 Days": 30,
        "Last 60 Days": 60,
        "Last 90 Days": 90,
    }
    start_date = end_date - timedelta(days=delta_map[date_option])

st.markdown(f"**Showing data from:** {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}")
st.markdown(f"**Last Updated:** {datetime.now():%Y-%m-%d %H:%M:%S}")

# Pull data
with st.spinner(
    f"🔄 Pulling {selected_client} data from {start_date:%m/%d} to {end_date:%m/%d}..."
):
    fb_data = get_facebook_data(start_date, end_date, current_account_id)

klaviyo_data = None
if client_info.get("klaviyo_enabled"):
    with st.spinner(f"🔄 Pulling email data for {selected_client}..."):
        klaviyo_data = get_klaviyo_data(start_date, end_date)

# ────────────────────────────────────────────────────────────────
# Process and display metrics (unchanged code from here down)
# ────────────────────────────────────────────────────────────────
# ...  (the remainder of your existing Streamlit dashboard code stays the same)
# Paste the rest of your original dashboard logic below without modification
# ────────────────────────────────────────────────────────────────
