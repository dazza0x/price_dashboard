
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
    # Explicit defaults
    st.session_state["global_price_mode"] = "Percent"
    st.session_state["global_price_adj"] = 0.0
    st.session_state["global_cost_mode"] = "Percent"
    st.session_state["global_cost_adj"] = 0.0

    # Reset filters
    st.session_state.pop("filter_services", None)
    st.session_state.pop("filter_stylists", None)
    st.session_state["filter_hide_zero_qty"] = True
    st.session_state["filter_hide_missing_cost"] = True
    st.session_state.pop("filter_qty_range", None)
    st.session_state.pop("filter_cost_range", None)

    # Clear tables so they rebuild from data
    for k in ["stylist_controls", "service_overrides", "stylist_controls_editor", "service_overrides_editor"]:
        st.session_state.pop(k, None)

    st.rerun()

_require_password()

st.title("📊 Touche Hairdressing — Pricing & Cost What‑If Dashboard")

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

# --- Load inputs ---
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

# --- Global scenario controls (main area) ---
st.subheader("Global scenario")

c1, c2, c3, c4 = st.columns([1.2, 1, 1.2, 1])
with c1:
    price_mode = st.selectbox("Price adjustment mode", ["Percent", "Add £"], index=0, key="global_price_mode")
with c2:
    price_adj = st.number_input("Price adjustment", value=0.0, step=0.5, key="global_price_adj")
with c3:
    cost_mode = st.selectbox("Per Service adjustment mode", ["Percent", "Add £"], index=0, key="global_cost_mode")
with c4:
    cost_adj = st.number_input("Per Service adjustment", value=0.0, step=0.5, key="global_cost_adj")

scenario = {
    "global_price_mode": price_mode,
    "global_price_adj": float(price_adj),
    "global_cost_mode": cost_mode,
    "global_cost_adj": float(cost_adj),
}

# --- Scenario controls ---
st.subheader("Scenario controls")

stylists = sorted(base_long["Stylist"].dropna().astype(str).unique())
default_stylist_controls = pd.DataFrame({"Stylist": stylists, "Price %": 0.0, "Price £": 0.0, "Cost %": 0.0, "Cost £": 0.0})
if "stylist_controls" not in st.session_state:
    st.session_state["stylist_controls"] = default_stylist_controls

with st.expander("Scenario controls — by stylist", expanded=True):
    st.session_state["stylist_controls"] = st.data_editor(
        st.session_state["stylist_controls"],
        use_container_width=True,
        hide_index=True,
        key="stylist_controls_editor",
    )

services = sorted(base_long["Services"].dropna().astype(str).unique())
default_service_overrides = pd.DataFrame({"Services": services, "Override Price": np.nan, "Override Per Service": np.nan})
if "service_overrides" not in st.session_state:
    st.session_state["service_overrides"] = default_service_overrides

with st.expander("Service-level overrides (optional) — set absolute values", expanded=False):
    st.caption("If you set an override, it becomes the final value (global/stylist adjustments are not applied on top).")
    st.session_state["service_overrides"] = st.data_editor(
        st.session_state["service_overrides"],
        use_container_width=True,
        hide_index=True,
        key="service_overrides_editor",
    )

# --- Apply scenario + baseline ---
result = apply_scenario(
    base_long=base_long,
    scenario=scenario,
    stylist_controls=st.session_state["stylist_controls"],
    service_overrides=st.session_state["service_overrides"],
)

baseline_scenario = {"global_price_mode": "Percent", "global_price_adj": 0.0, "global_cost_mode": "Percent", "global_cost_adj": 0.0}
baseline_controls = st.session_state["stylist_controls"].copy()
for c in ["Price %", "Price £", "Cost %", "Cost £"]:
    if c in baseline_controls.columns:
        baseline_controls[c] = 0.0
baseline_overrides = st.session_state["service_overrides"].copy()
for c in ["Override Price", "Override Per Service"]:
    if c in baseline_overrides.columns:
        baseline_overrides[c] = np.nan

baseline_result = apply_scenario(
    base_long=base_long,
    scenario=baseline_scenario,
    stylist_controls=baseline_controls,
    service_overrides=baseline_overrides,
)

# --- Filters (affect KPIs + view) ---
st.subheader("Scenario table")

filtered = result.copy()
filtered_base = baseline_result.copy()


with st.expander("Filters", expanded=False):
    svc_all = sorted(filtered["Services"].dropna().astype(str).unique())
    sty_all = sorted(filtered["Stylist"].dropna().astype(str).unique())

    sel_services = st.multiselect("Services", svc_all, default=svc_all, key="filter_services")
    sel_stylists = st.multiselect("Stylist", sty_all, default=sty_all, key="filter_stylists")

    hide_zero_qty = None
    if "Qty" in filtered.columns:
        hide_zero_qty = st.checkbox("Hide rows with Qty = 0", value=True, key="filter_hide_zero_qty")

    hide_missing_cost = st.checkbox("Hide rows with missing Per Service", value=True, key="filter_hide_missing_cost")

    qty_range = None
    if "Qty" in filtered.columns and len(filtered):
        qmin, qmax = int(filtered["Qty"].min()), int(filtered["Qty"].max())
        qty_range = st.slider(
            "Qty range",
            min_value=qmin,
            max_value=qmax,
            value=(qmin, qmax),
            key="filter_qty_range",
        )

    cost_range = None
    if len(filtered) and filtered["Per Service"].notna().any():
        cmin = float(filtered["Per Service"].min())
        cmax = float(filtered["Per Service"].max())
        cost_range = st.slider(
            "Per Service range",
            min_value=cmin,
            max_value=cmax,
            value=(cmin, cmax),
            key="filter_cost_range",
        )

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
st.caption(f"Showing {len(filtered):,} / {len(result):,} rows after filters.")
st.dataframe(filtered, use_container_width=True, height=520)

# --- KPIs (use filtered) ---
st.subheader("KPIs (filtered)")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows (filtered)", f"{len(filtered):,}")
k2.metric("Services (filtered)", f"{filtered['Services'].nunique():,}")
k3.metric("Stylists (filtered)", f"{filtered['Stylist'].nunique():,}")

after_profit = filtered["Weighted Difference"].sum() if "Weighted Difference" in filtered.columns else filtered["Difference"].sum()
before_profit = filtered_base["Weighted Difference"].sum() if "Weighted Difference" in filtered_base.columns else filtered_base["Difference"].sum()
delta_profit = after_profit - before_profit
k4.metric("Profit impact (Before → After)", f"£{before_profit:,.2f} → £{after_profit:,.2f}", delta=f"£{delta_profit:,.2f}")

# Qty * Per Service KPI
if "Qty" in filtered.columns:
    c1, c2, c3 = st.columns(3)
    after_cost = (filtered["Qty"] * filtered["Per Service"]).sum()
    before_cost = (filtered_base["Qty"] * filtered_base["Per Service"]).sum()
    delta_cost = after_cost - before_cost
    c1.metric("Qty × Per Service (Before)", f"£{before_cost:,.2f}")
    c2.metric("Qty × Per Service (After)", f"£{after_cost:,.2f}")
    c3.metric("Qty × Per Service (Delta)", f"£{delta_cost:,.2f}")
else:
    st.info("Upload a volumes file (Qty) to see the Qty × Per Service totals.")

# --- Validation ---
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

# --- Download ---
st.subheader("Download")

out = io.BytesIO()
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    result.to_excel(writer, index=False, sheet_name="Scenario Output")
    filtered.to_excel(writer, index=False, sheet_name="Filtered View")
    st.session_state["stylist_controls"].to_excel(writer, index=False, sheet_name="Stylist Controls")
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
