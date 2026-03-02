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
