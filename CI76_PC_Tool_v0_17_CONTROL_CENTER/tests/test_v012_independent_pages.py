"""First-page/manual and Demo/automatic current writers must not interfere.

Worker tests use a fake CI76 transport; UI wiring is checked structurally,
not rendered (headless Linux environment has no PySide6 Qt runtime).
"""
from __future__ import annotations
import ast
import unittest
from pathlib import Path
from test_v09_learning_demo import FakeClient
from worker import SerialWorker
from protocol import parse_group, ProtocolError

ROOT = Path(__file__).resolve().parents[1]

class IndependentPageTests(unittest.TestCase):
    def test_demo_then_page1_verified_value_wins_and_restore_cannot_revert_it(self):
        w = SerialWorker(); w.client = FakeClient()
        w._demo_limit(1.5)
        self.assertIsNotNone(w.demo_original_current)
        manual = {'current_limit':2.0, 'current_overload':9.0, 'current_time':500}
        actual = w._write_group('電流', manual)
        self.assertEqual(actual, manual)
        self.assertIsNone(w.demo_original_current)
        self.assertEqual(w._demo_restore()['restored'], False)
        self.assertEqual(parse_group('電流', w.client.current)['current_limit'],2.0)

    def test_page1_then_demo_value_wins_and_restore_goes_back_to_page1(self):
        w = SerialWorker(); w.client = FakeClient()
        manual = {'current_limit':1.25, 'current_overload':9.0, 'current_time':500}
        w._write_group('電流', manual)
        w._demo_limit(1.75)
        self.assertEqual(parse_group('電流',w.client.current)['current_limit'],1.75)
        self.assertTrue(w._demo_restore()['restored'])
        self.assertEqual(parse_group('電流',w.client.current)['current_limit'],1.25)

    def test_demo_updates_limit_only_and_preserves_other_current_params(self):
        w = SerialWorker(); w.client = FakeClient()
        original = parse_group('電流',w.client.current)
        w._demo_limit(1.8)
        new = parse_group('電流',w.client.current)
        self.assertEqual(new['current_overload'],original['current_overload'])
        self.assertEqual(new['current_time'],original['current_time'])
        self.assertEqual(new['current_limit'],1.8)

    def test_failed_page1_readback_does_not_retire_demo_snapshot(self):
        class WrongReadback(FakeClient):
            def write_cmd(self,cmd,payload,*,timeout=1.2):
                self.writes.append((cmd,bytes(payload)))
                # Simulate an MCU that ACKs but does not apply the command.
                return payload
        w = SerialWorker(); w.client = FakeClient()
        w._demo_limit(1.5)
        self.assertIsNotNone(w.demo_original_current)
        stuck = WrongReadback(); stuck.current = w.client.current
        w.client = stuck
        w._write_group('電流', {'current_limit':2.0,'current_overload':9.0,'current_time':500})
        self.assertIsNotNone(w.demo_original_current)

    def test_independent_gui_handlers_never_cross_change_fields_before_readback(self):
        tree = ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        clz = next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='CI76Window')
        methods = {node.name:node for node in clz.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
        slider_handler=ast.get_source_segment((ROOT/'main.py').read_text(),methods['_on_demo_slider_changed'])
        current_handler=ast.get_source_segment((ROOT/'main.py').read_text(),methods['_current_to_slider'])
        assert slider_handler and current_handler
        self.assertNotIn("self.fields['current_limit'].setValue",slider_handler)
        self.assertNotIn('self.demo_slider',current_handler)
        self.assertNotIn('self.demo_target_spin',current_handler)
        self.assertIn('self._set_demo_limit_display', (ROOT/'main.py').read_text())

    def test_switching_to_page1_discards_pending_demo_target_even_if_inflight(self):
        tree=ast.parse((ROOT/'main.py').read_text())
        clz=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='CI76Window')
        fun=next(node for node in clz.body if isinstance(node,ast.FunctionDef) and node.name=='_on_tab_changed')
        fn_src=ast.get_source_segment((ROOT/'main.py').read_text(),fun)
        self.assertIn('self._demo_pending_value = None',fn_src)
        self.assertIn('if self._demo_pending_value is not None:', fn_src)

if __name__ == '__main__':
    unittest.main()
