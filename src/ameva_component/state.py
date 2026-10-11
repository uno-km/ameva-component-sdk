"""
ameva_component.state
AMEVA Component Protocol v1 — ComponentStateFile 원자적 읽기/쓰기

상태 파일은 doctor-lite 실행 시만 갱신하는 것은 불충분합니다.
반드시 다음 시점마다 원자적으로 갱신해야 합니다:
  - Worker 시작 시
  - 모델 활성화/비활성화 시
  - Job 시작(active_jobs++) / 종료(active_jobs--) 시
  - 엔진 오류 발생 시 (ready=false, errors 기록)
  - 정상 종료 시 (running=false 또는 파일 제거)
  - Heartbeat 주기 (10초)

stale 판정: 현재 시각 - updated_at_unix_ms > stale_threshold_ms
마지막 정상 상태를 계속 정상으로 표시하면 안 됩니다.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ameva_component.output import log_stderr


_STATE_PATH_PRECEDENCE = [
    # 1순위: $XDG_RUNTIME_DIR/ameva/components/
    lambda: _env_path("XDG_RUNTIME_DIR", "ameva/components"),
    # 2순위: $PREFIX/var/run/ameva/components/  (Termux)
    lambda: _env_path("PREFIX", "var/run/ameva/components"),
    # 3순위: ~/.local/state/ameva/components/
    lambda: Path.home() / ".local" / "state" / "ameva" / "components",
]


def _env_path(env_var: str, suffix: str) -> Path | None:
    val = os.environ.get(env_var)
    if val:
        return Path(val) / suffix
    return None


def resolve_state_dir() -> Path:
    """
    상태 파일 디렉터리를 우선순위 순으로 탐색하여 반환합니다.
    최초 해결 경로를 사용하며, 디렉터리가 없으면 생성합니다.
    """
    for factory in _STATE_PATH_PRECEDENCE:
        p = factory()
        if p is not None:
            p.mkdir(parents=True, exist_ok=True)
            return p
    # fallback (도달하지 않아야 함 — home()은 항상 성공)
    fallback = Path.home() / ".local" / "state" / "ameva" / "components"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class ComponentStateFile:
    """
    컴포넌트 상태를 원자적으로 읽고 씁니다.

    쓰기 순서: 임시 파일 작성 → flush → fsync → rename
    이 순서로 작성하면 전원이 꺼지거나 프로세스가 죽어도
    상태 파일이 절반만 쓰인 상태로 남지 않습니다.
    """

    def __init__(self, component_id: str, state_dir: Path | None = None) -> None:
        self.component_id = component_id
        self._dir = state_dir if state_dir is not None else resolve_state_dir()
        self._path = self._dir / f"{component_id}.json"

    @property
    def path(self) -> Path:
        return self._path

    def write(self, data: dict) -> None:
        """
        상태 데이터를 원자적으로 저장합니다.
        data에는 반드시 protocol, component_id, updated_at_unix_ms, ready 필드가 있어야 합니다.
        실패 시 예외를 발생시킵니다 — 실패를 정상으로 위장하지 않습니다.
        """
        self._dir.mkdir(parents=True, exist_ok=True)

        # 임시 파일을 같은 디렉터리에 생성 (rename이 원자적이 되려면 같은 파티션이어야 함)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._dir,
            prefix=f".{self.component_id}.",
            suffix=".tmp.json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=None)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError as unlink_err:
                log_stderr(f"[state] Warning: failed to unlink tmp state file {tmp_path}: {unlink_err}")
            raise

    def read(self) -> dict | None:
        """
        상태 파일을 읽어 딕셔너리로 반환합니다.
        파일이 없으면 None, 파싱 오류(손상)이면 None (크래시 없이).
        None 반환 시 호출자는 ready=false로 처리해야 합니다.
        """
        if not self._path.exists():
            return None
        try:
            with self._path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def remove(self) -> None:
        """
        상태 파일을 제거합니다.
        정상 종료 시 Worker가 호출합니다.
        파일이 없어도 예외를 발생시키지 않습니다.
        """
        try:
            self._path.unlink(missing_ok=True)
        except OSError as unlink_err:
            log_stderr(f"[state] Warning: failed to unlink state file {self._path}: {unlink_err}")

    def is_stale(self, threshold_ms: int = 30_000) -> bool:
        """
        상태 파일이 stale 상태인지 판정합니다.
        파일이 없거나 updated_at_unix_ms 필드가 없으면 stale로 간주합니다.
        stale 상태에서는 마지막 ready=true를 신뢰해서는 안 됩니다.
        """
        import time
        data = self.read()
        if data is None:
            return True
        unix_ms = data.get("updated_at_unix_ms")
        if unix_ms is None:
            return True
        now_ms = int(time.time() * 1000)
        return (now_ms - unix_ms) > threshold_ms
