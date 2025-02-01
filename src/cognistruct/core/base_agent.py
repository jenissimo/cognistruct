from typing import Dict, Any, Optional, List, AsyncGenerator, Union, Callable, Awaitable
import asyncio
import json
import logging

from cognistruct.llm import BaseLLM
from cognistruct.llm.interfaces import StreamChunk, ToolCall
from .plugin_manager import PluginManager
from .base_plugin import IOMessage
from .messages import IOMessage
from .context import RequestContext

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Базовый класс для всех агентов.
    Обеспечивает обработку сообщений и работу с контекстом.
    """

    def __init__(self, llm: BaseLLM, auto_load_plugins: bool = False):
        """
        Инициализация агента
        
        Args:
            llm: Модель для обработки сообщений
            auto_load_plugins: Автоматически загружать плагины при setup
        """
        self.llm = llm
        self.plugin_manager = PluginManager()
        self.auto_load_plugins = auto_load_plugins
        self._current_system_prompt: Optional[str] = None
        
        # Устанавливаем ссылку на агента в plugin_manager
        self.plugin_manager.set_agent(self)
        
        # Автоматически загружаем плагины если нужно
        if auto_load_plugins:
            self.plugin_manager.load_plugins()
            
        # Устанавливаем обработчик инструментов для LLM
        self.llm.set_tool_executor(self.plugin_manager.execute_tool)

    async def start(self):
        """Инициализация и запуск агента"""
        if self.auto_load_plugins:
            await self.plugin_manager.load_plugins()
            logger.info("Loaded plugins: %s", 
                       [p.name for p in self.plugin_manager.get_all_plugins()])

    async def cleanup(self):
        """Очистка ресурсов агента"""
        await self.plugin_manager.cleanup()
        await self.llm.close()

    async def _prepare_llm_messages(
        self,
        message: IOMessage,
        system_prompt: Optional[str] = None,
        context: Optional[RequestContext] = None
    ) -> List[Dict[str, str]]:
        """
        Подготовка сообщений для LLM
        
        Args:
            message: Сообщение пользователя
            system_prompt: Системный промпт
            context: Контекст запроса
            
        Returns:
            List[Dict[str, str]]: Список сообщений для LLM
        """
        messages = []
        
        # Добавляем системный промпт
        if system_prompt:
            # Если system_prompt это функция, вызываем её
            if callable(system_prompt):
                try:
                    prompt_content = system_prompt()
                except Exception as e:
                    logger.error(f"Error calling system_prompt function: {e}")
                    prompt_content = ""
            else:
                prompt_content = system_prompt
                
            messages.append({
                "role": "system",
                "content": prompt_content
            })
            
        # Получаем дополнительный контекст от RAG-хуков
        rag_context = await self.plugin_manager.execute_rag_hooks(message)
        if rag_context:
            # Добавляем контекст от RAG в системный промпт
            rag_prompt = "\nДополнительный контекст:\n"
            for plugin_name, plugin_context in rag_context.items():
                rag_prompt += f"\nОт {plugin_name}:\n{json.dumps(plugin_context, ensure_ascii=False, indent=2)}"
            
            messages.append({
                "role": "system",
                "content": rag_prompt
            })
            
        # Добавляем текущее сообщение
        messages.append({
            "role": "user",
            "content": message.content
        })
        
        return messages

    async def _process_stream_through_plugins(
        self,
        stream_message: IOMessage,
        metadata: Dict[str, Any]
    ) -> AsyncGenerator[IOMessage, None]:
        """Обработка стрим-сообщения через плагины"""
        current_stream = stream_message
        last_chunk = None
        tool_calls = []

        logger.debug(f"🔄 Пропускаем стрим через плагины")

        # Пропускаем через streaming_output_hooks всех плагинов
        for plugin in self.plugin_manager.get_all_plugins():
            if hasattr(plugin, 'streaming_output_hook'):
                logger.debug(f"🔄 Пропускаем стрим через плагин {plugin.__class__.__name__}")
                try:
                    plugin_stream = plugin.streaming_output_hook(current_stream)
                    logger.debug(f"✨ Создан стрим для плагина {plugin.__class__.__name__}")
                    
                    # Обрабатываем все чанки от плагина
                    async for chunk in plugin_stream:
                        logger.debug(f"📦 Получен чанк от {plugin.__class__.__name__}: {chunk}")
                        if chunk and chunk.stream:
                            current_stream = chunk
                            logger.debug(f"🔄 Обновлен текущий стрим от {plugin.__class__.__name__}")
                            
                except Exception as e:
                    logger.error(f"❌ Ошибка в плагине {plugin.__class__.__name__}: {e}", exc_info=True)
                    raise

        # Отдаем финальный стрим и собираем последний чанк и tool_calls
        if current_stream and current_stream.stream:
            logger.debug("🚀 Начинаем отдавать чанки из финального стрима")
            async for chunk in current_stream.stream:
                chunk.metadata.update(metadata)
                # Собираем tool_calls
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)
                    logger.debug(f"🔧 Добавлены tool_calls: {chunk.tool_calls}")
                
                # Сохраняем последний чанк
                last_chunk = chunk
                logger.debug(f"📝 Обновлен последний чанк: {chunk}")
                
                yield chunk
            logger.debug("✅ Завершена отдача чанков из финального стрима")

        # После завершения стрима обрабатываем полное сообщение через output_hooks
        if last_chunk:
            logger.debug(f"📋 Создаем полное сообщение из последнего чанка (длина контента: {len(last_chunk.content)})")
            # Создаем финальное сообщение из последнего чанка с контекстом
            final_message = IOMessage(
                type="text",
                content=last_chunk.content,
                metadata=metadata,
                source=current_stream.source,
                is_async=current_stream.is_async,
                tool_calls=tool_calls,
                context=current_stream.context  # Передаем контекст
            )
            
            logger.debug(f"🔄 Обрабатываем полное сообщение через output_hooks")
            await self._process_complete_message(final_message)

    async def _process_complete_message(
        self,
        message: IOMessage
    ) -> None:
        """
        Обработка полного сообщения через output_hooks
        
        Args:
            message: Финальное сообщение для обработки
        """
        logger.debug("Processing complete message through output_hooks")
        for plugin in self.plugin_manager.get_all_plugins():
            if hasattr(plugin, 'output_hook'):
                try:
                    processed = await plugin.output_hook(message)
                    if processed is not None:
                        message = processed
                except Exception as e:
                    logger.error(f"Error in output_hook of plugin {plugin.__class__.__name__}: {e}")

    async def handle_message(
        self,
        message: Union[str, IOMessage],
        system_prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[str, AsyncGenerator[IOMessage, None]]:
        """
        Публичный API для обработки входящих сообщений.
        
        Args:
            message: Текст сообщения или IOMessage
            system_prompt: Системный промпт для LLM
            stream: Использовать потоковую генерацию
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            Union[str, AsyncGenerator[IOMessage, None]]: Ответ или генератор ответов
        """
        logger.debug(f"handle_message called with stream={stream}")
        return await self.process_message(message, system_prompt, stream, **kwargs)

    async def process_message(
        self,
        message: Union[str, IOMessage],
        system_prompt: Optional[str] = None,
        stream: bool = False,
        message_preprocessor: Optional[Callable[[IOMessage], Awaitable[IOMessage]]] = None,
        **kwargs
    ) -> Union[str, AsyncGenerator[IOMessage, None]]:
        """Обрабатывает сообщение пользователя с учетом контекста"""
        logger.debug("process_message called with stream=%s", stream)
        
        # Создаем IOMessage если получили строку
        if isinstance(message, str):
            message = IOMessage(
                type="text",
                content=message,
                source="user"
            )
            
        # Пропускаем через input_hooks всех плагинов
        for plugin in self.plugin_manager.get_all_plugins():
            if hasattr(plugin, 'input_hook'):
                try:
                    should_continue = await plugin.input_hook(message)
                    if not should_continue:
                        logger.debug(f"Message blocked by plugin {plugin.__class__.__name__}")
                        return None
                except Exception as e:
                    logger.error(f"Error in input_hook of plugin {plugin.__class__.__name__}: {e}")
                    return None
        
        # Получаем или создаем контекст
        context = message.context
        if not context:
            logger.warning("Message has no context, creating default")
            context = RequestContext(user_id="default")
            message.context = context
        
        # Получаем текст сообщения и метаданные
        message_text = message.content
        metadata = message.metadata
        
        # Подготавливаем сообщения для LLM с учетом контекста
        messages = await self._prepare_llm_messages(message, system_prompt, context)
        
        # Получаем инструменты от плагинов
        tools = self.plugin_manager.get_all_tools()
        
        # Создаем параметры запроса с контекстом
        request_params = {
            "messages": messages,
            "tools": tools if tools else None,
            "stream": stream,
            "context": context,  # Добавляем контекст в параметры
            **kwargs
        }
        
        # Получаем ответ от LLM
        response = await self.llm.generate_response(**request_params)
        
        if stream:
            logger.debug("Processing stream through plugins")
            stream_message = IOMessage.create_stream(response, metadata=metadata)
            logger.debug(f"🔄 Создан стрим-сообщение: {stream_message}")
            stream_message.context = context  # Устанавливаем контекст для стрим-сообщения
            
            async def stream_generator():
                logger.debug("🔄 Начинаем генерацию стрима")
                async for chunk in self._process_stream_through_plugins(stream_message, metadata):
                    yield chunk
                    
            return stream_generator()
        else:
            # Для обычного ответа сначала применяем препроцессор
            response_message = response
            response_message.metadata.update(metadata)
            response_message.context = context  # Устанавливаем контекст для ответа
            
            if kwargs.get('message_preprocessor'):
                try:
                    response_message = await kwargs['message_preprocessor'](response_message)
                except Exception as e:
                    logger.error(f"Error in message preprocessor: {e}", exc_info=True)
            
            # Затем пропускаем через output_hooks
            for plugin in self.plugin_manager.get_all_plugins():
                if hasattr(plugin, 'output_hook'):
                    processed = await plugin.output_hook(response_message)
                    if processed is None:
                        return None
                    response_message = processed
                    
            return response_message 