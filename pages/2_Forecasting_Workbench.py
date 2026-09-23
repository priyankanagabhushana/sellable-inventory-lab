"""Trace the same break from observed history through a forecast and uncertainty."""
import pandas as pd
import altair as alt
import streamlit as st
from forecast_workbench import MODEL_LABELS, interval_coverage, tree_explanation
from learning_ui import header, context, artifacts, tree_path, navigation, question
from ui import TEAL, ORANGE, NAVY, GOLD, callout

header("From earlier weeks to next week", "Follow the selected break. Change the method to see its forecast and the allocation change together.", 3)
case, campaign_id, campaign, break_id = context("forecast")
trained = artifacts()
method = st.session_state.lab_model
slot = case["breaks"].set_index("break_id").loc[break_id]
features = case["features"].set_index("break_id").loc[break_id]
history = trained.history[trained.history.slot_key == features.slot_key].sort_values("date").tail(8).copy()
history["Used directly"] = ["Earlier context"] * len(history)
count = 1 if method == "seasonal_naive" else 4
history.loc[history.tail(count).index, "Used directly"] = "Recent input"
history["Audience"] = history.actual_audience
points = alt.Chart(history).mark_line(point=True, color=NAVY).encode(
    x=alt.X("date:T", title="Earlier observations → selected future break", axis=alt.Axis(format="%d %b", tickCount=5)),
    y=alt.Y("Audience:Q", title="Synthetic audience", scale=alt.Scale(zero=False)),
    tooltip=[alt.Tooltip("date:T"), alt.Tooltip("Audience:Q", format=",.0f")])
highlight = alt.Chart(history).mark_circle(size=100).encode(
    x="date:T", y="Audience:Q",
    color=alt.Color("Used directly:N", scale=alt.Scale(domain=["Earlier context", "Recent input"], range=["#BBB5AA", TEAL]), title=None),
    tooltip=["Used directly:N", alt.Tooltip("Audience:Q", format=",.0f")])
future = pd.DataFrame([{"date": slot.air_time, "P20": slot.adults_p20, "P50": slot.adults_p50, "P80": slot.adults_p80}])
interval = alt.Chart(future).mark_rule(color=ORANGE, strokeWidth=7).encode(x="date:T", y=alt.Y("P20:Q", scale=alt.Scale(zero=False)), y2="P80:Q", tooltip=[alt.Tooltip("P20:Q", format=",.0f"), alt.Tooltip("P80:Q", format=",.0f")])
median = alt.Chart(future).mark_point(shape="diamond", filled=True, size=160, color=ORANGE).encode(x="date:T", y="P50:Q", tooltip=[alt.Tooltip("P50:Q", format=",.0f")])
st.altair_chart((points+highlight+interval+median).properties(height=230).configure_view(strokeWidth=0), width="stretch")
st.caption("Teal dots: recent inputs. Orange diamond: next week's median estimate. Orange line: estimated P20–P80 range. The vertical axis is zoomed to show changes. All data is synthetic.")
explanations = {
    "seasonal_naive": f"Copy the same slot from last week: {features.lag_1_week:,.0f}. This is the seasonal naïve baseline.",
    "rolling_average": f"Average the latest four comparable weeks: {features.rolling_4_week:,.0f}. This smooths one unusually high or low week.",
    "linear_regression": "Multiply the inputs by weights learned from training history, then add them. The inputs include recent audience, channel, time and genre.",
    "xgboost": "Start with a base value and add contributions from 120 small trees learned from training history. The trees combine recent audience with channel, time and genre.",
}
callout("What changed and why?", explanations[method] + f" Raw model prediction: {slot.raw_prediction:,.0f}. Past forecast errors then adjust the uncertainty estimates below.")
c1,c2,c3 = st.columns(3)
c1.metric("Lower estimate · P20", f"{slot.adults_p20:,.0f}")
c2.metric("Median estimate · P50", f"{slot.adults_p50:,.0f}")
c3.metric("Upper estimate · P80", f"{slot.adults_p80:,.0f}")
st.caption("Approximately 20%, 50% and 80% of future outcomes should fall below these respective estimates. This is checked over many breaks; none is a guarantee.")
question("forecast", "Can we use the actual audience of this future break as an input?",
    ["Yes, it would make the prediction better", "No, it has not happened yet"],
    "No, it has not happened yet",
    "The forecast is issued before the week begins. Only observations available before that moment may become inputs.")

with st.expander("Follow a real XGBoost tree"):
    st.write("This is the fitted XGBoost model for the same selected break, even if you are comparing another method above.")
    tree_number = st.select_slider("Tree to inspect", options=list(range(1,121)), value=1, key="_lab_tree_index")
    explanation = tree_explanation(trained, features, tree_number-1)
    tree_path(explanation)
    st.caption("A categorical input is encoded as 0 or 1. For example, channel 3+ = 1 means this row is on 3+. Leaf contributions already include the learning-rate scaling.")
    values = explanation["contributions"]
    terms = pd.DataFrame({
        "Part": ["Base value", "Tree 1", "Tree 2", "Tree 3", "Trees 4–120"],
        "Contribution": [explanation["base"], *values[:3], sum(values[3:])]
    })
    terms["End"] = terms.Contribution.cumsum()
    terms["Start"] = terms.End-terms.Contribution
    buildup = alt.Chart(terms).mark_bar(cornerRadius=3).encode(
        y=alt.Y("Part:N", sort=terms.Part.tolist(), title=None),
        x=alt.X("Start:Q", title="Running audience prediction"), x2="End:Q",
        color=alt.condition(alt.datum.Contribution >= 0, alt.value(TEAL), alt.value(ORANGE)),
        tooltip=["Part", alt.Tooltip("Contribution:Q", format="+,.2f"), alt.Tooltip("End:Q", format=",.2f")])
    st.altair_chart(buildup.properties(height=200), width="stretch")
    st.write(f"**Base + all 120 contributions = {explanation['reconstructed']:,.2f}.** Model prediction: {explanation['raw_prediction']:,.2f}.")
    st.caption("Tiny differences beyond displayed precision can come from floating-point arithmetic. This raw model output is separate from the calibrated median.")

with st.expander("Compare all four methods on later, unseen weeks"):
    metrics = trained.metrics.rename(columns={"model_label":"Method","mae":"MAE","wape":"WAPE","bias":"Bias"})
    st.dataframe(metrics[["Method","MAE","WAPE","Bias"]], hide_index=True, width="stretch", column_config={"MAE":st.column_config.NumberColumn(format="%.0f"),"WAPE":st.column_config.NumberColumn(format="%.4f"),"Bias":st.column_config.NumberColumn(format="%.0f")})
    st.write("MAE is the average size of a raw prediction error. WAPE divides total absolute error by total actual audience (0.07 means 7%). Bias is actual minus predicted: positive means the model usually predicted too low.")
    st.caption("A single synthetic test period demonstrates evaluation; it does not establish a production winner.")
    cover = interval_coverage(trained, method)
    chart = pd.DataFrame({"Level":["P20","P50","P80"],"Observed":[cover["below_p20"],cover["below_p50"],cover["below_p80"]],"Target":[.2,.5,.8]})
    bars = alt.Chart(chart).mark_bar(color=TEAL).encode(x=alt.X("Level:N", sort=["P20","P50","P80"]),y=alt.Y("Observed:Q", axis=alt.Axis(format="%"),scale=alt.Scale(domain=[0,1]),title="Share of actual audiences below estimate"),tooltip=["Level",alt.Tooltip("Observed:Q",format=".1%")])
    targets = alt.Chart(chart).mark_tick(color=ORANGE,size=40,thickness=3).encode(x="Level:N",y="Target:Q")
    st.altair_chart((bars+targets).properties(height=190),width="stretch")
    st.caption("Orange marks show target coverage. Calibration pools residuals across all channels and slots; aggregate coverage can hide weaker coverage for individual groups.")
    group = trained.predictions[(trained.predictions.model == method) & (trained.predictions.channel == slot.channel) & (trained.predictions.daypart == slot.daypart)]
    if not group.empty:
        group_coverage = (group.actual_audience <= group.p20).mean()
        st.write(f"For {slot.channel} / {slot.daypart} alone, {group_coverage:.0%} of {len(group):,} test audiences fell below P20. Compare this with the 20% target before trusting the estimate for this group.")

with st.expander("How we keep time in the correct order"):
    timeline = pd.DataFrame([
        {"Period":"Train","Start":trained.history.date.min(),"End":trained.training_cutoff},
        {"Period":"Calibrate","Start":trained.calibration_start,"End":trained.split_dates.validation_end},
        {"Period":"Test","Start":trained.predictions.date.min(),"End":trained.split_dates.test_end}])
    chart = alt.Chart(timeline).mark_bar(cornerRadius=5).encode(x=alt.X("Start:T",title="Time"),x2="End:T",y=alt.Y("Period:N",sort=["Train","Calibrate","Test"],title=None),color=alt.Color("Period:N",scale=alt.Scale(range=[GOLD,ORANGE,TEAL]),legend=None),tooltip=["Period","Start","End"])
    st.altair_chart(chart.properties(height=130),width="stretch")
    st.write("Training fits model weights and trees once. Calibration measures later prediction errors and takes their 20th, 50th and 80th percentiles. Testing checks a later untouched period. The model is not refitted on the calibration data.")
    st.write("The test simulates issuing a fresh one-week forecast each Monday. Earlier test-week outcomes can become history for a later Monday; no observation from the week being predicted is used.")
    st.write(f"Selected forecast issued: {slot.forecast_issue_time:%d %b %Y %H:%M}. Model trained through: {slot.training_cutoff:%d %b %Y}. Calibration: {slot.calibration_start:%d %b}–{slot.calibration_end:%d %b %Y}.")
    st.dataframe(pd.DataFrame([features]),hide_index=True,width="stretch")
    st.caption(f"For comparison only, 78% of this raw prediction is {max(slot.raw_prediction*.78,0):,.0f}. This fixed safety buffer has no calibrated probability.")

with st.expander("Feature importance and other model choices"):
    importance = pd.DataFrame({"Feature":trained.feature_columns,"Gain":trained.model.feature_importances_}).sort_values("Gain",ascending=False).head(8)
    st.altair_chart(alt.Chart(importance).mark_bar(color=TEAL).encode(x="Gain:Q",y=alt.Y("Feature:N",sort="-x")).properties(height=220),width="stretch")
    st.write("Gain measures average improvement in the training loss from splits using a feature, then normalizes it. It is not usage frequency or evidence of cause and effect.")
    st.write("ARIMA can be useful for a regular time series with temporal structure. Seasonal extensions and external regressors are possible; many changing programmes and channels make the setup less convenient.")
    st.write("LSTMs and transformers can learn sequence patterns. Their value depends on the data and model, including pretrained models. Add one only when time-based evaluation shows a useful improvement over these simpler methods.")
navigation(2)
