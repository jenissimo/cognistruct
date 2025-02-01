"""Базовые классы для плагинов"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, AsyncGenerator, Union

from .messages import IOMessage
from .context import GlobalContext, RequestContext
from ..llm.interfaces import ToolSchema

@dataclass
class PluginMetadata:
    """Метаданные плагина"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    priority: int = 0  # Приоритет для сортировки (больше - важнее)
    author: str = ""  # Добавляем поле для автора

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
        self.agent = None  # Ссылка на агента как обычный атрибут
    
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
    
    def get_tools(self) -> List[Union[ToolSchema, Dict[str, Any]]]:
        """
        Возвращает список доступных инструментов
        
        Returns:
            List[Union[ToolSchema, Dict[str, Any]]]: Список инструментов в виде объектов ToolSchema
            или словарей в формате OpenAI
        """
        return []
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any], context: Optional[RequestContext] = None) -> Any:
        """
        Выполняет инструмент с заданными параметрами
        
        Args:
            tool_name: Имя инструмента
            params: Параметры для выполнения
            context: Контекст запроса
            
        Returns:
            Any: Результат выполнения инструмента
            
        Raises:
            ValueError: Если инструмент не найден
        """
        raise NotImplementedError("Plugin must implement execute_tool method")

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
    
    async def rag_hook(self, message: IOMessage) -> Optional[Dict[str, Any]]:
        """
        Хук для RAG (Retrieval Augmented Generation)
        
        Args:
            message: Сообщение пользователя с контекстом и метаданными
            
        Returns:
            Дополнительный контекст для LLM или None
        """
        return None

    async def input_hook(self, message: IOMessage) -> bool:
        """
        Обработка входящих сообщений.
        По умолчанию пропускает все сообщения дальше.
        
        Args:
            message: Входящее сообщение
            
        Returns:
            True - пропустить сообщение дальше
            False - заблокировать сообщение
        """
        return True  # По умолчанию пропускаем все сообщения
        
    async def output_hook(self, message: IOMessage) -> Optional[IOMessage]:
        """
        Обработка исходящих сообщений
        
        Args:
            message: Исходящее сообщение
            
        Returns:
            Optional[IOMessage]: Модифицированное сообщение или None если сообщение не нужно отправлять
        """
        return message
        
    async def streaming_output_hook(self, message: IOMessage) -> AsyncGenerator[IOMessage, None]:
        """
        Обработка потоковых сообщений. Этот хук вызывается для сообщений с типом "stream".
        
        Плагины могут переопределить этот метод для:
        - Модификации чанков стрима
        - Добавления своей логики обработки
        - Фильтрации или агрегации чанков
        
        Args:
            message: Стрим-сообщение с полем stream, содержащим AsyncGenerator[IOMessage, None]
            
        Yields:
            IOMessage: Обработанные чанки данных
        """
        if not message.stream:
            yield message
            return
            
        # Создаем новый генератор, который будет обрабатывать чанки
        async def process_stream():
            async for chunk in message.stream:
                processed_chunk = self._process_stream_chunk(chunk)
                if processed_chunk is not None:
                    yield processed_chunk
        
        # Создаем новое сообщение с новым генератором
        new_message = IOMessage(
            type=message.type,
            content=message.content,
            metadata=message.metadata,
            source=message.source,
            is_async=message.is_async,
            stream=process_stream()
        )
        
        yield new_message

    def _process_stream_chunk(self, chunk: IOMessage) -> Optional[IOMessage]:
        """
        Обработка отдельного чанка стрима. Этот метод вызывается для каждого чанка в streaming_output_hook.
        
        Плагины могут переопределить этот метод для:
        - Модификации содержимого чанка
        - Фильтрации чанков (возврат None для пропуска)
        - Добавления метаданных
        
        Args:
            chunk: Входящий чанк (обычно с типом "stream_chunk")
            
        Returns:
            Optional[IOMessage]: Обработанный чанк или None если чанк нужно пропустить
            
        Example:
            ```python
            def _process_stream_chunk(self, chunk: IOMessage) -> Optional[IOMessage]:
                # Пропускаем пустые чанки
                if not chunk.content:
                    return None
                    
                # Добавляем timestamp в метаданные
                chunk.metadata["processed_at"] = time.time()
                return chunk
            ```
        """
        return chunk

    def register_input_type(self, message_type: str):
        """Регистрирует поддерживаемый тип входящих сообщений"""
        if message_type not in self._supported_input_types:
            self._supported_input_types.append(message_type)

    def register_output_type(self, message_type: str):
        """Регистрирует поддерживаемый тип исходящих сообщений"""
        if message_type not in self._supported_output_types:
            self._supported_output_types.append(message_type) 