from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.llm.client_factory import LLMClientFactory  # noqa: E402


DEFAULT_BASE_URL = "https://api.vectorengine.cn/v1"
DEFAULT_CHAT_MODEL = "gemini-3.1-pro-preview"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


class SmokeFailure(RuntimeError):
    def __init__(self, message: str, attempts: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


@dataclass
class SmokeResult:
    ok: bool
    base_url: str
    chat_model: str
    image_model: str
    chat_key_id: int | str | None
    image_key_id: int | str | None
    chat_elapsed_s: float | None
    image_elapsed_s: float | None
    generated_prompt: str | None
    image_path: str | None
    image_format: str | None
    image_width: int | None
    image_height: int | None
    image_bytes: int | None
    attempts: list[dict[str, Any]]
    error: str | None
    timestamp_utc: str


@dataclass
class ApiConfig:
    key_id: int | str
    model_type: str
    provider: str
    api_key: str
    base_url: str
    model: str
    priority: int = 0


def _read_single_api_key(args: argparse.Namespace) -> str:
    if args.api_key_env:
        key = os.getenv(args.api_key_env, "").strip()
        if key:
            return key
    for name in ("VECTORENGINE_API_KEY", "OPENAI_API_KEY"):
        key = os.getenv(name, "").strip()
        if key:
            return key
    raise RuntimeError(
        "Missing API key. Set VECTORENGINE_API_KEY or pass --api-key-env NAME."
    )


def _load_configs(args: argparse.Namespace) -> list[ApiConfig]:
    raw = os.getenv(args.configs_env, "").strip() if args.configs_env else ""
    configs: list[ApiConfig] = []
    if raw:
        for idx, item in enumerate(json.loads(raw)):
            api_key = str(item.get("api_key", "")).strip()
            if not api_key:
                continue
            configs.append(
                ApiConfig(
                    key_id=item.get("id", item.get("key_id", idx)),
                    model_type=str(item.get("model_type", "")).strip(),
                    provider=str(item.get("provider", "openai_compat")).strip(),
                    api_key=api_key,
                    base_url=str(item.get("base_url") or args.base_url).rstrip("/"),
                    model=str(item.get("model") or item.get("model_name") or "").strip(),
                    priority=int(item.get("priority") or 0),
                )
            )

    if configs:
        return sorted(configs, key=lambda cfg: cfg.priority, reverse=True)

    api_key = _read_single_api_key(args)
    return [
        ApiConfig(
            key_id="env-chat",
            model_type="chat",
            provider="openai_compat",
            api_key=api_key,
            base_url=args.base_url.rstrip("/"),
            model=args.chat_model,
        ),
        ApiConfig(
            key_id="env-image",
            model_type="image",
            provider="openai_compat",
            api_key=api_key,
            base_url=args.base_url.rstrip("/"),
            model=args.image_model,
        ),
    ]


def _select_configs(
    configs: list[ApiConfig],
    *,
    model_type: str,
    model: str,
    base_url: str,
) -> list[ApiConfig]:
    selected = [
        cfg
        for cfg in configs
        if cfg.model_type == model_type
        and cfg.provider == "openai_compat"
        and cfg.model == model
    ]
    if not selected:
        selected = [
            cfg
            for cfg in configs
            if cfg.model_type == model_type and cfg.provider == "openai_compat"
        ]
    return [
        ApiConfig(
            key_id=cfg.key_id,
            model_type=cfg.model_type,
            provider=cfg.provider,
            api_key=cfg.api_key,
            base_url=base_url.rstrip("/") if base_url else cfg.base_url,
            model=model or cfg.model,
            priority=cfg.priority,
        )
        for cfg in selected
    ]


def _ensure_png_or_jpeg(image_bytes: bytes, output_path: Path) -> tuple[str, int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    with Image.open(output_path) as img:
        fmt = img.format or "unknown"
        width, height = img.size
        img.verify()
    return fmt, width, height


def _strip_secret_like_values(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    for key in list(sanitized):
        normalized = key.lower()
        if normalized in {"api_key", "access_token", "refresh_token", "secret"}:
            sanitized[key] = "[redacted]"
    return sanitized


def _summarize_error(exc: Exception) -> tuple[str, int | None, bool]:
    status_code = None
    retryable = True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        retryable = status_code == 429 or 500 <= status_code <= 599
    elif isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        retryable = True
    else:
        retryable = True
    return str(exc), status_code, retryable


async def _run_with_polling(
    *,
    stage: str,
    configs: list[ApiConfig],
    max_rounds: int,
    retry_delay_s: float,
    attempts: list[dict[str, Any]],
    call,
) -> tuple[Any, ApiConfig, float]:
    if not configs:
        raise RuntimeError(f"No {stage} configs available")

    last_error = None
    for round_index in range(1, max_rounds + 1):
        for config in configs:
            started = time.perf_counter()
            record: dict[str, Any] = {
                "stage": stage,
                "round": round_index,
                "key_id": config.key_id,
                "provider": config.provider,
                "base_url": config.base_url,
                "model": config.model,
                "ok": False,
                "status_code": None,
                "elapsed_s": None,
                "error": None,
            }
            try:
                result = await call(config)
                elapsed = time.perf_counter() - started
                record["ok"] = True
                record["elapsed_s"] = round(elapsed, 3)
                attempts.append(record)
                return result, config, elapsed
            except Exception as exc:
                elapsed = time.perf_counter() - started
                message, status_code, retryable = _summarize_error(exc)
                record["status_code"] = status_code
                record["elapsed_s"] = round(elapsed, 3)
                record["error"] = message
                attempts.append(record)
                last_error = exc
                if not retryable:
                    break

        if round_index < max_rounds:
            await asyncio.sleep(retry_delay_s)

    raise SmokeFailure(
        f"All {stage} configs failed after {max_rounds} rounds. Last error: {last_error}",
        attempts,
    )


async def run_smoke(args: argparse.Namespace) -> SmokeResult:
    base_url = args.base_url.rstrip("/")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).resolve()
    image_path = output_dir / f"vectorengine-smoke-{timestamp}.png"

    configs = _load_configs(args)
    chat_configs = _select_configs(
        configs,
        model_type="chat",
        model=args.chat_model,
        base_url=base_url,
    )
    image_configs = _select_configs(
        configs,
        model_type="image",
        model=args.image_model,
        base_url=base_url,
    )
    attempts: list[dict[str, Any]] = []

    prompt_seed = (
        "Create one concise English image prompt for a clean academic figure. "
        "The figure should show a two-stage paper understanding pipeline: "
        "text analysis with a pro model, then image synthesis with a flash image model. "
        "Return only the prompt, no markdown."
    )

    if args.static_prompt:
        generated_prompt = " ".join(args.static_prompt.strip().split())
        chat_config = ApiConfig(
            key_id="static-prompt",
            model_type="chat",
            provider="openai_compat",
            api_key="",
            base_url=base_url,
            model=args.chat_model,
        )
        chat_elapsed = None
    else:
        async def chat_call(config: ApiConfig) -> str:
            client = LLMClientFactory.create(
                provider=config.provider,
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
            )
            return await client.chat(
                [{"role": "user", "content": prompt_seed}],
                temperature=0.2,
                max_tokens=args.chat_max_tokens,
            )

        generated_prompt, chat_config, chat_elapsed = await _run_with_polling(
            stage="chat",
            configs=chat_configs,
            max_rounds=args.max_rounds,
            retry_delay_s=args.retry_delay_s,
            attempts=attempts,
            call=chat_call,
        )
    generated_prompt = " ".join(generated_prompt.strip().split())
    if not generated_prompt:
        raise RuntimeError("Chat model returned an empty prompt")

    async def image_call(config: ApiConfig) -> bytes | None:
        client = LLMClientFactory.create(
            provider=config.provider,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )
        image = await client.generate_image(
            generated_prompt,
            image_model=config.model,
            aspect_ratio=args.aspect_ratio,
            image_size=args.image_size,
        )
        if not image:
            raise RuntimeError("Image model returned no image bytes")
        return image

    image_bytes, image_config, image_elapsed = await _run_with_polling(
        stage="image",
        configs=image_configs,
        max_rounds=args.max_rounds,
        retry_delay_s=args.retry_delay_s,
        attempts=attempts,
        call=image_call,
    )
    image_format, width, height = _ensure_png_or_jpeg(image_bytes, image_path)
    if width < 64 or height < 64:
        raise RuntimeError(f"Image dimensions look invalid: {width}x{height}")

    return SmokeResult(
        ok=True,
        base_url=base_url,
        chat_model=args.chat_model,
        image_model=args.image_model,
        chat_key_id=chat_config.key_id,
        image_key_id=image_config.key_id,
        chat_elapsed_s=round(chat_elapsed, 3) if chat_elapsed is not None else None,
        image_elapsed_s=round(image_elapsed, 3),
        generated_prompt=generated_prompt,
        image_path=str(image_path),
        image_format=image_format,
        image_width=width,
        image_height=height,
        image_bytes=len(image_bytes),
        attempts=attempts,
        error=None,
        timestamp_utc=timestamp,
    )


async def main_async(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "vectorengine-smoke-latest.json"

    try:
        result = await run_smoke(args)
        report = asdict(result)
        report_path.write_text(
            json.dumps(_strip_secret_like_values(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        attempts = getattr(exc, "attempts", [])
        result = SmokeResult(
            ok=False,
            base_url=args.base_url.rstrip("/"),
            chat_model=args.chat_model,
            image_model=args.image_model,
            chat_key_id=None,
            image_key_id=None,
            chat_elapsed_s=None,
            image_elapsed_s=None,
            generated_prompt=None,
            image_path=None,
            image_format=None,
            image_width=None,
            image_height=None,
            image_bytes=None,
            attempts=attempts,
            error=str(exc),
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        )
        report_path.write_text(
            json.dumps(_strip_secret_like_values(asdict(result)), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test PaperScholar's OpenAI-compatible client against "
            "VectorEngine chat-completions text and image models."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)
    parser.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--aspect-ratio", default="1:1")
    parser.add_argument("--image-size", default="1K")
    parser.add_argument("--api-key-env", default="")
    parser.add_argument(
        "--configs-env",
        default="VECTORENGINE_SMOKE_CONFIGS",
        help=(
            "Environment variable containing JSON API configs. Each item needs "
            "model_type, provider, api_key, base_url, and model/model_name."
        ),
    )
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--retry-delay-s", type=float, default=15.0)
    parser.add_argument("--chat-max-tokens", type=int, default=180)
    parser.add_argument(
        "--static-prompt",
        default="",
        help="Use this image prompt directly and skip the chat-model prompt-generation stage.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT.parent / "reports" / "vectorengine-smoke"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))
