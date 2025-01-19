import asyncio
from typing import Optional, Dict, Any, Callable, Awaitable
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from cognistruct.core import IOMessage
from .database import TelegramDatabase
from .bot import TelegramBot
from .utils import format_message, send_content_box

logger = logging.getLogger(__name__)

class TelegramHandlers:
    """Обработчики команд и сообщений Telegram"""
    
    def __init__(self, db: TelegramDatabase, bot: TelegramBot, plugin: 'TelegramPlugin'):
        self.db = db
        self.bot = bot
        self.plugin = plugin
        self.message_handler: Optional[Callable[[IOMessage], Awaitable[None]]] = None
        
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        chat_id = update.effective_chat.id
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Для привязки чата используйте команду /start с секретным ключом\n"
                "Пример: /start your-secret-key"
            )
            return
            
        secret_key = args[0]
        
        try:
            # Проверяем ключ
            key_data = await self.db.check_secret_key(secret_key)
            
            if not key_data:
                logger.warning(f"Invalid key {secret_key}: key not found or expired")
                await update.message.reply_text(
                    "Неверный или устаревший ключ. Запросите новый ключ."
                )
                return
                
            user_id = key_data["user_id"]
            
            # Помечаем ключ как использованный
            await self.db.mark_key_used(secret_key)
            
            # Привязываем чат
            await self.db.link_chat(str(chat_id), user_id)
            
            # Получаем информацию о пользователе
            telegram_user = update.effective_user
            user_info = {
                "telegram_username": telegram_user.username,
                "telegram_first_name": telegram_user.first_name,
                "telegram_last_name": telegram_user.last_name,
                "telegram_language_code": telegram_user.language_code
            }
            logger.debug(f"Got Telegram user info: {user_info}")
            
            # Уведомляем о привязке чата с информацией о пользователе
            await self.plugin._notify_chat_linked(str(chat_id), user_id, user_info)
            
            #await update.message.reply_text(
            #    "Чат успешно привязан! Теперь вы можете общаться со мной."
            #)
            
        except Exception as e:
            logger.error(f"Error linking chat: {e}")
            await update.message.reply_text(
                "Произошла ошибка при привязке чата. Попробуйте позже."
            )
            
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback query (кнопок)"""
        query = update.callback_query
        data = query.data
        
        if data.startswith("confirm_"):
            confirmation_id = data.replace("confirm_", "")
            status = "confirmed"
            
            # Обновляем статус подтверждения
            await self.db.update_confirmation_status(confirmation_id, status)
            
            await query.answer("Спасибо за ответ!")
            await query.edit_message_text(
                f"Действие {status}",
                reply_markup=None
            )
        elif data.startswith("reject_"):
            confirmation_id = data.replace("reject_", "")
            status = "rejected"
            
            # Обновляем статус подтверждения
            await self.db.update_confirmation_status(confirmation_id, status)
            
            await query.answer("Спасибо за ответ!")
            await query.edit_message_text(
                f"Действие {status}",
                reply_markup=None
            )
        else:
            # Для всех остальных кнопок создаем обычное сообщение
            chat_id = str(update.effective_chat.id)
            chat_link = await self.db.get_chat_link(chat_id)
            if not chat_link:
                await query.answer("Чат не привязан")
                return
                
            # Получаем текст нажатой кнопки
            selected_option = None
            for row in query.message.reply_markup.inline_keyboard:
                for button in row:
                    if button.callback_data == data:
                        selected_option = button.text
                        break
                if selected_option:
                    break
                    
            if not selected_option:
                await query.answer("Ошибка: кнопка не найдена")
                return
                
            message = IOMessage(
                type="telegram_message",
                content=selected_option,
                metadata={
                    "chat_id": chat_id,
                    "user_id": chat_link["user_id"],
                    "update": update,
                    "context": context,
                    "callback_data": data  # Передаем оригинальный callback_data для контекста
                }
            )
            
            # Передаем сообщение в обработчик
            if self.message_handler:
                await query.answer("Принято!")
                await query.edit_message_reply_markup(reply_markup=None)
                try:
                    # Показываем индикатор набора
                    await self.bot.send_chat_action(chat_id=chat_id, action="typing")
                    await self.message_handler(message)
                except Exception as e:
                    logger.error(f"Error processing button response: {e}")
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text="Произошла ошибка при обработке ответа. Попробуйте позже."
                    )
            
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих сообщений из Telegram"""
        logger.debug("Received message in handle_message")
        
        if not update.message or not update.message.text:
            logger.warning("No message or text in update")
            return
            
        chat_id = update.effective_chat.id
        text = update.message.text
        
        logger.debug(f"Processing message: {text[:50]}...")
        
        # Создаем IOMessage из телеграм сообщения
        message = IOMessage(
            type="telegram_message",
            content=text,
            metadata={
                "chat_id": str(chat_id),
                "update": update,
                "context": context
            }
        )
        
        # Показываем начальный индикатор набора
        await self.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Передаем сообщение в обработчик
        if self.message_handler:
            try:
                logger.debug("Passing message to handler")
                response = await self.message_handler(message)
                
                # Если ответ - генератор, итерируемся по нему
                if hasattr(response, '__aiter__'):
                    logger.debug("Got streaming response, starting iteration")
                    async for chunk in response:
                        # Просто проходим по чанкам, их обработка уже в streaming_output_hook
                        pass
                        
                logger.debug("Message processing completed")
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                await update.message.reply_text(
                    "Произошла ошибка при обработке сообщения. Попробуйте позже."
                )
        else:
            logger.warning("Message handler not set") 