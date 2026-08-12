"""Machine uptime / utilization statistics.

Uptime is derived from the historical stream of realtime samples in
dbo.vw_machine_realtime (the same view GET /api/realtime/{device_id} already
uses). Each sample carries `machine_status`; a machine reporting
machine_status == 1 is "active" (producing), any other reported value is
"standby" (idle but still online). A gap between two consecutive samples
longer than OFFLINE_GAP_SECONDS is treated as "off" -- this mirrors the live
dashboard's own offline detection (see statusOf()/ageText() in
frontend/js/app.js, which declares a device offline once its last sample is
older than 120 seconds).

Time is bucketed by calendar day first (splitting any segment that crosses
midnight), then rolled up into week/month buckets as requested, so the
day/week/month views all share one consistent calculation.
"""

from collections import OrderedDict
from contextlib import closing
from datetime import date, datetime, timedelta

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_connection
from ..security import require_user


router = APIRouter(prefix="/api", tags=["uptime"])

# Matches the offline threshold used live on the dashboard (ageText/statusOf
# in frontend/js/app.js): no data for more than this long => treat as off.
OFFLINE_GAP_SECONDS = 120

DEFAULT_PERIODS = {"day": 30, "week": 12, "month": 12}
MAX_PERIODS = {"day": 366, "week": 104, "month": 36}


def _range_start(granularity: str, periods: int, today: date) -> date:
    if granularity == "day":
        return today - timedelta(days=periods - 1)
    if granularity == "week":
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(weeks=periods - 1)
    # month
    total_months = (today.year * 12 + (today.month - 1)) - (periods - 1)
    year, month = divmod(total_months, 12)
    return date(year, month + 1, 1)


def _split_into_days(seg_start: datetime, seg_end: datetime, status: str, day_totals: dict):
    """Attribute the [seg_start, seg_end) interval to `status`, splitting
    across midnight so each calendar day only gets the seconds that
    actually fall inside it."""
    if seg_end <= seg_start:
        return
    cursor = seg_start
    while cursor < seg_end:
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
        chunk_end = min(next_midnight, seg_end)
        seconds = (chunk_end - cursor).total_seconds()
        bucket = day_totals.setdefault(cursor.date(), {"active": 0.0, "standby": 0.0, "off": 0.0})
        bucket[status] += seconds
        cursor = chunk_end


def _compute_day_totals(rows, range_start: datetime, range_end: datetime) -> dict:
    """rows: iterable of (data_time, machine_status) ordered by data_time."""
    day_totals: dict[date, dict] = {}
    previous_time = range_start
    # Nothing is known before the first sample in range -- treat it as off.
    previous_status = "off"

    for data_time, machine_status in rows:
        if data_time is None or data_time < range_start:
            continue

        gap = (data_time - previous_time).total_seconds()
        if previous_status == "off" or gap <= OFFLINE_GAP_SECONDS:
            _split_into_days(previous_time, data_time, previous_status, day_totals)
        else:
            # Long silence after a known status: assume it went offline
            # right after the last sample rather than staying in that status.
            _split_into_days(previous_time, data_time, "off", day_totals)

        previous_time = data_time
        previous_status = (
            "active" if machine_status is not None and int(machine_status) == 1 else "standby"
        )

    gap = (range_end - previous_time).total_seconds()
    if previous_status == "off" or gap <= OFFLINE_GAP_SECONDS:
        _split_into_days(previous_time, range_end, previous_status, day_totals)
    else:
        _split_into_days(previous_time, range_end, "off", day_totals)

    return day_totals


def _fill_missing_days(day_totals: dict, range_start: date, range_end: date, now: datetime):
    """Safety net: make sure every day in range sums to its full expected
    duration (rounding, or a day with zero rows some other way)."""
    day = range_start
    while day <= range_end:
        bucket = day_totals.setdefault(day, {"active": 0.0, "standby": 0.0, "off": 0.0})
        day_start = datetime.combine(day, datetime.min.time())
        day_end = min(day_start + timedelta(days=1), now)
        expected_total = max(0.0, (day_end - day_start).total_seconds())
        actual_total = bucket["active"] + bucket["standby"] + bucket["off"]
        if actual_total < expected_total - 1:
            bucket["off"] += expected_total - actual_total
        day += timedelta(days=1)


def _bucket_key(day: date, granularity: str):
    if granularity == "day":
        return day, day.strftime("%m-%d")
    if granularity == "week":
        monday = day - timedelta(days=day.weekday())
        return monday, f"{monday.strftime('%m-%d')} 周"
    return date(day.year, day.month, 1), f"{day.year}-{day.month:02d}"


def _roll_up(day_totals: dict, granularity: str, range_start: date, range_end: date, periods: int):
    grouped = OrderedDict()
    day = range_start
    while day <= range_end:
        key, label = _bucket_key(day, granularity)
        bucket = grouped.setdefault(key, {"label": label, "active": 0.0, "standby": 0.0, "off": 0.0})
        totals = day_totals.get(day, {"active": 0.0, "standby": 0.0, "off": 0.0})
        bucket["active"] += totals["active"]
        bucket["standby"] += totals["standby"]
        bucket["off"] += totals["off"]
        day += timedelta(days=1)

    result = []
    for key, bucket in list(grouped.items())[-periods:]:
        total = bucket["active"] + bucket["standby"] + bucket["off"]
        uptime_pct = round(bucket["active"] / total * 100, 1) if total > 0 else 0.0
        result.append(
            {
                "period_start": key.isoformat(),
                "label": bucket["label"],
                "active_seconds": round(bucket["active"]),
                "standby_seconds": round(bucket["standby"]),
                "off_seconds": round(bucket["off"]),
                "total_seconds": round(total),
                "uptime_pct": uptime_pct,
            }
        )
    return result


@router.get("/uptime/{device_id}")
def get_uptime(
    device_id: str,
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    periods: int | None = Query(None, ge=1),
    user: dict = Depends(require_user),
):
    del user
    periods = min(periods or DEFAULT_PERIODS[granularity], MAX_PERIODS[granularity])

    now = datetime.now().replace(microsecond=0)
    today = now.date()
    range_start_date = _range_start(granularity, periods, today)
    range_start_dt = datetime.combine(range_start_date, datetime.min.time())

    sql = """
        SELECT data_time, machine_status
        FROM dbo.vw_machine_realtime
        WHERE device_id = ? AND data_time >= ? AND data_time <= ?
        ORDER BY data_time
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, device_id, range_start_dt, now)
            rows = cursor.fetchall()
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    day_totals = _compute_day_totals(
        ((row.data_time, row.machine_status) for row in rows),
        range_start_dt,
        now,
    )
    _fill_missing_days(day_totals, range_start_date, today, now)
    buckets = _roll_up(day_totals, granularity, range_start_date, today, periods)

    return {"device_id": device_id, "granularity": granularity, "buckets": buckets}