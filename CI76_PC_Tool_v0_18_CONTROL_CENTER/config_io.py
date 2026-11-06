"""Versioned CI76 local configuration profiles (.config = UTF-8 JSON).

Import/export NEVER touches the serial port. Imported sensor selection is
staged only; the operator must explicitly apply it to the stopped device.
"""
from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
from protocol import FIELDS, GROUPS, ProtocolError, build_write

CONFIG_SCHEMA = 'CI76-config-v1'
LEGACY_SCHEMA = 'CI76-parameter-snapshot-v1'


def validate_parameters(values: dict) -> dict[str, float]:
    if not isinstance(values, dict):
        raise ValueError('parameters 必須是參數物件')
    cleaned = {}
    for key in FIELDS:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'缺少或無效參數：{key}')
        # no NaN/inf and exact centi-/deci-unit representability
        if not Decimal(str(value)).is_finite():
            raise ValueError(f'無效數值：{key}')
        cleaned[key] = float(value)
    for group in GROUPS:
        subset = {key: cleaned[key] for key in GROUPS[group][3]}
        try:
            build_write(group, subset)
        except ProtocolError as exc:
            # Firmware factory defaults brake 52/51 V, above normal write limits.
            # Accept as read-only profile but block their write until corrected.
            if not (group == '回生' and subset['brake_on'] == 52 and subset['brake_off'] == 51):
                raise ValueError(str(exc)) from exc
    return cleaned


def build_profile(parameters: dict, sensor_mode: int | None = None) -> dict:
    cleaned = validate_parameters(parameters)
    if sensor_mode not in (None, 1, 2):
        raise ValueError('感測器模式應為 Hall=1、POT=2 或未知')
    return {
        'schema': CONFIG_SCHEMA,
        'device': 'CI76',
        'description': '本機設定檔；不是 MCU Flash 儲存成功的證明',
        'parameters': cleaned,
        'sensor_mode': sensor_mode,
    }


def parse_profile(text: str) -> dict:
    try:
        doc = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('不是有效的 UTF-8 JSON/.config 設定檔') from exc
    if not isinstance(doc, dict) or doc.get('schema') not in (CONFIG_SCHEMA, LEGACY_SCHEMA):
        raise ValueError('設定檔 schema 不相容')
    if doc.get('device', 'CI76') != 'CI76':
        raise ValueError('設定檔不是 CI76 專用')
    parms = validate_parameters(doc.get('parameters'))
    sensor = doc.get('sensor_mode') if doc['schema'] == CONFIG_SCHEMA else None
    if sensor not in (None, 1, 2) or isinstance(sensor, bool):
        raise ValueError('sensor_mode 應為 1 (Hall)、2 (POT) 或 null')
    return {'parameters': parms, 'sensor_mode': sensor}


def save_profile(path: str | Path, parameters: dict, sensor_mode: int | None = None):
    doc = build_profile(parameters, sensor_mode)
    Path(path).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load_profile(path: str | Path) -> dict:
    return parse_profile(Path(path).read_text(encoding='utf-8-sig'))
