"""Explore one campaign's relationships and run read-only SQL proofs."""
import streamlit as st
from learning_ui import header, context, relationships, navigation, question
from learning_data import normalized_campaign_tables, SQL_EXAMPLES, run_sql_example, data_quality_report, contract_markdown
from ui import callout

header("One campaign. One goal.", "Separate the campaign's goal from the channels where it may run.", 2)
case, campaign_id, campaign, break_id = context("data")
relationships(campaign, campaign_id)

channels = [v.strip() for v in campaign.eligible_channels.split("|")]
question("data_"+campaign_id, f"This campaign can use {len(channels)} channels. Does that multiply its goal?",
         ["Yes, each channel gets the full goal", "No, the channels share one campaign goal"],
         "No, the channels share one campaign goal",
         f"The correct goal remains {campaign.goal_impressions:,.0f}. Copying and summing it on {len(channels)} rows would give {campaign.goal_impressions * len(channels):,.0f}.")

with st.expander("Technical view · the linked rows and primary keys"):
    tables = normalized_campaign_tables(case["requests"])
    for name, table in tables.items():
        st.markdown("**"+name.replace("_", " ").title()+"**")
        st.dataframe(table[table.request_id == campaign_id], hide_index=True, width="stretch")
    st.markdown(contract_markdown())
    st.write("A primary key identifies one row. Campaigns use request_id. Channel links use request_id plus channel. Daypart links use request_id plus daypart. Placements connect a campaign to a break.")
    st.code("Campaign ──→ Channel links\n        ├──→ Daypart links\n        └──→ Placements ←── Breaks ←── Programmes", language="text")

st.markdown("### Ask the data a question")
name = st.selectbox("Business question", list(SQL_EXAMPLES), key="_lab_sql_question")
result = run_sql_example(case, SQL_EXAMPLES[name])
callout("What this query found", "No overbooked breaks." if result.empty and name == "Find an overbooked break" else f"{len(result):,} rows in this result. Expand the proof to see the SQL and its output.")
with st.expander("Show the SQL and result"):
    st.code(SQL_EXAMPLES[name], language="sql")
    st.dataframe(result, hide_index=True, width="stretch")
    st.caption("Each campaign goal is counted once. A LEFT JOIN keeps campaigns with no placements visible.")

st.markdown("### See a quality check catch a mistake")
mistake = st.selectbox("Temporary example", ["Clean data", "Missing campaign ID", "Negative spot duration", "Unknown break reference", "Too many seconds in a break"], key="_lab_mistake")
requests, placements = case["requests"].copy(), case["placements"].copy()
if mistake == "Missing campaign ID":
    requests.loc[0, "request_id"] = None
elif mistake == "Negative spot duration":
    requests.loc[0, "spot_sec"] = -30
elif mistake == "Unknown break reference":
    placements.loc[0, "break_id"] = "missing-break"
elif mistake == "Too many seconds in a break":
    placements.loc[0, "spot_sec"] = 9999
report = data_quality_report(case["programmes"], case["breaks"], requests, placements)
if report.status.eq("FAIL").any():
    st.error("Calculation stopped: this example contains invalid data.")
    for message in report.loc[report.status.eq("FAIL"), "check"]:
        st.write(message)
else:
    st.success("All data checks passed. These same checks protect the allocation calculation.")
st.caption("This experiment changes a temporary copy only. The campaign you are following stays unchanged.")
with st.expander("Full checks and technical tables"):
    st.dataframe(report, hide_index=True, width="stretch")
    table = st.selectbox("Table", ["programmes", "breaks", "requests", "placements"], key="_lab_technical_table")
    st.dataframe(case[table], hide_index=True, width="stretch")
navigation(1)
