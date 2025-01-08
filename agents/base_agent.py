from typing import Any, Dict, List, Optional, Union, Literal, AsyncGenerator
import json

from llm import BaseLLM, LLMResponse, ToolCall, StreamChunk
from plugins import PluginManager
from plugins.base_plugin import IOMessage
from utils.logging import setup_logger


logger = setup_logger(__name__)


class BaseAgent:
    """Базовый класс для всех агентов"""

    def __init__(self, llm: BaseLLM, auto_load_plugins: bool = True):
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
        async def tool_executor(tool_name: str, **kwargs):
            return await self.plugin_manager.execute_tool(tool_name, kwargs)
            
        self.llm.set_tool_executor(tool_executor)

    def _update_system_prompt(self, new_prompt: Optional[str]) -> bool:
        """
        Обновляет системный промпт если он изменился
        
        Returns:
            bool: True если промпт был обновлен
        """
        if new_prompt != self._current_system_prompt:
            self._current_system_prompt = new_prompt
            return True
        return False

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

    def _get_available_tools(self):
        """Собирает все доступные инструменты от плагинов"""
        tools = []
        for plugin in self.plugin_manager.get_all_plugins():
            tools.extend(plugin.get_tools())
        return tools

    async def _execute_tool_call(self, tool_calls: List[ToolCall], response_type: str = "text") -> str:
        """Выполняет вызов инструмента и форматирует результат"""
        logger.info("Executing %d tool calls", len(tool_calls))
        print(tool_calls)

        if response_type == "json":
            results = []
            for call in tool_calls:
                try:
                    logger.info("Executing tool %s with params: %s", call.tool, call.params)
                    result = await self.plugin_manager.execute_tool(call.tool, call.params)
                    logger.info("Tool %s returned: %s", call.tool, result)
                    results.append({
                        "tool": call.tool,
                        "result": result,
                        "success": True
                    })
                except Exception as e:
                    logger.error("Tool %s failed: %s", call.tool, str(e))
                    results.append({
                        "tool": call.tool,
                        "error": str(e),
                        "success": False
                    })
            formatted_result = json.dumps(results, ensure_ascii=False)
            logger.info("Tool execution results (JSON): %s", formatted_result)
            return formatted_result
        
        # Для текстового формата сразу форматируем результаты
        formatted_results = []
        for call in tool_calls:
            try:
                logger.info("Executing tool %s with params: %s", call.tool, call.params)
                result = await self.plugin_manager.execute_tool(call.tool, call.params)
                logger.info("Tool %s returned: %s", call.tool, result)
                formatted_results.append(f"Tool {call.tool} returned: {result}")
            except Exception as e:
                logger.error("Tool %s failed: %s", call.tool, str(e))
                formatted_results.append(f"Tool {call.tool} failed: {str(e)}")
        
        formatted_result = "\n".join(formatted_results)
        logger.info("Tool execution results (text): %s", formatted_result)
        return formatted_result

    async def _get_formatted_rag_context(self, query: str) -> Optional[str]:
        """
        Получает и форматирует RAG контекст
        
        Args:
            query: Запрос пользователя
            
        Returns:
            Отформатированный контекст или None
        """
        context = await self.plugin_manager.execute_rag_hooks(query)
        if not context:
            return None
            
        sections = []
        for plugin_name, plugin_context in context.items():
            sections.append(f"Context from {plugin_name}:")
            if isinstance(plugin_context, dict):
                for key, value in plugin_context.items():
                    sections.append(f"{key}: {value}")
            else:
                sections.append(str(plugin_context))
        return "\n".join(sections)

    async def process_message(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[str, AsyncGenerator[StreamChunk, None]]:
        """
        Обрабатывает входящее сообщение
        
        Args:
            message: Входящее сообщение
            system_prompt: Системный промпт (опционально)
            stream: Использовать потоковую генерацию
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            - При stream=False: строка с ответом
            - При stream=True: AsyncGenerator[StreamChunk, None] для потоковой генерации
        """
        # Создаем объект сообщения
        io_message = IOMessage(content=message)
        
        # Выполняем input_hooks
        for plugin in self.plugin_manager.get_all_plugins():
            if hasattr(plugin, 'input_hook'):
                if await plugin.input_hook(io_message):
                    break
        
        # Создаем базовый список сообщений
        messages = []
        
        # Добавляем системный промпт если есть
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # Собираем контекст из RAG-хуков всех плагинов
        context = {}
        for plugin in self.plugin_manager.get_all_plugins():
            if hasattr(plugin, 'rag_hook'):
                plugin_context = await plugin.rag_hook(message)
                if plugin_context:
                    context.update(plugin_context)
        
        # Если есть контекст, добавляем его в системный промпт
        if context:
            context_message = "Контекст из предыдущих сообщений:\n" + \
                             "\n".join(f"{k}: {v}" for k, v in context.items())
            messages.append({
                "role": "system",
                "content": context_message
            })
        
        # Добавляем сообщение пользователя
        messages.append({
            "role": "user",
            "content": message
        })
        
        try:
            # Получаем ответ от LLM
            response = await self.llm.generate_response(
                messages=messages,
                tools=self.plugin_manager.get_all_tools(),
                stream=stream,
                **kwargs
            )
            
            if stream:
                # При стриминге возвращаем генератор
                async def stream_with_hooks():
                    current_content = ""
                    async for chunk in response:
                        # Обновляем текущий контент
                        if chunk.delta:
                            current_content += chunk.delta
                        yield chunk

                # Создаем генератор
                stream_generator = stream_with_hooks()
                
                # Создаем объект сообщения для стрима
                stream_message = IOMessage(
                    type="stream",
                    content="",  # Начальный контент пустой
                    stream=stream_generator  # Передаем генератор
                )
                
                # Выполняем output_hooks
                for plugin in self.plugin_manager.get_all_plugins():
                    if hasattr(plugin, 'output_hook'):
                        await plugin.output_hook(stream_message)
                
                # Возвращаем тот же генератор - он еще не использован,
                # так как консольный плагин только сохранил его для последующего использования
                return stream_generator
            else:
                # Создаем объект ответного сообщения
                response_message = IOMessage(
                    type="text",
                    content=response.content
                )
                
                # Выполняем output_hooks
                for plugin in self.plugin_manager.get_all_plugins():
                    if hasattr(plugin, 'output_hook'):
                        await plugin.output_hook(response_message)
                
                return response.content
                
        except Exception as e:
            logger.exception("Error processing message")
            raise 