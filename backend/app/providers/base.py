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
    """Chỉ khai báo interface — chưa implement, M2 (§05 mục 9)."""

    provider_name: str = "base"

    @abstractmethod
    def generate(self, prompt: str) -> bytes:
        ...

    @abstractmethod
    def test_connection(self) -> ProviderStatus:
        ...
