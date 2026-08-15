import json
import re
import time
import uuid
from typing import List, Dict, Optional, Generator, Tuple, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import logger, get_active_config


MAX_CTX_CHARS = 80000
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0
REASONING_FLOOD_LIMIT = 25000


class ReasoningFloodError(Exception):
    """Модель слишком долго 'думает' (reasoning_content) без выдачи ответа."""
    pass


class AIClientError(Exception):
    pass


class AIClient:
    def __init__(self):
        self.config = get_active_config()
        self.base_url = self.config["base_url"].rstrip("/")
        self.api_key = self.config["api_key"]
        self.model = self.config["model"]
        self.provider = self.config.get("provider", "")
        self._session_uuid = str(uuid.uuid4())
        self.    _http_session = self._create_session()
        logger.info(f"[AI] Initialized: model={self.model}, base_url={self.base_url}, provider={self.provider}")

    @staticmethod
    def _create_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=MAX_RETRIES + 2,
            connect=MAX_RETRIES,
            read=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF * 2,
            allowed_methods=["POST", "GET"],
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=4)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @staticmethod
    def _sanitize_header_value(value: str) -> str:
        try:
            value.encode("latin-1")
            return value
        except UnicodeEncodeError:
            return value.encode("latin-1", errors="replace").decode("latin-1")

    def _headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        key = api_key or self.api_key

        if self.provider == "zen":
            auth_value = f"Bearer {key}" if key else "Bearer public"
            headers["Authorization"] = self._sanitize_header_value(auth_value)
            headers["User-Agent"] = "opencode/1.15.0 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13"
            headers["x-opencode-client"] = "web"
            headers["x-opencode-project"] = "global"
            headers["x-opencode-request"] = f"msg_{uuid.uuid4().hex[:24]}"
            headers["x-opencode-session"] = f"ses_{self._session_uuid[:24]}"
            return headers

        if key:
            headers["Authorization"] = self._sanitize_header_value(f"Bearer {key}")
        return headers

    @staticmethod
    def _ensure_chat_url(base_url: str) -> str:
        base = base_url.rstrip("/")
        if "/chat/completions" in base:
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    @staticmethod
    def total_chars(messages: List[Dict]) -> int:
        return sum(len(str(m.get("content", ""))) + len(str(m.get("tool_calls", ""))) for m in messages)

    def compact_messages(self, messages: List[Dict]) -> List[Dict]:
        max_msgs = 20
        max_tool_msgs = 8

        total = self.total_chars(messages)

        system_msgs = []
        remaining = messages[:]
        while remaining and remaining[0].get("role") == "system":
            system_msgs.append(remaining.pop(0))

        user_msgs = []
        tool_iterations = []
        current_iter = []
        for m in remaining:
            if m["role"] == "user":
                if current_iter:
                    tool_iterations.append(current_iter)
                    current_iter = []
                user_msgs.append(m)
            elif m["role"] in ("assistant", "tool"):
                current_iter.append(m)
            elif m["role"] == "system":
                system_msgs.append(m)
        if current_iter:
            tool_iterations.append(current_iter)

        if len(tool_iterations) > max_tool_msgs:
            removed = len(tool_iterations) - max_tool_msgs
            tool_iterations = tool_iterations[removed:]
            logger.info(f"[AI] Compacted context: removed {removed} old tool iterations")

        compacted = user_msgs[:]
        for it in tool_iterations:
            compacted.extend(it)

        if system_msgs:
            compacted = system_msgs + compacted

        new_total = self.total_chars(compacted)
        logger.debug(f"[AI] Context compacted: msgs {len(remaining)}->{len(compacted)}, chars {total}->{new_total}")

        while new_total > MAX_CTX_CHARS and len(tool_iterations) > 2:
            tool_iterations = tool_iterations[2:]
            compacted = user_msgs[:]
            for it in tool_iterations:
                compacted.extend(it)
            if system_msgs:
                compacted = system_msgs + compacted
            new_total = self.total_chars(compacted)
            logger.info(f"[AI] Aggressive compact: dropped 2 more iterations, now {len(compacted)} msgs, {new_total} chars")

        return compacted

    def _post_with_retry(self, url: str, headers: Dict, payload: Dict, stream: bool) -> requests.Response:
        last_error = None
        for attempt in range(MAX_RETRIES + 3):
            try:
                return self._http_session.post(
                    url,
                    headers=headers,
                    json=payload,
                    stream=stream,
                    timeout=(30, 90),
                )
            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"[AI] Connection error (attempt {attempt+1}/{MAX_RETRIES+3}): {e}")
                wait = min(RETRY_BACKOFF * (3 ** attempt), 30)
                logger.info(f"[AI] Retrying in {wait:.1f}s with new session...")
                time.sleep(wait)
                self._http_session = self._create_session()
                continue
            except requests.exceptions.Timeout as e:
                last_error = e
                wait = min(RETRY_BACKOFF * (2 ** attempt), 20)
                logger.warning(f"[AI] Timeout (attempt {attempt+1}/{MAX_RETRIES+3}), retrying in {wait:.1f}s...")
                time.sleep(wait)
                continue
        logger.error(f"[AI] All retries exhausted for POST {url[:60]}")
        raise last_error  # type: ignore[misc]

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 8192,
        stream: bool = True,
        api_key: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        messages = self.compact_messages(messages)
        url = self._ensure_chat_url(self.base_url)

        total_chars = self.total_chars(messages)
        logger.info(f"[AI] Request: model={self.model}, msgs={len(messages)}, chars={total_chars}, tools={bool(tools)}")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        payload["stream"] = stream

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            response = self._post_with_retry(url, self._headers(api_key), payload, stream)

            if response.status_code == 400:
                error_body = response.text[:300]
                logger.warning(f"[AI] API 400: {error_body}")
                # Retry up to 3 times with compacted context + delay
                for retry_attempt in range(3):
                    wait = 2.0 * (retry_attempt + 1)
                    logger.info(f"[AI] Retrying 400 in {wait:.0f}s (attempt {retry_attempt+2})...")
                    time.sleep(wait)
                    extra_compact = self.compact_messages(messages[:1] + messages[-8:])
                    payload["messages"] = extra_compact
                    self._http_session = self._create_session()
                    response = self._post_with_retry(url, self._headers(api_key), payload, stream)
                    if response.status_code == 200:
                        break
                    elif response.status_code == 400:
                        continue
                    break
                else:
                    error_msg = f"API error {response.status_code}: {response.text[:500]}"
                    logger.error(f"[AI] {error_msg}")
                    yield {"type": "error", "content": error_msg}
                    return

            if response.status_code != 200:
                error_msg = f"API error {response.status_code}: {response.text[:500]}"
                logger.error(f"[AI] {error_msg}")
                yield {"type": "error", "content": error_msg}
                return

            if stream:
                yield from self._handle_stream(response)
            else:
                yield from self._handle_response(response, has_tools=bool(tools))

        except ReasoningFloodError as e:
            logger.warning(f"[AI] Reasoning flood ({e}) — retrying with short context")
            yield {"type": "error", "content": f"reasoning_only: {e}"}
        except requests.exceptions.Timeout:
            logger.error("[AI] Request timeout")
            yield {"type": "error", "content": "Request timeout (240s)"}
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[AI] Connection error after {MAX_RETRIES+1} attempts: {e}")
            yield {"type": "error", "content": f"Cannot connect to {self.base_url}: {e}"}
        except Exception as e:
            logger.error(f"[AI] Error: {e}")
            yield {"type": "error", "content": str(e)}

    def _handle_stream(self, response) -> Generator[Dict, None, None]:
        full_content = ""
        tool_calls_buffer = []
        reasoning_chars = 0
        finished = False

        try:
            for line in response.iter_lines(decode_unicode=False):
                if not line:
                    continue
                try:
                    line_str = line.decode("utf-8")
                except UnicodeDecodeError:
                    line_str = line.decode("utf-8", errors="replace")
                if not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    finished = True
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices")
                if not choices:
                    # Zen API meta event — treat as stream completion
                    if "x-opencode-type" in data:
                        logger.debug(f"[AI] Zen meta event: {data.get('x-opencode-type')}")
                        finished = True
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content", "") or ""
                reasoning = delta.get("reasoning_content", "") or ""

                if content:
                    logger.debug(f"[AI] chunk content={repr(content)[:80]}")
                    full_content += content
                    yield {"type": "chunk", "content": content}
                if reasoning:
                    logger.debug(f"[AI] reasoning={repr(reasoning)[:80]}")
                    reasoning_chars += len(reasoning)
                    if reasoning_chars > REASONING_FLOOD_LIMIT and not full_content and not tool_calls_buffer:
                        # Модель "думает" без выдачи ответа — обрываем поток, чтобы
                        # не зависнуть на минуты. Сервер повторит запрос с коротким
                        # контекстом и требованием ответить сразу.
                        logger.warning(f"[AI] Aborting stream: reasoning-only ({reasoning_chars} chars), no content")
                        response.close()
                        raise ReasoningFloodError(reasoning_chars)
                    yield {"type": "thinking", "content": reasoning}

                tc_delta = delta.get("tool_calls")
                if tc_delta:
                    for tc in tc_delta:
                        idx = tc.get("index", 0)
                        while len(tool_calls_buffer) <= idx:
                            tool_calls_buffer.append(None)
                        if tool_calls_buffer[idx] is None:
                            tool_calls_buffer[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        existing = tool_calls_buffer[idx]
                        if tc.get("id"):
                            existing["id"] = tc["id"]
                        if tc.get("function"):
                            fn = tc["function"]
                            if fn.get("name"):
                                existing["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                existing["function"]["arguments"] += fn["arguments"]

                finish = choices[0].get("finish_reason")
                if finish == "tool_calls":
                    finished = True
                    valid_calls = [tc for tc in tool_calls_buffer if tc is not None and tc["function"]["name"]]
                    if valid_calls:
                        for tc in valid_calls:
                            try:
                                tc["function"]["arguments"] = json.loads(tc["function"]["arguments"])
                            except (json.JSONDecodeError, TypeError):
                                tc["function"]["arguments"] = {}
                            logger.info(f"[AI] Stream tool call: {tc['function']['name']}({tc['function']['arguments']})")
                        yield {"type": "tool_calls", "calls": valid_calls}
                    break
                if finish == "stop":
                    finished = True
                    break
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[AI] Stream interrupted by connection error: {e}")
            if full_content.strip():
                yield {"type": "chunk", "content": full_content}
        except requests.exceptions.ChunkedEncodingError as e:
            logger.error(f"[AI] Stream chunked encoding error (server cut connection): {e}")
            # May have partial data, proceed to yield what we have
        except ReasoningFloodError:
            raise
        except Exception as e:
            logger.error(f"[AI] Stream error: {e}")
            # Yield partial data if any and let caller handle

        if not finished:
            if tool_calls_buffer and any(tc is not None and tc["function"]["name"] for tc in tool_calls_buffer):
                valid_calls = []
                for tc in tool_calls_buffer:
                    if tc is None or not tc["function"]["name"]:
                        continue
                    args = tc["function"]["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    # Skip calls with empty/partial arguments
                    if not args or args == {}:
                        logger.warning(f"[AI] Skipping recovered tool call '{tc['function']['name']}' with empty args")
                        continue
                    tc["function"]["arguments"] = args
                    valid_calls.append(tc)
                    logger.info(f"[AI] Recovered tool call after stream error: {tc['function']['name']}({args})")
                if valid_calls:
                    yield {"type": "tool_calls", "calls": valid_calls}
                elif full_content.strip():
                    logger.warning(f"[AI] Partial tool calls but text exists, treating as text response")
                    yield {"type": "chunk", "content": full_content}
                else:
                    logger.error("[AI] Stream cut with only partial/invalid tool calls")
                    yield {"type": "error", "content": "Stream was cut while generating tool calls. Retrying..."}
            elif full_content.strip():
                logger.warning(f"[AI] Stream ended without finish_reason, treating as text response")
                yield {"type": "chunk", "content": full_content}
            else:
                logger.error("[AI] Stream ended prematurely with no content or valid tool calls")
                yield {"type": "error", "content": "Connection was interrupted. Please try again."}

        yield {"type": "done", "content": full_content}

    def _handle_response(self, response, has_tools: bool) -> Generator[Dict, None, None]:
        data = response.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        finish = choice.get("finish_reason", "")

        content = msg.get("content", "") or ""
        reasoning = msg.get("reasoning_content", "") or ""

        if reasoning:
            yield {"type": "thinking", "content": reasoning}

        if finish == "tool_calls" and "tool_calls" in msg:
            calls = []
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}
                calls.append({
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": {"name": func.get("name", ""), "arguments": args}
                })
                logger.info(f"[AI] Tool call: {func.get('name')}({args})")
            yield {"type": "tool_calls", "calls": calls}
            yield {"type": "done", "content": content or ""}
            return

        if content:
            yield {"type": "chunk", "content": content}

        yield {"type": "done", "content": content}

    def switch_mode(self, mode: str, api_key: Optional[str] = None) -> bool:
        from config import AI_CONFIG

        if mode not in AI_CONFIG:
            logger.warning(f"[AI] Unknown mode: {mode}")
            return False

        self.config = AI_CONFIG[mode].copy()
        self.base_url = self.config["base_url"].rstrip("/")
        self.provider = self.config.get("provider", mode)

        if api_key:
            self.api_key = api_key
        else:
            self.api_key = self.config.get("api_key", "")

        self.model = self.config.get("model", "deepseek-chat")
        logger.info(f"[AI] Switched to {mode}: model={self.model}")
        return True
