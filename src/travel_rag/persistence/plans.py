from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, create_engine, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from travel_rag.domain.models import (
    PlanResponse,
    SavedPlanDetail,
    SavedPlanListResponse,
    SavedPlanSaveResponse,
    SavedPlanSummary,
)
from travel_rag.observability import log_event

LOGGER = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class SavedPlanRow(Base):
    __tablename__ = "saved_plans"

    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120), index=True)
    destination: Mapped[str] = mapped_column(String(50), index=True)
    days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SavedPlanRepository:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self.engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _summary(row: SavedPlanRow) -> SavedPlanSummary:
        return SavedPlanSummary(
            plan_id=row.plan_id,
            request_id=row.request_id,
            title=row.title,
            destination=row.destination,
            days=row.days,
            status=row.status,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @classmethod
    def _detail(cls, row: SavedPlanRow) -> SavedPlanDetail:
        return SavedPlanDetail(
            **cls._summary(row).model_dump(),
            plan=PlanResponse.model_validate_json(row.plan_json),
        )

    def save(self, plan: PlanResponse) -> SavedPlanSaveResponse:
        request_id = plan.research.request_id
        with self.session_factory() as session:
            existing = session.scalar(
                select(SavedPlanRow).where(SavedPlanRow.request_id == request_id)
            )
            if existing is not None:
                return SavedPlanSaveResponse(created=False, item=self._detail(existing))

            now = datetime.now(UTC)
            row = SavedPlanRow(
                plan_id=str(uuid4()),
                request_id=request_id,
                title=f"{plan.itinerary.destination}{plan.itinerary.days}日旅行方案",
                destination=plan.itinerary.destination,
                days=plan.itinerary.days,
                status="completed",
                version=1,
                plan_json=plan.model_dump_json(),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(SavedPlanRow).where(SavedPlanRow.request_id == request_id)
                )
                if existing is None:
                    raise
                return SavedPlanSaveResponse(created=False, item=self._detail(existing))

        log_event(
            LOGGER,
            "travel_plan_saved",
            plan_id=row.plan_id,
            request_id=row.request_id,
            destination=row.destination,
        )
        return SavedPlanSaveResponse(created=True, item=self._detail(row))

    def get(self, plan_id: str) -> SavedPlanDetail | None:
        with self.session_factory() as session:
            row = session.get(SavedPlanRow, plan_id)
            return self._detail(row) if row is not None else None

    def list(
        self,
        *,
        query: str = "",
        destination: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> SavedPlanListResponse:
        filters = [SavedPlanRow.status == "completed"]
        query_text = query.strip()
        if query_text:
            pattern = f"%{query_text}%"
            filters.append(
                or_(
                    SavedPlanRow.title.ilike(pattern),
                    SavedPlanRow.destination.ilike(pattern),
                    SavedPlanRow.request_id.ilike(pattern),
                )
            )
        if destination:
            filters.append(SavedPlanRow.destination == destination)

        with self.session_factory() as session:
            total = session.scalar(
                select(func.count()).select_from(SavedPlanRow).where(*filters)
            )
            rows = session.scalars(
                select(SavedPlanRow)
                .where(*filters)
                .order_by(SavedPlanRow.updated_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return SavedPlanListResponse(
                total=int(total or 0),
                offset=offset,
                limit=limit,
                items=[self._summary(row) for row in rows],
            )
