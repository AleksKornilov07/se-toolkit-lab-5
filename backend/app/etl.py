"""ETL pipeline: fetch data from the autochecker API and load it into the database."""

import httpx
from datetime import datetime

from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import settings
from app.models.item import ItemRecord
from app.models.learner import Learner
from app.models.interaction import InteractionLog

# ---------------------------------------------------------------------------
# Extract — fetch data from the autochecker API
# ---------------------------------------------------------------------------

async def fetch_items() -> list[dict]:
    """Fetch the lab/task catalog from the autochecker API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.autochecker_api_url}/api/items",
            auth=(settings.autochecker_email, settings.autochecker_password)
        )
        response.raise_for_status()
        return response.json()


async def fetch_logs(since: datetime | None = None) -> list[dict]:
    """Fetch check results from the autochecker API with pagination."""
    all_logs = []
    current_since = since
    limit = 500

    async with httpx.AsyncClient() as client:
        while True:
            params = {"limit": limit}
            if current_since:
                params["since"] = current_since.isoformat()

            response = await client.get(
                f"{settings.autochecker_api_url}/api/logs",
                params=params,
                auth=(settings.autochecker_email, settings.autochecker_password)
            )
            response.raise_for_status()
            data = response.json()

            logs = data.get("logs", [])
            all_logs.extend(logs)

            if not data.get("has_more") or not logs:
                break

            # Use the submitted_at of the last log as new since value
            last_log = logs[-1]
            current_since = datetime.fromisoformat(last_log["submitted_at"].replace("Z", "+00:00"))

    return all_logs


# ---------------------------------------------------------------------------
# Load — insert fetched data into the local database
# ---------------------------------------------------------------------------

async def load_items(items: list[dict], session: AsyncSession) -> int:
    """Load items (labs and tasks) into the database."""
    new_count = 0
    lab_map = {}

    # First pass: process labs
    for item in items:
        if item["type"] == "lab":
            # Check if lab already exists
            stmt = select(ItemRecord).where(
                ItemRecord.type == "lab",
                ItemRecord.title == item["title"]
            )
            result = await session.exec(stmt)
            lab = result.first()

            if not lab:
                lab = ItemRecord(
                    type="lab",
                    title=item["title"]
                )
                session.add(lab)
                await session.flush()
                new_count += 1

            # Store lab in map using short ID (e.g., "lab-01")
            lab_map[item["lab"]] = lab

    # Second pass: process tasks
    for item in items:
        if item["type"] == "task":
            parent_lab = lab_map.get(item["lab"])
            if not parent_lab:
                continue  # Skip tasks without parent lab

            # Check if task already exists
            stmt = select(ItemRecord).where(
                ItemRecord.type == "task",
                ItemRecord.title == item["title"],
                ItemRecord.parent_id == parent_lab.id
            )
            result = await session.exec(stmt)
            task = result.first()

            if not task:
                task = ItemRecord(
                    type="task",
                    title=item["title"],
                    parent_id=parent_lab.id
                )
                session.add(task)
                await session.flush()
                new_count += 1

    await session.commit()
    return new_count


async def load_logs(
    logs: list[dict], items_catalog: list[dict], session: AsyncSession
) -> int:
    """Load interaction logs into the database."""
    new_count = 0

    # Build lookup from (lab, task) to title
    title_lookup = {}
    for item in items_catalog:
        if item["type"] == "lab":
            title_lookup[(item["lab"], None)] = item["title"]
        else:  # task
            title_lookup[(item["lab"], item["task"])] = item["title"]

    for log in logs:
        # Find or create learner
        stmt = select(Learner).where(Learner.external_id == log["student_id"])
        result = await session.exec(stmt)
        learner = result.first()

        if not learner:
            learner = Learner(
                external_id=log["student_id"],
                student_group=log.get("group", "")
            )
            session.add(learner)
            await session.flush()

        # Find item by title
        key = (log["lab"], log.get("task"))
        title = title_lookup.get(key)
        if not title:
            continue  # Skip if no matching item

        stmt = select(ItemRecord).where(ItemRecord.title == title)
        result = await session.exec(stmt)
        item = result.first()
        if not item:
            continue

        # Check if interaction already exists (idempotent)
        stmt = select(InteractionLog).where(InteractionLog.external_id == int(log["id"]))
        result = await session.exec(stmt)
        if result.first():
            continue

        # Create interaction
        interaction = InteractionLog(
            external_id=int(log["id"]),
            learner_id=learner.id,
            item_id=item.id,
            kind="attempt",
            score=log["score"],
            checks_passed=log["passed"],
            checks_total=log["total"],
            created_at=datetime.fromisoformat(log["submitted_at"].replace("Z", "+00:00"))
        )
        session.add(interaction)
        new_count += 1

    await session.commit()
    return new_count


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def sync(session: AsyncSession) -> dict:
    """Run the full ETL pipeline."""
    # Step 1: Fetch and load items
    items_data = await fetch_items()
    new_items = await load_items(items_data, session)

    # Step 2: Get last sync timestamp
    stmt = select(InteractionLog.created_at).order_by(InteractionLog.created_at.desc()).limit(1)
    result = await session.exec(stmt)
    last_log = result.first()
    since = last_log if last_log else None

    # Step 3: Fetch and load logs
    logs_data = await fetch_logs(since)
    new_logs = await load_logs(logs_data, items_data, session)

    # Step 4: Get total count
    stmt = select(func.count()).select_from(InteractionLog)
    result = await session.exec(stmt)
    total = result.one()

    return {
        "new_records": new_logs,
        "total_records": total
    }
