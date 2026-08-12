"""Interface adapter chung cho provider AI — specs/05_ai_providers.md §3.

Pipeline chỉ phụ thuộc vào các ABC này, không biết đang gọi Claude hay Qwen local.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderStatus:
    ok: bool
    message: str = ""


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model: str = ""


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Mỗi task có một base class; mỗi provider là một adapter implement nó (§05 mục 3)."""

    provider_name: str = "base"
    model_name: str = ""

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> LLMResult:
        ...

    @abstractmethod
    def test_connection(self) -> ProviderStatus:
        ...


class TTSProvider(ABC):
    """Khai báo interface — MVP không thực thi thật (§05 mục 9), dùng ở M2."""

    provider_name: str = "base"

    @abstractmethod
    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        ...

    @abstractmethod
    def test_connection(self) -> ProviderStatus:
        ...


class ImageProvider(ABC):
    """Khai báo interface — MVP không thực thi thật, chỉ sinh prompt (§05 mục 9)."""

    provider_name: str = "base"

    @abstractmethod
    def generate(self, prompt: str) -> bytes:
        ...

    @abstractmethod
    def test_connection(self) -> ProviderStatus:
        ...


class VideoProvider(ABC):
    """Sinh video — M2 (§05 mục 9). Khác TTS/Image (đồng bộ, 1 request trả thẳng
    bytes), mọi provider video thật (Runway/Sora/Veo) đều theo mô hình BẤT ĐỒNG BỘ:
    gửi job → chờ (thường 1-5+ phút) → poll trạng thái → tải kết quả khi xong. Provider
    thực thi thật (VD `VideoProvider` cho Sora) implement `start_generation`/
    `poll_generation`; `generate()` giữ lại cho tương thích ngược/provider giả lập
    đồng bộ, nhưng provider bất đồng bộ thật PHẢI raise `NotImplementedError` ở đó và
    dùng 2 method mới — gọi qua `app/render/engine.py`, không gọi trực tiếp trong
    request handler (tránh block thread)."""

    provider_name: str = "base"

    @abstractmethod
    def generate(self, prompt: str) -> bytes:
        ...

    def start_generation(self, prompt: str, *, seconds: int = 8) -> str:
        """Gửi job sinh video, trả về job_id. Provider đồng bộ không cần override."""
        raise NotImplementedError("Provider video này không hỗ trợ start_generation (dùng generate() nếu đồng bộ).")

    def poll_generation(self, job_id: str) -> tuple[str, Optional[bytes]]:
        """Kiểm tra trạng thái job: trả (status, bytes|None). status thường là
        'queued'|'processing'|'completed'|'failed' (tuỳ provider); bytes chỉ khác None
        khi status là trạng thái hoàn tất thành công."""
        raise NotImplementedError("Provider video này không hỗ trợ poll_generation.")

    @abstractmethod
    def test_connection(self) -> ProviderStatus:
        ...


def raise_for_status_with_body(resp) -> None:
    """`httpx.Response.raise_for_status()` bỏ mất response body (thường chứa lý do lỗi
    thật — model không tồn tại, key sai quyền, hết quota...) trong message exception,
    khiến "Test kết nối" chỉ hiện được "404 Not Found" chung chung, không đủ để tự
    chẩn đoán. Dùng hàm này thay `resp.raise_for_status()` trực tiếp ở mọi adapter
    cloud để `test_connection()`/lỗi pipeline luôn kèm nội dung lỗi thật từ API."""
    if resp.status_code < 400:
        return
    try:
        detail = resp.text[:500]
    except Exception:  # noqa: BLE001
        detail = ""
    raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
