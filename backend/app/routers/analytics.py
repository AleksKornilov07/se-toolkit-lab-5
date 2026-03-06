"""Analytics endpoints for course performance data."""

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, func

from app.database import get_session
from app.models.item import ItemRecord
from app.models.interaction import InteractionLog
from app.models.learner import Learner

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _lab_title_from_param(lab: str) -> str:
    """Convert lab parameter (e.g. 'lab-04') to title format (e.g. 'Lab 04')."""
    if lab.startswith("lab-"):
        return "Lab " + lab[4:]
    return lab


@router.get("/scores")
async def get_scores_histogram(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-04'"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return score distribution across four buckets."""
    lab_title = _lab_title_from_param(lab)
    lab_stmt = select(ItemRecord).where(ItemRecord.title.ilike(f"%{lab_title}%"))
    lab_result = await session.exec(lab_stmt)
    lab_item = lab_result.first()

    if not lab_item:
        return [{"bucket": b, "count": 0} for b in ("0-25", "26-50", "51-75", "76-100")]

    tasks_stmt = select(ItemRecord.id).where(ItemRecord.parent_id == lab_item.id)
    tasks_result = await session.exec(tasks_stmt)
    task_ids = tasks_result.all()

    if not task_ids:
        return [{"bucket": b, "count": 0} for b in ("0-25", "26-50", "51-75", "76-100")]

    # Получаем все оценки для заданий
    scores_stmt = select(InteractionLog.score).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.score.is_not(None)
    )
    scores_result = await session.exec(scores_stmt)
    scores = scores_result.all()

    buckets = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for score in scores:
        if score <= 25:
            buckets["0-25"] += 1
        elif score <= 50:
            buckets["26-50"] += 1
        elif score <= 75:
            buckets["51-75"] += 1
        else:
            buckets["76-100"] += 1

    return [{"bucket": k, "count": v} for k, v in buckets.items()]


@router.get("/pass-rates")
async def get_pass_rates(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-04'"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return per-task average scores and attempt counts."""
    lab_title = _lab_title_from_param(lab)
    lab_stmt = select(ItemRecord).where(ItemRecord.title.ilike(f"%{lab_title}%"))
    lab_result = await session.exec(lab_stmt)
    lab_item = lab_result.first()

    if not lab_item:
        return []

    tasks_stmt = select(ItemRecord).where(ItemRecord.parent_id == lab_item.id).order_by(ItemRecord.title)
    tasks_result = await session.exec(tasks_stmt)
    tasks = tasks_result.all()

    result = []
    for task in tasks:
        agg_stmt = select(
            func.avg(InteractionLog.score),
            func.count(InteractionLog.id)
        ).where(
            InteractionLog.item_id == task.id,
            InteractionLog.score.is_not(None)
        )
        agg = await session.exec(agg_stmt)
        avg_score, attempts = agg.one()
        result.append({
            "task": task.title,
            "avg_score": float(avg_score) if avg_score is not None else 0.0,
            "attempts": attempts,
        })
    return result


@router.get("/timeline")
async def get_timeline(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-04'"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return submissions per day for the given lab."""
    lab_title = _lab_title_from_param(lab)
    lab_stmt = select(ItemRecord).where(ItemRecord.title.ilike(f"%{lab_title}%"))
    lab_result = await session.exec(lab_stmt)
    lab_item = lab_result.first()

    if not lab_item:
        return []

    tasks_stmt = select(ItemRecord.id).where(ItemRecord.parent_id == lab_item.id)
    tasks_result = await session.exec(tasks_stmt)
    task_ids = tasks_result.all()

    if not task_ids:
        return []

    timeline_stmt = select(
        func.date(InteractionLog.created_at).label("date"),
        func.count().label("submissions")
    ).where(
        InteractionLog.item_id.in_(task_ids)
    ).group_by(
        func.date(InteractionLog.created_at)
    ).order_by(
        func.date(InteractionLog.created_at)
    )
    timeline_result = await session.exec(timeline_stmt)
    rows = timeline_result.all()
    return [{"date": str(r.date), "submissions": r.submissions} for r in rows]


@router.get("/groups")
async def get_groups(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-04'"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return per-group average scores and student counts."""
    lab_title = _lab_title_from_param(lab)
    lab_stmt = select(ItemRecord).where(ItemRecord.title.ilike(f"%{lab_title}%"))
    lab_result = await session.exec(lab_stmt)
    lab_item = lab_result.first()

    if not lab_item:
        return []

    tasks_stmt = select(ItemRecord.id).where(ItemRecord.parent_id == lab_item.id)
    tasks_result = await session.exec(tasks_stmt)
    task_ids = tasks_result.all()

    if not task_ids:
        return []

    groups_stmt = select(
        Learner.student_group.label("group"),
        func.avg(InteractionLog.score).label("avg_score"),
        func.count(Learner.id.distinct()).label("students")
    ).join(
        InteractionLog, InteractionLog.learner_id == Learner.id
    ).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.score.is_not(None)
    ).group_by(
        Learner.student_group
    ).order_by(
        Learner.student_group
    )
    groups_result = await session.exec(groups_stmt)
    rows = groups_result.all()
    return [
        {
            "group": r.group,
            "avg_score": float(r.avg_score) if r.avg_score is not None else 0.0,
            "students": r.students,
        }
        for r in rows
    ]
