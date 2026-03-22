from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(object)
    result = Signal(object)
    progress = Signal(float)
    log = Signal(str, str)


class TaskContext:
    def __init__(self, signals: WorkerSignals):
        self._signals = signals

    def progress(self, value: float) -> None:
        self._signals.progress.emit(float(value))

    def log(self, message: str, level: str = "INFO") -> None:
        self._signals.log.emit(message, level)


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        context = TaskContext(self.signals)
        try:
            result = self.fn(context)
        except Exception as exc:
            self.signals.error.emit(
                {
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
