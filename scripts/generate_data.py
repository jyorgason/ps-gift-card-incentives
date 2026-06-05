"""
PS Gift Card Incentives — Data Generation Script
Uses the Databricks OAuth connector (same auth as the Workbench connector).
Writes data/gc_data.json for the HTML report.

Data source: analytics_us_east_2_production_sandbox_mktg.jyorgason.marketing_funnel
  - Row-level marketing funnel attribution table (matches the Tableau "Marketing Funnel"
    data source exactly — same field names, same funnel logic)
  - Scoped to CHANNEL_NAME = 'Paid Social'

Run locally:   python scripts/generate_data.py
Automated via: ~/Library/LaunchAgents/com.bamboohr.ps-gift-card-incentives.plist

NOTE — Known divergence from Tableau (approved 2026-06-05):
  MQL1>SAO rate = SUM(SAO) / SUM(MQL1)  [all SAOs in denominator]
  Tableau uses  = SUM(SAO where MQL_SOURCE='MQL1') / SUM(MQL1)  [MQL1-sourced only]
  This means our rate is slightly higher than Tableau's. Intentional.
"""

import os
import json
import sys
from datetime import date, datetime, timedelta

# Reuse the Workbench Databricks Connector for auth
sys.path.insert(0, os.path.expanduser(
    "~/Desktop/Workbench/Databricks Connector/your-project/src"
))

from databricks import sql
from dotenv import load_dotenv

load_dotenv(os.path.expanduser(
    "~/Desktop/Workbench/Databricks Connector/your-project/.env"
))

SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME")
HTTP_PATH       = os.getenv("DATABRICKS_HTTP_PATH")
TABLE           = "analytics_us_east_2_production_sandbox_mktg.jyorgason.marketing_funnel"
OUTPUT_FILE     = os.path.join(os.path.dirname(__file__), "..", "data", "gc_data.json")

LOOKBACK_DAYS = 730  # 2 years

# ---------------------------------------------------------------------------
# Gift Card Incentive tier classification — matches Tableau calculated field
# Calculation_6730700046477824000 exactly.
# ---------------------------------------------------------------------------
GC_TIER_SQL = """
CASE
  WHEN CONTAINS(AD_GROUP_NAME, '$50')
       OR AD_GROUP_ID IN ('301700166','307068346','307092336','307100326',
                          '307913506','307923256','391368056')
  THEN '$50'
  WHEN CONTAINS(AD_GROUP_NAME, '$75')  THEN '$75'
  WHEN CONTAINS(AD_GROUP_NAME, '$100') THEN '$100'
  WHEN CONTAINS(AD_GROUP_NAME, '$150')
       OR CONTAINS(UTM_CAMPAIGN, '150') THEN '$150'
  ELSE 'Other'
END
"""


def run_query(sql_text: str) -> list[dict]:
    with sql.connect(
        server_hostname=SERVER_HOSTNAME,
        http_path=HTTP_PATH,
        auth_type="databricks-oauth",
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_text)
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetch_monthly_by_tier(lookback_days: int) -> list[dict]:
    """
    All Paid Social rows, classified by GC tier.
    No GC filter applied — 'Other' captures all non-GC paid social campaigns.
    """
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    return run_query(f"""
    SELECT
      {GC_TIER_SQL}                                           AS gc_tier,
      DATE_FORMAT(DATE_TRUNC('month', `DATE`), 'yyyy-MM-dd') AS month,
      SUM(MQL1)      AS mql1,
      SUM(MQL2)      AS mql2,
      SUM(MQL1_TA)   AS mql1_ta,
      SUM(MQL2_TA)   AS mql2_ta,
      SUM(SAL)       AS sal,
      SUM(SAL_TA)    AS sal_ta,
      SUM(TQL)       AS tql,
      SUM(TQL_TA)    AS tql_ta,
      SUM(SAO)       AS sao,
      SUM(SAO_TA)    AS sao_ta,
      SUM(CW)        AS cw,
      SUM(CW_TA)     AS cw_ta,
      CAST(SUM(CW_MRR)    AS DOUBLE) AS cw_mrr,
      CAST(SUM(CW_MRR_TA) AS DOUBLE) AS cw_mrr_ta,
      SUM(CL)        AS cl,
      SUM(DQ)        AS dq
    FROM {TABLE}
    WHERE CHANNEL_NAME = 'Paid Social'
      AND ATTRIBUTION_MODEL = 'First 90 Days'
      AND `DATE` >= '{start}'
    GROUP BY 1, 2
    ORDER BY 2 DESC, 1
    """)


def fetch_ad_group_totals(lookback_days: int) -> list[dict]:
    """
    All Paid Social ad groups, classified by GC tier.
    'Other' rows = non-GC paid social campaigns.
    Only includes ad groups with at least 1 MQL1 or SAO to keep the table useful.
    """
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    return run_query(f"""
    SELECT
      {GC_TIER_SQL}  AS gc_tier,
      AD_GROUP_NAME  AS ad_group_name,
      AD_CAMPAIGN_NAME AS ad_campaign_name,
      SUM(MQL1)      AS mql1,
      SUM(SAO)       AS sao,
      SUM(CW)        AS cw,
      SUM(DQ)        AS dq,
      CAST(SUM(CW_MRR) AS DOUBLE) AS cw_mrr
    FROM {TABLE}
    WHERE CHANNEL_NAME = 'Paid Social'
      AND ATTRIBUTION_MODEL = 'First 90 Days'
      AND `DATE` >= '{start}'
    GROUP BY 1, 2, 3
    ORDER BY 1, 4 DESC
    """)


def fetch_monthly_adgroups(lookback_days: int) -> list[dict]:
    """
    Tier × month × ad_group breakdown — powers the VizInTooltip bar chart.
    Only the metrics needed for tooltip display; limited to last 13 months
    to keep JSON size manageable.
    """
    start = (date.today() - timedelta(days=lookback_days)).isoformat()  # match main lookback
    return run_query(f"""
    SELECT
      {GC_TIER_SQL}                                           AS gc_tier,
      DATE_FORMAT(DATE_TRUNC('month', `DATE`), 'yyyy-MM-dd') AS month,
      AD_GROUP_NAME                                           AS ad_group_name,
      SUM(MQL1)                    AS mql1,
      SUM(SAO)                     AS sao,
      SUM(CW)                      AS cw,
      CAST(SUM(CW_MRR) AS DOUBLE)  AS cw_mrr,
      SUM(MQL1_TA)                 AS mql1_ta,
      SUM(SAO_TA)                  AS sao_ta,
      SUM(CW_TA)                   AS cw_ta,
      CAST(SUM(CW_MRR_TA) AS DOUBLE) AS cw_mrr_ta,
      SUM(SAL)                     AS sal,
      SUM(TQL)                     AS tql,
      SUM(CL)                      AS cl,
      SUM(DQ)                      AS dq
    FROM {TABLE}
    WHERE CHANNEL_NAME = 'Paid Social'
      AND ATTRIBUTION_MODEL = 'First 90 Days'
      AND `DATE` >= '{start}'
    GROUP BY 1, 2, 3
    ORDER BY 2 DESC, 1, 4 DESC
    """)


def main():
    ts = datetime.utcnow().isoformat()
    print(f"[{ts}] Fetching monthly-by-tier ({LOOKBACK_DAYS} days)…")
    monthly = fetch_monthly_by_tier(LOOKBACK_DAYS)
    print(f"  → {len(monthly)} rows")

    print(f"[{ts}] Fetching ad-group totals…")
    ad_groups = fetch_ad_group_totals(LOOKBACK_DAYS)
    print(f"  → {len(ad_groups)} rows")

    print(f"[{ts}] Fetching monthly ad-group breakdown (for tooltip)…")
    monthly_adgroups = fetch_monthly_adgroups(LOOKBACK_DAYS)
    print(f"  → {len(monthly_adgroups)} rows")

    output = {
        "generated_at":    datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "monthly":         monthly,
        "ad_groups":       ad_groups,
        "monthly_adgroups": monthly_adgroups,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, default=str)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"[{ts}] Written → {OUTPUT_FILE} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
