import importlib
import os
from typing import Dict, List, Optional, Type, Any, Tuple, Set, Union, AsyncContextManager
from contextlib import contextmanager, asynccontextmanager
import logging

from .base_plugin import BasePlugin, IOMessage
from cognistruct.utils.logging import setup_logger
from ..llm.interfaces import ToolSchema
from .context import RequestContext


logger = logging.getLogger(__name__)


class PluginManager:
    """Менеджер для управления плагинами"""

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_classes: Dict[str, Type[BasePlugin]] = {}
        self._input_handlers: Dict[str, List[BasePlugin]] = {}  # type -> [plugins]
        self._output_handlers: Dict[str, List[BasePlugin]] = {}  # type -> [plugins]
        self._allowed_tools: Optional[Set[str]] = None  # Добавляем список разрешенных инструментов
        self.agent = None  # Ссылка на агента

    def set_agent(self, agent):
        """Устанавливает ссылку на агента"""
        self.agent = agent
        # Обновляем ссылку на агента у существующих плагинов
        for plugin in self._plugins.values():
            setattr(plugin, 'agent', agent)

    def register_plugin_class(self, name: str, plugin_class: Type[BasePlugin]):
        """Регистрирует класс плагина"""
        self._plugin_classes[name] = plugin_class

    def register_plugin(self, name: str, plugin: BasePlugin):
        """
        Регистрирует инстанс плагина
        
        Args:
            name: Имя плагина
            plugin: Инстанс плагина
        """
        if name in self._plugins:
            raise ValueError(f"Plugin {name} already registered")
            
        # Регистрируем плагин
        self._plugins[name] = plugin
        
        # Устанавливаем ссылку на агента
        if self.agent:
            plugin.agent = self.agent
        
        # Регистрируем обработчики I/O
        for input_type in plugin.supported_input_types:
            if input_type not in self._input_handlers:
                self._input_handlers[input_type] = []
            self._input_handlers[input_type].append(plugin)
            
        for output_type in plugin.supported_output_types:
            if output_type not in self._output_handlers:
                self._output_handlers[output_type] = []
            self._output_handlers[output_type].append(plugin)

    async def load_plugins(self, plugins_dir: str = "plugins"):
        """Загружает плагины из директории"""
        for item in os.listdir(plugins_dir):
            if os.path.isdir(os.path.join(plugins_dir, item)) and not item.startswith('_'):
                try:
                    # Пытаемся загрузить модуль плагина
                    module = importlib.import_module(f".{item}.plugin", package="plugins")
                    # Ищем класс плагина
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BasePlugin) and 
                            attr != BasePlugin):
                            self.register_plugin_class(item, attr)
                except Exception as e:
                    logger.error(f"Error loading plugin {item}: {e}")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Возвращает экземпляр плагина по имени"""
        return self._plugins.get(name)

    def get_all_plugins(self) -> List[BasePlugin]:
        """Возвращает список всех активных плагинов"""
        return sorted(
            self._plugins.values(),
            key=lambda x: x.priority,
            reverse=True
        )

    def get_input_handlers(self, message_type: str) -> List[BasePlugin]:
        """Возвращает список плагинов, обрабатывающих входящие сообщения данного типа"""
        return sorted(
            self._input_handlers.get(message_type, []),
            key=lambda x: x.priority,
            reverse=True
        )

    def get_output_handlers(self, message_type: str) -> List[BasePlugin]:
        """Возвращает список плагинов, обрабатывающих исходящие сообщения данного типа"""
        return sorted(
            self._output_handlers.get(message_type, []),
            key=lambda x: x.priority,
            reverse=True
        )

    def get_supported_message_types(self) -> Tuple[List[str], List[str]]:
        """Возвращает списки поддерживаемых типов входящих и исходящих сообщений"""
        return (
            sorted(self._input_handlers.keys()),
            sorted(self._output_handlers.keys())
        )

    async def process_input(self, message: IOMessage) -> bool:
        """
        Обрабатывает входящее сообщение через все подходящие плагины
        
        Returns:
            True если сообщение было обработано, False если нет
        """
        handlers = self.get_input_handlers(message.type)
        for plugin in handlers:
            try:
                if await plugin.input_hook(message):
                    return True
            except Exception as e:
                logger.error(f"Error in input hook of plugin {plugin.name}: {e}")
        return False

    async def process_output(self, message: IOMessage) -> Optional[IOMessage]:
        """
        Обрабатывает исходящее сообщение через все подходящие плагины
        
        Returns:
            Модифицированное сообщение или None если сообщение отменено
        """
        current_message = message
        handlers = self.get_output_handlers(message.type)
        
        for plugin in handlers:
            try:
                result = await plugin.output_hook(current_message)
                if result is None:
                    return None  # Сообщение отменено
                current_message = result
            except Exception as e:
                logger.error(f"Error in output hook of plugin {plugin.name}: {e}")
                
        return current_message

    async def init_plugin(self, name: str, **kwargs) -> BasePlugin:
        """
        Инициализирует плагин
        
        Args:
            name: Имя плагина
            **kwargs: Дополнительные параметры, передаваемые в setup()
        """
        if name not in self._plugin_classes:
            raise ValueError(f"Plugin {name} not found")
            
        if name in self._plugins:
            raise ValueError(f"Plugin {name} already initialized")
            
        plugin_class = self._plugin_classes[name]
        plugin = plugin_class()
        
        try:
            # Вызываем setup с переданными параметрами
            await plugin.setup(**kwargs)
        except Exception as e:
            logger.error(f"Failed to setup plugin {name}: {e}")
            raise
        
        # Регистрируем плагин
        self.register_plugin(name, plugin)
        return plugin

    async def cleanup(self):
        """Очищает ресурсы всех плагинов"""
        for plugin in self._plugins.values():
            await plugin.cleanup()
        self._plugins.clear()
        self._input_handlers.clear()
        self._output_handlers.clear()

    async def execute_rag_hooks(self, message: IOMessage) -> Dict[str, Any]:
        """
        Выполняет RAG-хуки всех плагинов
        
        Args:
            message: Сообщение пользователя с контекстом и метаданными
            
        Returns:
            Dict[str, Any]: Дополнительный контекст от плагинов
        """
        context = {}
        for plugin in self.get_all_plugins():
            try:
                plugin_context = await plugin.rag_hook(message)
                if plugin_context:
                    context[plugin.name] = plugin_context
            except Exception as e:
                logger.error(f"Error in RAG hook of plugin {plugin.name}: {e}")
        return context

    async def execute_tool(self, tool_name: str, params: Dict[str, Any], context: Optional[RequestContext] = None) -> Any:
        """
        Выполняет инструмент одного из плагинов
        
        Args:
            tool_name: Имя инструмента
            params: Параметры для выполнения
            context: Контекст запроса
        """
        # Сначала ищем плагин, у которого есть этот инструмент
        for plugin in self.get_all_plugins():
            if any(tool.name == tool_name for tool in plugin.get_tools()):
                try:
                    return await plugin.execute_tool(tool_name, params, context)
                except Exception as e:
                    logger.error("Error executing tool %s in plugin %s: %s", 
                               tool_name, plugin.name, str(e))
                    raise
        
        raise ValueError(f"Tool {tool_name} not found in any plugin")

    @asynccontextmanager
    async def limit_tools(self, allowed_tools: List[str]):
        """Временно ограничивает доступные инструменты"""
        previous = self._allowed_tools
        try:
            self._allowed_tools = set(allowed_tools)
            yield
        finally:
            self._allowed_tools = previous
            
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Возвращает список доступных инструментов от всех плагинов
        
        Returns:
            List[Dict[str, Any]]: Список инструментов в формате OpenAI
        """
        tools = []
        for plugin in self.get_all_plugins():
            plugin_tools = plugin.get_tools()
            if self._allowed_tools is not None:
                # Фильтруем инструменты если есть ограничения
                plugin_tools = [
                    tool for tool in plugin_tools 
                    if (isinstance(tool, dict) and tool["name"] in self._allowed_tools) or
                       (isinstance(tool, ToolSchema) and tool.name in self._allowed_tools)
                ]
            
            # Конвертируем все инструменты в формат OpenAI
            for tool in plugin_tools:
                if isinstance(tool, dict):
                    tools.append({
                        "type": "function",
                        "function": tool
                    })
                else:
                    # Собираем параметры
                    properties = {}
                    required = []
                    for param in tool.parameters:
                        properties[param.name] = {
                            "type": param.type,
                            "description": param.description
                        }
                        if param.required:
                            required.append(param.name)

                    # Формируем схему функции
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": {
                                "type": "object",
                                "properties": properties,
                                "required": required
                            }
                        }
                    })
                    
        return tools 