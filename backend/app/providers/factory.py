"""Factory chọn provider AI theo task (§05 mục 4)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.crypto import decrypt_secret
from app.models import ProviderConfig
from app.providers.base import EmbeddingProvider, ImageProvider, LLMProvider, TTSProvider, VideoProvider, VisionProvider
from app.providers.claude import ClaudeProvider
from app.providers.embedding_localai import LocalAIEmbeddingProvider
from app.providers.embedding_ollama import OllamaEmbeddingProvider
from app.providers.gemini import GeminiProvider
from app.providers.image_comfy_sdxl import ComfySDXLImageProvider
from app.providers.image_flux import FluxImageProvider
from app.providers.image_flux_kontext import FluxKontextImageProvider
from app.providers.image_gemini import GeminiImageProvider
from app.providers.image_localai import LocalAIImageProvider
from app.providers.image_openai import OpenAIImageProvider
from app.providers.local_openai_compat import LocalOpenAICompatProvider
from app.providers.mock import MockLLMProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.stubs import (
    MidjourneyImageProvider,
    OpenAITTSProvider,
    RunwayVideoProvider,
    VbeeTTSProvider,
)
from app.providers.tts_elevenlabs import ElevenLabsTTSProvider
from app.providers.tts_gemini import GeminiTTSProvider
from app.providers.tts_omnivoice import OmniVoiceProvider
from app.providers.tts_piper import PiperTTSProvider
from app.providers.video_comfy_wan import ComfyWanVideoProvider
from app.providers.video_flux import FluxVideoProvider
from app.providers.video_localai import LocalAIVideoProvider
from app.providers.video_sora import SoraVideoProvider
from app.providers.video_veo import VeoVideoProvider
from app.providers.vision_gemini import GeminiVisionProvider
from app.providers.vision_localai import LocalAIVisionProvider
from app.providers.vision_ollama import OllamaVisionProvider

_LLM_ADAPTERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}

# `local_sdxl`/`local_wan` (ComfyUI) SONG SONG `localai_image`/`localai_video` (LocalAI,
# mới 2026-08-25, xem docstring image_localai.py/video_localai.py) — additive theo kế
# hoạch migrate đã duyệt, KHÔNG xoá adapter ComfyUI ở đợt này (chỉ xoá SAU khi verify
# thật qua GPU người dùng).
_TTS_ADAPTERS = {"vbee": VbeeTTSProvider, "elevenlabs": ElevenLabsTTSProvider, "openai": OpenAITTSProvider, "gemini": GeminiTTSProvider, "piper": PiperTTSProvider, "omnivoice": OmniVoiceProvider}
_IMAGE_ADAPTERS = {
    "flux": FluxImageProvider, "flux_kontext": FluxKontextImageProvider, "midjourney": MidjourneyImageProvider, "openai": OpenAIImageProvider, "gemini": GeminiImageProvider,
    "local_sdxl": ComfySDXLImageProvider, "localai_image": LocalAIImageProvider,
}
_VIDEO_ADAPTERS = {
    "runway": RunwayVideoProvider, "sora": SoraVideoProvider, "veo": VeoVideoProvider, "flux": FluxVideoProvider,
    "local_wan": ComfyWanVideoProvider, "localai_video": LocalAIVideoProvider,
}
# Task "vision"/"embedding" — mới (CHANGE_Semantic_BRoll_Asset_Vault.md), phục vụ
# captioning + semantic matching Channel Asset Vault. `localai_vision`/`localai_embedding`
# và `ollama_vision`/`ollama_embedding` đều là local_endpoint (base_url+model_name, không
# api_key) — cùng nhánh `_build_asset_provider` đã xử lý cho
# local_sdxl/local_wan/localai_image/localai_video, không cần thêm nhánh riêng.
# `ollama_*` thêm sau (IMPLEMENTATION_REPORT.md mục 86) khi phát hiện máy người dùng
# KHÔNG cài LocalAI — tái dùng Ollama đã chạy sẵn cho task `llm` thay vì bắt cài thêm
# 1 service mới; giữ cả `localai_*` cho người dùng nào cài LocalAI thật (provider thay
# thế được, đúng CLAUDE.md nguyên tắc #4).
_VISION_ADAPTERS = {"ollama_vision": OllamaVisionProvider, "localai_vision": LocalAIVisionProvider, "gemini_vision": GeminiVisionProvider}
_EMBEDDING_ADAPTERS = {"ollama_embedding": OllamaEmbeddingProvider, "localai_embedding": LocalAIEmbeddingProvider}

# provider_name của adapter local (connection_type=="local_endpoint") theo từng task —
# dùng ở _build_asset_provider() để biết constructor không nhận api_key (khác cloud),
# xem §05 mục 2 (mở rộng local_endpoint sang tts/image/video, trước đó chỉ llm).
_LOCAL_ASSET_PROVIDER_NAMES = {"piper"}  # local_sdxl/local_wan dùng base_url (nhánh mặc định), không cần liệt kê ở đây


class NoProviderConfiguredError(Exception):
    """Chưa có provider AI khả dụng cho task này, hoặc provider đã cấu hình nhưng
    không khởi tạo được — người dùng cần vào Cài đặt → Provider AI để xử lý (đã build
    theo yêu cầu: không còn âm thầm dùng Mock provider thay thế, phải cảnh báo rõ để
    người dùng chủ động cập nhật cấu hình, xem IMPLEMENTATION_REPORT.md)."""


def _free_local_tts_vram(db: Session) -> None:
    """Giải phóng VRAM của TTS local dùng GPU thật (hiện chỉ OmniVoice — Piper chạy CPU,
    không cần) TRƯỚC khi LLM local (Ollama) sắp nạp model — chiều ngược lại của
    `render/engine.py::_free_llm_vram_if_local`. Đo thật lúc verify OmniVoice: ComfyUI
    SDXL + OmniVoice cùng thường trú ~12.1GB/16GB (RTX 5060 Ti), Ollama nạp thêm
    qwen3:14b (~9.6GB) làm TRÀN VRAM — Research thất bại HẲN (không chỉ chậm), xem
    IMPLEMENTATION_REPORT.md mục 22. Best-effort, không raise — dọn VRAM thất bại không
    nên chặn luồng LLM chính."""
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == "tts", ProviderConfig.connection_type == "local_endpoint", ProviderConfig.provider_name == "omnivoice", ProviderConfig.enabled == True)  # noqa: E712
        .first()
    )
    if cfg is None:
        return
    try:
        OmniVoiceProvider(base_url=cfg.endpoint_url or "").unload()
    except Exception:  # noqa: BLE001
        pass


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
    if cfg.connection_type == "local_endpoint" and cfg.provider_name != "mock":
        _free_local_tts_vram(db)
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


_TASK_LABEL = {"tts": "TTS", "image": "Image", "video": "Video", "vision": "Vision", "embedding": "Embedding"}


def _build_asset_provider(cfg: ProviderConfig, adapters: dict):
    adapter_cls = adapters.get(cfg.provider_name)
    if adapter_cls is None:
        raise ValueError(f'Provider "{cfg.display_name}" ({cfg.provider_name}) chưa hỗ trợ thực thi thật.')
    if cfg.connection_type == "local_endpoint":
        # Local (§05 mục 2, mở rộng sang tts/image/video) — không dùng api_key. Piper
        # (TTS) chạy in-process, không có server nào để trỏ base_url tới (khác
        # ComfyUI dùng cho image/video local — xem app/providers/image_comfy_sdxl.py,
        # video_comfy_wan.py).
        if cfg.provider_name in _LOCAL_ASSET_PROVIDER_NAMES:
            return adapter_cls(model_name=cfg.model_name or "")
        # local_sdxl/local_wan — **mới (2026-08-22)**: giờ truyền THÊM `model_name`
        # (trước chỉ truyền `base_url`) để checkpoint SDXL đổi được qua Cài đặt → Provider
        # AI mà không cần sửa code, xem app/providers/image_comfy_sdxl.py — rỗng vẫn giữ
        # đúng hành vi mặc định cũ (constructor tự fallback về checkpoint gốc).
        return adapter_cls(base_url=cfg.endpoint_url or "", model_name=cfg.model_name or "")
    api_key = decrypt_secret(cfg.api_key_encrypted) if cfg.api_key_encrypted else ""
    try:
        if cfg.provider_name == "elevenlabs":
            return adapter_cls(api_key=api_key, model_name=cfg.model_name or "", voice_id=cfg.endpoint_url or "")
        return adapter_cls(api_key=api_key, model_name=cfg.model_name or "")
    except TypeError:
        # provider stub chỉ nhận api_key (chưa thực thi thật, không dùng model_name)
        return adapter_cls(api_key=api_key)


def _get_asset_provider(db: Session, task: str, adapters: dict):
    """Dùng chung cho get_tts/get_image/get_video — CHỈ lấy 1 provider (default), dùng
    ở `routers/providers.py::test_provider`. Sinh asset thật dùng `_get_asset_chain()`
    bên dưới (có fallback) thay vì hàm này."""
    cfg = _default_config(db, task)
    if cfg is None:
        raise NoProviderConfiguredError(
            f"Chưa cấu hình Provider AI cho {_TASK_LABEL.get(task, task)}. Vào Cài đặt → Provider AI để kết nối."
        )
    try:
        return _build_asset_provider(cfg, adapters)
    except Exception as e:  # noqa: BLE001
        raise NoProviderConfiguredError(f'Provider "{cfg.display_name}" đã cấu hình nhưng không khởi tạo được ({e}).') from e


def get_tts(db: Session) -> TTSProvider:
    return _get_asset_provider(db, "tts", _TTS_ADAPTERS)


def get_image(db: Session) -> ImageProvider:
    return _get_asset_provider(db, "image", _IMAGE_ADAPTERS)


def get_video(db: Session) -> VideoProvider:
    return _get_asset_provider(db, "video", _VIDEO_ADAPTERS)


def get_vision(db: Session) -> VisionProvider:
    return _get_asset_provider(db, "vision", _VISION_ADAPTERS)


def get_embedding(db: Session) -> EmbeddingProvider:
    return _get_asset_provider(db, "embedding", _EMBEDDING_ADAPTERS)


def _candidate_configs(db: Session, task: str) -> list[ProviderConfig]:
    """Danh sách provider theo thứ tự thử: mặc định trước, fallback sau (nếu có VÀ
    khác mặc định) — cho sinh asset thật tự động thử provider fallback khi provider
    mặc định gọi API lỗi thật (không chỉ thiếu cấu hình). Trước đây `is_fallback` chỉ
    là cờ lưu DB không ai đọc — đây là chỗ đầu tiên thật sự dùng nó. Không có
    default/fallback -> fallback về "bất kỳ provider enabled" (giữ hành vi cũ)."""
    default = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == task, ProviderConfig.enabled == True, ProviderConfig.is_default == True)  # noqa: E712
        .first()
    )
    fallback = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == task, ProviderConfig.enabled == True, ProviderConfig.is_fallback == True)  # noqa: E712
        .first()
    )
    configs: list[ProviderConfig] = []
    for c in (default, fallback):
        if c and c.id not in [x.id for x in configs]:
            configs.append(c)
    if not configs:
        any_enabled = db.query(ProviderConfig).filter(ProviderConfig.task == task, ProviderConfig.enabled == True).first()  # noqa: E712
        if any_enabled:
            configs.append(any_enabled)
    return configs


def _get_asset_chain(db: Session, task: str, adapters: dict) -> list:
    """Trả về danh sách provider ĐÃ KHỞI TẠO theo thứ tự ưu tiên (default rồi
    fallback) — dùng ở app/render/engine.py + app/routers/pack.py để tự động thử
    provider kế tiếp khi provider hiện tại gọi API lỗi thật. Bỏ qua config nào khởi
    tạo lỗi (VD provider chưa hỗ trợ), chỉ raise `NoProviderConfiguredError` khi
    KHÔNG có provider nào khởi tạo được."""
    configs = _candidate_configs(db, task)
    if not configs:
        raise NoProviderConfiguredError(
            f"Chưa cấu hình Provider AI cho {_TASK_LABEL.get(task, task)}. Vào Cài đặt → Provider AI để kết nối."
        )
    providers = []
    build_errors = []
    for cfg in configs:
        try:
            providers.append(_build_asset_provider(cfg, adapters))
        except Exception as e:  # noqa: BLE001
            build_errors.append(f"{cfg.display_name}: {e}")
    if not providers:
        raise NoProviderConfiguredError(
            f"Không khởi tạo được provider nào cho {_TASK_LABEL.get(task, task)} — " + "; ".join(build_errors)
        )
    return providers


def get_tts_chain(db: Session) -> list[TTSProvider]:
    return _get_asset_chain(db, "tts", _TTS_ADAPTERS)


def get_image_chain(db: Session) -> list[ImageProvider]:
    return _get_asset_chain(db, "image", _IMAGE_ADAPTERS)


def get_video_chain(db: Session) -> list[VideoProvider]:
    return _get_asset_chain(db, "video", _VIDEO_ADAPTERS)
