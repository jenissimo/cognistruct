from utils import Config, setup_logger


logger = setup_logger(__name__)


def main():
    logger.info("Настройка Cognistruct")
    logger.info("---------------------")
    
    # Пробуем загрузить существующую конфигурацию
    try:
        current_config = Config.load()
        has_api_key = bool(current_config.deepseek_api_key)
        has_telegram = bool(current_config.telegram_token)
        
        if has_api_key:
            logger.info("Найден существующий DeepSeek API ключ")
        if has_telegram:
            logger.info("Найден существующий Telegram токен")
    except:
        current_config = None
        has_api_key = False
        has_telegram = False
    
    # Запрашиваем новые значения
    api_key = input("Введите ваш DeepSeek API ключ" + (" (Enter чтобы оставить текущий)" if has_api_key else "") + ": ").strip()
    telegram_token = input("Введите токен Telegram бота" + (" (Enter чтобы оставить текущий)" if has_telegram else " (опционально)") + ": ").strip()
    
    # Сохраняем старые значения если ввод пустой
    if has_api_key and not api_key:
        api_key = current_config.deepseek_api_key
    if has_telegram and not telegram_token:
        telegram_token = current_config.telegram_token
    
    config = Config(
        deepseek_api_key=api_key,
        telegram_token=telegram_token if telegram_token else None
    )
    config.save()
    
    logger.info("Конфигурация сохранена!")
    if telegram_token:
        logger.info("Для использования Telegram бота запустите example_telegram_agent.py")
    else:
        logger.info("Для базового тестирования запустите example_simple_agent.py")


if __name__ == "__main__":
    main() 