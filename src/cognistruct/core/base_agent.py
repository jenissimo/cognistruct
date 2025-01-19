from typing import Dict, Any, Optional, List, AsyncGenerator, Union, Callable, Awaitable
import asyncio
import json
import logging

from cognistruct.llm import BaseLLM
from cognistruct.llm.interfaces import StreamChunk, ToolCall
from .plugin_manager import PluginManager
from .base_plugin import IOMessage

logger = logging.getLogger(__name__)


class BaseAgent:
    """Базовый класс для всех агентов"""

    def __init__(self, llm: BaseLLM, auto_load_plugins: bool = False):
        """
        Инициализация агента
        
        Args:
            llm: Модель для обработки сообщений
            auto_load_plugins: Автоматически загружать плагины при setup
        """
        self.llm = llm
        self.plugin_manager = PluginManager()
        self.conversation_history: List[Dict[str, str]] = []
        self.auto_load_plugins = auto_load_plugins
        self._current_system_prompt: Optional[str] = None
        
        # Автоматически загружаем плагины если нужно
        if auto_load_plugins:
            self.plugin_manager.load_plugins()
            
        # Устанавливаем обработчик инструментов для LLM
        async def tool_executor(tool_name: str, args: Dict[str, Any]):
            return await self.plugin_manager.execute_tool(tool_name, args)
            
        self.llm.set_tool_executor(tool_executor)

    async def start(self):
        """Инициализация и запуск агента"""
        # Загружаем плагины если нужно
        if self.auto_load_plugins:
            await self.plugin_manager.load_plugins()
            logger.info("Loaded plugins: %s", 
                       [p.name for p in self.plugin_manager.get_all_plugins()])

    async def cleanup(self):
        """Очистка ресурсов агента, включая плагины и LLM"""
        await self.plugin_manager.cleanup()
        await self.llm.close()

    async def _prepare_llm_messages(
        self,
        message_text: str,
        system_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Подготовка сообщений для LLM"""
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
            
        messages.append({
            "role": "user",
            "content": message_text
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

        # Пропускаем через streaming_output_hooks всех плагинов
        for plugin in self.plugin_manager.get_all_plugins():
            if hasattr(plugin, 'streaming_output_hook'):
                logger.debug(f"Passing stream through plugin {plugin.__class__.__name__}")
                try:
                    plugin_stream = plugin.streaming_output_hook(current_stream)
                    logger.debug(f"Created stream for plugin {plugin.__class__.__name__}")
                    async for first_chunk in plugin_stream:
                        logger.debug(f"Got first chunk from {plugin.__class__.__name__}: {first_chunk}")
                        if first_chunk and first_chunk.stream:
                            current_stream = first_chunk
                            logger.debug(f"Updated current_stream from {plugin.__class__.__name__}")
                            break
                except Exception as e:
                    logger.error(f"Error in plugin {plugin.__class__.__name__}: {e}", exc_info=True)
                    raise

        # Отдаем финальный стрим и собираем последний чанк и tool_calls
        if current_stream and current_stream.stream:
            logger.debug("Starting to yield chunks from final stream")
            async for chunk in current_stream.stream:
                chunk.metadata.update(metadata)
                
                # Собираем tool_calls
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)
                    logger.debug(f"Added tool_calls: {chunk.tool_calls}")
                
                # Сохраняем последний чанк
                last_chunk = chunk
                logger.debug(f"Updated last chunk: {chunk}")
                
                yield chunk
            logger.debug("Finished yielding chunks from final stream")

        # После завершения стрима обрабатываем полное сообщение через output_hooks
        if last_chunk:
            logger.debug(f"Creating complete message from last chunk with content length {len(last_chunk.content)}")
            # Создаем финальное сообщение из последнего чанка
            final_message = IOMessage(
                type="text",
                content=last_chunk.content,  # Берем контент из последнего чанка
                metadata=metadata,
                source=current_stream.source,
                is_async=current_stream.is_async,
                tool_calls=tool_calls  # Используем накопленные tool_calls
            )
            
            logger.debug(f"Processing complete message through output_hooks")
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

    async def process_message(
        self,
        message: Union[str, IOMessage],
        system_prompt: Optional[str] = None,
        stream: bool = False,
        message_preprocessor: Optional[Callable[[IOMessage], Awaitable[IOMessage]]] = None,
        **kwargs
    ) -> Union[str, AsyncGenerator[IOMessage, None]]:
        """
        Обрабатывает сообщение пользователя
        
        Args:
            message: Сообщение для обработки (строка или IOMessage)
            system_prompt: Системный промпт (опционально)
            stream: Использовать стриминг
            message_preprocessor: Функция для предварительной обработки ответа от LLM
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            Union[str, AsyncGenerator[IOMessage, None]]: Ответ от LLM
        """
        logger.debug("process_message called with stream=%s, preprocessor=%s", 
                    stream, message_preprocessor.__name__ if message_preprocessor else None)
        
        # Получаем текст сообщения и метаданные
        message_text = message.content if isinstance(message, IOMessage) else message
        metadata = message.metadata if isinstance(message, IOMessage) else {}
        logger.debug("Message text: %s", message_text)
        logger.debug("Message metadata: %s", metadata)
        
        # Подготавливаем сообщения для LLM
        messages = await self._prepare_llm_messages(message_text, system_prompt)
        logger.debug("Prepared messages: %s", messages)
        
        # Получаем инструменты от плагинов
        tools = self.plugin_manager.get_all_tools()
        logger.debug("Got %d tools from plugins", len(tools) if tools else 0)
                
        # Получаем ответ от LLM
        logger.debug("Calling LLM.generate_response with stream=%s", stream)
        response = await self.llm.generate_response(
            messages=messages,
            tools=tools if tools else None,
            stream=stream,
            **kwargs
        )
        logger.debug("Got response from LLM: %s", response)

        if stream:
            logger.debug("Processing stream through plugins")
            stream_message = IOMessage.create_stream(response, metadata=metadata)
            
            async def stream_generator():
                async for chunk in self._process_stream_through_plugins(stream_message, metadata):
                    yield chunk
                    
            return stream_generator()
        else:
            # Для обычного ответа сначала применяем препроцессор, если есть
            response_message = response  # response уже является IOMessage
            response_message.metadata.update(metadata)
            
            if message_preprocessor:
                logger.debug("Applying message preprocessor")
                try:
                    response_message = await message_preprocessor(response_message)
                    logger.debug("Message preprocessor applied successfully")
                except Exception as e:
                    logger.error(f"Error in message preprocessor: {e}", exc_info=True)
            
            # Затем пропускаем через output_hooks
            logger.debug("Processing through output_hooks")
            for plugin in self.plugin_manager.get_all_plugins():
                if hasattr(plugin, 'output_hook'):
                    processed = await plugin.output_hook(response_message)
                    if processed is None:
                        return None
                    response_message = processed
                    
            return response_message

    async def handle_message(
        self,
        message: IOMessage,
        system_prompt: str = None,
        stream: bool = False
    ) -> Union[str, AsyncGenerator[IOMessage, None]]:
        """Обработка входящего сообщения"""
        logger.debug("BaseAgent.handle_message called with stream=%s", stream)
        
        try:
            # Обрабатываем через плагины
            logger.debug("Processing input through plugins")
            await self.plugin_manager.process_input(message)
            
            # Генерируем ответ через LLM
            logger.debug("Generating response through LLM")
            # Передаем весь IOMessage, а не только content
            response = await self.process_message(message, system_prompt, stream)
            logger.debug("Got response from LLM: %s", response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error in handle_message: {e}", exc_info=True)
            raise 