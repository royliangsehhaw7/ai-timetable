import os
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider


class LLMModelFactory:
    """
    Builds and returns a configured LLM model for use by agents.
    Provider and API keys are read from environment variables — never hardcoded.
    Switching providers requires only a .env change, no code changes.
    """

    def __init__(self, provider: str):
        self.provider = provider

    def get_model(self):
        if self.provider == "gemini":
            return GoogleModel(
                "gemini-2.5-flash",
                provider=GoogleProvider(
                    api_key=os.environ["GEMINI_API_KEY"]
                ),
                settings=GoogleModelSettings(
                    max_tokens=4096,
                    temperature=0.1
                )
            )

        if self.provider == "openrouter":
            return OpenAIChatModel(
                "nvidia/nemotron-super-49b-v1:free",
                provider=OpenAIProvider(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"]
                ),
                settings=OpenAIModelSettings(
                    max_tokens=4096,
                    temperature=0.1
                )
            )

        raise ValueError(f"Unknown provider: {self.provider}")