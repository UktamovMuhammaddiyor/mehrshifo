import json


class LLMClient:
    """Provider-agnostic interface. complete() returns a dict matching the schema."""

    def complete(self, system: str, messages: list, schema: dict) -> dict:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self, model: str, temperature: float = 0.3, max_output_tokens: int = 500):
        from openai import OpenAI
        from ..creditionals import OPENAI_API_KEY
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    def complete(self, system: str, messages: list, schema: dict) -> dict:
        from .schema import coerce_response
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
            messages=[{"role": "system", "content": system}] + messages,
            response_format={"type": "json_schema", "json_schema": schema},
        )
        return coerce_response(json.loads(resp.choices[0].message.content))
