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
        st.error("Password is not configured. Add this to Streamlit Secrets:\n\n[auth]\npassword = \"your-strong-password\"")
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
    for k in ["stylist_controls", "service_overrides"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

_require_password()

st.title("📊 Touche Hairdressing — Pricing & Cost What‑If Dashboard")
st.write(
    "Upload **Stylist Prices** and **Service Cost**. Optionally upload a **Service Sales by Team Member** report "
    "(or any volumes file with Stylist + Services/Description + Qty) to see weighted impacts. "
    "Use the controls and overrides to test scenarios in real time."
)

with st.sidebar:
    st.header("Uploads (required)")
    prices_file = st.file_uploader("1) Stylist Prices (xls/xlsx)", type=["xls","xlsx"])
    cost_file = st.file_uploader("2) Service Cost (xls/xlsx)", type=["xlsx","xls"])

    st.divider()
    st.header("Optional staff filter")
    staff_file = st.file_uploader("Staff list (xlsx) — optional", type=["xlsx","xls"])
    salon_choice = st.selectbox("Salon filter", ["Caterham","Purley"], index=0)
    st.caption("If provided, the app filters to Salon=selected and Type=Stylist.")

    st.divider()
    st.header("Optional volumes")
    qty_file = st.file_uploader("3) Volumes (xls/xlsx) — optional", type=["xlsx","xls"])
    st.caption("Accepted: a simple table (Stylist, Services/Description, Qty) OR a 'Service Sales by Team Member' .xls report.")

    st.divider()
    st.header("Global scenario")
    price_mode = st.selectbox("Price adjustment mode", ["Percent", "Add £"], index=0, key="global_price_mode")
    price_adj = st.number_input("Price adjustment", value=0.0, step=0.5, key="global_price_adj")

    cost_mode = st.selectbox("Per Service adjustment mode", ["Percent", "Add £"], index=0, key="global_cost_mode")
    cost_adj = st.number_input("Per Service adjustment", value=0.0, step=0.5, key="global_cost_adj")

    st.divider()
    if st.button("Reset scenario"):
        _reset_scenario()

if prices_file is None or cost_file is None:
    st.info("Upload **Stylist Prices** and **Service Cost** to start.")
    st.stop()

# --- Load inputs ---
price_matrix, meta = load_stylist_price_matrix(prices_file)
service_cost = load_service_cost(cost_file)

allowed_stylists = None
if staff_file is not None:
    staff_df = load_staff_list(staff_file)
    staff_df = staff_df[(staff_df['Salon'].astype(str).str.strip().str.lower() == salon_choice.lower()) & (staff_df['Type'].astype(str).str.strip().str.lower() == 'stylist')]
    allowed_stylists = set(staff_df['Stylist'].astype(str).str.strip())

qty_df = None
if qty_file is not None:
    qty_df = load_optional_qty(qty_file, allowed_stylists=allowed_stylists)

# --- Build base long table ---
base_long, validations = build_long_table(price_matrix, service_cost, qty_df)
if allowed_stylists:
    base_long = base_long[base_long['Stylist'].isin(allowed_stylists)].copy()

# --- Scenario controls (stylist table) ---
st.subheader("Scenario controls")

stylists = sorted(base_long["Stylist"].dropna().astype(str).unique())
default_stylist_controls = pd.DataFrame({
    "Stylist": stylists,
    "Price %": 0.0,
    "Price £": 0.0,
    "Cost %": 0.0,
    "Cost £": 0.0,
})

if "stylist_controls" not in st.session_state:
    st.session_state["stylist_controls"] = default_stylist_controls


with st.expander("Scenario controls — by stylist", expanded=True):
    st.session_state["stylist_controls"] = st.data_editor(
        st.session_state["stylist_controls"],
        use_container_width=True,
        hide_index=True,
        key="stylist_controls_editor",
    )

# --- Service overrides table (optional) ---
services = sorted(base_long["Services"].dropna().astype(str).unique())
default_service_overrides = pd.DataFrame({
    "Services": services,
    "Override Price": np.nan,
    "Override Per Service": np.nan,
})

if "service_overrides" not in st.session_state:
    st.session_state["service_overrides"] = default_service_overrides

with st.expander("Service-level overrides (optional) — set absolute values"):
    st.caption("If you set an override, it becomes the final value (global/stylist adjustments are not applied on top).")
    st.session_state["service_overrides"] = st.data_editor(
        st.session_state["service_overrides"],
        use_container_width=True,
        hide_index=True,
        key="service_overrides_editor",
    )

scenario = {
    "global_price_mode": price_mode,
    "global_price_adj": float(price_adj),
    "global_cost_mode": cost_mode,
    "global_cost_adj": float(cost_adj),
}

result = apply_scenario(
    base_long=base_long,
    scenario=scenario,
    stylist_controls=st.session_state["stylist_controls"],
    service_overrides=st.session_state["service_overrides"],
)

# Baseline (Before) — no adjustments, no overrides
baseline_scenario = {
    "global_price_mode": "Percent",
    "global_price_adj": 0.0,
    "global_cost_mode": "Percent",
    "global_cost_adj": 0.0,
}
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


# --- KPIs ---
st.subheader("Outputs")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Rows", f"{len(result):,}")
col2.metric("Services", f"{result['Services'].nunique():,}")
col3.metric("Stylists", f"{result['Stylist'].nunique():,}")

after_profit = result["Weighted Difference"].sum() if "Weighted Difference" in result.columns else result["Difference"].sum()
before_profit = baseline_result["Weighted Difference"].sum() if "Weighted Difference" in baseline_result.columns else baseline_result["Difference"].sum()
delta_profit = after_profit - before_profit
col4.metric("Profit impact (Before → After)", f"£{before_profit:,.2f} → £{after_profit:,.2f}", delta=f"£{delta_profit:,.2f}")

# --- Validation panels ---
with st.expander("Validation checks"):
    if validations["missing_cost_services"]:
        st.warning(f"{len(validations['missing_cost_services']):,} service(s) in prices are missing Per Service cost.")
        st.dataframe(pd.DataFrame({"Services": validations["missing_cost_services"]}), use_container_width=True)
    else:
        st.success("All priced services have a Per Service cost.")

    if validations["missing_price_services"]:
        st.warning(f"{len(validations['missing_price_services']):,} service(s) exist in costs but not in prices.")
        st.dataframe(pd.DataFrame({"Services": validations["missing_price_services"]}), use_container_width=True)
    else:
        st.success("All costed services exist in prices.")

    if qty_df is not None:
        if validations["qty_unmatched_services"]:
            st.warning(f"{len(validations['qty_unmatched_services']):,} service(s) in volumes could not be matched.")
            st.dataframe(pd.DataFrame({"Services": validations["qty_unmatched_services"]}), use_container_width=True)
        else:
            st.success("All volume services matched.")
    else:
        st.info("No volumes file uploaded; weighted checks disabled.")

# --- Result table ---

st.subheader("Scenario table")

# --- Filters (view only) ---
filtered = result.copy()

with st.expander("Filters", expanded=False):
    svc_all = sorted(filtered["Services"].dropna().astype(str).unique())
    sty_all = sorted(filtered["Stylist"].dropna().astype(str).unique())

    sel_services = st.multiselect("Services", svc_all, default=svc_all)
    sel_stylists = st.multiselect("Stylist", sty_all, default=sty_all)

    filtered = filtered[filtered["Services"].astype(str).isin(sel_services)]
    filtered = filtered[filtered["Stylist"].astype(str).isin(sel_stylists)]

    if "Qty" in filtered.columns:
        hide_zero_qty = st.checkbox("Hide rows with Qty = 0", value=True)
        if hide_zero_qty:
            filtered = filtered[filtered["Qty"] != 0]

    hide_missing_cost = st.checkbox("Hide rows with missing Per Service", value=True)
    if hide_missing_cost:
        filtered = filtered[filtered["Per Service"].notna()]

    if "Qty" in filtered.columns and len(filtered):
        qmin, qmax = int(filtered["Qty"].min()), int(filtered["Qty"].max())
        q_range = st.slider("Qty range", min_value=qmin, max_value=qmax, value=(qmin, qmax))
        filtered = filtered[(filtered["Qty"] >= q_range[0]) & (filtered["Qty"] <= q_range[1])]

    if len(filtered) and filtered["Per Service"].notna().any():
        cmin = float(filtered["Per Service"].min())
        cmax = float(filtered["Per Service"].max())
        c_range = st.slider("Per Service range", min_value=cmin, max_value=cmax, value=(cmin, cmax))
        filtered = filtered[(filtered["Per Service"] >= c_range[0]) & (filtered["Per Service"] <= c_range[1])]

st.caption(f"Showing {len(filtered):,} / {len(result):,} rows after filters.")
st.dataframe(filtered, use_container_width=True, height=520)


# --- Export ---
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
