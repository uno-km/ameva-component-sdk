"""
ameva_component.exceptions
AMEVA Component Protocol v1 — 오류 계층 정의

AmevaError 하위 계층은 code(문자열)와 exit_code(정수)를 보유합니다.
측정 실패를 0 또는 정상 상태로 변환하는 것을 방지하기 위해
모든 예외는 명시적 ExitCode를 포함합니다.
"""
from __future__ import annotations
import re
from typing import Any

# ──────────────────────────────────────────────────────────────
# Redaction Constants & Functions
# ──────────────────────────────────────────────────────────────
_BEARER_RE = re.compile(r'(?i)\bbearer\s+[a-zA-Z0-9_\-\.~+/]+=*')
_AUTH_KEY_VAL_RE = re.compile(r'(?i)\b(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;\'\"]+)')
_URL_CRED_RE = re.compile(r'(https?://)[^:/@\s]+:[^@/\s]+@')
_INTERNAL_URL_RE = re.compile(r'https?://[a-zA-Z0-9_\.\-]+:\d+(?:/[^\s]*)?')
_POSIX_PATH_RE = re.compile(r'/(?:data|home|usr|etc|var|tmp|private|storage|proc|sys)/[a-zA-Z0-9_\.\-/]+')
_WIN_PATH_RE = re.compile(r'[a-zA-Z]:\\[a-zA-Z0-9_\.\-\\]+')
_PROMPT_CONTENT_RE = re.compile(r'(?i)\buser\s+prompt\s+content\b')


def redact_text(text: str) -> str:
    """민감한 비밀키, 토큰, 내부 URL, 절대 경로 및 프롬프트 내용을 마스킹합니다."""
    if not isinstance(text, str):
        return text
    s = text
    s = _BEARER_RE.sub("Bearer [REDACTED]", s)
    s = _AUTH_KEY_VAL_RE.sub(r"\1: [REDACTED]", s)
    s = _URL_CRED_RE.sub(r"\1[REDACTED]:[REDACTED]@", s)
    s = _INTERNAL_URL_RE.sub("[REDACTED_URL]", s)
    s = _POSIX_PATH_RE.sub("[REDACTED_PATH]", s)
    s = _WIN_PATH_RE.sub("[REDACTED_PATH]", s)
    s = _PROMPT_CONTENT_RE.sub("[REDACTED_PROMPT]", s)
    return s


def redact_details(val: Any) -> Any:
    """오류 상세 객체에서 민감한 정보를 재귀적으로 마스킹합니다."""
    if isinstance(val, str):
        return redact_text(val)
    elif isinstance(val, dict):
        res: dict[str, Any] = {}
        for k, v in val.items():
            k_str = str(k).lower()
            if any(sec in k_str for sec in ["secret", "password", "token", "auth", "api_key", "prompt", "bearer"]):
                res[k] = "[REDACTED]"
            else:
                res[k] = redact_details(v)
        return res
    elif isinstance(val, list):
        return [redact_details(item) for item in val]
    elif isinstance(val, tuple):
        return tuple(redact_details(item) for item in val)
    return val


class AmevaError(Exception):
    """모든 AMEVA 오류의 베이스 클래스."""

    code: str = "AMEVA_ERROR"
    exit_code: int = 70  # 기본: 내부 소프트웨어 오류

    def __init__(
        self,
        message: str,
        *,
        details: dict | None = None,
        public_message: str | None = None,
        internal_message: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.internal_message: str = internal_message or message
        self.public_message: str = public_message or message
        self.details: dict = details or {}
        self.cause: Exception | None = cause
        if cause is not None and not getattr(self, "__cause__", None):
            self.__cause__ = cause

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}
        if self.details:
            d["details"] = self.details
        return d

    def to_public_dict(self) -> dict:
        d: dict = {
            "code": self.code,
            "message": redact_text(self.public_message),
            "retryable": getattr(self, "retryable", False),
        }
        if self.details:
            d["details"] = redact_details(self.details)
        return d


class OperationNotSupported(AmevaError):
    """지원하지 않는 기능 호출 시 — 빈 성공 반환 금지."""
    code = "OPERATION_NOT_SUPPORTED"
    exit_code = 64

    def __init__(self, operation: str, component_id: str) -> None:
        msg = f"Operation '{operation}' is not supported by {component_id}"
        super().__init__(
            msg,
            details={"operation": operation, "component_id": component_id},
            public_message=msg,
            internal_message=msg,
        )
        self.operation = operation
        self.component_id = component_id

    def to_public_dict(self) -> dict:
        return {
            "code": self.code,
            "message": redact_text(self.public_message),
            "retryable": False,
            "details": redact_details(self.details),
        }


class ModelNotFound(AmevaError):
    """모델 ID가 Registry에 없을 때."""
    code = "MODEL_NOT_FOUND"
    exit_code = 65

    def __init__(self, model_id: str) -> None:
        super().__init__(f"Model '{model_id}' not found in registry")
        self.model_id = model_id


class ModelLoadFailed(AmevaError):
    """엔진이 모델 로드에 실패했을 때."""
    code = "MODEL_LOAD_FAILED"
    exit_code = 3

    def __init__(self, model_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to load model '{model_id}': {reason}",
            details={"model_id": model_id, "reason": reason},
        )
        self.model_id = model_id


class RollbackFailed(AmevaError):
    """Activate 실패 후 Rollback도 실패했을 때 — 성공으로 위장 금지."""
    code = "ROLLBACK_FAILED"
    exit_code = 70

    def __init__(self, model_id: str, reason: str) -> None:
        super().__init__(
            f"Rollback failed for model '{model_id}': {reason}",
            details={"model_id": model_id, "reason": reason},
        )
        self.model_id = model_id


class HashMismatch(AmevaError):
    """SHA-256 검증 실패 — 파일을 installed로 처리하면 안 됨."""
    code = "HASH_MISMATCH"
    exit_code = 65

    def __init__(self, filename: str, expected: str, actual: str) -> None:
        super().__init__(
            f"SHA-256 mismatch for '{filename}': expected {expected[:16]}... got {actual[:16]}...",
            details={"filename": filename, "expected": expected, "actual": actual},
        )
        self.filename = filename
        self.expected = expected
        self.actual = actual


class InsufficientDisk(AmevaError):
    """다운로드 전 디스크 여유 공간 부족."""
    code = "INSUFFICIENT_DISK"
    exit_code = 75

    def __init__(self, required_bytes: int, available_bytes: int) -> None:
        super().__init__(
            f"Insufficient disk space: need {required_bytes} bytes, have {available_bytes} bytes",
            details={"required_bytes": required_bytes, "available_bytes": available_bytes},
        )
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes


class LockTimeout(AmevaError):
    """Lock 획득 타임아웃 — Retry 가능 오류."""
    code = "LOCK_TIMEOUT"
    exit_code = 4

    def __init__(self, lock_name: str, timeout_s: float) -> None:
        super().__init__(
            f"Timed out waiting for lock '{lock_name}' after {timeout_s}s",
            details={"lock_name": lock_name, "timeout_s": timeout_s},
        )


class InvalidManifest(AmevaError):
    """Manifest 파싱 또는 검증 실패."""
    code = "INVALID_MANIFEST"
    exit_code = 65

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid manifest: {reason}")


class InstanceNotFound(AmevaError):
    """Instance ID가 Registry에 없을 때."""
    code = "INSTANCE_NOT_FOUND"
    exit_code = 65

    def __init__(self, instance_id: str) -> None:
        super().__init__(f"Instance '{instance_id}' not found in registry")
        self.instance_id = instance_id


class ActivationConflict(AmevaError):
    """이미 Activation 연산 진행 중일 때 동시 요청 거부."""
    code = "ACTIVATION_CONFLICT"
    exit_code = 4

    def __init__(self) -> None:
        super().__init__("An activation operation is already in progress")


class DrainTimeout(AmevaError):
    """Drain 대기 시간 초과."""
    code = "DRAIN_TIMEOUT"
    exit_code = 75

    def __init__(self, instance_id: str, timeout_s: float) -> None:
        super().__init__(
            f"Instance '{instance_id}' did not drain within {timeout_s}s",
            details={"instance_id": instance_id, "timeout_s": timeout_s},
        )


class InvalidProtocol(AmevaError):
    """알 수 없는 protocol 버전 — unknown으로 위장 금지, 원문 보존."""
    code = "INVALID_PROTOCOL"
    exit_code = 65

    def __init__(self, received: str, expected: str) -> None:
        super().__init__(
            f"Unsupported protocol: '{received}' (expected '{expected}')",
            details={"received": received, "expected": expected},
        )


class ComponentError(AmevaError):
    """ComponentControl 계층에서 발생하는 구조화 오류의 베이스 클래스.

    Adapter에서 ComponentControl 호출 결과를 잡을 때 사용합니다.
    retryable 속성으로 재시도 여부를 명시합니다.
    """
    code = "COMPONENT_ERROR"
    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        code: str = "COMPONENT_ERROR",
        retryable: bool = False,
        details: dict | None = None,
        public_message: str | None = None,
        internal_message: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            details=details,
            public_message=public_message or "Component operation failed",
            internal_message=internal_message or message,
            cause=cause,
        )
        self.code = code  # type: ignore[assignment]
        self.retryable = retryable

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["retryable"] = self.retryable
        d["public_message"] = self.public_message
        return d

    def to_public_dict(self) -> dict:
        return {
            "code": self.code,
            "message": redact_text(self.public_message),
            "retryable": self.retryable,
            "details": redact_details(self.details),
        }
