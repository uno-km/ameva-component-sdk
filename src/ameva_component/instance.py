"""
ameva_component.instance
AMEVA Component Protocol v1 — Instance 상태 모델

Model과 Instance를 동일하게 취급하지 않습니다.
Model 하나에 Instance 여럿 가능 (v0.9.0 Pool 대비).

Instance 표준 상태 (알 수 없는 값을 unknown으로 위장 금지):
  created  → starting → warming → hot ←→ busy
                                   ↓
                               draining → stopping → stopped / failed
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InstanceState(str, Enum):
    """
    Instance 수명주기 상태.
    알 수 없는 Enum 값은 unknown으로 위장하지 말고 원문과 오류를 보존합니다.
    """
    CREATED  = "created"
    STARTING = "starting"
    WARMING  = "warming"
    HOT      = "hot"
    BUSY     = "busy"
    DRAINING = "draining"
    STOPPING = "stopping"
    STOPPED  = "stopped"
    FAILED   = "failed"

    @classmethod
    def from_str(cls, value: str) -> "InstanceState":
        """
        문자열에서 InstanceState를 변환합니다.
        알 수 없는 값은 ValueError — unknown으로 위장 금지.
        """
        try:
            return cls(value)
        except ValueError:
            valid = [e.value for e in cls]
            raise ValueError(
                f"Unknown InstanceState: '{value}'. Valid values: {valid}"
            )


class ControlMode(str, Enum):
    """Instance 내부 연결 방식 우선순위."""
    IN_PROCESS   = "in-process"    # 1순위: 동일 프로세스 Python 제어
    UNIX_SOCKET  = "unix-socket"   # 2순위: Unix Domain Socket Worker
    SUBPROCESS   = "subprocess"    # 3순위: JSON Lines Subprocess
    REST         = "rest"          # 4순위: Localhost REST Server


@dataclass(slots=True)
class InstanceStatus:
    """
    Instance 실행 상태.
    외부 UI에는 endpoint를 기본 노출하지 않습니다.
    active_jobs 측정 실패를 0으로 변환하지 않습니다.
    """
    instance_id:      str
    component_id:     str
    model_id:         str
    state:            InstanceState
    active_jobs:      int
    queue_depth:      int
    max_concurrency:  int
    backend:          str                # "vulkan", "cpu", "onnx", ...
    started_at:       float              # Unix timestamp
    last_heartbeat:   float              # Unix timestamp
    last_error:       str | None
    control_mode:     ControlMode
    endpoint:         str | None = None  # 외부 UI에 기본 노출 금지

    def to_dict(self, *, expose_endpoint: bool = False) -> dict:
        d: dict = {
            "instance_id":     self.instance_id,
            "component_id":    self.component_id,
            "model_id":        self.model_id,
            "state":           self.state.value,
            "active_jobs":     self.active_jobs,
            "queue_depth":     self.queue_depth,
            "max_concurrency": self.max_concurrency,
            "backend":         self.backend,
            "started_at":      self.started_at,
            "last_heartbeat":  self.last_heartbeat,
            "last_error":      self.last_error,
            "control_mode":    self.control_mode.value,
        }
        # 외부 UI에는 기본적으로 endpoint를 노출하지 않음
        if expose_endpoint and self.endpoint:
            d["endpoint"] = self.endpoint
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InstanceStatus":
        """
        필수 필드 누락 시 오류.
        알 수 없는 추가 필드는 무시합니다.
        """
        required = {
            "instance_id", "component_id", "model_id", "state",
            "active_jobs", "queue_depth", "max_concurrency",
            "backend", "started_at", "last_heartbeat",
        }
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Missing required instance fields: {sorted(missing)}")

        return cls(
            instance_id=data["instance_id"],
            component_id=data["component_id"],
            model_id=data["model_id"],
            state=InstanceState.from_str(data["state"]),
            active_jobs=data["active_jobs"],
            queue_depth=data["queue_depth"],
            max_concurrency=data["max_concurrency"],
            backend=data["backend"],
            started_at=float(data["started_at"]),
            last_heartbeat=float(data["last_heartbeat"]),
            last_error=data.get("last_error"),
            control_mode=ControlMode(data.get("control_mode", ControlMode.IN_PROCESS.value)),
            endpoint=data.get("endpoint"),
        )
