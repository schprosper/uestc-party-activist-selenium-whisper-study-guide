"""Exercise real decision logic with synthetic inputs; block external I/O."""
import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Client, UserError, resolve, title_key
from playback import StallGuard


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def demonstrate():
    results = []
    with ExitStack() as stack:
        for target in ('requests.sessions.Session.request',
                       'websocket.create_connection', 'subprocess.Popen'):
            stack.enter_context(patch(target, side_effect=AssertionError('Offline demo forbids external I/O')))
        guard = StallGuard(0)
        trace = []
        for now in (0, 10, 20, 21, 31, 41, 42, 52, 62):
            action = guard.observe(0, now)
            if action:
                trace.append({'second': now, 'action': action})
        require([row['action'] for row in trace] ==
                ['resume', 'reload', 'resume', 'reload', 'resume', 'stop'], 'Recovery budget changed')
        results.append({'scenario': 'bounded_recovery', 'pass': True, 'trace': trace})

        question = {'kind': 'radios', 'title': '示例：请选择苹果',
                    'options': [{'text': 'A. 梨', 'value': 'option-pear'},
                                {'text': 'B. 苹果', 'value': 'option-apple'}]}
        bank = {('radios', title_key(question['title'])):
                [{'options': ['A. 苹果', 'B. 梨'], 'correct_answer': 'A'}]}
        answer = resolve(question, bank)
        require(answer == 'option-apple', 'Option contents must determine the current ID')
        results.append({'scenario': 'reordered_options', 'pass': True, 'selected_id': answer})

        client = Client('fzdx', 0)
        try:
            client.term = '7'
            client.scan = Mock(return_value={'33': {'title': '合成课程', 'resources':
                               [{'href': '/fzdx/play?v_id=33&r_id=22'}]}})
            client.formal_status = Mock(return_value={'33': {'status': '已完成', 'hours': 1.5}})
            client.dom = Mock(return_value='现理论学习已完成')
            client.fetch = Mock(side_effect=AssertionError('Completed task must not write'))
            report = client.run_videos(write=True)
            require(report['completed'] == 1 and report['submitted'] == 0, 'Completed task was not skipped')
            client.fetch.assert_not_called()
            results.append({'scenario': 'completed_task_skipped', 'pass': True, 'submitted': 0})

            client.formal_status.return_value = {'33': {'status': '未完成', 'hours': 0}}
            body = '''<input name="_xsrf" value="synthetic-token">
            <script>$.ajax({url:'/fzdx/play/resource_record', type:'POST',
            data:{stg:'7',rid:'11',resource_id:'22',video_id:'33',lesson_id:'44',_xsrf:xsrf}});</script>'''
            client.fetch = Mock(side_effect=[body, '{"code":1}'])
            try:
                client.run_videos(write=True)
            except UserError as exc:
                require('正式课程仍未完成' in str(exc), 'Unexpected error during status verification')
                require(client.fetch.call_count == 2, 'Unexpected submission retry')
                results.append({'scenario': 'accepted_is_not_completed', 'pass': True,
                                'outcome': 'stopped_with_unconfirmed_completion'})
            else:
                raise AssertionError('Request acceptance must not imply business completion')
        finally:
            client.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print machine-readable results')
    args = parser.parse_args()
    results = demonstrate()
    if args.json:
        print(json.dumps({'synthetic': True, 'network_enabled': False, 'results': results}, indent=2))
    else:
        for row in results:
            print('PASS ' + row['scenario'])
        print('4 synthetic scenarios passed; no browser, account, or platform requests used.')


if __name__ == '__main__':
    main()
