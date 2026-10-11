"""
ameva_component.locks
AMEVA Component Protocol v1 — 4종 동시성 Lock

충돌 시나리오별 Lock:
  ArtifactLock:    파일별 — 다운로드 중 삭제 방지
  ModelLock:       모델별 — Activate + Deactivate 동시 방지
  InstanceLock:    인스턴스별 — Start + Stop 동시 방지
  ActivationLock:  전체 Activate 연산 — 동시 Activate 2번 방지

모든 Lock은 timeout 초과 시 LockTimeout 예외를 발생시킵니다.
Lock 획득 실패를 0이나 빈 성공으로 변환하지 않습니다.
"""
from __future__ import annotations

import contextlib
import threading
from typing import Iterator


class _PerKeyLock:
    """키별 독립 Lock을 관리하는 컨테이너."""

    def __init__(self) -> None:
        self._meta = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._ref_counts: dict[str, int] = {}

    @contextlib.contextmanager
    def acquire(self, key: str, timeout: float = 30.0) -> Iterator[None]:
        from ameva_component.exceptions import LockTimeout

        # 키별 Lock 가져오기 또는 생성
        with self._meta:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
                self._ref_counts[key] = 0
            lock = self._locks[key]
            self._ref_counts[key] += 1

        acquired = lock.acquire(timeout=timeout)
        if not acquired:
            with self._meta:
                self._ref_counts[key] -= 1
                if self._ref_counts[key] == 0:
                    del self._locks[key]
                    del self._ref_counts[key]
            raise LockTimeout(key, timeout)

        try:
            yield
        finally:
            lock.release()
            with self._meta:
                self._ref_counts[key] -= 1
                if self._ref_counts[key] == 0:
                    del self._locks[key]
                    del self._ref_counts[key]


class ArtifactLock:
    """
    파일(Artifact)별 개별 Lock.
    다운로드 중 같은 파일 삭제, 중복 다운로드를 방지합니다.
    """
    def __init__(self) -> None:
        self._impl = _PerKeyLock()

    @contextlib.contextmanager
    def acquire(self, filename: str, timeout: float = 30.0) -> Iterator[None]:
        with self._impl.acquire(filename, timeout=timeout):
            yield


class ModelLock:
    """
    모델별 상태 변경 Lock.
    Activate + Deactivate 동시 실행을 방지합니다.
    """
    def __init__(self) -> None:
        self._impl = _PerKeyLock()

    @contextlib.contextmanager
    def acquire(self, model_id: str, timeout: float = 30.0) -> Iterator[None]:
        with self._impl.acquire(model_id, timeout=timeout):
            yield


class InstanceLock:
    """
    인스턴스별 상태 변경 Lock.
    Start + Stop 동시 실행을 방지합니다.
    """
    def __init__(self) -> None:
        self._impl = _PerKeyLock()

    @contextlib.contextmanager
    def acquire(self, instance_id: str, timeout: float = 30.0) -> Iterator[None]:
        with self._impl.acquire(instance_id, timeout=timeout):
            yield


class ActivationLock:
    """
    전체 Activation 연산 싱글톤 Lock.
    동시에 모델 Activate 2번 실행을 방지합니다.
    Activate 중 Instance Stop 순서를 보장하기 위해 InstanceLock과 함께 사용합니다.
    """
    def __init__(self) -> None:
        self._lock = threading.Lock()

    @contextlib.contextmanager
    def acquire(self, timeout: float = 60.0) -> Iterator[None]:
        from ameva_component.exceptions import ActivationConflict, LockTimeout

        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            raise ActivationConflict()
        try:
            yield
        finally:
            self._lock.release()
