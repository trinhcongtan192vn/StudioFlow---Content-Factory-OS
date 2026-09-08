"""Embeddings qua Ollama (local, đã cài sẵn cho task `llm`) — bổ sung sau khi phát hiện
máy người dùng KHÔNG cài LocalAI (xem `vision_ollama.py` cho bối cảnh đầy đủ). Ollama hỗ
trợ `/v1/embeddings` qua shim OpenAI-compat — đã verify thật với model `nomic-embed-text`
(~274MB, nhẹ hơn nhiều so với `all-MiniLM-L6-v2` mặc định của phương án LocalAI ban đầu
nhưng cùng mục đích: vector ngắn cho semantic matching text, không cần model lớn)."""
from __future__ import annotations

import httpx

from app.providers.base import EmbeddingProvider, ProviderStatus
from app.providers.gpu_lock import gpu_lock

_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
_MODEL_NAME = "nomic-embed-text"


class OllamaEmbeddingProvider(EmbeddingProvider):
    provider_name = "ollama_embedding"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model_name or _MODEL_NAME

    def embed(self, text: str) -> list[float]:
        body = {"model": self.model_name, "input": text}
        with gpu_lock, httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/embeddings", json=body)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data") or []
        if not items or "embedding" not in items[0]:
            raise RuntimeError("Ollama không trả về embedding hợp lệ — kiểm tra lại model.")
        return items[0]["embedding"]

    def test_connection(self) -> ProviderStatus:
        try:
            self.embed("test")
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=f"Không kết nối được Ollama embeddings: {e}")
