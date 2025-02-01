from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass

from pydantic import BaseModel

from cognistruct.core.context import RequestContext


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True


@dataclass
class ToolSchema:
    """Схема инструмента для LLM"""
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolCall(BaseModel):
    """Модель для вызова инструмента"""
    tool: str  # Имя инструмента
    params: Dict[str, Any]  # Параметры вызова
    id: Optional[str] = None  # Идентификатор вызова
    index: Optional[int] = None  # Индекс вызова
    context: Optional[RequestContext] = None  # Контекст вызова


class StreamChunk(BaseModel):
    """Чанк данных при стриминге"""
    content: str  # Текстовый контент
    delta: str  # Новый контент в этом чанке
    tool_call: Optional[ToolCall] = None  # Вызов инструмента если есть
    tool_result: Optional[str] = None  # Результат выполнения инструмента
    is_complete: bool = False  # Флаг завершения генерации
    context: Optional[RequestContext] = None  # Контекст чанка


@dataclass
class LLMResponse:
    """Ответ от LLM"""
    content: str
    tool_calls: List[Dict[str, Any]] = None
    tool_messages: Optional[List[Dict[str, Any]]] = None  # История взаимодействия с инструментами
    context: Optional[RequestContext] = None  # Контекст ответа


class BaseLLM(ABC):
    """Базовый класс для работы с LLM"""
    
    @abstractmethod
    def set_tool_executor(self, executor):
        """Устанавливает функцию для выполнения инструментов"""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSchema]] = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, AsyncGenerator[Any, None]]:
        """Генерирует ответ от LLM"""
        pass
        
    @abstractmethod
    async def close(self):
        """Закрывает соединение с LLM"""
        pass 