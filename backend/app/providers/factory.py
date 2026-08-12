"""Factory chọn provider AI theo task (§05 mục 4)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.crypto import decrypt_secret
from app.models import ProviderConfig
from app.providers.base import ImageProvider, LLMProvider, TTSProvider, VideoProvider
from app.providers.claude import ClaudeProvider
from app.providers.gemini import GeminiProvider
from app.providers.image_openai import OpenAIImageProvider
from app.providers.local_openai_compat import LocalOpenAICompatProvider
from app.providers.mock import MockLLMProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.stubs import (
    FluxImageProvider,
    GeminiImageProvider,
    GeminiTTSProvider,
    MidjourneyImageProvider,
    OpenAITTSProvider,
    RunwayVideoProvider,
    VbeeTTSProvider,
    VeoVideoProvider,
)
from app.providers.tts_elevenlabs import ElevenLabsTTSProvider
from app.providers.video_sora import SoraVideoProvider

_LLM_ADAPTERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}

_TTS_ADAPTERS = {"vbee": VbeeTTSProvider, "elevenlabs": ElevenLabsTTSProvider, "openai": OpenAITTSProvider, "gemini": GeminiTTSProvider}
_IMAGE_ADAPTERS = {"flux": FluxImageProvider, "midjourney": MidjourneyImageProvider, "openai": OpenAIImageProvider, "gemini": GeminiImageProvider}
_VIDEO_ADAPTERS = {"runway": RunwayVideoProvider, "sora": SoraVideoProvider, "veo": VeoVideoProvider}


class NoProviderConfiguredError(Exception):
    """Chưa có provider AI khả dụng cho task này, hoặc provider đã cấu hình nhưng
    không khởi tạo được — người dùng cần vào Cài đặt → Provider AI để xử lý (đã build
    theo yêu cầu: không còn âm thầm dùng Mock provider thay thế, phải cảnh báo rõ để
    người dùng chủ động cập nhật cấu hình, xem IMPLEMENTATION_REPORT.md)."""


def build_llm_provider(cfg: ProviderConfig) -> LLMProvider:
    if cfg.provider_name == "mock":
        return MockLLMProvider(model_name=cfg.model_name or "mock-deterministic")
    if cfg.connection_type == "local_endpoint":
        return LocalOpenAICompatProvider(base_url=cfg.endpoint_url or "", model_name=cfg.model_name or "")
    adapter_cls = _LLM_ADAPTERS.get(cfg.provider_name)
    if adapter_cls is None:
        raise ValueError(f"Không hỗ trợ provider LLM: {cfg.provider_name}")
    api_key = decrypt_secret(cfg.api_key_encrypted) if cfg.api_key_encrypted else ""
    return adapter_cls(api_key=api_key, model_name=cfg.model_name or "")


def get_llm(db: Session, *, task_role: str = "default") -> LLMProvider:
    """task_role: 'research' | 'script' | 'hook' | ... — MVP dùng chung 1 default cho
    toàn bộ task LLM (§05 mục 4); override theo project để sau (chưa cần ở M1).

    Raise `NoProviderConfiguredError` khi chưa có provider nào — KHÔNG tự động dùng
    Mock provider thay thế (đổi hành vi theo yêu cầu người dùng): mọi bước pipeline
    cần AI phải cảnh báo rõ ràng để người dùng chủ động vào Cài đặt cấu hình, thay vì
    âm thầm sinh nội dung giả lập."""
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == "llm", ProviderConfig.enabled == True, ProviderConfig.is_default == True)  # noqa: E712
        .first()
    )
    if cfg is None:
        cfg = db.query(ProviderConfig).filter(ProviderConfig.task == "llm", ProviderConfig.enabled == True).first()
    if cfg is None:
        raise NoProviderConfiguredError(
            "Chưa cấu hình Provider AI cho LLM. Vào Cài đặt → Provider AI để kết nối Claude/GPT/Gemini hoặc model local (Ollama/vLLM)."
        )
    try:
        return build_llm_provider(cfg)
    except Exception as e:  # noqa: BLE001
        raise NoProviderConfiguredError(
            f'Provider "{cfg.display_name}" đã cấu hình nhưng không khởi tạo được ({e}). '
            "Kiểm tra lại API key/endpoint trong Cài đặt → Provider AI."
        ) from e


def _default_config(db: Session, task: str) -> ProviderConfig | None:
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == task, ProviderConfig.enabled == True, ProviderConfig.is_default == True)  # noqa: E712
        .first()
    )
    if cfg is None:
        cfg = db.query(ProviderConfig).filter(ProviderConfig.task == task, ProviderConfig.enabled == True).first()
    return cfg


_TASK_LABEL = {"tts": "TTS", "image": "Image", "video": "Video"}


def _get_asset_provider(db: Session, task: str, adapters: dict):
    """Dùng chung cho get_tts/get_image/get_video (M2 Production Layer) — cùng pattern
    raise NoProviderConfiguredError với get_llm() khi chưa cấu hình/khởi tạo được."""
    cfg = _default_config(db, task)
    if cfg is None:
        raise NoProviderConfiguredError(
            f"Chưa cấu hình Provider AI cho {_TASK_LABEL.get(task, task)}. Vào Cài đặt → Provider AI để kết nối."
        )
    adapter_cls = adapters.get(cfg.provider_name)
    if adapter_cls is None:
        raise NoProviderConfiguredError(f'Provider "{cfg.display_name}" ({cfg.provider_name}) chưa hỗ trợ thực thi thật cho task {task}.')
    api_key = decrypt_secret(cfg.api_key_encrypted) if cfg.api_key_encrypted else ""
    try:
        if cfg.provider_name == "elevenlabs":
            return adapter_cls(api_key=api_key, model_name=cfg.model_name or "", voice_id=cfg.endpoint_url or "")
        return adapter_cls(api_key=api_key, model_name=cfg.model_name or "")
    except TypeError:
        # provider stub chỉ nhận api_key (chưa thực thi thật, không dùng model_name)
        return adapter_cls(api_key=api_key)


def get_tts(db: Session) -> TTSProvider:
    return _get_asset_provider(db, "tts", _TTS_ADAPTERS)


def get_image(db: Session) -> ImageProvider:
    return _get_asset_provider(db, "image", _IMAGE_ADAPTERS)


def get_video(db: Session) -> VideoProvider:
    return _get_asset_provider(db, "video", _VIDEO_ADAPTERS)
