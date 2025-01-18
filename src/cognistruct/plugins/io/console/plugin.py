import asyncio
from typing import Optional, Any, Callable, Awaitable, AsyncGenerator
import sys
from rich import print
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.console import Group, Console

from cognistruct.core import BasePlugin, PluginMetadata, IOMessage
from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


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
        self._current_stream: Optional[Live] = None
        
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
                    response = await self.message_handler(message)
                    if hasattr(response, '__aiter__'):
                        logger.debug("Got streaming response, starting iteration")
                        async for chunk in response:
                            # Просто проходим по чанкам, их обработка уже в streaming_output_hook
                            pass
                
            except KeyboardInterrupt:
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
        # Получаем имя инструмента
        if isinstance(tool_call, dict) and 'function' in tool_call:
            tool_name = tool_call['function']['name']
        elif hasattr(tool_call, 'function') and hasattr(tool_call.function, 'name'):
            tool_name = tool_call.function.name
        else:
            tool_name = str(tool_call)
            
        # Формируем текст
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
            
    def print_tool_result(self, result: Any, return_str: bool = False) -> Optional[str]:
        """
        Форматирует и печатает результат инструмента
        
        Args:
            result: Результат работы инструмента (словарь или строка)
            return_str: Вернуть строку вместо печати
            
        Returns:
            str если return_str=True, иначе None
        """
        # Извлекаем результат из словаря если это словарь
        if isinstance(result, dict):
            if "answer" in result:
                result_text = result["answer"]
            elif "error" in result:
                result_text = f"Ошибка: {result['error']}"
            else:
                result_text = str(result)
        else:
            result_text = str(result)
        
        # Формируем текст
        prefix = "✅ " if self.use_emojis else ""
        text = f"> {prefix}**Результат**: {result_text}"
        
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

    async def streaming_output_hook(self, message: IOMessage) -> AsyncGenerator[IOMessage, None]:
        """
        Обрабатывает потоковые сообщения с поддержкой Markdown и обычного текста.
        
        Args:
            message: Стрим-сообщение
        """
        logger.debug("streaming_output_hook called with message: %s", message)
        
        if not message.stream:
            logger.debug("No stream in message, yielding as is")
            yield message
            return
            
        # Состояние стрима
        if not hasattr(self, '_stream_state'):
            logger.debug("Initializing stream state")
            self._stream_state = {
                'sections': [{"type": "text", "content": ""}],  # Начальная текстовая секция
                'current_content': "",
                'current_tool': None
            }
            
            # Создаем Live панель
            self._current_stream = Live(
                self._render_sections(),
                console=self.console,
                refresh_per_second=self.refresh_rate,
                vertical_overflow="visible",
                auto_refresh=True,
                transient=True
            )
            self._current_stream.start()
            logger.debug("Live panel started")
            
        try:
            # Создаем новый генератор для стрима
            async def process_stream():
                async for chunk in message.stream:
                    logger.debug("Processing chunk: %s", chunk)
                    # Обновляем отображение
                    if chunk.metadata.get("delta"):
                        delta = chunk.metadata["delta"]
                        logger.debug("Got delta: %s", delta)
                        # Добавляем текст в последнюю текстовую секцию
                        for section in reversed(self._stream_state['sections']):
                            if section["type"] == "text":
                                section["content"] += delta
                                break
                        self._stream_state['current_content'] += delta
                    
                    # Обрабатываем tool_calls
                    if chunk.tool_calls:
                        logger.debug("Processing tool calls: %s", chunk.tool_calls)
                        last_call = chunk.tool_calls[-1]
                        if "call" in last_call and "result" in last_call:
                            self._stream_state['sections'].append({"type": "tool", "content": last_call["call"]})
                            self._stream_state['sections'].append({
                                "type": "result", 
                                "content": last_call["result"]["content"]
                            })
                            self._stream_state['sections'].append({"type": "text", "content": ""})
                    
                    # Обновляем отображение
                    self._current_stream.update(self._render_sections())
                    logger.debug("Updated live panel")
                    
                    # Проверяем завершение
                    if chunk.metadata.get("is_complete"):
                        logger.debug("Stream complete, stopping live panel")
                        self._current_stream.stop()
                        self.console.print(self._render_sections())
                        self._current_stream = None
                        delattr(self, '_stream_state')
                        
                    yield chunk
            
            # Создаем новое сообщение со стримом
            new_message = IOMessage(
                type=message.type,
                content=message.content,
                metadata=message.metadata,
                source=message.source,
                is_async=True,
                tool_calls=message.tool_calls.copy() if message.tool_calls else [],
                stream=process_stream()
            )
            
            logger.debug("Yielding new message with stream")
            yield new_message
            
        except Exception as e:
            logger.error(f"Error in streaming_output_hook: {e}", exc_info=True)
            if self._current_stream:
                self._current_stream.stop()
                self._current_stream = None
            if hasattr(self, '_stream_state'):
                delattr(self, '_stream_state')
            raise

    def _render_sections(self) -> Panel:
        """Рендерит все секции в одну панель"""
        rendered = []
        for section in self._stream_state['sections']:
            if section["type"] == "text":
                rendered.append(Markdown(section["content"]))
            elif section["type"] == "tool":
                rendered.append(
                    Markdown(f"> 🔧 **Использую инструмент**: {section['content']['function']['name']}...")
                )
            elif section["type"] == "result":
                rendered.append(
                    Markdown(f"> ✅ **Результат**: {section['content']}")
                )
                rendered.append(Text())
        
        return Panel(
            Group(*rendered),
            title="🤖 Ответ",
            border_style="blue",
            padding=(0, 1)
        )

    async def output_hook(self, message: IOMessage) -> Optional[IOMessage]:
        """
        Обрабатывает не-стриминговые сообщения
        
        Args:
            message: Сообщение для обработки
            
        Returns:
            Optional[IOMessage]: Обработанное сообщение или None
        """
        # Пропускаем асинхронные сообщения, так как они уже были обработаны в streaming_output_hook
        if message.is_async:
            return message
            
        if message.type == "text":
            prefix = "🤖 " if self.use_emojis else "Bot: "
            content = str(message.content) if message.content is not None else ""
            
            # Обрабатываем tool_calls если есть
            tool_calls = message.get_tool_calls()
            if tool_calls:
                for tool_call in tool_calls:
                    if "call" in tool_call:
                        self.print_tool_call(tool_call["call"])
                    if "result" in tool_call:
                        self.print_tool_result(tool_call["result"]["content"])
            
            # Выводим основной контент
            if content:  # Выводим только если есть что выводить
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
            prefix = "❌ " if self.use_emojis else "Error: "
            error_content = str(message.content) if message.content is not None else "Unknown error"
            self.console.print(Panel(
                Text(error_content, style="red"),
                title=prefix.strip(),
                border_style="red"
            ))
            print()
        
        return message

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