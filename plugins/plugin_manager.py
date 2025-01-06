import importlib
import os
from typing import Dict, List, Optional, Type, Any

from .base_plugin import BasePlugin
from utils.logging import setup_logger


logger = setup_logger(__name__)


class PluginManager:
    """Менеджер для управления плагинами"""

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_classes: Dict[str, Type[BasePlugin]] = {}

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
        self._plugins[name] = plugin

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
                    print(f"Error loading plugin {item}: {e}")

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

    async def init_plugin(self, name: str, **kwargs) -> BasePlugin:
        """Инициализирует плагин"""
        if name not in self._plugin_classes:
            raise ValueError(f"Plugin {name} not found")
            
        if name in self._plugins:
            raise ValueError(f"Plugin {name} already initialized")
            
        plugin_class = self._plugin_classes[name]
        plugin = plugin_class()
        
        # Инициализируем базу данных если нужно
        if kwargs.get('init_db', True):
            await plugin.init_database(
                kwargs.get('db_connection_string', "sqlite+aiosqlite:///plugins.db")
            )
            
        # Вызываем setup
        await plugin.setup()
        
        self._plugins[name] = plugin
        return plugin

    async def cleanup(self):
        """Очищает ресурсы всех плагинов"""
        for plugin in self._plugins.values():
            await plugin.cleanup()
        self._plugins.clear()

    async def execute_rag_hooks(self, query: str) -> Dict[str, Any]:
        """Выполняет RAG-хуки всех плагинов"""
        context = {}
        for plugin in self.get_all_plugins():
            try:
                plugin_context = await plugin.rag_hook(query)
                if plugin_context:
                    context[plugin.name] = plugin_context
            except Exception as e:
                print(f"Error in RAG hook of plugin {plugin.name}: {e}")
        return context

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет инструмент одного из плагинов"""
        # Сначала ищем плагин, у которого есть этот инструмент
        for plugin in self.get_all_plugins():
            if any(tool.name == tool_name for tool in plugin.get_tools()):
                try:
                    return await plugin.execute_tool(tool_name, params)
                except Exception as e:
                    logger.error("Error executing tool %s in plugin %s: %s", 
                               tool_name, plugin.name, str(e))
                    raise
        
        raise ValueError(f"Tool {tool_name} not found in any plugin") 