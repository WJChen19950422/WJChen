"""New demo/normal page slider policy & device-write gates; no hardware."""
from __future__ import annotations
import unittest
from test_v09_learning_demo import FakeClient
from worker import SerialWorker
from lab_features import demo_current_write
from current_limits import (CURRENT_SLIDER_MIN_A,CURRENT_SLIDER_MAX_A,
                            amps_to_ticks,ticks_to_amps,within_slider_range)
from protocol import ProtocolError

class V11SliderTests(unittest.TestCase):
    def test_shared_0_8_slider_mapping(self):
        self.assertEqual((CURRENT_SLIDER_MIN_A,CURRENT_SLIDER_MAX_A),(0.0,8.0))
        for a in [0,0.01,1,1.99,2,3.5,8]:
            self.assertEqual(ticks_to_amps(amps_to_ticks(a)),a)
        self.assertFalse(within_slider_range(-.01))
        self.assertFalse(within_slider_range(8.01))

    def test_worker_zero_A_write_and_confirm(self):
        w=SerialWorker();w.client=FakeClient()
        result=w._demo_limit(0)
        self.assertEqual(result['actual_A'],0.0)
        self.assertEqual(w.client.writes[-1][0],0x06)
        self.assertEqual(w.client.current[:2],b'\x00\x00')
        self.assertEqual(w.client.current[2:],(900).to_bytes(2,'little')+(500).to_bytes(2,'little'))

    def test_8A_writes_without_extra_checkbox(self):
        w=SerialWorker();w.client=FakeClient()
        result=w._demo_limit(8)
        self.assertEqual(result['actual_A'],8)

    def test_above_overload_is_refused(self):
        raw=(100).to_bytes(2,'little')+(150).to_bytes(2,'little')+(500).to_bytes(2,'little')
        with self.assertRaisesRegex(ProtocolError,'過載門檻'):
            demo_current_write(raw,2)

    def test_all_nonlimit_current_fields_preserved(self):
        old=FakeClient().current
        for target in (0,1.23,8):
            _,payload,_,_=demo_current_write(old,target)
            self.assertEqual(payload[2:],old[2:])

if __name__=='__main__':unittest.main()
