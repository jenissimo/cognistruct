import logging
from typing import List, Any
import telegramify_markdown
from telegramify_markdown.customize import markdown_symbol
from telegramify_markdown.interpreters import BaseInterpreter, MermaidInterpreter
from telegramify_markdown.type import ContentTypes
import aiohttp
from io import BytesIO

logger = logging.getLogger(__name__)

async def format_message(content: str) -> List[Any]:
    """
    Форматирует сообщение для отправки в Telegram
    
    Args:
        content: Исходный текст сообщения
        
    Returns:
        List[Any]: Список отформатированных частей сообщения
    """
    try:
        # Настраиваем символы для форматирования
        markdown_symbol.head_level_1 = "📌"
        markdown_symbol.link = "🔗"
        
        # Создаем сессию для MermaidInterpreter
        async with aiohttp.ClientSession() as session:
            # Конвертируем и разбиваем на части если нужно
            boxes = await telegramify_markdown.telegramify(
                content=content,
                interpreters_use=[
                    BaseInterpreter(),
                    MermaidInterpreter(session=None)
                ],
                latex_escape=True,
                normalize_whitespace=True,
                max_word_count=4090
            )
            return boxes
            
    except Exception as e:
        logger.error(f"Error formatting message: {e}")
        logger.exception("Full traceback:")
        raise

async def send_content_box(bot, chat_id: str, item: Any):
    """
    Отправляет отформатированную часть сообщения
    
    Args:
        bot: Экземпляр TelegramBot
        chat_id: ID чата
        item: Отформатированная часть сообщения
    """
    try:
        logger.info(f"Sending item type: {item.content_type}")
        
        if item.content_type == ContentTypes.TEXT:
            logger.debug("Sending TEXT")
            await bot.send_message(
                chat_id=chat_id,
                text=item.content,
                parse_mode="MarkdownV2"
            )
        elif item.content_type == ContentTypes.PHOTO:
            logger.debug("Sending PHOTO")
            photo_data = BytesIO(item.file_data)
            photo_data.name = item.file_name
            await bot.app.bot.send_photo(
                chat_id=chat_id,
                photo=photo_data,
                caption=item.caption,
                parse_mode="MarkdownV2"
            )
        elif item.content_type == ContentTypes.FILE:
            logger.debug("Sending FILE")
            file_data = BytesIO(item.file_data)
            file_data.name = item.file_name
            await bot.app.bot.send_document(
                chat_id=chat_id,
                document=file_data,
                caption=item.caption,
                parse_mode="MarkdownV2"
            )
    except Exception as e:
        logger.error(f"Error sending item {item}: {e}")
        logger.exception("Full traceback:")
        raise 