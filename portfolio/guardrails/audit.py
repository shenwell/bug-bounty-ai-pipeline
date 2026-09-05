"""Audit trail — no-op stub (portfolio CLI does not require SQLAlchemy)."""

from __future__ import annotations

from portfolio.common.config import AppConfig
from portfolio.common.models import AuditEvent


class AuditTrail:
    def __init__(self, config: AppConfig):
        self._config = config

    def init_schema(self) -> None:
        return None

    def log(
        self,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            input_data=input_data or {},
            output_data=output_data or {},
        )

    def query(self, entity_id: str | None = None, limit: int = 100) -> list[AuditEvent]:
        return []
