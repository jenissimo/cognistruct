import asyncio
import uuid
from typing import Optional, Any, Callable, Awaitable, AsyncGenerator, Union
import sys
from rich import print
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.console import Group, Console

from cognistruct.core import BasePlugin, PluginMetadata, IOMessage, RequestContext
from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


class ConsolePlugin(BasePlugin):
    """Плагин для работы с консольным вводом/выводом с поддержкой стриминга"""
    
    # Константы для контекста
    DEFAULT_USER_ID = "console_user"
    
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
        self.message_handler: Optional[Callable[
            [Union[str, IOMessage], ...],  # Поддержка разных типов входа и доп. параметров
            Union[str, AsyncGenerator[IOMessage, None]]  # Поддержка обычных ответов и стриминга
        ]] = None
        self._running = False
        self.console = Console()
        self._input_future: Optional[asyncio.Future] = None
        self._current_stream: Optional[Live] = None
        self._session_id = str(uuid.uuid4())  # Уникальный ID сессии
        
    async def setup(self):
        """Инициализация плагина"""
        await super().setup()
        logger.info("Initialized console plugin with default user ID: %s", self.DEFAULT_USER_ID)
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="console",
            description="Обработка консольного ввода/вывода с поддержкой стриминга",
            version="1.1.0",
            priority=100  # Высокий приоритет для I/O
        )
        
    def set_message_handler(
        self, 
        handler: Callable[
            [Union[str, IOMessage], ...],  # Поддержка разных типов входа и доп. параметров
            Union[str, AsyncGenerator[IOMessage, None]]  # Поддержка обычных ответов и стриминга
        ]
    ):
        """
        Устанавливает обработчик сообщений.
        
        Args:
            handler: Функция-обработчик, принимающая сообщение (строку или IOMessage)
                    и возвращающая строку или генератор сообщений для стриминга
        """
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
                    
                # Создаем контекст для сообщения с дефолтным user_id
                context = RequestContext(
                    user_id=self.DEFAULT_USER_ID,
                    metadata={
                        "source": "console"
                    }
                )
                
                # Создаем сообщение с контекстом
                message = IOMessage(
                    type="console_input",
                    content=user_input,
                    source="console",
                    context=context
                )
                
                # Передаем сообщение обработчику
                if self.message_handler:
                    response = await self.message_handler(message)
                    
                    if isinstance(response, (str, IOMessage)):
                        # Для текстового ответа создаем IOMessage
                        if isinstance(response, str):
                            response = IOMessage(
                                type="text",
                                content=response,
                                source="agent",
                                context=context  # Добавляем контекст
                            )
                        # BaseAgent сам вызовет output_hook
                        
                    elif hasattr(response, '__aiter__'):
                        # Для стрима создаем IOMessage со стримом
                        stream_message = IOMessage.create_stream(
                            response, 
                            source="agent",
                            context=context  # Добавляем контекст
                        )
                        # Пропускаем через streaming_output_hook
                        async for chunk in self.streaming_output_hook(stream_message):
                            # Чанки уже обработаны в streaming_output_hook
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
            
        # Инициализируем состояние стрима если его еще нет
        if not hasattr(self, '_stream_state') or not hasattr(self, '_current_stream') or self._current_stream is None:
            logger.debug("Initializing stream state (stream_state exists: %s, current_stream exists: %s)", 
                        hasattr(self, '_stream_state'), 
                        hasattr(self, '_current_stream'))
            self._init_stream_state()
            
        try:
            # Флаг для отслеживания незавершенных тул коллов
            has_pending_tools = False
            
            # Сразу начинаем итерацию по стриму
            logger.debug("Starting stream iteration")
            async for chunk in message.stream:
                logger.debug("Processing chunk: %s", chunk)
                
                # Проверяем состояние стрима
                if not hasattr(self, '_current_stream') or self._current_stream is None:
                    logger.warning("Stream state lost, reinitializing")
                    self._init_stream_state()
                
                # Проверяем завершение
                if chunk.metadata.get("is_complete"):
                    logger.debug("Stream complete, checking tool calls state")
                    logger.debug("Current content: %s", self._stream_state['current_content'])
                    logger.debug("Has pending tools: %s", has_pending_tools)
                    logger.debug("Current sections: %s", self._stream_state['sections'])
                    
                    # Проверяем, есть ли что-то в текущем контенте
                    has_content = bool(self._stream_state['current_content'].strip())
                    logger.debug("Has content: %s", has_content)
                    
                    # Делаем полную очистку только если:
                    # 1. Нет незавершенных тул коллов
                    # 2. Нет контента для отображения
                    # 3. Последняя секция не пустая
                    last_section_empty = (
                        self._stream_state['sections'][-1]["type"] == "text" 
                        and not self._stream_state['sections'][-1]["content"].strip()
                    ) if self._stream_state['sections'] else True
                    
                    if not has_pending_tools and not has_content and not last_section_empty:
                        logger.debug("No pending tools, no content, and last section not empty - doing final cleanup")
                        self._cleanup_stream(final=True)
                    else:
                        logger.debug("Skipping cleanup (pending tools: %s, has content: %s, last section empty: %s)", 
                                   has_pending_tools, has_content, last_section_empty)
                        has_pending_tools = False  # Сбрасываем флаг для следующего стрима
                    yield chunk
                    continue
                
                # Обновляем отображение если есть delta
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
                    if "call" in last_call:
                        has_pending_tools = True
                        logger.debug("Found pending tool call")
                        # Добавляем секцию для тул колла
                        self._stream_state['sections'].append({"type": "tool", "content": last_call["call"]})
                        
                    if "call" in last_call and "result" in last_call:
                        has_pending_tools = False
                        logger.debug("Tool call completed")
                        # Добавляем только секцию с результатом и новую текстовую
                        self._stream_state['sections'].append({
                            "type": "result", 
                            "content": last_call["result"]["content"]
                        })
                        self._stream_state['sections'].append({"type": "text", "content": ""})
                        # Сбрасываем только текущий контент
                        self._stream_state['current_content'] = ""
                
                # Обновляем отображение
                try:
                    if self._current_stream:
                        self._current_stream.update(self._render_sections())
                        logger.debug("Updated live panel")
                    else:
                        logger.warning("Live panel is None, skipping update")
                except Exception as e:
                    logger.error(f"Error updating live panel: {e}", exc_info=True)
                    # Пробуем восстановить состояние
                    self._init_stream_state()
                    
                yield chunk
            
            # Если стрим закончился без is_complete, проверяем флаг
            if not has_pending_tools:
                logger.debug("Stream ended without is_complete, no pending tools, doing final cleanup")
                self._cleanup_stream(final=True)
            else:
                logger.debug("Stream ended without is_complete but has pending tools, skipping cleanup")
            
        except Exception as e:
            logger.error(f"Error in streaming_output_hook: {e}", exc_info=True)
            if not has_pending_tools:
                self._cleanup_stream(final=True)
            raise
            
    def _init_stream_state(self):
        """Инициализирует состояние стрима"""
        logger.debug("Initializing stream state")
        
        # Сохраняем старые секции если они есть
        old_sections = []
        if hasattr(self, '_stream_state'):
            old_sections = self._stream_state['sections']
            
        self._stream_state = {
            'sections': old_sections if old_sections else [{"type": "text", "content": ""}],
            'current_content': "",
            'current_tool': None
        }
        
        # Создаем Live панель если её еще нет или она None
        if not hasattr(self, '_current_stream') or self._current_stream is None:
            logger.debug("Creating new live panel")
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
        else:
            logger.debug("Using existing live panel")
        
    def _cleanup_stream(self, final: bool = False):
        """
        Очищает состояние стрима
        
        Args:
            final: Если True, полностью очищает состояние и останавливает панель
        """
        logger.debug("Cleaning up stream (final=%s)", final)
        if final:
            if hasattr(self, '_current_stream') and self._current_stream:
                try:
                    self._current_stream.stop()
                    self.console.print(self._render_sections())
                except Exception as e:
                    logger.error(f"Error stopping live panel: {e}", exc_info=True)
                finally:
                    self._current_stream = None
            if hasattr(self, '_stream_state'):
                delattr(self, '_stream_state')
        else:
            # Только сбрасываем текущий контент
            if hasattr(self, '_stream_state'):
                self._stream_state['current_content'] = ""

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

    async def input_hook(self, message: IOMessage) -> bool:
        """
        Проверяет входящие сообщения.
        В консольном плагине всегда пропускаем сообщения дальше.
        
        Args:
            message: Входящее сообщение
            
        Returns:
            bool: True - всегда пропускаем сообщения
        """
        return True