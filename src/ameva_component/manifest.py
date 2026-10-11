"""
ameva_component.manifest
AMEVA Component Protocol v1 — Model Manifest 파싱 및 ModelState 추적

핵심 원칙:
  파일 존재 ≠ Hash 검증됨 ≠ 엔진 호환성 확인됨 ≠ 활성화 가능
  failed 모델을 installed로 처리하면 안 됩니다.
  알 수 없는 Enum 값은 unknown으로 위장하지 않고 원문 보존.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ModelState(str, Enum):
    """
    모델 수명주기 상태.
    각 상태는 명시적 의미를 가지며 함부로 올려서는 안 됩니다.
      missing → downloading → verifying → installed → activating → active
                                                ↓             ↓
                                            inactive        failed
                                                              ↓
                                                        quarantined
    """
    MISSING      = "missing"
    DOWNLOADING  = "downloading"
    VERIFYING    = "verifying"
    INSTALLED    = "installed"
    ACTIVATING   = "activating"
    ACTIVE       = "active"
    INACTIVE     = "inactive"
    FAILED       = "failed"
    QUARANTINED  = "quarantined"

    @classmethod
    def from_str(cls, value: str) -> "ModelState":
        try:
            return cls(value)
        except ValueError:
            valid = [e.value for e in cls]
            raise ValueError(
                f"Unknown ModelState: '{value}'. Valid values: {valid}"
            )

    def is_usable(self) -> bool:
        """활성화 시도 가능한 상태인지 반환합니다."""
        return self in (ModelState.INSTALLED, ModelState.INACTIVE)

    def is_terminal_failure(self) -> bool:
        """수동 개입 없이는 복구 불가능한 실패 상태인지 반환합니다."""
        return self in (ModelState.FAILED, ModelState.QUARANTINED)


@dataclass(frozen=True)
class ModelFile:
    """모델을 구성하는 개별 파일."""
    filename: str
    bytes:    int     # 0 이하 금지
    sha256:   str     # 64자 hex 문자열

    def validate(self) -> None:
        if self.bytes <= 0:
            raise ValueError(f"ModelFile '{self.filename}': bytes must be > 0, got {self.bytes}")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.sha256):
            raise ValueError(
                f"ModelFile '{self.filename}': sha256 must be 64-char hex, got '{self.sha256[:16]}...'"
            )

    def verify_file(self, path: Path) -> bool:
        """실제 파일 SHA-256을 계산하여 선언값과 비교합니다. 일치하면 True."""
        if not path.exists():
            return False
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest().lower() == self.sha256.lower()


@dataclass(frozen=True)
class ModelManifest:
    """
    AMEVA Model Manifest v1.
    protocol: "ameva-model-manifest/1"

    termux-diffusion의 경우 model_id는 파일명이 아닌 Pipeline Manifest를 가리킵니다.
    (UNet + VAE + Text Encoder + Tokenizer + Scheduler Config)
    """
    protocol:              str                    # "ameva-model-manifest/1"
    model_id:              str
    component_type:        str
    format:                str                    # "gguf", "onnx", "safetensors", "pipeline", ...
    version:               str
    files:                 tuple[ModelFile, ...]
    capabilities:          tuple[str, ...]
    minimum_memory_mb:     int
    recommended_memory_mb: int
    accelerator:           dict                   # {"required": bool, "preferred": str}
    engine:                dict                   # {"minimum_version": str}

    def validate(self) -> None:
        from ameva_component.identity import PROTOCOL_MANIFEST, ALLOWED_CAPABILITIES
        from ameva_component.exceptions import InvalidManifest

        if self.protocol != PROTOCOL_MANIFEST:
            raise InvalidManifest(
                f"protocol must be '{PROTOCOL_MANIFEST}', got '{self.protocol}'"
            )
        if not self.model_id:
            raise InvalidManifest("model_id must not be empty")
        if self.minimum_memory_mb <= 0:
            raise InvalidManifest(f"minimum_memory_mb must be > 0, got {self.minimum_memory_mb}")
        if self.recommended_memory_mb < self.minimum_memory_mb:
            raise InvalidManifest(
                f"recommended_memory_mb ({self.recommended_memory_mb}) "
                f"must be >= minimum_memory_mb ({self.minimum_memory_mb})"
            )
        if not self.files:
            raise InvalidManifest("files must not be empty")
        for f in self.files:
            f.validate()

        # Capability 검증
        allowed = ALLOWED_CAPABILITIES.get(self.component_type, frozenset())
        for cap in self.capabilities:
            if allowed and cap not in allowed:
                raise InvalidManifest(
                    f"Capability '{cap}' not allowed for component_type '{self.component_type}'"
                )

    def to_dict(self) -> dict:
        return {
            "protocol":              self.protocol,
            "model_id":              self.model_id,
            "component_type":        self.component_type,
            "format":                self.format,
            "version":               self.version,
            "files":                 [
                {"filename": f.filename, "bytes": f.bytes, "sha256": f.sha256}
                for f in self.files
            ],
            "capabilities":          list(self.capabilities),
            "minimum_memory_mb":     self.minimum_memory_mb,
            "recommended_memory_mb": self.recommended_memory_mb,
            "accelerator":           self.accelerator,
            "engine":                self.engine,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelManifest":
        from ameva_component.exceptions import InvalidManifest

        required = {
            "protocol", "model_id", "component_type", "format",
            "version", "files", "capabilities",
            "minimum_memory_mb", "recommended_memory_mb",
            "accelerator", "engine",
        }
        missing = required - set(data.keys())
        if missing:
            raise InvalidManifest(f"Missing required manifest fields: {sorted(missing)}")

        files = tuple(
            ModelFile(
                filename=f["filename"],
                bytes=f["bytes"],
                sha256=f["sha256"],
            )
            for f in data["files"]
        )
        return cls(
            protocol=data["protocol"],
            model_id=data["model_id"],
            component_type=data["component_type"],
            format=data["format"],
            version=data["version"],
            files=files,
            capabilities=tuple(data["capabilities"]),
            minimum_memory_mb=int(data["minimum_memory_mb"]),
            recommended_memory_mb=int(data["recommended_memory_mb"]),
            accelerator=dict(data["accelerator"]),
            engine=dict(data["engine"]),
        )
