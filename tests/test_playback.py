import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from playback import StallGuard


class PlaybackTests(unittest.TestCase):
    def test_resume_before_reload_and_stop_after_two_reloads(self):
        g = StallGuard(0)
        self.assertIsNone(g.observe(0, 0))
        self.assertIsNone(g.observe(0, 9))
        self.assertEqual(g.observe(0, 10), 'resume')
        self.assertEqual(g.observe(0, 20), 'reload')
        self.assertIsNone(g.observe(0, 21))
        self.assertEqual(g.observe(0, 31), 'resume')
        self.assertEqual(g.observe(0, 41), 'reload')
        self.assertIsNone(g.observe(0, 42))
        self.assertEqual(g.observe(0, 52), 'resume')
        self.assertEqual(g.observe(0, 62), 'stop')

    def test_real_progress_resets_stall_timer(self):
        g = StallGuard(0)
        for now in range(100):
            self.assertIsNone(g.observe(now, now))
        self.assertEqual(g.reloads, 0)


if __name__ == '__main__':
    unittest.main()
