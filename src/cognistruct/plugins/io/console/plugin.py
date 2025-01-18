import asyncio
from typing import Optional, Any, Callable, Awaitable
import sys
from rich import print
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.console import Group, Console

from cognistruct.core import BasePlugin, PluginMetadata, IOMessage
from cognistruct.llm.interfaces import StreamChunk


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
        self._input_future: Optional[asyncio.Future] = None
        
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
    
    def print_tool_call(self, tool_call: Any, return_str: bool = False) -> Optional[str]:
        """
        Форматирует и печатает вызов инструмента
        
        Args:
            tool_call: Информация о вызове инструмента
            return_str: Вернуть строку вместо печати
            
        Returns:
            str если return_str=True, иначе None
        """
        # Формируем базовый текст
        tool_name = tool_call.tool if hasattr(tool_call, 'tool') else str(tool_call)
        prefix = "🔧 " if self.use_emojis else ""
        text = f"> {prefix}**Использую инструмент**: {tool_name}..."
        
        if return_str:
            return text
            
        # Печатаем с нужным форматированием
        if self.use_markdown:
            self.console.print(Markdown(text), style="yellow")
        else:
            # Убираем markdown-разметку для plain text
            plain_text = text.replace('**', '')
            self.console.print(plain_text, style="yellow")
            
    def print_tool_result(self, result: str, return_str: bool = False) -> Optional[str]:
        """
        Форматирует и печатает результат инструмента
        
        Args:
            result: Результат работы инструмента
            return_str: Вернуть строку вместо печати
            
        Returns:
            str если return_str=True, иначе None
        """
        # Формируем базовый текст
        prefix = "✅ " if self.use_emojis else ""
        text = f"> {prefix}**Результат**: {result}"
        
        if return_str:
            return text
            
        # Печатаем с нужным форматированием
        if self.use_markdown:
            self.console.print(Markdown(text), style="green")
        else:
            # Убираем markdown-разметку для plain text
            plain_text = text.replace('**', '')
            self.console.print(plain_text, style="green")

    async def handle_markdown_stream(self, message: str, stream: Any):
        """Обработка стрима с поддержкой Markdown"""
        current_content = ""
        current_tool = None
        first_chunk = True
        sections = []  # Список секций для отображения
        need_refresh = False
        
        def render_sections():
            """Рендерит все секции в одну панель"""
            rendered = []
            for section in sections:
                if section["type"] == "text":
                    rendered.append(Markdown(section["content"]))
                elif section["type"] == "tool":
                    rendered.append(
                        Markdown(self.print_tool_call(section['content'], return_str=True))
                    )
                elif section["type"] == "result":
                    rendered.append(
                        Markdown(self.print_tool_result(section['content'], return_str=True))
                    )
                    rendered.append(Text())
            
            return Panel(
                Group(*rendered),
                title="🤖 Ответ",
                border_style="blue",
                padding=(0, 1)
            )
        
        # Создаем начальную секцию для текста
        sections.append({"type": "text", "content": ""})
        
        # Создаем единую Live панель
        live_panel = Live(
            render_sections(),
            console=self.console,
            refresh_per_second=self.refresh_rate,
            vertical_overflow="visible",
            auto_refresh=True,  # Включаем автообновление
            transient=True  # Очищаем промежуточные состояния
        )
        
        with live_panel:
            async for chunk in stream:
                if first_chunk and not chunk.delta:
                    first_chunk = False
                    continue
                    
                if chunk.delta:
                    current_content += chunk.delta
                    # Обновляем только последнюю текстовую секцию
                    for section in reversed(sections):
                        if section["type"] == "text":
                            section["content"] += chunk.delta
                            break
                    need_refresh = True
                    first_chunk = False
                
                if chunk.tool_call and not current_tool:
                    current_tool = chunk.tool_call
                    sections.append({"type": "tool", "content": current_tool})
                    sections.append({"type": "text", "content": ""})
                    live_panel.update(render_sections())  # Обновляем сразу при добавлении инструмента
                
                if chunk.tool_result:
                    sections.append({"type": "result", "content": chunk.tool_result})
                    sections.append({"type": "text", "content": ""})
                    current_tool = None
                    live_panel.update(render_sections())  # Обновляем сразу при добавлении результата
                
                # Обновляем только если накопились изменения и прошло достаточно времени
                if need_refresh and not (chunk.tool_call or chunk.tool_result):
                    live_panel.update(render_sections())
                    need_refresh = False
        
        # После завершения Live выводим финальную версию
        self.console.print(render_sections())
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
                self.print_tool_call(current_tool)
            
            if chunk.tool_result:
                self.print_tool_result(chunk.tool_result)
                current_tool = None
        
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
            
            # Извлекаем контент и форматируем его
            content = message.content.content if hasattr(message.content, 'content') else str(message.content)
            content = self.format_output(content)
            
            # Если есть tool_calls в LLMResponse, выводим их перед основным контентом
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    self.print_tool_call(tool_call)
                    # Результат инструмента уже включен в основной контент
            
            # Выводим основной контент
            if self.use_markdown:
                self.console.print(Panel(
                    Markdown(content),
                    title=prefix.strip(),
                    border_style="blue"
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

    def print_header(self, message: str):
        """Выводит заголовок"""
        prefix = "🔷 " if self.use_emojis else ""
        if self.use_markdown:
            self.console.print(Markdown(f"{prefix}**{message}**"), style="blue bold")
        else:
            self.console.print(f"{prefix}{message}", style="blue bold")
            
    def print_info(self, message: str, end: str = "\n"):
        """Выводит информационное сообщение"""
        prefix = "ℹ️ " if self.use_emojis else ""
        if self.use_markdown:
            self.console.print(Markdown(f"{prefix}{message}"), style="blue", end=end)
        else:
            self.console.print(f"{prefix}{message}", style="blue", end=end)
            
    def print_success(self, message: str):
        """Выводит сообщение об успехе"""
        prefix = "✅ " if self.use_emojis else ""
        if self.use_markdown:
            self.console.print(Markdown(f"{prefix}{message}"), style="green")
        else:
            self.console.print(f"{prefix}{message}", style="green")
            
    def print_warning(self, message: str):
        """Выводит предупреждение"""
        prefix = "⚠️ " if self.use_emojis else ""
        if self.use_markdown:
            self.console.print(Markdown(f"{prefix}{message}"), style="yellow")
        else:
            self.console.print(f"{prefix}{message}", style="yellow")
            
    def print_error(self, message: str):
        """Выводит сообщение об ошибке"""
        prefix = "❌ " if self.use_emojis else ""
        if self.use_markdown:
            self.console.print(Markdown(f"{prefix}{message}"), style="red")
        else:
            self.console.print(f"{prefix}{message}", style="red")
            
    def print_debug(self, message: str):
        """Выводит отладочное сообщение"""
        prefix = "🔍 " if self.use_emojis else ""
        if self.use_markdown:
            self.console.print(Markdown(f"{prefix}{message}"), style="dim")
        else:
            self.console.print(f"{prefix}{message}", style="dim") 