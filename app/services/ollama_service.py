"""
Ollama Local LLM Client Service.
Provides robust HTTP communication with local Ollama instance (default: http://localhost:11434).
Handles health probing, model availability checks, timeouts, and JSON-constrained completions.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import httpx

from pipeline.config import config

logger = logging.getLogger("flightpulse.ai.ollama")


class OllamaClientError(Exception):
    """Base exception for Ollama client failures."""
    pass


class OllamaConnectionError(OllamaClientError):
    """Raised when Ollama server is offline or unreachable."""
    pass


class OllamaTimeoutError(OllamaClientError):
    """Raised when Ollama generation exceeds timeout threshold."""
    pass


class OllamaResponseError(OllamaClientError):
    """Raised when Ollama returns non-200 or invalid response payload."""
    pass


class OllamaClient:
    """
    HTTP client for local Ollama daemon.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        timeout_sec: Optional[float] = None,
    ):
        self.base_url = (base_url or config.ollama.base_url).rstrip("/")
        self.model = model or config.ollama.model
        self.timeout = timeout if timeout is not None else (timeout_sec if timeout_sec is not None else config.ollama.timeout_sec)

    def is_available(self) -> bool:
        """
        Check if the local Ollama HTTP service is alive.
        """
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def get_installed_models(self) -> List[str]:
        """
        Retrieve list of locally downloaded models from Ollama.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning("Failed to retrieve installed Ollama models: %s", e)
        return []

    def resolve_active_model(self) -> str:
        """
        Resolve the active model. If configured model is installed, use it;
        otherwise fallback to first available model or default.
        """
        installed = self.get_installed_models()
        if not installed:
            return self.model

        # Exact or prefix match
        if self.model in installed:
            return self.model
        for m in installed:
            if m.startswith(self.model.split(":")[0]):
                return m

        # If configured model not present, fallback to first installed
        logger.info("Configured model '%s' not in installed %s; using '%s'", self.model, installed, installed[0])
        return installed[0]

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        format_json: bool = True,
        model_override: Optional[str] = None,
    ) -> str:
        """
        Send a generation request to the local Ollama instance.
        
        Args:
            prompt: User/context prompt text
            system_prompt: Optional system instruction prompt
            format_json: Whether to constrain response to valid JSON format
            model_override: Optional override for model name
            
        Returns:
            The raw text response from Ollama.
        """
        target_model = model_override or self.resolve_active_model()
        url = f"{self.base_url}/api/generate"

        payload: Dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for deterministic adherence to evidence
                "top_p": 0.9,
                "num_ctx": 2048,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if format_json:
            payload["format"] = "json"

        logger.info(
            "Calling local Ollama at %s with model '%s' (timeout: %.1fs, format_json: %s)",
            url,
            target_model,
            self.timeout,
            format_json,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)

            if response.status_code != 200:
                raise OllamaResponseError(
                    f"Ollama returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            raw_text = data.get("response", "")
            return raw_text.strip()

        except httpx.ConnectError as exc:
            logger.warning("Cannot connect to local Ollama daemon at %s: %s", self.base_url, exc)
            raise OllamaConnectionError(f"Ollama service unreachable at {self.base_url}") from exc

        except httpx.TimeoutException as exc:
            logger.warning("Ollama generation with '%s' timed out after %.1fs", target_model, self.timeout)
            # Fast GPU fallback: if llama3 timed out, attempt lightweight tinyllama if installed
            if target_model != "tinyllama:latest":
                try:
                    installed = self.get_installed_models()
                    if "tinyllama:latest" in installed:
                        logger.info("Attempting fast GPU completion with 'tinyllama:latest' (30s timeout)...")
                        payload["model"] = "tinyllama:latest"
                        with httpx.Client(timeout=30.0) as client:
                            fb_resp = client.post(url, json=payload)
                        if fb_resp.status_code == 200:
                            fb_data = fb_resp.json()
                            fb_text = fb_data.get("response", "").strip()
                            if fb_text:
                                self.model = "tinyllama:latest"
                                return fb_text
                except Exception as fb_err:
                    logger.warning("Fast fallback to tinyllama failed: %s", fb_err)

            raise OllamaTimeoutError(f"Ollama request timed out after {self.timeout}s") from exc

        except httpx.HTTPError as exc:
            logger.error("HTTP error communicating with Ollama: %s", exc)
            raise OllamaResponseError(f"HTTP communication error: {exc}") from exc


# Global shared instance
ollama_client = OllamaClient()
