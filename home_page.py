"""Start with one campaign and follow its data to a placement decision."""
import streamlit as st
from learning_ui import header, context, campaign_card, airtime, goal_chart, navigation, question
from ui import callout

header("Can this campaign fit?", "Choose a campaign, inspect one break, then follow the four steps to understand the decision.", 1)
case, campaign_id, campaign, break_id = context("home")
campaign_card(campaign)
left, right = st.columns([1.1, 1])
with left:
    airtime(case, break_id)
with right:
    summary = case["summary"].set_index("request_id").loc[campaign_id]
    goal_chart(summary)

st.markdown("### Try a prediction")
question("home_"+campaign_id, "A break has 30 seconds free. Can it hold two 20-second spots?",
         ["Yes, because there are enough viewers", "No, because 40 seconds will not fit"],
         "No, because 40 seconds will not fit",
         "Audience and airtime are different. Two 20-second spots need 40 seconds, even if many people watch.")
callout("Your next action", "Continue to Data & SQL. Follow this same campaign and see why its goal must be stored only once.")
with st.expander("The whole journey in plain words"):
    st.write("1. Store one goal for this campaign and separate links for its allowed channels.")
    st.write("2. Use earlier audience observations to forecast next week's breaks.")
    st.write("3. Check existing bookings and the seconds each new spot needs.")
    st.write("4. Apply an explicit priority rule and compare the planned delivery with the goal.")
    st.write("A firm booking is a confirmed commitment. An option is a provisional request. This example uses a fixed target-group share; it is not measured targeting data.")
    st.caption("Programme listings may come from a public source. All commercial inputs, audiences, bookings and allocation results are simulated.")
navigation(0)
