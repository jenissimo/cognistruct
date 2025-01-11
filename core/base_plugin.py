from typing import Dict, List, Any, Optional, Union, AsyncGenerator
from dataclasses import dataclass, field
import time

from llm.interfaces import StreamChunk
from core.context import GlobalContext


@dataclass
class PluginMetadata:
    """Метаданные плагина"""
    name: str
    description: str = ""
    version: str = "0.1.0"
    author: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class IOMessage:
    """Сообщение для I/O хуков"""
    type: str = "text"           # Тип сообщения (text, image, action, stream, etc)
    content: Any = None          # Содержимое сообщения
    metadata: Dict[str, Any] = field(default_factory=dict)  # Дополнительные данные
    source: str = ""            # Источник сообщения
    timestamp: float = field(default_factory=time.time)  # Время создания
    stream: Optional[AsyncGenerator[StreamChunk, None]] = None  # Стрим для потоковой генерации


class BasePlugin:
    """
    Базовый класс для всех плагинов
    
    Плагин может работать с данными любым удобным способом:
    - Использовать SQLite для локального хранения
    - Подключаться к внешним БД
    - Хранить данные в файлах
    - Использовать кэш в памяти
    
    Работа с данными должна быть инкапсулирована внутри плагина
    и инициализироваться в методе setup() при необходимости.
    """
    
    def __init__(self):
        self._metadata = self.get_metadata()
        self._supported_input_types: List[str] = []
        self._supported_output_types: List[str] = []
        self.context = GlobalContext
    
    @property
    def name(self) -> str:
        """Имя плагина"""
        return self._metadata.name
        
    @property
    def priority(self) -> int:
        """Приоритет плагина"""
        return self._metadata.priority

    @property
    def user_id(self) -> int:
        """ID текущего пользователя из глобального контекста"""
        return self.context.get().user_id

    @property
    def supported_input_types(self) -> List[str]:
        """Поддерживаемые типы входящих сообщений"""
        return self._supported_input_types

    @property
    def supported_output_types(self) -> List[str]:
        """Поддерживаемые типы исходящих сообщений"""
        return self._supported_output_types
    
    def get_metadata(self) -> PluginMetadata:
        """
        Возвращает метаданные плагина
        
        Returns:
            PluginMetadata: метаданные плагина
        """
        raise NotImplementedError()
    
    async def setup(self):
        """
        Инициализация плагина
        
        В этом методе плагин может:
        - Инициализировать соединения с БД
        - Создавать необходимые таблицы
        - Загружать конфигурацию
        - Подключаться к внешним сервисам
        """
        pass
    
    async def cleanup(self):
        """
        Очистка ресурсов
        
        В этом методе плагин должен:
        - Закрыть соединения с БД
        - Сохранить состояние
        - Освободить ресурсы
        """
        pass
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Возвращает список доступных инструментов"""
        return []
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет инструмент"""
        raise NotImplementedError()

    # CRUDS базовые методы
    async def create(self, data: Dict[str, Any]) -> Any:
        """
        Создает новый объект
        
        Args:
            data: Данные для создания объекта
            
        Returns:
            ID созданного объекта или сам объект
        """
        raise NotImplementedError()
        
    async def read(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Получает объект по ID
        
        Args:
            id: Идентификатор объекта
            
        Returns:
            Объект или None, если не найден
        """
        raise NotImplementedError()
        
    async def update(self, id: str, data: Dict[str, Any]) -> bool:
        """
        Обновляет существующий объект
        
        Args:
            id: Идентификатор объекта
            data: Новые данные
            
        Returns:
            True если объект обновлен, False если объект не найден
        """
        raise NotImplementedError()
        
    async def delete(self, id: str) -> bool:
        """
        Удаляет объект
        
        Args:
            id: Идентификатор объекта
            
        Returns:
            True если объект удален, False если объект не найден
        """
        raise NotImplementedError()
        
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Поиск объектов по параметрам
        
        Args:
            query: Параметры поиска
            
        Returns:
            Список найденных объектов
        """
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

    async def input_hook(self, message: IOMessage) -> bool:
        """
        Обработка входящих сообщений
        
        Args:
            message: Входящее сообщение
            
        Returns:
            True если сообщение обработано, False если нужно продолжить обработку
        """
        return False
        
    async def output_hook(self, message: IOMessage) -> Optional[IOMessage]:
        """
        Обработка исходящих сообщений
        
        Args:
            message: Исходящее сообщение
            
        Returns:
            Модифицированное сообщение или None если сообщение не нужно отправлять
        """
        return message

    def register_input_type(self, message_type: str):
        """Регистрирует поддерживаемый тип входящих сообщений"""
        if message_type not in self._supported_input_types:
            self._supported_input_types.append(message_type)

    def register_output_type(self, message_type: str):
        """Регистрирует поддерживаемый тип исходящих сообщений"""
        if message_type not in self._supported_output_types:
            self._supported_output_types.append(message_type) 