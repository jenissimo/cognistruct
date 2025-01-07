import asyncio
from typing import Optional, Callable, Awaitable
from rich.console import Console
from rich.markdown import Markdown

from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage


class ConsolePlugin(BasePlugin):
    """Плагин для работы с консольным вводом/выводом"""
    
    def __init__(self, 
                 prompt: str = "👤 ",
                 exit_command: str = "exit",
                 exit_message: str = "\n👋 До свидания!",
                 use_markdown: bool = True,
                 use_emojis: bool = True):
        """
        Args:
            prompt: Строка приглашения ввода
            exit_command: Команда для выхода
            exit_message: Сообщение при выходе
            use_markdown: Использовать форматирование Markdown
            use_emojis: Использовать эмодзи в выводе
        """
        super().__init__()
        self.prompt = prompt
        self.exit_command = exit_command
        self.exit_message = exit_message
        self.use_markdown = use_markdown
        self.use_emojis = use_emojis
        self.message_handler: Optional[Callable[[IOMessage], Awaitable[None]]] = None
        self._running = False
        self.console = Console()
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="console",
            description="Обработка консольного ввода/вывода",
            version="1.0.0",
            priority=100  # Высокий приоритет для I/O
        )
        
    def set_message_handler(self, handler: Callable[[IOMessage], Awaitable[None]]):
        """Устанавливает обработчик сообщений"""
        self.message_handler = handler
        
    async def start(self):
        """Запускает обработку консольного ввода"""
        self._running = True
        
        while self._running:
            try:
                user_input = input(self.prompt).strip()
                
                if user_input.lower() == self.exit_command:
                    print(self.exit_message)
                    break
                    
                # Создаем сообщение
                message = IOMessage(
                    type="console_input",
                    content=user_input,
                    source="console"
                )
                
                # Передаем сообщение обработчику
                if self.message_handler:
                    await self.message_handler(message)
                    
            except KeyboardInterrupt:
                # Очищаем буфер ввода и печатаем новую строку
                print("\033[2K\033[G", end="")
                print("\n👋 Работа прервана пользователем")
                break
                
        self._running = False
        
    async def stop(self):
        """Останавливает обработку ввода"""
        self._running = False
        
    def format_output(self, content: str) -> str:
        """Форматирует текст для вывода"""
        if not self.use_emojis:
            # Убираем эмодзи если они отключены
            content = content.replace("🤖", "Bot:")
            
        return content
        
    async def output_hook(self, message: IOMessage):
        """Выводит сообщения в консоль"""
        if message.type in ["message", "text"]:
            prefix = "🤖 " if self.use_emojis else "Bot: "
            content = self.format_output(message.content)
            
            # Добавляем отступы
            print()
            if self.use_markdown:
                # Создаем и рендерим Markdown
                md = Markdown(content)
                self.console.print(prefix, end="")
                self.console.print(md)
            else:
                print(f"{prefix}{content}")
            print()
            
        elif message.type == "error":
            prefix = "❌ " if self.use_emojis else "Error: "
            print(f"\n{prefix}{message.content}\n") 