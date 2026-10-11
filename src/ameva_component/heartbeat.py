"""
ameva_component.heartbeat
AMEVA Component Protocol v1 — 공통 HeartbeatWriter 베이스

모든 패키지 StatusWriter가 상속하는 공통 백그라운드 Heartbeat 구현.

갱신 트리거 (Phase 4 표준):
  ① Worker 시작      → write()
  ② 모델 활성화      → write()
  ③ Job 시작         → notify_job_start()  (active_jobs++)
  ④ Job 종료         → notify_job_end()    (active_jobs--)
  ⑤ 엔진 오류        → notify_error()      (ready=False, last_error 기록)
  ⑥ 정상 종료        → write(ready=False)  또는 상태파일 제거
  ⑦ Heartbeat 주기   → 10초마다 updated_at 갱신
"""
from __future__ import annotations

import threading
import time
from typing import Any

from ameva_component.output import log_stderr


class HeartbeatWriter:
    """
    공통 백그라운드 Heartbeat Writer.

    사용법:
        class MyStatusWriter(HeartbeatWriter):
            def __init__(self, control):
                super().__init__(control, name="my-pkg")

        writer = MyStatusWriter(control)
        writer.start()
        ...
        writer.notify_job_start()
        writer.notify_job_end()
        writer.notify_error("inference failed")
        writer.stop()
    """

    _HEARTBEAT_INTERVAL: float = 10.0

    def __init__(self, control: Any, *, name: str = "component") -> None:
        self._control    = control
        self._name       = name
        self._thread: threading.Thread | None = None
        self._stop_evt   = threading.Event()
        self._active_jobs = 0
        self._jobs_lock   = threading.Lock()

    # ------------------------------------------------------------------
    # 수명 주기
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Heartbeat 백그라운드 스레드를 시작합니다. 이미 실행 중이면 무시."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._active_jobs = 0
        self._control._write_state(ready=True)
        self._thread = threading.Thread(
            target=self._loop, daemon=True,
            name=f"{self._name}-heartbeat"
        )
        self._thread.start()
        log_stderr(f"[{self._name}] Heartbeat started (interval={self._HEARTBEAT_INTERVAL}s)")

    def stop(self) -> None:
        """Heartbeat를 중단하고 상태 파일을 running=False로 갱신합니다."""
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        try:
            self._control._write_state(ready=False)
        except Exception as exc:
            log_stderr(f"[{self._name}] failed to write stopped state: {exc}")
        log_stderr(f"[{self._name}] Heartbeat stopped")

    def _loop(self) -> None:
        while not self._stop_evt.wait(timeout=self._HEARTBEAT_INTERVAL):
            try:
                self._control._write_state()
            except Exception as exc:
                log_stderr(f"[{self._name}] heartbeat write failed: {exc}")

    # ------------------------------------------------------------------
    # 이벤트 훅 — ComponentControl 내부에서 호출
    # ------------------------------------------------------------------

    def write(self, **overrides) -> None:
        """상태 파일을 즉시 강제 갱신합니다."""
        self._control._write_state(**overrides)

    def notify_job_start(self) -> None:
        """Job 시작 시 호출 — active_jobs 증가 후 상태 파일 갱신."""
        with self._jobs_lock:
            self._active_jobs += 1
        self._control._write_state()

    def notify_job_end(self) -> None:
        """Job 종료 시 호출 — active_jobs 감소 후 상태 파일 갱신."""
        with self._jobs_lock:
            self._active_jobs = max(0, self._active_jobs - 1)
        self._control._write_state()

    def notify_error(self, message: str) -> None:
        """엔진 오류 발생 시 호출 — ready=False, last_error 기록."""
        log_stderr(f"[{self._name}] Engine error: {message}")
        self._control._write_state(ready=False, last_error=message)

    def notify_ready(self) -> None:
        """엔진 복구 시 호출 — ready=True로 상태 파일 갱신."""
        self._control._write_state(ready=True, last_error=None)

    @property
    def active_jobs(self) -> int:
        with self._jobs_lock:
            return self._active_jobs

    # 하위 호환: 기존 llamacpp StatusWriter 인터페이스 별칭
    def start_heartbeat(self, interval: float | None = None) -> None:
        if interval is not None:
            self._HEARTBEAT_INTERVAL = interval
        self.start()

    def stop_heartbeat(self) -> None:
        self.stop()
