from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class LLMConfig:
    base_url: str
    model: str
    timeout_s: int
    max_tokens: int
    temperature: float
    api_key: str = "not-needed"
    retry_attempts: int = 1
    retry_backoff_s: float = 0.25
    local_update_target: str = ""


class LLMClientError(RuntimeError):
    """Base class for classified LLM client failures."""


class LLMConnectionError(LLMClientError):
    """Raised when the endpoint cannot be reached."""


class LLMTimeoutError(LLMClientError):
    """Raised when the endpoint times out."""


class LLMHTTPError(LLMClientError):
    """Raised when the endpoint returns an HTTP error."""


class LLMResponseFormatError(LLMClientError):
    """Raised when the response body is malformed or incomplete."""


class LLMClient:
    """OpenAI-compatible chat completions adapter with basic validation and retry handling."""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        self.url = self.base_url + "/chat/completions"
        self.model = cfg.model.strip()

    def chat(self, system: str, user: str) -> str:
        model = self._resolve_model()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }

        attempts = max(1, self.cfg.retry_attempts)
        total_attempts = attempts + (1 if self._local_load_target() else 0)
        last_error: Exception | None = None
        loaded_after_no_models_error = False
        for attempt in range(1, total_attempts + 1):
            try:
                response = requests.post(self.url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
                response.raise_for_status()
                data = response.json()
                return self._extract_content(data)
            except requests.Timeout:
                last_error = LLMTimeoutError(f"LLM request timed out after {self.cfg.timeout_s}s")
            except requests.ConnectionError as exc:
                last_error = LLMConnectionError(f"LLM connection failed for {self.url}: {exc}")
            except requests.HTTPError as exc:
                if (
                    not loaded_after_no_models_error
                    and self._local_load_target()
                    and self._is_no_models_loaded_error(exc)
                ):
                    self._load_local_model()
                    loaded_after_no_models_error = True
                    self.model = "auto"
                    payload["model"] = self._resolve_model()
                    continue
                detail = self._format_http_error(exc)
                last_error = LLMHTTPError(f"LLM endpoint returned HTTP error: {detail}")
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = LLMResponseFormatError(f"LLM returned invalid JSON payload: {exc}")
            except LLMResponseFormatError as exc:
                last_error = exc

            if attempt < total_attempts:
                time.sleep(max(0.0, self.cfg.retry_backoff_s) * attempt)

        assert last_error is not None
        raise last_error

    def _resolve_model(self) -> str:
        requested = self.model.strip()
        if requested and requested.lower() not in {"auto", "local-model"}:
            if self._local_load_target():
                self._ensure_local_model_loaded_if_needed()
                model_ids = self._fetch_model_ids()
                if model_ids:
                    self.model = model_ids[0]
                    return self.model
            return requested

        model_ids = self._fetch_model_ids()
        if not model_ids and self._local_load_target():
            self._load_local_model()
            model_ids = self._fetch_model_ids()
        model_id = self._extract_first_model_id({"data": [{"id": item} for item in model_ids]})
        self.model = model_id
        return model_id

    def _fetch_model_ids(self) -> list[str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }
        try:
            response = requests.get(self.base_url + "/models", headers=headers, timeout=self.cfg.timeout_s)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise LLMTimeoutError(f"LLM model discovery timed out after {self.cfg.timeout_s}s") from exc
        except requests.ConnectionError as exc:
            raise LLMConnectionError(f"LLM model discovery failed for {self.base_url}/models: {exc}") from exc
        except requests.HTTPError as exc:
            detail = self._format_http_error(exc)
            raise LLMHTTPError(f"LLM model discovery returned HTTP error: {detail}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseFormatError(f"LLM model discovery returned invalid JSON payload: {exc}") from exc

        return self._extract_model_ids(data)

    def _ensure_local_model_loaded_if_needed(self) -> None:
        if not self._local_load_target():
            return
        model_ids = self._fetch_model_ids()
        if model_ids:
            return
        self._load_local_model()

    def _local_load_target(self) -> str:
        target = str(self.cfg.local_update_target or "").strip()
        return target.strip("/\\")

    def _load_local_model(self) -> None:
        target = self._local_load_target()
        if not target:
            return
        lms = shutil.which("lms")
        if not lms:
            raise LLMConnectionError(
                "LLM endpoint has no loaded models and the 'lms' CLI was not found in PATH. "
                "Open LM Studio and load a model, or install/enable the LM Studio CLI."
            )
        try:
            proc = subprocess.run(
                [lms, "load", target],
                capture_output=True,
                text=True,
                timeout=max(30, min(int(self.cfg.timeout_s or 120), 600)),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LLMConnectionError(f"LLM local model auto-load failed via lms load {target!r}: {exc}") from exc
        if proc.returncode != 0:
            detail = " ".join(((proc.stdout or "") + " " + (proc.stderr or "")).split())
            if len(detail) > 500:
                detail = detail[:497] + "..."
            raise LLMConnectionError(
                f"LLM local model auto-load failed via lms load {target!r} (exit={proc.returncode}): {detail or '-'}"
            )

    @staticmethod
    def _is_no_models_loaded_error(exc: requests.HTTPError) -> bool:
        response = getattr(exc, "response", None)
        body = str(getattr(response, "text", "") or "").lower()
        return "no models loaded" in body

    @staticmethod
    def _extract_model_ids(data: Any) -> list[str]:
        if not isinstance(data, dict):
            raise LLMResponseFormatError("LLM model discovery JSON root must be an object")
        models = data.get("data")
        if not isinstance(models, list):
            raise LLMResponseFormatError("LLM model discovery JSON must include a 'data' array")
        model_ids: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                raise LLMResponseFormatError("LLM model discovery item must be an object")
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                model_ids.append(model_id.strip())
        return model_ids

    @classmethod
    def _extract_first_model_id(cls, data: Any) -> str:
        model_ids = cls._extract_model_ids(data)
        if not model_ids:
            raise LLMResponseFormatError("LLM model discovery JSON must include a non-empty 'data' array")
        return model_ids[0]

    @staticmethod
    def _format_http_error(exc: requests.HTTPError) -> str:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        detail = f"status={status_code}" if status_code is not None else str(exc)
        body = ""
        if response is not None:
            body = str(getattr(response, "text", "") or "").strip()
        if body:
            compact = " ".join(body.split())
            if len(compact) > 500:
                compact = compact[:497] + "..."
            detail += f", body={compact}"
        return detail

    @staticmethod
    def _extract_content(data: Any) -> str:
        if not isinstance(data, dict):
            raise LLMResponseFormatError("LLM JSON root must be an object")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseFormatError("LLM JSON must include a non-empty 'choices' array")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise LLMResponseFormatError("LLM JSON choice item must be an object")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise LLMResponseFormatError("LLM JSON choice must include a 'message' object")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseFormatError("LLM JSON message content must be a non-empty string")

        return content
