"""数据源健康状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceHealth:
    healthy: bool = True
    fail_count: int = 0
    last_error: str | None = None
    last_check: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "fail_count": self.fail_count,
            "last_error": self.last_error,
            "last_check": self.last_check.isoformat() if self.last_check else None,
        }


@dataclass
class SourceHealthRegistry:
    """轻量健康登记表，供新分层 provider/service 复用。"""

    fail_threshold: int = 3
    sources: dict[str, SourceHealth] = field(default_factory=dict)

    def mark_success(self, source: str) -> None:
        self.sources[source] = SourceHealth(healthy=True, fail_count=0, last_check=datetime.now())

    def mark_failure(self, source: str, error: Exception | str) -> None:
        current = self.sources.get(source, SourceHealth())
        fail_count = current.fail_count + 1
        self.sources[source] = SourceHealth(
            healthy=fail_count < self.fail_threshold,
            fail_count=fail_count,
            last_error=str(error),
            last_check=datetime.now(),
        )

    def snapshot(self) -> dict[str, dict]:
        return {source: health.to_dict() for source, health in self.sources.items()}

