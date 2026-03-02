import re
import numpy as np
import pandas as pd

def normalise_key(s: str) -> str:
    if s is None:
        return ""
    s = str(s).replace("\u00a0", " ").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _pick(cols, candidates):
    lower = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    for c in cols:
        cl = str(c).strip().lower()
        for cand in candidates:
            if cand.lower() in cl:
                return c
    return None

def load_staff_list(file) -> pd.DataFrame:
    """
    Staff list with columns like: Stylist, Salon, Type.
    Returns a cleaned table with trimmed text columns.
    """
    df = pd.read_excel(file)
    stylist_col = _pick(df.columns, ["Stylist", "Team Member", "Name"])
    salon_col = _pick(df.columns, ["Salon", "Location"])
    type_col = _pick(df.columns, ["Type", "Role"])
    if stylist_col is None or salon_col is None or type_col is None:
        raise ValueError(f"Staff list must include Stylist + Salon + Type. Found: {list(df.columns)}")

    out = df[[stylist_col, salon_col, type_col]].copy()
    out.columns = ["Stylist", "Salon", "Type"]
    out["Stylist"] = out["Stylist"].astype(str).str.replace("\u00a0", " ", regex=False).str.strip()
    out["Salon"] = out["Salon"].astype(str).str.strip()
    out["Type"] = out["Type"].astype(str).str.strip()
    out = out[(out["Stylist"] != "") & (out["Stylist"].str.lower() != "nan")]
    return out.reset_index(drop=True)

def load_stylist_price_matrix(file) -> tuple[pd.DataFrame, dict]:
    """
    Accepts a matrix-style sheet with columns:
      Description | Default Price | <Stylist 1> | <Stylist 2> | ...
    Finds the header row containing 'Description', then:
      - drops blank/garbage rows (e.g., Online Booking / Bookable Online / nan)
      - drops rows where *all* price columns are empty
      - keeps dynamic stylist columns
    Returns the cleaned matrix and metadata.
    """
    raw = pd.read_excel(file, header=None)

    # Find header row containing 'Description'
    header_i = -1
    for i in range(len(raw)):
        row = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
        if "description" in row:
            header_i = i
            break
    if header_i < 0:
        raise ValueError("Could not find a header row containing 'Description' in the Stylist Prices file.")

    headers = raw.iloc[header_i].tolist()
    df = raw.iloc[header_i + 1:].copy()
    df.columns = headers

    # Drop columns with blank/NaN header names
    df = df.loc[:, [c for c in df.columns if isinstance(c, str) and str(c).strip() != ""]].copy()

    desc_col = _pick(df.columns, ["Description", "Service", "Services"])
    default_col = _pick(df.columns, ["Default Price", "Default", "Price"])

    if desc_col is None or default_col is None:
        raise ValueError(f"Could not map 'Description' and 'Default Price'. Found columns: {list(df.columns)}")

    # Keep from description onwards (dynamic stylists)
    desc_idx = list(df.columns).index(desc_col)
    df = df.iloc[:, desc_idx:].copy()
    df = df.rename(columns={desc_col: "Description", default_col: "Default Price"})

    # Clean description text
    df["Description"] = (
        df["Description"]
        .astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.strip()
    )

    # Drop obvious non-service rows
    bad_desc = {
        "", "nan", "none",
        "online booking", "bookable online",
        "grand total", "inspired hair supplies",
    }
    df = df[~df["Description"].str.lower().isin(bad_desc)].copy()

    # Coerce numeric for all price columns
    for c in df.columns:
        if c != "Description":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows where ALL price columns are NaN (removes section labels etc.)
    price_cols = [c for c in df.columns if c != "Description"]
    df = df[~df[price_cols].isna().all(axis=1)].copy()

    df = df.reset_index(drop=True)

    meta = {"stylist_columns": [c for c in df.columns if c not in ("Description", "Default Price")]}
    return df, meta

def load_service_cost(file) -> pd.DataFrame:
    df = pd.read_excel(file)
    desc_col = _pick(df.columns, ["Service Description", "Description", "Service", "Services"])
    per_col = _pick(df.columns, ["Per Service", "Cost", "Charge", "PerService"])
    if desc_col is None or per_col is None:
        raise ValueError(f"Could not map Service Description + Per Service in cost file. Found: {list(df.columns)}")
    out = df[[desc_col, per_col]].copy()
    out.columns = ["Service Description", "Per Service"]
    out["Service Description"] = out["Service Description"].astype(str).str.replace("\u00a0"," ", regex=False).str.strip()
    out["Per Service"] = pd.to_numeric(out["Per Service"], errors="coerce")
    out = out[out["Service Description"].notna()].copy()
    return out.reset_index(drop=True)

def load_optional_qty(file, allowed_stylists: set[str] | None = None) -> pd.DataFrame:
    """
    Optional volumes file.

    Accepts either:
      A) Simple table with columns: Stylist, Description/Services, Qty
      B) A 'Service Sales by Team Member' style report (.xls/.xlsx)

    Output columns: Stylist, Services, Qty (aggregated)

    If `allowed_stylists` is provided, parsing prefers the fill direction (ffill vs bfill)
    that produces the most rows with a stylist in that allowed set, and it filters out
    rows not in that set.
    """
    xls = pd.ExcelFile(file)
    sheet_candidates = xls.sheet_names

    # --- Try simple table first (first sheet) ---
    df0 = pd.read_excel(file, sheet_name=sheet_candidates[0])

    stylist_col = _pick(df0.columns, ["Stylist", "Team Member", "TeamMember"])
    desc_col = _pick(df0.columns, ["Services", "Description", "Service Description"])
    qty_col = _pick(df0.columns, ["Qty", "Quantity"])

    if stylist_col is not None and desc_col is not None and qty_col is not None:
        out = df0[[stylist_col, desc_col, qty_col]].copy()
        out.columns = ["Stylist", "Services", "Qty"]
        out["Stylist"] = out["Stylist"].astype(str).str.strip()
        out["Services"] = out["Services"].astype(str).str.replace("\u00a0"," ", regex=False).str.strip()
        out["Qty"] = pd.to_numeric(out["Qty"], errors="coerce").fillna(0).astype(int)
        out = out[(out["Services"].notna()) & (out["Services"].astype(str).str.strip() != "")]
        out = out[(out["Stylist"].notna()) & (out["Stylist"].astype(str).str.strip() != "")]
        if allowed_stylists:
            out = out[out["Stylist"].isin(allowed_stylists)].copy()
        out = out.groupby(["Stylist","Services"], as_index=False)["Qty"].sum()
        return out.reset_index(drop=True)

    # --- Parse Service Sales by Team Member report ---
    ss_sheet = None
    for s in sheet_candidates:
        sl = s.lower()
        if "service sales" in sl or "team mem" in sl:
            ss_sheet = s
            break
    if ss_sheet is None:
        raise ValueError(
            f"Volumes file must include Stylist + Description/Services + Qty, OR be a Service Sales report. "
            f"Found columns: {list(df0.columns)}"
        )

    raw = pd.read_excel(file, sheet_name=ss_sheet, header=None)

    # Find header row containing 'Description' and 'Qty'
    header_i = -1
    for i in range(len(raw)):
        row = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
        if "description" in row and ("qty" in row or "quantity" in row):
            header_i = i
            break
    if header_i < 0:
        raise ValueError(f"Could not locate header row in sheet '{ss_sheet}' containing Description + Qty.")

    headers = raw.iloc[header_i].tolist()
    df = raw.iloc[header_i+1:].copy()
    df.columns = headers

    desc = _pick(df.columns, ["Description"])
    qty = _pick(df.columns, ["Qty", "Quantity"])
    if desc is None or qty is None:
        raise ValueError(f"Could not map Description/Qty after header promotion. Columns: {list(df.columns)}")

    df = df[[desc, qty]].copy()
    df.columns = ["Description", "Qty"]

    # Clean description: turn 'nan'/blank into real NaN
    df["Description"] = (
        df["Description"]
        .astype(str)
        .str.replace("\u00a0"," ", regex=False)
        .str.strip()
        .replace({"nan": None, "None": None, "": None})
    )

    # Qty numeric (blank => NaN)
    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce")

    # Drop known non-service / totals rows
    drop_desc = {"grand total", "hair", "treatment", "inspired hair supplies"}
    df = df[~df["Description"].fillna("").str.lower().isin(drop_desc)].copy()

    # Identify stylist headers
    df["StylistHeader"] = np.where(df["Qty"].isna() & df["Description"].notna(), df["Description"], np.nan)

    def _build_out(fill_method: str) -> pd.DataFrame:
        tmp = df.copy()
        tmp["Stylist"] = tmp["StylistHeader"].ffill() if fill_method == "ffill" else tmp["StylistHeader"].bfill()
        tmp = tmp[tmp["Qty"].notna()].copy()
        tmp = tmp[tmp["Stylist"].notna()].copy()
        tmp.rename(columns={"Description": "Services"}, inplace=True)
        tmp["Qty"] = tmp["Qty"].fillna(0).astype(int)
        out = tmp[["Stylist","Services","Qty"]].copy()
        out["Stylist"] = out["Stylist"].astype(str).str.strip()
        out["Services"] = out["Services"].astype(str).str.strip()
        out = out[(out["Stylist"] != "") & (out["Stylist"].str.lower() != "nan")]
        out = out[(out["Services"] != "") & (out["Services"].str.lower() != "nan")]
        if allowed_stylists:
            out = out[out["Stylist"].isin(allowed_stylists)].copy()
        return out

    out_ffill = _build_out("ffill")
    out_bfill = _build_out("bfill")

    out = out_ffill if len(out_ffill) >= len(out_bfill) else out_bfill

    out = out.groupby(["Stylist","Services"], as_index=False)["Qty"].sum()
    return out.reset_index(drop=True)

def build_long_table(price_matrix: pd.DataFrame, service_cost: pd.DataFrame, qty_df: pd.DataFrame | None):
    # Melt matrix to long
    stylist_cols = [c for c in price_matrix.columns if c not in ("Description", "Default Price")]
    long = price_matrix.melt(
        id_vars=["Description", "Default Price"],
        value_vars=stylist_cols,
        var_name="Stylist",
        value_name="Stylist Price",
    )

    long["Services"] = long["Description"].astype(str).str.strip()
    long.drop(columns=["Description"], inplace=True)

    # Effective base Price:
    # use stylist price ONLY if it is > 0, otherwise fall back to Default Price
    sp = pd.to_numeric(long["Stylist Price"], errors="coerce")
    dp = pd.to_numeric(long["Default Price"], errors="coerce")

    long["Price_base"] = np.where(sp.notna() & (sp > 0), sp, dp)

    # Join costs
    cost = service_cost.copy()
    cost["key"] = cost["Service Description"].map(normalise_key)
    long["key"] = long["Services"].map(normalise_key)

    merged = long.merge(cost[["key", "Per Service"]], how="left", on="key")
    merged["PerService_base"] = pd.to_numeric(merged["Per Service"], errors="coerce")
    merged.drop(columns=["Per Service"], inplace=True)

    validations = {
        "missing_cost_services": sorted(set(merged.loc[merged["PerService_base"].isna(), "Services"].dropna().unique())),
        "missing_price_services": sorted(set(cost.loc[~cost["key"].isin(set(merged["key"])), "Service Description"].dropna().unique())),
        "qty_unmatched_services": [],
    }

    if qty_df is not None:
        q = qty_df.copy()
        q["key"] = q["Services"].map(normalise_key)
        merged = merged.merge(q[["Stylist","key","Qty"]], how="left", on=["Stylist","key"])
        merged["Qty"] = merged["Qty"].fillna(0).astype(int)
        validations["qty_unmatched_services"] = sorted(set(q.loc[~q["key"].isin(set(merged["key"])), "Services"].dropna().unique()))

    base = merged[["Services","Stylist","Price_base","PerService_base"] + (["Qty"] if "Qty" in merged.columns else [])].copy()
    return base, validations

def apply_scenario(base_long: pd.DataFrame, scenario: dict, stylist_controls: pd.DataFrame, service_overrides: pd.DataFrame) -> pd.DataFrame:
    df = base_long.copy()

    # Global adjustments
    if scenario["global_price_mode"] == "Percent":
        df["Price"] = df["Price_base"] * (1 + scenario["global_price_adj"]/100.0)
    else:
        df["Price"] = df["Price_base"] + scenario["global_price_adj"]

    if scenario["global_cost_mode"] == "Percent":
        df["Per Service"] = df["PerService_base"] * (1 + scenario["global_cost_adj"]/100.0)
    else:
        df["Per Service"] = df["PerService_base"] + scenario["global_cost_adj"]

    # Stylist adjustments
    sc = stylist_controls.copy()
    sc_cols = ["Stylist","Price %","Price £","Cost %","Cost £"]
    for c in sc_cols:
        if c not in sc.columns:
            raise ValueError("Stylist controls table was modified unexpectedly; please reset the app.")
    df = df.merge(sc[sc_cols], how="left", on="Stylist")
    df[["Price %","Price £","Cost %","Cost £"]] = df[["Price %","Price £","Cost %","Cost £"]].fillna(0.0)

    df["Price"] = df["Price"] * (1 + df["Price %"]/100.0) + df["Price £"]
    df["Per Service"] = df["Per Service"] * (1 + df["Cost %"]/100.0) + df["Cost £"]

    df.drop(columns=["Price %","Price £","Cost %","Cost £"], inplace=True)

    # Service overrides (absolute)
    ov = service_overrides.copy()
    if "Services" in ov.columns:
        ov["key"] = ov["Services"].map(normalise_key)
    else:
        raise ValueError("Service overrides table must contain 'Services'.")

    for col in ["Override Price", "Override Per Service"]:
        if col not in ov.columns:
            ov[col] = np.nan

    df["key"] = df["Services"].map(normalise_key)
    df = df.merge(ov[["key","Override Price","Override Per Service"]], how="left", on="key")

    df["Price"] = np.where(df["Override Price"].notna(), df["Override Price"], df["Price"])
    df["Per Service"] = np.where(df["Override Per Service"].notna(), df["Override Per Service"], df["Per Service"])

    df.drop(columns=["Override Price","Override Per Service"], inplace=True)

    # Derived metrics
    df["Difference"] = df["Price"] - df["Per Service"]
    df["Service %"] = np.where(df["Price"] != 0, (df["Per Service"]/df["Price"]) * 100.0, 0.0)
    df["Profit %"] = np.where(df["Price"] != 0, (df["Difference"]/df["Price"]) * 100.0, 0.0)

    if "Qty" in df.columns:
        df["Weighted Difference"] = df["Difference"] * df["Qty"]

    # Output columns
    cols = ["Services","Stylist","Price","Per Service","Difference","Service %","Profit %"]
    if "Qty" in df.columns:
        cols.insert(3, "Qty")
        cols.append("Weighted Difference")

    out = df[cols].copy()
    out = out.sort_values(["Services","Stylist"]).reset_index(drop=True)
    return out
