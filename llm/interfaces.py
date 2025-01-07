from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, AsyncGenerator, Union

@dataclass
class ToolSchema:
    """Схема инструмента для LLM"""
    name: str
    description: str
    parameters: Dict[str, Any]

@dataclass
class LLMResponse:
    """Ответ от LLM"""
    content: str
    tool_messages: Optional[List[Dict[str, Any]]] = None
    is_complete: bool = True  # Флаг завершенности для стриминга

@dataclass
class LLMStreamChunk:
    """Чанк данных при стриминге"""
    content: str
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    is_complete: bool = False

class BaseLLM(ABC):
    """Базовый класс для всех LLM провайдеров"""
    
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
        response_format: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, AsyncGenerator[LLMStreamChunk, None]]:
        """
        Генерирует ответ на основе сообщений
        
        Args:
            messages: История сообщений
            tools: Доступные инструменты
            temperature: Температура генерации
            response_format: Формат ответа (например, "json")
            stream: Использовать потоковую генерацию
            **kwargs: Дополнительные параметры
            
        Returns:
            LLMResponse или AsyncGenerator[LLMStreamChunk, None] при stream=True
        """
        pass
        
    @abstractmethod
    async def close(self):
        """Закрывает соединение с API"""
        pass 