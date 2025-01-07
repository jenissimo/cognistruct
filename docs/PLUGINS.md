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
    description: str   # Описание функциональности
    version: str       # Версия плагина
    priority: int = 0  # Приоритет (больше - важнее)
```

### Базовый класс

Все плагины наследуются от `BasePlugin`, который определяет основной интерфейс:

```python
class MyPlugin(BasePlugin):
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": "my_plugin",
            "description": "Описание плагина",
            "version": "1.0.0",
            "priority": 0
        }
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
    metadata: Dict[str, Any] = {} # Дополнительные данные
    source: str = ""             # Источник сообщения
    timestamp: float = time.time() # Время создания

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

### 4. Документация
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