"""OpenAI LLM сервис"""

import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator, List, TYPE_CHECKING, Union
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .interfaces import BaseLLM, ToolSchema, LLMResponse
from .tool_call_manager import ToolCallManager, ToolCallBuilder
from ..core.messages import IOMessage

if TYPE_CHECKING:
    from ..core.context import RequestContext

logger = logging.getLogger(__name__)

# Константы для провайдеров
OPENAI = "openai"
DEEPSEEK = "deepseek"
OLLAMA = "ollama"
PROXYAPI = "proxyapi"


class OpenAIProvider:
    """Конфигурация провайдера OpenAI-совместимого API"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        provider: str = OPENAI,
        max_tokens: Optional[int] = None
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.provider = provider
        self.max_tokens = max_tokens


class OpenAIService(BaseLLM):
    """Сервис для работы с OpenAI API и совместимыми провайдерами"""

    def __init__(self, provider: OpenAIProvider):
        self.provider = provider
        self.max_iterations = 5  # Максимальное количество итераций

        # Для Ollama не требуется API ключ
        if provider.provider == OLLAMA:
            api_key = "ollama"
            logger.info(f"Initialized provider '{provider.provider}' without API key.")
        else:
            if not provider.api_key:
                logger.error(f"API key must be provided for provider '{provider.provider}'.")
                raise ValueError(f"API key must be provided for provider '{provider.provider}'")
            api_key = provider.api_key
            logger.info(f"Initialized provider '{provider.provider}' with provided API key.")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider.base_url
        )

    def set_tool_executor(self, executor):
        """Устанавливает функцию для выполнения инструментов"""
        self.tool_executor = executor

    async def _generate_regular_response(self, request_params: Dict[str, Any]) -> IOMessage:
        """Генерирует обычный (не потоковый) ответ"""
        try:
            context = request_params.pop("context", None)
            api_params = request_params.copy()

            response = await self.client.chat.completions.create(**api_params)

            tool_calls = []
            if response.choices[0].message.tool_calls:
                for call in response.choices[0].message.tool_calls:
                    tool_name = call.function.name
                    tool_params = json.loads(call.function.arguments)
                    result = await self.tool_executor(tool_name, tool_params, context)
                    tool_calls.append({
                        "call": call,
                        "result": {
                            "content": result
                        }
                    })

                messages = api_params["messages"].copy()
                messages.append({
                    "role": "assistant",
                    "content": response.choices[0].message.content,
                    "tool_calls": [tc["call"] for tc in tool_calls]
                })

                for tc in tool_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["call"].id,
                        "content": tc["result"]["content"]
                    })

                api_params["messages"] = messages
                final_response = await self.client.chat.completions.create(**api_params)

                return IOMessage(
                    type="text",
                    content=final_response.choices[0].message.content,
                    source="openai",
                    tool_calls=tool_calls,
                    context=context
                )

            return IOMessage(
                type="text",
                content=response.choices[0].message.content,
                source="openai",
                tool_calls=tool_calls,
                context=context
            )

        except Exception as e:
            logger.error("API request failed", exc_info=True)
            raise RuntimeError(f"API request failed: {str(e)}")

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, AsyncGenerator[IOMessage, None]]:
        """Генерирует ответ, при необходимости выполняя инструменты"""
        logger.debug("OpenAIService.generate_response called with stream=%s", stream)

        request_params = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        logger.debug("Initial request params: %s", request_params)

        if self.provider.max_tokens is not None:
            request_params["max_tokens"] = self.provider.max_tokens
            logger.debug("Added max_tokens=%d", self.provider.max_tokens)

        if self.provider.provider == OLLAMA and "max_tokens" not in request_params:
            request_params["max_tokens"] = 1000  # Разумное ограничение по умолчанию
            logger.debug("Added default max_tokens=1000 for ProxyAPI")

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            logger.debug("Added %d tools and tool_choice=%s", len(tools), request_params["tool_choice"])

        request_params["temperature"] = temperature
        logger.debug("Final request params: %s", request_params)

        if stream:
            logger.debug("Starting stream response generation")
            return self._generate_stream_response(request_params)
        else:
            logger.debug("Starting regular response generation")
            return await self._generate_regular_response(request_params)

    async def close(self):
        """Закрывает соединение с API"""
        if hasattr(self.client, 'close'):
            await self.client.close()
        elif hasattr(self.client.http_client, 'aclose'):
            await self.client.http_client.aclose()

    async def _create_stream_chunk(
        self,
        content: str,
        delta: Optional[str] = None,
        tool_call: Any = None,
        tool_result: Any = None,
        error: Optional[str] = None,
        is_complete: bool = False,
        context: Any = None
    ) -> IOMessage:
        """Создает чанк для стриминга"""
        logger.debug(
            f"Creating stream chunk: content='{content}', delta='{delta}', tool_call={tool_call}, "
            f"tool_result={tool_result}, error={error}, is_complete={is_complete}"
        )

        metadata = {"is_complete": is_complete, "delta": delta}
        if error:
            metadata["error"] = error

        tool_calls = []
        if tool_call:
            tool_calls.append({
                "call": tool_call,
                "result": tool_result
            })

        chunk = IOMessage(
            type="stream_chunk",
            content=content,
            metadata=metadata,
            source="openai",
            tool_calls=tool_calls,
            context=context
        )
        logger.debug(f"Created chunk: {chunk}")
        return chunk

    async def _generate_stream_response(self, request_params: Dict[str, Any]) -> AsyncGenerator[IOMessage, None]:
        """Генерирует потоковый ответ с поддержкой инструментов"""
        current_content = ""
        current_tool_builder = None
        context = request_params.pop("context", None)
        api_params = request_params.copy()
        messages = api_params.get("messages", [])

        tool_manager = ToolCallManager()
        if hasattr(self, 'tool_executor'):
            tool_manager.set_tool_executor(self.tool_executor)
        if context:
            tool_manager.set_context(context)

        try:
            # Убираем параметр stream из запроса, он передается явно
            api_params.pop("stream", None)
            stream = await self.client.chat.completions.create(**api_params, stream=True)
            logger.debug("Получен потоковый ответ от API")
        except Exception as e:
            logger.error(f"Stream request failed: {e}", exc_info=True)
            error_chunk = await self._create_stream_chunk(
                content="Извините, произошла ошибка при обработке запроса.",
                error=str(e),
                context=context
            )
            yield error_chunk
            return

        async for chunk in stream:
            try:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = getattr(choice, 'delta', None)
                if delta is None:
                    continue

                finish_reason = getattr(choice, 'finish_reason', None)
                if finish_reason:
                    final_chunk = await self._create_stream_chunk(
                        content=current_content,
                        is_complete=True,
                        context=context
                    )
                    logger.debug("Финальный чанк отправлен по finish_reason")
                    yield final_chunk
                    continue

                # Обработка контента
                content_delta = getattr(delta, 'content', None)
                if content_delta:
                    current_content += content_delta
                    content_chunk = await self._create_stream_chunk(
                        content=current_content,
                        delta=content_delta,
                        context=context
                    )
                    logger.debug("Отправляется чанк с контентом")
                    yield content_chunk

                # Обработка инструментов (tool_calls)
                tool_calls_delta = getattr(delta, 'tool_calls', None)
                if tool_calls_delta:
                    if current_tool_builder is None:
                        current_tool_builder = ToolCallBuilder()
                        logger.debug("Создан новый ToolCallBuilder")
                    for tool_call_delta in tool_calls_delta:
                        current_tool_builder.add_chunk(tool_call_delta)
                        logger.debug("Добавлен чанк в ToolCallBuilder")
                    if current_tool_builder.can_build():
                        processed_call = current_tool_builder.build()
                        logger.debug(f"Собран tool call: {processed_call}")
                        results = await tool_manager.process_tool_calls([processed_call])
                        logger.debug(f"Получены результаты инструментов: {results}")
                        if results and results[0].result:
                            tool_call_id = (
                                processed_call["id"]
                                if isinstance(processed_call, dict)
                                else processed_call.id
                            )
                            tool_chunk = await self._create_stream_chunk(
                                content=current_content,
                                tool_call=processed_call,
                                tool_result=results[0].result,
                                context=context
                            )
                            logger.debug("Отправляется чанк с результатом инструмента")
                            yield tool_chunk
                            messages.append({
                                "role": "assistant",
                                "content": current_content,
                                "tool_calls": [processed_call]
                            })
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": results[0].result["content"]
                            })
                            api_params["messages"] = messages
                            logger.debug("Обновлены сообщения для следующего запроса")
                            
                            # Сброс только builder
                            current_tool_builder = None
                            # НЕ сбрасываем current_content
                            
                            # Делаем новый запрос с результатами tool calls
                            logger.debug("Отправляем новый запрос к LLM с результатами инструментов")
                            try:
                                new_stream = await self.client.chat.completions.create(
                                    **api_params,
                                    stream=True
                                )
                                async for new_chunk in new_stream:
                                    if not new_chunk.choices:
                                        continue
                                        
                                    choice = new_chunk.choices[0]
                                    delta = getattr(choice, 'delta', None)
                                    if delta is None:
                                        continue
                                        
                                    content_delta = getattr(delta, 'content', None)
                                    if content_delta:
                                        current_content += content_delta  # Добавляем к существующему контенту
                                        content_chunk = await self._create_stream_chunk(
                                            content=current_content,
                                            delta=content_delta,
                                            context=context
                                        )
                                        logger.debug("Отправляется чанк с ответом на результаты инструментов")
                                        yield content_chunk
                                        
                                    finish_reason = getattr(choice, 'finish_reason', None)
                                    if finish_reason:
                                        final_chunk = await self._create_stream_chunk(
                                            content=current_content,
                                            is_complete=True,
                                            context=context
                                        )
                                        logger.debug("Финальный чанк отправлен после обработки инструментов")
                                        yield final_chunk
                                        break
                                        
                            except Exception as e:
                                logger.error(f"Error in follow-up request: {e}", exc_info=True)
                                error_chunk = await self._create_stream_chunk(
                                    content="Извините, произошла ошибка при обработке результатов инструментов.",
                                    error=str(e),
                                    context=context
                                )
                                yield error_chunk
                                
            except Exception as e:
                logger.error(f"Error processing chunk: {e}", exc_info=True)
                continue

        if current_content:
            final_chunk = await self._create_stream_chunk(
                content=current_content,
                is_complete=True,
                context=context
            )
            logger.debug("Стрим завершен, отправляется финальный чанк")
            yield final_chunk