"""Real Chromium DOM parsing with synthetic accounts; no live platform writes."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Client, CDP, browser_executable, browser_port, local_get
from test_core import fixture

root = Path(__file__).resolve().parents[1]
profile = Path(tempfile.mkdtemp(prefix='dxpx-fixture-', dir=root / 'audit'))
proc = subprocess.Popen([str(browser_executable()), '--headless=new', '--remote-debugging-port=0',
                         '--user-data-dir=' + str(profile), '--no-first-run', 'about:blank'],
                        creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
results = []
try:
    deadline = time.monotonic() + 30
    port = None
    while time.monotonic() < deadline:
        port = browser_port(profile)
        if port:
            break
        time.sleep(.2)
    if not port:
        raise RuntimeError('fixture browser startup failed')
    target = next(t for t in local_get(port, '/json/list') if t['type'] == 'page')
    for track in ['jjfz','fzdx']:
        c = Client(track, port)
        c.term = '7'
        c.cdp = CDP(target)
        submitted = []
        completed = False
        def fetch(path, data=None):
            global completed
            if data is not None:
                assert path == f'/{track}/play/resource_record'
                assert data['video_id'] == '33' and data['resource_id'] == '22'
                submitted.append(dict(data))
                completed = True
                return '{"code":1}'
            if path.startswith(f'/{track}/lesson?'):
                return f'<a href="/{track}/lesson/video?lesson_id=44&stg=7">专题</a><div class="expand_text1">现理论学习已完成</div>'
            if path.startswith(f'/{track}/lesson/video?'):
                return f'<div class="l_list_right"><h2><a href="/{track}/play?v_id=33&r_id=22&stg=7">模拟课程</a></h2></div>'
            if path.startswith(f'/{track}/play?'):
                return fixture(track) + f'<a href="/{track}/play?v_id=33&r_id=22&stg=7">第一节</a>'
            if path.startswith('/user/training/lesson'):
                state = '已完成' if completed else '未完成'
                return f'<div class="study_plan2"><a class="plan_a" href="/{track}/play?v_id=33&stg=7">模拟课程</a><div>{state}</div><div>学时：1.5</div></div>'
            raise AssertionError('unexpected fixture request')
        c.fetch = fetch
        first = c.run_videos(write=True)
        second = c.run_videos(write=True)
        assert first['completed'] == 1 and first['submitted'] == 1
        assert second['submitted'] == 0
        assert len(submitted) == 1
        results.append({'track':track, 'first':first, 'second':second, 'network_writes':False, 'real_chromium_dom':True})
        c.close()
    (root/'audit'/'browser-fixture-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: both tracks, real Chromium DOM, synthetic records, completed-course rerun skipped')
finally:
    # Only this fresh headless test process; never touch a user's browser.
    proc.terminate()
    proc.wait(timeout=15)
    time.sleep(1)
    # No credentials were used; keep temporary fixtures on failed cleanup for diagnosis.
    if profile.resolve().parent == (root/'audit').resolve() and profile.name.startswith('dxpx-fixture-'):
        try:
            shutil.rmtree(profile)
        except OSError:
            pass
