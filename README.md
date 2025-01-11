# CogniStruct

Модульный фреймворк для создания AI-ассистентов с поддержкой плагинов.

---

## Особенности

- 🔌 **Модульная архитектура:** плагины расширяют базовые возможности фреймворка.
- 🧠 **Поддержка различных LLM:** интеграция с OpenAI, DeepSeek, Ollama.
- 🛠 **Потоковый вывод (streaming):** отображение ответов в режиме реального времени.
- 🛠 **Инструменты:** система для расширения функционала через дополнительные утилиты.
- 💾 **Память:** краткосрочная и долгосрочная для хранения контекста.
- 📅 **Планировщик:** система для отложенного выполнения задач.
- 📱 **Telegram интеграция:** запуск и настройка бота.
- 🎨 **Markdown:** поддержка форматированного вывода в консоли.
- 🌐 **REST API:** с автодокументацией (Swagger/ReDoc).

---

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/jenissimo/cognistruct.git
cd cognistruct
```

### 2. Создание и активация виртуального окружения

```bash
# Создание виртуального окружения
python -m venv venv

# Активация:
# Для Linux/macOS:
source venv/bin/activate
# Для Windows:
# venv\Scripts\activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

---

## Быстрый старт

### Настройка конфигурации

Запустите интерактивного помощника для настройки API ключей и токенов:

```bash
python setup_config.py
```

Помощник предложит ввести следующие параметры (все поля опциональны):

- **DeepSeek API ключ**
- **Telegram токен**
- **Креденшлы для REST API**

Конфигурация сохраняется в `~/.cognistruct/config` и может быть переопределена переменными окружения:

```bash
export DEEPSEEK_API_KEY=your_api_key
export TELEGRAM_BOT_TOKEN=your_bot_token
```

### Запуск примеров

Запустите один из примеров для проверки работы:

```bash
# Консольный агент (например, с Ollama):
python examples/example_simple_agent.py

# Агент с использованием DeepSeek:
python examples/example_simple_agent.py  # Ключ загружается из конфигурации

# Telegram бот:
python examples/example_telegram_agent.py  # Используется токен из конфигурации

# REST API сервер:
python examples/example_rest_agent.py
```

Также можно настроить конфигурацию LLM непосредственно в файлах примеров или через переменные окружения:

```python
LLM_CONFIG = {
    # Пример конфигурации для Ollama (локально):
    "provider": "ollama",
    "model": "qwen2.5",
    "api_key": "ollama",
    
    # Пример для DeepSeek:
    # "provider": "deepseek",
    # "model": "deepseek-chat",
    # "api_key": Config.load().deepseek_api_key,
    "temperature": 0.5
}
```

---

## Описание плагинов

### RESTApiPlugin

Обеспечивает автоматическую генерацию CRUDS эндпоинтов с документацией Swagger/ReDoc и JWT авторизацией.

```python
rest_api = RESTApiPlugin(
    port=8000,                    # Порт сервера
    enable_auth=True,             # Включить JWT авторизацию
    admin_username="admin",       # Имя пользователя
    admin_password="secret",      # Пароль
    allowed_origins=["*"]         # Настройки CORS
)
```

**Эндпоинты:**

- `POST /auth/token` – получение JWT
- `POST /chat` – чат с агентом
- CRUD операции для плагинов:
  - `POST /api/{plugin}`
  - `GET /api/{plugin}/{id}`
  - `PUT /api/{plugin}/{id}`
  - `DELETE /api/{plugin}/{id}`
  - `POST /api/{plugin}/search` – поиск ресурсов

---

### InternetPlugin

Позволяет выполнять поиск в интернете и извлекать контент.

```python
internet = InternetPlugin(
    max_search_results=5,     # Максимальное число результатов поиска
    min_word_count=20         # Минимальное количество слов на блок текста
)

results = await internet.execute_tool("search", {
    "query": "Python async programming"
})
content = await internet.execute_tool("crawl", {
    "url": "https://example.com/article"
})
```

**Особенности:**

- 🔍 Поиск через DuckDuckGo.
- 📝 Извлечение текста в формате Markdown.
- 🔗 Сохранение ссылок и медиа.
- 🚫 Удаление popup-ов и лишних элементов.

---

### LongTermMemoryPlugin

Плагин для хранения долговременной памяти с тегированием и умным поиском.

```python
memory = LongTermMemoryPlugin(
    max_context_memories=5,     # Максимальное число фактов в контексте
    recency_weight=0.3,         # Вес недавнего доступа (0-1)
    db_path="memory.db"
)

await memory.execute_tool("remember", {
    "fact": "Пользователь предпочитает краткие ответы",
    "tags": ["preferences", "communication"]
})

results = await memory.execute_tool("recall", {
    "query": "предпочтения пользователя"
})
```

**Особенности:**

- TF-IDF и косинусное сходство для релевантного поиска.
- Тегирование для категоризации фактов.
- Автоматическое добавление контекста через RAG.
- Ранжирование по времени обращения.

---

### VersionedStoragePlugin

Хранилище версионированных артефактов с умным поиском и автоматическим версионированием.

```python
storage = VersionedStoragePlugin(
    version_weight=0.3,  # Вес версии при ранжировании
    time_weight=0.2      # Вес времени создания
)

note_id = storage.generate_id("note", "Моя первая заметка")
await storage.create({
    "key": note_id,
    "value": {"text": "Важная информация о проекте"},
    "metadata": {
        "tags": ["important", "project"],
        "author": "user"
    }
})
```

Обновление автоматически создаёт новую версию. Также поддерживается иерархическая генерация ID:

```python
chapter_id = storage.generate_hierarchical_id("story", "chapter1", "scene2")
# -> "story/chapter1/scene2"
```

**Особенности:**

- TF-IDF и косинусное сходство для поиска.
- Автоматическое версионирование при изменениях.
- Поддержка тегов и метаданных.
- Ранжирование по релевантности.

---

### ConsolePlugin

Плагин для организации консольного ввода/вывода с поддержкой Markdown и стриминга.

```python
console = ConsolePlugin(
    prompt="👤 ",                    # Приглашение к вводу
    exit_command="exit",             # Команда для выхода
    exit_message="\n👋 До свидания!",# Прощальное сообщение
    use_markdown=True,               # Включение Markdown
    use_emojis=True,                 # Эмодзи в выводе
    refresh_rate=10                  # Частота обновления (FPS)
)

async def handle_message(message: IOMessage):
    await agent.process_message(
        message.content,
        stream=True  # Включён стриминг
    )

console.set_message_handler(handle_message)
```

**Особенности:**

- Реальное время стриминга ответов.
- Поддержка форматирования Markdown.
- Визуально приятный интерфейс с эмодзи.

---

### ShortTermMemory

Плагин для хранения последнего контекста диалога, поддерживающий ограниченное число сообщений.

```python
memory = ShortTermMemoryPlugin(
    max_messages=15  # Около 7-8 обменов репликами
)
```

**Особенности:**

- Автоматическое добавление новых сообщений в контекст.
- Удаление старых сообщений по мере достижения лимита.
- Хранение данных в SQLite.

---

### CalculatorPlugin

Плагин для безопасного выполнения математических вычислений.

```python
calculator = CalculatorPlugin()
# Использование: "calculate 2 + 2"
```

---

### SchedulerPlugin

Позволяет планировать и выполнять отложенные задачи.

```python
scheduler = SchedulerPlugin(
    tick_interval=1.0,     # Интервал обновления
    timezone="Europe/Moscow"
)
# Пример: "schedule_task ..."
```

---

## Создание агента

Пример создания агента и подключения плагинов:

```python
from core import BaseAgent
from llm import LLMRouter
from plugins.io.console import ConsolePlugin
from plugins.tools.calculate import CalculatorPlugin
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

# Инициализация плагинов
calculator = CalculatorPlugin()
console = ConsolePlugin(
    prompt="👤 ",
    exit_command="exit",
    exit_message="\n👋 До свидания!",
    use_markdown=True,
    use_emojis=True,
    refresh_rate=10
)

# Подключение обработчика консоли
console.set_message_handler(
    partial(agent.handle_message, system_prompt=SYSTEM_PROMPT, stream=True)
)

# Асинхронная инициализация плагинов
await calculator.setup()
await console.setup()

# Регистрация плагинов в агенте
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

---

## Разработка плагинов

Чтобы создать новый плагин, унаследуйтесь от `BasePlugin`:

```python
from core.base_plugin import BasePlugin, PluginMetadata, IOMessage

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
        # Возвращайте True, если обработка завершена плагином
        return False
        
    async def output_hook(self, message: IOMessage):
        """Обработка исходящих сообщений"""
        pass
```

---

## Лицензия

Проект распространяется под лицензией [MIT License](LICENSE).

---