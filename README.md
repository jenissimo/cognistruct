# CogniStruct 🤖

Фреймворк для создания интеллектуальных агентов с поддержкой плагинов и инструментов. CogniStruct позволяет быстро создавать и расширять возможности агентов через систему плагинов, обеспечивая гибкую архитектуру и простоту разработки.

## Философия

CogniStruct построен на принципах:

### 🧩 Модульность как основа
Каждый компонент системы - независимый модуль с четко определенным интерфейсом:
- Агенты отвечают за обработку сообщений и координацию
- Плагины предоставляют конкретные возможности через:
  - Инструменты (tools) для LLM
  - I/O хуки для обработки сообщений
  - RAG хуки для обогащения контекста
- LLM-провайдеры абстрагируют работу с моделями

### 🔧 Конструктор возможностей
Создание агента - это сборка из готовых компонентов:
- Выбор базового агента с нужной логикой
- Подключение необходимых плагинов
- Настройка системного промпта
- Добавление специфичной функциональности

### 🎯 Разделение ответственности
Каждый модуль решает свою задачу:
- Агент не знает деталей работы плагинов
- Плагины не зависят от конкретной LLM
- LLM не привязана к бизнес-логике

### 🔄 Простота расширения
Добавление новых возможностей не требует изменения существующего кода:
- Новые плагины регистрируются автоматически
- Инструменты доступны через единый интерфейс
- Поддержка новых LLM через абстракцию

### 📦 Переиспользование компонентов
Модули можно комбинировать для разных задач:
- Один плагин в разных агентах
- Разные LLM с одними плагинами
- Общие инструменты для разных задач

## Возможности

- 🔌 Расширяемая архитектура на основе плагинов
- 🛠 Поддержка инструментов (function calling)
- 📝 Сохранение истории диалога
- 🌍 Учет часового пояса пользователя
- 📊 Поддержка JSON и текстовых ответов
- 🔍 Контекстный поиск через RAG-хуки плагинов
- 🔄 Асинхронное выполнение операций
- 🎯 Приоритизация плагинов
- 🤖 Поддержка локальных моделей через Ollama

## Архитектура

### Основные компоненты

- `BaseAgent` - базовый класс агента, обрабатывающий сообщения и управляющий плагинами
- `PluginManager` - менеджер для загрузки и управления плагинами
- `BaseLLM` - абстрактный класс для работы с языковыми моделями
- `OpenAIService` - универсальная реализация для работы с OpenAI-совместимыми API:
  - OpenAI
  - DeepSeek
  - Ollama

### Плагины

CogniStruct предоставляет гибкую систему плагинов с несколькими типами расширений:

#### 🛠 Инструменты (Tools)
Плагины могут предоставлять инструменты для LLM:
```python
def get_tools(self):
    return [{
        "name": "calculate",
        "description": "Выполняет математические вычисления",
        "parameters": {
            "expression": {"type": "string"}
        }
    }]
```

#### 🔄 I/O хуки
Обработка входящих и исходящих сообщений:
```python
async def input_hook(self, message: IOMessage) -> bool:
    # Обработка входящего сообщения
    if message.type == "telegram":
        await self.process_telegram_message(message)
        return True
    return False
```

#### 🔍 RAG хуки
Обогащение контекста дополнительными данными:
```python
async def rag_hook(self, query: str) -> Optional[Dict]:
    # Поиск релевантной информации
    results = await self.search_knowledge_base(query)
    return {"context": results} if results else None
```

#### 📦 Управление состоянием
Каждый плагин может работать с данными удобным способом:
- Локальная SQLite база
- Внешние БД (PostgreSQL, MongoDB)
- Файловое хранилище
- Кэш в памяти

В комплекте идут демонстрационные плагины:
- `CalculatorPlugin` - математические вычисления
- `SchedulerPlugin` - планирование задач

### Пример создания агента

Рассмотрим создание простого агента для обработки задач:

```python
from typing import Optional
from agents.base_agent import BaseAgent
from llm import DeepSeekLLM, DeepSeekConfig
from plugins.example_plugin.plugin import CalculatorPlugin
from utils import Config, setup_logger

logger = setup_logger(__name__)

class TaskAgent(BaseAgent):
    """Агент для обработки задач с поддержкой вычислений"""
    
    def __init__(self):
        # Загружаем конфигурацию
        config = Config.load()
        
        # Инициализируем LLM
        llm = DeepSeekLLM(
            DeepSeekConfig(
                api_key=config.deepseek_api_key
            )
        )
        
        # Инициализируем базовый класс
        super().__init__(llm=llm, auto_load_plugins=False)
        
    async def setup(self):
        """Инициализация агента"""
        # Создаем и настраиваем плагины
        calculator = CalculatorPlugin()
        await calculator.setup()
        
        # Регистрируем плагины
        self.plugin_manager.register_plugin("calculator", calculator)
        
        logger.info("TaskAgent готов к работе")
    
    async def process_task(self, task: str) -> str:
        """Обработка задачи с системным промптом"""
        return await self.process_message(
            message=task,
            system_prompt=(
                "Ты - помощник для решения задач. "
                "Для любых вычислений используй инструмент calculator. "
                "Объясняй ход решения."
            )
        )

# Пример использования
async def main():
    # Создаем и инициализируем агента
    agent = TaskAgent()
    await agent.setup()
    
    try:
        # Обрабатываем задачу
        result = await agent.process_task(
            "Если у меня есть 5 яблок, и я отдам 2, сколько останется?"
        )
        print(f"Ответ: {result}")
        
    finally:
        # Очищаем ресурсы
        await agent.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
```

Этот пример демонстрирует:

1. **Инициализация**:
   - Загрузка конфигурации
   - Настройка LLM
   - Регистрация нужных плагинов

2. **Конфигурация**:
   - Отключение автозагрузки плагинов (`auto_load_plugins=False`)
   - Настройка только необходимых плагинов
   - Определение системного промпта

3. **Обработка**:
   - Метод `process_task` для удобной обработки задач
   - Использование системного промпта
   - Автоматическое использование инструментов

4. **Управление ресурсами**:
   - Корректная инициализация через `setup()`
   - Освобождение ресурсов через `cleanup()`
   - Использование контекстного менеджера `try/finally`

Агент будет:
- Использовать калькулятор для вычислений
- Объяснять ход решения
- Корректно обрабатывать ошибки
- Освобождать ресурсы при завершении

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/cognistruct.git
cd cognistruct
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Настройте конфигурацию:
```bash
python setup_config.py
```
Скрипт проведет вас через процесс настройки и создаст файл `config.json` с необходимыми параметрами.

## Использование

### Примеры

В директории `examples` находятся готовые примеры использования фреймворка:

#### 🤖 Простой консольный агент (`example_simple_agent.py`)
```bash
python examples/example_simple_agent.py
```
Демонстрирует:
- Базовую работу с агентом
- Использование калькулятора и планировщика
- Консольный интерфейс

#### 📱 Telegram бот (`example_telegram_agent.py`)
```bash
python examples/example_telegram_agent.py
```
Демонстрирует:
- Интеграцию с Telegram
- Обработку сообщений
- Систему привязки чатов
- Индикацию набора текста
- Обработку ошибок

### Примеры команд

Математические вычисления:
```
👤 посчитай 2+2
🤖 Результат вычисления: 4
```

Планирование задач:
```
👤 напомни мне через 5 минут выпить кофе
🤖 Задача "coffee_reminder" запланирована на 14:35
```

## Разработка

### Создание своего агента

1. Создайте класс, наследующийся от `BaseAgent`
2. Настройте необходимые плагины
3. Определите системный промпт
4. Реализуйте свою логику обработки сообщений

```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    async def start(self):
        await super().start()
        # Дополнительная инициализация
        
    async def process_message(self, message: str, **kwargs):
        # Своя логика обработки
        return await super().process_message(message, **kwargs)
```

### Создание нового плагина

1. Создайте директорию плагина в `plugins/`
2. Создайте класс плагина, наследующийся от `BasePlugin`
3. Реализуйте необходимые методы:
   - `setup()` - инициализация плагина
   - `cleanup()` - очистка ресурсов
   - `get_tools()` - список доступных инструментов
   - `execute_tool()` - выполнение инструмента
   - `rag_hook()` - (опционально) контекстный поиск
   - `input_hook()` - (опционально) обработка входящих сообщений
   - `output_hook()` - (опционально) обработка исходящих сообщений

Пример структуры плагина:
```python
from plugins.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    name = "my_plugin"
    priority = 0
    
    async def setup(self):
        # Инициализация
        pass
        
    def get_tools(self):
        return [
            ToolSchema(
                name="my_tool",
                description="Описание инструмента",
                parameters={...}
            )
        ]
        
    async def input_hook(self, message: IOMessage) -> bool:
        # Обработка входящих сообщений
        return False
        
    async def output_hook(self, message: IOMessage):
        # Обработка исходящих сообщений
        pass
```

### Логирование

В проекте настроено многоуровневое логирование:
- Общее логирование через `init_logging()`
- Логирование по модулям через `setup_logger(__name__)`
- Логи сохраняются в файлы и выводятся в консоль

### 🚀 Следующие шаги

### 🗄️ Работа с памятью

Реализация плагинов для работы с разными типами памяти:
- `ShortTermMemory` - кратковременная память на основе SQLite
  ```python
  # Пример использования
  memory = ShortTermMemory(retention_period="1h")
  await memory.add("user_preference", "likes_coffee")
  recent = await memory.get_recent(limit=10)
  ```
  
- `LongTermMemory` - долговременная память с векторным поиском
  ```python
  # Пример использования
  memory = LongTermMemory(embeddings_provider="sentence-transformers")
  await memory.store("Пользователь любит пить кофе в 15:00")
  context = await memory.search("когда пользователь пьет кофе?")
  ```

### 🖥️ Абстракции интерфейсов

Создание базовых классов для разных типов интерфейсов:
- `BaseInterface` - общий интерфейс для всех реализаций
- `ConsoleInterface` - работа через командную строку
- `WebAPI` - REST API на FastAPI
- `WebSocket` - поддержка WebSocket соединений

### 🤖 Streaming поддержка

Добавление потоковой обработки:
- Streaming ответов от LLM
- Прогресс выполнения инструментов
- WebSocket обновления
- Server-Sent Events

## Лицензия

MIT 