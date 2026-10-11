"""
ameva_component.cli_support
AMEVA Component Protocol v1 — 공통 CLI 지원 함수

모든 패키지 CLI에서 재사용하는 공통 명령 구현.
사용법:
    from ameva_component.cli_support import build_protocol_parser, dispatch_protocol

    # 기존 subparsers에 추가
    build_protocol_parser(subparsers)

    # dispatch에 추가
    "component": lambda args: dispatch_protocol(args, control),
    "instance":  lambda args: dispatch_protocol(args, control),
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


def build_protocol_subcommands(subparsers: Any) -> None:
    """기존 argparse subparsers에 component/instance 명령을 추가합니다."""
    # ------------------------------------------------------------------ component
    p_comp = subparsers.add_parser(
        "component",
        help="[AMEVA Protocol v1] Component identity and health"
    )
    comp_sub = p_comp.add_subparsers(dest="comp_action", required=True)

    # component info
    p_info = comp_sub.add_parser("info", help="Print component identity (protocol, id, capabilities)")
    p_info.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON to stdout")

    # component doctor-lite
    p_dlite = comp_sub.add_parser("doctor-lite", help="Lightweight health check (no inference, <500ms)")
    p_dlite.add_argument("--json", action="store_true", dest="json_output")

    # component doctor-full
    p_dfull = comp_sub.add_parser("doctor-full", help="Full diagnostic including hardware/Vulkan checks")
    p_dfull.add_argument("--json", action="store_true", dest="json_output")

    # ------------------------------------------------------------------ model
    p_mod = subparsers.add_parser(
        "model",
        help="[AMEVA Protocol v1] Model lifecycle management"
    )
    mod_sub = p_mod.add_subparsers(dest="model_action", required=True)

    # model list
    p_mlist = mod_sub.add_parser("list", help="List installed models from AMEVA ModelRegistry")
    p_mlist.add_argument("--json", action="store_true", dest="json_output")

    # model status
    p_mstat = mod_sub.add_parser("status", help="Show model status (state, hash, timestamps)")
    p_mstat.add_argument("model_id", nargs="?", default=None, help="Model ID (omit for all)")
    p_mstat.add_argument("--json", action="store_true", dest="json_output")

    # model install
    p_minst = mod_sub.add_parser("install", help="Download and verify model (SHA-256 + format check)")
    p_minst.add_argument("--url",            required=True,  help="Download URL")
    p_minst.add_argument("--filename",       required=True,  help="Target filename")
    p_minst.add_argument("--sha256",         default="",     help="Expected SHA-256 hex digest")
    p_minst.add_argument("--expected-bytes", type=int, default=0, help="Expected file size")
    p_minst.add_argument("--model-id",       default=None,   help="Model ID (default: stem of filename)")
    p_minst.add_argument("--json", action="store_true", dest="json_output")

    # model activate
    p_mact = mod_sub.add_parser("activate", help="Activate model (safe-switch with rollback)")
    p_mact.add_argument("--model-id", required=True, help="Model ID to activate")
    p_mact.add_argument("--voice-id", default=None, help="[TTS only] Voice ID")
    p_mact.add_argument("--json", action="store_true", dest="json_output")

    # model deactivate
    p_mdeact = mod_sub.add_parser("deactivate", help="Deactivate model")
    p_mdeact.add_argument("--model-id", required=True, help="Model ID to deactivate")
    p_mdeact.add_argument("--json", action="store_true", dest="json_output")

    # ------------------------------------------------------------------ instance
    p_inst = subparsers.add_parser(
        "instance",
        help="[AMEVA Protocol v1] Instance (worker) management"
    )
    inst_sub = p_inst.add_subparsers(dest="inst_action", required=True)

    # instance list
    p_ilist = inst_sub.add_parser("list", help="List running instances / workers")
    p_ilist.add_argument("--json", action="store_true", dest="json_output")

    # instance start
    p_istart = inst_sub.add_parser("start", help="Start a new instance/worker")
    p_istart.add_argument("--model-id",    default="",   help="Model ID to load in the instance")
    p_istart.add_argument("--instance-id", default=None, help="Custom instance ID")
    p_istart.add_argument("--backend",     default=None, help="Backend override (e.g. dsp, onnx, cpu, vulkan)")
    p_istart.add_argument("--json", action="store_true", dest="json_output")

    # instance drain
    p_idrain = inst_sub.add_parser("drain", help="Signal instance to stop accepting new jobs")
    p_idrain.add_argument("instance_id", help="Instance ID")
    p_idrain.add_argument("--json", action="store_true", dest="json_output")

    # instance stop
    p_istop = inst_sub.add_parser("stop", help="Terminate instance")
    p_istop.add_argument("instance_id", help="Instance ID")
    p_istop.add_argument("--json", action="store_true", dest="json_output")


def dispatch_protocol(args: Any, control: Any) -> None:
    """
    args.command ('component' | 'model' | 'instance') 에 따라
    ComponentControl 메서드를 호출하고 결과를 stdout에 JSON으로 출력합니다.

    로그/오류는 stderr로만 출력.
    EXIT CODE:
      0 = OK
      1 = ERROR (ameva 오류 또는 OPERATION_NOT_SUPPORTED)
      2 = DEGRADED (component ready=False)
    """
    from ameva_component.output import render_ok, render_error, render_from_exception, log_stderr
    from ameva_component.exceptions import AmevaError, OperationNotSupported

    cmd = args.command
    json_out = getattr(args, "json_output", False)
    component_id: str = getattr(control, "COMPONENT_ID", "unknown")

    def _emit_json(json_str: str) -> None:
        """render_ok/render_error 반환값(JSON 문자열)을 stdout으로 출력."""
        print(json_str)

    def _print_result(result: dict) -> None:
        """결과 dict를 JSON 문자열로 변환해 출력."""
        if json_out:
            _emit_json(render_ok(component_id, result))
        else:
            _pretty_result(result)

    def _pretty_result(data: dict) -> None:
        """--json 없을 때 가독성 있는 출력."""
        ok = data.get("ready", True)
        prefix = "[OK]" if ok else "[WARN]"
        print(f"{prefix} {data.get('component_id', component_id)} {data.get('component_type', '')}")
        for k, v in data.items():
            if k in ("protocol",):
                continue
            if isinstance(v, (dict, list)):
                print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                print(f"  {k}: {v}")

    def _emit_error(code: str, message: str) -> None:
        if json_out:
            _emit_json(render_error(component_id, code, message))
        else:
            print(f"[ERROR] {code}: {message}", file=sys.stderr)

    try:
        # ---------------------------------------------------------------- component
        if cmd == "component":
            action = args.comp_action
            if action == "info":
                result = control.component_info()
                _print_result(result)
            elif action == "doctor-lite":
                result = control.doctor_lite()
                _print_result(result)
                if not result.get("ready", True):
                    sys.exit(2)
            elif action == "doctor-full":
                if hasattr(control, "doctor_full"):
                    result = control.doctor_full()
                else:
                    result = control.doctor_lite()
                _print_result(result)

        # ---------------------------------------------------------------- model
        elif cmd == "model":
            action = args.model_action
            if action == "list":
                result = control.list_models()
                _print_result(result)
            elif action == "status":
                result = control.model_status(getattr(args, "model_id", None))
                _print_result(result)
            elif action == "install":
                request = {
                    "url":            args.url,
                    "filename":       args.filename,
                    "sha256":         args.sha256,
                    "expected_bytes": args.expected_bytes,
                    "model_id":       args.model_id,
                }
                result = control.install_model(request)
                _print_result(result)
            elif action == "activate":
                request = {"model_id": args.model_id, "voice_id": getattr(args, "voice_id", None)}
                result = asyncio.run(control.activate_model(request))
                if result.get("activated", False):
                    _print_result(result)
                else:
                    _emit_error("MODEL_ACTIVATION_FAILED", str(result))
                    sys.exit(1)
            elif action == "deactivate":
                request = {"model_id": args.model_id}
                result = asyncio.run(control.deactivate_model(request))
                _print_result(result)

        # ---------------------------------------------------------------- instance
        elif cmd == "instance":
            action = args.inst_action
            if action == "list":
                result = control.list_instances()
                _print_result(result)
            elif action == "start":
                request = {
                    "model_id":    getattr(args, "model_id", ""),
                    "instance_id": getattr(args, "instance_id", None),
                    "backend":     getattr(args, "backend", None),
                }
                result = asyncio.run(control.start_instance(request))
                _print_result(result)
            elif action == "drain":
                result = asyncio.run(control.drain_instance(args.instance_id))
                _print_result(result)
            elif action == "stop":
                result = asyncio.run(control.stop_instance(args.instance_id))
                _print_result(result)

    except OperationNotSupported as e:
        _emit_error("OPERATION_NOT_SUPPORTED", str(e))
        sys.exit(1)
    except AmevaError as e:
        json_str, exit_code = render_from_exception(component_id, e)
        if json_out:
            print(json_str)
        else:
            print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(exit_code)
    except Exception as e:
        _emit_error("INTERNAL_ERROR", str(e))
        sys.exit(1)

