"""
ameva_component.registry
AMEVA Component Protocol v1 — Model Registry + Instance Registry

진실의 원천은 반드시 하나여야 합니다.
파일 존재만으로 installed/verified 처리 금지.
Model과 Instance를 동일하게 취급하지 않습니다.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ameva_component.manifest import ModelManifest, ModelState
from ameva_component.instance import InstanceStatus, InstanceState


from ameva_component.output import log_stderr


def _resolve_registry_dir(base: str) -> Path:
    p = Path.home() / ".local" / "share" / "ameva" / base
    p.mkdir(parents=True, exist_ok=True)
    return p


def _atomic_write(path: Path, data: Any) -> None:
    """임시 파일 작성 → flush → fsync → rename 순서로 원자적 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError as unlink_err:
            log_stderr(f"[registry] Warning: failed to unlink temporary file {tmp}: {unlink_err}")
        raise


class ModelRegistry:
    """
    모델 상태를 영속적으로 추적합니다.

    저장 위치: ~/.local/share/ameva/models/{component_id}/{model_id}/registry.json

    파일이 존재한다는 이유만으로 installed/verified 처리를 금지합니다.
    failed 모델을 installed로 반환하는 것을 금지합니다.
    """

    def __init__(self, component_id: str, registry_dir: Path | None = None) -> None:
        self.component_id = component_id
        self._base = (
            registry_dir
            if registry_dir is not None
            else _resolve_registry_dir(f"models/{component_id}")
        )

    def _path(self, model_id: str) -> Path:
        return self._base / model_id / "registry.json"

    def _manifest_path(self, model_id: str) -> Path:
        return self._base / model_id / "manifest.json"

    def get(self, model_id: str) -> dict | None:
        """모델 정보를 반환합니다. 없거나 손상 시 None."""
        p = self._path(model_id)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_all(self) -> list[dict]:
        """등록된 모든 모델의 레코드를 반환합니다."""
        result = []
        if not self._base.exists():
            return result
        for model_dir in sorted(self._base.iterdir()):
            if model_dir.is_dir():
                rec = self.get(model_dir.name)
                if rec is not None:
                    result.append(rec)
        return result

    def set_state(self, model_id: str, state: ModelState, *, last_error: str | None = None) -> None:
        """모델 상태를 갱신합니다."""
        rec = self.get(model_id) or {
            "model_id": model_id,
            "component_id": self.component_id,
            "files": [],
            "verified_at": None,
        }
        rec["state"] = state.value
        rec["last_error"] = last_error
        rec["updated_at_unix_ms"] = int(time.time() * 1000)
        _atomic_write(self._path(model_id), rec)

    def record_install(
        self,
        model_id: str,
        manifest: ModelManifest,
        verified_at: float,
    ) -> None:
        """
        설치 및 SHA-256 검증 완료 후 호출합니다.
        파일이 존재한다고 이 메서드를 호출해서는 안 됩니다.
        """
        rec = {
            "model_id":      model_id,
            "component_id":  self.component_id,
            "state":         ModelState.INSTALLED.value,
            "format":        manifest.format,
            "files": [
                {"filename": f.filename, "bytes": f.bytes, "sha256": f.sha256}
                for f in manifest.files
            ],
            "verified_at":      verified_at,
            "last_error":       None,
            "updated_at_unix_ms": int(time.time() * 1000),
        }
        _atomic_write(self._path(model_id), rec)
        # Manifest도 함께 저장
        _atomic_write(self._manifest_path(model_id), manifest.to_dict())

    def quarantine(self, model_id: str, reason: str) -> None:
        """모델을 격리 상태로 전환합니다. 수동 개입 없이 복구 불가."""
        self.set_state(model_id, ModelState.QUARANTINED, last_error=reason)

    def get_manifest(self, model_id: str) -> ModelManifest | None:
        """저장된 Manifest를 반환합니다."""
        p = self._manifest_path(model_id)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return ModelManifest.from_dict(data)
        except Exception:
            return None


class InstanceRegistry:
    """
    Instance 실행 상태를 영속적으로 추적합니다.

    저장 위치: ~/.local/share/ameva/instances/{component_id}/{instance_id}.json

    Model 하나에 Instance 여럿 가능 (v0.9.0 Pool 대비).
    Model과 Instance를 동일하게 취급하지 않습니다.
    active_jobs 측정 실패를 0으로 변환하지 않습니다.
    """

    def __init__(self, component_id: str, registry_dir: Path | None = None) -> None:
        self.component_id = component_id
        self._base = (
            registry_dir
            if registry_dir is not None
            else _resolve_registry_dir(f"instances/{component_id}")
        )

    def _path(self, instance_id: str) -> Path:
        return self._base / f"{instance_id}.json"

    def register(self, spec: InstanceStatus) -> None:
        """인스턴스를 등록합니다."""
        _atomic_write(self._path(spec.instance_id), spec.to_dict(expose_endpoint=False))

    def get(self, instance_id: str) -> InstanceStatus | None:
        """인스턴스 상태를 반환합니다. 없거나 손상 시 None."""
        p = self._path(instance_id)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return InstanceStatus.from_dict(data)
        except Exception:
            return None

    def list_all(self) -> list[InstanceStatus]:
        """등록된 모든 인스턴스를 반환합니다."""
        result = []
        if not self._base.exists():
            return result
        for p in sorted(self._base.glob("*.json")):
            try:
                with p.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                result.append(InstanceStatus.from_dict(data))
            except Exception:
                continue
        return result

    def update_state(
        self,
        instance_id: str,
        state: InstanceState,
        *,
        last_error: str | None = None,
    ) -> None:
        inst = self.get(instance_id)
        if inst is None:
            from ameva_component.exceptions import InstanceNotFound
            raise InstanceNotFound(instance_id)
        inst.state = state
        inst.last_error = last_error
        inst.last_heartbeat = time.time()
        _atomic_write(self._path(instance_id), inst.to_dict(expose_endpoint=False))

    def increment_jobs(self, instance_id: str) -> None:
        """Job 시작 시 호출합니다. active_jobs를 1 증가시킵니다."""
        inst = self.get(instance_id)
        if inst is None:
            return
        inst.active_jobs += 1
        inst.last_heartbeat = time.time()
        _atomic_write(self._path(instance_id), inst.to_dict(expose_endpoint=False))

    def decrement_jobs(self, instance_id: str) -> None:
        """Job 종료 시 호출합니다. active_jobs를 1 감소시킵니다 (음수 방지)."""
        inst = self.get(instance_id)
        if inst is None:
            return
        inst.active_jobs = max(0, inst.active_jobs - 1)
        inst.last_heartbeat = time.time()
        _atomic_write(self._path(instance_id), inst.to_dict(expose_endpoint=False))

    def update_heartbeat(self, instance_id: str) -> None:
        """Heartbeat 갱신. 10초 주기 호출."""
        inst = self.get(instance_id)
        if inst is None:
            return
        inst.last_heartbeat = time.time()
        _atomic_write(self._path(instance_id), inst.to_dict(expose_endpoint=False))

    def remove(self, instance_id: str) -> None:
        """인스턴스 레코드를 제거합니다. 없어도 예외 없음."""
        try:
            self._path(instance_id).unlink(missing_ok=True)
        except OSError as unlink_err:
            log_stderr(f"[registry] Warning: failed to unlink instance record {instance_id}: {unlink_err}")
