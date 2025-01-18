from typing import Protocol, Callable, Awaitable, Optional
from cognistruct.core import IOMessage

class TelegramHandlerProtocol(Protocol):
    """Протокол для обработчика сообщений"""
    async def __call__(self, message: IOMessage, **kwargs) -> Optional[IOMessage]: ...

class TelegramPluginProtocol(Protocol):
    """Протокол для Telegram плагина"""
    async def _notify_chat_linked(self, chat_id: str, user_id: str): ... 