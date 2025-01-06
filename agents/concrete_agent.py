from typing import Optional

from llm import BaseLLM
from .base_agent import BaseAgent


class ConcreteAgent(BaseAgent):
    """Конкретная реализация агента с базовым набором плагинов"""

    def __init__(
        self,
        llm: BaseLLM,
        system_prompt: Optional[str] = None
    ):
        super().__init__(llm)
        if system_prompt:
            self.conversation_history.append({
                "role": "system",
                "content": system_prompt
            })

    async def setup(self):
        """Инициализация агента с базовыми плагинами"""
        await super().setup()
        
        # Инициализируем базовые плагины
        await self.plugin_manager.init_plugin("example_plugin")  # Калькулятор
        await self.plugin_manager.init_plugin("short_term_memory")
        await self.plugin_manager.init_plugin("long_term_memory")

    async def process_message(self, message: str) -> str:
        """
        Обрабатывает входящее сообщение с дополнительной логикой
        
        В этой реализации можно добавить специфичную логику обработки,
        например, предварительную обработку сообщения или пост-обработку ответа
        """
        return await super().process_message(message) 