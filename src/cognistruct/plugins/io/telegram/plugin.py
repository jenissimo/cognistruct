import asyncio
from typing import Optional, Dict, Any, List, AsyncGenerator
import json
from datetime import datetime
import logging
import time
import os
import telegramify_markdown
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from cognistruct.core import BasePlugin, IOMessage, PluginMetadata
from cognistruct.llm.interfaces import StreamChunk
from .bot import TelegramBot
from .database import TelegramDatabase
from .handlers import TelegramHandlers
from .utils import format_message, send_content_box

# Настраиваем логирование
logging.getLogger("httpx").setLevel(logging.WARNING)
telegramify_logger = logging.getLogger("telegramify_markdown")
telegramify_logger.setLevel(logging.INFO)
telegramify_logger.warn = telegramify_logger.warning  # Добавляем алиас для warn

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Устанавливаем уровень DEBUG для плагина

class TelegramPlugin(BasePlugin):
    """Telegram плагин для CogniStruct"""
    
    def __init__(self, telegram_user_id: str = None):
        super().__init__()
        self.bot = None
        self.db = None
        self.handlers = None
        self._current_chat_id = None  # Текущий чат для обработки
        self.telegram_user_id = telegram_user_id  # ID пользователя для привязки
        self._chat_linked_callbacks = []  # Коллбэки для привязки чата
        logger.info("🚀 TelegramPlugin initialized")
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="telegram",
            description="Telegram интеграция",
            version="1.0.0",
            priority=10
        )
        
    def set_message_handler(self, handler):
        """Устанавливает обработчик сообщений"""
        if self.handlers:
            self.handlers.message_handler = handler
        else:
            raise RuntimeError("TelegramPlugin not initialized. Call setup() first")
        
    async def setup(self, token: str = None):
        """
        Инициализация плагина
        
        Args:
            token: Telegram Bot токен. Если не указан, берется из TELEGRAM_BOT_TOKEN
            
        Returns:
            dict: Результат инициализации с информацией о статусе чата
        """
        # Регистрируем типы сообщений
        self.register_input_type("telegram_message")
        self.register_output_type("message")
        self.register_output_type("action")
        self.register_output_type("confirmation_request")
        self.register_output_type("interactive_message")
        
        # Получаем токен
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("Telegram token not provided")
            
        # Инициализируем компоненты
        self.db = TelegramDatabase()
        await self.db.connect()
        
        self.bot = TelegramBot(self.token)
        self.handlers = TelegramHandlers(self.db, self.bot, self)
        
        # Регистрируем обработчики
        self.bot.add_handler(CommandHandler("start", self.handlers.handle_start))
        self.bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_message))
        self.bot.add_handler(CallbackQueryHandler(self.handlers.handle_callback_query))
        
        # Инициализируем и запускаем бота
        await self.bot.start()
        await self.bot.start_polling()
        
        result = {"status": "initialized"}
        
        # Если задан user_id, проверяем/создаем привязку чата
        if self.telegram_user_id:
            chat_id = await self.check_chat_link(self.telegram_user_id)
            if chat_id:
                logger.info(f"Found existing chat link: {chat_id}")
                self._current_chat_id = chat_id
                result.update({
                    "chat_status": "linked",
                    "chat_id": chat_id
                })
            else:
                key = await self.generate_key(self.telegram_user_id)
                logger.info(f"Generated new key for user {self.telegram_user_id}: {key}")
                result.update({
                    "chat_status": "not_linked",
                    "key": key
                })
        
        logger.info("Telegram bot initialized and polling started")
        return result
        
    async def setup_minimal(self, token: str = None):
        # Инициализируем компоненты
        self.db = TelegramDatabase()
        await self.db.connect()


    async def cleanup(self):
        """Очистка ресурсов"""
        if self.bot:
            await self.bot.stop()
        if self.db:
            await self.db.close()
        
    async def input_hook(self, message: IOMessage) -> bool:
        """
        Проверяет привязку чата.
        
        Returns:
            True - пропустить сообщение дальше
            False - заблокировать сообщение
        """
        logger.debug(f"Input hook received message: {message}")
        
        # Проверяем, что сообщение от Telegram
        if message.source == "telegram":
            chat_id = message.metadata.get("chat_id")
            if not chat_id:
                logger.warning("No chat_id in message metadata")
                return False  # Блокируем сообщение без chat_id
                
            logger.debug(f"Checking chat link for chat_id: {chat_id}")
            chat_link = await self.db.get_chat_link(chat_id)
            
            if not chat_link:
                logger.warning(f"Chat {chat_id} not linked to any user")
                await self.bot.send_message(
                    chat_id,
                    "Чат не привязан. Используйте /start с секретным ключом"
                )
                return False  # Блокируем сообщение если чат не привязан
                
            # Сохраняем chat_id для текущего запроса
            logger.debug(f"Chat {chat_id} is linked to user {chat_link['user_id']}")
            self._current_chat_id = chat_id
            return True  # Пропускаем сообщение если чат привязан
            
        logger.debug("Message is not from Telegram, passing through")
        return True  # Пропускаем не-Telegram сообщения
        
    async def output_hook(self, message: IOMessage) -> Optional[IOMessage]:
        """Обработка исходящих сообщений"""
        logger.info("🔄 Начинаю обработку исходящего сообщения")

        # Пытаемся получить chat_id разными способами
        chat_id = (
            message.metadata.get("chat_id") or  # из метаданных сообщения
            (message.context.metadata.get("chat_id") if message.context else None) or  # из контекста
            self._current_chat_id or  # из текущего контекста плагина
            (  # или пробуем получить по user_id
                await self.get_chat_id(str(message.context.user_id if message.context else message.metadata.get("user_id")))
                if message.context or "user_id" in message.metadata
                else None
            )
        )
        
        if not chat_id:
            logger.warning("❌ Не удалось определить chat_id")
            return message
            
        logger.debug(f"Используем chat_id: {chat_id} для сообщения: {message}")
        
        try:
            content = ""
            
            # Обрабатываем tool_calls если есть
            tool_calls = message.get_tool_calls()
            if tool_calls:
                logger.debug(f"Обрабатываю tool_calls: {tool_calls}")
                for tool_call in tool_calls:
                    # Создаем сообщение для вызова инструмента
                    if "call" in tool_call:
                        tool_msg = IOMessage(
                            type="tool_call",
                            content=f"\n🔧 Использую инструмент: {tool_call['call']['function']['name']}\n",
                            metadata={"chat_id": chat_id},
                            context=message.context  # Передаем контекст
                        )
                        content += tool_msg.content
                        
                    # Создаем сообщение для результата
                    if "result" in tool_call:
                        result_msg = IOMessage(
                            type="tool_result",
                            content=f"✅ Результат: {tool_call['result']['content']}\n",
                            metadata={"chat_id": chat_id},
                            context=message.context  # Передаем контекст
                        )
                        content += result_msg.content
            
            # Добавляем основной контент сообщения
            if message.content is not None:
                content += str(message.content)
                logger.debug(f"Добавлен контент: {content}")

            # Если контент пустой, используем плейсхолдер
            if not content.strip():
                logger.warning("Пустой контент сообщения, использую плейсхолдер")
                content = "..."

            # Проверяем тип сообщения
            if message.type == "interactive_message" and "options" in message.metadata:
                logger.debug("Отправляю интерактивное сообщение с кнопками")
                # Формируем кнопки для интерактивного сообщения
                buttons = [
                    {
                        "text": option,
                        "callback_data": message.metadata.get("callback_data", [])[i] if message.metadata.get("callback_data") else f"option_{i}"
                    }
                    for i, option in enumerate(message.metadata["options"])
                ]
                await self.send_buttons(chat_id, content, buttons)
            else:
                # Отправляем обычное сообщение
                logger.debug("Отправляю обычное сообщение")
                boxes = await format_message(content)
                for item in boxes:
                    await send_content_box(self.bot, chat_id, item)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке сообщения: {e}", exc_info=True)
            # В случае ошибки пробуем отправить без форматирования
            await self.bot.send_message(
                chat_id=chat_id,
                text=content if content.strip() else "..."  # Используем плейсхолдер если контент пустой
            )
                    
        logger.info("✅ Сообщение успешно обработано и отправлено")
        return message

    async def streaming_output_hook(self, message: IOMessage) -> AsyncGenerator[IOMessage, None]:
        """Обработка стриминга для Telegram.
        
        Показывает индикатор набора пока идет генерация.
        Само сообщение будет отправлено через output_hook.
        """
        logger.info("🔄 Начинаю обработку стрима в Telegram")
        
        if not message.stream:
            logger.warning("❌ Нет стрима в сообщении")
            yield message
            return
            
        # Пытаемся получить chat_id разными способами
        chat_id = (
            message.metadata.get("chat_id") or  # из метаданных сообщения
            (message.context.metadata.get("chat_id") if message.context else None) or  # из контекста
            self._current_chat_id  # из текущего контекста плагина
        )
        
        if not chat_id:
            logger.warning("❌ Не удалось определить chat_id для стрима")
            async for chunk in message.stream:
                yield chunk
            return
            
        try:
            # Показываем индикатор набора
            typing_task = asyncio.create_task(
                self._show_typing_indicator(chat_id)
            )
            logger.debug(f"🎯 Запущен индикатор набора для chat_id: {chat_id}")
            
            # Инициализируем состояние стрима
            current_content = ""
            tool_calls = []
            
            # Обрабатываем стрим
            async for chunk in message.stream:
                logger.debug(f"📝 Получен чанк: {chunk.content[:50]}...")
                
                # Копируем контекст в чанк если его нет
                if message.context and not chunk.context:
                    chunk.context = message.context
                    
                # Добавляем chat_id в метаданные чанка
                if "chat_id" not in chunk.metadata:
                    chunk.metadata["chat_id"] = chat_id
                    
                # Накапливаем контент
                if chunk.metadata.get("delta"):
                    current_content += chunk.metadata["delta"]
                    
                # Собираем tool_calls
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)
                                        
                yield chunk
                
            # Создаем финальное сообщение
            final_message = IOMessage(
                type="text",
                content=current_content,
                metadata={"chat_id": chat_id},
                source="agent",
                context=message.context,
                tool_calls=tool_calls
            )
            # Отправляем через output_hook
            if len(current_content) > 0 or len(tool_calls) > 0:
                await self.output_hook(final_message)

            # Отменяем индикатор набора
            typing_task.cancel()
            logger.debug("✅ Стрим завершен, индикатор набора отключен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке стрима: {e}", exc_info=True)
            # Отменяем индикатор набора в случае ошибки
            if 'typing_task' in locals():
                typing_task.cancel()
            raise
        
    async def check_chat_link(self, user_id: str) -> Optional[str]:
        """
        Проверяет привязку чата к пользователю
        
        Args:
            user_id: ID пользователя
            
        Returns:
            str: ID чата, если найден
            None: если чат не найден
        """
        chat_data = await self.db.get_chat_by_user(user_id)
        if chat_data:
            return chat_data["chat_id"]
        return None
        
    async def get_all_chat_links(self, user_id: str) -> list[str]:
        """
        Получает все чаты пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            list[str]: Список ID чатов
        """
        chats = await self.db.get_all_chats_by_user(user_id)
        return [chat["chat_id"] for chat in chats] 
        
    async def generate_key(self, user_id: str, expires_in: int = 3600) -> str:
        """
        Генерирует ключ для привязки чата
        
        Args:
            user_id: ID пользователя
            expires_in: Время жизни ключа в секундах (по умолчанию 1 час)
            
        Returns:
            str: Сгенерированный ключ
        """
        return await self.db.generate_secret_key(user_id, expires_in)
        
    async def get_chat_id(self, user_id: str) -> Optional[str]:
        """
        Получает ID чата пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            str: ID чата, если найден
            None: если чат не найден
        """
        chat_data = await self.db.get_chat_by_user(user_id)
        if chat_data:
            return chat_data["chat_id"]
        return None
        
    async def send_typing(self, chat_id: str):
        """
        Отправляет индикатор набора текста
        
        Args:
            chat_id: ID чата
        """
        logger.debug(f"Sending typing indicator to chat {chat_id}")
        try:
            await self.bot.send_chat_action(chat_id=chat_id, action="typing")
            logger.debug("Typing indicator sent successfully")
        except Exception as e:
            logger.error(f"Error sending typing indicator: {e}", exc_info=True)
        
    async def send_message_to_user(self, user_id: str, text: str, **kwargs):
        """
        Отправляет сообщение пользователю
        
        Args:
            user_id: ID пользователя
            text: Текст сообщения
            **kwargs: Дополнительные параметры для отправки
        """
        chat_id = await self.get_chat_id(user_id)
        if chat_id:
            await self.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        else:
            logger.warning(f"No linked chat found for user {user_id}")
            
    async def request_confirmation(self, user_id: str, message: str, expires_in: int = 3600) -> str:
        """
        Запрашивает подтверждение у пользователя
        
        Args:
            user_id: ID пользователя
            message: Текст запроса
            expires_in: Время жизни запроса в секундах
            
        Returns:
            str: ID запроса на подтверждение
        """
        chat_id = await self.get_chat_id(user_id)
        if not chat_id:
            raise ValueError(f"No linked chat found for user {user_id}")
            
        confirmation_id = await self.db.create_confirmation(
            message=message,
            chat_id=chat_id,
            expires_in=expires_in
        )
        
        keyboard = [
            [
                {"text": "✅ Подтвердить", "callback_data": f"confirm_{confirmation_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{confirmation_id}"}
            ]
        ]
        
        await self.bot.send_message(
            chat_id=chat_id,
            text=f"Требуется подтверждение:\n\n{message}",
            reply_markup={"inline_keyboard": keyboard}
        )
        
        return confirmation_id 
        
    async def send_welcome_message(self, chat_id: str):
        """Отправляет приветственное сообщение"""
        await self.output_hook(
            IOMessage(
                type="text",
                content="Привет! Я готов к работе. Отправь мне сообщение, и я постараюсь помочь.",
                metadata={"chat_id": chat_id}
            )
        ) 

    def register_chat_linked_callback(self, callback):
        """Регистрирует коллбэк для события привязки чата"""
        if asyncio.iscoroutinefunction(callback):
            logger.debug(f"Registering async callback {callback.__name__}")
            self._chat_linked_callbacks.append(callback)
        else:
            logger.debug(f"Registering sync callback {callback.__name__}, wrapping in async")
            async def wrapper(*args, **kwargs):
                return callback(*args, **kwargs)
            self._chat_linked_callbacks.append(wrapper)
        logger.info(f"Registered chat linked callback, total callbacks: {len(self._chat_linked_callbacks)}")

    async def _notify_chat_linked(self, chat_id: str, user_id: str, user_info: Dict[str, Any] = None):
        """Уведомляет все зарегистрированные коллбэки о привязке чата"""
        logger.debug(f"Notifying {len(self._chat_linked_callbacks)} callbacks about chat link: {chat_id} -> {user_id}")
        logger.debug(f"User info: {user_info}")
        for callback in self._chat_linked_callbacks:
            try:
                logger.debug(f"Executing callback {callback.__name__}")
                await callback(chat_id, user_id, user_info)
                logger.debug(f"Callback {callback.__name__} completed successfully")
            except Exception as e:
                logger.error(f"Error in chat linked callback {callback.__name__}: {e}", exc_info=True)

    async def send_buttons(self, chat_id: str, text: str, buttons: List[Dict[str, str]], **kwargs):
        """
        Отправляет сообщение с кнопками
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            buttons: Список кнопок в формате [{"text": "Текст кнопки", "callback_data": "data"}]
            **kwargs: Дополнительные параметры для отправки сообщения
        """
        if not self.bot:
            logger.error("Bot not initialized")
            return

        await self.bot.send_message_with_buttons(chat_id, text, buttons, **kwargs)

    async def _show_typing_indicator(self, chat_id: str):
        """
        Показывает индикатор набора с интервалом
        
        Args:
            chat_id: ID чата
        """
        TYPING_INTERVAL = 4  # Интервал обновления typing в секундах
        
        try:
            while True:
                await self.bot.send_chat_action(
                    chat_id=chat_id, 
                    action="typing"
                )
                await asyncio.sleep(TYPING_INTERVAL)
        except asyncio.CancelledError:
            # Нормальное завершение при отмене задачи
            pass
        except Exception as e:
            logger.error(f"❌ Ошибка при показе индикатора набора: {e}", exc_info=True) 