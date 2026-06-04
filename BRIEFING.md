# PS Gift Card Incentives — Project Briefing

**Repo:** `jyorgason/ps-gift-card-incentives`  
**Live URL:** https://jyorgason.github.io/ps-gift-card-incentives/  
**Last updated:** 2026-06-04  

---

## 1. Objective

Convert the Tableau workbook *Paid Social Gift Card Incentives* into a static HTML report
hosted on GitHub Pages. The report refreshes hourly via GitHub Actions and is embeddable
in Google Sites via iframe.

**Reference:** https://jyorgason.github.io/paid-social-report/ (existing paid-social report)

---

## 2. Source Tableau Workbook

**File:** `Paid Social Gift Card Incentives.twb`  
**Tableau Server:** `prod-useast-b.online.tableau.com/t/bamboohr/workbooks/PaidSocialGiftCardIncentives`  
**Revision:** 1.2  

### Dashboards in workbook (only "Gift Card Incentives" is rebuilt here)
The workbook contains 11 dashboards total; this project specifically recreates the
**Gift Card Incentives** dashboard plus its 8 constituent sheets.

---

## 3. Data Source

**Databricks table:**
```
analytics_us_east_2_certified_models.semantics.view_marketing_lead_gen_to_sales_funnel_stage_attribution
```

**Filter:** `channel_name_group = 'Paid Social'` + Gift Card classification filter (see §4)

**Key columns used:**
| Tableau field       | Databricks column                 | Notes                          |
|---------------------|-----------------------------------|--------------------------------|
| FUNNEL_STAGE        | attribution_stage_type            | MQL1, MQL2, OPP CREATION, etc. |
| DATE                | attribution_stage_date            |                                |
| MQL1                | mql1_counter                      | SUM = MQL1 count               |
| MQL2                | mql2_counter                      |                                |
| SAO                 | opportunity_creation_counter      | Concurrent zero-out applied    |
| CW                  | closed_won_counter                 | Concurrent zero-out applied    |
| DQ                  | disqualified_counter              |                                |
| CW_MRR              | booked_commissionable_mrr         |                                |
| AD_GROUP_NAME       | ad_group_name                     |                                |
| AD_GROUP_ID         | ad_group_id                       |                                |
| UTM_CAMPAIGN        | utm_campaign                      |                                |
| SUBCHANNEL_NAME     | subchannel_name                   |                                |

**Lookback:** 2 years (730 days) on each refresh

---

## 4. Gift Card Incentive Classification Logic

Recreates the Tableau calculated field `Calculation_6730700046477824000`:

```sql
CASE
  WHEN CONTAINS(ad_group_name, '$50')
       OR ad_group_id IN ('301700166','307068346','307092336','307100326',
                          '307913506','307923256','391368056')
  THEN '$50'
  WHEN CONTAINS(ad_group_name, '$75')  THEN '$75'
  WHEN CONTAINS(ad_group_name, '$100') THEN '$100'
  WHEN CONTAINS(ad_group_name, '$150')
       OR CONTAINS(utm_campaign, '150') THEN '$150'
  ELSE 'Other'
END
```

**Tier colors (from Tableau dashboard):**
| Tier    | Hex       |
|---------|-----------|
| Other   | `#df5857` |
| $50     | `#4e79a8` |
| $75     | `#78b7b2` |
| $100    | `#f18f1c` |
| $150    | `#59a14f` |

---

## 5. Report Layout (index.html)

### Header
- Title: "Paid Social Gift Card Incentives"
- Controls: Start Date, End Date, Metric selector (MQL1/MQL2/SAO/CW/DQ/CW MRR)
- Last updated timestamp, dark mode toggle

### Tier Filter Pills
- Toggle visibility of any/all of: Other | $50 | $75 | $100 | $150

### Section 1 — KPI Cards by Tier
Five side-by-side cards, one per tier, each showing:
- MQL1, SAO (+ MQL1→SAO%), CW (+ SAO→CW%), DQ (+ DQ rate), CW MRR

### Section 2 — Line Chart
Selected metric over time, one line per tier. Filterable by date + tier.

### Section 3 — Stacked Bar + Conversion Rate Bar
- Left: Monthly stacked bar by tier for selected metric
- Right: MQL1→SAO conversion rate by tier (horizontal comparison)

### Section 4 — Ad Group Table
Sortable, searchable table with columns:
Tier | Ad Group | Campaign | MQL1 | SAO | CW | DQ | CW MRR | MQL1→SAO%

---

## 6. Tableau Sheets Recreated

| Tableau Sheet              | Web App Component                      |
|----------------------------|----------------------------------------|
| GC \| Other \| Totals       | KPI Card — Other                       |
| GC \| 50 \| Totals          | KPI Card — $50                         |
| GC \| 75 \| Totals          | KPI Card — $75                         |
| GC \| 100 \| Totals         | KPI Card — $100                        |
| GC \| 150 \| Totals         | KPI Card — $150                        |
| GC \| Lines                 | Line Chart (metric over time)          |
| GC \| Bar Stacked \| Total  | Stacked Bar Chart                      |
| GC \| Bar \| Metric \| Ad Group | Ad Group Table + Conversion Bar    |
| GC \| Bar \| Totals \| Ad Group | Ad Group Table                     |

---

## 7. Parameters Retained

| Tableau Parameter | Web App Control           | Values                                |
|-------------------|---------------------------|---------------------------------------|
| Start Date        | Date input                | Any date                              |
| End Date          | Date input (default Today)| Any date or Today                     |
| Metric            | Dropdown                  | MQL1, MQL2, SAO, CW, DQ, CW MRR      |
| Gift Card Tier    | Toggle pills              | Other, $50, $75, $100, $150           |

---

## 8. Architecture

```
ps-gift-card-incentives/
├── index.html                      # Single-page report app
├── scripts/
│   └── generate_data.py            # Databricks → data/gc_data.json
├── data/
│   └── gc_data.json                # Auto-generated (do not edit)
├── fonts/
│   └── Fields-*.woff2              # BambooHR proprietary fonts
├── .github/
│   └── workflows/
│       └── refresh.yml             # Hourly GitHub Actions job
└── BRIEFING.md                     # This file
```

**Data pipeline:**
1. GitHub Actions runs `generate_data.py` every hour
2. Script queries Databricks (Token auth) → writes `gc_data.json`
3. Commits + pushes updated JSON to `main`
4. GitHub Pages serves the static files

**JSON structure (`gc_data.json`):**
```json
{
  "generated_at": "ISO timestamp",
  "monthly": [
    { "gc_tier":"$100", "month":"2026-05-01", "mql1":67, "mql2":0, "sao":20, "cw":0, "dq":4, "cw_mrr":0 },
    ...
  ],
  "ad_groups": [
    { "gc_tier":"$100", "ad_group_name":"...", "ad_campaign_name":"...", "mql1":10, "sao":4, "cw":1, "dq":0, "cw_mrr":500 },
    ...
  ]
}
```

---

## 9. GitHub Secrets Required

| Secret                  | Value                                               |
|-------------------------|-----------------------------------------------------|
| `DATABRICKS_HOST`       | `https://dbc-eeb5fa04-7840.cloud.databricks.com`    |
| `DATABRICKS_HTTP_PATH`  | `/sql/1.0/warehouses/2b4daea90ede5709`              |
| `DATABRICKS_TOKEN`      | Personal Access Token (from Databricks Settings)    |

---

## 10. Data Verification (as of 2026-06-04)

Sample from Databricks query (2024-01-01 → present):

| Tier   | Months w/ Data | Total MQL1 | Total SAO | Total CW |
|--------|----------------|------------|-----------|----------|
| $50    | 30             | ~2,100     | ~1,200    | ~55      |
| $100   | 28             | ~1,900     | ~700      | ~25      |
| $75    | 22             | ~700       | ~280      | ~12      |
| $150   | 15             | ~600       | ~250      | ~6       |
| Other  | (minimal)      | —          | —         | —        |

---

## 11. Enhancements vs. Tableau

| Feature                              | Tableau | Web App |
|--------------------------------------|---------|---------|
| Dark mode                            | ✗       | ✓       |
| Tier toggle pills                    | ✗       | ✓       |
| Ad group search                      | ✗       | ✓       |
| Sortable table                       | ✗       | ✓       |
| MQL1→SAO conversion rate chart       | ✗       | ✓       |
| Embeddable via iframe                | ✗       | ✓       |
| Hourly auto-refresh                  | ✗       | ✓       |
| Mobile responsive                    | ✗       | ✓       |

---

## 12. Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| Q1 | Use `channel_name_group = 'Paid Social'` as the channel filter | Matches the Tableau workbook's Marketing Funnel data source which is scoped to paid social |
| Q2 | Lookback = 730 days (2 years) | Provides full trend history while keeping JSON file size reasonable |
| Q3 | No SAO_TA / CW_TA columns in web app | Not available in certified view; Tactical Attribution metrics can be added later if needed |
| Q4 | Ad group table is not broken out by month | Keeps data size manageable; monthly detail available in the line/bar charts |
| Q5 | Fonts served from local `fonts/` dir | Same approach as paid-social-report; avoids Google Fonts for proprietary typeface |

---

## 13. Changelog

| Date       | Change                                         |
|------------|------------------------------------------------|
| 2026-06-04 | Initial project setup; Tableau workbook audited; Databricks schema confirmed; full web app built; GitHub repo created |
