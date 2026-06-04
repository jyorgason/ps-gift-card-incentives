"""
PS Gift Card Incentives — Data Generation Script
Queries Databricks and writes data/gc_data.json for the HTML report.

Environment variables required:
  DATABRICKS_HOST          e.g. https://dbc-eeb5fa04-7840.cloud.databricks.com
  DATABRICKS_TOKEN         Personal Access Token
  DATABRICKS_HTTP_PATH     e.g. /sql/1.0/warehouses/abc123def456

Run locally:   python scripts/generate_data.py
Run via CI:    triggered by .github/workflows/refresh.yml
"""

import os
import json
import time
import requests
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST        = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN       = os.environ["DATABRICKS_TOKEN"]
HTTP_PATH   = os.environ["DATABRICKS_HTTP_PATH"]
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "gc_data.json")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

LOOKBACK_DAYS = 730  # 2 years

# ---------------------------------------------------------------------------
# Gift Card Incentive classification (matches Tableau workbook logic)
# ---------------------------------------------------------------------------
GC_TIER_SQL = """
CASE
  WHEN CONTAINS(ad_group_name, '$50')
       OR ad_group_id IN ('301700166','307068346','307092336','307100326','307913506','307923256','391368056')
  THEN '$50'
  WHEN CONTAINS(ad_group_name, '$75') THEN '$75'
  WHEN CONTAINS(ad_group_name, '$100') THEN '$100'
  WHEN CONTAINS(ad_group_name, '$150') OR CONTAINS(utm_campaign, '150') THEN '$150'
  ELSE 'Other'
END
"""

GC_FILTER_SQL = """(
  CONTAINS(ad_group_name, '$50') OR CONTAINS(ad_group_name, '$75')
  OR CONTAINS(ad_group_name, '$100') OR CONTAINS(ad_group_name, '$150')
  OR CONTAINS(utm_campaign, '150')
  OR ad_group_id IN ('301700166','307068346','307092336','307100326','307913506','307923256','391368056')
)"""

# ---------------------------------------------------------------------------
# Databricks SQL execution helpers
# ---------------------------------------------------------------------------
def run_query(sql: str) -> list[dict]:
    """Execute SQL on Databricks; return rows as list of dicts."""
    warehouse_id = HTTP_PATH.split("/")[-1]
    resp = requests.post(
        f"{HOST}/api/2.0/sql/statements",
        headers=HEADERS,
        json={
            "statement": sql,
            "warehouse_id": warehouse_id,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY",
        },
    )
    resp.raise_for_status()
    body = resp.json()
    statement_id = body["statement_id"]

    while body["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(3)
        r = requests.get(
            f"{HOST}/api/2.0/sql/statements/{statement_id}",
            headers=HEADERS,
        )
        r.raise_for_status()
        body = r.json()

    if body["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"Query failed: {body['status']}\nSQL:\n{sql[:500]}")

    columns = [c["name"] for c in body["manifest"]["schema"]["columns"]]
    rows = []
    for chunk in body.get("result", {}).get("data_array", []):
        rows.append(dict(zip(columns, chunk)))

    # Fetch additional pages if truncated
    chunk_count = body["manifest"]["total_chunk_count"]
    for chunk_idx in range(1, chunk_count):
        r = requests.get(
            f"{HOST}/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_idx}",
            headers=HEADERS,
        )
        r.raise_for_status()
        for chunk in r.json().get("data_array", []):
            rows.append(dict(zip(columns, chunk)))

    return rows


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def fetch_monthly_by_tier(lookback_days: int) -> list[dict]:
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    sql = f"""
    SELECT
      {GC_TIER_SQL} AS gc_tier,
      DATE_FORMAT(DATE_TRUNC('month', attribution_stage_date), 'yyyy-MM-dd') AS month,
      SUM(mql1_counter)                AS mql1,
      SUM(mql2_counter)                AS mql2,
      SUM(opportunity_creation_counter) AS sao,
      SUM(closed_won_counter)          AS cw,
      SUM(disqualified_counter)        AS dq,
      CAST(SUM(booked_commissionable_mrr) AS DOUBLE) AS cw_mrr
    FROM analytics_us_east_2_certified_models.semantics.view_marketing_lead_gen_to_sales_funnel_stage_attribution
    WHERE channel_name_group = 'Paid Social'
      AND {GC_FILTER_SQL}
      AND attribution_stage_date >= '{start}'
    GROUP BY 1, 2
    ORDER BY 2 DESC, 1
    """
    return run_query(sql)


def fetch_ad_group_totals(lookback_days: int) -> list[dict]:
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    sql = f"""
    SELECT
      {GC_TIER_SQL} AS gc_tier,
      ad_group_name,
      ad_campaign_name,
      SUM(mql1_counter)                AS mql1,
      SUM(opportunity_creation_counter) AS sao,
      SUM(closed_won_counter)          AS cw,
      SUM(disqualified_counter)        AS dq,
      CAST(SUM(booked_commissionable_mrr) AS DOUBLE) AS cw_mrr
    FROM analytics_us_east_2_certified_models.semantics.view_marketing_lead_gen_to_sales_funnel_stage_attribution
    WHERE channel_name_group = 'Paid Social'
      AND {GC_FILTER_SQL}
      AND attribution_stage_date >= '{start}'
    GROUP BY 1, 2, 3
    ORDER BY 1, SUM(mql1_counter) DESC
    """
    return run_query(sql)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ts = datetime.utcnow().isoformat()
    print(f"[{ts}] Fetching monthly-by-tier data ({LOOKBACK_DAYS} days)...")
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
