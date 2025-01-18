"""Модуль с базовыми классами для сообщений"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, AsyncGenerator, List
import time
import json


@dataclass
class IOMessage:
    """Сообщение для I/O хуков"""
    type: str = "text"           # Тип сообщения (text, stream, etc)
    content: Any = None          # Содержимое сообщения
    metadata: Dict[str, Any] = field(default_factory=dict)  # Дополнительные данные
    source: str = ""            # Источник сообщения
    timestamp: float = field(default_factory=time.time)  # Время создания
    stream: Optional[AsyncGenerator['IOMessage', None]] = None  # Стрим возвращает IOMessage
    is_async: bool = False       # Флаг асинхронного режима
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # История использованных инструментов

    @classmethod
    def create_stream(cls, generator: AsyncGenerator[Any, None], is_async: bool = True, **kwargs) -> 'IOMessage':
        """
        Создает стрим-сообщение
        
        Args:
            generator: Исходный генератор данных
            is_async: Флаг асинхронного режима
            **kwargs: Дополнительные параметры для IOMessage
            
        Returns:
            IOMessage: Сообщение со стримом
        """
        return cls(
            type="stream",
            stream=cls._wrap_generator(generator),
            is_async=is_async,
            **kwargs
        )
    
    @classmethod
    async def _wrap_generator(cls, generator: AsyncGenerator[Any, None]) -> AsyncGenerator['IOMessage', None]:
        """
        Оборачивает любой генератор в генератор IOMessage
        
        Args:
            generator: Исходный генератор данных
            
        Yields:
            IOMessage: Чанки данных в виде сообщений
        """
        async for chunk in generator:
            if isinstance(chunk, IOMessage):
                yield chunk
            else:
                yield cls(
                    type="stream_chunk",
                    content=chunk
                )

    def add_tool_call(self, tool_name: str, args: Dict[str, Any], result: Any = None, tool_id: str = None) -> None:
        """
        Добавляет информацию об использованном инструменте
        
        Args:
            tool_name: Имя инструмента
            args: Аргументы вызова
            result: Результат выполнения (опционально)
            tool_id: ID вызова (опционально)
        """
        # Сообщение от ассистента с вызовом инструмента
        tool_call = {
            "id": tool_id or f"call_{len(self.tool_calls) + 1}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(args) if isinstance(args, dict) else args
            }
        }
        
        # Результат выполнения инструмента
        tool_result = {
            "role": "tool",
            "content": json.dumps({"answer": str(result)}) if result is not None else None,
            "tool_call_id": tool_call["id"]
        }
        
        # Добавляем в историю
        self.tool_calls.append({
            "call": tool_call,
            "result": tool_result,
            "timestamp": time.time()
        })

    def get_tool_calls(self) -> List[Dict[str, Any]]:
        """
        Возвращает историю использованных инструментов
        
        Returns:
            List[Dict[str, Any]]: Список вызовов инструментов
        """
        return self.tool_calls.copy()

    def get_last_tool_call(self) -> Optional[Dict[str, Any]]:
        """
        Возвращает последний использованный инструмент
        
        Returns:
            Optional[Dict[str, Any]]: Информация о последнем вызове или None
        """
        return self.tool_calls[-1] if self.tool_calls else None

    @classmethod
    def create_error(cls, error: str, context: Dict[str, Any] = None) -> 'IOMessage':
        """
        Создает сообщение об ошибке
        
        Args:
            error: Текст ошибки
            context: Контекст ошибки
            
        Returns:
            IOMessage: Сообщение об ошибке
        """
        return cls(
            type="error",
            content=error,
            metadata=context or {}
        ) 