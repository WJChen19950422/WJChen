"""Per-session durable event log and diagnostic export, no third-party dependencies."""
from __future__ import annotations
import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_log_dir() -> Path:
    documents = Path.home() / 'Documents'
    return (documents if documents.is_dir() else Path.home()) / 'CI76_Logs'


class EventLog:
    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder else default_log_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.session = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.file = self.folder / f'CI76_{self.session}.jsonl'
        self.telemetry_file = self.folder / f'CI76_{self.session}_telemetry.csv'
        with self.telemetry_file.open('w', encoding='utf-8-sig', newline='') as out:
            csv.writer(out).writerow(('time', 'current_A', 'position_pct', 'motor_status',
                                      'error_byte0', 'error_byte1', 'motor_seconds'))
        self.append('session_start', tool='v0.9 LAB', note='Host-PC events only; not MCU offline history')

    def append(self, kind: str, **data: Any) -> Path:
        record = {'time': datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds'),
                  'event': kind, **data}
        with self.file.open('a', encoding='utf-8') as out:
            out.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        return self.file

    def sample(self, *, current_A=None, position_pct=None, motor_status=None, flags=None, motor_seconds=None):
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')
        flag0, flag1 = flags if isinstance(flags, (list, tuple)) and len(flags) == 2 else ('', '')
        with self.telemetry_file.open('a', encoding='utf-8', newline='') as out:
            csv.writer(out).writerow((stamp, current_A, position_pct, motor_status,
                                      flag0, flag1, motor_seconds))

    def export_snapshot(self, snapshot: dict[str, Any], path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        body = {'schema': 'CI76 Diagnostic Snapshot v1',
                'captured_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
                'session_log': str(self.file), 'source': 'Live reads: CI76 firmware; no historical timestamp support',
                **snapshot}
        target.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        self.append('report_exported', file=str(target))
        return target
