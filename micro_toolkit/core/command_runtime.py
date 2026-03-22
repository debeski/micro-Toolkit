from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path


class HeadlessTaskContext:
    def __init__(self, services, *, command_id: str = ""):
        self.services = services
        self.command_id = command_id
        self.progress_updates: list[float] = []
        self.log_messages: list[dict[str, str]] = []

    def progress(self, value: float) -> None:
        normalized = max(0.0, min(1.0, float(value)))
        self.progress_updates.append(normalized)

    def log(self, message: str, level: str = "INFO") -> None:
        text = str(message)
        self.log_messages.append({"level": level, "message": text})
        self.services.log(text, level)


def serialize_command_result(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value):
        return serialize_command_result(asdict(value))

    if isinstance(value, dict):
        return {str(key): serialize_command_result(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [serialize_command_result(item) for item in value]

    value_type = type(value)
    module_name = getattr(value_type, "__module__", "")
    type_name = getattr(value_type, "__name__", "")

    if module_name.startswith("pandas") and type_name == "DataFrame":
        columns = [str(column) for column in value.columns]
        preview_records = value.head(50).to_dict(orient="records")
        return {
            "_type": "dataframe",
            "rows": int(len(value)),
            "columns": columns,
            "preview": serialize_command_result(preview_records),
        }

    if module_name.startswith("pandas") and type_name == "Series":
        return {
            "_type": "series",
            "rows": int(len(value)),
            "name": str(getattr(value, "name", "")),
            "preview": serialize_command_result(value.head(50).to_dict()),
        }

    if isinstance(value, bytes):
        return {"_type": "bytes", "length": len(value)}

    return str(value)


def describe_command_result(value) -> str:
    serialized = serialize_command_result(value)
    if isinstance(serialized, dict):
        if serialized.get("_type") == "dataframe":
            return f"Generated dataframe with {serialized.get('rows', 0)} row(s)."
        if "output_path" in serialized:
            return f"Wrote output to {serialized['output_path']}."
        if "report_path" in serialized and serialized.get("report_path"):
            return f"Wrote report to {serialized['report_path']}."
        if "count" in serialized:
            return f"Processed {serialized['count']} item(s)."
    return str(serialized)[:500]
