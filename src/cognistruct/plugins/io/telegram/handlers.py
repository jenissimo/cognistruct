import asyncio
from typing import Optional, Dict, Any, Callable, Awaitable
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from cognistruct.core import IOMessage
from cognistruct.core.context import RequestContext
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
        logger.info("🔘 Получено нажатие кнопки в Telegram")
        query = update.callback_query
        data = query.data
        logger.debug(f"Callback data: {data}")
        
        if data.startswith("confirm_"):
            confirmation_id = data.replace("confirm_", "")
            status = "confirmed"
            logger.debug(f"Processing confirmation {confirmation_id} with status {status}")
            
            # Обновляем статус подтверждения
            await self.db.update_confirmation_status(confirmation_id, status)
            
            await query.answer("Спасибо за ответ!")
            await query.edit_message_text(
                f"Действие {status}",
                reply_markup=None
            )
            logger.info("✅ Подтверждение обработано")
            
        elif data.startswith("reject_"):
            confirmation_id = data.replace("reject_", "")
            status = "rejected"
            logger.debug(f"Processing rejection {confirmation_id} with status {status}")
            
            # Обновляем статус подтверждения
            await self.db.update_confirmation_status(confirmation_id, status)
            
            await query.answer("Спасибо за ответ!")
            await query.edit_message_text(
                f"Действие {status}",
                reply_markup=None
            )
            logger.info("❌ Отклонение обработано")
            
        else:
            # Для всех остальных кнопок создаем обычное сообщение
            logger.info("🔄 Обработка пользовательской кнопки")
            chat_id = str(update.effective_chat.id)
            chat_link = await self.db.get_chat_link(chat_id)
            if not chat_link:
                logger.warning(f"Chat {chat_id} not linked to any user")
                await query.answer("Чат не привязан")
                return
                
            logger.debug(f"Found chat link: {chat_link}")
            
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
                logger.warning("Button not found in keyboard markup")
                await query.answer("Ошибка: кнопка не найдена")
                return
                
            logger.debug(f"Selected option: {selected_option}")
            
            # Получаем информацию о пользователе
            telegram_user = update.effective_user
            user_info = {
                "telegram_username": telegram_user.username,
                "telegram_first_name": telegram_user.first_name,
                "telegram_last_name": telegram_user.last_name,
                "telegram_language_code": telegram_user.language_code
            }
            
            # Создаем контекст запроса с очищенными метаданными
            request_context = RequestContext(
                user_id=chat_link["user_id"],  # Используем user_id из базы
                metadata={
                    "chat_id": chat_id,
                    "platform": "telegram",
                    "user_info": user_info,  # Добавляем информацию о пользователе
                    "message_id": query.message.message_id,
                    "message_date": query.message.date.timestamp(),
                    "callback_data": data,
                    "selected_option": selected_option
                },
                timestamp=datetime.now().timestamp()
            )
            logger.debug(f"Created request context: {request_context}")
                
            message = IOMessage(
                type="text",
                content=selected_option,
                metadata={
                    "chat_id": chat_id,
                    "user_id": chat_link["user_id"],
                    "user_info": user_info,  # Добавляем информацию о пользователе
                    "callback_data": data,
                    "selected_option": selected_option
                },
                source="telegram",
                context=request_context
            )
            logger.debug(f"Created IO message: {message}")
            
            # Передаем сообщение в обработчик
            if self.message_handler:
                await query.answer("Принято!")
                await query.edit_message_reply_markup(reply_markup=None)
                try:
                    # Показываем индикатор набора
                    await self.bot.send_chat_action(chat_id=chat_id, action="typing")
                    logger.info("🔄 Передаю сообщение обработчику...")
                    
                    # Получаем ответ от обработчика
                    response = await self.message_handler(message)
                    
                    # Если ответ - строка или IOMessage, передаем контекст
                    if isinstance(response, str):
                        response = IOMessage(
                            type="text",
                            content=response,
                            source="agent",
                            context=request_context  # Передаем тот же контекст
                        )
                    elif isinstance(response, IOMessage) and not response.context:
                        response.context = request_context  # Добавляем контекст если его нет
                    
                    logger.info("✅ Сообщение успешно обработано")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке ответа: {e}", exc_info=True)
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text="Произошла ошибка при обработке ответа. Попробуйте позже."
                    )
            
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих сообщений"""
        logger.info("🔵 Получено новое сообщение в Telegram")
        chat_id = update.effective_chat.id
        logger.debug(f"Chat ID: {chat_id}, Message: {update.message.text[:50]}...")
        
        # Проверяем привязку чата
        chat_link = await self.db.get_chat_link(str(chat_id))
        if not chat_link:
            logger.warning(f"Chat {chat_id} not linked to any user")
            await update.message.reply_text(
                "Этот чат не привязан к пользователю. Используйте /start для привязки."
            )
            return
            
        logger.debug(f"Found chat link: {chat_link}")
        
        # Получаем информацию о пользователе
        telegram_user = update.effective_user
        user_info = {
            "telegram_username": telegram_user.username,
            "telegram_first_name": telegram_user.first_name,
            "telegram_last_name": telegram_user.last_name,
            "telegram_language_code": telegram_user.language_code
        }
        
        # Создаем контекст запроса с очищенными метаданными
        request_context = RequestContext(
            user_id=chat_link["user_id"],  # Используем user_id из базы
            metadata={
                "chat_id": str(chat_id),
                "platform": "telegram",
                "user_info": user_info,  # Добавляем информацию о пользователе
                "message_id": update.message.message_id,
                "message_date": update.message.date.timestamp()
            },
            timestamp=datetime.now().timestamp()
        )
        logger.debug(f"Created request context: {request_context}")
        
        # Создаем сообщение
        message = IOMessage(
            type="text",
            content=update.message.text,
            metadata={
                "chat_id": str(chat_id),
                "user_id": chat_link["user_id"],
                "user_info": user_info  # Добавляем информацию о пользователе
            },
            source="telegram",
            context=request_context
        )
        logger.debug(f"Created IO message: {message}")
        
        # Передаем сообщение обработчику
        if self.message_handler:
            try:
                # Показываем индикатор набора
                await self.bot.send_chat_action(chat_id=chat_id, action="typing")
                logger.info("🔄 Передаю сообщение обработчику...")
                
                # Получаем ответ от обработчика
                response = await self.message_handler(message)
                
                # Если ответ - генератор (стрим)
                if hasattr(response, '__aiter__'):
                    logger.debug("Получен стрим-ответ")
                    # Создаем IOMessage со стримом
                    stream_message = IOMessage.create_stream(
                        response,
                        source="agent",
                        context=request_context
                    )
                    # Пропускаем через streaming_output_hook плагина
                    async for chunk in self.plugin.streaming_output_hook(stream_message):
                        # Чанки уже обработаны в streaming_output_hook
                        pass
                        
                # Если ответ - строка или IOMessage
                else:
                    logger.debug("Получен обычный ответ")
                    if isinstance(response, str):
                        response = IOMessage(
                            type="text",
                            content=response,
                            source="agent",
                            context=request_context
                        )
                    elif isinstance(response, IOMessage) and not response.context:
                        response.context = request_context
                        
                    # Передаем ответ в output_hook плагина
                    await self.plugin.output_hook(response)
                    
                logger.info("✅ Сообщение успешно обработано")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке сообщения: {e}", exc_info=True)
                await update.message.reply_text(
                    "Произошла ошибка при обработке сообщения. Попробуйте позже."
                )
        else:
            logger.warning("❗ Message handler not set") 