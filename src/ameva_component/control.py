"""
ameva_component.control
AMEVA Component Protocol v1 — ComponentControl 추상 베이스 클래스

진실의 원천은 반드시 하나여야 합니다.
CLI / 상태 파일 Writer / Orchestrator Adapter 모두 이 클래스를 통해 상태를 조회합니다.

구현 의무:
  - 모든 상태값은 실제 상태 파일, PID, Worker, Registry에서 계산
  - 측정 실패를 0, 빈 배열, 정상 상태로 변환 금지
  - 지원하지 않는 기능은 OperationNotSupported 예외 발생 (빈 성공 금지)
  - doctor_lite 실행 시간 목표: 500ms 이내
  - doctor_lite 금지 항목: 모델 전체 Load, Vulkan 전체 Doctor,
                          대형 Hash 재계산, 샘플 추론, ONNX Session 생성,
                          Audio Device 초기화, 모델 다운로드 서버 접속
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ComponentControl(ABC):
    """
    AMEVA Component Protocol v1 공통 컨트롤 인터페이스.

    각 패키지는 이 클래스를 상속하고 모든 abstractmethod를 구현해야 합니다.
    기존 엔진 코드를 Adapter 방식으로 감싸서 연결하세요.
    기존 기능을 가짜 Stub로 대체하지 마세요.
    """

    # 서브클래스가 반드시 선언해야 하는 클래스 변수
    COMPONENT_ID:   str  # e.g. "termux-llamacpp"
    COMPONENT_TYPE: str  # "llm", "stt", "tts", "vision", "diffusion", "train", "browser"
    CAPABILITIES:   tuple[str, ...]  # 실제 지원하는 Capability만

    @abstractmethod
    def component_info(self) -> dict:
        """
        컴포넌트 자기 신원 정보를 반환합니다.
        protocol: "ameva-component/1" 포함.
        실패 시 예외 발생 — ok:false 응답을 직접 반환하지 않습니다.
        """

    @abstractmethod
    def doctor_lite(self) -> dict:
        """
        경량 상태 확인. 실행 시간 목표 500ms 이내.

        필수 포함:
          - 버전, 상태 파일 경로 및 updated_at
          - 활성 모델 ID
          - Worker PID 존재 여부 및 실제 생존 여부 (os.kill(pid, 0))
          - 최근 Heartbeat 시간
          - Listening Socket 또는 Worker 연결 상태
          - 현재 Instance 수
          - 현재 Active Job 수
          - 마지막 오류
          - Backend와 Device의 이미 확인된 상태

        포함 금지:
          - 모델 전체 Load
          - Vulkan 전체 Doctor
          - 대형 모델 Hash 재계산
          - 샘플 추론
          - ONNX Session 생성
          - Audio Device 전체 초기화
          - 모델 다운로드 서버 접속
        """

    @abstractmethod
    def doctor_full(self) -> dict:
        """
        상세 진단. 수 분 소요 가능.
        Vulkan 전체 Doctor, 샘플 추론 등 포함 가능.
        """

    @abstractmethod
    def list_models(self) -> dict:
        """
        설치된 모델 목록을 반환합니다.
        각 모델의 state (missing/installed/active 등)를 포함합니다.
        failed 모델을 installed로 반환하지 않습니다.

        미지원 패키지 (termux-playwright, termux-train): OperationNotSupported 발생.
        """

    @abstractmethod
    def model_status(self, model_id: str | None = None) -> dict:
        """
        특정 모델 또는 전체 모델 상태를 반환합니다.
        failed를 installed로 변환하지 않습니다.

        미지원 패키지: OperationNotSupported 발생.
        """

    @abstractmethod
    def install_model(self, request: dict) -> dict:
        """
        모델을 설치합니다.

        공통 순서:
          1. URL 검사
          2. 디스크 여유 공간 검사
          3. 임시 파일 다운로드 (진행 상황 → stderr)
          4. 최대 크기 검사
          5. 예상 크기 검사
          6. SHA-256 검사
          7. 형식 검사 (패키지별 after_download hook)
          8. Package 호환성 검사
          9. Manifest 저장
          10. installed 상태 기록

        미지원 패키지: OperationNotSupported 발생.
        """

    @abstractmethod
    async def activate_model(self, request: dict) -> dict:
        """
        모델을 활성화합니다 (safe-switch 기본 전략).

        순서:
          1. 모델이 verified 상태인지 확인
          2. 대상 Instance 확인
          3. RAM 및 Accelerator 예산 확인
          4. 신규 Job 접수 일시 중단
          5. 기존 Job Drain
          6. 새 모델 준비
          7. 새 모델 Load
          8. 최소 Health Probe (실제 추론 없이 메타데이터만)
          9. 성공 시에만 Active Pointer 변경
          10. 기존 모델 자원 해제

        실패 시:
          - Active Pointer 변경 금지
          - 기존 모델 유지
          - rollback.succeeded를 정직하게 반환
          - 성공으로 위장 금지

        미지원 패키지 (termux-playwright): OperationNotSupported 발생.
        """

    @abstractmethod
    async def deactivate_model(self, request: dict) -> dict:
        """
        활성 모델을 비활성화합니다.
        미지원 패키지: OperationNotSupported 발생.
        """

    @abstractmethod
    def list_instances(self) -> dict:
        """
        현재 등록된 Instance 목록을 반환합니다.
        termux-playwright는 Browser Context 또는 Worker 목록.
        termux-train은 Training Worker 목록.
        """

    @abstractmethod
    async def start_instance(self, request: dict) -> dict:
        """
        새 Instance를 시작합니다.
        termux-train: Training Worker.
        """

    @abstractmethod
    async def drain_instance(self, instance_id: str) -> dict:
        """
        Instance를 Drain 상태로 전환합니다 (신규 Job 접수 중단, 기존 Job 완료 대기).
        termux-train: Checkpoint 저장 후 중단 또는 새 작업 접수 중단.
        """

    @abstractmethod
    async def stop_instance(self, instance_id: str) -> dict:
        """Instance를 중지합니다."""
