from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class PluginMetadata:
    """Метаданные плагина"""
    name: str
    description: str
    version: str
    priority: int = 0


class BasePlugin:
    """Базовый класс для всех плагинов"""
    
    def __init__(self):
        self._metadata = self.get_metadata()
    
    @property
    def name(self) -> str:
        """Имя плагина"""
        return self._metadata["name"]
        
    @property
    def priority(self) -> int:
        """Приоритет плагина"""
        return self._metadata["priority"]
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Возвращает метаданные плагина
        
        Returns:
            Dict с полями:
                name: Имя плагина
                description: Описание плагина
                version: Версия плагина
                priority: Приоритет плагина (больше - важнее)
        """
        raise NotImplementedError()
    
    async def init_database(self, connection_string: str):
        """Инициализирует базу данных плагина"""
        pass
    
    async def setup(self):
        """Инициализация плагина"""
        pass
    
    async def cleanup(self):
        """Очистка ресурсов"""
        pass
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Возвращает список доступных инструментов"""
        return []
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет инструмент"""
        raise NotImplementedError()
    
    async def rag_hook(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Хук для RAG (Retrieval Augmented Generation)
        
        Args:
            query: Запрос пользователя
            
        Returns:
            Дополнительный контекст для LLM или None
        """
        return None 