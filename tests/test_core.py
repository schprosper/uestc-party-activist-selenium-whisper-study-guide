import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import (Client, UserError, Cancelled, check_stop, safe_path, record_payload,
                  resolve, title_key, exam_route, saved_answer)


def fixture(track='fzdx', term='7', token='test-token', endpoint='play'):
    stage = f'stg: "{term}",' if term else ''
    return f'''<input value="{token}" type="hidden" name="_xsrf">
    <script>const ignored={{url:'/{track}/play/progress',data:{{rid:'999'}}}};
    $.ajax({{url:'/{track}/{endpoint}/resource_record',type:'POST',data:{{{stage}
        rid:"11", resource_id:"22",video_id:"33",lesson_id:"44",_xsrf:xsrf}}}});</script>'''


class CoreTests(unittest.TestCase):
    def test_current_fzdx_record(self):
        endpoint, data = record_payload(fixture(), 'fzdx', '7', '33', '22')
        self.assertEqual(endpoint, '/fzdx/play/resource_record')
        self.assertEqual(data, dict(rid='11', resource_id='22', video_id='33', lesson_id='44', stg='7', _xsrf='test-token'))

    def test_legacy_jjfz_record(self):
        endpoint, data = record_payload(fixture('jjfz', '', endpoint='lesson'), 'jjfz', None, '33', '22')
        self.assertEqual(endpoint, '/jjfz/lesson/resource_record')
        self.assertNotIn('stg', data)

    def test_identity_and_stage_must_match(self):
        for term, vid, rid in [('8', '33', '22'), ('7', '34', '22'), ('7', '33', '23')]:
            with self.assertRaises(UserError):
                record_payload(fixture(), 'fzdx', term, vid, rid)

    def test_missing_token_or_ambiguous_record_stops(self):
        for body in [fixture(token=''), fixture() + fixture().replace('rid:"11"', 'rid:"12"')]:
            with self.assertRaises(UserError):
                record_payload(body, 'fzdx', '7', '33', '22')

    def test_request_scope(self):
        self.assertEqual(safe_path('https://dxpx.uestc.edu.cn/fzdx/play?a=1&amp;b=2', 'fzdx'), '/fzdx/play?a=1&b=2')
        for path in ['https://evil.test/fzdx/play', '//evil.test/fzdx/play', '/jjfz/play', '/user/login', 'http://dxpx.uestc.edu.cn/fzdx/play']:
            with self.assertRaises(UserError):
                safe_path(path, 'fzdx')

    def test_option_reordering_matches_contents(self):
        q = dict(kind='radios', title='题目', options=[dict(text='A. 乙', value='2'), dict(text='B. 甲', value='1')])
        banks = {('radios', title_key('题目')): [dict(options=['A.甲','B.乙'], correct_answer='A')]}
        self.assertEqual(resolve(q, banks), '1')
        banks[('radios', title_key('题目'))].append(dict(options=['A.甲','B.乙'], correct_answer='B'))
        self.assertIsNone(resolve(q, banks))

    def test_unknown_and_fill_alternatives_not_guessed(self):
        q = dict(kind='gap_fillings', title='填空')
        self.assertIsNone(resolve(q, {}))
        self.assertIsNone(resolve(q, {('gap_fillings', '填空'): [dict(correct_answer='十五|15')]}))
        self.assertNotEqual(title_key('应该'), title_key('不应该'))

    def test_exam_routes_exclude_final_and_new_exam_actions(self):
        for track, suffix in [('fzdx','exam'),('jjfz','end_exam')]:
            self.assertEqual(exam_route(track, f'https://dxpx.uestc.edu.cn/{track}/exam_center/{suffix}?stg=9')[0], f'/{track}/exam_center')
        self.assertEqual(exam_route('jjfz', 'https://dxpx.uestc.edu.cn/jjfz/lesson/exam?lesson_id=123')[1], {'lid':'123'})
        for url in ['https://dxpx.uestc.edu.cn/fzdx/exam_center/result', 'https://dxpx.uestc.edu.cn/fzdx/final/exam', 'https://evil.test/fzdx/exam_center/exam']:
            with self.assertRaises(UserError):
                exam_route('fzdx', url)

    def test_cancel_prevents_further_work(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            check_stop(event)

    def test_completed_courses_skip_writes(self):
        for track in ['fzdx', 'jjfz']:
            client = Client(track, 1)
            client.scan = Mock(return_value={'33':{'title':'课程','resources':[{'href':f'/{track}/play?v_id=33&r_id=22'}]}})
            client.formal_status = Mock(return_value={'33':dict(status='已完成', hours=1.5)})
            client.dom = Mock(return_value='现理论学习已完成')
            client.fetch = Mock(side_effect=AssertionError('Completed course must not write'))
            report = client.run_videos(write=True)
            self.assertEqual(report['submitted'], 0)
            self.assertEqual(report['completed'], 1)
            client.close()

    def test_platform_acceptance_alone_does_not_mean_completed(self):
        client = Client('fzdx', 1)
        client.term = '7'
        client.scan = Mock(return_value={'33':{'title':'课程','resources':[{'href':'/fzdx/play?v_id=33&r_id=22'}]}})
        client.formal_status = Mock(return_value={'33':dict(status='未完成', hours=0)})
        client.fetch = Mock(side_effect=[fixture(), '{"code":1}'])
        with self.assertRaisesRegex(UserError, '正式课程仍未完成'):
            client.run_videos(write=True)
        self.assertEqual(client.fetch.call_count, 2)
        client.close()

    def test_mismatched_lists_prevent_submission(self):
        client = Client('fzdx', 1)
        client.scan = Mock(return_value={'33':{}})
        client.formal_status = Mock(return_value={'34':dict(status='未完成',hours=0)})
        client.fetch = Mock()
        with self.assertRaises(UserError):
            client.run_videos(write=True)
        client.fetch.assert_not_called()
        client.close()

    def test_network_errors_do_not_retry_post(self):
        import requests
        client = Client('fzdx', 1)
        client.http.request = Mock(side_effect=requests.Timeout())
        with self.assertRaises(UserError):
            client.fetch('/fzdx/play/resource_record', {'rid':'1'})
        self.assertEqual(client.http.request.call_count, 1)
        client.close()

    def test_saved_checkbox_order(self):
        self.assertEqual(saved_answer(dict(kind='checkboxes', options=[dict(value='9',checked=True),dict(value='2',checked=True)])), '2|9')


if __name__ == '__main__':
    unittest.main()
