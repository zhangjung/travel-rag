from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import uvicorn
from huggingface_hub import snapshot_download

from travel_rag.api import create_app
from travel_rag.config import PROJECT_ROOT, Settings
from travel_rag.domain.models import Pace, TravelRequest
from travel_rag.observability import configure_logging
from travel_rag.rag.factory import create_knowledge_base
from travel_rag.workflow import create_workflow

DEMO_DIR = PROJECT_ROOT / "data" / "demo"
LOGGER = logging.getLogger(__name__)


def ingest_demo(settings: Settings, mode: str) -> dict[str, int]:
    kb_mode = "mock" if mode == "mock" else "local"
    knowledge_base = create_knowledge_base(settings, kb_mode)
    return {
        "cases": knowledge_base.ingest_jsonl("cases", DEMO_DIR / "cases.jsonl"),
        "experiences": knowledge_base.ingest_jsonl("experiences", DEMO_DIR / "experiences.jsonl"),
    }


def demo_request() -> TravelRequest:
    return TravelRequest(
        destination="北京",
        days=4,
        budget_cny=6000,
        travelers=["2位成人", "1名儿童"],
        interests=["历史", "亲子"],
        pace=Pace.RELAXED,
        constraints=["每天仅一个高体力核心景点", "午间需要休息"],
    )


def download_models(settings: Settings) -> dict[str, str]:
    common_patterns = [
        "*.json",
        "*.txt",
        "*.model",
        "*.safetensors",
        "1_Pooling/*",
    ]
    embedding_path = snapshot_download(
        repo_id=settings.embedding_model,
        revision=settings.embedding_revision,
        cache_dir=settings.hf_home,
        allow_patterns=common_patterns,
        max_workers=1,
    )
    reranker_path = snapshot_download(
        repo_id=settings.reranker_model,
        revision=settings.reranker_revision,
        cache_dir=settings.hf_home,
        allow_patterns=common_patterns,
        max_workers=1,
    )
    return {"embedding": embedding_path, "reranker": reranker_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="travel-rag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-demo", help="幂等写入 Demo 知识库")
    ingest.add_argument("--mode", choices=["mock", "local"], required=True)

    subparsers.add_parser(
        "download-models",
        help="按锁定 revision 下载必要 Safetensors 到 D 盘缓存",
    )

    demo = subparsers.add_parser("demo", help="运行北京四日最小实例")
    group = demo.add_mutually_exclusive_group(required=True)
    group.add_argument("--mock", action="store_true")
    group.add_argument("--live", action="store_true")
    demo.add_argument("--output", type=Path)

    serve = subparsers.add_parser("serve", help="启动 FastAPI 与网页")
    serve.add_argument("--mode", choices=["mock", "live"], required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    selected_mode = getattr(args, "mode", None)
    if args.command == "ingest-demo":
        selected_mode = "live" if args.mode == "local" else "mock"
    if args.command == "demo":
        selected_mode = "live" if args.live else "mock"
    settings = Settings(app_mode=selected_mode or "mock")
    configure_logging(settings.log_dir, settings.log_level)

    if args.command == "ingest-demo":
        counts = ingest_demo(settings, args.mode)
        print(json.dumps({"mode": args.mode, "ingested": counts}, ensure_ascii=False, indent=2))
        return

    if args.command == "download-models":
        paths = download_models(settings)
        print(json.dumps(paths, ensure_ascii=False, indent=2))
        return

    if args.command == "demo":
        mode = "live" if args.live else "mock"
        workflow = create_workflow(settings, mode)
        response = workflow.run(demo_request())
        payload = response.model_dump_json(indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
            print(f"结果已写入：{args.output.resolve()}")
        else:
            print(payload)
        return

    if args.command == "serve":
        uvicorn.run(
            create_app(settings=settings, mode=args.mode),
            host=args.host,
            port=args.port,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOGGER.exception(
            "cli_failed",
            extra={
                "event": {
                    "command": " ".join(sys.argv[1:]),
                    "error_type": sys.exc_info()[0].__name__ if sys.exc_info()[0] else None,
                }
            },
        )
        raise
