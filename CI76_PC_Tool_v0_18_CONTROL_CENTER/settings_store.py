"""Safe connection preferences only: never store parameter or motion intents."""
from dataclasses import asdict, dataclass
import json
from PySide6.QtCore import QSettings


@dataclass(frozen=True)
class PortIdentity:
    device: str
    description: str = ''
    hwid: str = ''
    serial_number: str = ''
    vid: int | None = None
    pid: int | None = None

    @classmethod
    def from_port(cls, port):
        return cls(**{k: getattr(port, k, None) if k in ('vid', 'pid')
                      else (getattr(port, k, '') or '') for k in cls.__dataclass_fields__})


def match_port(saved, ports):
    """Return (unique candidate, reason); a COM name is never device proof."""
    if saved is None:
        return None, '尚無已驗證的連線紀錄；請手動選取'
    if saved.serial_number and saved.vid is not None and saved.pid is not None:
        candidates = [p for p in ports if (p.serial_number, p.vid, p.pid) ==
                      (saved.serial_number, saved.vid, saved.pid)]
    else:
        # Without USB serial identity require the same COM and at least one
        # useful descriptor; compare all metadata that was previously known.
        candidates = [p for p in ports if p.device == saved.device and
                      (saved.hwid or saved.description) and
                      all(not getattr(saved, k) or getattr(saved, k) == getattr(p, k)
                          for k in ('hwid', 'description', 'serial_number')) and
                      all(getattr(saved, k) is None or getattr(saved, k) == getattr(p, k)
                          for k in ('vid', 'pid'))]
    if len(candidates) == 1:
        return candidates[0], ''
    return None, ('符合紀錄的裝置不唯一；請手動選取' if candidates
                  else '上次裝置未找到或識別資料已變更；請手動選取')


class SettingsStore:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else QSettings('MOTECK', 'CI76ControlCenter')

    @property
    def auto_connect(self):
        return self.settings.value('connection/auto_connect', False, type=bool)

    def set_auto_connect(self, enabled):
        self.settings.setValue('connection/auto_connect', bool(enabled))
        self.settings.sync()

    def last_port(self):
        try:
            raw = json.loads(self.settings.value('connection/last_verified_port', '{}'))
            if not isinstance(raw, dict):
                return None
            if any(not isinstance(raw.get(k, ''), str) for k in
                   ('device','description','hwid','serial_number')):
                return None
            if any(raw.get(k) is not None and type(raw[k]) is not int for k in ('vid','pid')):
                return None
            return PortIdentity(**raw) if raw.get('device') else None
        except (TypeError, ValueError):
            return None

    def remember_verified(self, port, device_code):
        if device_code != '0x0B01' or port is None:
            return False
        self.settings.setValue('connection/last_verified_port', json.dumps(asdict(port)))
        self.settings.sync()
        return True
