from __future__ import annotations

import json
from pathlib import Path


class WorkflowManager:
    def __init__(self, workflows_root: Path):
        self.workflows_root = Path(workflows_root)
        self.workflows_root.mkdir(parents=True, exist_ok=True)

    def list_workflows(self) -> list[str]:
        return sorted(file_path.stem for file_path in self.workflows_root.glob("*.json"))

    def load_workflow(self, name: str) -> dict:
        path = self._workflow_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {name}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_workflow(self, name: str, payload: dict) -> Path:
        normalized = self._normalize_name(name)
        path = self._workflow_path(normalized)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def delete_workflow(self, name: str) -> None:
        path = self._workflow_path(name)
        if path.exists():
            path.unlink()

    def run_workflow(self, name: str, command_registry, *, log_cb=print, progress_cb=None) -> dict:
        payload = self.load_workflow(name)
        steps = payload.get("steps", [])
        results = []
        total = max(1, len(steps))
        log_cb(f"Running workflow '{payload.get('name', name)}' with {len(steps)} step(s).")
        for index, step in enumerate(steps, start=1):
            command_id = step.get("command")
            arguments = step.get("args", {})
            if not command_id:
                raise ValueError(f"Workflow step {index} is missing a command id.")
            log_cb(f"[{index}/{total}] {command_id}")
            result = command_registry.execute(command_id, **arguments)
            results.append({"command": command_id, "result": result})
            if progress_cb is not None:
                progress_cb(index / total)
        return {
            "name": payload.get("name", name),
            "steps": len(steps),
            "results": results,
        }

    def _normalize_name(self, name: str) -> str:
        cleaned = "".join(char for char in name.strip() if char.isalnum() or char in {"_", "-", " "})
        cleaned = cleaned.strip().replace(" ", "_")
        if not cleaned:
            raise ValueError("Workflow name cannot be empty.")
        return cleaned

    def _workflow_path(self, name: str) -> Path:
        normalized = self._normalize_name(name)
        return self.workflows_root / f"{normalized}.json"
