"""
ameva_component.identity
AMEVA Component Protocol v1 — ComponentInfo 및 Capability 검증

지원하지 않는 Capability를 선언하면 즉시 ValueError 발생.
Enum 알 수 없는 값은 unknown으로 위장하지 않고 원문 보존.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROTOCOL_COMPONENT = "ameva-component/1"
PROTOCOL_STATUS    = "ameva-component-status/1"
PROTOCOL_MANIFEST  = "ameva-model-manifest/1"
PROTOCOL_INSTANCE  = "ameva-instance-status/1"
PROTOCOL_ERROR     = "ameva-error/1"
PROTOCOL_OPERATION = "ameva-operation/1"

# 패키지별 허용 Capability 목록
# 이 목록 외의 Capability를 ComponentInfo에 선언하면 validate() 시 ValueError 발생
ALLOWED_CAPABILITIES: dict[str, frozenset[str]] = {
    "llm": frozenset({
        "llm.chat",
        "llm.completion",
        "embedding.generate",
        "rerank",
    }),
    "stt": frozenset({
        "audio.transcribe",
        "audio.translate",
        "audio.diarize",
        "audio.vad",
    }),
    "tts": frozenset({
        "audio.synthesize",
        "voice.list",
        "voice.preview",
    }),
    "vision": frozenset({
        "vision.classify",
        "vision.detect",
        "vision.caption",
        "vision.ocr",
        "vision.vlm",
    }),
    "diffusion": frozenset({
        "image.generate",
        "image.inpaint",
        "image.outpaint",
        "image.upscale",
    }),
    "train": frozenset({
        "train.lora",
        "train.finetune",
        "train.evaluate",
    }),
    "browser": frozenset({
        "browser.navigate",
        "browser.extract",
        "browser.screenshot",
        "browser.action",
    }),
}

VALID_COMPONENT_TYPES: frozenset[str] = frozenset(ALLOWED_CAPABILITIES.keys())


@dataclass(frozen=True, slots=True)
class ComponentInfo:
    """
    패키지 자기 신원 정보.
    실제로 지원하는 Capability만 포함해야 합니다.
    지원하지 않는 Capability는 목록에 넣으면 안 됩니다.
    """
    protocol:       str              # 항상 PROTOCOL_COMPONENT
    component_id:   str              # e.g. "termux-diffusion"
    component_type: str              # "llm", "stt", "tts", "vision", "diffusion", "train", "browser"
    version:        str              # semver e.g. "1.2.0"
    capabilities:   tuple[str, ...]  # 실제 지원하는 Capability만

    def validate(self) -> None:
        """
        ComponentInfo 유효성 검사.
        실패 시 ValueError 발생 — unknown으로 위장하거나 무시하지 않습니다.
        """
        if self.protocol != PROTOCOL_COMPONENT:
            raise ValueError(
                f"Invalid protocol: '{self.protocol}' (expected '{PROTOCOL_COMPONENT}')"
            )

        if not self.component_id.startswith("termux-"):
            raise ValueError(
                f"component_id must start with 'termux-': '{self.component_id}'"
            )

        if self.component_type not in VALID_COMPONENT_TYPES:
            raise ValueError(
                f"Unknown component_type: '{self.component_type}'. "
                f"Valid types: {sorted(VALID_COMPONENT_TYPES)}"
            )

        allowed = ALLOWED_CAPABILITIES[self.component_type]
        for cap in self.capabilities:
            if cap not in allowed:
                raise ValueError(
                    f"Capability '{cap}' is not allowed for component_type "
                    f"'{self.component_type}'. Allowed: {sorted(allowed)}"
                )

        _validate_semver(self.version)

    def to_dict(self) -> dict:
        return {
            "protocol":       self.protocol,
            "component_id":   self.component_id,
            "component_type": self.component_type,
            "version":        self.version,
            "capabilities":   list(self.capabilities),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComponentInfo":
        """
        딕셔너리로부터 ComponentInfo를 생성합니다.
        필수 필드 누락 시 오류 — 알 수 없는 추가 필드는 무시합니다.
        """
        required = {"protocol", "component_id", "component_type", "version", "capabilities"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")

        return cls(
            protocol=data["protocol"],
            component_id=data["component_id"],
            component_type=data["component_type"],
            version=data["version"],
            capabilities=tuple(data["capabilities"]),
        )


def _validate_semver(version: str) -> None:
    """
    기본 semver 형식 검증 (MAJOR.MINOR.PATCH).
    사전 릴리스 접미사(-alpha.1 등)도 허용합니다.
    """
    parts = version.split(".")
    if len(parts) < 3:
        raise ValueError(f"Version '{version}' is not valid semver (expected MAJOR.MINOR.PATCH)")
    # 첫 두 파트는 정수여야 함
    for i, part in enumerate(parts[:2]):
        if not part.isdigit():
            raise ValueError(f"Version '{version}' part {i} is not an integer")
    # 세 번째 파트는 숫자 + 선택적 사전 릴리스 접미사
    patch_part = parts[2].split("-")[0]
    if not patch_part.isdigit():
        raise ValueError(f"Version '{version}' patch part is not valid")
