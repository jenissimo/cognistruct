import json
from typing import Any, Dict, List, Optional

import aiohttp
from pydantic import BaseModel

from llm.interfaces import BaseLLM, LLMResponse, ToolSchema, ToolCall
from utils.logging import setup_logger


logger = setup_logger(__name__)


class DeepSeekConfig(BaseModel):
    """Конфигурация для DeepSeek API"""
    api_key: str
    model: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com/v1/chat/completions"


class DeepSeekLLM(BaseLLM):
    """Реализация для работы с DeepSeek API"""

    def __init__(self, config: DeepSeekConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.config.api_key}"}
            )

    def _convert_tool_schema(self, tools: List[ToolSchema]) -> List[Dict[str, Any]]:
        """Конвертирует наши схемы инструментов в формат DeepSeek"""
        converted = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            param.name: {
                                "type": param.type,
                                "description": param.description
                            }
                            for param in tool.parameters
                        },
                        "required": [
                            param.name
                            for param in tool.parameters
                            if param.required
                        ]
                    }
                }
            }
            for tool in tools
        ]
        logger.debug("Converted tools schema:\n%s", 
                    json.dumps(converted, indent=2, ensure_ascii=False))
        return converted

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSchema]] = None,
        temperature: float = 0.7,
        response_format: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        await self._ensure_session()
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = self._convert_tool_schema(tools)
            
        if response_format:
            payload["response_format"] = {
                "type": response_format
            }
            logger.debug("Using response format: %s", response_format)
            
        payload.update(kwargs)
            
        logger.debug("Sending request to DeepSeek API:\n%s",
                    json.dumps(payload, indent=2, ensure_ascii=False))
            
        async with self.session.post(
            self.config.api_base,
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error("DeepSeek API error (%d):\n%s", 
                           response.status, error_text)
                raise RuntimeError(f"DeepSeek API error: {error_text}")
                
            data = await response.json()
            logger.debug("Received response from DeepSeek API:\n%s",
                        json.dumps(data, indent=2, ensure_ascii=False))
            
            # Извлекаем ответ из результата
            assistant_message = data["choices"][0]["message"]
            content = assistant_message.get("content", "")
            finish_reason = data["choices"][0].get("finish_reason")
            
            # Проверяем наличие вызова функции
            tool_calls = None
            message_tool_calls = assistant_message.get("tool_calls", [])
            
            if message_tool_calls:
                logger.info("Detected tool calls:\n%s",
                           json.dumps(message_tool_calls, indent=2, ensure_ascii=False))
                tool_calls = []
                for call in message_tool_calls:
                    if call["type"] == "function":
                        tool_calls.append(ToolCall(
                            tool=call["function"]["name"],
                            params=json.loads(call["function"]["arguments"]),
                            id=call["id"],
                            index=call["index"]
                        ))
                
                # Если контент пустой и есть вызовы инструментов, 
                # добавляем информацию об этом в контент
                if not content and finish_reason == "tool_calls":
                    content = f"Использую инструмент {tool_calls[0].tool}"
            
            return LLMResponse(
                content=content,
                tool_calls=tool_calls
            )

    async def close(self):
        """Закрывает сессию"""
        if self.session:
            await self.session.close()
            self.session = None 