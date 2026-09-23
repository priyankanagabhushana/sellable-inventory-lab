"""Explore policy choices using the model forecasts from the shared scenario."""
import pandas as pd
import streamlit as st
from allotment import allot, policy_difference, allocation_trace
from learning_ui import header, context, choose, campaign_card, airtime, goal_chart, navigation, question
from learning_data import data_quality_report
from schedule_source import public_refresh_enabled, load_schedule
from ui import callout

header("Give every spot a reason", "Use the forecast, check the available seconds, and apply an explicit priority rule.", 4)
case, campaign_id, campaign, break_id = context("allocation")
left, right = st.columns(2)
with left:
    policy = choose("Who goes first?", ["firm_first","first_come"], "policy", "allocation",
        lambda x: {"firm_first":"Firm bookings first","first_come":"First come, first served"}[x])
with right:
    planning = choose("Plan toward the goal using", ["p20","p50"], "planning", "allocation",
        lambda x: {"p20":"Lower estimates","p50":"Median estimates"}[x])

case["placements"], case["summary"], case["fill"] = allot(case["breaks"],case["requests"],policy,planning)
report = data_quality_report(case["programmes"],case["breaks"],case["requests"],case["placements"])
if report.status.eq("FAIL").any():
    st.error("Data checks failed. Allocation cannot be shown.")
    st.dataframe(report)
    st.stop()

campaign_card(campaign)
left,right = st.columns(2)
with left:
    airtime(case,break_id)
with right:
    summary = case["summary"].set_index("request_id").loc[campaign_id]
    goal_chart(summary)

trace = allocation_trace(case["breaks"],case["requests"],campaign_id,policy,planning)
decision = trace.set_index("break_id").loc[break_id]
callout("Why this break was used or skipped",
    f"{decision.reason}. It ranked {decision['rank']} among eligible candidates and had {decision.free_seconds_at_decision:g} seconds free at this campaign's turn. Each spot needs {campaign.spot_sec} seconds.")
st.caption("Candidate order: listed channel preference, then higher forecast audience, then time and break ID. The airtime strip shows the final state after all campaigns; decision-time free seconds may differ.")

question("allocation", "If we choose lower audience estimates, does the break gain more seconds?",
    ["Yes, a smaller audience frees airtime","No, airtime capacity stays the same"],
    "No, airtime capacity stays the same",
    "A cautious forecast may require more spots to reach the same goal. Each spot still uses its full duration.")

st.markdown("### Who changes when the priority rule changes?")
diff = policy_difference(case["breaks"],case["requests"],planning)
chosen = diff.set_index("request_id").loc[campaign_id]
left,right = st.columns(2)
left.metric("Your campaign · firm first", int(chosen.spots_firm_first), help="Number of selected spots")
right.metric("Your campaign · first come", int(chosen.spots_first_come), help="Number of selected spots")
callout("What changed and why?",
    f"The selected campaign receives {chosen.spots_firm_first} spots with firm priority and {chosen.spots_first_come} with arrival order. Firm priority protects confirmed requests before options. Arrival order can give a provisional request access earlier.")
with st.expander("Other campaigns and every placement decision"):
    readable = case["summary"][["advertiser","status","goal","spots","planned_p20","planned_p50"]].rename(columns={"advertiser":"Campaign","status":"Booking","goal":"Goal","spots":"Spots","planned_p20":"Lower planning sum","planned_p50":"Median planning sum"})
    st.dataframe(readable,hide_index=True,width="stretch")
    st.dataframe(diff,hide_index=True,width="stretch")
    st.dataframe(trace,hide_index=True,width="stretch")
    st.dataframe(case["placements"],hide_index=True,width="stretch")
    st.download_button("Download simulated placements",case["placements"].to_csv(index=False).encode(),file_name="synthetic_placements.csv",mime="text/csv")

with st.expander("Understand what these delivery numbers mean"):
    st.write("The forecast counts impressions, which may include the same person seeing more than one spot. This is not a count of unique people.")
    st.write("We add each chosen break's lower audience estimate for cautious planning. Adding P20 values does not produce the P20 of total campaign delivery. Errors across breaks can move together; a campaign probability needs their joint uncertainty.")
    st.write("The fictional target group uses a fixed 28% share of adults. Real target-group forecasts require suitable observed audience data and their own validation.")
    st.write("There is no real quotation here. Pricing needs its own market evidence, rules and approvals. Mathematical optimisation could later compare valid combinations against this greedy rule.")

with st.expander("Source, model version and checks"):
    st.dataframe(report,hide_index=True,width="stretch")
    slot=case["breaks"].set_index("break_id").loc[break_id]
    st.write(f"Model: {slot.model_name}. Forecast issue time: {slot.forecast_issue_time:%d %b %Y %H:%M}. Training cutoff: {slot.training_cutoff:%d %b %Y}. Calibration ends: {slot.calibration_end:%d %b %Y}.")
    st.write("The connected example uses a stable fictional schedule. Public listings alone cannot supply observed audience history for a new programme.")
    if public_refresh_enabled():
        if st.button("Inspect optional public listings"):
            listing,source=load_schedule(refresh=True,allow_remote=True)
            st.caption(source)
            st.dataframe(listing,hide_index=True,width="stretch")
            st.info("This is a listings preview. It does not replace the connected example or imply that these programmes have measured audiences.")
    else:
        st.caption("External listings refresh is disabled.")
navigation(3)
