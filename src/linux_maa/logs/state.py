from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from linux_maa.logs.records import LogTone
from linux_maa.logs.translator import RunLogTranslator


LogParser = Literal["maa", "plain"]


@dataclass
class RunLogBuffer:
    max_output_chunks: int = 2000
    translator: RunLogTranslator = field(default_factory=RunLogTranslator)
    output: deque[str] = field(init=False)

    def __post_init__(self) -> None:
        self.output = deque(maxlen=self.max_output_chunks)

    def to_dict(self) -> dict[str, object]:
        return {
            "output": list(self.output),
            "task_results": self.translator.task_results(),
            "log_entries": self.translator.entries(),
        }

    def append_event(self, text: str, *, time: str | None = None, tone: LogTone = "info") -> bool:
        rendered = self.translator.add_event(text, time=time, tone=tone)
        if not rendered:
            return False
        self.output.append(rendered)
        return True

    def append_process_output(self, text: str, *, source: str = "output", parser: LogParser = "maa") -> bool:
        if parser == "plain":
            rendered = self.translator.translate_plain(text, source=source)
        else:
            rendered = self.translator.translate(text, source=source)
        if not rendered:
            return False
        self.output.append(rendered)
        return True

    def flush(self) -> bool:
        rendered = self.translator.flush()
        if not rendered:
            return False
        self.output.append(rendered)
        return True

    def task_results(self) -> list[dict[str, object]]:
        return self.translator.task_results()

    def entries(self) -> list[dict[str, object]]:
        return self.translator.entries()

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        self.translator.begin_task_sequence(tasks)

    def current_task_elapsed_seconds(self) -> tuple[str, float] | None:
        return self.translator.current_task_elapsed_seconds()
