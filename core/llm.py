"""Client LLM OpenAI-compatible (configurable à chaud).

Couvre OpenAI, DeepSeek, Mistral, Groq, vLLM et Ollama (`/v1/chat/completions`).
La configuration est persistée dans `data/llm_config.json` et modifiable depuis
la page « Paramètres IA ».
"""
from __future__ import annotations

import json
import os
from typing import Dict, Iterator, List, Optional

import httpx

import config


class LLMError(RuntimeError):
    """Le LLM est injoignable ou a renvoyé une erreur."""


def load_config() -> Dict[str, str]:
    if not os.path.exists(config.LLM_CONFIG_PATH):
        return {}
    try:
        with open(config.LLM_CONFIG_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(cfg: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(config.LLM_CONFIG_PATH), exist_ok=True)
    tmp = config.LLM_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, config.LLM_CONFIG_PATH)


def is_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("base_url") and cfg.get("model"))


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "") -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Génération non-streaming : retourne le texte complet."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        try:
            with httpx.Client(timeout=300.0) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM injoignable ({self.base_url}) : {exc}") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Réponse LLM inattendue : {data}") from exc

    def stream(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> Iterator[str]:
        """Génération streaming : produit des fragments de texte."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        try:
            with httpx.Client(timeout=300.0) as client:
                with client.stream("POST", url, json=payload, headers=self._headers()) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        try:
                            delta = obj["choices"][0]["delta"].get("content")
                        except (KeyError, IndexError):
                            continue
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM injoignable ({self.base_url}) : {exc}") from exc


def get_client() -> Optional[LLMClient]:
    cfg = load_config()
    if not cfg.get("base_url") or not cfg.get("model"):
        return None
    return LLMClient(cfg["base_url"], cfg["model"], cfg.get("api_key", ""))
