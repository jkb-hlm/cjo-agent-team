"""GA4 Data API tools for Kai.

Auth:     Service account JSON key
API:      Google Analytics Data API v1 (google-analytics-data library)
Docs:     https://developers.google.com/analytics/devguides/reporting/data/v1

Properties configured via GA4_PROPERTY_WEBSHOP and GA4_PROPERTY_APP env vars.

Common dimensions:
  date, country, city, deviceCategory, sessionDefaultChannelGroup,
  sessionSource, sessionMedium, sessionCampaignName, pagePath, pageTitle,
  landingPage, newVsReturning, browser, operatingSystem

Common metrics:
  sessions, totalUsers, newUsers, bounceRate, averageSessionDuration,
  screenPageViews, screenPageViewsPerSession, conversions, purchaseRevenue,
  transactions, ecommercePurchases, sessionConversionRate,
  addToCarts, checkouts, cartToViewRate, purchaseToViewRate
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    FilterExpressionList,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.oauth2 import service_account

load_dotenv(Path(__file__).parent.parent / ".env")

_KEY_FILE = os.getenv("GA4_KEY_FILE")
_PROPERTY_WEB = os.getenv("GA4_PROPERTY_WEBSHOP")
_PROPERTY_APP = os.getenv("GA4_PROPERTY_APP")

_DEFAULT_WEB_METRICS = [
    "sessions",
    "totalUsers",
    "newUsers",
    "bounceRate",
    "averageSessionDuration",
    "screenPageViewsPerSession",
    "sessionConversionRate",
    "ecommercePurchases",
    "purchaseRevenue",
]


def _client() -> BetaAnalyticsDataClient:
    creds = service_account.Credentials.from_service_account_file(
        _KEY_FILE,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


def _property_id(property: str) -> str:
    if property == "app":
        return f"properties/{_PROPERTY_APP}"
    return f"properties/{_PROPERTY_WEB}"


def run_report(
    start_date: str,
    end_date: str,
    dimensions: Optional[list[str]] = None,
    metrics: Optional[list[str]] = None,
    dimension_filters: Optional[list[dict]] = None,
    order_by: Optional[str] = None,
    order_desc: bool = True,
    limit: int = 100,
    property: str = "web",
) -> dict:
    """
    Run a GA4 Data API report.

    Args:
        start_date:        YYYY-MM-DD or relative ('7daysAgo', '30daysAgo', 'yesterday')
        end_date:          YYYY-MM-DD or 'today'
        dimensions:        List of dimension names, e.g. ['country', 'deviceCategory']
        metrics:           List of metric names — defaults to standard web KPI set
        dimension_filters: List of filter dicts:
                             {"dimension": "country", "value": "United States"}
                             {"dimension": "pagePath", "contains": "/collections/"}
                             {"dimension": "country", "not": True, "value": "Germany"}
        order_by:          Metric or dimension name to sort by
        order_desc:        True = descending (default)
        limit:             Max rows to return (default 100)
        property:          'web' (default) or 'app'

    Returns:
        dict with 'headers' (list of names) and 'rows' (list of dicts)
    """
    if metrics is None:
        metrics = _DEFAULT_WEB_METRICS

    req = RunReportRequest(
        property=_property_id(property),
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name=d) for d in (dimensions or [])],
        metrics=[Metric(name=m) for m in metrics],
        limit=limit,
    )

    # Build dimension filters
    if dimension_filters:
        filter_exprs = []
        for f in dimension_filters:
            dim = f["dimension"]
            negate = f.get("not", False)

            if "contains" in f:
                filt = Filter(
                    field_name=dim,
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.CONTAINS,
                        value=f["contains"],
                        case_sensitive=False,
                    ),
                )
            elif "begins_with" in f:
                filt = Filter(
                    field_name=dim,
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.BEGINS_WITH,
                        value=f["begins_with"],
                        case_sensitive=False,
                    ),
                )
            else:
                filt = Filter(
                    field_name=dim,
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.EXACT,
                        value=f["value"],
                        case_sensitive=False,
                    ),
                )

            expr = FilterExpression(filter=filt)
            if negate:
                expr = FilterExpression(not_expression=expr)
            filter_exprs.append(expr)

        if len(filter_exprs) == 1:
            req.dimension_filter = filter_exprs[0]
        else:
            req.dimension_filter = FilterExpression(
                and_group=FilterExpressionList(expressions=filter_exprs)
            )

    # Order by
    if order_by:
        if order_by in (metrics or []):
            req.order_bys = [OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name=order_by),
                desc=order_desc,
            )]
        else:
            req.order_bys = [OrderBy(
                dimension=OrderBy.DimensionOrderBy(dimension_name=order_by),
                desc=order_desc,
            )]

    try:
        client = _client()
        response = client.run_report(req)
    except Exception as e:
        return {"error": str(e)}

    dim_headers = [h.name for h in response.dimension_headers]
    met_headers = [h.name for h in response.metric_headers]
    headers = dim_headers + met_headers

    rows = []
    for row in response.rows:
        record = {}
        for i, val in enumerate(row.dimension_values):
            record[dim_headers[i]] = val.value
        for i, val in enumerate(row.metric_values):
            # Cast numeric strings
            raw = val.value
            try:
                record[met_headers[i]] = float(raw) if "." in raw else int(raw)
            except (ValueError, TypeError):
                record[met_headers[i]] = raw
        rows.append(record)

    return {
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "totals": {
            met_headers[i]: (
                float(t.value) if "." in t.value else int(t.value)
                if t.value else 0
            )
            for i, t in enumerate(response.totals[0].metric_values)
        } if response.totals else {},
    }


# ── Convenience wrappers ────────────────────────────────────────────────────

def get_by_country(start_date: str, end_date: str, limit: int = 30) -> dict:
    """Sessions, CR, revenue by country."""
    return run_report(start_date, end_date, dimensions=["country"], limit=limit,
                      order_by="sessions")


def get_by_device(start_date: str, end_date: str) -> dict:
    """Sessions, CR, revenue by device category (desktop/mobile/tablet)."""
    return run_report(start_date, end_date, dimensions=["deviceCategory"])


def get_by_channel(start_date: str, end_date: str) -> dict:
    """Sessions, CR, revenue by default channel group."""
    return run_report(start_date, end_date, dimensions=["sessionDefaultChannelGroup"])


def get_us_funnel(start_date: str, end_date: str) -> dict:
    """US-only sessions by device and channel — for funnel analysis."""
    return run_report(
        start_date, end_date,
        dimensions=["deviceCategory", "sessionDefaultChannelGroup"],
        dimension_filters=[{"dimension": "country", "value": "United States"}],
        order_by="sessions",
        limit=50,
    )
