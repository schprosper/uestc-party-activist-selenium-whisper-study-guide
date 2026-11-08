"""Portable, account-independent DXPX client. No bundled identity or session."""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
import websocket

HOST = 'dxpx.uestc.edu.cn'
ORIGIN = 'https://' + HOST
TRACKS = {'jjfz': '积极分子', 'fzdx': '发展对象'}
KINDS = {'单选题': 'radios', '多选题': 'checkboxes', '判断题': 'yes_or_nos', '填空题': 'gap_fillings'}
VERSION = '1.2'


class UserError(Exception):
    pass


class Cancelled(UserError):
    pass


class LoginNeeded(UserError):
    pass


def local_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'UESTC_DXPX_Helper'


def check_stop(stop):
    if stop.is_set():
        raise Cancelled('已停止后续操作，浏览器保持打开。')


def safe_path(value, track):
    u = urlsplit(html.unescape(value))
    if u.scheme and u.scheme != 'https':
        raise UserError('页面包含非 HTTPS 链接，已停止。')
    if u.netloc and u.netloc != HOST:
        raise UserError('页面包含外部站点链接，已停止。')
    if not (u.path.startswith('/' + track + '/') or u.path == '/user/training/lesson'):
        raise UserError('链接不属于当前培训类别，已停止。')
    return u.path + ('?' + u.query if u.query else '')


def browser_executable():
    candidates = []
    for base in (os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('LOCALAPPDATA', '')):
        for suffix in ('Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe'):
            candidates.append(Path(base) / suffix)
    for item in candidates:
        if item.is_file():
            return item
    raise UserError('未找到 Chrome 或 Edge。请先安装其中一个浏览器，再打开本程序。')


def local_get(port, path, method='GET'):
    # Local browser traffic must not go through a system HTTP proxy.
    with requests.Session() as session:
        session.trust_env = False
        response = session.request(method, f'http://127.0.0.1:{port}{path}', timeout=2)
        response.raise_for_status()
        return response.json()


def browser_port(profile):
    try:
        port = int((profile / 'DevToolsActivePort').read_text().splitlines()[0])
        local_get(port, '/json/version')
        return port
    except (OSError, ValueError, IndexError, requests.RequestException):
        return None


def ensure_browser(track, stop, emit):
    profile = local_root() / track / 'browser'
    profile.mkdir(parents=True, exist_ok=True)
    port = browser_port(profile)
    if port:
        emit('已连接本类别的课程浏览器。')
        return port
    exe = browser_executable()
    emit('正在打开课程浏览器；首次使用请在官网登录，验证码由本人完成。')
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 4  # SW_SHOWNOACTIVATE: interactive window, no forced focus.
    subprocess.Popen([str(exe), '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
                      '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check', ORIGIN + '/'],
                     startupinfo=startup, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        check_stop(stop)
        port = browser_port(profile)
        if port:
            return port
        stop.wait(.5)
    raise UserError('课程浏览器连接超时。请检查浏览器是否正常打开；不用关闭日常浏览器。')


class CDP:
    def __init__(self, target):
        self.target = target['id']
        self.ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=25,
                                             suppress_origin=True, http_no_proxy=['127.0.0.1', 'localhost'])
        self.sequence = 0

    def call(self, method, params=None):
        self.sequence += 1
        ident = self.sequence
        self.ws.send(json.dumps({'id': ident, 'method': method, 'params': params or {}}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = json.loads(self.ws.recv())
            if message.get('id') != ident:
                continue
            if 'error' in message:
                raise UserError('浏览器操作未完成，请检查课程页面后重试。')
            return message.get('result', {})
        raise UserError('浏览器响应超时；已停止，不会循环提交。')

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in result:
            raise UserError('当前页面结构无法识别，请保留页面并留下反馈。')
        return result.get('result', {}).get('value')

    def close(self):
        self.ws.close()  # Never Browser.close or Target.closeTarget.


def target_list(port):
    return [t for t in local_get(port, '/json/list') if t.get('type') == 'page'
            and urlsplit(t.get('url', '')).hostname == HOST]


class Client:
    def __init__(self, track, port, stop=None, emit=None):
        if track not in TRACKS:
            raise ValueError('unknown track')
        self.track, self.port = track, port
        self.stop = stop or threading.Event()
        self.emit = emit or (lambda message: None)
        self.term = None
        self.cdp = None
        self.http = requests.Session()
        self.http.headers['User-Agent'] = 'Mozilla/5.0'

    def close(self):
        self.http.close()
        if self.cdp:
            self.cdp.close()

    def attach(self, target):
        if self.cdp and self.cdp.target == target['id']:
            return
        if self.cdp:
            self.cdp.close()
        self.cdp = CDP(target)

    def sync(self):
        self.http.cookies.clear()
        for c in self.cdp.call('Network.getCookies', {'urls': [ORIGIN + '/']}).get('cookies', []):
            domain = c['domain'].lstrip('.')
            if domain == HOST or HOST.endswith('.' + domain):
                self.http.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'], secure=c.get('secure', True))
        self.http.headers['User-Agent'] = self.cdp.evaluate('navigator.userAgent')

    def connect(self, wait=True):
        deadline = time.monotonic() + (600 if wait else 3)
        last_notice = ''
        navigated = set()
        while time.monotonic() < deadline:
            check_stop(self.stop)
            targets = target_list(self.port)
            if not targets:
                local_get(self.port, '/json/new?' + ORIGIN + '/', method='PUT')
                self.stop.wait(1)
                continue
            ranked = sorted(targets, key=lambda t: urlsplit(t['url']).path.startswith('/' + self.track + '/'), reverse=True)
            notice = '请在课程浏览器登录，并进入本期' + TRACKS[self.track] + '课程。登录后自动继续。'
            for target in ranked:
                self.attach(target)
                page = self.cdp.evaluate("({url:location.href,text:document.body?.innerText||'',links:Array.from(document.querySelectorAll('a[href]')).map(a=>({href:a.href,text:a.textContent.trim()}))})")
                parsed = urlsplit(page['url'])
                if parsed.path.startswith(('/login', '/user/login')):
                    continue
                query = parse_qs(parsed.query)
                if parsed.path.startswith('/' + self.track + '/'):
                    term = query.get('stg', [None])[0]
                    if term is not None and not term.isdigit():
                        raise UserError('页面学期参数无效。')
                    # Never reuse another person's saved stage. Legacy JJFZ can omit stg.
                    if term or self.track == 'jjfz':
                        self.term = term
                        self.sync()
                        try:
                            self.fetch(self.path('lesson'))
                        except LoginNeeded:
                            if not wait:
                                raise
                            # The official login page is interactive; no credential handling here.
                            self.cdp.call('Page.navigate', {'url': ORIGIN + '/user/login'})
                            break
                        self.emit('已识别' + TRACKS[self.track] + ('，学期 ' + term if term else '（页面未使用学期参数）') + '。')
                        return
                links = []
                for item in page['links']:
                    url = urlsplit(item['href'])
                    if url.hostname == HOST and url.path in ('/' + self.track + '/', '/' + self.track, '/' + self.track + '/lesson'):
                        if item['href'] not in navigated:
                            links.append(item)
                stages = {parse_qs(urlsplit(x['href']).query).get('stg', [''])[0] for x in links}
                if len(stages) == 1 and links:
                    link = links[0]['href']
                    navigated.add(link)
                    self.cdp.call('Page.navigate', {'url': link})
                    break
                if len(stages) > 1:
                    notice = '账号有多个培训期，请在浏览器点击本次要处理的培训期，随后自动继续。'
            if notice != last_notice:
                self.emit(notice)
                last_notice = notice
            self.stop.wait(2)
        raise UserError('十分钟内未识别到本期课程。浏览器已保留，进入课程后再点启动即可。' if wait else '未发现已登录的本期课程。')

    def path(self, suffix, **params):
        if self.term is not None:
            params['stg'] = self.term
        return '/' + self.track + '/' + suffix + ('?' + urlencode(params) if params else '')

    def fetch(self, path, data=None):
        check_stop(self.stop)
        path = safe_path(path, self.track)
        if urlsplit(path).path == '/user/training/lesson' and data is not None:
            raise UserError('正式进度页面只允许读取。')
        method = 'POST' if data is not None else 'GET'
        try:
            response = self.http.request(method, ORIGIN + path, data=data, timeout=(5, 20), allow_redirects=False)
        except requests.RequestException:
            raise UserError('网络中断或超时，已停止。提交不会自动重试；恢复网络后重新核验。') from None
        if response.is_redirect:
            destination = urlsplit(response.headers.get('Location', ''))
            if destination.path.startswith(('/login', '/user/login')):
                raise LoginNeeded('登录已过期，请在课程浏览器重新登录，然后再次启动。')
            raise UserError('登录已过期或平台发生跳转。请在课程浏览器重新登录，然后再次启动。')
        if response.status_code != 200:
            raise UserError('平台返回 HTTP ' + str(response.status_code) + '，已停止。')
        response.encoding = 'utf-8'
        body = response.text
        if '访问路径有误' in body or re.search(r'<title>[^<]*(?:错误|平台-登录)', body):
            raise UserError('平台未接受当前页面路径或登录已失效，请重新进入本期课程。')
        return body

    def parse(self, body, code):
        return self.cdp.evaluate('(()=>{const doc=new DOMParser().parseFromString(' + json.dumps(body) + ',"text/html");' + code + '})()')

    def dom(self, path, code):
        return self.parse(self.fetch(path), code)

    def scan(self, playback=False):
        links = self.dom(self.path('lesson'), "return Array.from(doc.querySelectorAll('a[href]')).map(a=>a.getAttribute('href'));")
        lessons = sorted({parse_qs(urlsplit(html.unescape(x)).query)['lesson_id'][0] for x in links
                          if '/' + self.track + '/lesson/video' in x and 'lesson_id=' in x})
        if not lessons:
            raise UserError('未找到本期课程专题，不能报告已完成。')
        seeds = {}
        for lid in lessons:
            page, total = 1, 1
            while page <= total:
                result = self.dom(self.path('lesson/video', lesson_id=lid, cat=1, page=page), """
                    return {text:doc.body.textContent,links:Array.from(doc.querySelectorAll('a[href]')).map(a=>({href:a.getAttribute('href'),title:a.textContent.trim()}))};
                """)
                found = 0
                for item in result['links']:
                    u = urlsplit(html.unescape(item['href']))
                    q = parse_qs(u.query)
                    if u.path == '/' + self.track + '/lesson/video' and q.get('page') and q.get('lesson_id', [lid])[0] == lid:
                        total = max(total, int(q['page'][0]))
                    if u.path.startswith('/' + self.track + '/') and q.get('v_id'):
                        item['parent'] = self.path('lesson/video', lesson_id=lid, cat=1, page=page)
                        seeds.setdefault(q['v_id'][0], item)
                        found += 1
                if not found and not re.search(r'共\s*0\s*页', result['text']):
                    raise UserError('专题课程列表为空或页面已改变，停止以免漏项。')
                if total > 50:
                    raise UserError('课程分页数量异常。')
                page += 1
            self.emit('已读取专题 ' + lid + '。')
        groups = {}
        for vid, seed in seeds.items():
            links = self.dom(safe_path(seed['href'], self.track), "return Array.from(doc.querySelectorAll('a[href]')).map(a=>({href:a.getAttribute('href'),title:a.textContent.trim()}));")
            resources = {}
            for item in [seed] + links:
                u = urlsplit(html.unescape(item['href']))
                q = parse_qs(u.query)
                if u.path == '/' + self.track + '/play' and q.get('v_id', [''])[0] == vid and q.get('r_id'):
                    item['href'] = safe_path(item['href'], self.track)
                    item['parent'] = seed['parent']
                    resources[q['r_id'][0]] = item
            if not resources:
                if playback and urlsplit(html.unescape(seed['href'])).path == '/' + self.track + '/play':
                    groups[vid] = {'title': seed['title'], 'resources': [seed]}
                    continue
                # Some single-resource courseware exposes identity only in the page's record block.
                body = self.fetch(safe_path(seed['href'], self.track))
                record = record_payload(body, self.track, self.term, vid)
                resources[record[1]['resource_id']] = seed
            groups[vid] = {'title': seed['title'], 'resources': list(resources.values())}
        if not groups:
            raise UserError('没有发现必修课程，不能报告完成。')
        return groups

    def formal_status(self):
        params = {'stg': self.term} if self.term else {}
        rows = self.dom('/user/training/lesson' + ('?' + urlencode(params) if params else ''), """
            return Array.from(doc.querySelectorAll('.study_plan2')).map(card=>{
                const a=card.querySelector('a.plan_a');
                if(!a)return null;
                return {href:a.getAttribute('href'),title:a.textContent.trim(),status:Array.from(card.querySelectorAll('div')).map(x=>x.textContent.trim()).find(t=>t==='已完成'||t==='未完成'),hours:Number(card.textContent.match(/学时：\s*([\d.]+)/)?.[1])};
            }).filter(Boolean);
        """)
        selected = {}
        for row in rows:
            u = urlsplit(html.unescape(row['href']))
            q = parse_qs(u.query)
            if not u.path.startswith('/' + self.track + '/') or not q.get('v_id'):
                continue
            if self.term and q.get('stg', [self.term])[0] != self.term:
                continue
            if row.get('status') not in ('已完成', '未完成') or row.get('hours') is None:
                raise UserError('正式学时页面结构已改变，无法可靠核验，请留下反馈。')
            selected[q['v_id'][0]] = row
        if not selected:
            raise UserError('未识别到本类别的正式课程状态，已停止，不能把接口成功当作已完成。')
        return selected

    def run_videos(self, write=False):
        groups = self.scan()
        formal = self.formal_status()
        if set(groups) != set(formal):
            raise UserError('必修清单和正式课程清单不一致，已停止，请留下反馈。')
        submitted = 0
        for vid, group in groups.items():
            check_stop(self.stop)
            status = formal[vid]['status']
            self.emit(status + '：' + group['title'])
            if status == '已完成' or not write:
                continue
            for resource in group['resources']:
                body = self.fetch(safe_path(resource['href'], self.track))
                q = parse_qs(urlsplit(html.unescape(resource['href'])).query)
                endpoint, data = record_payload(body, self.track, self.term, vid, q.get('r_id', [None])[0])
                response = json.loads(self.fetch(endpoint, data))
                if str(response.get('code')) != '1':
                    raise UserError('平台未接受课程记录，已停止，不循环尝试。')
                submitted += 1
            formal = self.formal_status()
            if formal.get(vid, {}).get('status') != '已完成':
                raise UserError('提交后正式课程仍未完成，已停止；不能报告成功。')
            self.emit('平台已确认完成：' + group['title'])
        formal = self.formal_status()
        theory = self.dom(self.path('lesson'), "return Array.from(doc.querySelectorAll('.expand_text1')).find(x=>x.textContent.includes('现理论学习'))?.textContent.trim()||'';")
        report = {'track': self.track, 'term': self.term, 'total': len(groups),
                  'completed': sum(v['status'] == '已完成' for v in formal.values()), 'submitted': submitted,
                  'hours': round(sum(v['hours'] for v in formal.values() if v['status'] == '已完成'), 2), 'theory': theory}
        self.emit(f"核验结果：{report['completed']}/{report['total']} 门完成，{report['hours']} 学时，本轮提交 {submitted} 段。")
        if theory:
            self.emit(' '.join(theory.split()))
        return report


def record_payload(body, track, term, vid, rid=None):
    """Extract only the matching record request, never a progress/heartbeat ID."""
    results = []
    for script in re.findall(r'<script\b[^>]*>([\s\S]*?)</script>', body, re.I):
        pattern = r'url\s*:\s*[\"\'](/' + track + r'/(?:play|lesson)/resource_record)[\"\']'
        for match in re.finditer(pattern, script):
            tail = script[match.end():]
            data = re.match(r'[\s\S]{0,600}?\bdata\s*:\s*\{([^}]+)\}', tail)
            if not data:
                continue
            values = {}
            for key in ('rid', 'resource_id', 'video_id', 'lesson_id', 'stg'):
                field = re.search(r'\b' + key + r'\s*:\s*[\"\']?(\d+)[\"\']?\s*[,}]?', data[1])
                if field:
                    values[key] = field[1]
            if not all(x in values for x in ('rid', 'resource_id', 'video_id', 'lesson_id')):
                continue
            if values['video_id'] != str(vid) or (rid and values['resource_id'] != str(rid)):
                continue
            if term and values.get('stg', str(term)) != str(term):
                continue
            if term:
                values['stg'] = str(term)
            results.append((match[1], values))
    # Parse input attributes without assuming attribute order.
    from html.parser import HTMLParser
    class Tokens(HTMLParser):
        token = None
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == 'input' and a.get('name') == '_xsrf':
                self.token = a.get('value')
    parser = Tokens()
    parser.feed(body)
    unique = {json.dumps(x, sort_keys=True): x for x in results}
    if len(unique) != 1 or not parser.token:
        raise UserError('无法唯一确认当前视频的记录参数，已停止；请留下反馈。')
    endpoint, data = next(iter(unique.values()))
    data['_xsrf'] = parser.token
    return endpoint, data


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', html.unescape(str(value))))


def title_key(value):
    return re.sub(r'[\W_]+', '', normalize(value))


def option_key(value):
    return normalize(re.sub(r'^\s*[A-Z][、.:：．]\s*', '', str(value)))


def resolve(question, banks):
    answers = set()
    for row in banks.get((question['kind'], title_key(question['title'])), []):
        if question['kind'] == 'gap_fillings':
            answer = normalize(row['correct_answer']).replace(',', '，')
            if answer and '|' not in answer and answer.lower() not in ('nan', 'none', 'error!', 'unknownanswer'):
                answers.add(answer)
            continue
        old = [option_key(x) for x in row.get('options', [])]
        new = [option_key(x['text']) for x in question['options']]
        if sorted(old) != sorted(new) or len(set(new)) != len(new):
            continue
        letters = re.findall('[A-Z]', str(row['correct_answer']))
        if not letters or any(ord(x) - 65 >= len(old) for x in letters):
            continue
        if question['kind'] != 'checkboxes' and len(letters) != 1:
            continue
        answers.add('|'.join(sorted(question['options'][new.index(old[ord(x)-65])]['value'] for x in letters)))
    return next(iter(answers)) if len(answers) == 1 else None


def load_banks(path):
    banks = {}
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    for row in rows:
        banks.setdefault((row['kind'], title_key(row['title'])), []).append(row)
    return banks


def exam_route(track, url):
    p = urlsplit(url)
    if p.hostname != HOST:
        raise UserError('请进入官网的测试页面。')
    q = parse_qs(p.query)
    if p.path == f'/{track}/exam_center/' + ('exam' if track == 'fzdx' else 'end_exam'):
        return f'/{track}/exam_center', {}
    if track == 'jjfz' and p.path == '/jjfz/lesson/exam':
        lid = q.get('lesson_id', q.get('lid', [None]))[0]
        if lid and lid.isdigit():
            return '/jjfz/lesson/exam', {'lid': lid}
    raise UserError('请先在官网进入要处理的综合测试或章节测试。本功能不自行开考。')


def saved_answer(q):
    if q['kind'] == 'gap_fillings':
        return normalize(q.get('written', ''))
    return '|'.join(sorted(x['value'] for x in q['options'] if x['checked']))


def fill_active_exam(client, banks):
    # Select an already open test only; never visit a start-exam URL.
    candidates = []
    for t in target_list(client.port):
        try:
            exam_route(client.track, t['url'])
            candidates.append(t)
        except UserError:
            pass
    if len(candidates) != 1:
        raise UserError('请只保留一个已开始的综合/章节测试页面，再点击填写。')
    client.attach(candidates[0])
    origin_url = candidates[0]['url']
    base, extra = exam_route(client.track, origin_url)
    term = parse_qs(urlsplit(origin_url).query).get('stg', [None])[0]
    if term:
        extra['stg'] = term
    client.sync()
    count = client.cdp.evaluate("document.querySelectorAll('.exam_ul li').length")
    if not isinstance(count, int) or not 1 <= count <= 150:
        raise UserError('未识别到有效答题卡，停止。')
    token = client.cdp.evaluate("document.querySelector('input[name=\"_xsrf\"]')?.value")
    if not token:
        raise UserError('测试页缺少请求校验参数，请重新进入页面。')

    def read(index):
        check_stop(client.stop)
        if client.cdp.evaluate('location.href') != origin_url:
            raise UserError('测试页面发生变化，已停止。')
        item = client.dom(base + '/get_question?' + urlencode(dict(extra, i=index)), r"""
            const mark=doc.querySelector('.exam_label_btn');
            return {index:Number(mark?.getAttribute('data-index')),qid:Number(mark?.getAttribute('data-val')),
                title:doc.querySelector('h2.exam_h2')?.textContent.trim().replace(/^\d+\.\s*/,''),
                type:doc.querySelector('.e_cont_title span')?.textContent.trim(),
                options:Array.from(doc.querySelectorAll('label')).filter(x=>x.querySelector('input')).map(x=>({text:x.textContent.trim(),value:x.querySelector('input').value,checked:x.classList.contains('checked')||x.querySelector('input').checked})),
                written:doc.querySelector('.summary_question')?.value||''};
        """)
        if item['index'] != index or not item['qid'] or not item.get('title') or item.get('type') not in KINDS:
            raise UserError('题目结构改变，已停止。')
        item['kind'] = KINDS[item['type']]
        return item

    plan = []
    for index in range(1, count + 1):
        item = read(index)
        item['answer'] = resolve(item, banks)
        plan.append(item)
    if len({q['qid'] for q in plan}) != count:
        raise UserError('题目身份重复，已停止。')
    filled, unresolved, preserved = 0, [], 0
    for item in plan:
        live = read(item['index'])
        if live['qid'] != item['qid'] or live['title'] != item['title'] or [(x['text'], x['value']) for x in live['options']] != [(x['text'], x['value']) for x in item['options']]:
            raise UserError('题干或选项改变，已停止，避免写入其他试卷。')
        if saved_answer(live):
            preserved += 1
            continue
        if not item['answer']:
            unresolved.append(item['index'])
            continue
        data = dict(extra, i=item['index'], qid=item['qid'], answer=item['answer'], _xsrf=token)
        response = json.loads(client.fetch(base + '/answer?' + urlencode({'i': item['index']}), data))
        if str(response.get('code')) != '1':
            raise UserError('平台未接受答案保存，已停止。')
        checked = read(item['index'])
        if checked['qid'] != item['qid'] or saved_answer(checked) != normalize(item['answer']):
            raise UserError('答案保存后核对不一致，已停止。')
        filled += 1
        client.emit('已保存并核对第 ' + str(item['index']) + ' 题。')
    client.emit(f'填写结束：新增 {filled} 题，保留已有答案 {preserved} 题，待本人处理 {len(unresolved)} 题。')
    if unresolved:
        client.emit('待处理题号：' + '、'.join(map(str, unresolved)))
    client.emit('请在官网检查答案后交卷。本程序没有自动交卷或重复开考。')
    return {'total': count, 'filled': filled, 'preserved': preserved, 'unresolved': unresolved, 'submitted': False}
