"""Compatibility playback through the website player; no synthetic completion POST."""
import json
import time
from urllib.parse import parse_qs, urlsplit

from core import HOST, ORIGIN, UserError, LoginNeeded, check_stop, safe_path, target_list


class StallGuard:
    def __init__(self, now):
        self.last_time = None
        self.last_progress = now
        self.attempted = False
        self.reloads = 0

    def observe(self, media_time, now):
        if media_time is not None and (self.last_time is None or media_time > self.last_time + .2):
            self.last_progress = now
            self.attempted = False
        self.last_time = media_time
        if now - self.last_progress < 10:
            return None
        self.last_progress = now
        if not self.attempted:
            self.attempted = True
            return 'resume'
        if self.reloads < 2:
            self.reloads += 1
            self.last_time = None
            # Keep recovery state until actual playback advances.
            return 'reload'
        return 'stop'


def click_point(cdp, point):
    if not point:
        return False
    for kind in ['mousePressed', 'mouseReleased']:
        cdp.call('Input.dispatchMouseEvent', {'type':kind, 'x':point['x'], 'y':point['y'],
                                            'button':'left', 'clickCount':1})
    return True


def click_link(client, href):
    absolute = ORIGIN + safe_path(href, client.track)
    point = client.cdp.evaluate('''(()=>{
        const link=Array.from(document.querySelectorAll('a[href]')).find(a=>a.href===%s);
        if(!link)return null;
        link.scrollIntoView({block:'center'});const r=link.getBoundingClientRect();
        return r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null;
    })()''' % json.dumps(absolute))
    return click_point(client.cdp, point)


def enter_resource(client, resource):
    href = safe_path(resource['href'], client.track)
    expected = parse_qs(urlsplit(href).query)
    if not click_link(client, href):
        parent = resource.get('parent')
        if parent:
            client.cdp.call('Page.navigate', {'url':ORIGIN + safe_path(parent, client.track)})
            client.stop.wait(2)
        if not click_link(client, href):
            # For multi-part courses, enter its observed course link before choosing the part.
            seed = client.cdp.evaluate('''Array.from(document.querySelectorAll('a[href]')).find(a=>
                new URL(a.href).pathname.startsWith(%s) && new URL(a.href).searchParams.get('v_id')===%s)?.href'''
                % (json.dumps('/' + client.track + '/'), json.dumps(expected.get('v_id',[''])[0])))
            if seed:
                click_link(client, seed)
                client.stop.wait(2)
                click_link(client, href)
            else:
                raise UserError('无法在课程列表找到当前视频的入口。请在课程浏览器打开目标课程后再试，未强行跳转地址。')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        check_stop(client.stop)
        same_video = []
        for target in target_list(client.port):
            current = urlsplit(target['url'])
            q = parse_qs(current.query)
            if current.path == '/' + client.track + '/play' and q.get('v_id') == expected.get('v_id'):
                same_video.append(target)
                if expected.get('r_id') and q.get('r_id') != expected['r_id']:
                    continue
                client.attach(target)
                return target['url']
        if same_video:
            client.attach(same_video[0])
            click_link(client, href)
        client.stop.wait(.5)
    raise UserError('点击课程入口后没有进入预期视频，已停止。请把最后的提示发给维护者。')


def resume_player(client):
    result = client.cdp.evaluate(r'''(()=>{
        const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
        const point=e=>{e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}};
        for(const b of document.querySelectorAll('button,a.public_cancel,a.public_submit')){
            if(!visible(b)||b.disabled)continue;
            const label=b.textContent.trim();
            if(!['继续','继续播放','继续观看','我知道了'].includes(label))continue;
            let node=b.parentElement;
            for(let depth=0;node&&depth<6;depth++,node=node.parentElement){
                const text=node.innerText||'';
                const known=(label==='继续播放'&&text.includes('继续观看'))||
                  (label==='继续'&&text.includes('视频已暂停'))||
                  ((label==='继续观看'||label==='我知道了')&&b.matches('a.public_cancel,a.public_submit'));
                if(known)return {kind:label,point:point(b)};
            }
        }
        const v=document.querySelector('video');
        if(!v||v.ended||!v.paused)return null;
        for(const selector of ['.xgplayer-start','.xgplayer-play','.vjs-big-play-button','.vjs-play-control',
            '.prism-big-play-btn','button.plyr__control--overlaid','button[data-plyr="play"]','button[aria-label="Play"]']){
            const e=Array.from(document.querySelectorAll(selector)).find(visible);
            if(e)return {kind:'播放器播放按钮',point:point(e)};
        }
        return {kind:'video.play',direct:true};
    })()''')
    if result and result.get('point'):
        click_point(client.cdp, result['point'])
        return result['kind']
    if result and result.get('direct'):
        # Do not add browser-native controls or touch currentTime/playbackRate.
        client.cdp.evaluate("(()=>{const v=document.querySelector('video');if(v&&v.paused&&!v.ended){v.muted=true;v.play().catch(()=>{});}return true;})()")
        return result['kind']
    return None


def watch_resource(client, expected_url):
    guard = StallGuard(time.monotonic())
    next_heartbeat = 0
    next_resume = 0
    while True:
        check_stop(client.stop)
        state = client.cdp.evaluate("(()=>{const v=document.querySelector('video');return {url:location.href,missing:!v,time:v?.currentTime||0,duration:Number.isFinite(v?.duration)?v.duration:null,paused:v?.paused,ended:v?.ended,error:v?.error?.code};})()")
        url = urlsplit(state['url'])
        if url.hostname != HOST or url.path != '/' + client.track + '/play':
            raise UserError('课程页已离开或登录失效，已停止播放监控。')
        expected = parse_qs(urlsplit(expected_url).query)
        actual = parse_qs(url.query)
        if actual.get('v_id') != expected.get('v_id') or (expected.get('r_id') and actual.get('r_id') != expected['r_id']):
            raise UserError('正在播放的视频已改变，已停止，避免误操作其他课程。')
        if state['ended']:
            client.stop.wait(2)  # Allow the site's own ended handler to save progress.
            client.emit('播放器已结束；接下来读取平台状态，尚不据此宣告课程完成。')
            return
        now = time.monotonic()
        if now >= next_resume:
            action = resume_player(client)
            if action:
                client.emit('已点击/触发：' + action)
            next_resume = now + 4
        step = guard.observe(None if state['missing'] else state['time'], now)
        if step == 'resume':
            client.emit('播放连续 10 秒未前进，先尝试继续播放。')
            resume_player(client)
        elif step == 'reload':
            client.emit('恢复后仍未前进，刷新当前播放页（' + str(guard.reloads) + '/2）；刷新后自动处理继续播放弹窗。')
            client.cdp.call('Page.reload', {})
            client.stop.wait(2)
        elif step == 'stop':
            raise UserError('当前视频连续恢复失败，已停止并保留页面，不会无限刷新。请查看是否需要重新登录或人工处理。')
        if now >= next_heartbeat:
            client.emit('播放位置 ' + str(int(state['time'])) + ' 秒' + (' / ' + str(int(state['duration'])) + ' 秒' if state['duration'] else '；等待播放器加载'))
            next_heartbeat = now + 30
        client.stop.wait(2)


def try_formal(client):
    try:
        return client.formal_status()
    except LoginNeeded:
        raise
    except UserError as exc:
        if any(fragment in str(exc) for fragment in ['未识别到本类别', '正式学时页面结构', 'HTTP 404']):
            client.emit('此页面暂不支持正式学时自动读取；继续正常播放，最终完成状态需在官网确认。')
            return None
        raise


def run_playback(client):
    client.emit('兼容模式：正常播放视频；处理继续弹窗，卡住 10 秒开始恢复，不直接提交观看记录。')
    groups = client.scan(playback=True)
    formal = try_formal(client)
    ended = 0
    for vid, group in groups.items():
        check_stop(client.stop)
        if formal and formal.get(vid, {}).get('status') == '已完成':
            client.emit('平台已完成，跳过：' + group['title'])
            continue
        client.emit('进入课程：' + group['title'])
        for resource in group['resources']:
            expected_url = enter_resource(client, resource)
            watch_resource(client, expected_url)
            ended += 1
        formal = try_formal(client)
        if formal and formal.get(vid, {}).get('status') != '已完成':
            raise UserError('视频播放已结束，但平台正式课程尚未完成，已停止，请检查官网状态。')
    formal = try_formal(client)
    confirmed = sum(formal.get(v, {}).get('status') == '已完成' for v in groups) if formal else None
    client.emit(f'播放处理结束：本轮播放结束 {ended} 段；' + (f'平台确认 {confirmed}/{len(groups)} 门完成。' if formal else '平台完成状态待官网确认。'))
    return {'track':client.track,'mode':'playback','term':client.term,'total':len(groups),
            'completed':confirmed,'played_to_end':ended,'submitted':0,'platform_verified':confirmed==len(groups) if formal else False}
