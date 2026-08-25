"""Schedule Engine: time-budget allocation + exam-driven priority (M9).

Given a ScheduleConfig (daily minutes, available days, exam dates) and a
habit signal (should the plan be more granular?), this module decides how
many tasks fit per day, how long each should be, and which concepts get
priority based on proximity to exam dates.

Pure functions, deterministic, zero LLM. The output is consumed by
task_executor when materialising the weekly plan into DailyTasks.
"""
from __future__ import annotations

import time
from typing import Any

from .schema import HabitStats, ScheduleConfig

_DAY_SECONDS = 24 * 3600
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# task granularity presets (minutes) -- granularize uses the smaller set
_GRANULAR_MINUTES = [10, 15, 15, 20]
_NORMAL_MINUTES = [15, 20, 25, 30]


def _weekday_key(ts: float) -> str:
    t = time.localtime(ts)
    return _WEEKDAYS[t.tm_wday]


def day_available(schedule: ScheduleConfig, day_ts: float) -> bool:
    """Whether the student studies on this weekday."""
    return _weekday_key(day_ts) in (schedule.available_days or _WEEKDAYS)


def slots_per_day(schedule: ScheduleConfig, habit: HabitStats | None,
                  *, granularize: bool | None = None) -> list[int]:
    """How many minutes-long slots fit in one study day.

    When granularize is True (or habit says so), uses shorter slots so the
    student gets more frequent, smaller tasks -- a behavioural adaptation for
    students struggling with consistency.
    """
    do_granular = granularize if granularize is not None else (
        habit is not None and _should_granularize_safe(habit))
    presets = _GRANULAR_MINUTES if do_granular else _NORMAL_MINUTES
    total = 0
    slots: list[int] = []
    for m in presets:
        if total + m <= schedule.daily_minutes:
            slots.append(m)
            total += m
        else:
            break
    return slots or [min(15, schedule.daily_minutes)]


def _should_granularize_safe(habit: HabitStats) -> bool:
    try:
        from .habit_tracker import should_granularize
        return should_granularize(habit)
    except Exception:
        return False


def exam_urgency(concept_id: str, schedule: ScheduleConfig, *,
                 now: float | None = None) -> float:
    """A 0..1 urgency score for a concept based on days-until-exam.

    1.0 = exam is today or past; 0.0 = no exam or >90 days away. Concepts
    with higher urgency get higher task priority.
    """
    now = now if now is not None else time.time()
    exam = schedule.exam_dates.get(concept_id, 0)
    if exam <= 0:
        return 0.0
    days_left = max(0, (exam - now) / _DAY_SECONDS)
    if days_left <= 0:
        return 1.0
    if days_left >= 90:
        return 0.0
    return round(1.0 - days_left / 90.0, 3)


def assign_priority(concept_id: str, difficulty: int, schedule: ScheduleConfig, *,
                    now: float | None = None) -> int:
    """Assign a 1(highest)..5(lowest) priority to a concept's tasks.

    Combines exam urgency (closer = higher priority) with difficulty (harder
    concepts that need more time get slightly higher priority). Pure function.
    """
    urgency = exam_urgency(concept_id, schedule, now=now)
    # base priority from difficulty: harder => higher priority (lower number)
    base = max(1, min(5, 6 - max(1, min(5, difficulty))))
    # shift toward 1 (higher priority) as urgency rises
    shifted = max(1, round(base - urgency * 2))
    return min(5, shifted)


def plan_week_dates(*, week_index: int, week_start: float | None = None,
                    schedule: ScheduleConfig) -> list[float]:
    """Return the epoch timestamps of available study days in a week.

    week_start is the Monday 00:00; if omitted, derived from now + week_index.
    Only days in schedule.available_days are returned.
    """
    now = week_start if week_start else time.time()
    # find the Monday of the current week
    t = time.localtime(now)
    monday = now - t.tm_wday * _DAY_SECONDS
    monday_midnight = monday - (t.tm_sec + t.tm_min * 60 + t.tm_hour * 3600)
    start = monday_midnight + week_index * 7 * _DAY_SECONDS
    days: list[float] = []
    for i in range(7):
        day_ts = start + i * _DAY_SECONDS
        if day_available(schedule, day_ts):
            days.append(day_ts)
    return days
