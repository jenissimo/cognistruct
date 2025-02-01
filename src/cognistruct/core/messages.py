"""Модуль с базовыми классами для сообщений"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, AsyncGenerator, List, TYPE_CHECKING
import time
import json

if TYPE_CHECKING:
    from .context import RequestContext


@dataclass
class IOMessage:
    """
    Универсальный формат сообщения для обмена между компонентами системы.
    Поддерживает как обычные сообщения, так и стриминг.
    
    Attributes:
        type: Тип сообщения (например, "text", "image", "audio")
        content: Содержимое сообщения
        metadata: Дополнительные данные (например, для Telegram - reply_to, inline_keyboard)
        source: Источник сообщения (например, "telegram", "console", "llm")
        is_async: Флаг асинхронности (для стриминга)
        stream: Генератор для стриминга
        tool_calls: История вызовов инструментов
        context: Контекст запроса
    """
    type: str
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    is_async: bool = False
    stream: Optional[AsyncGenerator['IOMessage', None]] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    context: Optional['RequestContext'] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.tool_calls is None:
            self.tool_calls = []

    @property
    def context(self) -> Optional['RequestContext']:
        """Получить контекст сообщения."""
        return self._context

    @context.setter
    def context(self, value: Optional['RequestContext']):
        """Установить контекст сообщения."""
        self._context = value

    def with_context(self, context: Optional['RequestContext']) -> 'IOMessage':
        """Создает копию сообщения с новым контекстом"""
        msg = self.copy()
        msg.context = context
        return msg

    def copy(self) -> 'IOMessage':
        """Создает копию сообщения"""
        return IOMessage(
            type=self.type,
            content=self.content,
            metadata=self.metadata.copy(),
            source=self.source,
            is_async=self.is_async,
            stream=self.stream,
            tool_calls=self.tool_calls.copy(),
            context=self.context
        )

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
        context = kwargs.pop('context', None)
        return cls(
            type="stream",
            stream=cls._wrap_generator(generator, context=context),
            is_async=is_async,
            context=context,
            **kwargs
        )
    
    @classmethod
    async def _wrap_generator(cls, generator: AsyncGenerator[Any, None], context: Optional['RequestContext'] = None) -> AsyncGenerator['IOMessage', None]:
        """
        Оборачивает любой генератор в генератор IOMessage
        
        Args:
            generator: Исходный генератор данных
            context: Контекст для чанков
            
        Yields:
            IOMessage: Чанки данных в виде сообщений
        """
        async for chunk in generator:
            if isinstance(chunk, IOMessage):
                if context and not chunk.context:
                    chunk.context = context
                yield chunk
            else:
                yield cls(
                    type="stream_chunk",
                    content=chunk,
                    context=context
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