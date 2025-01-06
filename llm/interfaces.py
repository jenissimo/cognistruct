from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True


class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]


class ToolCall(BaseModel):
    """Модель для вызова инструмента"""
    tool: str  # Имя инструмента
    params: Dict[str, Any]  # Параметры вызова
    id: Optional[str] = None  # Идентификатор вызова
    index: Optional[int] = None  # Индекс вызова


class LLMResponse(BaseModel):
    """Ответ от языковой модели"""
    content: str
    tool_calls: Optional[List[ToolCall]] = None


class BaseLLM(ABC):
    """Базовый интерфейс для работы с языковыми моделями"""

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSchema]] = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Генерирует ответ на основе истории сообщений и доступных инструментов

        Args:
            messages: История сообщений в формате [{role: str, content: str}]
            tools: Список доступных инструментов
            temperature: Температура генерации (0.0 - 1.0)

        Returns:
            LLMResponse с текстом ответа и опциональными вызовами инструментов
        """
        pass 