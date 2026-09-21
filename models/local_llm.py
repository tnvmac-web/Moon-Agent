"""
Local LLM wrapper supporting multiple backends:
- Ollama (recommended for local models)
- OpenAI-compatible API
- NVIDIA NIM (cloud inference)
- Mock mode for testing
"""

import os
from abc import ABC, abstractmethod

import requests


class LocalLLM(ABC):
    """Abstract base class for local LLM backends"""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        pass


class OllamaLLM(LocalLLM):
    """Ollama local model backend"""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api"

    def _check_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": kwargs,
        }
        response = requests.post(f"{self.api_url}/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": kwargs,
        }
        response = requests.post(f"{self.api_url}/chat", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")

    def list_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.api_url}/tags", timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []


class OpenAICompatibleLLM(LocalLLM):
    """OpenAI-compatible API backend (LM Studio, vLLM, etc.)"""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "not-needed",
        model: str = "local-model",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class NVIDIANIM_LLM(LocalLLM):
    """NVIDIA NIM (NVIDIA Inference Microservices) cloud backend"""

    def __init__(
        self,
        model: str = "meta/llama-3.1-8b-instruct",
        api_key: str = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY environment variable required for NVIDIA NIM backend")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _check_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
            "stream": False,
        }
        # NVIDIA NIM uses OpenAI-compatible chat/completions endpoint
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def list_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=10)
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        except Exception:
            return []


class MockLLM(LocalLLM):
    """Mock LLM for testing without a model server"""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.call_log = []

    def generate(self, prompt: str, **kwargs) -> str:
        self.call_log.append({"type": "generate", "prompt": prompt, "kwargs": kwargs})
        return self.responses.get(prompt, f"[Mock response to: {prompt[:50]}...]")

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        self.call_log.append({"type": "chat", "messages": messages, "kwargs": kwargs})
        last_msg = messages[-1]["content"] if messages else ""
        return self.responses.get(last_msg, f"[Mock response to: {last_msg[:50]}...]")


def create_llm(backend: str = "auto", **kwargs) -> LocalLLM:
    """Factory function to create LLM instance"""

    if backend == "ollama" or (backend == "auto" and _try_ollama()):
        return OllamaLLM(**kwargs)

    if backend == "openai-compatible" or (backend == "auto" and _try_openai_compatible()):
        return OpenAICompatibleLLM(**kwargs)

    if backend == "nvidia-nim" or (backend == "auto" and _try_nvidia_nim()):
        return NVIDIANIM_LLM(**kwargs)

    if backend == "mock":
        return MockLLM(**kwargs)

    # Default to mock if nothing else works
    return MockLLM()


def _try_ollama() -> bool:
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def _try_openai_compatible() -> bool:
    try:
        response = requests.get("http://localhost:1234/v1/models", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def _try_nvidia_nim() -> bool:
    """Check if NVIDIA API key is available"""
    return bool(os.environ.get("NVIDIA_API_KEY"))
