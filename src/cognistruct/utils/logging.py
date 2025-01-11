import logging
import sys
from typing import Optional

def init_logging(level: int = logging.INFO, format_str: Optional[str] = None):
    """
    Инициализирует корневой логгер.

    Args:
        level: Уровень логирования.
        format_str: Формат сообщений. Если None, используется стандартный формат.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        if format_str is None:
            format_str = "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(format_str)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

def setup_logger(
    name: str,
    level: Optional[int] = None,
    format_str: Optional[str] = None
) -> logging.Logger:
    """
    Создаёт и настраивает логгер для модуля.

    Args:
        name: Имя логгера (обычно __name__ модуля).
        level: Уровень логирования. Если None, используется уровень корневого логгера.
        format_str: Формат сообщений. Если None, используется стандартный формат.

    Returns:
        Настроенный логгер.
    """
    logger = logging.getLogger(name)

    if level is not None:
        logger.setLevel(level)
    else:
        logger.setLevel(logging.NOTSET)  # Наследует уровень от корневого логгера

    # Убедимся, что логгер не дублирует сообщения, если он не корневой
    if logger is not logging.getLogger():
        logger.propagate = True

    # Добавляем обработчик только если у логгера нет собственных обработчиков
    if not logger.handlers:
        if format_str:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logger.level)
            formatter = logging.Formatter(format_str)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        # Иначе полагаемся на корневой логгер через пропагацию

    return logger
