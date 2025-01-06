from typing import Dict, Any

from plugins.base_plugin import BasePlugin, PluginMetadata


class LongTermMemoryPlugin(BasePlugin):
    """Плагин для хранения долгосрочной памяти (важных фактов)"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="long_term_memory",
            version="1.0.0",
            description="Хранит важные факты с возможностью поиска",
            priority=80  # Высокий приоритет, но ниже чем у краткосрочной памяти
        )

    async def rag_hook(self, query: str) -> Dict[str, Any]:
        # В базовой реализации просто возвращаем пустой контекст
        return {} 