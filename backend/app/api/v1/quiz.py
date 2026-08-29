"""Quiz grading API: stream LLM grading feedback for a student's answer.

For fill-in-the-blank / short-answer questions (where a simple string compare
is unreliable), the frontend submits the student's answer here; the LLM
judges correctness and streams a concise explanation. Multiple-choice keeps
its client-side letter compare (deterministic, no LLM round-trip needed).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.llm_async import get_llm
from app.core.quiz_attempts import record_quiz_attempt
from app.core.quiz_recent import list_recent_questions, record_recent_verdict
from app.identity.deps import resolve_student_id
from app.agents.student_model import is_enabled as student_model_enabled
from app.agents.assessment import (AssessmentContext, Question,
                                   get_assessment_manager, grade_open_prompt,
                                   is_enabled as assessment_enabled,
                                   parse_grade, evaluate_mc)

router = APIRouter(prefix="/quiz", tags=["quiz"])


def _write_back_answer(session_id: str, *, stem: str, verdict: str,
                       student_answer: str) -> None:
    """Attach the graded result to the matching question in the session's
    quiz_history, so the NEXT chat turn sees what the student answered.

    Card interactions (MC reveal / open-answer grading) happen outside the
    chat stream; without this write-back the model has zero visibility into
    them ("我这边没有收到你的作答"). Matches by stem prefix within the newest
    quiz set first. Never raises.
    """
    try:
        if not session_id or not verdict or verdict == "unknown":
            return
        from app.core.session import load_session, save_session
        session = load_session(session_id)
        if session is None:
            return
        stem_key = (stem or "").strip()[:60]
        if not stem_key:
            return
        for qh in reversed(session.quiz_history or []):
            if not isinstance(qh, dict):
                continue
            for q in (qh.get("questions") or []):
                if not isinstance(q, dict):
                    continue
                if str(q.get("stem", "")).strip()[:60] != stem_key:
                    continue
                result = {"verdict": verdict,
                          "student_answer": (student_answer or "")[:200]}
                q["result"] = result
                # Also sync the result into the persisted assistant message's
                # tool payload, so a reloaded chat restores the card's
                # answered state (locked) instead of allowing a second answer.
                for msg in reversed(session.messages or []):
                    if not isinstance(msg, dict) or msg.get("role") != "assistant":
                        continue
                    for tc in (msg.get("toolCalls") or []):
                        data = tc.get("result", {}).get("data") \
                            if isinstance(tc, dict) and isinstance(tc.get("result"), dict) else None
                        for mq in ((data or {}).get("questions") or []):
                            if isinstance(mq, dict) and \
                                    str(mq.get("stem", "")).strip()[:60] == stem_key:
                                mq["result"] = dict(result)
                from app.core.session_learning_card import (SessionLearningCard,
                                                             reconcile_quiz_history)
                card = SessionLearningCard.from_dict(session.context_card)
                reconcile_quiz_history(card, session.quiz_history or [])
                session.context_card = card.to_dict()
                save_session(session)
                # 同步回填跨会话「最近习题」库的判分状态
                record_recent_verdict(
                    session_id, getattr(session, "student_id", "") or "",
                    stem=stem, verdict=verdict, student_answer=student_answer)
                return
    except Exception:
        pass


class GradeRequest(BaseModel):
    stem: str = Field(..., description="题干")
    q_type: str = Field("short_answer", description="题型: fill_blank | short_answer")
    student_answer: str = Field(..., min_length=1, description="学生作答")
    correct_answer: str = Field(..., description="参考答案")
    explanation: str = Field("", description="参考解析（可选，辅助判断）")
    knowledge_point: str = Field("", description="对应知识点")
    grade: str = Field("本科", description="学段")
    session_id: str = Field("", description="会话 id（据此记录做题结果更新掌握度）")
    subject: str = Field("", description="学科，可选")
    difficulty: int = Field(0, description="题目难度 1-5（M4 评分上下文，可选）")
    record: bool = Field(True, description="是否写入掌握度/作答记录；MC 点评等只读调用传 false")


@router.post("/grade")
async def grade_answer(req: GradeRequest,
                       student_id: str = Depends(resolve_student_id)):
    llm = get_llm()
    # M4: three-level prompt ([对]/[部分对]/[错]) from the assessment engine.
    prompt = grade_open_prompt(
        stem=req.stem, q_type=req.q_type, correct_answer=req.correct_answer,
        explanation=req.explanation, student_answer=req.student_answer,
        grade=req.grade,
    )

    async def event_stream():
        full = ""
        try:
            async for ev in llm.stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=400,
            ):
                if ev["kind"] == "answer":
                    full += ev["delta"]
                    yield f"event: delta\ndata: {json.dumps({'content': ev['delta']}, ensure_ascii=False)}\n\n"
                elif ev["kind"] == "retry":
                    yield f"event: retry\ndata: {json.dumps({'attempt': ev.get('attempt'), 'reason': ev.get('reason')}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return
        # M4: route the streamed grade through the assessment engine for a
        # three-level parse (score / concept_status / mistake_type) and a
        # single closed-loop writeback to the Student Model. Backward
        # compatible: old frontends read verdict/feedback/full only.
        question = Question(
            concept=req.knowledge_point, q_type=req.q_type, stem=req.stem,
            answer=req.correct_answer, explanation=req.explanation,
            difficulty=max(1, min(5, int(req.difficulty or 3))),
        )
        ctx = AssessmentContext(concept=req.knowledge_point, subject=req.subject,
                                grade=req.grade, skill_id="")
        result = None
        if req.record and assessment_enabled():
            try:
                result = await get_assessment_manager().evaluate_and_record(
                    question, req.student_answer, ctx, raw_grade=full,
                    student_id=student_id)
            except Exception:
                result = None
        # fall back to the legacy inline parse if the engine is off / failed,
        # so grading never regresses to "no verdict".
        if result is not None and result.verdict != "unknown":
            verdict = result.verdict
            body = result.feedback
            done = {"verdict": verdict, "feedback": body, "full": full,
                    "score": result.score, "concept_status": result.concept_status}
        else:
            verdict = None
            stripped = full.lstrip()
            if stripped.startswith("[对]"):
                verdict = "correct"
            elif stripped.startswith("[错]"):
                verdict = "wrong"
            elif stripped.startswith("[部分对]"):
                verdict = "partial"
            body = (stripped[3:].lstrip() if verdict in ("correct", "wrong")
                    else stripped[5:].lstrip() if verdict == "partial" else full)
            if (req.record and verdict and req.session_id
                    and student_model_enabled() and req.knowledge_point):
                try:
                    from app.agents.student_model import record_quiz_result
                    record_quiz_result(
                        concept=req.knowledge_point,
                        correct=(verdict == "correct"),
                        session_id=req.session_id,
                        knowledge_point=req.knowledge_point,
                        subject=req.subject,
                        note=(body[:60] if verdict != "correct" else ""),
                        student_id=student_id,
                    )
                except Exception:
                    pass
            done = {"verdict": verdict, "feedback": body, "full": full}
        if req.record:
            _write_back_answer(req.session_id, stem=req.stem, verdict=verdict or "",
                               student_answer=req.student_answer)
            record_quiz_attempt(
                req.session_id, stem=req.stem, verdict=verdict or "",
                student_answer=req.student_answer, concept=req.knowledge_point,
                subject=req.subject, student_id=student_id,
                correct=(verdict == "correct"), note=(body or "")[:60])
        yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


class RecordRequest(BaseModel):
    """Report a (deterministically graded) multiple-choice result back so it
    feeds the Student Model mastery loop -- closes the section-14.14 gap where
    MC was graded client-side and never recorded."""
    stem: str = Field("", description="题干")
    q_type: str = Field("multiple_choice", description="题型")
    student_answer: str = Field(..., description="学生选择的选项字母")
    correct_answer: str = Field(..., description="正确选项字母")
    options: dict[str, str] = Field(default_factory=dict, description="选项（可选，辅助上下文）")
    explanation: str = Field("", description="参考解析")
    knowledge_point: str = Field("", description="对应知识点")
    grade: str = Field("本科", description="学段")
    session_id: str = Field("", description="会话 id")
    subject: str = Field("", description="学科")
    difficulty: int = Field(3, description="题目难度 1-5")


@router.post("/record")
async def record_answer(req: RecordRequest,
                        student_id: str = Depends(resolve_student_id)):
    """Record a graded answer (MC) into the Student Model via the assessment
    engine's single closed-loop point. Returns the structured result so the
    frontend can show score / concept_status if it wants to."""
    question = Question(
        concept=req.knowledge_point, q_type=req.q_type or "multiple_choice",
        stem=req.stem, answer=req.correct_answer, explanation=req.explanation,
        options=dict(req.options or {}),
        difficulty=max(1, min(5, int(req.difficulty or 3))),
    )
    ctx = AssessmentContext(concept=req.knowledge_point, subject=req.subject,
                            grade=req.grade)
    def _finalize(verdict: str) -> None:
        _write_back_answer(req.session_id, stem=req.stem, verdict=verdict,
                           student_answer=req.student_answer)
        record_quiz_attempt(
            req.session_id, stem=req.stem, verdict=verdict,
            student_answer=req.student_answer, concept=req.knowledge_point,
            subject=req.subject, student_id=student_id,
            correct=(verdict == "correct"))

    if not assessment_enabled():
        result = evaluate_mc(question, req.student_answer)
        _finalize(result.verdict)
        return {"status": "disabled",
                "result": result.to_dict()}
    try:
        result = await get_assessment_manager().evaluate_and_record(
            question, req.student_answer, ctx, student_id=student_id)
        _finalize(result.verdict)
        return {"status": "ok", "result": result.to_dict()}
    except Exception as e:
        result = evaluate_mc(question, req.student_answer)
        _finalize(result.verdict)
        return {"status": "error", "message": str(e),
                "result": result.to_dict()}


@router.get("/recent")
async def recent_questions(student_id: str = Depends(resolve_student_id)) -> dict:
    """跨会话「最近习题」列表（新→旧，每学生上限 100 道）。

    测评中心分页展示用：出题时快照入库，答题卡判分后回填 verdict。
    """
    return {"status": "ok", "questions": list_recent_questions(student_id)}
