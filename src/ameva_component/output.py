"""
ameva_component.output
AMEVA Component Protocol v1 — 표준 출력 포맷터

규칙:
  - stdout: --json 사용 시 JSON 문서 1개만 출력 (로그/진행상황 혼입 금지)
  - stderr: 모든 로그, 진행 상황, 다운로드 청크 번호, SHA-256 검증 메시지
  - 측정 실패를 0, 빈 배열, 정상 상태로 변환하는 렌더링 금지

Exit Code 체계 (의무 최소: 0, 2, 3, 64):
  0   정상 성공
  2   Degraded (기능 저하, 동작 가능)
  3   실행 실패
  4   일시적 Retry 가능 오류
  64  잘못된 명령 또는 인자 (OPERATION_NOT_SUPPORTED 포함)
  65  잘못된 데이터 또는 Manifest
  69  외부 서비스 이용 불가
  70  내부 소프트웨어 오류
  75  일시적 실패
  77  권한 부족
"""
from __future__ import annotations

import json
import sys


class ExitCode:
    OK         = 0
    DEGRADED   = 2
    FAIL       = 3
    RETRY      = 4
    BAD_ARGS   = 64
    BAD_DATA   = 65
    UNAVAIL    = 69
    INTERNAL   = 70
    TEMP_FAIL  = 75
    PERMISSION = 77


def render_ok(
    component_id: str,
    result: dict,
    *,
    protocol: str = "ameva-component-status/1",
) -> str:
    """
    성공 응답 JSON 문자열을 생성합니다.
    stdout 출력용 — 진행 상황/로그를 절대 포함하지 않습니다.
    """
    return json.dumps(
        {
            "protocol": protocol,
            "ok": True,
            "component_id": component_id,
            "result": result,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def render_error(
    component_id: str,
    code: str,
    message: str,
    *,
    details: dict | None = None,
    protocol: str = "ameva-component-status/1",
) -> str:
    """
    오류 응답 JSON 문자열을 생성합니다.
    지원하지 않는 기능의 경우 빈 성공으로 대체하지 않고 이 함수를 사용합니다.
    """
    error: dict = {"code": code, "message": message}
    if details:
        error.update(details)
    return json.dumps(
        {
            "protocol": protocol,
            "ok": False,
            "component_id": component_id,
            "error": error,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def render_from_exception(component_id: str, exc: Exception) -> tuple[str, int]:
    """
    AmevaError 또는 임의의 Exception으로부터 (json_str, exit_code)를 생성합니다.
    알 수 없는 예외는 INTERNAL (70) 으로 처리합니다.
    """
    from ameva_component.exceptions import AmevaError

    if isinstance(exc, AmevaError):
        return (
            render_error(component_id, exc.code, exc.message, details=exc.details or None),
            exc.exit_code,
        )
    return (
        render_error(
            component_id,
            "INTERNAL_ERROR",
            str(exc),
            details={"type": type(exc).__name__},
        ),
        ExitCode.INTERNAL,
    )


def log_stderr(message: str, *, flush: bool = True) -> None:
    """
    stderr에만 로그를 출력합니다.
    다운로드 진행 상황, SHA-256 검증 메시지 등 모든 진행 정보는 이 함수를 사용합니다.
    stdout에 절대 출력하지 않습니다.
    """
    print(message, file=sys.stderr, flush=flush)


def log_progress(step: str, current: int, total: int) -> None:
    """다운로드/설치 진행 상황을 stderr에 출력합니다."""
    pct = int(current / total * 100) if total > 0 else 0
    log_stderr(f"[{step}] {current}/{total} ({pct}%)")


def exit_for_result(result: dict) -> int:
    """
    결과 딕셔너리의 ready/degraded 필드를 보고 적절한 Exit Code를 반환합니다.
    측정 실패를 0으로 변환하지 않습니다.
    """
    if not result.get("ready", True):
        return ExitCode.FAIL
    if result.get("degraded", False):
        return ExitCode.DEGRADED
    return ExitCode.OK
