
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

# Revenue / Cost / Margin (using the filtered view)
if "Qty" in filtered.columns:
    # Ensure numeric
    for df_ in (filtered, filtered_base):
        df_["Qty"] = pd.to_numeric(df_["Qty"], errors="coerce").fillna(0.0)
        df_["Price"] = pd.to_numeric(df_["Price"], errors="coerce")
        df_["Per Service"] = pd.to_numeric(df_["Per Service"], errors="coerce")

    rev_after = (filtered["Qty"] * filtered["Price"]).sum()
    rev_before = (filtered_base["Qty"] * filtered_base["Price"]).sum()
    rev_delta = rev_after - rev_before

    cost_after = (filtered["Qty"] * filtered["Per Service"]).sum()
    cost_before = (filtered_base["Qty"] * filtered_base["Per Service"]).sum()
    cost_delta = cost_after - cost_before

    margin_after = rev_after - cost_after
    margin_before = rev_before - cost_before
    margin_delta = margin_after - margin_before

    # Rightmost KPI shows Margin impact (what you "make" after paying Per Service)
    # Note: This is NOT the same as revenue (Qty × Price).
    k4.metric(
        "Margin impact (Before → After)",
        f"£{margin_before:,.2f} → £{margin_after:,.2f}",
        delta=f"{margin_delta:+,.2f}",
        delta_color="normal",
    )

    r1, r2, r3 = st.columns(3)
    r1.metric("Qty × Price (Before)", f"£{rev_before:,.2f}")
    r2.metric("Qty × Price (After)", f"£{rev_after:,.2f}")
    r3.metric("Qty × Price (Delta)", f"£{rev_delta:,.2f}", delta=f"{rev_delta:+,.2f}", delta_color="normal")

    c1, c2, c3 = st.columns(3)
    c1.metric("Qty × Per Service (Before)", f"£{cost_before:,.2f}")
    c2.metric("Qty × Per Service (After)", f"£{cost_after:,.2f}")
    c3.metric("Qty × Per Service (Delta)", f"£{cost_delta:,.2f}", delta=f"{cost_delta:+,.2f}", delta_color="normal")
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
    st.info("Upload a volumes file (Qty) to see revenue/cost/margin totals and stylist summary.")

# Helpful indicator: overrides in effect
overrides_active = 0
if "service_overrides" in st.session_state:
    ov = st.session_state["service_overrides"]
    overrides_active = int(ov["Override Price"].notna().sum() + ov["Override Per Service"].notna().sum())
if overrides_active:
    st.warning(f"Overrides active: {overrides_active} cell(s) set in Service-level overrides (these affect totals).")
st.subheader("Stylist summary (filtered)")



# ---------------- Diagnostics: what changed? ----------------
with st.expander("Diagnostics — what changed between Before and After?", expanded=False):
    # Compare scenario vs baseline row-by-row (Services + Stylist)
    key_cols = ["Services", "Stylist"]
    left = filtered_base[key_cols + (["Qty"] if "Qty" in filtered_base.columns else []) + ["Price", "Per Service"]].copy()
    right = filtered[key_cols + (["Qty"] if "Qty" in filtered.columns else []) + ["Price", "Per Service"]].copy()

    left = left.rename(columns={"Price": "Price_Before", "Per Service": "PerService_Before"})
    right = right.rename(columns={"Price": "Price_After", "Per Service": "PerService_After"})

    comp = left.merge(right, on=key_cols + (["Qty"] if "Qty" in left.columns and "Qty" in right.columns else []), how="outer")

    for c in ["Price_Before","Price_After","PerService_Before","PerService_After"]:
        comp[c] = pd.to_numeric(comp[c], errors="coerce")

    comp["Price_Diff"] = comp["Price_After"] - comp["Price_Before"]
    comp["PerService_Diff"] = comp["PerService_After"] - comp["PerService_Before"]

    if "Qty" in comp.columns:
        comp["Qty"] = pd.to_numeric(comp["Qty"], errors="coerce").fillna(0.0)
        comp["Rev_Delta"] = comp["Qty"] * comp["Price_Diff"]
        comp["Cost_Delta"] = comp["Qty"] * comp["PerService_Diff"]
        comp["Margin_Delta"] = comp["Rev_Delta"] - comp["Cost_Delta"]

    changed = comp[(comp["Price_Diff"].fillna(0).abs() > 1e-9) | (comp["PerService_Diff"].fillna(0).abs() > 1e-9)].copy()
    if len(changed) == 0:
        st.success("No per-row changes detected (Before and After match for the filtered selection).")
    else:
        st.warning(f"{len(changed):,} row(s) have changes. This explains any non-zero deltas.")
        show_cols = key_cols + (["Qty"] if "Qty" in comp.columns else []) + [
            "Price_Before","Price_After","Price_Diff",
            "PerService_Before","PerService_After","PerService_Diff",
        ]
        if "Qty" in comp.columns:
            show_cols += ["Rev_Delta","Cost_Delta","Margin_Delta"]
        changed = changed[show_cols].sort_values(["Stylist","Services"]).reset_index(drop=True)
        st.dataframe(changed, use_container_width=True, height=420)

if "Qty" in filtered.columns:
    # Ensure numeric
    for df_ in (filtered, filtered_base):
        df_["Qty"] = pd.to_numeric(df_["Qty"], errors="coerce").fillna(0)
        df_["Price"] = pd.to_numeric(df_["Price"], errors="coerce")
        df_["Per Service"] = pd.to_numeric(df_["Per Service"], errors="coerce")

    # Totals
    filtered["QtyPriceTotal"] = filtered["Qty"] * filtered["Price"]
    filtered_base["QtyPriceTotal"] = filtered_base["Qty"] * filtered_base["Price"]

    filtered["QtyCostTotal"] = filtered["Qty"] * filtered["Per Service"]
    filtered_base["QtyCostTotal"] = filtered_base["Qty"] * filtered_base["Per Service"]

    after_by = filtered.groupby("Stylist", as_index=False).agg(
        QtyPriceTotal=("QtyPriceTotal", "sum"),
        QtyCostTotal=("QtyCostTotal", "sum"),
    )
    before_by = filtered_base.groupby("Stylist", as_index=False).agg(
        QtyPriceTotal_Before=("QtyPriceTotal", "sum"),
        QtyCostTotal_Before=("QtyCostTotal", "sum"),
    )

    summ = after_by.merge(before_by, on="Stylist", how="left")
    summ["Price Difference"] = summ["QtyPriceTotal"] - summ["QtyPriceTotal_Before"]
    summ["Value Difference"] = summ["QtyCostTotal"] - summ["QtyCostTotal_Before"]

    # Rename columns to requested names
    summ.rename(
        columns={
            "QtyPriceTotal": "Qty * Price Total",
            "QtyCostTotal": "Qty * Per Service Total",
        },
        inplace=True,
    )
    summ = summ[["Stylist", "Qty * Price Total", "Price Difference", "Qty * Per Service Total", "Value Difference"]]
    summ[["Qty * Price Total","Price Difference","Qty * Per Service Total","Value Difference"]] = summ[["Qty * Price Total","Price Difference","Qty * Per Service Total","Value Difference"]].round(2)

    summ = summ.sort_values("Stylist").reset_index(drop=True)

    st.dataframe(summ, use_container_width=True, height=420)
else:
    st.info("No volumes file loaded — stylist summary requires Qty.")

# ---------------- Scenario table view ----------------
st.caption(f"Showing {len(filtered):,} / {len(result):,} rows after filters.")
st.dataframe(filtered, use_container_width=True, height=520)

# ---------------- Validation ----------------
with st.expander("Validation checks"):
    if validations.get("missing_cost_services"):
        st.warning(f"{len(validations['missing_cost_services']):,} service(s) in prices are missing Per Service cost.")
        st.dataframe(pd.DataFrame({"Services": validations["missing_cost_services"]}), use_container_width=True)
    else:
        st.success("All priced services have a Per Service cost.")

    if validations.get("missing_price_services"):
        st.warning(f"{len(validations['missing_price_services']):,} service(s) exist in costs but not in prices.")
        st.dataframe(pd.DataFrame({"Services": validations["missing_price_services"]}), use_container_width=True)
    else:
        st.success("All costed services exist in prices.")

    if qty_df is not None:
        if validations.get("qty_unmatched_services"):
            st.warning(f"{len(validations['qty_unmatched_services']):,} service(s) in volumes could not be matched.")
            st.dataframe(pd.DataFrame({"Services": validations["qty_unmatched_services"]}), use_container_width=True)
        else:
            st.success("All volume services matched.")
    else:
        st.info("No volumes file uploaded; weighted checks disabled.")

# ---------------- Download ----------------
st.subheader("Download")

out = io.BytesIO()
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    result.to_excel(writer, index=False, sheet_name="Scenario Output")
    filtered.to_excel(writer, index=False, sheet_name="Filtered View")
    if "Qty" in filtered.columns:
        summ.to_excel(writer, index=False, sheet_name="Stylist Summary")
    st.session_state["service_overrides"].to_excel(writer, index=False, sheet_name="Service Overrides")
    price_matrix.to_excel(writer, index=False, sheet_name="Input_StylistPrices")
    service_cost.to_excel(writer, index=False, sheet_name="Input_ServiceCost")
    if qty_df is not None:
        qty_df.to_excel(writer, index=False, sheet_name="Input_Volumes")

out.seek(0)
st.download_button(
    "Download scenario output (.xlsx)",
    data=out,
    file_name="Touche Pricing Scenario.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
