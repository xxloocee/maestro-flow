from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from maestro_flow.config import AgentConfig
from maestro_flow.prompting import load_prompt_spec
from maestro_flow.providers import resolve_provider


class LLMClient:
    def __init__(self, *, repo_root: Path, model: str, mock: bool = False):
        self.repo_root = repo_root
        self.model = model
        self.mock = mock
        self._client: OpenAI | None = None

        if not mock:
            _, api_key, base_url, headers = resolve_provider()
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            if headers:
                client_kwargs["default_headers"] = headers
            self._client = OpenAI(**client_kwargs)

    def complete_json(
        self,
        *,
        stage: str,
        agent: AgentConfig,
        schema: type[BaseModel],
        requirement: str,
        context: dict[str, Any],
        prompt_text: str = "",
    ) -> BaseModel:
        if self.mock:
            from maestro_flow.mock_data import mock_stage_output

            return mock_stage_output(stage, requirement)

        prompt = prompt_text or load_prompt_spec(self.repo_root, agent.prompt_file).content
        user_payload = {
            "requirement": requirement,
            "stage": stage,
            "context": context,
            "output_schema": schema.model_json_schema(),
            "instruction": "Return strict JSON matching output_schema.",
        }

        response = self._client.responses.create(
            model=self.model,
            temperature=agent.temperature,
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )

        text = self._extract_output_text(response)
        parsed = self._safe_json_parse(text)
        return schema.model_validate(parsed)

    @staticmethod
    def _safe_json_parse(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        return json.loads(text)

    @staticmethod
    def _extract_output_text(response) -> str:
        if getattr(response, "output_text", None):
            return response.output_text

        output = []
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    output.append(content.text)
        if not output:
            raise RuntimeError("Model returned no text output")
        return "\n".join(output)

