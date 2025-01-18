import asyncio
from typing import Optional, Dict, Any, List
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
from .types import TelegramPluginProtocol

# Настраиваем логирование
logging.getLogger("httpx").setLevel(logging.WARNING)
telegramify_logger = logging.getLogger("telegramify_markdown")
telegramify_logger.setLevel(logging.INFO)
telegramify_logger.warn = telegramify_logger.warning  # добавляем алиас для warn

logger = logging.getLogger(__name__)

class TelegramPlugin(BasePlugin):
    """Telegram плагин для CogniStruct"""
    
    def __init__(self):
        super().__init__()
        self.db = None
        self.bot = None
        self.handlers = None
        self._current_chat_id = None
        self.telegram_user_id = None
        self._chat_linked_callbacks = []  # список коллбэков для обработки привязки
        
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
        # Добавляем паттерн для обработки коллбэков: choice, confirm, reject, onboarding и других, если понадобится
        self.bot.add_handler(CallbackQueryHandler(self.handlers.handle_callback_query, 
                                                    pattern="^(choice|confirm|reject|onboarding)_"))
        
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
        
    async def cleanup(self):
        """Очистка ресурсов"""
        if self.bot:
            await self.bot.stop()
        if self.db:
            await self.db.close()
        
    async def input_hook(self, message: IOMessage) -> bool:
        """Проверяет привязку чата"""
        if message.type == "telegram_message":
            chat_id = message.metadata["chat_id"]
            chat_link = await self.db.get_chat_link(chat_id)
            
            if not chat_link:
                await self.bot.send_message(
                    chat_id,
                    "Чат не привязан. Используйте /start с секретным ключом"
                )
                return True
                
            # Сохраняем chat_id для текущего запроса
            self._current_chat_id = chat_id
            return False
            
        return False
        
    async def output_hook(self, message: IOMessage):
        """Обрабатывает исходящие сообщения"""
        if "chat_id" not in message.metadata:
            logger.warning("No chat_id in message metadata: %s", message.metadata)
            return message
        
        chat_id = message.metadata["chat_id"]
        
        try:
            # Обрабатываем интерактивное сообщение с кнопками
            if message.type == "interactive_message":
                options = message.metadata.get("options", [])
                callback_prefix = message.metadata.get("callback_prefix", "choice")
                
                # Формируем клавиатуру из вариантов
                keyboard = []
                for i, option in enumerate(options):
                    keyboard.append([{
                        "text": option,
                        "callback_data": f"{callback_prefix}_{i}"
                    }])
                    
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message.content,
                    reply_markup={"inline_keyboard": keyboard}
                )
                
            # Обрабатываем стриминг
            elif message.type == "stream":
                current_content = ""
                last_typing = 0
                typing_interval = 3.0  # Интервал обновления статуса набора
                
                async for chunk in message.content:
                    current_time = time.time()
                    if current_time - last_typing >= typing_interval:
                        await self.bot.send_chat_action(
                            chat_id=chat_id,
                            action="typing"
                        )
                        last_typing = current_time
                        
                    current_content += chunk.delta
                
                boxes = await format_message(current_content)
                for item in boxes:
                    await send_content_box(self.bot, chat_id, item)
                    
            # Обрабатываем обычное текстовое сообщение
            elif message.type == "text":
                content = str(message.content)
                boxes = await format_message(content)
                for item in boxes:
                    await send_content_box(self.bot, chat_id, item)
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            content = str(message.content)
            await self.bot.send_message(
                chat_id=chat_id,
                text=content
            )
                    
        return message
        
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
        await self.bot.send_chat_action(chat_id=chat_id, action="typing")
        
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
        
    async def setup_minimal(self, token: str):
        """Минимальная инициализация без поллинга"""
        self.token = token
        self.db = TelegramDatabase()
        await self.db.connect()
        # self.bot = TelegramBot(token)
        
    async def add_chat_linked_callback(self, callback):
        """Добавляет коллбэк для обработки успешной привязки чата"""
        self._chat_linked_callbacks.append(callback)
        
    async def _notify_chat_linked(self, chat_id: str, user_id: str):
        """Уведомляет все коллбэки о привязке чата"""
        for callback in self._chat_linked_callbacks:
            try:
                await callback(chat_id, user_id)
            except Exception as e:
                logger.error(f"Error in chat linked callback: {e}")
