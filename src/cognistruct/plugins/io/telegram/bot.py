import logging
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class TelegramBot:
    """Обертка над python-telegram-bot"""
    
    def __init__(self, token: str):
        self.token = token
        # Создаем билдер с нужными параметрами
        builder = Application.builder()
        builder.token(token)
        # Устанавливаем параметры по умолчанию
        builder.arbitrary_callback_data(True)
        builder.read_timeout(30)
        builder.write_timeout(30)
        builder.connect_timeout(30)
        builder.pool_timeout(30)
        
        self.app = builder.build()
        self._is_running = False
        
    async def start(self):
        """Инициализирует бота без запуска поллинга"""
        if not self._is_running:
            logger.info("Initializing telegram bot...")
            await self.app.initialize()
            await self.app.start()
            self._is_running = True
        
    async def start_polling(self):
        """Запускает поллинг"""
        logger.info("Starting telegram polling...")
        if not self._is_running:
            await self.app.initialize()
            await self.app.start()
            self._is_running = True
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
    async def stop(self):
        """Останавливает бота"""
        try:
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            if self._is_running:
                await self.app.stop()
                self._is_running = False
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
        
    def add_handler(self, handler):
        """Регистрирует обработчик"""
        self.app.add_handler(handler)
        
    async def send_message(self, chat_id: str, text: str, **kwargs):
        """Отправляет сообщение"""
        await self.app.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        
    async def send_message_with_buttons(self, chat_id: str, text: str, buttons: List[Dict[str, str]], **kwargs):
        """
        Отправка сообщения с кнопками
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            buttons: Список кнопок в формате [{"text": "Текст кнопки", "callback_data": "data"}]
            **kwargs: Дополнительные параметры для отправки сообщения
        """
        keyboard = []
        row = []
        
        for button in buttons:
            row.append(InlineKeyboardButton(
                text=button["text"],
                callback_data=button["callback_data"]
            ))
            
            # Создаем новый ряд каждые 2 кнопки
            if len(row) == 2:
                keyboard.append(row)
                row = []
                
        # Добавляем оставшиеся кнопки
        if row:
            keyboard.append(row)
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self.app.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            **kwargs
        )
        
    async def send_chat_action(self, chat_id: str, action: str):
        """Отправляет действие (печатает, отправляет фото и т.д.)"""
        await self.app.bot.send_chat_action(chat_id=chat_id, action=action) 