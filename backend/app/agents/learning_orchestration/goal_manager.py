"""Goal Manager: long-term learning goal management (M9).

Owns the top of the plan hierarchy: the student sets a goal (exam date /
ability target / interest), and the weekly planner lays it out into weeks of
action-level tasks. Progress is DERIVED read-only from M2 mastery over the
planned concepts -- M9 owns the plan *structure*, never the mastery values.

Distinct from M2 StudentProfile.goals (a free-text list of stated intents
collected passively from conversation). LearningGoal here is the structured,
scheduled object that drives weekly planning.
"""
from __future__ import annotations

import time
from typing import Any

from .schema import GoalType, LearningGoal, OrchestrationState


def set_goal(state: OrchestrationState, *, title: str, description: str = "",
             goal_type: str = "ability", subjects: list[str] | None = None,
             deadline: float = 0.0,
             target_concept_ids: list[str] | None = None) -> None:
    """Set (or replace) the student's long-term learning goal.

    This does NOT auto-generate the plan -- that comes from the weekly
    planner (which needs the M5 knowledge graph to order concepts). The goal
    is just the top-level intent + deadline. target_concept_ids optionally
    binds the goal to specific graph concepts (prerequisite-closure analysis).
    """
    state.goal = LearningGoal(
        title=title.strip(),
        description=description.strip(),
        goal_type=GoalType.from_value(goal_type),
        subjects=list(subjects or []),
        target_concept_ids=[c for c in (target_concept_ids or []) if str(c).strip()],
        deadline=float(deadline),
    )
    state.goal.updated_at = time.time()


def overall_progress(state: OrchestrationState,
                     mastery_view: dict[str, Any]) -> float:
    """A 0..1 progress score across the weekly plan, read-only over M2 mastery.

    The fraction of planned concepts whose mastery reached their planned
    target. Returns 0 when there is no plan. (Milestone-based before the
    plan-hierarchy rebuild; now computed over weekly_plan concepts.)
    """
    total = 0
    mastered = 0
    for w in state.weekly_plan:
        for pc in w.concepts:
            total += 1
            rec = mastery_view.get(pc.concept_id) or {}
            p = float(rec.get("p_known", 0)) if isinstance(rec, dict) else 0.0
            if p >= pc.planned_mastery:
                mastered += 1
    if not total:
        return 0.0
    return round(mastered / total, 3)
