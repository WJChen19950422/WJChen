"""v0.14: Demo current-priority polling and one global monitor switch."""
from __future__ import annotations
import ast
import unittest
from pathlib import Path
from monitoring import scheduled_monitor_commands
ROOT = Path(__file__).resolve().parents[1]

class DemoRefreshTests(unittest.TestCase):
    def test_demo_one_background_command_maximum(self):
        last={}
        a=scheduled_monitor_commands(auto=True,now=10.0,last=last,fast_demo=True)
        b=scheduled_monitor_commands(auto=True,now=10.05,last=last,fast_demo=True)
        c=scheduled_monitor_commands(auto=True,now=10.25,last=last,fast_demo=True)
        self.assertEqual(a, [0x10,0x17])
        self.assertEqual(b, [0x10])
        self.assertEqual(c, [0x10,0x12])
        for commands in (a,b,c):
            self.assertEqual(commands[0],0x10)
            self.assertLessEqual(len(commands),2)

    def test_demo_background_fairness(self):
        last={}
        background=[]
        for tick in range(50):
            commands=scheduled_monitor_commands(auto=True,now=10+tick*0.05,last=last,fast_demo=True)
            self.assertEqual(commands[0],0x10)
            if len(commands)>1: background.append(commands[1])
        self.assertTrue({0x11,0x12,0x13,0x14,0x17}.issubset(set(background)))
        self.assertLess(len(background),15)

    def test_page1_keeps_original_monitor_schedule(self):
        last={}
        scheduled_monitor_commands(auto=True, now=20,last=last,fast_demo=False)
        self.assertEqual(scheduled_monitor_commands(auto=True,now=20.05,last=last,fast_demo=False),[0x10,0x11])

    def test_manual_monitor_reads_all(self):
        self.assertEqual(scheduled_monitor_commands(auto=False,now=10,last={},fast_demo=True),
                         [0x10,0x11,0x12,0x13,0x17,0x14])

    def test_demo_large_digital_right_of_needle(self):
        src=(ROOT/'dial.py').read_text(encoding='utf-8')
        self.assertIn('right_x = cx + r + 36.0',src)
        self.assertIn("f'{number} A'",src)
        self.assertIn('digit_size = 31',src)

    def test_global_auto_monitor_keeps_value_on_tab_change(self):
        src=(ROOT/'main.py').read_text(encoding='utf-8')
        tree=ast.parse(src)
        window=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CI76Window')
        methods={n.name:ast.get_source_segment(src,n) for n in window.body if isinstance(n,ast.FunctionDef)}
        self.assertNotIn('demo_fast_check',src)
        self.assertNotIn('_demo_fast_saved',src)
        self.assertNotIn('self.auto_poll.setChecked(',methods['_on_tab_changed'])
        self.assertIn('self.tabs.currentWidget() is self.demo_tab',methods['poll_once'])
        self.assertIn('self.auto_poll.isChecked()',methods['poll_once'])
        self.assertIn('self.demo_sample_rate.setText',methods['on_success'])

    def test_demo_only_limit_and_current_display(self):
        src=(ROOT/'main.py').read_text(encoding='utf-8')
        tree=ast.parse(src)
        window=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CI76Window')
        fn=next(n for n in window.body if isinstance(n,ast.FunctionDef) and n.name=='_build_demo_tab')
        build=ast.get_source_segment(src,fn)
        self.assertIn('self.demo_slider',build)
        self.assertIn('self.demo_current_dial',build)
        self.assertIn('self.demo_restore_btn',build)
        for attr in ('self.demo_mode_btn','self.demo_ext_btn','self.demo_ret_btn',
                     'self.demo_stop_btn','self.demo_mode_select','self.demo_speed_apply'):
            self.assertNotIn(attr,build)
        self.assertNotIn('Demo 自動快速監控',build)
        self.assertIn('QProgressBar',build)

if __name__=='__main__': unittest.main()
