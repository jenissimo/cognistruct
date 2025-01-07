from utils import Config, setup_logger


logger = setup_logger(__name__)


def main():
    logger.info("Настройка Cognistruct")
    logger.info("---------------------")
    
    api_key = input("Введите ваш DeepSeek API ключ: ").strip()
    telegram_token = input("Введите токен Telegram бота (опционально): ").strip()
    
    config = Config(
        deepseek_api_key=api_key,
        telegram_token=telegram_token if telegram_token else None
    )
    config.save()
    
    logger.info("Конфигурация сохранена!")
    if telegram_token:
        logger.info("Для использования Telegram бота запустите example_telegram_agent.py")
    else:
        logger.info("Для базового тестирования запустите test_agent.py")


if __name__ == "__main__":
    main() 