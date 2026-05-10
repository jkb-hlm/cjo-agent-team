"""PostgreSQL connection and helpers for CJO data cache."""

import json
from contextlib import contextmanager
from datetime import date

import psycopg2
from psycopg2.extras import execute_values, Json

from config import PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE, PG_SCHEMA


@contextmanager
def get_conn():
    """Context manager for PostgreSQL connection."""
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        database=PG_DATABASE,
        options=f"-c search_path={PG_SCHEMA},public",
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    """Run schema.sql to create tables."""
    schema_path = __import__("pathlib").Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()
    with get_conn() as conn:
        conn.cursor().execute(sql)
    print("Schema initialized.")


def upsert_etracker_rows(report_id: str, attribute_name: str, rows: list[dict], report_date: date):
    """Insert or update etracker data rows."""
    if not rows:
        return 0

    def _num(v):
        """Convert etracker '-' placeholders to None."""
        if v is None or v == "-":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    values = []
    for row in rows:
        fid = __import__('config').ETRACKER_FUNNEL_ID
        values.append((
            report_date,
            report_id,
            attribute_name,
            str(row.get(attribute_name, "total")),
            _num(row.get("unique_visits")),
            _num(row.get("unique_visitors")),
            _num(row.get("page_impressions")),
            _num(row.get("bounces_per_visit")),
            _num(row.get("staytime_per_unique_visits_v3")),
            _num(row.get("pi_per_unique_visits")),
            _num(row.get(f"conversion_count_af_position({fid})")),
            _num(row.get(f"conversion_value_af_position({fid})")),
            _num(row.get(f"conversion_rate_af_position({fid})")),
            Json(row),
        ))

    sql = """
        INSERT INTO kpi_daily_etracker
            (date, report_id, attribute_name, attribute_value,
             unique_visits, unique_visitors, page_impressions,
             bounces_per_visit, staytime_per_visit, pi_per_visit,
             conversion_count, conversion_value, conversion_rate, raw_json)
        VALUES %s
        ON CONFLICT (date, report_id, attribute_name, attribute_value)
        DO UPDATE SET
            unique_visits = EXCLUDED.unique_visits,
            unique_visitors = EXCLUDED.unique_visitors,
            page_impressions = EXCLUDED.page_impressions,
            bounces_per_visit = EXCLUDED.bounces_per_visit,
            staytime_per_visit = EXCLUDED.staytime_per_visit,
            pi_per_visit = EXCLUDED.pi_per_visit,
            conversion_count = EXCLUDED.conversion_count,
            conversion_value = EXCLUDED.conversion_value,
            conversion_rate = EXCLUDED.conversion_rate,
            raw_json = EXCLUDED.raw_json
    """
    with get_conn() as conn:
        execute_values(conn.cursor(), sql, values)
    return len(values)


def upsert_ga4_rows(table: str, dimension_name: str, rows: list[dict], report_date: date):
    """Insert or update GA4 data rows (works for both web and app tables)."""
    if not rows:
        return 0

    values = []
    for row in rows:
        values.append((
            report_date,
            dimension_name,
            str(row.get(dimension_name, "total")),
            row.get("sessions"),
            row.get("totalUsers"),
            row.get("newUsers"),
            row.get("bounceRate"),
            row.get("averageSessionDuration"),
            row.get("screenPageViewsPerSession"),
            row.get("sessionConversionRate"),
            row.get("ecommercePurchases"),
            row.get("purchaseRevenue"),
            Json(row),
        ))

    sql = f"""
        INSERT INTO {table}
            (date, dimension_name, dimension_value,
             sessions, total_users, new_users, bounce_rate,
             avg_session_duration, pages_per_session,
             session_conversion_rate, ecommerce_purchases,
             purchase_revenue, raw_json)
        VALUES %s
        ON CONFLICT (date, dimension_name, dimension_value)
        DO UPDATE SET
            sessions = EXCLUDED.sessions,
            total_users = EXCLUDED.total_users,
            new_users = EXCLUDED.new_users,
            bounce_rate = EXCLUDED.bounce_rate,
            avg_session_duration = EXCLUDED.avg_session_duration,
            pages_per_session = EXCLUDED.pages_per_session,
            session_conversion_rate = EXCLUDED.session_conversion_rate,
            ecommerce_purchases = EXCLUDED.ecommerce_purchases,
            purchase_revenue = EXCLUDED.purchase_revenue,
            raw_json = EXCLUDED.raw_json
    """
    with get_conn() as conn:
        execute_values(conn.cursor(), sql, values)
    return len(values)


def query(sql: str, params=None) -> list[dict]:
    """Run a SELECT and return rows as dicts."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def save_learning(agent: str, type_: str, insight: str, source_test_id: str = None, page_type: str = None):
    """Save an agent learning to persistent memory."""
    with get_conn() as conn:
        conn.cursor().execute(
            """INSERT INTO learnings (agent, type, insight, source_test_id, page_type)
               VALUES (%s, %s, %s, %s, %s)""",
            (agent, type_, insight, source_test_id, page_type),
        )


if __name__ == "__main__":
    init_schema()
