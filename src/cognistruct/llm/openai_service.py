import json
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass
import asyncio

from openai import AsyncOpenAI
from pydantic import BaseModel

from cognistruct.llm.interfaces import BaseLLM, LLMResponse, ToolSchema, StreamChunk, ToolCall
from cognistruct.utils.logging import setup_logger
from cognistruct.utils.schema_converter import convert_tool_schema

logger = setup_logger(__name__)


@dataclass
class OpenAIProvider:
    """Конфигурация провайдера OpenAI API"""
    name: str
    model: str
    api_base: str
    api_key: Optional[str] = None  # Может быть None для некоторых провайдеров
    temperature: float = 0.7  # Добавляем температуру по умолчанию
    max_tokens: Optional[int] = None  # Максимальное количество токенов
    is_proxy: bool = False  # Флаг использования ProxyAPI


# Предопределенные провайдеры
OPENAI = OpenAIProvider(
    name="openai",
    model="gpt-4o",
    api_base="https://api.openai.com/v1",
    api_key="",  # Заполняется из конфига
    temperature=0.7,
    max_tokens=None,
    is_proxy=False
)

PROXYAPI = OpenAIProvider(
    name="proxyapi",
    model="gpt-4o",
    api_base="https://api.proxyapi.ru/openai/v1",
    api_key="",  # Заполняется из конфига
    temperature=0.7,
    max_tokens=None,
    is_proxy=True
)

DEEPSEEK = OpenAIProvider(
    name="deepseek",
    model="deepseek-chat",
    api_base="https://api.deepseek.com/v1",
    api_key="",  # Заполняется из конфига
    temperature=0.7,
    max_tokens=None,
    is_proxy=False
)

OLLAMA = OpenAIProvider(
    name="ollama",
    model="",  # Заполняется пользователем
    api_base="http://localhost:11434/v1",
    api_key=None,  # Не требуется для локального Ollama
    temperature=0.7,
    max_tokens=None,
    is_proxy=False
)


class OpenAIService(BaseLLM):
    """Реализация для работы с OpenAI-совместимыми API"""

    def __init__(self, provider: OpenAIProvider):
        self.provider = provider
        self.tool_executor = None
        self._tool_call_counter = 0  # Счетчик для генерации уникальных ID
        self.max_iterations = 5  # Максимальное количество итераций
        
        # Для Ollama не требуется API ключ
        if provider.name == "ollama":
            api_key = "ollama"
            logger.info(f"Initialized provider '{provider.name}' without API key.")
        else:
            if not provider.api_key:
                logger.error(f"API key must be provided for provider '{provider.name}'.")
                raise ValueError(f"API key must be provided for provider '{provider.name}'")
            
            # OpenAI клиент сам добавляет Bearer к ключу
            api_key = provider.api_key
                
            logger.info(f"Initialized provider '{provider.name}' with provided API key.")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider.api_base
        )

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

    def _generate_tool_call_id(self) -> str:
        """Генерирует уникальный ID для вызова инструмента"""
        self._tool_call_counter += 1
        return f"call_{self._tool_call_counter}"

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
            "stream": stream
        }

        # Добавляем user_id в метаданные из kwargs
        if "response_format" in kwargs:
            request_params["response_format"] = kwargs["response_format"]

        # Добавляем max_tokens если он указан в провайдере
        if self.provider.max_tokens is not None:
            request_params["max_tokens"] = self.provider.max_tokens

        # Для ProxyAPI всегда добавляем max_tokens чтобы контролировать стоимость
        if self.provider.is_proxy and "max_tokens" not in request_params:
            request_params["max_tokens"] = 1000  # Разумное ограничение по умолчанию

        if tools:
            request_params["tools"] = convert_tool_schema(tools)
            # Используем "none" по умолчанию, чтобы модель не использовала инструменты без необходимости
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        print("=== available tools ===")
        print(request_params["tools"])

        if stream:
            return self._generate_stream_response(request_params)
        else:
            return await self._generate_regular_response(request_params)

    async def _generate_stream_response(
        self, 
        request_params: Dict[str, Any]
    ) -> AsyncGenerator[StreamChunk, None]:
            """Генерирует потоковый ответ с обработкой вызовов инструментов"""
            try:
                logger.info("Starting stream generation with params: %s", request_params)
                
                # Инициализируем список сообщений и счетчик итераций
                messages = request_params.get("messages", []).copy()
                iteration = 0
                used_tool_calls = set()  # Множество для отслеживания использованных вызовов
                
                while iteration < self.max_iterations:
                    iteration += 1
                    logger.info(f"Starting iteration {iteration}/{self.max_iterations}")
                    
                    # Обновляем параметры запроса с текущими сообщениями
                    current_request_params = request_params.copy()
                    current_request_params["messages"] = messages
                    current_request_params["temperature"] = self.provider.temperature

                    # Создаем потоковый запрос к LLM
                    stream = await self.client.chat.completions.create(**current_request_params)
                    
                    current_content = ""
                    current_tool = None
                    tool_executed = False
                    default_tool_id = self._generate_tool_call_id()

                    async for chunk in stream:
                        #logger.info("Received chunk: %s", chunk)
                        if len(chunk.choices) == 0:
                            logger.debug("Received empty choices in chunk, might be final chunk")
                            # Если это последний чанк и у нас есть накопленный контент
                            if current_content:
                                yield StreamChunk(
                                    content=current_content,
                                    delta="",
                                    is_complete=True
                                )
                            continue
                        delta = chunk.choices[0].delta
                        #logger.debug("Delta content: %s", getattr(delta, "content", None))
                        #logger.debug("Delta tool_calls: %s", getattr(delta, "tool_calls", None))
                        
                        # Обработка текстового контента
                        if hasattr(delta, "content") and delta.content:
                            current_content += delta.content
                            #logger.info("Yielding text chunk: %s", delta.content)
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
                                    "name": getattr(tool_call.function, "name", ""),
                                    "arguments": getattr(tool_call.function, "arguments", ""),
                                    "id": getattr(tool_call, "id", None) or default_tool_id  # Используем ID из стрима или запасной
                                }
                                logger.info("Started new tool call: %s", current_tool)
                            else:
                                # Обновляем поля если пришли новые значения
                                if getattr(tool_call.function, "name", ""):
                                    current_tool["name"] = tool_call.function.name
                                if getattr(tool_call.function, "arguments", ""):
                                    current_tool["arguments"] += tool_call.function.arguments
                                if getattr(tool_call, "id", None):  # Обновляем ID если пришел из стрима
                                    current_tool["id"] = tool_call.id
                                logger.info("Updated tool call: %s", current_tool)
                            
                            # Проверяем, что у нас есть имя и аргументы похожи на полный JSON
                            if current_tool["name"] and current_tool["arguments"]:
                                tool_key = f"{current_tool['name']}:{current_tool['arguments']}"
                                if tool_key in used_tool_calls:
                                    logger.warning(f"Skipping duplicate tool call: {tool_key}")
                                    current_tool = None
                                    continue
                                
                                args_str = current_tool["arguments"].strip()
                                if args_str.startswith("{") and args_str.endswith("}"):
                                    try:
                                        args = json.loads(args_str)
                                        used_tool_calls.add(tool_key)  # Добавляем в использованные
                                        tool_call_obj = ToolCall(
                                            tool=current_tool["name"],
                                            params=args,
                                            id=current_tool["id"]
                                        )
                                        
                                        # Отправляем информацию о полном вызове инструмента в стрим
                                        yield StreamChunk(
                                            content=current_content,
                                            delta="",
                                            tool_call=tool_call_obj,
                                            is_complete=False
                                        )
                                        
                                        logger.info("Executing tool: %s with args: %s", tool_call_obj.tool, args)
                                        
                                        # Выполняем инструмент
                                        result = await self.tool_executor(
                                            tool_call_obj.tool,
                                            **tool_call_obj.params
                                        )
                                        logger.info("Tool execution result: %s", result)
                                        
                                        # Добавляем сообщение от ассистента с вызовом инструмента
                                        assistant_message = {
                                            "role": "assistant",
                                            "content": None,
                                            "tool_calls": [
                                                {
                                                    "id": current_tool["id"],
                                                    "type": "function",
                                                    "function": {
                                                        "name": current_tool["name"],
                                                        "arguments": current_tool["arguments"]
                                                    }
                                                }
                                            ]
                                        }
                                        messages.append(assistant_message)

                                        # Добавляем результат вызова инструмента
                                        tool_message = {
                                            "role": "tool",
                                            "content": json.dumps({"answer": str(result)}),
                                            "tool_call_id": current_tool["id"]
                                        }
                                        messages.append(tool_message)
                                        
                                        # Отправляем только результат в стрим
                                        yield StreamChunk(
                                            content=current_content,
                                            delta="",
                                            tool_result=str(result),
                                            is_complete=False
                                        )
                                        
                                        # Сброс текущего инструмента
                                        current_tool = None
                                        tool_executed = True
                                        
                                        # Завершаем текущий поток, чтобы начать новый с обновленными сообщениями
                                        break
                                        
                                    except json.JSONDecodeError as e:
                                        logger.debug("JSON not complete yet: %s", e)
                                        # Продолжаем собирать чанки
                                        pass
                                
                    if not tool_executed:
                        # Если инструмент не был выполнен, значит генерация завершена
                        final_chunk = StreamChunk(
                            content=current_content,
                            delta="",
                            is_complete=True
                        )
                        logger.info("Stream completed")
                        yield final_chunk
                        break
                    elif iteration >= self.max_iterations:
                        # Если достигли максимума итераций
                        error_msg = f"Reached maximum number of iterations ({self.max_iterations})"
                        logger.warning(error_msg)
                        yield StreamChunk(
                            content=error_msg,
                            delta=error_msg,
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
        try:
            messages = request_params.get("messages", []).copy()
            tools = request_params.get("tools", [])
            response_format = request_params.get("response_format")
            used_tool_calls = set()  # Для отслеживания уже использованных инструментов
            tool_messages = []  # Сохраняем все сообщения связанные с инструментами
            
            while True:  # Цикл для обработки вызовов инструментов
                response = await self.client.chat.completions.create(**request_params)
                choice = response.choices[0]
                message = choice.message
                
                # Если есть вызовы инструментов
                if message.tool_calls:
                    current_tool_calls = []  # Сохраняем текущие вызовы
                    tool_responses = []  # Сохраняем ответы инструментов
                    
                    # Сначала добавляем сообщение ассистента с вызовами
                    assistant_message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            } for tc in message.tool_calls
                        ]
                    }
                    messages.append(assistant_message)
                    tool_messages.append(assistant_message)
                    
                    # Затем обрабатываем каждый вызов
                    for tool_call in message.tool_calls:
                        try:
                            # Получаем имя и аргументы инструмента
                            tool_name = tool_call.function.name
                            tool_args = tool_call.function.arguments
                            
                            # Проверяем на дубликат
                            tool_key = f"{tool_name}:{tool_args}"
                            if tool_key in used_tool_calls:
                                logger.warning(f"Skipping duplicate tool call: {tool_key}")
                                # Даже для пропущенных вызовов нужно добавить ответ
                                tool_responses.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": "Skipped duplicate tool call"
                                })
                                continue
                                
                            used_tool_calls.add(tool_key)
                            
                            # Создаем объект вызова для ответа
                            tool_call_obj = ToolCall(
                                tool=tool_name,
                                params=json.loads(tool_args)
                            )
                            current_tool_calls.append(tool_call_obj)
                            
                            # Выполняем инструмент
                            result = await self.tool_executor(
                                tool_call_obj.tool,
                                **tool_call_obj.params
                            )
                            
                            # Создаем сообщение с результатом в правильном формате
                            tool_response = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,  # Важно использовать именно id из вызова
                                "content": str(result)  # Результат должен быть строкой
                            }
                            tool_responses.append(tool_response)
                            tool_messages.append(tool_response)
                            
                        except Exception as e:
                            logger.error(f"Tool execution failed: {e}")
                            # Даже при ошибке добавляем сообщение с результатом
                            error_response = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": f"Error: {str(e)}"
                            }
                            tool_responses.append(error_response)
                            tool_messages.append(error_response)
                    
                    # Добавляем все ответы инструментов после сообщения ассистента
                    messages.extend(tool_responses)
                    
                    # Обновляем параметры запроса
                    request_params["messages"] = messages
                    continue
                
                # Проверяем формат ответа
                if response_format and response_format.get("type") == "json_object":
                    try:
                        content = json.loads(message.content)
                        return LLMResponse(
                            content=json.dumps(content, ensure_ascii=False),
                            finish_reason=choice.finish_reason,
                            tool_calls=current_tool_calls if 'current_tool_calls' in locals() else None,
                            tool_messages=tool_messages
                        )
                    except json.JSONDecodeError:
                        content = {
                            "response": message.content,
                            "is_last": False
                        }
                        return LLMResponse(
                            content=json.dumps(content, ensure_ascii=False),
                            finish_reason=choice.finish_reason,
                            tool_calls=current_tool_calls if 'current_tool_calls' in locals() else None,
                            tool_messages=tool_messages
                        )
                
                # Обычный текстовый ответ
                return LLMResponse(
                    content=message.content,
                    finish_reason=choice.finish_reason,
                    tool_calls=current_tool_calls if 'current_tool_calls' in locals() else None,
                    tool_messages=tool_messages
                )
                
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            logger.error("Full traceback:", exc_info=True)
            raise RuntimeError(f"API request failed: {str(e)}")

    async def close(self):
        """Закрывает соединение с API"""
        if hasattr(self.client, 'close'):
            await self.client.close()
        elif hasattr(self.client.http_client, 'aclose'):
            await self.client.http_client.aclose()
