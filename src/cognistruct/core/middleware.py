from typing import Optional, AsyncGenerator
import logging
from .base_plugin import BasePlugin
from .messages import IOMessage
from .context import RequestContext

logger = logging.getLogger(__name__)

class ContextMiddleware(BasePlugin):
    """
    Middleware для проверки и валидации контекста в сообщениях.
    Блокирует сообщения без контекста и следит за его корректностью.
    """
    
    def __init__(self):
        super().__init__()
        
    async def input_hook(self, message: IOMessage) -> bool:
        """
        Проверяет наличие и валидность контекста во входящем сообщении.
        Возвращает True если сообщение нужно заблокировать.
        """
        if not message.context:
            logger.warning("Message has no context, blocking")
            return True

        if not self._validate_context(message.context):
            logger.warning("Invalid context in message, blocking")
            return True

        return False

    async def streaming_output_hook(self, message: IOMessage) -> AsyncGenerator[IOMessage, None]:
        """
        Копирует контекст в каждый чанк стрима.
        """
        if not message.stream:
            yield message
            return

        async for chunk in message.stream:
            if not chunk.context and message.context:
                chunk.context = message.context
            yield chunk

    def _validate_context(self, context: RequestContext) -> bool:
        """
        Проверяет валидность контекста.
        """
        if not context.user_id:
            logger.warning("Context missing user_id")
            return False

        if not isinstance(context.metadata, dict):
            logger.warning("Context metadata is not a dictionary")
            return False

        return True 