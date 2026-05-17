# chrome.exe --remote-debugging-port=9222 --user-data-dir="D:/selenium_test"
# https://dxpx.uestc.edu.cn/
# https://dxpx.uestc.edu.cn/fzdx/lesson
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
from dxpx_transcribe import DxpxTranscriber, clean_text, clear_resource_timing, enable_network_capture, find_current_m3u8_url


class Main:
    def __init__(self):
        """
        selenium预处理
        """
        self.base_url = 'https://dxpx.uestc.edu.cn/fzdx/lesson'  # 基准url
        self.option = Options()
        self.option.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        self.option.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        try:
            self.wd = webdriver.Chrome(options=self.option)
            enable_network_capture(self.wd)
        except Exception as e:
            raise RuntimeError(
                "无法连接 Chrome 调试窗口。请先运行 launch_chrome_debug.ps1，"
                "在打开的 Chrome 中登录后再运行本脚本。"
            ) from e
        self.wd.implicitly_wait(15)  # 隐式等待
        self.wd.get(self.base_url)
        self.pause_seen_since = None
        self.stalled_seen_since = None
        self.last_pause_attempt = 0
        self.last_video_time = None
        self.pause_recovery_failures = 0
        self.visibility_patch_added = False
        self.transcriber = DxpxTranscriber("发展对象")
        self.prepare_playback_page()
        self.video_stuck_reload_seconds = 25
        self.video_stuck_reload_limit = 2
        self.video_retry_limit = 3
        self.pause_recovery_failure_limit = 3

    def close(self):
        if self.transcriber.enabled:
            print("等待后台转写任务完成...")
        self.transcriber.close(wait=True)

    def activate_chrome_window(self):
        """恢复被最小化的调试 Chrome，并把当前标签页带到前台。"""
        try:
            info = self.wd.execute_cdp_cmd("Browser.getWindowForTarget", {})
            window_id = info.get("windowId")
            if window_id is not None:
                bounds = info.get("bounds") or {}
                if bounds.get("windowState") == "minimized":
                    self.wd.execute_cdp_cmd(
                        "Browser.setWindowBounds",
                        {"windowId": window_id, "bounds": {"windowState": "normal"}},
                    )
        except Exception:
            pass
        try:
            self.wd.execute_cdp_cmd("Page.bringToFront", {})
        except Exception:
            pass

    def prepare_playback_page(self):
        """降低后台/失焦时网站暂停播放器的概率。"""
        visibility_script = """
            (() => {
                const patch = (target, prop, value) => {
                    try {
                        Object.defineProperty(target, prop, {
                            configurable: true,
                            get: () => value
                        });
                    } catch (e) {}
                };
                patch(Document.prototype, 'hidden', false);
                patch(Document.prototype, 'visibilityState', 'visible');
                patch(document, 'hidden', false);
                patch(document, 'visibilityState', 'visible');
                try { document.dispatchEvent(new Event('visibilitychange')); } catch (e) {}
            })();
        """
        self.activate_chrome_window()
        if not self.visibility_patch_added:
            try:
                self.wd.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": visibility_script},
                )
                self.visibility_patch_added = True
            except Exception:
                pass
        try:
            self.wd.execute_script(visibility_script)
        except Exception:
            pass

    def remove_blank(self):
        """更改属性target为'_self'"""
        js = 'var items = document.getElementsByTagName("a");for (var i = 0; i < items.length; i++) {var tmp = items[' \
             'i];tmp.target="_self";} '
        self.wd.execute_script(js)

    def click_element(self, element):
        self.wd.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        try:
            element.click()
        except Exception:
            try:
                self.wd.execute_script("arguments[0].click();", element)
            except Exception:
                element.send_keys(Keys.ENTER)

    def reset_playback_tracking(self):
        self.pause_seen_since = None
        self.stalled_seen_since = None
        self.last_pause_attempt = 0
        self.last_video_time = None
        self.pause_recovery_failures = 0

    def force_video_play(self):
        """尽量用真实点击和 video.play 恢复播放。"""
        self.prepare_playback_page()
        clicked = []
        popup_selectors = (
            ('a.public_cancel', '继续观看'),
            ('a.public_submit', '我知道了'),
            ('.public_btn a', '弹窗按钮'),
        )
        play_selectors = (
            ('button[aria-label="Play"]', 'Play'),
            ('button.plyr__control--overlaid', 'OverlayPlay'),
            ('.plyr__controls button[data-plyr="play"]', 'PlyrPlay'),
            ('button[data-plyr="play"]', 'PlyrPlay2'),
            ('.vjs-big-play-button', 'VjsBigPlay'),
            ('.vjs-play-control', 'VjsPlay'),
            ('.prism-big-play-btn', 'PrismPlay'),
            ('.xgplayer-start', 'XgStart'),
            ('.xgplayer-play', 'XgPlay'),
        )

        for selector, label in popup_selectors:
            try:
                for element in self.wd.find_elements(By.CSS_SELECTOR, selector):
                    if element.is_displayed() and element.is_enabled():
                        self.click_element(element)
                        clicked.append(label)
                        time.sleep(0.2)
                        break
            except Exception:
                pass

        if self.is_video_paused():
            clicked_play_control = False
            for selector, label in play_selectors:
                try:
                    for element in self.wd.find_elements(By.CSS_SELECTOR, selector):
                        if element.is_displayed() and element.is_enabled():
                            self.click_element(element)
                            clicked.append(label)
                            clicked_play_control = True
                            time.sleep(0.2)
                            break
                    if clicked_play_control:
                        break
                except Exception:
                    pass

        if self.is_video_paused():
            try:
                video = self.wd.find_element(By.CSS_SELECTOR, 'video')
                ActionChains(self.wd).move_to_element(video).click().perform()
                clicked.append('video-center-click')
                time.sleep(0.3)
            except Exception:
                pass

        try:
            self.wd.execute_script("""
                const video = document.querySelector('video');
                if (video && !video.ended) {
                    video.muted = true;
                    video.controls = true;
                    const promise = video.play();
                    if (promise && promise.catch) {
                        promise.catch(() => {});
                    }
                }
            """)
            clicked.append('video.play')
        except Exception:
            pass

        if self.is_video_paused():
            try:
                video = self.wd.find_element(By.CSS_SELECTOR, 'video')
                ActionChains(self.wd).move_to_element(video).click().perform()
                clicked.append('video-center-click-2')
                time.sleep(0.3)
            except Exception:
                pass

        return clicked

    def is_video_paused(self):
        try:
            return bool(self.wd.execute_script("""
                const video = document.querySelector('video');
                return video ? video.paused : false;
            """))
        except Exception:
            return False

    def wait_for_video_progress(self, previous_time=None, timeout=3):
        deadline = time.time() + timeout
        if previous_time is None:
            state = self.get_video_state()
            previous_time = float((state or {}).get("currentTime") or 0)
        while time.time() < deadline:
            state = self.get_video_state()
            if state and state.get("ended"):
                return True
            current_time = float((state or {}).get("currentTime") or 0)
            if current_time > float(previous_time or 0) + 0.3:
                return True
            time.sleep(0.4)
        return False

    def reload_current_video_page(self, reason):
        """当前视频长时间不动时刷新播放页。"""
        current_url = self.wd.current_url
        print(f"\n{reason}，刷新当前播放页后重试: {current_url}")
        try:
            if "/play" in current_url:
                self.wd.refresh()
            else:
                self.wd.get(current_url)
            time.sleep(3)
            self.reset_playback_tracking()
            self.prepare_playback_page()
            self.address_box()
            clicked = self.force_video_play()
            if clicked:
                print("刷新后已尝试触发播放: " + ", ".join(clicked))
        except Exception as exc:
            print(f"刷新当前播放页失败: {exc}")

    def address_pause(self):
        """处理视频暂停问题"""
        self.prepare_playback_page()
        state = self.wd.execute_script("""
            const video = document.querySelector('video');
            if (!video) {
                return null;
            }
            return {
                paused: video.paused,
                ended: video.ended,
                currentTime: video.currentTime || 0,
                readyState: video.readyState
            };
        """)
        if not state or state.get("ended"):
            self.pause_seen_since = None
            self.stalled_seen_since = None
            return

        now = time.time()
        current_time = float(state.get("currentTime") or 0)
        is_moving = self.last_video_time is not None and current_time > self.last_video_time + 0.2
        self.last_video_time = current_time

        if is_moving:
            self.pause_seen_since = None
            self.stalled_seen_since = None
            return

        if state.get("paused"):
            self.stalled_seen_since = None
            if self.pause_seen_since is None:
                self.pause_seen_since = now
                return
            if now - self.pause_seen_since < 2:
                return
            reason = "暂停"
        else:
            self.pause_seen_since = None
            if self.stalled_seen_since is None:
                self.stalled_seen_since = now
                return
            if now - self.stalled_seen_since < 5:
                return
            reason = "时间不前进"

        if now - self.last_pause_attempt < 10:
            return

        self.last_pause_attempt = now
        try:
            clicked = self.force_video_play()
            recovered = self.wait_for_video_progress(current_time, timeout=3)
            still_paused = self.is_video_paused()
            if recovered:
                self.pause_recovery_failures = 0
            else:
                self.pause_recovery_failures += 1
            suffix = "，已恢复" if recovered else f"，未恢复({self.pause_recovery_failures}/{self.pause_recovery_failure_limit})"
            if still_paused and not recovered:
                suffix += "，仍处于暂停状态"
            if clicked:
                suffix += f"，触发: {', '.join(clicked)}"
            print(f"\n视频{reason}超过阈值，已尝试继续播放{suffix}")
            if not recovered and self.pause_recovery_failures >= self.pause_recovery_failure_limit:
                return "failed"
        except Exception as e:
            print(f"\n尝试继续播放失败: {e}")
            self.pause_recovery_failures += 1
            if self.pause_recovery_failures >= self.pause_recovery_failure_limit:
                return "failed"
        return "attempted"

    def is_completed_required(self, element):
        try:
            return bool(self.wd.execute_script("""
                const target = arguments[0];
                let node = target;
                for (let depth = 0; node && depth < 7; depth++, node = node.parentElement) {
                    if (!node.querySelectorAll) {
                        continue;
                    }
                    const firstTitle = node.querySelector('h2 > a');
                    const statusItems = Array.from(node.querySelectorAll('.lesson_pass, .lesson1_img'));
                    if ((firstTitle === target || node.contains(target)) && statusItems.length) {
                        return statusItems.some((item) => {
                            return (item.innerText || item.textContent || '').includes('完成');
                        });
                    }
                }
                return false;
            """, element))
        except Exception:
            return False

    def get_sidebar_videos(self):
        items = []
        for element in self.wd.find_elements(By.CSS_SELECTOR, 'a[href*="/fzdx/play"]'):
            try:
                title = clean_text(element.text)
                href = element.get_attribute("href") or ""
                if title and title != "完成" and "/fzdx/play" in href:
                    items.append(element)
            except Exception:
                pass
        return items

    def get_video_state(self):
        try:
            return self.wd.execute_script("""
                const video = document.querySelector('video');
                if (!video) {
                    return null;
                }
                const duration = Number.isFinite(video.duration) ? video.duration : null;
                const currentTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
                return {
                    ended: video.ended,
                    paused: video.paused,
                    currentTime,
                    duration,
                    remaining: duration === null ? null : Math.max(0, Math.round(duration - currentTime)),
                    readyState: video.readyState
                };
            """)
        except Exception:
            return None

    def format_remaining(self, remaining_seconds):
        seconds = max(0, int(remaining_seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def address_box(self):
        handled = False
        for selector, label in (
            ('a.public_submit', '我知道了'),
            ('a.public_cancel', '继续观看'),
        ):
            try:
                element = self.wd.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed() and element.is_enabled():
                    try:
                        element.click()
                    except Exception:
                        element.send_keys(Keys.ENTER)
                    handled = True
                    print(f"\n已处理弹窗按钮: {label}")
                    time.sleep(0.5)
            except Exception:
                pass
        return handled

    def printInfo(self, one_index):
        """输出视频信息"""
        print()  # 换行
        time.sleep(1)
        missing_timer_since = None
        last_missing_notice = 0
        missing_player_timeout = 60
        last_progress_seen = time.time()
        last_progress_value = None
        reload_attempts = 0
        while True:
            if "/play" not in self.wd.current_url:
                print("\n当前不是播放页，跳过播放器等待，继续后续课程。")
                return "not_play_page"

            time_text = None
            try:
                time_text = self.wd.find_element(By.CSS_SELECTOR, 'div[aria-label="Current time"]').get_attribute("innerText").replace('-', '')
                missing_timer_since = None
            except Exception as e:
                time_text = None

            state = self.get_video_state()
            if time_text == "00:00" or (state and state.get("ended")):
                print('播放完成,点击按钮"我知道了"')
                time.sleep(5)
                return "completed"

            if state and state.get("duration") is not None and state.get("remaining") is not None:
                now = time.time()
                current_time = float(state.get("currentTime") or 0)
                if current_time > 0 and int(state.get("remaining") or 0) <= 1:
                    print('播放完成,点击按钮"我知道了"')
                    time.sleep(5)
                    return "completed"
                if last_progress_value is None:
                    last_progress_value = current_time
                    last_progress_seen = now
                elif current_time > last_progress_value + 0.2:
                    last_progress_value = current_time
                    last_progress_seen = now
                    reload_attempts = 0
                elif now - last_progress_seen >= self.video_stuck_reload_seconds:
                    if reload_attempts < self.video_stuck_reload_limit:
                        reload_attempts += 1
                        stuck_seconds = int(now - last_progress_seen)
                        self.reload_current_video_page(
                            f"播放时间连续 {stuck_seconds} 秒未前进({reload_attempts}/{self.video_stuck_reload_limit})"
                        )
                        last_progress_seen = time.time()
                        last_progress_value = None
                        continue
                    stuck_seconds = int(now - last_progress_seen)
                    print(f"\n播放时间连续 {stuck_seconds} 秒未前进，放弃当前等待，交给外层重新进入该视频。")
                    return "stalled"
                print("\r剩余时间:" + self.format_remaining(state.get("remaining")), end='')
                pause_result = self.address_pause()
                if pause_result == "failed":
                    if reload_attempts < self.video_stuck_reload_limit:
                        reload_attempts += 1
                        self.reload_current_video_page(
                            f"连续 {self.pause_recovery_failures} 次恢复播放失败({reload_attempts}/{self.video_stuck_reload_limit})"
                        )
                        last_progress_seen = time.time()
                        last_progress_value = None
                        continue
                    print("\n连续恢复失败，放弃当前等待，交给外层重新进入该视频。")
                    return "stalled"
                time.sleep(1)
                continue

            if time_text:
                print("\r剩余时间:" + time_text, end='')
                pause_result = self.address_pause()
                if pause_result == "failed":
                    print("\n连续恢复失败，放弃当前等待，交给外层重新进入该视频。")
                    return "stalled"
                time.sleep(1)
                continue

            self.address_box()
            try:
                self.address_pause()
            except Exception:
                pass
            now = time.time()
            if missing_timer_since is None:
                missing_timer_since = now
            if now - last_missing_notice > 10:
                wait_seconds = int(now - missing_timer_since)
                print(f"\n未找到播放器时间或 video 状态，已等待 {wait_seconds} 秒，继续处理弹窗...")
                try:
                    self.wd.save_screenshot(f"视频{one_index}.png")
                    with open(f"视频{one_index}.txt", "w", encoding="utf-8") as f:
                        f.write("未找到播放器时间或 video 状态")
                except Exception:
                    pass
                last_missing_notice = now
            if now - missing_timer_since >= missing_player_timeout:
                wait_seconds = int(now - missing_timer_since)
                print(f"\n连续 {wait_seconds} 秒未找到播放器时间或 video 状态，跳过当前视频，继续后续课程。")
                return "missing_player"
            time.sleep(1)

    def manage(self, j):
        """处理每一个必修视频"""
        # 必修页面的课程列表
        necessary = self.wd.find_elements(By.CSS_SELECTOR, 'div.l_list_right > h2 > a')
        if j >= len(necessary):
            print(f"必修课程列表已变化，索引 {j + 1} 不存在，跳过当前项。")
            return
        lesson_title = clean_text(necessary[j].text)
        lesson_href = necessary[j].get_attribute("href")
        if self.is_completed_required(necessary[j]):
            print(f"必修课程已完成，跳过: {lesson_title}")
            return
        # 点击必修课程
        self.click_element(necessary[j])
        time.sleep(1)
        if "/play" not in self.wd.current_url and lesson_href and "/play" in lesson_href:
            self.wd.get(lesson_href)
            time.sleep(1)
        # 接下来只考虑三级界面
        # 获得侧边栏的课程列表
        sidebars = self.get_sidebar_videos()
        length_sidebar = len(sidebars)
        print(f"成功加载侧边栏的课程列表,一共{length_sidebar}个视频")
        if length_sidebar == 0:
            if "/play" in self.wd.current_url:
                print("未找到侧边栏视频列表，尝试监控当前播放页。")
                self.printInfo(j)
            else:
                print("当前页面不是播放页且没有侧边栏视频，跳过。")
            return
        for sidebar_i in range(length_sidebar):
            attempt = 0
            while attempt < self.video_retry_limit:
                # 获得侧边栏的课程列表
                sidebars = self.get_sidebar_videos()
                if sidebar_i >= len(sidebars):
                    break
                sidebar = sidebars[sidebar_i]
                sidebar_title = clean_text(sidebar.text)
                sidebar_href = sidebar.get_attribute("href")
                if attempt == 0:
                    print(f"正在播放第{sidebar_i + 1}个视频，一共{length_sidebar}个")
                else:
                    print(f"重新进入第{sidebar_i + 1}个视频，第{attempt + 1}/{self.video_retry_limit}次尝试")
                # 判断是否播放完
                if "red" in sidebar.get_attribute("style"):
                    print(f"视频{sidebar_i + 1}播放完成,即将播放下一个视频")
                    break
                try:
                    previous_m3u8_url = find_current_m3u8_url(self.wd)
                except Exception:
                    previous_m3u8_url = None
                clear_resource_timing(self.wd)
                self.prepare_playback_page()
                self.click_element(sidebar)
                time.sleep(1)
                if "/play" not in self.wd.current_url and sidebar_href and "/play" in sidebar_href:
                    self.wd.get(sidebar_href)
                # 处理继续观看
                try:
                    self.address_box()
                except Exception as e:
                    print(e)
                self.reset_playback_tracking()
                self.prepare_playback_page()
                self.transcriber.submit_from_driver(
                    self.wd,
                    lesson_title,
                    sidebar_title,
                    previous_m3u8_url=previous_m3u8_url,
                )
                result = self.printInfo(sidebar_i)  # 输出视频信息
                if result == "completed":
                    break
                attempt += 1
                if attempt < self.video_retry_limit:
                    print(f"视频{sidebar_i + 1}未能稳定播放，重新进入课程页后再试。")
                    if lesson_href:
                        self.wd.get(lesson_href)
                        time.sleep(2)
                    continue
                print(f"视频{sidebar_i + 1}连续 {self.video_retry_limit} 次未能稳定播放，跳过，继续后续视频。")

    def run(self):
        # 按钮'我要学习'的列表
        study_list = self.wd.find_elements(By.CSS_SELECTOR, 'div.expand_btn a')
        # 一共几门课
        length_study_list = len(study_list)
        for index_study_list in range(length_study_list):
            # 按钮'开始学习'的列表
            study_list = self.wd.find_elements(By.CSS_SELECTOR, 'div.expand_btn a')
            # 点击按钮'开始学习' 然后进入二级界面
            self.click_element(study_list[index_study_list])
            # 接下来只考虑二级界面
            # 获得按钮'必修'
            necessary_btn = self.wd.find_element(By.CSS_SELECTOR,
                                                 'body > div > div.w1150 > div.wrap_right > div.lesson1_cont.q_lesson1_con > div.lesson1_title > div > a:nth-child(2)')
            # 点击‘按钮’必修
            self.click_element(necessary_btn)
            # 必修页面的课程列表
            necessary_list = self.wd.find_elements(By.CSS_SELECTOR, 'div.l_list_right > h2 > a')
            # 二级页面(必修)的地址
            necessary_page = self.wd.current_url
            # 必修课的个数
            length_necessary_list = len(necessary_list)

            for index_necessary_list in range(length_necessary_list):
                # 处理每个必修专题视频
                self.manage(index_necessary_list)
                # 处理完视频回退
                self.wd.get(necessary_page)
                print(
                    f"专题{index_study_list + 1}/{length_study_list}:完成必修课程{index_necessary_list + 1}/{length_necessary_list},三秒后进入下一个必修课程...")
            self.wd.get(self.base_url)
        print("完成所有必修课程学习!")


if __name__ == '__main__':
    m = Main()
    try:
        m.run()
    finally:
        m.close()
