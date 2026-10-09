"""维护者通过内存管道转交现有模型配置，固定运行合成真实模型探针。"""

import argparse
import asyncio
import json
import os
import sys
from contextlib import redirect_stdout


LIVE_FIELDS = frozenset(
    "HEALTH_SAFE_PLANNER_LIVE_" + name
    for name in (
        "PROVIDER_ID",
        "PROVIDER_TYPE",
        "BASE_URL",
        "API_KEY",
        "MODEL_ID",
        "HEADERS_JSON",
        "EXTRA_JSON",
        "MODEL_JSON",
        "INCLUDE_USER_UID",
    )
)


def main() -> int:
    """显式启用后导出到内部管道，或从管道启动唯一验收文件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--spec", required=True)
    subparsers.add_parser("run")
    args = parser.parse_args()
    try:
        if os.getenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL") != "1":
            raise ValueError("真实配餐探针需要明确设置 RUN_HEALTH_SAFE_PLANNER_REAL_MODEL=1")
        if args.command == "export":
            with redirect_stdout(sys.stderr):
                packet = asyncio.run(export_environment(args.spec))
            # 此 stdout 只能连接受控 runner 的 stdin，禁止重定向到文件或工具输出。
            sys.stdout.write(json.dumps(packet, ensure_ascii=True) + "\n")
            return 0
        if os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true":
            raise ValueError("真实配餐探针只能在明确标记的健康隔离槽执行")
        packet = read_environment_packet(sys.stdin.read())
        os.environ.update(packet)
        from test.support.health_safe_planner_live_inputs import load_live_inputs

        load_live_inputs(os.environ)
        import pytest

        return int(
            pytest.main(
                [
                    "test/e2e/test_health_safe_planner_live_e2e.py",
                    "-q",
                    "--tb=short",
                    "--show-capture=no",
                    "-o",
                    "log_cli=false",
                    "-o",
                    "cache_dir=/tmp/health-safe-planner-live",
                ]
            )
        )
    except Exception as exc:
        # 不输出原始 packet、供应商响应或异常正文，避免凭据进入控制台。
        print(f"真实配餐探针入口拒绝执行：{type(exc).__name__}", file=sys.stderr)
        return 2


async def export_environment(spec: str) -> dict[str, str]:
    """读取正式供应商 Owner，不选择默认模型，也不调用远端模型。"""
    from yuxi.models.providers.service import get_model_provider_by_id
    from yuxi.models.providers.cache import model_cache
    from yuxi.services.health_vision_service import current_health_model_info
    from yuxi.storage.postgres.manager import pg_manager

    provider_id, separator, model_id = spec.partition(":")
    if (
        not separator
        or not provider_id
        or not model_id
        or any(alias in model_id.lower() for alias in ("latest", "preview"))
    ):
        raise ValueError("必须明确指定固定版本供应商与模型")
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            provider = await get_model_provider_by_id(session, provider_id)
            model_cache.refresh()
            info = await current_health_model_info(session, spec)
            if provider is None or info is None or not info.api_key:
                raise ValueError("指定模型未在正式供应商和当前运行投影中就绪")
            selected = next(model for model in provider.enabled_models if model["id"] == model_id)
            values = {
                "PROVIDER_ID": provider.provider_id,
                "PROVIDER_TYPE": provider.provider_type,
                "BASE_URL": info.base_url,
                "API_KEY": info.api_key,
                "MODEL_ID": model_id,
                "HEADERS_JSON": json.dumps(provider.headers_json or {}, ensure_ascii=False),
                "EXTRA_JSON": json.dumps(provider.extra_json or {}, ensure_ascii=False),
                "MODEL_JSON": json.dumps(selected, ensure_ascii=False),
                "INCLUDE_USER_UID": "true" if provider.include_user_uid else "false",
            }
            return {"HEALTH_SAFE_PLANNER_LIVE_" + key: value for key, value in values.items()}
    finally:
        await pg_manager.close()


def read_environment_packet(raw: str) -> dict[str, str]:
    """严格解析管道字段，拒绝用输入包授予外呼开关或覆盖其它环境。"""
    if os.getenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL") != "1":
        raise ValueError("真实配餐探针未显式启用")
    packet = json.loads(raw)
    if not isinstance(packet, dict) or set(packet) != LIVE_FIELDS:
        raise ValueError("模型输入包字段不合法")
    if not all(isinstance(value, str) for value in packet.values()):
        raise ValueError("模型输入包值必须为字符串")
    return packet


if __name__ == "__main__":
    raise SystemExit(main())
