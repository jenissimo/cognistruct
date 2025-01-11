# CogniStruct

Модульный фреймворк для создания AI-ассистентов с поддержкой плагинов.

## Особенности

- 🔌 Модульная архитектура на основе плагинов
- 🧠 Поддержка различных LLM (OpenAI, DeepSeek, Ollama)
- 🛠� Поддержка потокового вывода (streaming)
- 🛠 Система инструментов для расширения возможностей
- 💾 Краткосрочная и долгосрочная память
- 📅 Планировщик задач
- 📱 Интеграция с Telegram
- 🎨 Поддержка Markdown в консоли
- 🌐 REST API с автодокументацией

## Установка

1. Клонируем репозиторий:
```bash
git clone https://github.com/your-username/cognistruct.git
cd cognistruct
```

2. Создаем и активируем виртуальное окружение:
```bash
# Создаем виртуальное окружение
python -m venv venv

# Активируем его:
# - для Linux/macOS:
source venv/bin/activate
# - для Windows:
# venv\Scripts\activate
```

3. Устанавливаем зависимости:
```bash
pip install -r requirements.txt
```

## Быстрый старт

1. Настройте API ключи и токены через интерактивный помощник:
```bash
python setup_config.py
```
Помощник попросит ввести (все поля опциональны):
- DeepSeek API ключ (для использования DeepSeek LLM)
- Telegram токен (для запуска Telegram бота)
- Креденшлы для REST API (для защиты API endpoints)

Конфигурация сохраняется в файл `~/.cognistruct/config` и может быть перезаписана через переменные окружения:
```bash
# Приоритет конфигурации:
# 1. Переменные окружения (если заданы)
# 2. Файл ~/.cognistruct/config (если существует)
export DEEPSEEK_API_KEY=your_api_key
export TELEGRAM_BOT_TOKEN=your_bot_token
```

2. Запустите один из примеров:
```bash
# Консольный агент с Ollama (локальный):
python examples/example_simple_agent.py

# Консольный агент с DeepSeek:
python examples/example_simple_agent.py  # Используется ключ из конфига

# Telegram бот
python examples/example_telegram_agent.py  # Используется токен из конфига

# REST API сервер
python examples/example_rest_agent.py
```

Вы также можете настроить конфигурацию LLM прямо в файлах примеров или через переменные окружения. Например, в `example_simple_agent.py`:

```python
# Конфигурация LLM (выберите один вариант)
LLM_CONFIG = {
    # Для Ollama (локальный):
    "provider": "ollama",
    "model": "qwen2.5",
    "api_key": "ollama",
    
    # Для DeepSeek:
    #"provider": "deepseek",
    #"model": "deepseek-chat",
    #"api_key": Config.load().deepseek_api_key,  # Загружаем из конфига
    "temperature": 0.5
}
```

## Плагины

### RESTApiPlugin
REST API с автоматической генерацией CRUDS эндпоинтов и Swagger/ReDoc документацией.

```python
rest_api = RESTApiPlugin(
    port=8000,                    # Порт сервера
    enable_auth=True,             # Включить JWT авторизацию
    admin_username="admin",       # Имя пользователя для API
    admin_password="secret",      # Пароль для API
    allowed_origins=["*"]         # CORS настройки
)

# Автоматически создаются эндпоинты:
# - POST   /auth/token           # Получение JWT токена
# - POST   /chat                 # Чат с агентом
# - POST   /api/{plugin}         # Создание ресурса
# - GET    /api/{plugin}/{id}    # Чтение ресурса
# - PUT    /api/{plugin}/{id}    # Обновление ресурса
# - DELETE /api/{plugin}/{id}    # Удаление ресурса
# - POST   /api/{plugin}/search  # Поиск ресурсов
```

Особенности:
- 🔐 JWT авторизация
- 📚 Swagger UI и ReDoc документация
- 🔄 Автоматическая генерация CRUDS API
- 💬 Чат с агентом через API
- 🌍 CORS поддержка
- 📝 Подробные описания и примеры

### InternetPlugin
Поиск и извлечение информации из интернета.

```python
internet = InternetPlugin(
    max_search_results=5,     # Максимум результатов поиска
    min_word_count=20,        # Минимум слов в блоке текста
)

# Поиск информации
results = await internet.execute_tool("search", {
    "query": "Python async programming"
})
# -> Список результатов с заголовками и ссылками

# Извлечение контента
content = await internet.execute_tool("crawl", {
    "url": "https://example.com/article"
})
# -> Markdown контент со ссылками и медиа
```

Особенности:
- 🔍 Поиск через DuckDuckGo
- 📝 Извлечение контента в Markdown
- 🔗 Сохранение внутренних и внешних ссылок
- 🖼️ Извлечение медиа-контента
- 🤖 Поддержка JavaScript и iframe
- 🚫 Автоматическое удаление попапов
- 💾 Управление кэшированием

### LongTermMemoryPlugin
Долгосрочная память с умным поиском по контексту и тегам.

```python
memory = LongTermMemoryPlugin(
    max_context_memories=5,     # Максимум фактов в контексте
    recency_weight=0.3,        # Вес недавних обращений (0-1)
    db_path="memory.db"        # Путь к базе данных
)

# Сохранение факта
await memory.execute_tool("remember", {
    "fact": "Пользователь предпочитает краткие ответы",
    "tags": ["preferences", "communication"]
})

# Поиск фактов
results = await memory.execute_tool("recall", {
    "query": "предпочтения пользователя"
})
```

Особенности:
- 🧠 Умный поиск с TF-IDF и косинусным сходством
- 🏷 Поддержка тегов для категоризации
- ⏱ Учет времени последнего доступа
- 🤖 Автоматическое добавление контекста через RAG
- 📊 Ранжирование по релевантности и свежести

### VersionedStoragePlugin
Хранилище версионированных артефактов с умным поиском и автоматическим версионированием.

```python
storage = VersionedStoragePlugin(
    version_weight=0.3,  # Вес версии при ранжировании
    time_weight=0.2      # Вес времени создания
)

# Создание артефакта с тегами
note_id = storage.generate_id("note", "Моя первая заметка")
await storage.create({
    "key": note_id,
    "value": {"text": "Важная информация о проекте"},
    "metadata": {
        "tags": ["important", "project"],
        "author": "user"
    }
})

# Обновление (автоматически создает новую версию)
await storage.update(note_id, {
    "value": {"text": "Обновленная информация о проекте"},
    "metadata": {
        "tags": ["important", "project", "updated"],
        "edited_by": "ai"
    }
})

# Умный поиск с ранжированием
notes = await storage.search({
    "text_query": "информация о проекте",  # Поиск по содержимому
    "tags": ["important"],                 # Фильтрация по тегам
    "latest_only": True                    # Только последние версии
})

# Иерархические ID для структурированного контента
chapter_id = storage.generate_hierarchical_id("story", "chapter1", "scene2")
# -> "story/chapter1/scene2"
```

Особенности:
- 🧠 Умный поиск с TF-IDF и косинусным сходством
- 📝 Автоматическое версионирование при обновлении
- 🏷 Поддержка тегов и метаданных
- 📊 Ранжирование по релевантности, версии и времени
- 📂 Иерархические ID (например, "story/chapter1/scene2")
- 🔄 Асинхронные операции через asyncio
- 🔒 Надежное хранение в SQLite

### ConsolePlugin
Обработка консольного ввода/вывода с поддержкой Markdown и стриминга.

```python
console = ConsolePlugin(
    prompt="👤 ",                    # Строка приглашения ввода
    exit_command="exit",             # Команда для выхода
    exit_message="\n👋 До свидания!", # Сообщение при выходе
    use_markdown=True,               # Включить форматирование Markdown
    use_emojis=True,                 # Использовать эмодзи
    refresh_rate=10                  # Частота обновления стриминга (кадров в секунду)
)

# Регистрация обработчика сообщений с поддержкой стриминга
async def handle_message(message: IOMessage):
    await agent.process_message(
        message.content,
        stream=True  # Включаем стриминг
    )

console.set_message_handler(handle_message)
```

Особенности:
- 🌊 Потоковый вывод ответов в реальном времени
- 🎨 Поддержка Markdown с живым обновлением
- 🔧 Отображение вызовов инструментов в процессе генерации
- ✨ Красивое форматирование с эмодзи
- 🖥️ Интерактивный консольный интерфейс

### ShortTermMemory
Хранит контекст последних сообщений для поддержания связного диалога.

```python
memory = ShortTermMemoryPlugin(
    max_messages=15  # Количество хранимых сообщений (примерно 7-8 обменов репликами)
)
```

Плагин автоматически:
- Сохраняет входящие и исходящие сообщения
- Поддерживает ограниченное количество сообщений
- Добавляет историю диалога в контекст для LLM
- Удаляет старые сообщения при добавлении новых
- Хранит сообщения в SQLite базе данных

### Calculator
Безопасное выполнение математических вычислений.

```python
calculator = CalculatorPlugin()
# Использование: "calculate 2 + 2"
```

### Scheduler
Планирование и выполнение отложенных задач.

```python
scheduler = SchedulerPlugin(
    tick_interval=1.0,
    timezone="Europe/Moscow"
)
# Использование: "schedule_task ..."
```

## Создание агента

```python
from agents import BaseAgent
from llm import LLMRouter
from plugins.console_plugin import ConsolePlugin
from plugins.example_plugin import CalculatorPlugin
from functools import partial

# Конфигурация LLM
LLM_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": "YOUR_API_KEY"
}

# Системный промпт
SYSTEM_PROMPT = """
Ты - полезный ассистент. Для ЛЮБЫХ математических вычислений используй инструмент calculate.
НИКОГДА не пытайся вычислять самостоятельно.
""".strip()

# Инициализация LLM
llm = LLMRouter().create_instance(**LLM_CONFIG)

# Создание агента (без автозагрузки плагинов)
agent = BaseAgent(llm=llm, auto_load_plugins=False)

# Создание плагинов
calculator = CalculatorPlugin()
console = ConsolePlugin(
    prompt="👤 ",
    exit_command="exit",
    exit_message="\n👋 До свидания!",
    use_markdown=True,
    use_emojis=True,
    refresh_rate=10
)

# Подключаем обработчик к консоли
console.set_message_handler(
    partial(agent.handle_message, system_prompt=SYSTEM_PROMPT, stream=True)
)

# Инициализируем плагины
await calculator.setup()
await console.setup()

# Регистрация плагинов
agent.plugin_manager.register_plugin("calculator", calculator)
agent.plugin_manager.register_plugin("console", console)

try:
    # Запуск агента и консоли
    await agent.start()
    await console.start()
except Exception as e:
    print(f"\n❌ Неожиданная ошибка: {str(e)}")
    raise
finally:
    # Очистка ресурсов
    await agent.cleanup()
```

## Разработка плагинов

Создайте новый плагин, унаследовавшись от BasePlugin:

```python
from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage

class MyPlugin(BasePlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",
            description="Описание плагина",
            version="1.0.0",
            priority=50
        )
        
    async def input_hook(self, message: IOMessage) -> bool:
        """Обработка входящих сообщений"""
        return False
        
    async def output_hook(self, message: IOMessage):
        """Обработка исходящих сообщений"""
        pass
```


## Лицензия

MIT License
