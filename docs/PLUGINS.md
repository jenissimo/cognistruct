# Архитектура плагинов CogniStruct 🧩

## Введение

Плагины в CogniStruct - это независимые модули, расширяющие функциональность агентов. Каждый плагин следует единому интерфейсу, что обеспечивает простоту интеграции и переиспользования.

## Базовая структура

### Метаданные плагина

Каждый плагин должен предоставлять метаданные через класс `PluginMetadata`:

```python
@dataclass
class PluginMetadata:
    name: str          # Уникальное имя плагина
    description: str = ""   # Описание функциональности
    version: str = "0.1.0"  # Версия плагина
    author: str = ""        # Автор плагина
    metadata: Dict[str, Any] = field(default_factory=dict)  # Дополнительные метаданные
    priority: int = 0  # Приоритет (больше - важнее)
```

### Базовый класс

Все плагины наследуются от `BasePlugin`, который определяет основной интерфейс:

```python
class BasePlugin:
    def __init__(self):
        self._metadata = self.get_metadata()
        self._supported_input_types: List[str] = []
        self._supported_output_types: List[str] = []
    
    @property
    def name(self) -> str:
        """Имя плагина"""
        return self._metadata["name"]
        
    @property
    def priority(self) -> int:
        """Приоритет плагина"""
        return self._metadata["priority"]

    @property
    def supported_input_types(self) -> List[str]:
        """Поддерживаемые типы входящих сообщений"""
        return self._supported_input_types

    @property
    def supported_output_types(self) -> List[str]:
        """Поддерживаемые типы исходящих сообщений"""
        return self._supported_output_types

    def get_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные плагина"""
        return {
            "name": "my_plugin",
            "description": "Описание плагина",
            "version": "1.0.0",
            "priority": 0
        }

    def register_input_type(self, message_type: str):
        """Регистрирует поддерживаемый тип входящих сообщений"""
        if message_type not in self._supported_input_types:
            self._supported_input_types.append(message_type)

    def register_output_type(self, message_type: str):
        """Регистрирует поддерживаемый тип исходящих сообщений"""
        if message_type not in self._supported_output_types:
            self._supported_output_types.append(message_type)
```

## Жизненный цикл

### 1. Инициализация

```python
async def setup(self):
    """
    Инициализация ресурсов плагина:
    - Подключение к внешним сервисам
    - Загрузка конфигурации
    - Инициализация кэша
    """
    pass
```

### 2. Работа с базой данных

```python
async def init_database(self, connection_string: str):
    """
    Инициализация базы данных:
    - Создание таблиц
    - Миграции
    - Начальные данные
    """
    pass
```

### 3. Очистка

```python
async def cleanup(self):
    """
    Освобождение ресурсов:
    - Закрытие соединений
    - Сохранение состояния
    - Очистка временных файлов
    """
    pass
```

## Функциональность

### Инструменты (Tools)

Плагины могут предоставлять инструменты для использования LLM:

```python
def get_tools(self) -> List[Dict[str, Any]]:
    return [{
        "name": "my_tool",
        "description": "Описание инструмента",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "Параметр 1"},
                "param2": {"type": "integer", "description": "Параметр 2"}
            },
            "required": ["param1"]
        }
    }]
```

### Выполнение инструментов

```python
async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
    """
    Выполнение инструмента:
    - Валидация параметров
    - Обработка ошибок
    - Возврат результата
    """
    if tool_name == "my_tool":
        return await self._handle_my_tool(params)
    raise ValueError(f"Unknown tool: {tool_name}")
```

### RAG-хуки

Плагины могут участвовать в обогащении контекста:

```python
async def rag_hook(self, query: str) -> Optional[Dict[str, Any]]:
    """
    Поиск релевантного контекста:
    - Векторный поиск
    - Фильтрация результатов
    - Форматирование контекста
    """
    results = await self._search_context(query)
    return {
        "type": "context",
        "content": results
    } if results else None
```

### I/O хуки

Плагины могут обрабатывать ввод/вывод через специальные хуки:

```python
@dataclass
class IOMessage:
    """Сообщение для I/O хуков"""
    type: str                     # Тип сообщения (text, image, action, etc)
    content: Any                  # Содержимое сообщения
    metadata: Dict[str, Any] = field(default_factory=dict) # Дополнительные данные
    source: str = ""             # Источник сообщения
    timestamp: float = field(default_factory=time.time) # Время создания

class BasePlugin:
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
```

#### Примеры использования

**1. Telegram плагин для подтверждения действий:**
```python
class TelegramPlugin(BasePlugin):
    async def output_hook(self, message: IOMessage) -> Optional[IOMessage]:
        # Если требуется подтверждение
        if message.type == "action_confirmation":
            chat_id = message.metadata.get("chat_id")
            action = message.content
            
            # Отправляем запрос подтверждения
            confirmation = await self.bot.send_message(
                chat_id,
                f"Подтвердите действие: {action}",
                reply_markup=self._get_confirmation_keyboard()
            )
            
            # Ждем ответа пользователя
            response = await self._wait_for_confirmation(confirmation.message_id)
            
            if response:
                # Возвращаем оригинальное сообщение для продолжения обработки
                return message
            return None  # Отменяем действие
            
        return message  # Пропускаем остальные типы сообщений
```

**2. CLI плагин для интерактивного ввода:**
```python
class CLIPlugin(BasePlugin):
    async def input_hook(self, message: IOMessage) -> bool:
        if message.type == "cli_input":
            # Запрашиваем ввод у пользователя
            user_input = input(message.content)
            
            # Сохраняем ответ в контексте
            self.context.set(message.metadata["response_key"], user_input)
            return True  # Прерываем обработку
            
        return False  # Продолжаем обработку
```

**3. API плагин для webhook уведомлений:**
```python
class WebhookPlugin(BasePlugin):
    async def input_hook(self, message: IOMessage) -> bool:
        if message.type == "webhook":
            # Обрабатываем входящий webhook
            payload = message.content
            
            # Проверяем подпись
            if not self._verify_signature(payload, message.metadata.get("signature")):
                return True  # Прерываем обработку
                
            # Добавляем в очередь обработки
            await self.queue.put(payload)
            return True
            
        return False
```

#### Преимущества подхода

1. **Универсальность**
   - Единый интерфейс для разных типов взаимодействия
   - Возможность комбинировать плагины
   - Простое добавление новых типов сообщений

2. **Гибкость**
   - Асинхронная обработка
   - Возможность модификации сообщений
   - Поддержка метаданных

3. **Расширяемость**
   - Плагины могут обрабатывать любые типы сообщений
   - Легко добавлять новые источники данных
   - Поддержка сложных сценариев взаимодействия

4. **Контроль**
   - Возможность отмены операций
   - Логирование всех взаимодействий
   - Обработка ошибок на уровне плагина

## Лучшие практики

### 1. Изоляция состояния
- Каждый плагин должен хранить своё состояние независимо
- Использовать dependency injection для внешних зависимостей
- Избегать глобальных переменных

### 2. Обработка ошибок
- Логировать все ошибки
- Предоставлять понятные сообщения об ошибках
- Реализовать механизм повторных попыток для нестабильных операций

### 3. Асинхронность
- Использовать `async/await` для I/O операций
- Не блокировать event loop
- Правильно закрывать ресурсы

### 4. Работа с контекстом и пользователями

Каждый плагин имеет доступ к глобальному контексту через `self.context`. Особенно важно правильно работать с `user_id`:

```python
class MyPlugin(BasePlugin):
    @property
    def user_id(self) -> int:
        """ID текущего пользователя из глобального контекста"""
        return self.context.get().user_id

    async def my_method(self, data: Dict[str, Any], user_id: Optional[int] = None):
        # Если user_id передан явно - используем его
        # Если нет - берем из контекста
        actual_user_id = user_id if user_id is not None else self.user_id
        
        # Важно! Используем is not None вместо or,
        # чтобы корректно обработать случай user_id = 0
        
        # Дальше работаем с actual_user_id...
```

#### Лучшие практики работы с user_id:

1. **Явное лучше неявного**
   - Всегда добавляйте `user_id` в схему данных
   - Документируйте поведение методов с `user_id`

2. **Безопасность**
   - Проверяйте права доступа к данным
   - Изолируйте данные разных пользователей
   - Не полагайтесь на отсутствие `user_id` как признак системного действия

3. **SQL и user_id**
   ```sql
   -- Правильно: явная фильтрация по user_id
   SELECT * FROM items WHERE user_id = ?
   
   -- Правильно: группировка по user_id
   SELECT id, ROW_NUMBER() OVER (
       PARTITION BY user_id 
       ORDER BY created_at DESC
   ) as rn FROM items
   ```

4. **Обработка значения по умолчанию**
   ```python
   # Правильно
   user_id = data.get("user_id")
   if user_id is not None:
       # Используем переданный user_id
   else:
       # Используем self.user_id из контекста
   
   # Неправильно - потеряем user_id = 0
   user_id = data.get("user_id") or self.user_id
   ```

### 5. Документация
- Документировать все публичные методы
- Предоставлять примеры использования
- Описывать требования и зависимости

## Примеры

### Простой плагин

```python
class CalculatorPlugin(BasePlugin):
    def get_metadata(self):
        return {
            "name": "calculator",
            "description": "Базовые математические операции",
            "version": "1.0.0",
            "priority": 1
        }
    
    def get_tools(self):
        return [{
            "name": "calculate",
            "description": "Выполняет математические вычисления",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Математическое выражение"
                    }
                },
                "required": ["expression"]
            }
        }]
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]):
        if tool_name == "calculate":
            return eval(params["expression"])
        raise ValueError(f"Unknown tool: {tool_name}")
```

### Плагин с состоянием

```python
class CachePlugin(BasePlugin):
    async def setup(self):
        self.cache = {}
        
    def get_tools(self):
        return [{
            "name": "cache_get",
            "description": "Получает значение из кэша",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        }, {
            "name": "cache_set",
            "description": "Сохраняет значение в кэш",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }]
    
    async def cleanup(self):
        self.cache.clear()
```

## Отладка

### Логирование

```python
from utils.logging import setup_logger

logger = setup_logger(__name__)

class MyPlugin(BasePlugin):
    async def setup(self):
        logger.info("Initializing MyPlugin")
        try:
            # initialization code
            logger.debug("MyPlugin initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MyPlugin: {e}")
            raise
```

### Тестирование

```python
import pytest

async def test_my_plugin():
    plugin = MyPlugin()
    await plugin.setup()
    
    try:
        result = await plugin.execute_tool("my_tool", {"param": "value"})
        assert result == expected_value
    finally:
        await plugin.cleanup()
```

## Управление плагинами

### Менеджер плагинов

Для управления плагинами используется класс `PluginManager`:

```python
class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_classes: Dict[str, Type[BasePlugin]] = {}
        self._input_handlers: Dict[str, List[BasePlugin]] = {}
        self._output_handlers: Dict[str, List[BasePlugin]] = {}
```

### Загрузка плагинов

Плагины могут загружаться автоматически или вручную:

```python
# Автоматическая загрузка при создании агента
agent = BaseAgent(llm, auto_load_plugins=True)  # По умолчанию True

# Ручная загрузка
agent = BaseAgent(llm, auto_load_plugins=False)
await agent.plugin_manager.load_plugins()
```

При загрузке плагинов:
- Каждый плагин должен находиться в отдельной поддиректории `plugins`
- Основной класс плагина должен быть определен в файле `plugin.py`
- Директории, начинающиеся с `_`, игнорируются

После загрузки плагины нужно инициализировать:
```python
await plugin_manager.init_plugin("telegram")  # Инициализация конкретного плагина
```

### Приоритеты и порядок выполнения

Плагины выполняются в порядке их приоритета (от большего к меньшему):
- Входящие сообщения обрабатываются до первого успешного обработчика
- Исходящие сообщения проходят через все обработчики последовательно
- RAG-хуки выполняются для всех плагинов параллельно
- Инструменты выполняются первым плагином, который их поддерживает

```python
# Пример порядка обработки сообщений
plugins = [
    TelegramPlugin(priority=100),  # Выполнится первым
    LoggingPlugin(priority=50),    # Выполнится вторым
    DefaultPlugin(priority=0)      # Выполнится последним
]

# Для входящих сообщений
for plugin in sorted_by_priority(plugins):
    if await plugin.input_hook(message):
        break  # Останавливаемся после первой успешной обработки

# Для исходящих сообщений
message = original_message
for plugin in sorted_by_priority(plugins):
    message = await plugin.output_hook(message)
    if message is None:
        break  # Сообщение отменено
```

### Методы менеджера

```python
class PluginManager:
    async def load_plugins(self, plugins_dir: str = "plugins"):
        """Загружает плагины из директории"""
        pass

    async def init_plugin(self, name: str, **kwargs) -> BasePlugin:
        """Инициализирует плагин с переданными параметрами"""
        pass

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Возвращает экземпляр плагина по имени"""
        pass

    def get_all_plugins(self) -> List[BasePlugin]:
        """Возвращает отсортированный по приоритету список плагинов"""
        pass

    async def process_input(self, message: IOMessage) -> bool:
        """Обрабатывает входящее сообщение через все подходящие плагины"""
        pass

    async def process_output(self, message: IOMessage) -> Optional[IOMessage]:
        """Обрабатывает исходящее сообщение через все подходящие плагины"""
        pass

    async def execute_rag_hooks(self, query: str) -> Dict[str, Any]:
        """Выполняет RAG-хуки всех плагинов"""
        pass

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет инструмент одного из плагинов"""
        pass

    async def cleanup(self):
        """Очищает ресурсы всех плагинов"""
        pass
```

### Типы сообщений

Плагины могут регистрировать поддерживаемые типы сообщений:

```python
class MyPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.register_input_type("text")
        self.register_input_type("image")
        self.register_output_type("text")
```

Менеджер плагинов автоматически маршрутизирует сообщения к нужным обработчикам:

```python
input_types, output_types = plugin_manager.get_supported_message_types()
handlers = plugin_manager.get_input_handlers("text")  # Плагины для обработки текста
``` 