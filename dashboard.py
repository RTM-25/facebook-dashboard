# ────────────────────────────────────────────────────────────────
#  dashboard.py  –  Live Facebook Ads & Email Performance Monitor
# ────────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# ────────────────────────────────────────────────────────────────
# Streamlit page settings
# ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Live Facebook Ads Dashboard",
    page_icon="📊",
    layout="wide",
)

# ────────────────────────────────────────────────────────────────
# Simple password gate
# ────────────────────────────────────────────────────────────────
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["dashboard_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Enter Access Code:",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.write("*Please enter the 4-digit access code to view the dashboard*")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Enter Access Code:",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("😞  Access code incorrect")
        return False
    else:
        return True


if not check_password():
    st.stop()

# ────────────────────────────────────────────────────────────────
# Account configuration
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
# Facebook helpers
# ────────────────────────────────────────────────────────────────
def get_facebook_data(start_date, end_date, account_id):
    try:
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)
        account = AdAccount(account_id)

        def fetch(level):
            return list(
                account.get_insights(
                    fields=[
                        "campaign_id",
                        "campaign_name",
                        "adset_id",
                        "adset_name",
                        "ad_id",
                        "ad_name",
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
                        "level": level,
                        "action_breakdowns": ["action_type"],
                        "action_attribution_windows": ["7d_click", "1d_view"],
                    },
                )
            )

        return {"campaigns": fetch("campaign"), "adsets": fetch("adset"), "ads": fetch("ad")}

    except Exception as e:
        st.error(f"Facebook API Error: {e}")
        return None


# ────────────────────────────────────────────────────────────────
# Klaviyo helpers (***FIXED status filter uses 'Sent'***)
# ────────────────────────────────────────────────────────────────
def get_klaviyo_data(start_date, end_date):
    """
    Pull live email-campaign metrics from Klaviyo.
    Filters:
      • channel == 'email'
      • status  == 'Sent'  (capital S)
      • updated_at between start_date & end_date
    """
    try:
        api_key = st.secrets["klaviyo_api_key"]
        headers = {
            "Authorization": f"Klaviyo-API-Key {api_key}",
            "revision": "2024-10-15",
            "Content-Type": "application/json",
        }

        # 1) find campaigns
        params = {
            "filter": (
                f"equals(messages.channel,'email'),"
                f"equals(status,'Sent'),"
                f"greater-than(updated_at,{start_date.isoformat()}),"
                f"less-than(updated_at,{end_date.isoformat()})"
            ),
            "fields[campaign]": "name,status,created_at,send_time",
        }
        campaigns_resp = requests.get("https://a.klaviyo.com/api/campaigns/", headers=headers, params=params)
        if campaigns_resp.status_code != 200:
            st.error(f"Klaviyo API Error: {campaigns_resp.status_code} - {campaigns_resp.text}")
            return None
        campaigns_json = campaigns_resp.json()

        total_rev = tot_sent = tot_open = tot_click = 0
        processed = []

        # 2) loop campaigns and pull metrics
        for camp in campaigns_json.get("data", []):
            cid = camp["id"]
            cname = camp["attributes"]["name"]

            m_resp = requests.get(f"https://a.klaviyo.com/api/campaign-metrics/{cid}/", headers=headers)
            sent = opened = clicked = revenue = 0
            if m_resp.status_code == 200:
                m = m_resp.json().get("data", {}).get("attributes", {})
                sent = m.get("emails_sent", 0)
                opened = m.get("opens", 0)
                clicked = m.get("clicks", 0)
                revenue = m.get("revenue", 0)

            tot_sent += sent
            tot_open += opened
            tot_click += clicked
            total_rev += revenue

            o_rate = opened / sent * 100 if sent else 0
            c_rate = clicked / sent * 100 if sent else 0

            processed.append(
                {
                    "name": cname,
                    "emails_sent": sent,
                    "opens": opened,
                    "clicks": clicked,
                    "revenue": revenue,
                    "open_rate": o_rate,
                    "click_rate": c_rate,
                    "status": camp["attributes"]["status"],
                }
            )

        return {
            "total_revenue": total_rev,
            "total_emails_sent": tot_sent,
            "total_opens": tot_open,
            "total_clicks": tot_click,
            "campaigns": processed,
        }

    except Exception as e:
        st.error(f"Klaviyo API Error: {e}")
        return None


# ────────────────────────────────────────────────────────────────
# Helper utilities
# ────────────────────────────────────────────────────────────────
def calculate_roas(spend, revenue):
    return revenue / spend if spend else 0


def get_purchases_and_revenue_from_actions(actions, action_values=None):
    purchases = revenue = 0
    if actions:
        for a in actions:
            if a.get("action_type") in ("purchase", "app_install", "complete_registration"):
                purchases += int(a.get("value", 0))
    if action_values:
        for av in action_values:
            if av.get("action_type") == "purchase":
                try:
                    revenue += float(av.get("value", 0))
                except (TypeError, ValueError):
                    pass
    return purchases, revenue


def process_insights_data(insights, aov):
    rows = []
    for item in insights:
        spend = float(item.get("spend", 0))
        imps = int(item.get("impressions", 0))
        clicks = int(item.get("clicks", 0))
        purchases, rev_actual = get_purchases_and_revenue_from_actions(
            item.get("actions", []), item.get("action_values", [])
        )
        revenue = rev_actual if rev_actual else purchases * aov
        rows.append(
            {
                "campaign_id": item.get("campaign_id", ""),
                "campaign_name": item.get("campaign_name", "Unknown"),
                "adset_id": item.get("adset_id", ""),
                "adset_name": item.get("adset_name", ""),
                "ad_id": item.get("ad_id", ""),
                "ad_name": item.get("ad_name", ""),
                "spend": spend,
                "impressions": imps,
                "clicks": clicks,
                "purchases": purchases,
                "revenue": revenue,
                "roas": calculate_roas(spend, revenue),
                "cpa": spend / purchases if purchases else 0,
                "ctr": clicks / imps * 100 if imps else 0,
                "cpm": float(item.get("cpm", 0)),
            }
        )
    return rows


# ────────────────────────────────────────────────────────────────
# Top-level dashboard UI
# ────────────────────────────────────────────────────────────────
st.title("📊 Live Facebook Ads Dashboard")

# Choose client
st.sidebar.header("🏢 Client")
selected_client = st.sidebar.selectbox("Choose Client:", list(CLIENTS.keys()), index=0)
info = CLIENTS[selected_client]

# Branding header
hcol1, hcol2 = st.columns([1, 4])
with hcol1:
    st.markdown(f'<img src="{info["logo_url"]}" width="75px">', unsafe_allow_html=True)
with hcol2:
    st.markdown(f"### {selected_client} Performance Dashboard")

st.markdown("---")

# Date range
st.sidebar.header("📅 Date Range")
preset = st.sidebar.selectbox(
    "Select Time Period:",
    ["Last 7 Days", "Last 14 Days", "Last 30 Days", "Last 60 Days", "Last 90 Days", "Custom Range"],
)
if preset == "Custom Range":
    s1, s2 = st.sidebar.columns(2)
    with s1:
        start_date = st.sidebar.date_input("Start", datetime.now() - timedelta(days=30))
    with s2:
        end_date = st.sidebar.date_input("End", datetime.now())
else:
    end_date = datetime.now()
    delta = {
        "Last 7 Days": 7,
        "Last 14 Days": 14,
        "Last 30 Days": 30,
        "Last 60 Days": 60,
        "Last 90 Days": 90,
    }[preset]
    start_date = end_date - timedelta(days=delta)

st.markdown(f"**Data window:** {start_date:%Y-%m-%d} → {end_date:%Y-%m-%d}")
st.markdown(f"**Last refresh:** {datetime.now():%Y-%m-%d %H:%M:%S}")

# ----------------  Fetch data  ----------------
with st.spinner("🔄  Fetching Facebook data…"):
    fb = get_facebook_data(start_date, end_date, info["account_id"])

klaviyo = None
if info["klaviyo_enabled"]:
    with st.spinner("🔄  Fetching Klaviyo data…"):
        klaviyo = get_klaviyo_data(start_date, end_date)

# ----------------  Guard clause  ----------------
if not fb:
    st.error("❌  Could not load Facebook data.")
    st.stop()

# ----------------  Process data  ----------------
campaigns = process_insights_data(fb["campaigns"], info["avg_order_value"])
adsets = process_insights_data(fb["adsets"], info["avg_order_value"])
ads = process_insights_data(fb["ads"], info["avg_order_value"])

tot_spend = sum(d["spend"] for d in campaigns)
tot_rev = sum(d["revenue"] for d in campaigns)
tot_imps = sum(d["impressions"] for d in campaigns)
tot_clicks = sum(d["clicks"] for d in campaigns)
tot_purch = sum(d["purchases"] for d in campaigns)

# ----------------  KPI header  ----------------
if klaviyo:
    email_rev = klaviyo["total_revenue"]
    combined_rev = tot_rev + email_rev
    comb_roas = calculate_roas(tot_spend, combined_rev)

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("💰 FB Spend", f"${tot_spend:,.2f}")
    k2.metric("📧 Email Revenue", f"${email_rev:,.2f}")
    k3.metric("🎯 Combined ROAS", f"{comb_roas:.2f}x")
    k4.metric("🛒 Conversions", f"{tot_purch:,}")
    k5.metric("📈 FB ROAS", f"{calculate_roas(tot_spend, tot_rev):.2f}x")
    k6.metric("👆 CTR", f"{tot_clicks/tot_imps*100 if tot_imps else 0:.2f}%")
else:
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("💰 Spend", f"${tot_spend:,.2f}")
    k2.metric("🛒 Purchases", f"{tot_purch:,}")
    k3.metric("📈 ROAS", f"{calculate_roas(tot_spend, tot_rev):.2f}x")
    k4.metric("🎯 CPA", f"${tot_spend/tot_purch if tot_purch else 0:.2f}")
    k5.metric("👆 CTR", f"{tot_clicks/tot_imps*100 if tot_imps else 0:.2f}%")

st.markdown("---")

# ----------------  Tabs  ----------------
if klaviyo:
    tab_over, tab_camp, tab_adset, tab_ad, tab_email = st.tabs(
        ["📊 Overview", "🎯 Campaigns", "🔍 Ad Sets", "📢 Ads", "📧 Email"]
    )
else:
    tab_over, tab_camp, tab_adset, tab_ad = st.tabs(
        ["📊 Overview", "🎯 Campaigns", "🔍 Ad Sets", "📢 Ads"]
    )

# == Overview (top performers & actions) ==
with tab_over:
    c1, c2 = st.columns([2, 1])

    #  Top performers
    with c1:
        st.subheader("🏆 Top Performers")
        st.markdown("**Top 5 Campaigns (ROAS)**")
        for d in sorted(campaigns, key=lambda x: x["roas"], reverse=True)[:5]:
            if d["purchases"]:
                st.write(f"• **{d['campaign_name'][:40]}…** – {d['roas']:.2f}x, {d['purchases']} buys")

        st.markdown("**Top 5 Ad Sets (ROAS)**")
        for d in sorted(adsets, key=lambda x: x["roas"], reverse=True)[:5]:
            if d["purchases"]:
                st.write(f"• **{d['adset_name'][:40]}…** – {d['roas']:.2f}x, CPA ${d['cpa']:.2f}")

        st.markdown("**Top 5 Ads (ROAS)**")
        for d in sorted(ads, key=lambda x: x["roas"], reverse=True)[:5]:
            if d["purchases"]:
                st.write(f"• **{d['ad_name'][:40]}…** – {d['roas']:.2f}x, CTR {d['ctr']:.2f}%")

    #  Actionable items
    with c2:
        st.subheader("⚡ Priority Actions")
        for d in sorted(campaigns, key=lambda x: x["roas"], reverse=True):
            if d["roas"] > 4 and d["purchases"] >= 5:
                st.success(f"Scale campaign **{d['campaign_name'][:22]}…** (ROAS {d['roas']:.1f}x)")
            elif d["roas"] < 2 and d["spend"] > 50:
                st.error(f"Pause **{d['campaign_name'][:22]}…** (ROAS {d['roas']:.1f}x)")
            if sum(1 for _ in c2.container()._children) > 5:
                break

# == Campaign table ==
with tab_camp:
    st.header("🎯 Campaign Analysis")
    df = pd.DataFrame(campaigns).sort_values("roas", ascending=False)
    df_display = df.assign(
        spend=lambda d: d["spend"].map("${:,.2f}".format),
        revenue=lambda d: d["revenue"].map("${:,.2f}".format),
        roas=lambda d: d["roas"].map("{:.2f}x".format),
        cpa=lambda d: d["cpa"].map(lambda x: f"${x:.2f}" if x else "–"),
        ctr=lambda d: d["ctr"].map("{:.2f}%".format),
        impressions=lambda d: d["impressions"].map("{:,}".format),
    )
    st.dataframe(df_display[
        ["campaign_name","spend","impressions","clicks","purchases","roas","cpa","ctr"]
    ], use_container_width=True)

# == Ad-set table ==
with tab_adset:
    st.header("🔍 Ad-Set Analysis")
    df = pd.DataFrame(adsets).sort_values("roas", ascending=False)
    df_disp = df.assign(
        spend=lambda d: d["spend"].map("${:,.2f}".format),
        revenue=lambda d: d["revenue"].map("${:,.2f}".format),
        roas=lambda d: d["roas"].map("{:.2f}x".format),
        cpa=lambda d: d["cpa"].map(lambda x: f"${x:.2f}" if x else "–"),
        ctr=lambda d: d["ctr"].map("{:.2f}%".format),
        cpm=lambda d: d["cpm"].map("${:.2f}".format),
    )
    st.dataframe(df_disp[
        ["campaign_name","adset_name","spend","purchases","roas","cpa","ctr","cpm"]
    ], use_container_width=True)

# == Ad table ==
with tab_ad:
    st.header("📢 Ad Analysis")
    df = pd.DataFrame(ads).sort_values("roas", ascending=False)
    df_disp = df.assign(
        spend=lambda d: d["spend"].map("${:,.2f}".format),
        revenue=lambda d: d["revenue"].map("${:,.2f}".format),
        roas=lambda d: d["roas"].map("{:.2f}x".format),
        ctr=lambda d: d["ctr"].map("{:.2f}%".format),
        cpm=lambda d: d["cpm"].map("${:.2f}".format),
    )
    st.dataframe(df_disp[
        ["campaign_name","adset_name","ad_name","spend","purchases","roas","ctr","cpm"]
    ], use_container_width=True)

# == Email tab ==
if klaviyo:
    with tab_email:
        st.header("📧 Email Campaign Performance")
        k1, k2, k3 = st.columns(3)
        k1.metric("💸 Total Email Revenue", f"${klaviyo['total_revenue']:,.2f}")
        k2.metric(
            "📬 Open Rate",
            f"{klaviyo['total_opens']/klaviyo['total_emails_sent']*100 if klaviyo['total_emails_sent'] else 0:.1f}%",
        )
        k3.metric(
            "👆 Click Rate",
            f"{klaviyo['total_clicks']/klaviyo['total_emails_sent']*100 if klaviyo['total_emails_sent'] else 0:.1f}%",
        )

        df_email = pd.DataFrame(klaviyo["campaigns"]).assign(
            revenue=lambda d: d["revenue"].map("${:,.2f}".format),
            open_rate=lambda d: d["open_rate"].map("{:.1f}%".format),
            click_rate=lambda d: d["click_rate"].map("{:.1f}%".format),
            emails_sent=lambda d: d["emails_sent"].map("{:,}".format),
        )
        st.dataframe(
            df_email[["name", "emails_sent", "open_rate", "click_rate", "revenue", "status"]],
            use_container_width=True,
        )

# ----------------  Sidebar quick stats  ----------------
st.sidebar.header("🔧 Settings")
st.sidebar.markdown(
    f"**Client:** {selected_client}\n\n"
    f"**Account ID:** {info['account_id']}\n\n"
    f"**AOV:** ${info['avg_order_value']}\n\n"
    f"**Range:** {start_date:%m/%d/%Y}–{end_date:%m/%d/%Y}\n\n"
    f"**Days:** {(end_date - start_date).days + 1}",
)
st.sidebar.markdown("📧 **Email Integration:** " + ("Enabled" if info["klaviyo_enabled"] else "Disabled"))
if st.sidebar.button("🔄 Refresh"):
    st.experimental_rerun()

# ----------------  Footer  ----------------
st.markdown("---")
st.markdown(
    "*Dashboard built with Python & Streamlit | Data from Facebook Marketing API"
    + (" & Klaviyo*" if info["klaviyo_enabled"] else "*")
)
