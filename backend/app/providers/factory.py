"""Factory chọn provider AI theo task (§05 mục 4)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.crypto import decrypt_secret
from app.models import ProviderConfig
from app.providers.base import LLMProvider
from app.providers.claude import ClaudeProvider
from app.providers.gemini import GeminiProvider
from app.providers.local_openai_compat import LocalOpenAICompatProvider
from app.providers.mock import MockLLMProvider
from app.providers.openai_provider import OpenAIProvider

_LLM_ADAPTERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


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
    """task_role: 'research' | 'script' | 'hook' | ... — MVP dùng chung 1 default/fallback
    cho toàn bộ task LLM (§05 mục 4); override theo project để sau (chưa cần ở M1)."""
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == "llm", ProviderConfig.enabled == True, ProviderConfig.is_default == True)  # noqa: E712
        .first()
    )
    if cfg is None:
        cfg = db.query(ProviderConfig).filter(ProviderConfig.task == "llm", ProviderConfig.enabled == True).first()
    if cfg is None:
        return MockLLMProvider()
    try:
        return build_llm_provider(cfg)
    except Exception:  # noqa: BLE001
        return MockLLMProvider()


def get_llm_with_fallback(db: Session, *, task_role: str = "default") -> LLMProvider:
    """Gọi provider chính; nếu lỗi/timeout, factory ở tầng gọi (pipeline) tự bắt exception
    và có thể gọi lại với provider is_fallback (§05 mục 6)."""
    return get_llm(db, task_role=task_role)


def get_fallback_llm(db: Session) -> LLMProvider | None:
    cfg = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.task == "llm", ProviderConfig.enabled == True, ProviderConfig.is_fallback == True)  # noqa: E712
        .first()
    )
    if cfg is None:
        return None
    try:
        return build_llm_provider(cfg)
    except Exception:  # noqa: BLE001
        return None
