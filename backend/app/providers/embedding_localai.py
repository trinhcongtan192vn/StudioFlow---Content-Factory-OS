"""Embeddings qua LocalAI — CHANGE_Semantic_BRoll_Asset_Vault.md §2/§3, dùng để sinh
vector cho semantic matching Asset Vault (caption+tags+mood_tone của clip, và mô tả shot
khi tìm candidate).

**Endpoint CHƯA xác nhận chắc chắn 100%** — tài liệu chính thức
(localai.io/docs/features/embeddings/) ghi ví dụ `POST /embeddings` (KHÔNG có tiền tố
`/v1`), khác hẳn quy ước `/v1/images/generations`/`/v1/chat/completions` đã verify thật
cho 2 provider LocalAI khác trong app (`image_localai.py`/`vision_localai.py`). Theo
đúng bài học mục 77 (endpoint `/video` cũng từng đoán sai `/v1/videos`) — KHÔNG tin tài
liệu 100% khi chưa test qua LocalAI thật của người dùng: thử `/v1/embeddings` (khớp quy
ước OpenAI-compat phổ biến nhất + 2 adapter LocalAI khác trong app) TRƯỚC, tự động dự
phòng sang `/embeddings` (đúng tài liệu) nếu bản đầu trả 404."""
from __future__ import annotations

import httpx

from app.providers.base import EmbeddingProvider, ProviderStatus

_DEFAULT_BASE_URL = "http://127.0.0.1:8080"
_MODEL_NAME = "all-MiniLM-L6-v2"


class LocalAIEmbeddingProvider(EmbeddingProvider):
    provider_name = "localai_embedding"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model_name or _MODEL_NAME

    def _post(self, client: httpx.Client, path: str, body: dict) -> httpx.Response:
        return client.post(f"{self.base_url}{path}", json=body)

    def embed(self, text: str) -> list[float]:
        body = {"model": self.model_name, "input": text}
        with httpx.Client(timeout=30) as client:
            resp = self._post(client, "/v1/embeddings", body)
            if resp.status_code == 404:
                resp = self._post(client, "/embeddings", body)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data") or []
        if not items or "embedding" not in items[0]:
            raise RuntimeError("LocalAI không trả về embedding hợp lệ — kiểm tra lại model.")
        return items[0]["embedding"]

    def test_connection(self) -> ProviderStatus:
        try:
            self.embed("test")
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=f"Không kết nối được LocalAI embeddings: {e}")
