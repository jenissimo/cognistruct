from typing import Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from cognistruct.core.messages import IOMessage
import time
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

@dataclass
class AppContext:
    """Глобальный контекст приложения"""
    user_id: int = 0  # 0 = дефолтный пользователь
    
    
class GlobalContext:
    """Синглтон для хранения глобального контекста"""
    _instance: Optional[AppContext] = None
    
    @classmethod
    def get(cls) -> AppContext:
        """Получить текущий контекст"""
        if cls._instance is None:
            cls._instance = AppContext()
        return cls._instance
    
    @classmethod
    def set_user_id(cls, user_id: int):
        """Установить текущего пользователя"""
        ctx = cls.get()
        ctx.user_id = user_id
        
    @classmethod
    def reset(cls):
        """Сбросить контекст"""
        cls._instance = None 

@dataclass
class RequestContext:
    """Контекст запроса, содержащий информацию о пользователе и метаданные"""
    user_id: str
    metadata: Dict[str, Any] = None
    timestamp: float = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует контекст в словарь"""
        return {
            "user_id": self.user_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RequestContext':
        """Создает контекст из словаря"""
        return cls(
            user_id=data["user_id"],
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp")
        )

    def merge(self, other: 'RequestContext') -> 'RequestContext':
        """Объединяет два контекста, сохраняя user_id текущего"""
        return RequestContext(
            user_id=self.user_id,
            metadata={**self.metadata, **other.metadata},
            timestamp=other.timestamp or self.timestamp
        )

    def with_metadata(self, **kwargs) -> 'RequestContext':
        """Создает новый контекст с дополнительными метаданными"""
        return RequestContext(
            user_id=self.user_id,
            metadata={**self.metadata, **kwargs},
            timestamp=self.timestamp
        )

    @classmethod
    def from_message(cls, message: "IOMessage") -> "RequestContext":
        """Создает контекст из сообщения"""
        metadata = message.metadata
        
        # Пытаемся получить user_id разными способами
        user_id = (
            metadata.get("user_id") or
            metadata.get("user_context", {}).get("user_id") or
            metadata.get("telegram", {}).get("user_id")
        )
        
        if not user_id:
            raise ValueError("Cannot create context: no user_id found in message metadata")
            
        return cls(
            user_id=user_id,
            metadata=metadata
        ) 

class ContextMiddleware(ABC):
    """Базовый класс для проверки и валидации контекста в сообщениях"""

    async def input_hook(self, message) -> bool:
        """Проверяет наличие и валидность контекста во входящем сообщении"""
        # Импортируем здесь чтобы избежать циркулярного импорта
        from .messages import IOMessage
        
        if not isinstance(message, IOMessage):
            logger.warning("Message is not an instance of IOMessage")
            return True

        if not message.context:
            logger.warning("Message has no context")
            return True

        if not self._validate_context(message.context):
            logger.warning("Invalid context in message")
            return True

        return True

    async def streaming_output_hook(self, message) -> AsyncGenerator:
        """Копирует контекст в стриминговые чанки"""
        # Импортируем здесь чтобы избежать циркулярного импорта
        from .messages import IOMessage
        
        if not isinstance(message, IOMessage):
            yield message
            return

        if not hasattr(message, 'stream') or not message.stream:
            yield message
            return

        async for chunk in message.stream:
            if isinstance(chunk, IOMessage) and message.context:
                chunk.context = message.context
            yield chunk

    def _validate_context(self, context: RequestContext) -> bool:
        """Проверяет валидность контекста"""
        if not context.user_id:
            return False
        if not isinstance(context.metadata, dict):
            return False
        return True 