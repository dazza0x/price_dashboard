import io
import hmac
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from transform import (
    load_stylist_price_matrix,
    load_service_cost,
    load_optional_qty,
    load_staff_list,
    build_long_table,
    apply_scenario,
)

# ─────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Touche — Pricing Dashboard",
    page_icon="✂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Global CSS
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
      /* Card-style metric boxes */
      div[data-testid="stMetric"] {
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 12px 16px;
      }
      div[data-testid="stMetric"] label  { font-size: 0.75rem !important; color: #6b7280; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
      div[data-testid="stMetricValue"]   { font-size: 1.05rem !important; font-weight: 700; color: #111827; }
      div[data-testid="stMetricDelta"]   { font-size: 0.78rem !important; }

      /* Tighter section headings */
      h2 { margin-top: 1.6rem !important; margin-bottom: 0.4rem !important; }
      h3 { margin-top: 1.2rem !important; margin-bottom: 0.3rem !important; }

      /* Sidebar upload labels */
      .sidebar-section { font-size: 0.78rem; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; margin-top: 1rem; margin-bottom: 0.2rem; }

      /* Badge chip */
      .badge { display:inline-block; background:#fef3c7; color:#92400e; border-radius:999px; padding:2px 10px; font-size:0.72rem; font-weight:600; }
      .badge-green { background:#d1fae5; color:#065f46; }
      .badge-red   { background:#fee2e2; color:#991b1b; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────
#  Password gate
# ─────────────────────────────────────────────
def _require_password():
    if "auth" not in st.secrets or "password" not in st.secrets["auth"]:
        st.error(
            "Password not configured. Add to Streamlit Secrets:\n\n"
            '[auth]\npassword = "your-strong-password"'
        )
        st.stop()
    if st.session_state.get("authenticated"):
        return
    with st.sidebar:
        st.markdown("### 🔒 Access")
        pw = st.text_input("Password", type="password", placeholder="Enter password…")
        correct = st.secrets["auth"]["password"]
        if pw and hmac.compare_digest(pw, correct):
            st.session_state["authenticated"] = True
            st.rerun()
        if pw:
            st.error("Incorrect password")
    st.stop()


_require_password()


# ─────────────────────────────────────────────
#  Reset helper
# ─────────────────────────────────────────────
def _reset_scenario():
    st.session_state["global_price_mode"] = "Percent"
    st.session_state["global_price_adj"] = 0.0
    st.session_state["global_cost_mode"] = "Percent"
    st.session_state["global_cost_adj"] = 0.0
    for k in [
        "filter_services", "filter_stylists", "filter_qty_range",
        "filter_cost_range", "filter_hide_zero_qty", "filter_hide_missing_cost",
        "service_overrides", "service_overrides_editor",
    ]:
        st.session_state.pop(k, None)
    st.rerun()


# ─────────────────────────────────────────────
#  Sidebar — uploads + settings
# ─────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/emoji/48/scissors-emoji.png", width=36)
    st.markdown("## Touche Dashboard")
    st.markdown("---")

    st.markdown('<p class="sidebar-section">Required files</p>', unsafe_allow_html=True)
    prices_file = st.file_uploader("Stylist Prices (.xls/.xlsx)", type=["xls", "xlsx"])
    cost_file   = st.file_uploader("Service Costs (.xls/.xlsx)",  type=["xls", "xlsx"])

    st.markdown('<p class="sidebar-section">Optional files</p>', unsafe_allow_html=True)
    qty_file   = st.file_uploader("Volumes — Stylist / Service / Qty", type=["xls", "xlsx"])
    staff_file = st.file_uploader("Staff list — Stylist / Salon / Type", type=["xls", "xlsx"])

    if staff_file:
        salon_choice = st.selectbox("Filter salon", ["Caterham", "Purley"], index=0)
    else:
        salon_choice = "Caterham"

    st.markdown("---")
    if st.button("↺  Reset scenario", use_container_width=True, type="secondary"):
        _reset_scenario()

    st.caption("Upload **Stylist Prices** and **Service Costs** to begin.")


# ─────────────────────────────────────────────
#  Gate — require both core files
# ─────────────────────────────────────────────
if prices_file is None or cost_file is None:
    st.markdown("## ✂️ Touche Hairdressing — Pricing Dashboard")
    st.info(
        "👈  Upload **Stylist Prices** and **Service Costs** in the sidebar to get started.",
        icon="📂",
    )
    st.stop()


# ─────────────────────────────────────────────
#  Load data
# ─────────────────────────────────────────────
price_matrix, _ = load_stylist_price_matrix(prices_file)
service_cost     = load_service_cost(cost_file)

allowed_stylists = None
if staff_file is not None:
    staff_df = load_staff_list(staff_file)
    staff_df = staff_df[
        (staff_df["Salon"].str.strip().str.lower() == salon_choice.lower())
        & (staff_df["Type"].str.strip().str.lower() == "stylist")
    ].copy()
    allowed_stylists = set(staff_df["Stylist"].str.strip())

qty_df = None
if qty_file is not None:
    qty_df = load_optional_qty(qty_file, allowed_stylists=allowed_stylists)

base_long, validations = build_long_table(price_matrix, service_cost, qty_df)
if allowed_stylists:
    base_long = base_long[base_long["Stylist"].isin(allowed_stylists)].copy()

stylists = sorted(base_long["Stylist"].dropna().astype(str).unique())
services = sorted(base_long["Services"].dropna().astype(str).unique())


# ─────────────────────────────────────────────
#  Page header
# ─────────────────────────────────────────────
st.markdown("## ✂️ Touche Hairdressing — Pricing & Cost Dashboard")
st.markdown(
    f"Loaded **{len(services)} services** across **{len(stylists)} stylists**."
    + (f"  ·  Volumes: ✅" if qty_df is not None else "  ·  Volumes: not uploaded")
)
st.markdown("---")


# ─────────────────────────────────────────────
#  Section 1 — Global scenario controls
# ─────────────────────────────────────────────
st.markdown("### 🎛️ Scenario Controls")

for key, default in [
    ("global_price_mode", "Percent"),
    ("global_price_adj",  0.0),
    ("global_cost_mode",  "Percent"),
    ("global_cost_adj",   0.0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

col_pm, col_pa, col_cm, col_ca = st.columns([1.3, 1, 1.3, 1])
with col_pm:
    price_mode = st.selectbox("Price adjustment mode", ["Percent", "Add £"], key="global_price_mode")
with col_pa:
    price_adj = st.number_input(
        "%" if price_mode == "Percent" else "£ amount",
        step=0.5, key="global_price_adj",
        help="Applied to every service price globally before any overrides.",
    )
with col_cm:
    cost_mode = st.selectbox("Cost adjustment mode", ["Percent", "Add £"], key="global_cost_mode")
with col_ca:
    cost_adj = st.number_input(
        "%" if cost_mode == "Percent" else "£ amount",
        step=0.5, key="global_cost_adj",
        help="Applied to every Per Service cost globally.",
    )

scenario = {
    "global_price_mode": price_mode,
    "global_price_adj":  float(price_adj),
    "global_cost_mode":  cost_mode,
    "global_cost_adj":   float(cost_adj),
}

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 2 — Chair rent
# ─────────────────────────────────────────────
st.markdown("### 🪑 Chair Rent")

if "rent_plus" not in st.session_state:
    st.session_state["rent_plus"] = 0.0

rc1, rc2 = st.columns([1, 3])
with rc1:
    rent_plus = st.number_input("Daily rate (£ per day)", step=1.0, key="rent_plus")

default_rent_days = pd.DataFrame({"Stylist": stylists, "Days": 0.0})
if "rent_days" not in st.session_state:
    st.session_state["rent_days"] = default_rent_days

with rc2:
    st.caption("Enter the number of days worked per stylist to compute chair rent.")
    st.session_state["rent_days"] = st.data_editor(
        st.session_state["rent_days"],
        use_container_width=True,
        hide_index=True,
        key="rent_days_editor",
        height=min(200, 38 + len(stylists) * 35),
    )

rent_days_df = st.session_state["rent_days"].copy()
rent_days_df["Stylist"]    = rent_days_df["Stylist"].astype(str).str.strip()
rent_days_df["Days"]       = pd.to_numeric(rent_days_df["Days"], errors="coerce").fillna(0.0)
rent_days_df["Total Rent"] = (rent_days_df["Days"] * float(rent_plus)).round(2)

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 3 — Service overrides
# ─────────────────────────────────────────────
st.markdown("### 🔧 Service-Level Overrides")

default_service_overrides = pd.DataFrame({
    "Services": services,
    "Override Price": np.nan,
    "Override Per Service": np.nan,
})
if "service_overrides" not in st.session_state:
    st.session_state["service_overrides"] = default_service_overrides

overrides_active = int(
    st.session_state["service_overrides"]["Override Price"].notna().sum()
    + st.session_state["service_overrides"]["Override Per Service"].notna().sum()
)

with st.expander(
    f"Set absolute price / cost overrides per service  {'— ' + str(overrides_active) + ' active' if overrides_active else '(none active)'}",
    expanded=False,
):
    st.caption("Override values replace the global adjustment entirely for that service.")
    st.session_state["service_overrides"] = st.data_editor(
        st.session_state["service_overrides"],
        use_container_width=True,
        hide_index=True,
        key="service_overrides_editor",
    )

if overrides_active:
    st.warning(f"⚠️  {overrides_active} override cell(s) active — global adjustments are bypassed for those rows.")

st.markdown("---")


# ─────────────────────────────────────────────
#  Apply scenario + baseline
# ─────────────────────────────────────────────
stylist_controls = pd.DataFrame(
    {"Stylist": stylists, "Price %": 0.0, "Price £": 0.0, "Cost %": 0.0, "Cost £": 0.0}
)

result = apply_scenario(
    base_long=base_long,
    scenario=scenario,
    stylist_controls=stylist_controls,
    service_overrides=st.session_state["service_overrides"],
)

baseline_scenario = {"global_price_mode": "Percent", "global_price_adj": 0.0,
                     "global_cost_mode":  "Percent", "global_cost_adj":  0.0}
baseline_result = apply_scenario(
    base_long=base_long,
    scenario=baseline_scenario,
    stylist_controls=stylist_controls,
    service_overrides=default_service_overrides,
)


# ─────────────────────────────────────────────
#  Section 4 — Filters
# ─────────────────────────────────────────────
st.markdown("### 🔍 Filters")

with st.expander("Expand to filter services, stylists, and ranges", expanded=False):
    fa, fb = st.columns(2)
    with fa:
        sel_services = st.multiselect("Services", services, default=services, key="filter_services")
    with fb:
        sel_stylists = st.multiselect("Stylists", stylists, default=stylists, key="filter_stylists")

    fc, fd = st.columns(2)
    with fc:
        hide_zero_qty = None
        if "Qty" in result.columns:
            hide_zero_qty = st.checkbox("Hide rows where Qty = 0", value=True, key="filter_hide_zero_qty")
    with fd:
        hide_missing_cost = st.checkbox("Hide rows with missing Per Service", value=True, key="filter_hide_missing_cost")

    both = pd.concat([result, baseline_result], ignore_index=True)

    fe, ff = st.columns(2)
    with fe:
        qty_range = None
        if "Qty" in both.columns:
            qmin = int(pd.to_numeric(both["Qty"], errors="coerce").fillna(0).min())
            qmax = int(pd.to_numeric(both["Qty"], errors="coerce").fillna(0).max())
            if qmin < qmax:
                qty_range = st.slider("Qty range", qmin, qmax, (qmin, qmax), key="filter_qty_range")
    with ff:
        cost_range = None
        if pd.to_numeric(both["Per Service"], errors="coerce").notna().any():
            cmin = float(pd.to_numeric(both["Per Service"], errors="coerce").min())
            cmax = float(pd.to_numeric(both["Per Service"], errors="coerce").max())
            if cmin < cmax:
                cost_range = st.slider("Per Service range (£)", cmin, cmax, (cmin, cmax), key="filter_cost_range")


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    out = df[df["Services"].astype(str).isin(sel_services)]
    out = out[out["Stylist"].astype(str).isin(sel_stylists)]
    if hide_zero_qty and "Qty" in out.columns:
        out = out[out["Qty"] != 0]
    if hide_missing_cost:
        out = out[out["Per Service"].notna()]
    if qty_range is not None and "Qty" in out.columns:
        out = out[(out["Qty"] >= qty_range[0]) & (out["Qty"] <= qty_range[1])]
    if cost_range is not None:
        out = out[(out["Per Service"] >= cost_range[0]) & (out["Per Service"] <= cost_range[1])]
    return out.copy()


filtered      = _apply_filters(result)
filtered_base = _apply_filters(baseline_result)

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 5 — KPI summary
# ─────────────────────────────────────────────
st.markdown("### 📊 Key Metrics")

k1, k2, k3 = st.columns(3)
k1.metric("Services (filtered)",  f"{filtered['Services'].nunique():,}")
k2.metric("Stylists (filtered)",  f"{filtered['Stylist'].nunique():,}")
k3.metric("Rows (filtered)",      f"{len(filtered):,}")

st.markdown("")

has_qty = "Qty" in filtered.columns

if has_qty:
    for df_ in (filtered, filtered_base):
        df_["Qty"]         = pd.to_numeric(df_["Qty"],         errors="coerce").fillna(0)
        df_["Price"]       = pd.to_numeric(df_["Price"],       errors="coerce")
        df_["Per Service"] = pd.to_numeric(df_["Per Service"], errors="coerce")

    rev_after  = (filtered["Qty"]      * filtered["Price"]).sum()
    rev_before = (filtered_base["Qty"] * filtered_base["Price"]).sum()
    rev_delta  = rev_after - rev_before

    svc_after  = (filtered["Qty"]      * filtered["Per Service"]).sum()
    svc_before = (filtered_base["Qty"] * filtered_base["Per Service"]).sum()
    svc_delta  = svc_after - svc_before

    rent_map   = rent_days_df.set_index("Stylist")["Total Rent"].to_dict()
    rent_after = filtered["Stylist"].map(rent_map).fillna(0).drop_duplicates().sum()
    rent_before= filtered_base["Stylist"].map(rent_map).fillna(0).drop_duplicates().sum()

    income_after  = svc_after  + rent_after
    income_before = svc_before + rent_before
    income_delta  = income_after - income_before

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Client Revenue",
        f"£{rev_after:,.0f}",
        delta=f"£{rev_delta:+,.0f} vs baseline",
        delta_color="normal",
        help="Qty × Price — what clients pay stylists",
    )
    m2.metric(
        "Service Charges to Salon",
        f"£{svc_after:,.0f}",
        delta=f"£{svc_delta:+,.0f} vs baseline",
        delta_color="normal",
        help="Qty × Per Service — what stylists pay the salon",
    )
    m3.metric(
        "Chair Rent",
        f"£{rent_after:,.0f}",
        help="Days × Daily Rate per stylist",
    )
    m4.metric(
        "Total Salon Income",
        f"£{income_after:,.0f}",
        delta=f"£{income_delta:+,.0f} vs baseline",
        delta_color="normal",
        help="Service Charges + Chair Rent",
    )
else:
    after_profit  = filtered["Difference"].sum()
    before_profit = filtered_base["Difference"].sum()
    delta_profit  = after_profit - before_profit
    m1, m2 = st.columns(2)
    m1.metric("Total Profit (after)", f"£{after_profit:,.2f}",
              delta=f"£{delta_profit:+,.2f} vs baseline", delta_color="normal")
    m2.metric("Total Profit (baseline)", f"£{before_profit:,.2f}")
    st.info("Upload a Volumes file to unlock Revenue, Salon Income, and Chair Rent metrics.")

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 6 — Charts
# ─────────────────────────────────────────────
st.markdown("### 📈 Charts")

tab_profit, tab_revenue = st.tabs(["Profit % by Service", "Revenue Before vs After by Stylist"])

# ── Chart 1: Profit % by service ──
with tab_profit:
    if len(filtered) == 0:
        st.info("No data to display — adjust your filters.")
    else:
        svc_profit = (
            filtered.groupby("Services", as_index=False)
            .agg(Avg_Price=("Price", "mean"), Avg_Cost=("Per Service", "mean"))
        )
        svc_profit = svc_profit[svc_profit["Avg_Price"] > 0].copy()
        svc_profit["Profit %"] = ((svc_profit["Avg_Price"] - svc_profit["Avg_Cost"]) / svc_profit["Avg_Price"] * 100).round(1)
        svc_profit = svc_profit.sort_values("Profit %", ascending=True).tail(40)  # top 40 for readability

        fig1 = px.bar(
            svc_profit,
            x="Profit %",
            y="Services",
            orientation="h",
            color="Profit %",
            color_continuous_scale=["#ef4444", "#f59e0b", "#10b981"],
            range_color=[0, 100],
            labels={"Profit %": "Profit Margin %"},
            title="Average Profit Margin % by Service (scenario)",
            height=max(400, len(svc_profit) * 22),
        )
        fig1.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            font_family="Inter, sans-serif",
            coloraxis_showscale=False,
            margin=dict(l=10, r=20, t=40, b=20),
            xaxis=dict(gridcolor="#f3f4f6", range=[0, 105]),
            yaxis=dict(tickfont=dict(size=11)),
        )
        fig1.update_traces(
            texttemplate="%{x:.1f}%",
            textposition="outside",
        )
        st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Revenue before vs after by stylist ──
with tab_revenue:
    if not has_qty:
        st.info("Upload a Volumes file to see Revenue Before vs After by Stylist.")
    elif len(filtered) == 0:
        st.info("No data to display — adjust your filters.")
    else:
        rev_after_sty = (
            filtered.groupby("Stylist", as_index=False)
            .apply(lambda x: pd.Series({"Revenue After": (x["Qty"] * x["Price"]).sum()}))
            .reset_index(drop=True)
        )
        rev_before_sty = (
            filtered_base.groupby("Stylist", as_index=False)
            .apply(lambda x: pd.Series({"Revenue Before": (x["Qty"] * x["Price"]).sum()}))
            .reset_index(drop=True)
        )
        rev_comp = rev_after_sty.merge(rev_before_sty, on="Stylist", how="outer").fillna(0)
        rev_comp = rev_comp.sort_values("Revenue After", ascending=True)

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            name="Baseline",
            y=rev_comp["Stylist"],
            x=rev_comp["Revenue Before"],
            orientation="h",
            marker_color="#cbd5e1",
        ))
        fig2.add_trace(go.Bar(
            name="Scenario",
            y=rev_comp["Stylist"],
            x=rev_comp["Revenue After"],
            orientation="h",
            marker_color="#6366f1",
        ))
        fig2.update_layout(
            barmode="group",
            title="Client Revenue Before vs After by Stylist",
            plot_bgcolor="white",
            paper_bgcolor="white",
            font_family="Inter, sans-serif",
            height=max(400, len(rev_comp) * 44),
            margin=dict(l=10, r=20, t=40, b=20),
            xaxis=dict(gridcolor="#f3f4f6", tickprefix="£", tickformat=",.0f"),
            yaxis=dict(tickfont=dict(size=12)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 7 — Stylist summary table
# ─────────────────────────────────────────────
st.markdown("### 👤 Stylist Summary")

if has_qty:
    summ = (
        filtered.groupby("Stylist", dropna=False)
        .apply(lambda x: pd.Series({
            "Revenue (After)":      (x["Qty"] * x["Price"]).sum(),
            "Service Charges (After)": (x["Qty"] * x["Per Service"]).sum(),
        }))
        .reset_index()
    )
    base_summ = (
        filtered_base.groupby("Stylist", dropna=False)
        .apply(lambda x: pd.Series({
            "Revenue (Before)":     (x["Qty"] * x["Price"]).sum(),
            "Service Charges (Before)": (x["Qty"] * x["Per Service"]).sum(),
        }))
        .reset_index()
    )
    summ = summ.merge(base_summ, on="Stylist", how="left").fillna(0.0)

    rent_map = rent_days_df.set_index("Stylist")["Total Rent"].to_dict()
    summ["Chair Rent"]       = summ["Stylist"].map(rent_map).fillna(0.0)
    summ["Salon Income"]     = summ["Service Charges (After)"] + summ["Chair Rent"]
    summ["Revenue Δ"]        = summ["Revenue (After)"]         - summ["Revenue (Before)"]
    summ["Service Charges Δ"]= summ["Service Charges (After)"] - summ["Service Charges (Before)"]

    summ = summ[[
        "Stylist",
        "Revenue (Before)", "Revenue (After)",  "Revenue Δ",
        "Service Charges (Before)", "Service Charges (After)", "Service Charges Δ",
        "Chair Rent", "Salon Income",
    ]]
    currency_cols = summ.columns.drop("Stylist")
    summ[currency_cols] = summ[currency_cols].round(2)
    summ = summ.sort_values("Stylist").reset_index(drop=True)

    st.dataframe(
        summ.style.format({c: "£{:,.2f}" for c in currency_cols})
                  .applymap(lambda v: "color: #10b981; font-weight:600" if isinstance(v, (int,float)) and v > 0
                            else ("color: #ef4444; font-weight:600" if isinstance(v,(int,float)) and v < 0 else ""),
                            subset=["Revenue Δ","Service Charges Δ"]),
        use_container_width=True,
        height=min(500, 60 + len(summ) * 35),
    )
else:
    st.info("Upload a Volumes file to see the Stylist Summary table.")

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 8 — Scenario detail table
# ─────────────────────────────────────────────
st.markdown("### 📋 Scenario Detail Table")
st.caption(f"Showing {len(filtered):,} rows after filters.")

st.dataframe(
    filtered.style.format({
        c: "£{:,.2f}" for c in ["Price","Per Service","Difference","Price_base","PerService_base"]
        if c in filtered.columns
    } | {
        "Service %": "{:.1f}%",
        "Profit %":  "{:.1f}%",
    }),
    use_container_width=True,
    height=420,
)

if validations.get("missing_cost_services"):
    with st.expander(f"⚠️  {len(validations['missing_cost_services'])} services missing a cost — expand to review"):
        st.write(validations["missing_cost_services"])

st.markdown("---")


# ─────────────────────────────────────────────
#  Section 9 — Downloads
# ─────────────────────────────────────────────
st.markdown("### ⬇️ Downloads")

dl1, dl2, dl3 = st.columns(3)

# ── Full scenario workbook ──
out1 = io.BytesIO()
with pd.ExcelWriter(out1, engine="openpyxl") as writer:
    result.to_excel(writer, index=False, sheet_name="Scenario Output")
    filtered.to_excel(writer, index=False, sheet_name="Filtered View")
    if has_qty and "summ" in dir():
        summ.to_excel(writer, index=False, sheet_name="Stylist Summary")
    st.session_state["service_overrides"].to_excel(writer, index=False, sheet_name="Service Overrides")
    price_matrix.to_excel(writer, index=False, sheet_name="Input_StylistPrices")
    service_cost.to_excel(writer, index=False, sheet_name="Input_ServiceCost")
    if qty_df is not None:
        qty_df.to_excel(writer, index=False, sheet_name="Input_Volumes")
    rent_days_df.to_excel(writer, index=False, sheet_name="Input_ChairRent")
out1.seek(0)

with dl1:
    st.download_button(
        "📥 Full Scenario Workbook",
        data=out1,
        file_name="Touche Pricing Scenario.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ── Service price list (before vs after) ──
svc_b = baseline_result.groupby("Services", as_index=False).agg(
    Price_Before=("Price","mean"), PerService_Before=("Per Service","mean"))
svc_a = result.groupby("Services", as_index=False).agg(
    Price_After=("Price","mean"),  PerService_After=("Per Service","mean"))
svc_list = svc_b.merge(svc_a, on="Services", how="outer")
for c in ["Price_Before","PerService_Before","Price_After","PerService_After"]:
    svc_list[c] = pd.to_numeric(svc_list[c], errors="coerce")
svc_list["Price_Δ"]      = svc_list["Price_After"]      - svc_list["Price_Before"]
svc_list["PerService_Δ"] = svc_list["PerService_After"] - svc_list["PerService_Before"]
svc_list = svc_list.sort_values("Services").reset_index(drop=True).round(2)

out2 = io.BytesIO()
with pd.ExcelWriter(out2, engine="openpyxl") as writer:
    svc_list.to_excel(writer, index=False, sheet_name="Service Price List")
out2.seek(0)

with dl2:
    st.download_button(
        "📥 Service Price List (Before vs After)",
        data=out2,
        file_name="Service Price List - Before vs After.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ── Stylist price list ──
stylist_prices = result.pivot_table(
    index="Services", columns="Stylist", values="Price", aggfunc="mean"
).sort_index().reset_index()
per_svc_after = result.groupby("Services", as_index=False).agg(
    PerService_After=("Per Service","mean")).sort_values("Services").reset_index(drop=True)

out3 = io.BytesIO()
with pd.ExcelWriter(out3, engine="openpyxl") as writer:
    stylist_prices.round(2).to_excel(writer, index=False, sheet_name="Stylist Prices (After)")
    per_svc_after.round(2).to_excel(writer, index=False, sheet_name="Per Service (After)")
out3.seek(0)

with dl3:
    st.download_button(
        "📥 Stylist Price List (After)",
        data=out3,
        file_name="Stylist Service Price List - After.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
