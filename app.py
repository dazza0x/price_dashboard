
import io
import hmac
import pandas as pd
import numpy as np
import streamlit as st

from transform import (
    load_stylist_price_matrix,
    load_service_cost,
    load_optional_qty,
    load_staff_list,
    build_long_table,
    apply_scenario,
)

st.set_page_config(page_title="Touche Hairdressing — Pricing Dashboard", page_icon="📊", layout="wide")

def _require_password():
    if "auth" not in st.secrets or "password" not in st.secrets["auth"]:
        st.error('Password is not configured. Add to Streamlit Secrets:\n\n[auth]\npassword = "your-strong-password"')
        st.stop()
    if st.session_state.get("authenticated"):
        return
    st.sidebar.subheader("🔒 Access")
    pw = st.sidebar.text_input("Password", type="password")
    correct = st.secrets["auth"]["password"]
    if pw and hmac.compare_digest(pw, correct):
        st.session_state["authenticated"] = True
        st.sidebar.success("Access granted")
        return
    if pw:
        st.sidebar.error("Incorrect password")
    st.stop()

def _reset_scenario():
    """
    Reset approach:
    - Explicitly set global widget keys (these are the widget's source of truth)
    - Clear overrides so they rebuild from data
    - Clear filters so they revert to defaults
    """
    # Global scenario defaults
    st.session_state["global_price_mode"] = "Percent"
    st.session_state["global_price_adj"] = 0.0
    st.session_state["global_cost_mode"] = "Percent"
    st.session_state["global_cost_adj"] = 0.0


    # Filters
    for k in ["filter_services", "filter_stylists", "filter_qty_range", "filter_cost_range",
              "filter_hide_zero_qty", "filter_hide_missing_cost"]:
        st.session_state.pop(k, None)

    # Overrides tables
    for k in ["service_overrides", "service_overrides_editor"]:
        st.session_state.pop(k, None)

    st.rerun()

_require_password()

st.title("📊 Touche Hairdressing — Pricing & Cost What‑If Dashboard")

# ---------------- Sidebar: uploads + reset ----------------


# ---------------- Chair rent inputs ----------------
st.subheader("Chair rent")

# Rent Plus applies to all stylists
if "rent_plus" not in st.session_state:
    st.session_state["rent_plus"] = 0.0

rent_plus = st.number_input("Rent Plus (£ per day)", step=1.0, key="rent_plus")

# Days table (one row per stylist). We build it later once stylists are known, so initialise placeholder here.
# The real table is created after data is loaded (so we know stylist list).
with st.sidebar:
    st.header("Uploads (required)")
    prices_file = st.file_uploader("1) Stylist Prices (xls/xlsx)", type=["xls", "xlsx"])
    cost_file = st.file_uploader("2) Service Cost (xls/xlsx)", type=["xls", "xlsx"])

    st.divider()
    st.header("Optional volumes")
    qty_file = st.file_uploader("3) Volumes (xls/xlsx) — optional", type=["xls", "xlsx"])
    st.caption("Accepted: simple table (Stylist, Services/Description, Qty) OR a 'Service Sales by Team Member' report.")

    st.divider()
    st.header("Optional staff filter")
    staff_file = st.file_uploader("Staff list (xlsx) — optional", type=["xls", "xlsx"])
    salon_choice = st.selectbox("Salon filter", ["Caterham", "Purley"], index=0)
    st.caption("If provided, keeps only rows where Salon matches and Type=Stylist.")

    st.divider()
    if st.button("Reset scenario", use_container_width=True):
        _reset_scenario()

if prices_file is None or cost_file is None:
    st.info("Upload **Stylist Prices** and **Service Cost** to start.")
    st.stop()

# ---------------- Load inputs ----------------
price_matrix, _ = load_stylist_price_matrix(prices_file)
service_cost = load_service_cost(cost_file)

allowed_stylists = None
if staff_file is not None:
    staff_df = load_staff_list(staff_file)
    staff_df = staff_df[
        (staff_df["Salon"].astype(str).str.strip().str.lower() == salon_choice.lower())
        & (staff_df["Type"].astype(str).str.strip().str.lower() == "stylist")
    ].copy()
    allowed_stylists = set(staff_df["Stylist"].astype(str).str.strip())

qty_df = None
if qty_file is not None:
    qty_df = load_optional_qty(qty_file, allowed_stylists=allowed_stylists)

base_long, validations = build_long_table(price_matrix, service_cost, qty_df)
if allowed_stylists:
    base_long = base_long[base_long["Stylist"].isin(allowed_stylists)].copy()

# ---------------- Global scenario controls (main area) ----------------
st.subheader("Global scenario")

# Ensure widget keys exist BEFORE widgets are created (allows programmatic reset without 'value=' conflicts)
if "global_price_mode" not in st.session_state:
    st.session_state["global_price_mode"] = "Percent"
if "global_price_adj" not in st.session_state:
    st.session_state["global_price_adj"] = 0.0
if "global_cost_mode" not in st.session_state:
    st.session_state["global_cost_mode"] = "Percent"
if "global_cost_adj" not in st.session_state:
    st.session_state["global_cost_adj"] = 0.0


c1, c2, c3, c4 = st.columns([1.2, 1, 1.2, 1])
with c1:
    price_mode = st.selectbox("Price adjustment mode", ["Percent", "Add £"], key="global_price_mode")
with c2:
    price_adj = st.number_input("Price adjustment", step=0.5, key="global_price_adj")
with c3:
    cost_mode = st.selectbox("Per Service adjustment mode", ["Percent", "Add £"], key="global_cost_mode")
with c4:
    cost_adj = st.number_input("Per Service adjustment", step=0.5, key="global_cost_adj")

scenario = {
    "global_price_mode": price_mode,
    "global_price_adj": float(price_adj),
    "global_cost_mode": cost_mode,
    "global_cost_adj": float(cost_adj),
}

# ---------------- Scenario controls (service overrides only) ----------------
st.subheader("Scenario controls")

services = sorted(base_long["Services"].dropna().astype(str).unique())
default_service_overrides = pd.DataFrame(
    {"Services": services, "Override Price": np.nan, "Override Per Service": np.nan}
)
if "service_overrides" not in st.session_state:
    st.session_state["service_overrides"] = default_service_overrides

with st.expander("Service-level overrides (optional) — set absolute values", expanded=False):
    st.caption("If you set an override, it becomes the final value (global adjustments are not applied on top).")
    st.session_state["service_overrides"] = st.data_editor(
        st.session_state["service_overrides"],
        use_container_width=True,
        hide_index=True,
        key="service_overrides_editor",
    )

# No per-stylist adjustments table (requested). Use a zeroed controls table internally.
stylists = sorted(base_long["Stylist"].dropna().astype(str).unique())

# Chair rent table (days worked) — editable
default_rent_days = pd.DataFrame({"Stylist": stylists, "Days": 0.0})
if "rent_days" not in st.session_state:
    st.session_state["rent_days"] = default_rent_days

st.session_state["rent_days"] = st.data_editor(
    st.session_state["rent_days"],
    use_container_width=True,
    hide_index=True,
    key="rent_days_editor",
)

rent_days_df = st.session_state["rent_days"].copy()
rent_days_df["Stylist"] = rent_days_df["Stylist"].astype(str).str.strip()
rent_days_df["Days"] = pd.to_numeric(rent_days_df["Days"], errors="coerce").fillna(0.0)
rent_days_df["Total Rent"] = (rent_days_df["Days"] * float(rent_plus)).round(2)

# Display computed rent
st.dataframe(rent_days_df[["Stylist", "Days", "Total Rent"]], use_container_width=True, height=260)

stylist_controls = pd.DataFrame(
    {"Stylist": stylists, "Price %": 0.0, "Price £": 0.0, "Cost %": 0.0, "Cost £": 0.0}
)

# ---------------- Apply scenario + baseline ----------------
result = apply_scenario(
    base_long=base_long,
    scenario=scenario,
    stylist_controls=stylist_controls,
    service_overrides=st.session_state["service_overrides"],
)

baseline_scenario = {
    "global_price_mode": "Percent",
    "global_price_adj": 0.0,
    "global_cost_mode": "Percent",
    "global_cost_adj": 0.0,
}
baseline_result = apply_scenario(
    base_long=base_long,
    scenario=baseline_scenario,
    stylist_controls=stylist_controls,
    service_overrides=default_service_overrides,  # baseline: no overrides
)

# ---------------- Filters (affect KPIs + view) ----------------
st.subheader("Scenario table")

filtered = result.copy()
filtered_base = baseline_result.copy()


with st.expander("Filters", expanded=False):
    # NOTE: bounds are computed from BOTH scenario + baseline so the default range does not accidentally
    # filter out baseline rows (which would create a fake revenue delta).
    svc_all = sorted(filtered["Services"].dropna().astype(str).unique())
    sty_all = sorted(filtered["Stylist"].dropna().astype(str).unique())

    sel_services = st.multiselect("Services", svc_all, default=svc_all, key="filter_services")
    sel_stylists = st.multiselect("Stylist", sty_all, default=sty_all, key="filter_stylists")

    hide_zero_qty = None
    if "Qty" in filtered.columns:
        hide_zero_qty = st.checkbox("Hide rows with Qty = 0", value=True, key="filter_hide_zero_qty")

    hide_missing_cost = st.checkbox("Hide rows with missing Per Service", value=True, key="filter_hide_missing_cost")

    # Combine for bounds
    both = pd.concat([filtered, filtered_base], ignore_index=True)

    qty_range = None
    if "Qty" in both.columns and len(both):
        qmin, qmax = int(pd.to_numeric(both["Qty"], errors="coerce").fillna(0).min()), int(pd.to_numeric(both["Qty"], errors="coerce").fillna(0).max())
        qty_range = st.slider("Qty range", min_value=qmin, max_value=qmax, value=(qmin, qmax), key="filter_qty_range")

    cost_range = None
    if len(both) and pd.to_numeric(both["Per Service"], errors="coerce").notna().any():
        cmin = float(pd.to_numeric(both["Per Service"], errors="coerce").min())
        cmax = float(pd.to_numeric(both["Per Service"], errors="coerce").max())
        cost_range = st.slider("Per Service range", min_value=cmin, max_value=cmax, value=(cmin, cmax), key="filter_cost_range")
def _apply_filters_values(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out[out["Services"].astype(str).isin(sel_services)]
    out = out[out["Stylist"].astype(str).isin(sel_stylists)]

    if hide_zero_qty and "Qty" in out.columns:
        out = out[out["Qty"] != 0]

    if hide_missing_cost:
        out = out[out["Per Service"].notna()]

    if qty_range is not None and "Qty" in out.columns:
        out = out[(out["Qty"] >= qty_range[0]) & (out["Qty"] <= qty_range[1])]

    if cost_range is not None:
        out = out[(out["Per Service"] >= cost_range[0]) & (out["Per Service"] <= cost_range[1])]

    return out

filtered = _apply_filters_values(filtered)
filtered_base = _apply_filters_values(filtered_base)

# ---------------- KPIs (filtered) — moved up under Global Scenario ----------------

# ---------------- KPIs (filtered) — moved up under Global Scenario ----------------
st.subheader("KPIs (filtered)")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows (filtered)", f"{len(filtered):,}")
k2.metric("Services (filtered)", f"{filtered['Services'].nunique():,}")
k3.metric("Stylists (filtered)", f"{filtered['Stylist'].nunique():,}")

# Revenue / Cost / Salon income (using the filtered view)
if "Qty" in filtered.columns:
    # Ensure numeric
    for df_ in (filtered, filtered_base):
        df_["Qty"] = pd.to_numeric(df_["Qty"], errors="coerce").fillna(0.0)
        df_["Price"] = pd.to_numeric(df_["Price"], errors="coerce")
        df_["Per Service"] = pd.to_numeric(df_["Per Service"], errors="coerce")

    # Client-facing revenue (what stylist charges)
    rev_after = (filtered["Qty"] * filtered["Price"]).sum()
    rev_before = (filtered_base["Qty"] * filtered_base["Price"]).sum()
    rev_delta = rev_after - rev_before

    # Service charges payable to salon (Per Service)
    svc_after = (filtered["Qty"] * filtered["Per Service"]).sum()
    svc_before = (filtered_base["Qty"] * filtered_base["Per Service"]).sum()
    svc_delta = svc_after - svc_before

    # Chair rent (one value per stylist in the filtered selection)
    rent_map = rent_days_df.set_index("Stylist")["Total Rent"].to_dict()
    rent_after = filtered["Stylist"].map(rent_map).fillna(0.0).drop_duplicates().sum()
    rent_before = filtered_base["Stylist"].map(rent_map).fillna(0.0).drop_duplicates().sum()
    rent_delta = rent_after - rent_before

    # Salon income = service charges + chair rent
    income_after = svc_after + rent_after
    income_before = svc_before + rent_before
    income_delta = income_after - income_before

    k4.metric(
        "Salon income (Per Service + Rent)",
        f"£{income_before:,.2f} → £{income_after:,.2f}",
        delta=f"{income_delta:+,.2f}",
        delta_color="normal",
    )

    r1, r2, r3 = st.columns(3)
    r1.metric("Qty × Price (Before)", f"£{rev_before:,.2f}")
    r2.metric("Qty × Price (After)", f"£{rev_after:,.2f}")
    r3.metric("Qty × Price (Delta)", f"£{rev_delta:,.2f}", delta=f"{rev_delta:+,.2f}", delta_color="normal")

    s1, s2, s3 = st.columns(3)
    s1.metric("Qty × Per Service (Before)", f"£{svc_before:,.2f}")
    s2.metric("Qty × Per Service (After)", f"£{svc_after:,.2f}")
    s3.metric("Qty × Per Service (Delta)", f"£{svc_delta:,.2f}", delta=f"{svc_delta:+,.2f}", delta_color="normal")

    rt1, rt2, rt3 = st.columns(3)
    rt1.metric("Chair rent (Before)", f"£{rent_before:,.2f}")
    rt2.metric("Chair rent (After)", f"£{rent_after:,.2f}")
    rt3.metric("Chair rent (Delta)", f"£{rent_delta:,.2f}", delta=f"{rent_delta:+,.2f}", delta_color="normal")
else:
    # Fallback when Qty isn't available (no volumes file)
    after_profit = filtered["Difference"].sum()
    before_profit = filtered_base["Difference"].sum()
    delta_profit = after_profit - before_profit
    k4.metric(
        "Profit impact (Before → After)",
        f"£{before_profit:,.2f} → £{after_profit:,.2f}",
        delta=f"{delta_profit:+,.2f}",
        delta_color="normal",
    )
    st.info("Upload a volumes file (Qty) to see revenue, service charges, chair rent and stylist summary.")

# Helpful indicator: overrides in effect
overrides_active = 0
if "service_overrides" in st.session_state:
    ov = st.session_state["service_overrides"]
    overrides_active = int(ov["Override Price"].notna().sum() + ov["Override Per Service"].notna().sum())
if overrides_active:
    st.warning(f"Overrides active: {overrides_active} cell(s) set in Service-level overrides (these affect totals).")

st.subheader("Stylist summary (filtered)")

if "Qty" in filtered.columns:
    summ = (
        filtered.groupby("Stylist", dropna=False)
        .apply(lambda x: pd.Series({
            "Qty * Price Total": (x["Qty"] * x["Price"]).sum(),
            "Qty * Per Service Total": (x["Qty"] * x["Per Service"]).sum(),
        }))
        .reset_index()
    )

    base_summ = (
        filtered_base.groupby("Stylist", dropna=False)
        .apply(lambda x: pd.Series({
            "Qty * Price Total (Base)": (x["Qty"] * x["Price"]).sum(),
            "Qty * Per Service Total (Base)": (x["Qty"] * x["Per Service"]).sum(),
        }))
        .reset_index()
    )

    summ = summ.merge(base_summ, on="Stylist", how="left").fillna(0.0)

    summ["Price Difference"] = summ["Qty * Price Total"] - summ["Qty * Price Total (Base)"]
    summ["Value Difference"] = summ["Qty * Per Service Total"] - summ["Qty * Per Service Total (Base)"]

    # Add Chair Rent
    rent_map = rent_days_df.set_index("Stylist")["Total Rent"].to_dict()
    summ["Total Rent"] = summ["Stylist"].map(rent_map).fillna(0.0)

    summ["Salon Income Total"] = summ["Qty * Per Service Total"] + summ["Total Rent"]
    summ["Income Difference"] = summ["Value Difference"]  # rent constant unless changed

    summ = summ[[
        "Stylist",
        "Qty * Price Total",
        "Price Difference",
        "Qty * Per Service Total",
        "Value Difference",
        "Total Rent",
        "Salon Income Total",
        "Income Difference",
    ]]

    # Round currency columns
    currency_cols = summ.columns.drop("Stylist")
    summ[currency_cols] = summ[currency_cols].round(2)

    summ = summ.sort_values("Stylist").reset_index(drop=True)

    st.dataframe(summ, use_container_width=True, height=400)

else:
    st.info("Upload a volumes file (Qty) to see stylist summary.")


