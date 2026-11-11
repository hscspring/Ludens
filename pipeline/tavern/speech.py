from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro
from misaki.zh import ZHG2P
from onnxruntime.capi.onnxruntime_pybind11_state import Fail, InvalidArgument, RuntimeException

LOG = logging.getLogger(__name__)


class Speech:
    def __init__(self, model_dir: Path, output_dir: Path, voice: str = "zm_010") -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model_dir / "kokoro-v1.1-zh.onnx"), sess_options=options,
                                       providers=["CPUExecutionProvider"])
        self.model = Kokoro.from_session(session, str(model_dir / "voices-v1.1-zh.bin"),
                                         vocab_config=str(model_dir / "config.json"))
        self.g2p = ZHG2P(version="1.1", en_callable=self._english)
        self.voice = voice
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue()
        threading.Thread(target=self._work, daemon=True).start()

    def _english(self, text: str) -> str:
        return self.model.tokenizer.phonemize(text, lang="en-us")

    def submit(self, key: str, text: str, done: Callable[[dict], None]) -> None:
        self.queue.put((key, text, done, time.monotonic()))

    def _work(self) -> None:
        while True:
            key, text, done, submitted = self.queue.get()
            started = time.monotonic()
            try:
                phonemes, _ = self.g2p(text)
                samples, rate = self.model.create(phonemes, voice=self.voice, speed=1, is_phonemes=True)
                path = self.output_dir / f"{key}.wav"
                sf.write(path, samples, rate)
                result = {"status": "ready", "path": str(path), "duration": round(len(samples) / rate, 2),
                          "ms": round((time.monotonic() - started) * 1000),
                          "wait_ms": round((started - submitted) * 1000)}
            except (ValueError, RuntimeError, OSError, KeyError, Fail, InvalidArgument, RuntimeException):
                LOG.exception("Speech failed for %s", key)
                result = {"status": "failed", "error": "语音生成失败，文字回应已保留。"}
            done(result)
            self.queue.task_done()
