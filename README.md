# Touche Hairdressing — Pricing & Cost What‑If Dashboard

## What it is
An interactive Streamlit dashboard for exploring pricing and costing scenarios.

## Inputs
### 1) Stylist Prices (xls/xlsx)
Matrix format:
- `Description`
- `Default Price`
- One column per stylist (dynamic)

### 2) Service Cost (xls/xlsx)
A table with:
- `Service Description`
- `Per Service`

### 3) Optional volumes (xls/xlsx)
A table with:
- `Stylist`
- `Description` (or `Services`)
- `Qty`

If uploaded, the dashboard calculates **Weighted Difference** = Difference × Qty.

## Scenario controls
- Global adjustment (Percent or Add £) for Prices and Per Service costs
- Per-stylist adjustments via editable table
- Optional per-service absolute overrides

## Outputs
- Live scenario table with:
  - Services, Stylist, Price, Per Service, Difference, Service %, Profit %
  - (optional) Qty and Weighted Difference
- Downloadable Excel workbook with outputs + inputs + scenario tables

## Deploy
- Main file: `app.py`
- Streamlit Cloud recommended Python: 3.12


## Password protection
Add to Streamlit Secrets:

```toml
[auth]
password = "your-strong-password"
```

## Reset scenario
Use the sidebar button **Reset scenario** to clear overrides and return to defaults.


## Stylist Prices cleaning
The app drops non-service rows such as **Online Booking / Bookable Online** and any rows where all price columns are blank.


## Stylist price fallback
If a stylist-specific price is **blank or zero**, the **Default Price** is automatically used.


## Volumes parsing
If you upload the **Service Sales by Team Member** report, the parser uses a FillUp-style logic (bfill) and drops **Grand Total**.


## Volumes (Service Sales report)
The Service Sales by Team Member report includes an overall service summary before stylist breakdown. The app drops rows with no stylist assigned and also removes the **Grand Total** line.


## Staff list filter (optional)
Upload a staff list with columns **Stylist, Salon, Type** to filter the dashboard. The app keeps only rows where **Salon** matches the selected salon and **Type = Stylist**. This filter is applied to volumes and scenario outputs.


## v9 layout + KPI updates
- Global scenario controls moved into the main page.
- KPIs now use the filtered view.
- Added Qty × Per Service KPI (Before/After/Delta) when volumes provided.
- Reset scenario now explicitly restores global defaults and clears tables/filters.


## v10 hotfix
- Fixed DuplicateWidgetID in filters by creating filter widgets once and applying settings to both scenario and baseline tables without re-registering widgets.


## v11 hotfix
- Reset scenario now removes widget keys instead of setting them, fixing Streamlit session-state conflict for global inputs.


## v12 changes
- Reset now reliably resets global adjustments (widgets have no `value=` defaults; state is initialized explicitly).
- KPIs moved up directly below Global Scenario.
- Removed per-stylist scenario controls table.
- Added Stylist Summary table (filtered) with Qty×Price / Qty×Per Service totals and deltas.
