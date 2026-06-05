"""
PS Gift Card Incentives — Data Generation Script
Uses the Databricks OAuth connector (same auth as the Workbench connector).
Writes data/gc_data.json for the HTML report.

Run locally:   python scripts/generate_data.py
Automated via: ~/Library/LaunchAgents/com.bamboohr.ps-gift-card-incentives.plist
"""

import os
import json
import sys
from datetime import date, datetime, timedelta

# Use same connector as /Users/jyorgason/Desktop/Workbench/Databricks Connector
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
OUTPUT_FILE     = os.path.join(os.path.dirname(__file__), "..", "data", "gc_data.json")

LOOKBACK_DAYS = 730  # 2 years

# ---------------------------------------------------------------------------
# Gift Card Incentive classification (matches Tableau workbook logic exactly)
# ---------------------------------------------------------------------------
GC_TIER_SQL = """
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
"""

GC_FILTER_SQL = """(
  CONTAINS(ad_group_name, '$50') OR CONTAINS(ad_group_name, '$75')
  OR CONTAINS(ad_group_name, '$100') OR CONTAINS(ad_group_name, '$150')
  OR CONTAINS(utm_campaign, '150')
  OR ad_group_id IN ('301700166','307068346','307092336','307100326',
                     '307913506','307923256','391368056')
)"""


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
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    # No GC filter here — ALL paid social rows included so "Other" tier is populated.
    # "Other" = any paid social row whose ad_group_name/utm_campaign has no GC amount.
    return run_query(f"""
    SELECT
      {GC_TIER_SQL} AS gc_tier,
      DATE_FORMAT(DATE_TRUNC('month', attribution_stage_date), 'yyyy-MM-dd') AS month,
      SUM(mql1_counter)                 AS mql1,
      SUM(mql2_counter)                 AS mql2,
      SUM(opportunity_creation_counter) AS sao,
      SUM(closed_won_counter)           AS cw,
      SUM(disqualified_counter)         AS dq,
      CAST(SUM(booked_commissionable_mrr) AS DOUBLE) AS cw_mrr
    FROM analytics_us_east_2_certified_models.semantics.view_marketing_lead_gen_to_sales_funnel_stage_attribution
    WHERE channel_name_group = 'Paid Social'
      AND attribution_stage_date >= '{start}'
    GROUP BY 1, 2
    ORDER BY 2 DESC, 1
    """)


def fetch_ad_group_totals(lookback_days: int) -> list[dict]:
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    return run_query(f"""
    SELECT
      {GC_TIER_SQL} AS gc_tier,
      ad_group_name,
      ad_campaign_name,
      SUM(mql1_counter)                 AS mql1,
      SUM(opportunity_creation_counter) AS sao,
      SUM(closed_won_counter)           AS cw,
      SUM(disqualified_counter)         AS dq,
      CAST(SUM(booked_commissionable_mrr) AS DOUBLE) AS cw_mrr
    FROM analytics_us_east_2_certified_models.semantics.view_marketing_lead_gen_to_sales_funnel_stage_attribution
    WHERE channel_name_group = 'Paid Social'
      AND {GC_FILTER_SQL}
      AND attribution_stage_date >= '{start}'
    GROUP BY 1, 2, 3
    ORDER BY 1, SUM(mql1_counter) DESC
    """)


def main():
    ts = datetime.utcnow().isoformat()
    print(f"[{ts}] Fetching monthly-by-tier ({LOOKBACK_DAYS} days)...")
    monthly = fetch_monthly_by_tier(LOOKBACK_DAYS)
    print(f"  → {len(monthly)} rows")

    print(f"[{ts}] Fetching ad-group totals...")
    ad_groups = fetch_ad_group_totals(LOOKBACK_DAYS)
    print(f"  → {len(ad_groups)} rows")

    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "monthly": monthly,
        "ad_groups": ad_groups,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, default=str)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"[{ts}] Written → {OUTPUT_FILE} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
