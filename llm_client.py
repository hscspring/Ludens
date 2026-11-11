"""Ludens 最小闭环共享 LLM 客户端:OpenAI 兼容 chat 端点,主端点失败降级到兜底,产解析好的 JSON。

端点与 demo_server.INIT_ENDPOINTS / data_pipeline configs/llm.yaml 对齐(gemini-3.8-flash 主、
deepseek-v4-pro 兜底)。key 只从环境变量读,经 _load_env 从 dotenv 补进本进程,绝不写进文件。
后续可让 demo_server 也改 import 本模块以消除端点定义的重复(需先经用户同意改现有代码)。
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable

import requests

from scene_state import first_json_object

DEFAULT_ENV_FILE = "/mnt/sv0/sean/data_pipeline/.env"

ENDPOINTS = [
    {"name": "gemini-3.8-flash", "base_url": "https://kaon-router.kaonai.com/v1",
     "model": "google/gemini-3.8-flash", "key_env": "GEMINI38_KEY",
     "params": {"temperature": 0.0, "max_tokens": 16384, "reasoning_effort": "low", "stream": False}},
    {"name": "deepseek-v4-pro", "base_url": "http://staging-kaon-router.flow.chat/v1",
     "model": "kaon/deepseek-v4-pro", "key_env": "KAON_KEY",
     "params": {"temperature": 0.7, "max_tokens": 16384, "enable_thinking": False, "stream": False}},
]


def _load_env(path: str) -> None:
    # 把 dotenv 的 KEY=VALUE 补进本进程环境(只补未设置的;key 绝不写文件、不打印)
    if not path or not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLMOutputError(ValueError): pass


class LLMClient:
    def __init__(self, endpoints: list[dict] | None = None, env_file: str = DEFAULT_ENV_FILE,
                 recorder: Callable[[dict], None] | None = None) -> None:
        _load_env(env_file)
        self.endpoints = endpoints or ENDPOINTS
        self.recorder = recorder

    def call_json(self, system: str, user: str | list[dict], **overrides) -> dict:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err = None
        for ep in self.endpoints:
            try:
                raw = self._chat(ep, messages, overrides)
                obj = first_json_object(raw)
                if not obj:
                    raise LLMOutputError("LLM returned no JSON object")
                parsed = json.loads(obj)
                if not isinstance(parsed, dict):
                    raise LLMOutputError("LLM returned a non-object JSON value")
                return parsed
            except (requests.RequestException, KeyError, ValueError) as e:
                last_err = e  # 主端点失败降级到下一个(用户指定的兜底语义)
        raise RuntimeError(f"all LLM endpoints failed: {last_err}")

    def _chat(self, ep: dict, messages: list[dict], overrides: dict) -> str:
        key = os.environ.get(ep["key_env"], "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        body = {"model": ep["model"], "messages": messages, **ep["params"], **overrides}
        started = time.monotonic()
        r = requests.post(ep["base_url"].rstrip("/") + "/chat/completions",
                          json=body, headers=headers, timeout=ep.get("timeout", 120))
        r.raise_for_status()
        result = r.json()
        raw = result["choices"][0]["message"]["content"] or ""
        if self.recorder is not None:
            self.recorder({"request": body, "response": raw, "usage": result.get("usage"),
                           "finish_reason": result["choices"][0].get("finish_reason"),
                           "elapsed_seconds": round(time.monotonic() - started, 3)})
        return raw
