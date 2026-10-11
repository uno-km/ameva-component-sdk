"""
ameva_component.timestamps
AMEVA Component Protocol v1 — 3종 타임스탬프 생성

상태 응답에는 다음 세 가지가 모두 필요합니다:
  - updated_at:         ISO 8601 UTC (사람이 읽는 용도)
  - updated_at_unix_ms: 정수 Unix milliseconds (오케스트레이터 stale 판정)
  - monotonic_age_ms:   time.monotonic() 기반 경과시간 (벽시계 변경 방어)

벽시계(wall clock)는 NTP 보정이나 시스템 설정 변경으로 뒤로 이동할 수 있으므로
같은 프로세스 안에서의 경과시간 측정에는 monotonic clock을 사용합니다.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

# 프로세스 시작 시점의 monotonic 기준값 (모듈 임포트 시점에 고정)
_PROCESS_START_MONO: float = time.monotonic()
_PROCESS_START_WALL: float = time.time()


def now_timestamps(*, reference_mono: float | None = None) -> dict:
    """
    현재 시각의 3종 타임스탬프 딕셔너리를 반환합니다.

    Args:
        reference_mono: monotonic_age_ms 계산의 기준점.
                        None이면 프로세스 시작 시점을 기준으로 사용합니다.

    Returns:
        {
            "updated_at":         "2026-09-02T13:00:00.000000Z",
            "updated_at_unix_ms": 1788350400000,
            "monotonic_age_ms":   1450
        }
    """
    wall = time.time()
    mono = time.monotonic()
    ref = reference_mono if reference_mono is not None else _PROCESS_START_MONO

    dt = datetime.fromtimestamp(wall, tz=timezone.utc)
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    unix_ms = int(wall * 1000)
    age_ms = int((mono - ref) * 1000)

    return {
        "updated_at": iso,
        "updated_at_unix_ms": unix_ms,
        "monotonic_age_ms": age_ms,
    }


def process_start_timestamps() -> dict:
    """프로세스 시작 시점의 3종 타임스탬프를 반환합니다."""
    dt = datetime.fromtimestamp(_PROCESS_START_WALL, tz=timezone.utc)
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return {
        "updated_at": iso,
        "updated_at_unix_ms": int(_PROCESS_START_WALL * 1000),
        "monotonic_age_ms": 0,
    }


def is_stale(updated_at_unix_ms: int, threshold_ms: int = 30_000) -> bool:
    """
    상태 파일의 stale 여부를 판정합니다.

    오케스트레이터 기준:
        현재 시각 - updated_at_unix_ms > threshold_ms  →  stale

    마지막 정상 상태를 계속 정상으로 표시하면 안 되므로
    stale 판정 시 호출자는 ready=false로 처리해야 합니다.
    """
    now_ms = int(time.time() * 1000)
    return (now_ms - updated_at_unix_ms) > threshold_ms
