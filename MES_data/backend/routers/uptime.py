"""Machine uptime / utilization statistics.

Uptime is derived from the historical stream of realtime samples in
dbo.vw_machine_realtime (the same view GET /api/realtime/{device_id} already
uses). Each sample carries `machine_status`; a machine reporting
machine_status == 2 is "active" (producing), any other reported value is
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

# machine_status code that means the machine is actively producing.
# Matches MACHINE_STATUS_LABELS (parameter_labels.py) and statusOf() in
# app.js, both of which treat 2 = 生产/production and 1 = 待机/standby.
ACTIVE_STATUS_CODE = 2

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


def _period_start(granularity: str, day: date) -> date:
    """Calendar start date of the bucket `day` falls into (mirrors _bucket_key)."""
    if granularity == "day":
        return day
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    return date(day.year, day.month, 1)


def _shift_period_start(granularity: str, period_start: date) -> date:
    """One granularity-step earlier -- calendar-correct, not just -N days."""
    if granularity == "day":
        return period_start - timedelta(days=1)
    if granularity == "week":
        return period_start - timedelta(weeks=1)
    total_months = period_start.year * 12 + (period_start.month - 1) - 1
    year, month = divmod(total_months, 12)
    return date(year, month + 1, 1)


def _comparable_previous_window(granularity: str, today: date, now: datetime) -> tuple[datetime, datetime]:
    """[start, end) for the previous period, clipped to the same elapsed
    duration as the current in-progress period -- e.g. at Wed 2pm this is
    'last Wednesday midnight -> 2pm', not the full previous day/week/month.
    Keeps the summary-card delta an apples-to-apples comparison instead of
    penalizing every in-progress period against a previous period that had
    a full 24h/7d/month to accumulate against."""
    current_start = datetime.combine(_period_start(granularity, today), datetime.min.time())
    elapsed = now - current_start
    previous_start = datetime.combine(_shift_period_start(granularity, current_start.date()), datetime.min.time())
    return previous_start, previous_start + elapsed


def _uptime_pct_for_range(cursor, device_ids: list[str], range_start: datetime, range_end: datetime) -> float | None:
    """Active-time % across `device_ids` for an arbitrary (non
    calendar-aligned) window -- used only as the comparable-previous
    baseline, since it doesn't reuse the pre-rolled-up buckets. None if
    the window is empty (e.g. before any period at that granularity)."""
    if range_end <= range_start or not device_ids:
        return None

    placeholders = ",".join("?" for _ in device_ids)
    cursor.execute(
        f"""
        SELECT device_id, data_time, machine_status
        FROM dbo.vw_machine_realtime
        WHERE device_id IN ({placeholders}) AND data_time >= ? AND data_time <= ?
        ORDER BY device_id, data_time
        """,
        *device_ids, range_start, range_end,
    )
    rows_by_device: dict[str, list] = {}
    for row in cursor.fetchall():
        rows_by_device.setdefault(row.device_id, []).append((row.data_time, row.machine_status))

    active = standby = off = 0.0
    for device_id in device_ids:
        totals = _compute_day_totals(rows_by_device.get(device_id, []), range_start, range_end)
        for bucket in totals.values():
            active += bucket["active"]
            standby += bucket["standby"]
            off += bucket["off"]

    total = active + standby + off
    return round(active / total * 100, 1) if total > 0 else None


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
            "active"
            if machine_status is not None and int(machine_status) == ACTIVE_STATUS_CODE
            else "standby"
        )

    gap = (range_end - previous_time).total_seconds()
    if previous_status == "off" or gap <= OFFLINE_GAP_SECONDS:
        _split_into_days(previous_time, range_end, previous_status, day_totals)
    else:
        _split_into_days(previous_time, range_end, "off", day_totals)

    return day_totals


def _compute_day_segments(prev_row, rows, day_start: datetime, day_end: datetime) -> list[dict]:
    """Like _compute_day_totals, but returns the actual ordered list of
    {start, end, status} segments for a single day instead of summed
    per-status seconds -- this is what powers the day drill-down timeline.
    Adjacent segments with the same status are merged into one block.
    """
    segments: list[dict] = []
    previous_time = day_start
    if prev_row is not None and prev_row.machine_status is not None:
        previous_status = "active" if int(prev_row.machine_status) == ACTIVE_STATUS_CODE else "standby"
    else:
        previous_status = "off"

    def add_segment(start: datetime, end: datetime, status: str):
        if end <= start:
            return
        if segments and segments[-1]["status"] == status:
            segments[-1]["end"] = end.isoformat()
        else:
            segments.append({"start": start.isoformat(), "end": end.isoformat(), "status": status})

    for data_time, machine_status in rows:
        if data_time is None:
            continue
        gap = (data_time - previous_time).total_seconds()
        status_for_gap = previous_status if (previous_status == "off" or gap <= OFFLINE_GAP_SECONDS) else "off"
        add_segment(previous_time, data_time, status_for_gap)
        previous_time = data_time
        previous_status = "active" if machine_status is not None and int(machine_status) == ACTIVE_STATUS_CODE else "standby"

    gap = (day_end - previous_time).total_seconds()
    status_for_gap = previous_status if (previous_status == "off" or gap <= OFFLINE_GAP_SECONDS) else "off"
    add_segment(previous_time, day_end, status_for_gap)

    return segments


@router.get("/uptime/{device_id}/day")
def get_uptime_day(
    device_id: str,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(require_user),
):
    del user
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from None

    day_start = datetime.combine(day, datetime.min.time())
    now = datetime.now().replace(microsecond=0)
    day_end = min(day_start + timedelta(days=1), now)
    if day_end <= day_start:
        raise HTTPException(status_code=400, detail="所选日期还没有开始")

    sql_prev = """
        SELECT TOP 1 data_time, machine_status
        FROM dbo.vw_machine_realtime
        WHERE device_id = ? AND data_time < ?
        ORDER BY data_time DESC
    """
    sql_day = """
        SELECT data_time, machine_status
        FROM dbo.vw_machine_realtime
        WHERE device_id = ? AND data_time >= ? AND data_time <= ?
        ORDER BY data_time
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql_prev, device_id, day_start)
            prev_row = cursor.fetchone()
            cursor.execute(sql_day, device_id, day_start, day_end)
            rows = cursor.fetchall()
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    segments = _compute_day_segments(prev_row, rows, day_start, day_end)
    return {
        "device_id": device_id,
        "date": day.isoformat(),
        "day_start": day_start.isoformat(),
        "day_end": day_end.isoformat(),
        "segments": segments,
    }





def _fill_missing_days(day_totals: dict, range_start: date, range_end: date, now: datetime, device_count: int = 1):
    """Safety net: make sure every day in range sums to its full expected
    duration (rounding, or a day with zero rows some other way). When
    device_count > 1 (combined-fleet totals), the expected duration for
    each day is multiplied accordingly."""
    day = range_start
    while day <= range_end:
        bucket = day_totals.setdefault(day, {"active": 0.0, "standby": 0.0, "off": 0.0})
        day_start = datetime.combine(day, datetime.min.time())
        day_end = min(day_start + timedelta(days=1), now)
        expected_total = max(0.0, (day_end - day_start).total_seconds()) * device_count
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

@router.get("/uptime-summary")
def get_uptime_summary(
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    periods: int | None = Query(None, ge=1),
    user: dict = Depends(require_user),
):
    """Fleet-wide uptime: same active/standby/off accounting as
    GET /api/uptime/{device_id}, summed across every known device so the
    standalone 利用率报表 overview can show one combined percentage/trend
    instead of requiring a single device to be selected."""
    del user
    periods = min(periods or DEFAULT_PERIODS[granularity], MAX_PERIODS[granularity])

    now = datetime.now().replace(microsecond=0)
    today = now.date()
    range_start_date = _range_start(granularity, periods, today)
    range_start_dt = datetime.combine(range_start_date, datetime.min.time())

    sql_devices = """
        SELECT DISTINCT device_id
        FROM dbo.mqtt_messages
        WHERE device_id IS NOT NULL AND device_id <> N''
    """
    sql_rows = """
        SELECT device_id, data_time, machine_status
        FROM dbo.vw_machine_realtime
        WHERE data_time >= ? AND data_time <= ?
        ORDER BY device_id, data_time
    """
    try:
        with closing(get_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql_devices)
            device_ids = [row.device_id for row in cursor.fetchall()]
            cursor.execute(sql_rows, range_start_dt, now)
            rows = cursor.fetchall()

            prev_start, prev_end = _comparable_previous_window(granularity, today, now)
            comparable_previous_pct = _uptime_pct_for_range(cursor, device_ids, prev_start, prev_end)
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    rows_by_device: dict[str, list] = {}
    for row in rows:
        rows_by_device.setdefault(row.device_id, []).append(row)

    combined_day_totals: dict[date, dict] = {}
    for device_id in device_ids:
        device_rows = rows_by_device.get(device_id, [])
        device_day_totals = _compute_day_totals(
            ((r.data_time, r.machine_status) for r in device_rows),
            range_start_dt,
            now,
        )
        for day, totals in device_day_totals.items():
            bucket = combined_day_totals.setdefault(day, {"active": 0.0, "standby": 0.0, "off": 0.0})
            bucket["active"] += totals["active"]
            bucket["standby"] += totals["standby"]
            bucket["off"] += totals["off"]

    device_count = len(device_ids)
    _fill_missing_days(combined_day_totals, range_start_date, today, now, device_count)
    buckets = _roll_up(combined_day_totals, granularity, range_start_date, today, periods)

    return {
        "granularity": granularity,
        "device_count": device_count,
        "buckets": buckets,
        "comparable_previous_pct": comparable_previous_pct,
    }

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

            prev_start, prev_end = _comparable_previous_window(granularity, today, now)
            comparable_previous_pct = _uptime_pct_for_range(cursor, [device_id], prev_start, prev_end)
    except pyodbc.Error as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    day_totals = _compute_day_totals(
        ((row.data_time, row.machine_status) for row in rows),
        range_start_dt,
        now,
    )
    _fill_missing_days(day_totals, range_start_date, today, now)
    buckets = _roll_up(day_totals, granularity, range_start_date, today, periods)

    return {
        "device_id": device_id,
        "granularity": granularity,
        "buckets": buckets,
        "comparable_previous_pct": comparable_previous_pct,
    }