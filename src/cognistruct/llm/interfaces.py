from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, AsyncGenerator

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


class StreamChunk(BaseModel):
    """Чанк данных при стриминге"""
    content: str  # Текстовый контент
    delta: str  # Новый контент в этом чанке
    tool_call: Optional[ToolCall] = None  # Вызов инструмента если есть
    tool_result: Optional[str] = None  # Результат выполнения инструмента
    is_complete: bool = False  # Флаг завершения генерации


class LLMResponse(BaseModel):
    """Ответ от языковой модели"""
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_messages: Optional[List[Dict[str, Any]]] = None  # История взаимодействия с инструментами


class BaseLLM(ABC):
    """Базовый интерфейс для работы с языковыми моделями"""
    
    @abstractmethod
    def set_tool_executor(self, executor):
        """Устанавливает функцию для выполнения инструментов"""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSchema]] = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, AsyncGenerator[StreamChunk, None]]:
        """
        Генерирует ответ на основе истории сообщений и доступных инструментов

        Args:
            messages: История сообщений в формате [{role: str, content: str}]
            tools: Список доступных инструментов
            temperature: Температура генерации (0.0 - 1.0)
            stream: Использовать потоковую генерацию
            **kwargs: Дополнительные параметры

        Returns:
            - При stream=False: LLMResponse с текстом ответа и опциональными вызовами инструментов
            - При stream=True: AsyncGenerator[StreamChunk, None] для потоковой генерации
        """
        pass
        
    @abstractmethod
    async def close(self):
        """Закрывает соединение с API"""
        pass 