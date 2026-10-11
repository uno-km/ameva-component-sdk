"""
ameva_component.installer
AMEVA Component Protocol v1 — 공통 10단계 모델 설치 순서

패키지마다 중복 구현하지 않기 위한 공통 설치 로직.
패키지별 추가 검사는 after_download(path) hook으로 주입합니다.

공통 순서:
  1. URL 형식 검사 (https:// 만 허용)
  2. 디스크 여유 공간 검사
  3. 임시 파일 다운로드 (진행 상황 → stderr only)
  4. 최대 크기 검사 (expected_bytes * 1.05 상한)
  5. 예상 크기 검사 (± 1% 허용)
  6. SHA-256 검사
  7. after_download hook (패키지별 형식/호환성 검사)
  8. 최종 위치로 이동
  9. Manifest 저장
  10. installed 상태 기록

SHA-256 불일치 시 임시 파일을 삭제하고 HashMismatch 예외 발생.
실패 시 모델 상태를 FAILED로 기록 — installed로 처리 금지.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable

from ameva_component.exceptions import (
    HashMismatch,
    InsufficientDisk,
    InvalidManifest,
)
from ameva_component.manifest import ModelManifest, ModelState
from ameva_component.output import log_progress, log_stderr


class ModelInstaller:
    """
    공통 모델 설치 로직.

    Args:
        component_id:  설치 대상 컴포넌트 ID
        dest_dir:      모델 파일 최종 저장 디렉터리
        registry:      ModelRegistry 인스턴스 (상태 기록용)
    """

    MAX_SIZE_MULTIPLIER = 1.05   # expected_bytes * 1.05 상한
    SIZE_TOLERANCE      = 0.01   # ± 1% 예상 크기 허용

    def __init__(self, component_id: str, dest_dir: Path, registry) -> None:
        self.component_id = component_id
        self.dest_dir = dest_dir
        self.registry = registry
        self.dest_dir.mkdir(parents=True, exist_ok=True)

    def install(
        self,
        *,
        url: str,
        filename: str,
        sha256: str,
        expected_bytes: int,
        model_id: str,
        manifest: ModelManifest | None = None,
        after_download: Callable[[Path], None] | None = None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> dict:
        """
        10단계 공통 설치 순서를 실행합니다.

        Args:
            url:             다운로드 URL (https:// 만 허용)
            filename:        저장할 파일명
            sha256:          기대 SHA-256 hex
            expected_bytes:  기대 파일 크기 (bytes)
            model_id:        모델 ID (Registry 기록용)
            manifest:        ModelManifest (있으면 함께 저장)
            after_download:  패키지별 형식/호환성 검사 hook
            progress_cb:     진행 상황 콜백 (bytes_done, total_bytes) — stderr 출력용

        Returns:
            {"state": "installed", "model_id": ..., "verified_at": ...}

        Raises:
            ValueError:           URL 형식 오류
            InsufficientDisk:     디스크 여유 공간 부족
            HashMismatch:         SHA-256 불일치
            Exception:            after_download hook 오류 (그대로 전파)
        """
        # 1. URL 형식 검사
        self._step_validate_url(url)

        # 2. 디스크 여유 공간 검사
        self._step_check_disk(expected_bytes)

        # 3. 임시 파일 다운로드
        log_stderr(f"[install] Downloading {filename} ...")
        tmp_path = self._step_download(url, filename, expected_bytes, progress_cb)

        try:
            actual_bytes = tmp_path.stat().st_size

            # 4. 최대 크기 검사
            self._step_check_max_size(tmp_path, expected_bytes)

            # 5. 예상 크기 검사
            self._step_check_expected_size(tmp_path, expected_bytes)

            # 6. SHA-256 검사
            log_stderr(f"[install] Verifying SHA-256 for {filename} ...")
            self._step_verify_sha256(tmp_path, filename, sha256)
            log_stderr(f"[install] SHA-256 verified: {sha256[:16]}...")

            # 7. after_download hook
            if after_download is not None:
                log_stderr(f"[install] Running package compatibility check ...")
                after_download(tmp_path)

            # 8. 최종 위치로 이동
            dest = self.dest_dir / filename
            os.replace(tmp_path, dest)
            log_stderr(f"[install] Saved to {dest}")

        except Exception as exc:
            # 임시 파일 정리
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as unlink_err:
                log_stderr(f"[install] Warning: failed to unlink tmp file {tmp_path}: {unlink_err}")
            # 상태를 FAILED로 기록
            try:
                self.registry.set_state(model_id, ModelState.FAILED, last_error=str(exc))
            except Exception as reg_err:
                log_stderr(f"[install] Warning: failed to record FAILED state for {model_id}: {reg_err}")
            raise

        # 9. Manifest 저장 + 10. installed 상태 기록
        verified_at = time.time()
        if manifest is not None:
            self.registry.record_install(model_id, manifest, verified_at)
        else:
            self.registry.set_state(model_id, ModelState.INSTALLED)

        log_stderr(f"[install] {model_id} installed successfully.")
        return {
            "state":       ModelState.INSTALLED.value,
            "model_id":    model_id,
            "verified_at": verified_at,
            "filename":    filename,
            "bytes":       actual_bytes,
        }

    # ------------------------------------------------------------------
    # 개별 단계 메서드
    # ------------------------------------------------------------------

    def _step_validate_url(self, url: str) -> None:
        if not url.startswith("https://"):
            raise ValueError(f"URL must start with 'https://': '{url}'")

    def _step_check_disk(self, expected_bytes: int) -> None:
        try:
            usage = shutil.disk_usage(self.dest_dir)
            required = int(expected_bytes * 1.1)   # 10% 마진
            if usage.free < required:
                raise InsufficientDisk(required, usage.free)
        except OSError as disk_err:
            log_stderr(f"[install] Warning: disk usage check unavailable for {self.dest_dir}: {disk_err}")

    def _step_download(
        self,
        url: str,
        filename: str,
        expected_bytes: int,
        progress_cb: Callable[[int, int], None] | None,
    ) -> Path:
        fd, tmp = tempfile.mkstemp(
            dir=self.dest_dir,
            prefix=f".dl_{filename}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "wb") as out:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "ameva-component-installer/1"},
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    done = 0
                    chunk_size = 1 << 20  # 1 MiB
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        if progress_cb:
                            progress_cb(done, expected_bytes)
                        else:
                            log_progress("download", done, max(expected_bytes, done))
            return Path(tmp)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError as unlink_err:
                log_stderr(f"[install] Warning: failed to remove temporary download file {tmp}: {unlink_err}")
            raise

    def _step_check_max_size(self, path: Path, expected_bytes: int) -> None:
        actual = path.stat().st_size
        max_allowed = int(expected_bytes * self.MAX_SIZE_MULTIPLIER)
        if actual > max_allowed:
            raise ValueError(
                f"Downloaded file is too large: {actual} bytes "
                f"(expected ≤ {max_allowed}, limit = expected_bytes * {self.MAX_SIZE_MULTIPLIER})"
            )

    def _step_check_expected_size(self, path: Path, expected_bytes: int) -> None:
        actual = path.stat().st_size
        tolerance = int(expected_bytes * self.SIZE_TOLERANCE)
        low = expected_bytes - tolerance
        high = expected_bytes + tolerance
        if not (low <= actual <= high):
            raise ValueError(
                f"File size mismatch: got {actual} bytes, expected {expected_bytes} ± {tolerance}"
            )

    def _step_verify_sha256(self, path: Path, filename: str, expected_sha256: str) -> None:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual.lower() != expected_sha256.lower():
            raise HashMismatch(filename, expected_sha256, actual)
