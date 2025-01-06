from typing import Any, Dict, List, Optional, Union, Literal
import json

from llm import BaseLLM, LLMResponse, ToolCall
from plugins import PluginManager
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

    async def setup(self):
        """Инициализация агента"""
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
        response_type: Literal["text", "json"] = "text",
        llm_params: Optional[Dict[str, Any]] = None
    ) -> Union[str, dict]:
        """
        Обрабатывает входящее сообщение
        
        Args:
            message: Текст сообщения от пользователя
            system_prompt: Системный промпт для модели
            response_type: Тип ответа ("text" или "json")
            llm_params: Дополнительные параметры для LLM
            
        Returns:
            Ответ агента (строка или JSON в зависимости от response_type)
        """
        logger.info("Processing message: %s", message)
        
        # Создаем временную историю для этого запроса
        current_history = []
        
        # Обновляем системный промпт только если он изменился
        if self._update_system_prompt(system_prompt) and system_prompt:
            current_history.append({
                "role": "system",
                "content": system_prompt
            })
        
        # Добавляем предыдущую историю
        current_history.extend(self.conversation_history)
        
        # Добавляем текущее сообщение
        current_history.append({"role": "user", "content": message})
        
        # Получаем и добавляем RAG контекст
        rag_context = await self._get_formatted_rag_context(message)
        if rag_context:
            current_history.append({
                "role": "system",
                "content": f"Additional context:\n{rag_context}"
            })
        
        # Получаем доступные инструменты
        tools = self._get_available_tools()
        logger.debug("Available tools: %s", [t.name for t in tools])
        
        # Подготавливаем параметры для LLM
        llm_call_params = {
            "messages": current_history,
            "tools": tools,
        }
        
        # Если запрошен JSON-ответ, указываем это для LLM
        if response_type == "json":
            llm_call_params["response_format"] = "json_object"
            
        # Добавляем дополнительные параметры
        if llm_params:
            llm_call_params.update(llm_params)
        
        # Генерируем ответ через LLM
        response: LLMResponse = await self.llm.generate_response(**llm_call_params)
        
        logger.info("LLM response: %s", response.content)
        if response.tool_calls:
            logger.debug("Tool calls: %s", response.tool_calls)
        
        # Если есть вызов инструмента, выполняем его
        if response.tool_calls:
            logger.debug("Tool calls detected, executing...")
            tool_result = await self._execute_tool_call(response.tool_calls, response_type)
            
            # Добавляем результат выполнения инструмента в историю
            logger.debug("Adding tool results to conversation history")
            
            # Преобразуем ToolCall в словарь для JSON
            tool_calls_dict = []
            for call in response.tool_calls:
                tool_calls_dict.append({
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.tool,
                        "arguments": json.dumps(call.params)
                    }
                })
            
            # Сначала добавляем сообщение от ассистента с вызовом инструмента
            current_history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_dict
            })
            
            # Затем добавляем результаты выполнения инструментов
            for call in response.tool_calls:
                current_history.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tool_result
                })
            
            # Получаем финальный ответ от LLM с учетом результата
            logger.debug("Getting final response from LLM with tool results")
            response = await self.llm.generate_response(
                messages=current_history,
                **(llm_params or {})
            )
            logger.info("Final LLM response: %s", response.content)
        
        # Добавляем ответ ассистента в основную историю
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content
        })
        
        # Возвращаем ответ в нужном формате
        if response_type == "json":
            return {
                "response": response.content,
                "history": current_history,
                "tool_calls": response.tool_calls
            }
        else:
            return response.content 