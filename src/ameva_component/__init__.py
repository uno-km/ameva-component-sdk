"""
ameva_component
AMEVA Component Protocol v1 공개 API

사용 예:
    from ameva_component import ComponentControl, ComponentInfo
    from ameva_component import ComponentStateFile, ModelRegistry, InstanceRegistry
    from ameva_component import render_ok, render_error, log_stderr, ExitCode
    from ameva_component.exceptions import OperationNotSupported, ModelNotFound
"""
from ameva_component.control import ComponentControl
from ameva_component.exceptions import (
    AmevaError,
    ActivationConflict,
    ComponentError,
    DrainTimeout,
    HashMismatch,
    InsufficientDisk,
    InstanceNotFound,
    InvalidManifest,
    InvalidProtocol,
    LockTimeout,
    ModelLoadFailed,
    ModelNotFound,
    OperationNotSupported,
    RollbackFailed,
    redact_details,
    redact_text,
)
from ameva_component.identity import (
    ComponentInfo,
    ALLOWED_CAPABILITIES,
    PROTOCOL_COMPONENT,
    PROTOCOL_STATUS,
    PROTOCOL_MANIFEST,
    PROTOCOL_INSTANCE,
)
from ameva_component.instance import ControlMode, InstanceState, InstanceStatus
from ameva_component.installer import ModelInstaller
from ameva_component.locks import ActivationLock, ArtifactLock, InstanceLock, ModelLock
from ameva_component.manifest import ModelFile, ModelManifest, ModelState
from ameva_component.output import (
    ExitCode,
    exit_for_result,
    log_progress,
    log_stderr,
    render_error,
    render_from_exception,
    render_ok,
)
from ameva_component.registry import InstanceRegistry, ModelRegistry
from ameva_component.state import ComponentStateFile, resolve_state_dir
from ameva_component.timestamps import is_stale, now_timestamps, process_start_timestamps

__version__ = "0.1.1"

__all__ = [
    # 핵심 추상 클래스
    "ComponentControl",
    # 예외
    "AmevaError",
    "ActivationConflict",
    "ComponentError",
    "DrainTimeout",
    "HashMismatch",
    "InsufficientDisk",
    "InstanceNotFound",
    "InvalidManifest",
    "InvalidProtocol",
    "LockTimeout",
    "ModelLoadFailed",
    "ModelNotFound",
    "OperationNotSupported",
    "RollbackFailed",
    "redact_details",
    "redact_text",
    # 신원
    "ComponentInfo",
    "ALLOWED_CAPABILITIES",
    "PROTOCOL_COMPONENT",
    "PROTOCOL_STATUS",
    "PROTOCOL_MANIFEST",
    "PROTOCOL_INSTANCE",
    # Instance
    "ControlMode",
    "InstanceState",
    "InstanceStatus",
    # 설치
    "ModelInstaller",
    # Lock
    "ActivationLock",
    "ArtifactLock",
    "InstanceLock",
    "ModelLock",
    # Manifest
    "ModelFile",
    "ModelManifest",
    "ModelState",
    # 출력
    "ExitCode",
    "exit_for_result",
    "log_progress",
    "log_stderr",
    "render_error",
    "render_from_exception",
    "render_ok",
    # Registry
    "InstanceRegistry",
    "ModelRegistry",
    # 상태 파일
    "ComponentStateFile",
    "resolve_state_dir",
    # 타임스탬프
    "is_stale",
    "now_timestamps",
    "process_start_timestamps",
    # CLI 지원
    "build_protocol_subcommands",
    "dispatch_protocol",
    # Heartbeat
    "HeartbeatWriter",
]

from ameva_component.cli_support import build_protocol_subcommands, dispatch_protocol  # noqa: E402
from ameva_component.heartbeat import HeartbeatWriter  # noqa: E402
from ameva_component.adapter_base import BaseOrchestratorAdapter  # noqa: E402

__all__ += ["BaseOrchestratorAdapter"]
