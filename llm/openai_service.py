import json
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass

from openai import AsyncOpenAI
from pydantic import BaseModel

from llm.interfaces import BaseLLM, LLMResponse, ToolSchema, StreamChunk, ToolCall
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
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, AsyncGenerator[StreamChunk, None]]:
        """Генерирует ответ, при необходимости выполняя инструменты"""
        
        request_params = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }

        if tools:
            request_params["tools"] = convert_tool_schema(tools)
            request_params["tool_choice"] = "auto"

        if stream:
            return self._generate_stream_response(request_params)
        else:
            return await self._generate_regular_response(request_params)

    async def _generate_stream_response(
        self, 
        request_params: Dict[str, Any]
    ) -> AsyncGenerator[StreamChunk, None]:
        """Генерирует потоковый ответ"""
        try:
            logger.info("Starting stream generation with params: %s", request_params)
            stream = await self.client.chat.completions.create(**request_params)
            
            current_content = ""
            current_tool = None
            
            async for chunk in stream:
                logger.info("Received chunk: %s", chunk)
                delta = chunk.choices[0].delta
                logger.info("Delta content: %s", delta.content if hasattr(delta, "content") else None)
                logger.info("Delta tool_calls: %s", delta.tool_calls if hasattr(delta, "tool_calls") else None)
                
                # Обработка текстового контента
                if hasattr(delta, "content") and delta.content:
                    current_content += delta.content
                    logger.info("Yielding text chunk: %s", delta.content)
                    yield StreamChunk(
                        content=current_content,
                        delta=delta.content,
                        is_complete=False
                    )
                
                # Обработка вызова инструмента
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    tool_call = delta.tool_calls[0]
                    logger.info("Processing tool call: %s", tool_call)
                    
                    # Собираем вызов инструмента
                    if not current_tool:
                        current_tool = {
                            "name": tool_call.function.name if hasattr(tool_call.function, "name") else "",
                            "arguments": tool_call.function.arguments if hasattr(tool_call.function, "arguments") else ""
                        }
                        logger.info("Started new tool call: %s", current_tool)
                    else:
                        # Обновляем только если пришло новое значение
                        if hasattr(tool_call.function, "name") and tool_call.function.name:
                            current_tool["name"] = tool_call.function.name
                        if hasattr(tool_call.function, "arguments") and tool_call.function.arguments:
                            current_tool["arguments"] += tool_call.function.arguments
                        logger.info("Updated tool call: %s", current_tool)
                    
                    # Проверяем, что у нас есть имя и аргументы похожи на полный JSON
                    if current_tool["name"] and current_tool["arguments"]:
                        # Проверяем, что JSON полный (начинается с { и заканчивается })
                        args_str = current_tool["arguments"].strip()
                        if args_str.startswith("{") and args_str.endswith("}"):
                            try:
                                args = json.loads(args_str)
                                tool_call = ToolCall(
                                    tool=current_tool["name"],
                                    params=args
                                )
                                logger.info("Executing tool: %s with args: %s", tool_call.tool, args)
                                
                                # Отправляем чанк с вызовом
                                yield StreamChunk(
                                    content=current_content,
                                    delta="",
                                    tool_call=tool_call,
                                    is_complete=False
                                )
                                
                                # Выполняем инструмент
                                result = await self.tool_executor(
                                    current_tool["name"],
                                    **args
                                )
                                logger.info("Tool execution result: %s", result)
                                
                                # Отправляем результат
                                yield StreamChunk(
                                    content=current_content,
                                    delta="",
                                    tool_call=tool_call,
                                    tool_result=str(result),
                                    is_complete=False
                                )
                                
                                current_tool = None
                                
                            except json.JSONDecodeError as e:
                                logger.debug("JSON not complete yet: %s", e)  # Понижаем уровень до debug
                                # Продолжаем собирать чанки
                                pass
                
                # Проверяем завершение
                if chunk.choices[0].finish_reason is not None:
                    logger.info("Stream completed with reason: %s", chunk.choices[0].finish_reason)
                    yield StreamChunk(
                        content=current_content,
                        delta="",
                        is_complete=True
                    )
                    break
                    
        except Exception as e:
            logger.error("Stream generation failed: %s", str(e))
            logger.exception("Full traceback:")
            yield StreamChunk(
                content=f"Error: {str(e)}",
                delta=f"Error: {str(e)}",
                is_complete=True
            )

    async def _generate_regular_response(
        self,
        request_params: Dict[str, Any]
    ) -> LLMResponse:
        """Генерирует обычный (не потоковый) ответ"""
        current_messages = request_params["messages"].copy()
        tool_messages = []
        final_content = ""
        
        while True:
            try:
                response = await self.client.chat.completions.create(**request_params)
                message = response.choices[0].message
                
                # Добавляем сообщение от ассистента
                message_dict = message.model_dump()
                current_messages.append(message_dict)
                tool_messages.append(message_dict)
                
                # Проверяем наличие tool_calls
                tool_calls = message_dict.get('tool_calls') or []
                if tool_calls:  # Если есть tool_calls
                    # Обрабатываем инструменты
                    for tool_call in tool_calls:
                        # Получаем имя и аргументы инструмента
                        tool_name = tool_call['function']['name']
                        tool_args = tool_call['function']['arguments']
                        
                        if self._is_duplicate_tool_call({"name": tool_name, "arguments": tool_args}, current_messages):
                            continue
                            
                        try:
                            args = json.loads(tool_args)
                            tool_call_obj = ToolCall(
                                tool=tool_name,
                                params=args
                            )
                            
                            # Выполняем инструмент
                            result = await self.tool_executor(
                                tool_name,
                                **args
                            )
                            
                            # Добавляем результат
                            tool_message = {
                                "role": "tool",
                                "content": json.dumps({"answer": str(result)}),
                                "tool_call_id": tool_call.get('id', 'unknown')
                            }
                            
                            current_messages.append(tool_message)
                            tool_messages.append(tool_message)
                            
                        except json.JSONDecodeError as e:
                            logger.error("Failed to parse tool arguments: %s", e)
                            continue
                            
                    request_params["messages"] = current_messages
                    continue
                
                # Сохраняем только последний контент как финальный
                final_content = message_dict.get('content', '')
                
                # Собираем вызовы инструментов
                tool_calls_list = []
                for msg in tool_messages:
                    msg_tool_calls = msg.get('tool_calls') or []
                    for call in msg_tool_calls:
                        tool_calls_list.append(ToolCall(
                            tool=call['function']['name'],
                            params=json.loads(call['function']['arguments']),
                            id=call.get('id', 'unknown'),
                            index=call.get('index', 0)
                        ))
                
                return LLMResponse(
                    content=final_content,  # Используем только финальный контент
                    tool_calls=tool_calls_list,
                    tool_messages=[]  # Не передаем tool_messages, так как они уже в content
                )
                
            except Exception as e:
                logger.error("API request failed: %s", str(e))
                logger.exception("Full traceback:")
                raise RuntimeError(f"API request failed: {str(e)}")

    async def close(self):
        """Закрывает соединение с API"""
        if hasattr(self.client, 'close'):
            await self.client.close()
        elif hasattr(self.client.http_client, 'aclose'):
            await self.client.http_client.aclose()
