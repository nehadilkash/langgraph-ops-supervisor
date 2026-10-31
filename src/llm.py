"""Shared configuration for the chat model."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


def get_chat_model() -> ChatOpenAI:
    """Build an Ollama or OpenAI-compatible chat model from environment settings."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

    if provider == "ollama":
        return ChatOpenAI(
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
            temperature=0,
        )
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "replace-me":
            raise ValueError(
                "LLM_PROVIDER=openai requires a valid OPENAI_API_KEY in your "
                "environment or .env file."
            )
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=api_key,
            temperature=0,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER {provider!r}; choose 'ollama' or 'openai'."
    )
