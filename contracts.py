"""Executable input and output contracts shared by the model and allocation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def required(frame, columns, name):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        return [f"{name}: missing columns {', '.join(missing)}"]
    if frame[list(columns)].isna().any().any():
        return [f"{name}: required values are missing"]
    return []


def keys(frame, columns, name):
    if frame.empty:
        return []
    return [f"{name}: duplicate or blank key"] if (
        frame.duplicated(columns).any()
        or any(frame[c].astype(str).str.strip().eq("").any() for c in columns)
    ) else []


def numeric(frame, columns, name, positive=False, integer=False):
    errors = []
    for column in columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            errors.append(f"{name}: {column} must contain numeric values")
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        bad = ~np.isfinite(values) | (values <= 0 if positive else values < 0)
        if integer:
            bad |= values.mod(1).ne(0)
        if bad.any():
            errors.append(f"{name}: invalid {column}")
    return errors


def programme_errors(frame):
    errors = required(frame, ["programme_id", "channel", "start", "stop", "duration_min", "genre"], "Programmes")
    if errors:
        return errors
    errors += keys(frame, ["programme_id"], "Programmes")
    errors += numeric(frame, ["duration_min"], "Programmes", positive=True)
    if errors:
        return errors
    if not all(pd.api.types.is_datetime64_any_dtype(frame[c]) for c in ["start", "stop"]):
        return ["Programmes: timestamps must be parsed dates"]
    if (frame.stop <= frame.start).any():
        errors.append("Programmes: stop must follow start")
    durations = (frame.stop - frame.start).dt.total_seconds() / 60
    if not np.allclose(durations, frame.duration_min):
        errors.append("Programmes: duration disagrees with timestamps")
    ordered = frame.sort_values(["channel", "start"])
    # Running maximum also detects a long programme containing several shorter ones.
    prior = ordered.groupby("channel")["stop"].transform(lambda values: values.cummax().shift())
    if (ordered.start < prior).any():
        errors.append("Programmes: overlapping intervals on the same channel")
    return errors


def allocation_errors(breaks, requests, placements=None):
    bc = ["break_id", "programme_id", "channel", "air_time", "daypart", "capacity_sec", "presold_sec", "adults_p20", "adults_p50"]
    rc = ["request_id", "status", "booked_on", "eligible_channels", "dayparts", "target_group", "spot_sec", "goal_impressions", "max_spots"]
    errors = required(breaks, bc, "Breaks") + required(requests, rc, "Campaigns")
    if errors:
        return errors
    errors += keys(breaks, ["break_id"], "Breaks") + keys(requests, ["request_id"], "Campaigns")
    errors += numeric(breaks, ["capacity_sec"], "Breaks", positive=True, integer=True)
    errors += numeric(breaks, ["presold_sec", "adults_p20", "adults_p50"], "Breaks")
    errors += numeric(requests, ["spot_sec", "max_spots"], "Campaigns", positive=True, integer=True)
    errors += numeric(requests, ["goal_impressions"], "Campaigns", positive=True)
    if errors:
        return errors
    if not pd.api.types.is_datetime64_any_dtype(breaks.air_time):
        return ["Breaks: airtime must be a parsed date"]
    if "adults_p80" in breaks:
        errors += numeric(breaks, ["adults_p80"], "Breaks")
        if errors:
            return errors
        if (breaks.adults_p50 > breaks.adults_p80).any():
            errors.append("Breaks: median exceeds upper forecast")
    if (breaks.presold_sec > breaks.capacity_sec).any():
        errors.append("Breaks: existing bookings exceed capacity")
    if (breaks.adults_p20 > breaks.adults_p50).any():
        errors.append("Breaks: lower forecast exceeds median")
    if not requests.status.isin(["firm", "option"]).all():
        errors.append("Campaigns: unknown status")
    if not requests.target_group.isin(["All adults", "Women 25–49"]).all():
        errors.append("Campaigns: unsupported target group")
    if pd.to_datetime(requests.booked_on, errors="coerce").isna().any():
        errors.append("Campaigns: invalid booking date")
    for column in ["eligible_channels", "dayparts"]:
        for value in requests[column]:
            parts = [p.strip() for p in str(value).split("|") if p.strip()]
            if not parts or len(parts) != len(set(parts)):
                errors.append(f"Campaigns: empty or duplicate {column}")
                break
    if placements is None or placements.empty:
        return errors
    pc = ["request_id", "break_id", "spot_sec", "target_p20", "target_p50"]
    malformed = required(placements, pc, "Placements")
    if malformed:
        return errors + malformed
    errors += keys(placements, ["request_id", "break_id"], "Placements")
    errors += numeric(placements, ["spot_sec"], "Placements", positive=True, integer=True)
    errors += numeric(placements, ["target_p20", "target_p50"], "Placements")
    if not placements.break_id.isin(breaks.break_id).all() or not placements.request_id.isin(requests.request_id).all():
        return errors + ["Placements: unknown campaign or break reference"]
    if errors:
        return errors
    b = breaks.set_index("break_id")
    r = requests.set_index("request_id")
    for p in placements.itertuples():
        request, slot = r.loc[p.request_id], b.loc[p.break_id]
        if slot.channel not in [v.strip() for v in request.eligible_channels.split("|")] or slot.daypart not in [v.strip() for v in request.dayparts.split("|")]:
            errors.append("Placements: ineligible channel or daypart")
        if p.spot_sec != request.spot_sec:
            errors.append("Placements: duration differs from campaign")
        share = 1.0 if request.target_group == "All adults" else 0.28
        if p.target_p20 != int(slot.adults_p20 * share) or p.target_p50 != int(slot.adults_p50 * share):
            errors.append("Placements: audience differs from supplied forecast")
    used = placements.groupby("break_id").spot_sec.sum().reindex(b.index, fill_value=0) + b.presold_sec
    if (used > b.capacity_sec).any():
        errors.append("Placements: total used seconds exceed capacity")
    counts = placements.groupby("request_id").size().reindex(r.index, fill_value=0)
    if (counts > r.max_spots).any():
        errors.append("Placements: campaign spot limit exceeded")
    return list(dict.fromkeys(errors))


def require_valid(errors):
    if errors:
        raise ValueError("Data check failed: " + "; ".join(errors))
