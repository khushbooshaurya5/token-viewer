"""Read a capture: the file capture-nvidia-response in llm_inference writes.

A capture holds three kinds of facts, and this module keeps them apart:

- request: what the laptop sent, e.g. the requested model and the URL.
- provider: what the provider's service answered, in the status line and the
  JSON body, e.g. the reported model, the finish reason and the usage.
- local: what the laptop measured or this viewer reconstructs, e.g. the
  elapsed time, the provider's name derived from the URL, and the prompt
  tokens counted with a local tokenizer.

Part of the model: it imports no view and no web framework.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias
from urllib.parse import urlsplit

Source: TypeAlias = Literal["request", "provider", "local"]

# Hosts the course uses, and the provider each one belongs to.
_PROVIDERS: dict[str, str] = {
    "integrate.api.nvidia.com": "NVIDIA Build",
    "openrouter.ai": "OpenRouter",
}


class CaptureError(Exception):
    """The file is not a capture this module can read. The message says why."""


@dataclass(frozen=True)
class Fact:
    """One piece of response metadata, with where it comes from."""

    label: str
    value: str
    source: Source


@dataclass(frozen=True)
class Capture:
    """What one capture file says, sorted by source."""

    name: str
    requested_model: str | None
    url: str | None
    provider: str | None
    status_code: int | None
    reason: str | None
    reported_model: str | None
    finish_reason: str | None
    usage: dict[str, Any]
    elapsed_seconds: float | None
    waited_seconds: float | None
    captured_at: str | None
    error: str | None
    answer: str | None
    reasoning: str | None
    request_messages: list[tuple[str, str]]
    """The messages the request sent, as role and content."""
    template_switches: dict[str, bool] = field(default_factory=dict)
    """The request's chat_template_kwargs that are switches (True or False)."""

    @property
    def reported_prompt_tokens(self) -> int | None:
        """The prompt tokens the provider reports in its usage, if any."""
        value: Any = self.usage.get("prompt_tokens")
        return value if isinstance(value, int) else None

    def facts(self) -> list[Fact]:
        """Return the metadata the views show, each with its source."""
        facts: list[Fact] = []

        def add(label: str, value: object, source: Source) -> None:
            if value is not None and value != {}:
                facts.append(Fact(label, _as_text(value), source))

        add("Requested model", self.requested_model, "request")
        add("Request URL", self.url, "request")
        add("Template switches sent", self.template_switches or None, "request")
        add("Provider (derived from the URL)", self.provider, "local")
        add("HTTP status", _status_line(self.status_code, self.reason), "provider")
        add("Reported model", self.reported_model, "provider")
        add("Finish reason", self.finish_reason, "provider")
        add("Usage", self.usage, "provider")
        add("Elapsed until the headers arrived (s)", self.elapsed_seconds, "local")
        add("Whole call, laptop clock (s)", self.waited_seconds, "local")
        add("Captured at", self.captured_at, "local")
        add("Error without a response", self.error, "local")
        return facts


def read_capture(name: str, content: str) -> Capture:
    """Read a capture from the text of its file.

    Raises:
        CaptureError: If the text is not JSON, or not shaped like a capture.
    """
    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as problem:
        raise CaptureError(
            f"{name} is not JSON: {problem.msg} at line {problem.lineno}."
        ) from None
    if not isinstance(data, dict) or not {"request", "response"} <= data.keys():
        raise CaptureError(
            f"{name} is not a capture: it lacks the keys request and response "
            "that capture-nvidia-response writes."
        )

    request: dict[str, Any] = _mapping(data.get("request"))
    request_body: dict[str, Any] = _mapping(request.get("body"))
    response: dict[str, Any] = _mapping(data.get("response"))
    # An error page need not be JSON; the capture then keeps its text.
    response_body: dict[str, Any] = _mapping(response.get("body"))
    choice: dict[str, Any] = _first_choice(response_body)
    message: dict[str, Any] = _mapping(choice.get("message"))
    error: dict[str, Any] = _mapping(data.get("error"))

    url: str | None = _text(request.get("url"))
    kwargs: dict[str, Any] = _mapping(request_body.get("chat_template_kwargs"))
    return Capture(
        name=name,
        requested_model=_text(request_body.get("model")),
        url=url,
        provider=_provider(url),
        status_code=_integer(response.get("status_code")),
        reason=_text(response.get("reason")),
        reported_model=_text(response_body.get("model")),
        finish_reason=_text(choice.get("finish_reason")),
        usage=_mapping(response_body.get("usage")),
        elapsed_seconds=_number(response.get("elapsed_seconds")),
        waited_seconds=_number(data.get("waited_seconds")),
        captured_at=_text(data.get("captured_at")),
        error=(
            f"{error.get('type', 'Error')}: {error.get('message', '')}"
            if error
            else None
        ),
        answer=_text(message.get("content")),
        # NVIDIA names the field reasoning_content; other providers reasoning.
        reasoning=_text(message.get("reasoning_content"))
        or _text(message.get("reasoning")),
        request_messages=_messages(request_body.get("messages")),
        template_switches={k: v for k, v in kwargs.items() if isinstance(v, bool)},
    )


def _mapping(value: object) -> dict[str, Any]:
    """Return value if it is a JSON object, else an empty one."""
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    """Return value if it is a non-empty string, else None."""
    return value if isinstance(value, str) and value != "" else None


def _integer(value: object) -> int | None:
    """Return value if it is an int (and not a bool), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> float | None:
    """Return value as a float if it is a number, else None."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _first_choice(body: dict[str, Any]) -> dict[str, Any]:
    """Return the first choice of a chat completion, or an empty object."""
    choices: Any = body.get("choices")
    if isinstance(choices, list) and choices:
        return _mapping(choices[0])
    return {}


def _messages(value: object) -> list[tuple[str, str]]:
    """Return the request's messages whose role and content are strings."""
    if not isinstance(value, list):
        return []
    return [
        (item["role"], item["content"])
        for item in value
        if isinstance(item, dict)
        and isinstance(item.get("role"), str)
        and isinstance(item.get("content"), str)
    ]


def _provider(url: str | None) -> str | None:
    """Name the provider from the request URL's host."""
    if url is None:
        return None
    host: str = urlsplit(url).hostname or ""
    return _PROVIDERS.get(host, host or None)


def _status_line(code: int | None, reason: str | None) -> str | None:
    """Join the status code and reason, as in "200 OK"."""
    if code is None:
        return None
    return f"{code} {reason}" if reason else str(code)


def _as_text(value: object) -> str:
    """Show a value as text; objects as compact JSON."""
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
