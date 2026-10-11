"""
ameva_component.adapter_base
============================
BaseOrchestratorAdapter — v0.8.1 Orchestrator Adapter 공통 베이스 클래스.

사용법:
    from ameva_component.adapter_base import BaseOrchestratorAdapter

    class MyAdapter(BaseOrchestratorAdapter):
        COMPONENT_ID = "termux-mypackage"
        ...
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from ameva_component.exceptions import InstanceNotFound, OperationNotSupported


_INFER_NOT_SUPPORTED_COMPONENTS = frozenset({
    # streaming LLM inference를 지원하지 않는 컴포넌트는 서브클래스에서 오버라이드
})


class BaseOrchestratorAdapter:
    """AMEVA Component Orchestrator Adapter 공통 베이스.

    오케스트레이터 v0.8.1 ComponentAdapter Protocol 전체 표면을 구현합니다.
    서브클래스는 `_control` 속성을 통해 ComponentControl에 접근합니다.

    메서드 계약:
        - info / health / models / instances: dict 반환 (동기)
        - activate / deactivate / start_instance / stop_instance: async dict 반환
        - drain_instance / resume_instance: async dict 반환
        - infer: AsyncIterator[dict] — 미지원 시 OPERATION_NOT_SUPPORTED 구조화 오류 반환
    """

    COMPONENT_ID: str = ""  # 서브클래스에서 반드시 선언

    # ──────────────────────────────────────────────────────────────
    # 동기 표면
    # ──────────────────────────────────────────────────────────────

    def info(self) -> dict[str, Any]:
        return self._control.component_info()

    def health(self) -> dict[str, Any]:
        return self._control.doctor_lite()

    def models(self) -> dict[str, Any]:
        return self._control.list_models()

    def instances(self) -> dict[str, Any]:
        return self._control.list_instances()

    # ──────────────────────────────────────────────────────────────
    # 비동기 표면 — 모델 Lifecycle
    # ──────────────────────────────────────────────────────────────

    async def activate(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._control.activate_model(request)

    async def deactivate(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._control.deactivate_model(request)

    # ──────────────────────────────────────────────────────────────
    # 비동기 표면 — 인스턴스 Lifecycle
    # ──────────────────────────────────────────────────────────────

    async def start_instance(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._control.start_instance(request)

    async def drain_instance(self, instance_id: str) -> dict[str, Any]:
        """인스턴스를 Draining 상태로 전환합니다.

        현재 처리 중인 요청이 완료되길 기다리되, 신규 요청은 거부합니다.
        ComponentControl에 drain_instance가 없으면 DRAINING 상태로 전환 후 stop_instance 위임.
        """
        try:
            if hasattr(self._control, "drain_instance"):
                return await self._control.drain_instance(instance_id)
            # Fallback: DRAINING 전환 후 stop_instance
            return await self._control.stop_instance(instance_id)
        except InstanceNotFound:
            return {
                "ok": False,
                "error": {
                    "code": "INSTANCE_NOT_FOUND",
                    "message": f"instance {instance_id!r} not found",
                    "operation": "drain_instance",
                    "component_id": self.COMPONENT_ID,
                    "retryable": False,
                },
            }

    async def resume_instance(self, instance_id: str) -> dict[str, Any]:
        """Draining 상태의 인스턴스를 ACTIVE로 복귀합니다.

        ComponentControl에 resume_instance가 없으면 OPERATION_NOT_SUPPORTED 반환.
        """
        if hasattr(self._control, "resume_instance"):
            return await self._control.resume_instance(instance_id)
        return self._not_supported("resume_instance")

    async def stop_instance(self, instance_id: str) -> dict[str, Any]:
        return await self._control.stop_instance(instance_id)

    # ──────────────────────────────────────────────────────────────
    # Inference 표면
    # ──────────────────────────────────────────────────────────────

    async def infer(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Streaming inference. 미지원 컴포넌트는 OperationNotSupported를 발생시킵니다.

        서브클래스에서 오버라이드하여 실제 스트리밍을 구현합니다.
        """
        raise OperationNotSupported(operation="infer", component_id=self.COMPONENT_ID)
        if False:
            yield {}

    # ──────────────────────────────────────────────────────────────
    # 내부 유틸리티
    # ──────────────────────────────────────────────────────────────

    def _not_supported(self, operation: str) -> dict[str, Any]:
        """OPERATION_NOT_SUPPORTED 구조화 오류 딕셔너리 반환."""
        return {
            "ok": False,
            "error": {
                "code": "OPERATION_NOT_SUPPORTED",
                "operation": operation,
                "component_id": self.COMPONENT_ID,
                "message": (
                    f"{self.COMPONENT_ID} does not support {operation}"
                ),
                "retryable": False,
            },
        }
