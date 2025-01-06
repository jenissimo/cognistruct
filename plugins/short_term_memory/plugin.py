from typing import Dict, Any

from plugins.base_plugin import BasePlugin, PluginMetadata


class ShortTermMemoryPlugin(BasePlugin):
    """Плагин для хранения краткосрочной памяти (последних сообщений)"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="short_term_memory",
            version="1.0.0",
            description="Хранит последние сообщения чата",
            priority=90  # Высокий приоритет для контекста
        )

    async def rag_hook(self, query: str) -> Dict[str, Any]:
        # В базовой реализации просто возвращаем пустой контекст
        return {} 