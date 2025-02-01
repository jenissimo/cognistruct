# Архитектура CogniStruct

## Основные компоненты

### 1. Система сообщений (`messages.py`)
Ядро коммуникации между компонентами системы - класс `IOMessage`:

```python
class IOMessage:
    type: str           # Тип сообщения
    content: Any        # Содержимое
    metadata: Dict      # Метаданные
    source: str         # Источник
    stream: Generator   # Стрим для асинхронных данных
    is_async: bool      # Флаг асинхронности
    tool_calls: List    # История инструментов
    context: RequestContext  # Контекст запроса
```

### 2. Система контекста (`context.py`)
Управление контекстом запросов в многопользовательской среде:

```python
@dataclass
class RequestContext:
    user_id: str        # ID пользователя
    chat_id: str        # ID чата (опционально)
    metadata: Dict      # Дополнительные данные
    timestamp: float    # Время создания
```

Ключевые особенности:
- Инкапсуляция пользовательского контекста
- Автоматическое распространение через цепочку плагинов
- Поддержка метаданных специфичных для платформы

### 3. Базовый плагин (`base_plugin.py`)
Абстрактный класс для всех плагинов системы:

```python
class BasePlugin:
    async def input_hook(message: IOMessage) -> bool
    async def output_hook(message: IOMessage) -> Optional[IOMessage]
    async def streaming_output_hook(message: IOMessage) -> AsyncGenerator[IOMessage]
```

### 4. Middleware система
Промежуточные обработчики для кросс-плагинной функциональности:

```python
class ContextMiddleware(BasePlugin):
    async def input_hook(message: IOMessage) -> bool:
        # Проверка наличия контекста
        if not message.context:
            return True  # Блокируем сообщения без контекста
```

## Поток данных

1. **Входящее сообщение**:
   ```
   User Input -> Plugin (создание контекста) -> IOMessage -> Middleware -> LLM
   ```

2. **Обработка ответа**:
   ```
   LLM Response -> IOMessage (с контекстом) -> Plugins -> User
   ```

3. **Стриминг**:
   ```
   LLM Stream -> Chunks (копирование контекста) -> Plugins -> Real-time Updates
   ```

## Управление контекстом

### 1. Создание контекста
- **Ответственность плагинов**:
  ```python
  # В Telegram плагине
  chat_link = await db.get_chat_link(chat_id)
  context = RequestContext(
      user_id=chat_link["user_id"],
      chat_id=chat_id,
      metadata={"platform": "telegram"}
  )
  message.context = context
  ```

### 2. Проверка контекста
- **Middleware**:
  ```python
  # В ContextMiddleware
  if not message.context:
      logger.warning("No context in message")
      return True  # Блокируем обработку
  ```

### 3. Распространение контекста
- **В стримах**:
  ```python
  async for chunk in message.stream:
      chunk.context = original_context
      yield chunk
  ```

## Рекомендации по реализации

1. **Плагины**:
   - Создавать контекст до отправки сообщения в цепочку
   - Использовать свои механизмы аутентификации
   - Добавлять платформо-специфичные метаданные

2. **Middleware**:
   - Проверять наличие обязательных полей контекста
   - Логировать проблемы с контекстом
   - Обеспечивать копирование контекста в стримах

3. **LLM интеграция**:
   - Передавать контекст через метаданные
   - Использовать user_id для разделения истории
   - Учитывать контекст при генерации ответов

## Примеры использования

### 1. Telegram интеграция
```python
# В обработчике сообщений
chat_link = await db.get_chat_link(chat_id)
context = RequestContext(user_id=chat_link["user_id"])
message = IOMessage(content=text).with_context(context)
```

### 2. Доступ к контексту
```python
# В любом плагине
if message.context:
    user_id = message.context.user_id
    platform_data = message.context.metadata
```

### 3. Стриминг с контекстом
```python
# В streaming_output_hook
async for chunk in message.stream:
    chunk.context = message.context
    # Обработка чанка
```

## Безопасность

1. **Изоляция пользователей**:
   - Проверка контекста в middleware
   - Валидация user_id
   - Логирование подозрительной активности

2. **Защита данных**:
   - Минимизация данных в контексте
   - Очистка чувствительной информации
   - Контроль доступа к метаданным

## Будущие улучшения

1. **Производительность**:
   - Кэширование контекста
   - Оптимизация копирования
   - Ленивая загрузка метаданных

2. **Расширяемость**:
   - Поддержка вложенных контекстов
   - Система событий контекста
   - Плагины для работы с контекстом

3. **Надежность**:
   - Восстановление контекста
   - Валидация целостности
   - Отказоустойчивость

## Диаграммы потоков

### Telegram Plugin Flow
```mermaid
sequenceDiagram
    participant User
    participant TelegramBot
    participant TelegramPlugin
    participant ContextMiddleware
    participant BaseAgent
    participant LLM
    participant OutputPlugins

    User->>TelegramBot: Отправка сообщения
    TelegramBot->>TelegramPlugin: handle_message()
    
    TelegramPlugin->>TelegramPlugin: get_chat_link()
    Note over TelegramPlugin: Проверка привязки чата
    
    TelegramPlugin->>TelegramPlugin: create_context()
    Note over TelegramPlugin: user_id + chat_id
    
    TelegramPlugin->>ContextMiddleware: input_hook(message)
    Note over ContextMiddleware: Проверка контекста
    
    ContextMiddleware->>BaseAgent: process_message()
    BaseAgent->>LLM: generate_response()
    
    alt Streaming Response
        LLM-->>OutputPlugins: stream chunks
        OutputPlugins-->>TelegramPlugin: update message
        TelegramPlugin-->>User: Обновление сообщения
    else Regular Response
        LLM->>OutputPlugins: complete message
        OutputPlugins->>TelegramPlugin: format message
        TelegramPlugin->>User: Отправка ответа
    end
```

### Console Plugin Flow
```mermaid
sequenceDiagram
    participant User
    participant ConsolePlugin
    participant ContextMiddleware
    participant BaseAgent
    participant LLM

    User->>ConsolePlugin: Ввод команды
    ConsolePlugin->>ConsolePlugin: create_context()
    Note over ConsolePlugin: default user_id
    
    ConsolePlugin->>ContextMiddleware: input_hook(message)
    ContextMiddleware->>BaseAgent: process_message()
    BaseAgent->>LLM: generate_response()
    
    alt Streaming Response
        LLM-->>ConsolePlugin: stream chunks
        ConsolePlugin-->>User: Live Updates
    else Regular Response
        LLM->>ConsolePlugin: complete message
        ConsolePlugin->>User: Print Response
    end
```

### REST API Flow
```mermaid
sequenceDiagram
    participant Client
    participant APIPlugin
    participant AuthMiddleware
    participant ContextMiddleware
    participant BaseAgent
    participant LLM

    Client->>APIPlugin: POST /api/chat
    APIPlugin->>AuthMiddleware: validate_token()
    Note over AuthMiddleware: JWT validation
    
    AuthMiddleware->>APIPlugin: user_data
    APIPlugin->>APIPlugin: create_context()
    Note over APIPlugin: user_id from JWT
    
    APIPlugin->>ContextMiddleware: input_hook(message)
    ContextMiddleware->>BaseAgent: process_message()
    BaseAgent->>LLM: generate_response()
    
    alt Streaming Response
        LLM-->>Client: SSE Stream
    else Regular Response
        LLM->>Client: JSON Response
    end
```

### Scheduler Plugin Flow
```mermaid
sequenceDiagram
    participant Scheduler
    participant SchedulerPlugin
    participant ContextMiddleware
    participant BaseAgent
    participant LLM
    participant OutputPlugins

    Scheduler->>SchedulerPlugin: trigger_task()
    Note over SchedulerPlugin: Task with user_id
    
    SchedulerPlugin->>SchedulerPlugin: create_context()
    Note over SchedulerPlugin: Restore user context
    
    SchedulerPlugin->>ContextMiddleware: input_hook(message)
    ContextMiddleware->>BaseAgent: process_message()
    BaseAgent->>LLM: generate_response()
    
    LLM->>OutputPlugins: response
    
    par Multiple Outputs
        OutputPlugins->>TelegramPlugin: send_message()
        OutputPlugins->>EmailPlugin: send_email()
        OutputPlugins->>WebhookPlugin: post_webhook()
    end
```

### Message Lifecycle Flow
```mermaid
flowchart TB
    subgraph Input
        A[User Input] --> B[Input Plugin]
        B --> C{Has Context?}
        C -->|No| D[Create Context]
        C -->|Yes| E[Validate Context]
        D --> E
        E --> F[input_hook]
    end

    subgraph Memory
        F --> G[Memory Plugin]
        G --> H[Load History]
        G --> I[Load RAG Context]
        H --> J[Enrich Message]
        I --> J
    end

    subgraph Processing
        J --> K[BaseAgent]
        K --> L[LLM Service]
        L --> M{Is Streaming?}
    end

    subgraph Output
        M -->|Yes| N[Stream Chunks]
        M -->|No| O[Complete Message]
        N --> P[streaming_output_hook]
        O --> Q[output_hook]
        P --> R[Update UI]
        Q --> S[Send Response]
    end

    subgraph Storage
        R --> T[Save to History]
        S --> T
        T --> U[Update Embeddings]
    end
```

### Memory Integration Flow
```mermaid
sequenceDiagram
    participant User
    participant Plugin
    participant MemoryPlugin
    participant VectorDB
    participant RAG
    participant LLM
    participant History

    User->>Plugin: Сообщение
    Plugin->>MemoryPlugin: pre_process_hook()
    
    par Memory Loading
        MemoryPlugin->>History: load_chat_history()
        MemoryPlugin->>VectorDB: semantic_search()
        VectorDB->>RAG: get_relevant_chunks()
    end

    MemoryPlugin->>MemoryPlugin: enrich_message()
    Note over MemoryPlugin: Добавление контекста
    
    MemoryPlugin->>LLM: process_message()
    
    LLM->>Plugin: response
    
    par Memory Update
        Plugin->>History: save_interaction()
        Plugin->>VectorDB: update_embeddings()
    end
    
    Plugin->>User: Ответ
```

### Hook Execution Flow
```mermaid
stateDiagram-v2
    [*] --> InputMessage
    
    state "Input Processing" as IP {
        InputMessage --> PreProcess
        PreProcess --> InputHook
        InputHook --> MemoryHook
        MemoryHook --> ValidationHook
    }
    
    state "LLM Processing" as LP {
        ValidationHook --> LLMPreProcess
        LLMPreProcess --> LLMCall
        LLMCall --> LLMPostProcess
    }
    
    state "Output Processing" as OP {
        LLMPostProcess --> StreamingHook
        StreamingHook --> OutputHook
        OutputHook --> PostProcess
    }
    
    PostProcess --> [*]

    note right of IP
        - Контекст
        - Валидация
        - Память
    end note

    note right of LP
        - Промпты
        - Tool calls
        - Streaming
    end note

    note right of OP
        - Форматирование
        - Сохранение
        - Отправка
    end note
```

### RAG Integration Flow
```mermaid
sequenceDiagram
    participant User
    participant Plugin
    participant RAGPlugin
    participant Chunker
    participant Embedder
    participant VectorDB
    participant LLM

    User->>Plugin: Запрос
    Plugin->>RAGPlugin: pre_process()
    
    RAGPlugin->>VectorDB: search_similar()
    
    par Document Processing
        VectorDB->>Chunker: chunk_documents()
        Chunker->>Embedder: create_embeddings()
        Embedder->>VectorDB: store_vectors()
    end
    
    VectorDB-->>RAGPlugin: relevant_chunks
    
    RAGPlugin->>RAGPlugin: format_context()
    Note over RAGPlugin: Сборка промпта
    
    RAGPlugin->>LLM: enhanced_query
    LLM-->>Plugin: response
    
    Plugin->>User: Ответ с контекстом
```

## Жизненный цикл сообщения

### 1. Входная обработка
- Создание/валидация контекста
- Загрузка истории чата
- Поиск релевантного контекста (RAG)
- Обогащение сообщения метаданными

### 2. Обработка LLM
- Подготовка промпта
- Вызов инструментов
- Стриминг ответа
- Обработка ошибок

### 3. Выходная обработка
- Форматирование ответа
- Сохранение в историю
- Обновление эмбеддингов
- Отправка пользователю

## Интеграция с памятью

### 1. Типы памяти
- Краткосрочная (текущая сессия)
- Долгосрочная (векторная БД)
- Семантическая (RAG)
- Эпизодическая (история чата)

### 2. Механизмы обновления
- Автоматическое сохранение диалогов
- Периодическое обновление эмбеддингов
- Прунинг устаревших данных
- Индексация новых документов

### 3. Контекстное обогащение
- Релевантные чанки документов
- История взаимодействий
- Пользовательские предпочтения
- Системные метаданные

## Проблемные точки

1. **Контекст в стримах**:
   - Каждый чанк копирует весь контекст
   - Возможна оптимизация через ссылки

2. **Множественные выходы**:
   - Планировщик может отправлять в несколько каналов
   - Нужна синхронизация контекста между каналами

3. **Восстановление контекста**:
   - При перезапуске планировщика
   - При повторных попытках отправки

4. **Валидация контекста**:
   - Разные плагины требуют разные поля
   - Нужна гибкая система валидации

## Предложения по улучшению

1. **Оптимизация памяти**:
   ```python
   class StreamContext:
       """Легковесный контекст для стримов"""
       __slots__ = ['user_id', 'chat_id']
   ```

2. **Система событий**:
   ```python
   @context_event('user_authenticated')
   async def handle_auth(context: RequestContext):
       # Дополнительная обработка после аутентификации
   ```

3. **Валидация контекста**:
   ```python
   class TelegramContext(RequestContext):
       chat_id: str  # Обязательное поле для Telegram
       platform: str = 'telegram'  # Автоматически
   ```

[остальной контент остается без изменений...] 