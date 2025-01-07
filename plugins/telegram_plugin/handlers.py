import logging
from typing import Optional, Callable, Awaitable
from telegram import Update
from telegram.ext import ContextTypes
from .database import TelegramDatabase
from plugins.base_plugin import IOMessage

logger = logging.getLogger(__name__)

class TelegramHandlers:
    """Обработчики команд и сообщений Telegram"""
    
    def __init__(self, db: TelegramDatabase):
        self.db = db
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
            
            await update.message.reply_text(
                "Чат успешно привязан! Теперь вы можете общаться со мной."
            )
            
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
        elif data.startswith("reject_"):
            confirmation_id = data.replace("reject_", "")
            status = "rejected"
        else:
            await query.answer("Неизвестное действие")
            return
            
        # Обновляем статус подтверждения
        await self.db.update_confirmation_status(confirmation_id, status)
        
        await query.answer("Спасибо за ответ!")
        await query.edit_message_text(
            f"Действие {status}",
            reply_markup=None
        )
            
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих сообщений"""
        if not update.message or not update.message.text:
            return
            
        chat_id = update.effective_chat.id
        text = update.message.text
        
        # Создаем IOMessage
        message = IOMessage(
            type="telegram_message",
            content=text,
            metadata={
                "chat_id": str(chat_id),
                "update": update,
                "context": context
            }
        )
        
        # Проверяем привязку
        chat_link = await self.db.get_chat_link(str(chat_id))
        if not chat_link:
            await update.message.reply_text(
                "Чат не привязан. Используйте /start с секретным ключом"
            )
            return
            
        # Добавляем user_id в метаданные
        message.metadata["user_id"] = chat_link["user_id"]
        
        # Передаем сообщение обработчику
        if self.message_handler:
            await self.message_handler(message)
        else:
            logger.warning("Message handler not set") 