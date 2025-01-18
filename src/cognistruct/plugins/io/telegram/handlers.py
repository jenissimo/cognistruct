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
from .types import TelegramPluginProtocol

logger = logging.getLogger(__name__)

class TelegramHandlers:
    """Обработчики команд и сообщений Telegram"""
    
    def __init__(self, db: TelegramDatabase, bot: TelegramBot, plugin: TelegramPluginProtocol):
        self.db = db
        self.bot = bot
        self.plugin = plugin
        self.message_handler = None
        
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        chat_id = str(update.effective_chat.id)
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
            await self.db.link_chat(chat_id, user_id)
            
            # Отправляем сообщение об успешной привязке
            await update.message.reply_text(
                "Чат успешно привязан! Давайте начнем!"
            )
            
            # Уведомляем коллбэки о привязке
            await self.plugin._notify_chat_linked(chat_id, user_id)
            
        except Exception as e:
            logger.error(f"Error linking chat: {e}")
            await update.message.reply_text(
                "Произошла ошибка при привязке чата. Попробуйте позже."
            )
            
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback-запросов от кнопок"""
        if not update.callback_query:
            return
        
        query = update.callback_query
        data = query.data
        chat_id = str(query.message.chat_id)
        
        try:
            # Получаем привязку чата к пользователю
            chat_link = await self.db.get_chat_link(chat_id)
            if not chat_link:
                await query.answer("Чат не привязан")
                return
            
            # Обрабатываем онбординг (например, callback_data вида onboarding_<step_id>_<option_idx>)
            if isinstance(data, str) and data.startswith("onboarding_"):
                try:
                    _, step_id, option_idx = data.split("_")
                    option_idx = int(option_idx)
                    
                    # Проверяем наличие кнопок и индекс
                    if not query.message.reply_markup or \
                       not query.message.reply_markup.inline_keyboard or \
                       option_idx >= len(query.message.reply_markup.inline_keyboard):
                        await query.answer("Ошибка: кнопка не найдена")
                        return
                    
                    # Получаем текст выбранного варианта
                    selected_option = query.message.reply_markup.inline_keyboard[option_idx][0].text
                    
                    # Создаем сообщение с выбранным вариантом
                    message = IOMessage(
                        type="text",
                        content=selected_option,
                        metadata={
                            "chat_id": chat_id,
                            "user_id": chat_link["user_id"],
                            "from_callback": True
                        }
                    )
                    
                    # Обновляем сообщение, показывая выбор
                    await query.edit_message_text(
                        f"{query.message.text}\n\n✅ Выбрано: {selected_option}",
                        reply_markup=None
                    )
                    
                    # Отвечаем на callback
                    await query.answer("Выбор принят")
                    
                    # Передаем сообщение в основной обработчик, если он установлен
                    if self.message_handler:
                        await self.message_handler(message)
                        
                except (ValueError, IndexError) as e:
                    logger.error(f"Error processing onboarding callback: {e}")
                    await query.answer("Ошибка обработки выбора")
                    
            # Обрабатываем подтверждения (callback_data вида confirm_<confirmation_id> или reject_<confirmation_id>)
            elif isinstance(data, str) and (data.startswith("confirm_") or data.startswith("reject_")):
                confirmation_id = data.split("_")[1]
                is_confirmed = data.startswith("confirm_")
                
                # Проверяем подтверждение
                confirmation = await self.db.get_confirmation(confirmation_id)
                if not confirmation:
                    await query.answer("Подтверждение не найдено или устарело")
                    return
                
                # Обновляем статус подтверждения
                await self.db.update_confirmation_status(
                    confirmation_id,
                    "confirmed" if is_confirmed else "rejected"
                )
                
                # Удаляем кнопки
                await query.edit_message_reply_markup(reply_markup=None)
                
                # Отвечаем на callback
                await query.answer(
                    "✅ Подтверждено" if is_confirmed else "❌ Отклонено"
                )
                
            else:
                await query.answer("Неизвестный callback")
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}", exc_info=True)
            await query.answer("Произошла ошибка")
            
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих сообщений"""
        logger.debug("Received message in handle_message")
        
        if not update.message or not update.message.text:
            logger.warning("No message or text in update")
            return
            
        chat_id = str(update.effective_chat.id)
        text = update.message.text
        
        logger.debug(f"Processing message: {text[:50]}...")
        
        # Получаем привязку чата к пользователю
        chat_link = await self.db.get_chat_link(chat_id)
        if not chat_link:
            await update.message.reply_text(
                "Чат не привязан. Используйте /start с секретным ключом"
            )
            return
        
        # Создаем IOMessage с user_id в метаданных
        message = IOMessage(
            type="telegram_message",
            content=text,
            metadata={
                "chat_id": chat_id,
                "user_id": chat_link["user_id"],
                # Сохраняем только нужные поля из Update
                "telegram": {
                    "message_id": update.message.message_id,
                    "from_user": {
                        "id": update.message.from_user.id,
                        "username": update.message.from_user.username,
                        "first_name": update.message.from_user.first_name,
                        "last_name": update.message.from_user.last_name
                    } if update.message.from_user else None,
                    "chat": {
                        "id": update.message.chat.id,
                        "type": update.message.chat.type,
                        "title": update.message.chat.title
                    }
                }
            }
        )
        
        # Отправляем индикатор набора
        await self.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Вызываем обработчик, если он установлен
        if self.message_handler:
            try:
                logger.debug("Calling message handler")
                await self.message_handler(message)
                logger.debug("Message handler completed")
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                await update.message.reply_text(
                    "Произошла ошибка при обработке сообщения. Попробуйте позже."
                )
        else:
            logger.warning("Message handler not set")
