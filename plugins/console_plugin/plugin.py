import asyncio
from typing import Optional, Callable, Awaitable, Any
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text
from rich.panel import Panel
from rich.layout import Layout
import sys

from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage


class ConsolePlugin(BasePlugin):
    """Плагин для работы с консольным вводом/выводом с поддержкой стриминга"""
    
    def __init__(self, 
                 prompt: str = "👤 ",
                 exit_command: str = "exit",
                 exit_message: str = "\n👋 До свидания!",
                 use_markdown: bool = True,
                 use_emojis: bool = True,
                 refresh_rate: int = 10):
        """
        Args:
            prompt: Строка приглашения ввода
            exit_command: Команда для выхода
            exit_message: Сообщение при выходе
            use_markdown: Использовать форматирование Markdown
            use_emojis: Использовать эмодзи в выводе
            refresh_rate: Частота обновления при стриминге (кадров в секунду)
        """
        super().__init__()
        self.prompt = prompt
        self.exit_command = exit_command
        self.exit_message = exit_message
        self.use_markdown = use_markdown
        self.use_emojis = use_emojis
        self.refresh_rate = refresh_rate
        self.message_handler: Optional[Callable[[IOMessage], Awaitable[None]]] = None
        self._running = False
        self.console = Console()
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="console",
            description="Обработка консольного ввода/вывода с поддержкой стриминга",
            version="1.1.0",
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

    async def handle_markdown_stream(self, message: str, stream: Any):
        """Обработка стрима с поддержкой Markdown"""
        current_content = ""
        current_tool = None
        first_chunk = True
        sections = []  # Список секций для отображения
        
        def render_sections():
            """Рендерит все секции в одну панель"""
            rendered = []
            for section in sections:
                if section["type"] == "text":
                    rendered.append(Markdown(section["content"]))
                elif section["type"] == "tool":
                    rendered.append(Text())  # Пустая строка перед инструментом
                    rendered.append(
                        Markdown(f"> 🔧 **Использую инструмент**: {section['content']}...")
                    )
                elif section["type"] == "result":
                    rendered.append(Text())  # Пустая строка перед результатом
                    rendered.append(
                        Markdown(f"> ✅ **Результат**: {section['content']}")
                    )
            
            return Panel(
                Group(*rendered),
                title="🤖 Ответ",
                border_style="blue",
                padding=(0, 1)
            )
        
        # Создаем начальную секцию для текста
        sections.append({"type": "text", "content": ""})
        
        with Live(
            render_sections(),
            console=self.console,
            refresh_per_second=10,
            vertical_overflow="visible",
            auto_refresh=True
        ) as live:
            async for chunk in stream:
                # Отладочный вывод для каждого чанка
                print(f"\n[DEBUG] Chunk: delta={bool(chunk.delta)}, "
                      f"tool_call={bool(chunk.tool_call)}, "
                      f"tool_result={bool(chunk.tool_result)}", 
                      file=sys.stderr)
                
                if first_chunk and not chunk.delta:
                    first_chunk = False
                    continue
                    
                if chunk.delta:
                    current_content += chunk.delta
                    # Обновляем последнюю текстовую секцию
                    for section in reversed(sections):
                        if section["type"] == "text":
                            section["content"] += chunk.delta
                            break
                    live.update(render_sections())
                    first_chunk = False
                
                if chunk.tool_call and not current_tool:
                    current_tool = chunk.tool_call
                    print(f"\n[DEBUG] Tool call: {current_tool.tool} with params: {current_tool.params}",
                          file=sys.stderr)
                    sections.append({"type": "tool", "content": current_tool.tool})
                    sections.append({"type": "text", "content": ""})
                    live.update(render_sections())
                
                if chunk.tool_result:
                    print(f"\n[DEBUG] Tool result: {chunk.tool_result}", file=sys.stderr)
                    sections.append({"type": "result", "content": chunk.tool_result})
                    sections.append({"type": "text", "content": ""})
                    current_tool = None
                    live.update(render_sections())
            
            return current_content
        
    async def handle_regular_stream(self, message: str, stream: Any):
        """Обработка стрима без Markdown"""
        current_content = ""
        current_tool = None
        first_chunk = True
        
        # Печатаем начальную рамку
        print()
        self.console.print("🤖 Ответ:", style="blue bold")
        
        async for chunk in stream:            
            if first_chunk and not chunk.delta:
                first_chunk = False
                continue
                
            if chunk.delta:
                current_content += chunk.delta
                # Сразу печатаем новый чанк
                self.console.print(chunk.delta, end="")
                first_chunk = False
            
            if chunk.tool_call and not current_tool:
                current_tool = chunk.tool_call
                self.console.print(f"\n\n> Использую инструмент: {current_tool.tool}...", 
                                 style="yellow")
            
            if chunk.tool_result:
                current_tool = None
                self.console.print(f"\n> Результат: {chunk.tool_result}", style="green")
        
        print("\n")
        return current_content

    async def handle_stream(self, message: str, stream: Any):
        """
        Обрабатывает потоковый ответ от LLM
        
        Args:
            message: Исходное сообщение
            stream: Генератор стрим-чанков
        """
        if self.use_markdown:
            return await self.handle_markdown_stream(message, stream)
        else:
            return await self.handle_regular_stream(message, stream)

    async def output_hook(self, message: IOMessage):
        """Выводит сообщения в консоль"""
        
        if message.type == "stream" and message.stream:
            # Обрабатываем стриминг напрямую
            await self.handle_stream(message.content, message.stream)
            return
        
        # Для остальных типов сообщений
        if message.type in ["message", "text"]:
            prefix = "🤖 " if self.use_emojis else "Bot: "
            content = self.format_output(message.content)
            
            # Создаем консоль с прокруткой
            console = Console(height=20, force_terminal=True)
            
            # Добавляем отступы
            print()
            if self.use_markdown:
                console.print(Panel(
                    Markdown(content),
                    title=prefix.strip(),
                    border_style="blue",
                    height=20
                ))
            else:
                print(f"{prefix}{content}")
            print()
            
        elif message.type == "error":
            print("[DEBUG] Handling error message", file=sys.stderr)
            prefix = "❌ " if self.use_emojis else "Error: "
            self.console.print(Panel(
                Text(message.content, style="red"),
                title=prefix.strip(),
                border_style="red"
            ))
            print() 