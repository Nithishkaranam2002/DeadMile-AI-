"""LLM calls for the experiment agent, through LiteLLM.

* The main model comes from LAB_LLM_MODEL, the optional offline backup (Ollama)
  from LAB_LLM_OFFLINE_MODEL. The model used is recorded on every call.
* Structured output: for cloud models the pydantic schema is sent as a JSON
  schema (``response_format``, checked in litellm 1.106.6). Ollama 0.16.2
  refuses our variant schema as a ``format`` grammar for deepseek-r1:8b
  ("failed to load model vocabulary required for format"), so local models
  get JSON mode with the schema written into the prompt. Either way the reply
  is validated by the caller with pydantic; nothing is repaired.
* Cost comes from LiteLLM's per call cost tracking (``completion_cost``). A
  local Ollama model has no API cost (0 USD, stated on the record). Before each
  call the worst case (prompt tokens + the max output tokens) is checked
  against the budget, so a call can never push spend over the cap.
* Keys: read by LiteLLM from the environment, never passed in prompts. Every
  text that is logged goes through ``redact``, which removes the value of any
  environment variable that looks like a secret.
* Tests use ``FakeLLM`` with fixed answers; they never call a real model.
* Kill switch (Module 4): checked before every call, for every client.
"""

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from dmlab.safeguards import killswitch

SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
REDACTED = "[REDACTED]"
MAIN_MODEL_ENV = "LAB_LLM_MODEL"
OFFLINE_MODEL_ENV = "LAB_LLM_OFFLINE_MODEL"
LOCAL_NUM_CTX = 24_576


def _secret_values() -> list[str]:
    vals = {v for k, v in os.environ.items() if SECRET_NAME.search(k) and v and len(v) >= 8}
    return sorted(vals, key=len, reverse=True)


def redact(text: str) -> str:
    for value in _secret_values():
        text = text.replace(value, REDACTED)
    return text


class LLMCall(BaseModel):
    """One LLM call, as logged (texts are redacted)."""

    index: int
    node: str
    model: str
    local: bool
    messages: list[dict[str, str]]
    response_text: str
    reasoning_text: str | None = None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int | None = None
    cost_usd: float
    cost_note: str
    latency_s: float
    max_output_tokens: int


class LLMBudgetExceeded(Exception):
    pass


class LLMError(Exception):
    pass


class LLMClient(ABC):
    model: str
    local: bool

    def __init__(self) -> None:
        self.calls: list[LLMCall] = []

    def prepare(
        self, messages: list[dict[str, str]], schema: type[BaseModel]
    ) -> list[dict[str, str]]:
        """Messages exactly as sent (and logged)."""
        return messages

    @abstractmethod
    def _complete(
        self, messages: list[dict[str, str]], schema: type[BaseModel], max_output_tokens: int
    ) -> tuple[str, str | None, int, int, int | None, float, str]:
        """(text, reasoning, prompt_tokens, completion_tokens, reasoning_tokens,
        cost_usd, cost_note)."""

    @abstractmethod
    def worst_case(
        self, messages: list[dict[str, str]], max_output_tokens: int
    ) -> tuple[int, float]:
        """Upper bound of (tokens, USD) for one call."""

    def complete(
        self,
        node: str,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        max_output_tokens: int,
    ) -> LLMCall:
        killswitch.check(f"before the LLM call at {node}")
        messages = self.prepare(messages, schema)
        start = time.perf_counter()
        text, reasoning, p_tok, c_tok, r_tok, cost, note = self._complete(
            messages, schema, max_output_tokens
        )
        call = LLMCall(
            index=len(self.calls) + 1,
            node=node,
            model=self.model,
            local=self.local,
            messages=[{k: redact(v) for k, v in m.items()} for m in messages],
            response_text=redact(text),
            reasoning_text=redact(reasoning) if reasoning else None,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            reasoning_tokens=r_tok,
            cost_usd=cost,
            cost_note=note,
            latency_s=time.perf_counter() - start,
            max_output_tokens=max_output_tokens,
        )
        self.calls.append(call)
        return call


def _quiet_litellm() -> Any:
    import litellm

    # Never echo requests: LITELLM_LOG from the product's .env is not honored here.
    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return litellm


class LiteLLMClient(LLMClient):
    def __init__(self, model: str, timeout_s: float = 600.0) -> None:
        super().__init__()
        if not model:
            raise LLMError(f"no model given; set {MAIN_MODEL_ENV} or {OFFLINE_MODEL_ENV}")
        self.model = model
        self.local = model.startswith(("ollama/", "ollama_chat/"))
        self.timeout_s = timeout_s
        self.litellm = _quiet_litellm()
        if not self.local:
            # The dollar budget needs a price; refuse models LiteLLM cannot price.
            try:
                self.litellm.cost_per_token(model=model, prompt_tokens=1, completion_tokens=1)
            except Exception as exc:
                raise LLMError(f"LiteLLM has no price for {model!r}: {exc}") from None

    def prepare(
        self, messages: list[dict[str, str]], schema: type[BaseModel]
    ) -> list[dict[str, str]]:
        if not self.local:
            return messages
        spec = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        note = (
            "\n\nReply with one JSON object only, valid against this JSON schema "
            f"({schema.__name__}):\n{spec}"
        )
        return [*messages[:-1], {**messages[-1], "content": messages[-1]["content"] + note}]

    def worst_case(
        self, messages: list[dict[str, str]], max_output_tokens: int
    ) -> tuple[int, float]:
        try:
            prompt = self.litellm.token_counter(model=self.model, messages=messages)
        except Exception:
            prompt = sum(len(m["content"]) for m in messages) // 3  # conservative fallback
        tokens = prompt + max_output_tokens
        if self.local:
            return tokens, 0.0
        p_cost, c_cost = self.litellm.cost_per_token(
            model=self.model, prompt_tokens=prompt, completion_tokens=max_output_tokens
        )
        return tokens, p_cost + c_cost

    def _complete(
        self, messages: list[dict[str, str]], schema: type[BaseModel], max_output_tokens: int
    ) -> tuple[str, str | None, int, int, int | None, float, str]:
        response_format: dict[str, Any] = (
            {"type": "json_object"}
            if self.local
            else {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": False,
                },
            }
        )
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": response_format,
            "max_tokens": max_output_tokens,
            "timeout": self.timeout_s,
            "num_retries": 2,
        }
        if self.local:
            kwargs["api_base"] = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
            # Ollama's default context window (4096 tokens) silently truncates
            # our prompts; this fits the largest prompt plus the output budget.
            kwargs["num_ctx"] = LOCAL_NUM_CTX
        try:
            resp = self.litellm.completion(**kwargs)
        except Exception as exc:
            raise LLMError(redact(f"{type(exc).__name__}: {exc}")) from None
        msg = resp.choices[0].message
        text = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None)
        usage = resp.usage
        details = getattr(usage, "completion_tokens_details", None)
        r_tok = getattr(details, "reasoning_tokens", None) if details else None
        if self.local:
            cost, note = 0.0, "local model (Ollama): no API cost"
        else:
            cost = float(self.litellm.completion_cost(completion_response=resp))
            note = "LiteLLM completion_cost (provider list price)"
        return (
            text,
            reasoning,
            int(usage.prompt_tokens),
            int(usage.completion_tokens),
            r_tok,
            cost,
            note,
        )


class FakeLLM(LLMClient):
    """Fixed answers per node, for tests. Never calls a model."""

    def __init__(
        self,
        answers: dict[str, Sequence[str | dict[str, Any]]],
        model: str = "fake/fixed-answers",
        tokens_per_call: tuple[int, int] = (1000, 500),
        usd_per_call: float = 0.001,
    ) -> None:
        super().__init__()
        self.model = model
        self.local = False
        self.answers = {k: list(v) for k, v in answers.items()}
        self.tokens_per_call = tokens_per_call
        self.usd_per_call = usd_per_call

    def worst_case(
        self, messages: list[dict[str, str]], max_output_tokens: int
    ) -> tuple[int, float]:
        return sum(self.tokens_per_call), self.usd_per_call

    def _complete(
        self, messages: list[dict[str, str]], schema: type[BaseModel], max_output_tokens: int
    ) -> tuple[str, str | None, int, int, int | None, float, str]:
        node = schema.__name__
        queue = self.answers.get(node) or []
        if not queue:
            raise LLMError(f"FakeLLM has no answer left for {node}")
        answer = queue.pop(0)
        text = answer if isinstance(answer, str) else json.dumps(answer)
        p, c = self.tokens_per_call
        return text, None, p, c, None, self.usd_per_call, "fake LLM (fixed test cost)"


def parse_json(text: str) -> Any:
    """Parse a JSON reply. Reasoning models sometimes wrap it in a code fence or
    put <think> text first; only that wrapper is removed, nothing is repaired."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, flags=re.S)
    if fence:
        t = fence.group(1)
    return json.loads(t)
