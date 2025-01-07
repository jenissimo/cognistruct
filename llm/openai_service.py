import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from openai import AsyncOpenAI
from pydantic import BaseModel

from llm.interfaces import BaseLLM, LLMResponse, ToolSchema
from utils.logging import setup_logger
from utils.schema_converter import convert_tool_schema

logger = setup_logger(__name__)


@dataclass
class OpenAIProvider:
    """Конфигурация провайдера OpenAI API"""
    name: str
    model: str
    api_base: str
    api_key: Optional[str] = None  # Может быть None для некоторых провайдеров


# Предопределенные провайдеры
OPENAI = OpenAIProvider(
    name="openai",
    model="gpt-3.5-turbo",
    api_base="https://api.openai.com/v1",
    api_key=""  # Заполняется из конфига
)

DEEPSEEK = OpenAIProvider(
    name="deepseek",
    model="deepseek-chat",
    api_base="https://api.deepseek.com/v1",
    api_key=""  # Заполняется из конфига
)

OLLAMA = OpenAIProvider(
    name="ollama",
    model="",  # Заполняется пользователем
    api_base="http://localhost:11434/v1",
    api_key=None  # Не требуется для локального Ollama
)


class OpenAIService(BaseLLM):
    """Реализация для работы с OpenAI-совместимыми API"""

    def __init__(self, provider: OpenAIProvider):
        self.provider = provider

        # Для Ollama не требуется API ключ
        if provider.name == "ollama":
            api_key = "ollama"
            logger.info(f"Initialized provider '{provider.name}' without API key.")
        else:
            if not provider.api_key:
                logger.error(f"API key must be provided for provider '{provider.name}'.")
                raise ValueError(f"API key must be provided for provider '{provider.name}'")
            api_key = provider.api_key
            logger.info(f"Initialized provider '{provider.name}' with provided API key.")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider.api_base
        )
        self.tool_executor = None

    def set_tool_executor(self, executor):
        """Устанавливает функцию для выполнения инструментов"""
        self.tool_executor = executor

    def _is_duplicate_tool_call(self, new_call: Dict, current_messages: List[Dict]) -> bool:
        """Проверяет, не вызывался ли уже этот инструмент с теми же аргументами"""
        new_name = new_call.get("name")
        new_args = new_call.get("arguments")

        for msg in current_messages:
            if msg.get("role") == "tool" and "name" in msg:
                if (msg.get("name") == new_name and
                        msg.get("arguments") == new_args):
                    return True
        return False

    async def process_tool_call(self, tool_call) -> Dict[str, Any]:
        """
        Обрабатывает вызов инструмента
        
        Args:
            tool_call: Объект вызова инструмента
            
        Returns:
            Словарь с результатом вызова в формате {role, content, tool_call_id}
        """
        if not self.tool_executor:
            raise RuntimeError("Tool executor не установлен")
            
        try:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"Executing tool '{tool_name}' with arguments: {tool_args}")
            result = await self.tool_executor(
                tool_name,
                **tool_args
            )
            logger.info(f"Tool {tool_name} returned: {result}")
            
            # Всегда сериализуем результат в JSON
            try:
                # Пробуем распарсить как JSON
                content_json = json.loads(str(result))
                # Если успешно и нет поля answer, оборачиваем
                if "answer" not in content_json:
                    content = json.dumps({"answer": content_json})
                else:
                    content = json.dumps(content_json)
            except json.JSONDecodeError:
                # Если не JSON, оборачиваем в {"answer": ...}
                content = json.dumps({"answer": str(result)})
            
            return {
                "role": "tool",
                "content": content,
                "tool_call_id": tool_call.id
            }
            
        except json.JSONDecodeError as jde:
            error_msg = f"Invalid JSON in function arguments: {str(jde)}"
            logger.error(error_msg)
            return {
                "role": "tool",
                "content": json.dumps({"error": error_msg}),
                "tool_call_id": tool_call.id
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool execution failed: {error_msg}")
            return {
                "role": "tool",
                "content": json.dumps({"error": error_msg}),
                "tool_call_id": tool_call.id
            }

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSchema]] = None,
        temperature: float = 0.7,
        response_format: Optional[str] = None,
        max_iterations: int = 5,
        **kwargs
    ) -> LLMResponse:
        """Генерирует ответ, при необходимости выполняя инструменты"""

        request_params = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": temperature,
            **kwargs  # Добавляем дополнительные параметры
        }

        if tools:
            request_params["tools"] = convert_tool_schema(tools)
            request_params["tool_choice"] = "auto"  # Разрешаем модели самостоятельно вызывать функции

        if response_format:
            request_params["response_format"] = response_format

        iteration = 0
        current_messages = messages.copy()

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration}, messages: {[f'{m.get('role')}: {m.get('content')[:30]}...' for m in current_messages]}")

            try:
                # Делаем запрос к LLM
                response = await self.client.chat.completions.create(**request_params)
                message = response.choices[0].message
                logger.debug(f"LLM response: {message}")

                # Проверяем наличие tool_calls
                tool_calls = getattr(message, 'tool_calls', None)
                has_tool_calls = tool_calls is not None and len(tool_calls) > 0
                
                # Добавляем сообщение от ассистента в историю
                current_messages.append(message.model_dump())

                if has_tool_calls:
                    logger.info(f"Processing {len(message.tool_calls)} tool calls")
                    
                    # Обрабатываем каждый вызов инструмента
                    for tool_call in message.tool_calls:
                        # Пропускаем дубликаты
                        if self._is_duplicate_tool_call(tool_call.function.model_dump(), current_messages):
                            logger.warning("Skipping duplicate tool call")
                            continue
                            
                        # Обрабатываем вызов и добавляем результат в историю
                        tool_message = await self.process_tool_call(
                            tool_call
                        )
                        current_messages.append(tool_message)
                    
                    # Обновляем сообщения для следующей итерации
                    request_params["messages"] = current_messages
                    continue
                
                # Если нет tool_calls, форматируем и возвращаем ответ
                content = message.content or ""
                if response_format == "json":
                    try:
                        content_json = json.loads(content)
                        if "answer" not in content_json:
                            content = json.dumps({"answer": content})
                    except json.JSONDecodeError:
                        content = json.dumps({"answer": content})

                return LLMResponse(
                    content=content,
                    tool_messages=current_messages[len(messages):]
                )

            except Exception as e:
                logger.error(f"API request failed: {str(e)}")
                raise RuntimeError(f"API request failed: {str(e)}")

        logger.warning("Max iterations reached")
        return LLMResponse(
            content=json.dumps({"error": "Max iterations reached"}),
            tool_messages=current_messages[len(messages):]
        )

    async def close(self):
        """Закрывает соединение с API"""
        if hasattr(self.client, 'close'):
            await self.client.close()
        elif hasattr(self.client.http_client, 'aclose'):
            await self.client.http_client.aclose()
