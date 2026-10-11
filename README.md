# ameva-component-sdk

AMEVA Component Protocol v1 공유 SDK.

7개 `termux-*` 패키지가 공통으로 사용하는 ComponentControl 추상 계층, 상태 파일 원자적 읽기/쓰기,
Model/Instance Registry, JSON Schema 계약 검증 및 표준 출력 포맷터를 제공합니다.

## 사용 대상

- termux-llamacpp
- termux-stt
- termux-tts
- termux-vision
- termux-diffusion
- termux-train
- termux-playwright
- termux-bitnet

## 설치 (개발용)

```bash
pip install -e .
```

## 표준 라이브러리만 사용 (외부 의존성 없음)

## 설치 (Install)

PyPI 없이 GitHub Releases에서 바로 설치합니다. 설치 전 `SHA256SUMS`로 해시를 확인할 수 있습니다.

```bash
pip install https://github.com/uno-km/ameva-component-sdk/releases/download/v0.1.2/ameva_component_sdk-0.1.2-py3-none-any.whl
```

Python 3.8 이상, 표준 라이브러리만 사용합니다.
