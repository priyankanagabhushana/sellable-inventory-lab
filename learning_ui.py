"""Shared scenario state and small, data-driven teaching visuals."""
from __future__ import annotations

import html
import pandas as pd
import streamlit as st
import altair as alt
from allotment import allot, split_list
from forecast_workbench import evaluate_models, MODEL_LABELS
from learning_data import stable_case
from ui import apply_theme, hero, TEAL, GOLD, ORANGE, NAVY

ROUTES = ["home_page.py", "pages/1_Data_and_SQL.py", "pages/2_Forecasting_Workbench.py", "pages/3_Allocation_Lab.py"]


@st.cache_resource
def artifacts():
    return evaluate_models()


@st.cache_data
def model_case(model_name):
    return stable_case(artifacts(), model_name)


def reset_example():
    for key in list(st.session_state):
        if key.startswith(("lab_", "_lab_")):
            del st.session_state[key]


def choose(label, options, state_key, page, format_func=str):
    permanent = "lab_" + state_key
    widget = "_lab_" + page + "_" + state_key
    if st.session_state.get(permanent) not in options:
        st.session_state[permanent] = options[0]
    st.session_state[widget] = st.session_state[permanent]
    def save():
        st.session_state[permanent] = st.session_state[widget]
    return st.selectbox(label, options, key=widget, format_func=format_func, on_change=save)


def header(title, subtitle, number):
    st.set_page_config(page_title=f"Sellable · {title}", page_icon="◈", layout="wide", initial_sidebar_state="auto")
    apply_theme()
    hero(title, subtitle, f"Simulated example · {number} / 4", ["Fictional campaigns · synthetic audiences"])
    with st.sidebar:
        st.caption("One campaign, followed from data to decision.")
        st.button("Reset example", on_click=reset_example, width="stretch")


def context(page):
    if "lab_model" not in st.session_state:
        st.session_state.lab_model = "xgboost"
    base = model_case(st.session_state.lab_model)
    left, right = st.columns([1.2, 1])
    lookup = base["requests"].set_index("request_id")
    with left:
        campaign_id = choose("Follow a campaign", lookup.index.tolist(), "campaign", page, lambda x: lookup.loc[x, "advertiser"])
    with right:
        method = choose("Audience forecast method", list(MODEL_LABELS), "model", page, MODEL_LABELS.get)
    case = model_case(method)
    campaign = case["requests"].set_index("request_id").loc[campaign_id]
    allowed = case["breaks"][case["breaks"].channel.isin(split_list(campaign.eligible_channels)) & case["breaks"].daypart.isin(split_list(campaign.dayparts))]
    lookup_break = allowed.set_index("break_id")
    break_id = choose("Follow an eligible break", allowed.break_id.tolist(), "break", page, lambda x: f"{lookup_break.loc[x, 'channel']} · {lookup_break.loc[x, 'air_time']:%a %d %b, %H:%M} · {lookup_break.loc[x, 'programme']}")
    policy = st.session_state.get("lab_policy", "firm_first")
    planning = st.session_state.get("lab_planning", "p20")
    case["placements"], case["summary"], case["fill"] = allot(case["breaks"], case["requests"], policy, planning)
    return case, campaign_id, campaign, break_id


def navigation(index):
    st.divider()
    left, right = st.columns(2)
    if index > 0:
        left.page_link(ROUTES[index-1], label="← Previous step")
    if index < 3:
        right.page_link(ROUTES[index+1], label="Continue → " + ["Start", "Data & SQL", "Forecasting", "Allocation"][index+1])
    st.caption("All audience, booking and delivery numbers are simulated. Impressions can include repeat viewers.")


def campaign_card(campaign):
    st.markdown(f'<div class="lab-card"><h3>{html.escape(campaign.advertiser)} wants {campaign.goal_impressions:,.0f} impressions</h3><div>{campaign.spot_sec}-second spots · {html.escape(campaign.target_group)} · {html.escape(campaign.eligible_channels)} · {html.escape(campaign.dayparts)}</div><div class="lab-caption">An impression is one opportunity to see a spot. It is not necessarily a new person.</div></div>', unsafe_allow_html=True)


def airtime(case, break_id):
    slot = case["fill"].set_index("break_id").loc[break_id]
    parts = [("Already booked", slot.presold_sec, GOLD, "#17212B"), ("New spots", slot.allotted_sec, TEAL, "white"), ("Free", slot.capacity_sec-slot.used_sec, "#DED8CC", "#17212B")]
    spans = "".join(f'<span style="width:{100*n/slot.capacity_sec:.4f}%;background:{color};color:{text}" title="{label}: {n:g} seconds">{f"{n:g}s" if n/slot.capacity_sec >= .09 else ""}</span>' for label,n,color,text in parts if n>0)
    legend = "".join(f'<span><b style="color:{color}">■</b> {label}: {n:g}s</span>' for label,n,color,text in parts)
    st.markdown(f'<div class="lab-card"><h3>{slot.channel} · {slot.air_time:%a %H:%M} · {slot.capacity_sec:g} seconds</h3><div class="lab-strip" role="img" aria-label="Break airtime: {slot.presold_sec:g} booked, {slot.allotted_sec:g} new, {slot.capacity_sec-slot.used_sec:g} free">{spans}</div><div class="lab-legend">{legend}</div></div>', unsafe_allow_html=True)


def goal_chart(summary):
    frame = pd.DataFrame({"Estimate": ["Lower sum", "Median sum"], "Impressions": [summary.planned_p20, summary.planned_p50]})
    bars = alt.Chart(frame).mark_bar(cornerRadiusEnd=5).encode(x=alt.X("Impressions:Q", title="Simulated impressions"), y=alt.Y("Estimate:N", title=None, axis=alt.Axis(labelLimit=140)), color=alt.Color("Estimate:N", scale=alt.Scale(domain=["Lower sum", "Median sum"], range=[ORANGE, TEAL]), legend=None), tooltip=["Estimate", alt.Tooltip("Impressions:Q", format=",.0f")])
    goal = alt.Chart(pd.DataFrame({"Goal": [summary.goal]})).mark_rule(color=NAVY, strokeDash=[5,4]).encode(x="Goal:Q", tooltip=[alt.Tooltip("Goal:Q", format=",")])
    st.altair_chart((bars+goal).properties(height=130).configure_view(strokeWidth=0), width="stretch")
    st.caption(f"Dashed line: campaign goal {summary.goal:,.0f}. The lower sum is a planning measure, not a campaign-level P20 guarantee.")


def question(key, prompt, choices, correct, explanation):
    selected = st.radio(prompt, choices, index=None, key="_lab_question_"+key)
    if selected is not None:
        if selected == correct:
            st.success(explanation)
        else:
            st.info("Try this reasoning: " + explanation)


def relationships(campaign, campaign_id):
    channels = split_list(campaign.eligible_channels)
    chips = "".join(f'<span class="lab-chip">{html.escape(campaign_id)} → {html.escape(c)}</span>' for c in channels)
    st.markdown(f'<div class="lab-card"><h3>1 campaign → {len(channels)} allowed channel links</h3><p><strong>{html.escape(campaign_id)} · Goal: {campaign.goal_impressions:,.0f}</strong><br>The goal stays here, once.</p><div aria-hidden="true">↓</div>{chips}<p class="lab-caption">These links say where the campaign may run. They do not each receive another copy of its goal.</p></div>', unsafe_allow_html=True)


def tree_path(explanation):
    blocks = []
    for item in explanation["path"]:
        if "leaf" in item:
            blocks.append(f'<div class="lab-decision"><strong>Leaf contribution: {item["leaf"]:+,.2f}</strong><br><small>Added to the running prediction</small></div>')
        else:
            feature = html.escape(item["feature"].replace("_", " "))
            blocks.append(f'<div class="lab-decision"><strong>Is {feature} &lt; {item["threshold"]:,.3f}?</strong><br>This row: {item["value"]:,.3f}<br><small>The other branch is not taken.</small></div><div class="lab-answer">{item["answer"]} ↓</div>')
    st.markdown('<div class="lab-path">'+"".join(blocks)+'</div>', unsafe_allow_html=True)
