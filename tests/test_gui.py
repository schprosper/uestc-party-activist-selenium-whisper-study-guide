import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import app


class GuiTests(unittest.TestCase):
    def test_both_buttons_launch_and_recover_from_failure(self):
        root = tk.Tk()
        root.withdraw()
        ui = app.App(root)
        try:
            for track in ['jjfz','fzdx']:
                ui.track.set(track)
                fake = Mock()
                fake.run_videos.return_value = {'track':track,'total':1,'completed':1,'submitted':0}
                with patch.object(app, 'ensure_browser', return_value=1234), patch.object(app, 'Client', return_value=fake), patch.object(app, 'run_playback', return_value={'mode':'playback'}) as playback, patch.object(app, 'local_root', return_value=Path(__file__).resolve().parents[1]/'audit'/'gui-fixture-data'):
                    ui.start('videos')
                    deadline = time.monotonic()+5
                    while ui.running and time.monotonic()<deadline:
                        root.update()
                        time.sleep(.02)
                    self.assertFalse(ui.running)
                    if track == 'jjfz':
                        playback.assert_called_once_with(fake)
                        fake.run_videos.assert_not_called()
                    else:
                        fake.run_videos.assert_called_once_with(write=True)
                    fake.close.assert_called_once()
                    self.assertEqual(str(ui.start_button['state']), 'normal')
            with patch.object(app, 'ensure_browser', side_effect=app.UserError('模拟连接失败')), patch.object(app, 'local_root', return_value=Path(__file__).resolve().parents[1]/'audit'/'gui-fixture-data'):
                ui.start('check')
                deadline = time.monotonic()+5
                while ui.running and time.monotonic()<deadline:
                    root.update()
                    time.sleep(.02)
                self.assertFalse(ui.running)
                self.assertIn('模拟连接失败', ui.output.get('1.0', 'end'))
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
