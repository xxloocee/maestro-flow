from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    key_env: str
    default_base_url: str
    model_hint: str


PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "openai": ProviderProfile(
        name="openai",
        key_env="OPENAI_API_KEY",
        default_base_url="",
        model_hint="gpt-5.4-mini",
    ),
    "openrouter": ProviderProfile(
        name="openrouter",
        key_env="OPENROUTER_API_KEY",
        default_base_url="https://openrouter.ai/api/v1",
        model_hint="openai/gpt-4.1-mini or anthropic/claude-sonnet-4",
    ),
    "deepseek": ProviderProfile(
        name="deepseek",
        key_env="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com/v1",
        model_hint="deepseek-chat",
    ),
    "moonshot": ProviderProfile(
        name="moonshot",
        key_env="MOONSHOT_API_KEY",
        default_base_url="https://api.moonshot.cn/v1",
        model_hint="moonshot-v1-8k",
    ),
    "qwen": ProviderProfile(
        name="qwen",
        key_env="DASHSCOPE_API_KEY",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_hint="qwen-max",
    ),
    "siliconflow": ProviderProfile(
        name="siliconflow",
        key_env="SILICONFLOW_API_KEY",
        default_base_url="https://api.siliconflow.cn/v1",
        model_hint="Qwen/Qwen3-Coder-480B-A35B-Instruct",
    ),
    "volcengine": ProviderProfile(
        name="volcengine",
        key_env="ARK_API_KEY",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        model_hint="doubao-seed-1-6-thinking-250715",
    ),
    "custom": ProviderProfile(
        name="custom",
        key_env="MAESTRO_API_KEY",
        default_base_url="",
        model_hint="Any model on your OpenAI-compatible endpoint",
    ),
}


def supported_providers() -> list[ProviderProfile]:
    return [PROVIDER_PROFILES[k] for k in sorted(PROVIDER_PROFILES.keys())]


def resolve_provider(
    provider: str | None = None,
) -> tuple[ProviderProfile, str, str, dict[str, str]]:
    selected = (provider or os.getenv("MAESTRO_PROVIDER") or "openai").strip().lower()
    if selected not in PROVIDER_PROFILES:
        allowed = ", ".join(sorted(PROVIDER_PROFILES.keys()))
        raise RuntimeError(f"Unknown provider '{selected}'. Supported: {allowed}")

    profile = PROVIDER_PROFILES[selected]
    api_key = os.getenv("MAESTRO_API_KEY") or os.getenv(profile.key_env)
    if not api_key:
        raise RuntimeError(
            f"API key is missing. Set MAESTRO_API_KEY or {profile.key_env} for provider '{selected}'."
        )

    base_url = os.getenv("MAESTRO_BASE_URL") or profile.default_base_url
    headers: dict[str, str] = {}
    if profile.name == "openrouter":
        referer = os.getenv("OPENROUTER_HTTP_REFERER")
        title = os.getenv("OPENROUTER_APP_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

    return profile, api_key, base_url, headers
