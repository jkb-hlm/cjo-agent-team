#!/usr/bin/env python3
"""Daily anomaly check: compare yesterday vs. 7-day rolling average.

Scheduled via n8n at 06:30 daily (after daily_cache).
Alerts Jakob on Slack only if Tier 1 KPIs deviate >10%.
Silent if all normal.
"""

from datetime import date, timedelta

from db import query
from slack import post


def check_etracker_anomalies() -> list[str]:
    """Check etracker Tier 1 KPIs for anomalies."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    week_ago = (date.today() - timedelta(days=8)).isoformat()

    alerts = []

    # Compare yesterday's totals vs. 7-day average (by device)
    rows = query("""
        WITH yesterday AS (
            SELECT attribute_value AS device,
                   conversion_rate AS cr,
                   conversion_value AS revenue,
                   unique_visits AS sessions
            FROM kpi_daily_etracker
            WHERE date = %s AND report_id = 'EADeviceType'
        ),
        avg_7d AS (
            SELECT attribute_value AS device,
                   AVG(conversion_rate) AS avg_cr,
                   AVG(conversion_value) AS avg_revenue,
                   AVG(unique_visits) AS avg_sessions
            FROM kpi_daily_etracker
            WHERE date BETWEEN %s AND %s
              AND report_id = 'EADeviceType'
            GROUP BY attribute_value
        )
        SELECT y.device, y.cr, a.avg_cr, y.revenue, a.avg_revenue,
               y.sessions, a.avg_sessions
        FROM yesterday y JOIN avg_7d a ON y.device = a.device
    """, (yesterday, week_ago, yesterday))

    for row in rows:
        device = row["device"]
        if row["avg_cr"] and row["avg_cr"] > 0:
            cr_delta = (row["cr"] - row["avg_cr"]) / row["avg_cr"]
            if abs(cr_delta) > 0.10:
                direction = "up" if cr_delta > 0 else "DOWN"
                alerts.append(
                    f"*CR {direction} {abs(cr_delta):.0%}* on {device} "
                    f"(yesterday: {row['cr']:.3%}, 7d avg: {row['avg_cr']:.3%})"
                )

        if row["avg_revenue"] and row["avg_revenue"] > 0:
            rev_delta = (row["revenue"] - row["avg_revenue"]) / row["avg_revenue"]
            if abs(rev_delta) > 0.15:
                direction = "up" if rev_delta > 0 else "DOWN"
                alerts.append(
                    f"*Revenue {direction} {abs(rev_delta):.0%}* on {device} "
                    f"(yesterday: {row['revenue']:.0f}, 7d avg: {row['avg_revenue']:.0f})"
                )

    return alerts


def check_ga4_anomalies() -> list[str]:
    """Check GA4 web KPIs for channel anomalies."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    week_ago = (date.today() - timedelta(days=8)).isoformat()

    alerts = []

    rows = query("""
        WITH yesterday AS (
            SELECT dimension_value AS channel,
                   session_conversion_rate AS cr,
                   sessions
            FROM kpi_daily_ga4_web
            WHERE date = %s AND dimension_name = 'sessionDefaultChannelGroup'
        ),
        avg_7d AS (
            SELECT dimension_value AS channel,
                   AVG(session_conversion_rate) AS avg_cr,
                   AVG(sessions) AS avg_sessions
            FROM kpi_daily_ga4_web
            WHERE date BETWEEN %s AND %s
              AND dimension_name = 'sessionDefaultChannelGroup'
            GROUP BY dimension_value
        )
        SELECT y.channel, y.cr, a.avg_cr, y.sessions, a.avg_sessions
        FROM yesterday y JOIN avg_7d a ON y.channel = a.channel
        WHERE a.avg_sessions > 50
    """, (yesterday, week_ago, yesterday))

    for row in rows:
        if row["avg_cr"] and row["avg_cr"] > 0:
            cr_delta = (row["cr"] - row["avg_cr"]) / row["avg_cr"]
            if abs(cr_delta) > 0.15:
                direction = "up" if cr_delta > 0 else "DOWN"
                alerts.append(
                    f"*CR {direction} {abs(cr_delta):.0%}* on {row['channel']} "
                    f"(yesterday: {row['cr']:.3%}, 7d avg: {row['avg_cr']:.3%})"
                )

    return alerts


def main():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    print(f"=== Anomaly Check — {yesterday} ===")

    all_alerts = []
    all_alerts.extend(check_etracker_anomalies())
    all_alerts.extend(check_ga4_anomalies())

    if not all_alerts:
        print("All clear — no anomalies detected.")
        return

    message = f"*Anomaly Alert — {yesterday}*\n\n" + "\n".join(f"- {a}" for a in all_alerts)
    print(message)
    post(message, channel="cjo")


if __name__ == "__main__":
    main()
