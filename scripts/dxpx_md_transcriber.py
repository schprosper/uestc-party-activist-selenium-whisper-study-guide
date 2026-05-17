import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


COURSES = {
    "jjfz": {
        "title": "积极分子",
        "base_url": "https://dxpx.uestc.edu.cn/jjfz/lesson",
        "card_selector": "div.lesson_center_a a.study",
        "entry_selectors": [
            (By.XPATH, '//a[contains(., "我要去学习")]'),
            (By.XPATH, '//a[contains(., "开始学习")]'),
            (By.XPATH, '//a[contains(., "去完成")]'),
            (By.CSS_SELECTOR, 'a[href*="/jjfz/lesson"]'),
        ],
    },
    "fzdx": {
        "title": "发展对象",
        "base_url": "https://dxpx.uestc.edu.cn/fzdx/lesson",
        "card_selector": "div.expand_btn a",
        "entry_selectors": [],
    },
}

MEDIA_MARKERS = (".m3u8", ".mp4")
CONFLICT_MARKERS = (
    "run_jjfz.ps1",
    "run_fzdx.ps1",
    "jjfz.py",
    "fzdx.py",
    "run_dxpx_download.ps1",
    "dxpx_loggedin_downloader.py",
)


@dataclass
class VideoTask:
    course_id: str
    course_title: str
    course_index: int
    topic_index: int
    video_index: int
    course_card_title: str
    topic_title: str
    video_title: str


def is_done_status(status):
    value = (status or "").strip().lower()
    return value in {"completed", "skipped_existing", "resume_skipped"} or value.startswith("partial_")


def task_key_parts(course_id, course_index, topic_index, video_index):
    try:
        return f"{course_id}|{int(course_index)}|{int(topic_index)}|{int(video_index)}"
    except (TypeError, ValueError):
        return ""


def task_key(task):
    return task_key_parts(task.course_id, task.course_index, task.topic_index, task.video_index)


def record_task_key(record):
    return task_key_parts(
        record.get("courseId"),
        record.get("courseIndex"),
        record.get("topicIndex"),
        record.get("videoIndex"),
    )


def clean_text(value):
    return " ".join((value or "").split())


def safe_name(value, default="untitled", max_length=80):
    text = clean_text(value) or default
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    if len(text) > max_length:
        text = text[:max_length].strip(" ._")
    return text or default


def compose_video_title(topic_title, video_title):
    topic = clean_text(topic_title)
    video = clean_text(video_title)
    if topic and video and topic not in video and video not in topic:
        return f"{topic}_{video}"
    return video or topic or "DXPX视频"


def is_media_url(value):
    if not isinstance(value, str):
        return False
    lower = value.lower()
    return any(marker in lower for marker in MEDIA_MARKERS)


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def append_jsonl(path, record):
    ensure_dir(Path(path).parent)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_text(path, text):
    ensure_dir(Path(path).parent)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def unique_media_urls(candidates, previous_resource_url=None):
    unique = []
    for url in candidates:
        if not is_media_url(url):
            continue
        if previous_resource_url and url == previous_resource_url:
            continue
        if url not in unique:
            unique.append(url)
    return unique


def choose_resource(candidates, previous_resource_url=None):
    unique = unique_media_urls(candidates, previous_resource_url=previous_resource_url)
    if not unique:
        return None
    for url in reversed(unique):
        if ".m3u8" in url.lower():
            return url
    return unique[-1]


def ordered_resources(primary_url, candidates, previous_resource_url=None):
    unique = unique_media_urls(candidates, previous_resource_url=previous_resource_url)
    ranked = []
    if primary_url:
        ranked.append(primary_url)
    ranked.extend(url for url in reversed(unique) if ".m3u8" in url.lower())
    ranked.extend(url for url in reversed(unique) if ".m3u8" not in url.lower())

    result = []
    for url in ranked:
        if url not in result:
            result.append(url)
    return result


def find_running_conflicting_processes():
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress -Depth 2",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        processes = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(processes, dict):
        processes = [processes]

    running = []
    for proc in processes:
        cmd = proc.get("CommandLine") or ""
        lower = cmd.lower()
        if any(marker.lower() in lower for marker in CONFLICT_MARKERS):
            running.append(proc)
    return running


def fail_if_conflicting_process_running():
    running = find_running_conflicting_processes()
    if not running:
        return
    print("另一个 DXPX 自动播放或下载脚本正在运行，请先停止：")
    for proc in running:
        print(f"  PID {proc.get('ProcessId')}: {proc.get('CommandLine')}")
    raise SystemExit(2)


def connect_driver(port):
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(3)
    enable_network_capture(driver)
    activate_chrome_window(driver)
    return driver


def activate_chrome_window(driver):
    try:
        info = driver.execute_cdp_cmd("Browser.getWindowForTarget", {})
        window_id = info.get("windowId")
        bounds = info.get("bounds") or {}
        if window_id is not None and bounds.get("windowState") == "minimized":
            driver.execute_cdp_cmd(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"windowState": "normal"}},
            )
    except Exception:
        pass
    try:
        driver.execute_cdp_cmd("Page.bringToFront", {})
    except Exception:
        pass


def enable_network_capture(driver):
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    drain_performance_logs(driver)


def drain_performance_logs(driver):
    try:
        return driver.get_log("performance")
    except Exception:
        return []


def clear_resource_timing(driver):
    try:
        driver.execute_script(
            "if (window.performance && performance.clearResourceTimings) { performance.clearResourceTimings(); }"
        )
    except Exception:
        pass


def parse_media_urls_from_logs(entries):
    urls = []
    for entry in entries:
        try:
            message = json.loads(entry.get("message", "{}")).get("message", {})
            params = message.get("params", {})
            request = params.get("request") or {}
            response = params.get("response") or {}
            headers = response.get("headers") or {}
            candidates = [
                request.get("url"),
                response.get("url"),
                params.get("documentURL"),
                headers.get("Location"),
                headers.get("location"),
            ]
            urls.extend(candidate for candidate in candidates if is_media_url(candidate))
        except Exception:
            continue
    return urls


def get_page_media_urls(driver):
    try:
        return driver.execute_script(
            """
            const out = [];
            const push = (value) => {
                if (!value) {
                    return;
                }
                try {
                    out.push(new URL(value, document.baseURI).href);
                } catch (error) {
                    out.push(String(value));
                }
            };
            const video = document.querySelector('video');
            if (video) {
                push(video.currentSrc);
                push(video.src);
            }
            document.querySelectorAll('video source, source').forEach((source) => {
                push(source.src || source.getAttribute('src'));
            });
            if (window.performance && performance.getEntriesByType) {
                performance.getEntriesByType('resource').forEach((entry) => push(entry.name));
            }
            return Array.from(new Set(out)).filter((url) => {
                if (typeof url !== 'string') {
                    return false;
                }
                const lower = url.toLowerCase();
                return lower.includes('.m3u8') || lower.includes('.mp4');
            });
            """
        ) or []
    except Exception:
        return []


def trigger_video_load(driver):
    handle_popups(driver)
    try:
        driver.execute_script(
            """
            const video = document.querySelector('video');
            if (video) {
                video.muted = true;
                if (video.paused && !video.ended) {
                    const promise = video.play();
                    if (promise && promise.catch) {
                        promise.catch(() => {});
                    }
                    return true;
                }
            }
            const selectors = [
                'button[aria-label="Play"]',
                'button.plyr__control--overlaid',
                'a.public_cancel',
                '.public_btn a'
            ];
            for (const selector of selectors) {
                for (const element of document.querySelectorAll(selector)) {
                    if (element.offsetParent !== null && !element.disabled) {
                        element.click();
                        return true;
                    }
                }
            }
            return false;
            """
        )
    except Exception:
        pass


def pause_video(driver):
    try:
        driver.execute_script(
            """
            const video = document.querySelector('video');
            if (video && !video.paused) {
                video.pause();
            }
            """
        )
    except Exception:
        pass


def handle_popups(driver):
    for selector in ("a.public_submit", "a.public_cancel"):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if element.is_displayed() and element.is_enabled():
                        element.click()
                        time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass


def is_logged_in_course_page(driver):
    try:
        current = (driver.current_url or "").lower()
    except Exception:
        current = ""
    if not current.startswith("https://dxpx.uestc.edu.cn/"):
        return False
    if url_looks_like_login(current):
        return False

    selectors = (
        "div.lesson_center_a a.study",
        "div.expand_btn a",
        "div.l_list_right > h2 > a",
        'a[href*="/jjfz/play"]',
        'a[href*="/fzdx/play"]',
        'a[href*="/lesson/video"]',
    )
    for selector in selectors:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return True
        except Exception:
            pass

    try:
        title = driver.title or ""
        if "课程中心" in title or "在线培训" in title:
            return True
    except Exception:
        pass

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "课程中心" in body_text or "退出" in body_text:
            return True
    except Exception:
        pass
    return False


def url_looks_like_login(value):
    try:
        parsed = urlsplit(value or "")
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return (
        "authserver" in host
        or host == "cas"
        or host.startswith("cas.")
        or path == "/login"
        or path.startswith("/login/")
        or path == "/sso"
        or path.startswith("/sso/")
        or path.endswith("/login")
    )


def is_login_page(driver):
    if is_logged_in_course_page(driver):
        return False
    try:
        current = (driver.current_url or "").lower()
    except Exception:
        current = ""
    if url_looks_like_login(current):
        return True
    try:
        for element in driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'):
            try:
                if element.is_displayed():
                    return True
            except Exception:
                return True
    except Exception:
        pass
    try:
        title = driver.title or ""
        if "统一身份认证" in title:
            return True
    except Exception:
        pass
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "统一身份认证" in body_text:
            return True
        if "登录" in body_text and "密码" in body_text:
            return True
    except Exception:
        pass
    return False


def is_http_error_page(driver):
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body_text = ""
    try:
        title = driver.title or ""
    except Exception:
        title = ""
    text = f"{title}\n{body_text}"
    return "HTTP ERROR 500" in text or "目前无法处理此请求" in text or "该网页无法正常运作" in text


def ensure_logged_in(driver, check_url, timeout):
    try:
        driver.get(check_url)
        time.sleep(2)
    except InvalidSessionIdException as exc:
        raise RuntimeError("Chrome 调试会话已断开。请不要关闭调试 Chrome；如刚启动失败，先运行 launch_chrome_debug.ps1 后再重试。") from exc
    if is_http_error_page(driver):
        raise RuntimeError(f"课程入口返回 HTTP 500：{check_url}。这是网页服务端/登录态响应，脚本暂时不能继续。")
    if is_logged_in_course_page(driver):
        return
    if not is_login_page(driver):
        return

    print("检测到登录页。请在打开的 Chrome 中完成登录，脚本会自动继续。")
    deadline = time.time() + timeout
    last_reload = 0
    while time.time() < deadline:
        if is_logged_in_course_page(driver):
            print("已检测到登录态，继续转写。")
            return
        if is_http_error_page(driver):
            raise RuntimeError(f"登录后课程入口返回 HTTP 500：{check_url}。")
        if not is_login_page(driver):
            time.sleep(1)
            driver.get(check_url)
            time.sleep(1)
            if is_http_error_page(driver):
                raise RuntimeError(f"登录后课程入口仍返回 HTTP 500：{check_url}。")
            if is_logged_in_course_page(driver):
                print("已检测到登录态，继续转写。")
                return
            if not is_login_page(driver):
                print("已检测到登录态，继续转写。")
                return
        now = time.time()
        if now - last_reload > 10:
            last_reload = now
            print("仍在等待登录...")
        time.sleep(1)
    raise RuntimeError(f"等待登录超时：{timeout} 秒")


def wait_until(predicate, timeout=8, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def find_clickable(driver, locators, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for by, value in locators:
            try:
                elements = driver.find_elements(by, value)
            except Exception:
                continue
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        return element
                except Exception:
                    pass
        time.sleep(0.3)
    return None


def click_element(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    try:
        driver.execute_script(
            "if (arguments[0].tagName && arguments[0].tagName.toLowerCase() === 'a') { arguments[0].target = '_self'; }",
            element,
        )
    except Exception:
        pass
    try:
        element.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
        except Exception:
            element.send_keys(Keys.ENTER)


def close_non_dxpx_tabs_and_focus(driver):
    original = driver.current_window_handle
    dxpx_handle = None
    for handle in list(driver.window_handles):
        try:
            driver.switch_to.window(handle)
            current = driver.current_url or ""
            if current.startswith("https://dxpx.uestc.edu.cn/"):
                dxpx_handle = handle
            elif current and not current.startswith(("chrome://", "devtools://")):
                driver.close()
        except Exception:
            pass
    handles = list(driver.window_handles)
    target = dxpx_handle if dxpx_handle in handles else (original if original in handles else (handles[0] if handles else None))
    if target:
        driver.switch_to.window(target)


def close_other_tabs(driver, keep_handle=None):
    try:
        if keep_handle is None:
            keep_handle = driver.current_window_handle
    except Exception:
        keep_handle = None

    for handle in list(driver.window_handles):
        if keep_handle and handle == keep_handle:
            continue
        try:
            driver.switch_to.window(handle)
            driver.close()
        except Exception:
            pass

    handles = list(driver.window_handles)
    if keep_handle in handles:
        driver.switch_to.window(keep_handle)
    elif handles:
        driver.switch_to.window(handles[0])


def force_links_same_tab(driver):
    try:
        driver.execute_script("document.querySelectorAll('a[target]').forEach((a) => { a.target = '_self'; });")
    except Exception:
        pass


def focus_dxpx_play_tab(driver):
    for handle in list(driver.window_handles):
        try:
            driver.switch_to.window(handle)
            current = driver.current_url or ""
            if current.startswith("https://dxpx.uestc.edu.cn/") and "/play" in current:
                return True
        except Exception:
            pass
    for handle in list(driver.window_handles):
        try:
            driver.switch_to.window(handle)
            current = driver.current_url or ""
            if current.startswith("https://dxpx.uestc.edu.cn/"):
                return False
        except Exception:
            pass
    return False


def get_video_links(driver, course_id):
    selectors = [
        f'a[href*="/{course_id}/play"]',
        'a[href*="/play"][href*="r=video"]',
    ]
    links = []
    seen = set()
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                href = element.get_attribute("href") or ""
                if not href.startswith("https://dxpx.uestc.edu.cn/") or "/play" not in href:
                    continue
                key = href.split("#", 1)[0]
                if key in seen:
                    continue
                seen.add(key)
                text = clean_text(element.text) or clean_text(element.get_attribute("title")) or clean_text(element.get_attribute("aria-label"))
                links.append((element, text or f"视频{len(links) + 1}", href))
            except Exception:
                continue
    return links


def click_first(driver, locators, label, required=True):
    element = find_clickable(driver, locators)
    if not element:
        if required:
            raise RuntimeError(f"没有找到可点击元素: {label}")
        return False
    click_element(driver, element)
    time.sleep(1)
    return True


def open_learning_entry_if_needed(driver, config):
    if not config["entry_selectors"]:
        return
    if driver.find_elements(By.CSS_SELECTOR, config["card_selector"]):
        return
    if "/lesson/video" in driver.current_url:
        return
    click_first(driver, config["entry_selectors"], "学习入口", required=False)


def open_course_card(driver, config, index):
    cards = driver.find_elements(By.CSS_SELECTOR, config["card_selector"])
    if index >= len(cards):
        raise RuntimeError(f"课程卡片数量不足: index={index}, count={len(cards)}")
    before_url = driver.current_url
    click_element(driver, cards[index])

    def entered_course_page():
        return (
            driver.current_url != before_url
            or bool(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/lesson/video"]'))
            or bool(driver.find_elements(By.XPATH, '//a[contains(., "精品课程")]'))
            or bool(driver.find_elements(By.XPATH, '//a[contains(., "必修")]'))
        )

    if not wait_until(entered_course_page, timeout=6):
        cards = driver.find_elements(By.CSS_SELECTOR, config["card_selector"])
        if index < len(cards):
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", cards[index])
            wait_until(entered_course_page, timeout=5)


def open_good_course_if_needed(driver):
    if "/lesson/video" in driver.current_url:
        return
    click_first(
        driver,
        [
            (By.XPATH, '//a[contains(., "精品课程")]'),
            (By.CSS_SELECTOR, 'a[href*="/lesson/video"]'),
        ],
        "精品课程",
        required=False,
    )


def open_required_tab(driver):
    if "required=1" in driver.current_url and driver.find_elements(By.CSS_SELECTOR, "div.l_list_right > h2 > a"):
        return
    click_first(
        driver,
        [
            (By.XPATH, '//a[normalize-space(.)="必修" or contains(., "必修")]'),
            (By.CSS_SELECTOR, 'a[href*="required=1"]'),
        ],
        "必修",
        required=True,
    )


def get_video_duration(driver):
    try:
        duration = driver.execute_script(
            """
            const video = document.querySelector('video');
            if (!video || !Number.isFinite(video.duration)) {
                return null;
            }
            return Math.round(video.duration);
            """
        )
        return "" if duration is None else str(int(duration))
    except Exception:
        return ""


def video_ready(driver):
    try:
        state = driver.execute_script(
            """
            const video = document.querySelector('video');
            if (!video) {
                return {hasVideo: false, readyState: 0, src: ''};
            }
            return {
                hasVideo: true,
                readyState: video.readyState || 0,
                src: video.currentSrc || video.src || ''
            };
            """
        ) or {}
        return bool(state.get("hasVideo")) and int(state.get("readyState") or 0) >= 1
    except Exception:
        return False


def recover_video_page(driver, fallback_url=None, wait_seconds=2):
    try:
        current = driver.current_url or ""
    except Exception:
        current = ""
    if fallback_url and ("/play" not in current or not current.startswith("https://dxpx.uestc.edu.cn/")):
        driver.get(fallback_url)
    else:
        driver.refresh()
    time.sleep(wait_seconds)
    handle_popups(driver)
    trigger_video_load(driver)
    time.sleep(wait_seconds)


def sniff_resource(driver, timeout, previous_resource_url=None):
    deadline = time.time() + timeout
    candidates = []
    last_trigger = 0
    while time.time() < deadline:
        candidates.extend(parse_media_urls_from_logs(drain_performance_logs(driver)))
        candidates.extend(get_page_media_urls(driver))
        resource = choose_resource(candidates, previous_resource_url=previous_resource_url)
        if resource:
            return resource, candidates
        now = time.time()
        if now - last_trigger > 2:
            trigger_video_load(driver)
            last_trigger = now
        time.sleep(0.5)
    return None, candidates


def refresh_and_sniff_resource(driver, timeout, previous_resource_url=None):
    clear_resource_timing(driver)
    drain_performance_logs(driver)
    driver.refresh()
    time.sleep(2)
    handle_popups(driver)
    trigger_video_load(driver)
    return sniff_resource(driver, timeout=timeout, previous_resource_url=previous_resource_url)


def get_request_context(driver, page_url):
    try:
        user_agent = driver.execute_script("return navigator.userAgent || '';") or ""
    except Exception:
        user_agent = ""
    try:
        cookies = driver.get_cookies()
    except Exception:
        cookies = []
    cookie_parts = []
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        cookie_text = name + value
        if name and not any(ch in cookie_text for ch in "\t\r\n"):
            cookie_parts.append(f"{name}={value}")
    parsed = urlsplit(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://dxpx.uestc.edu.cn"
    return {
        "user_agent": user_agent,
        "referer": page_url,
        "cookie_header": "; ".join(cookie_parts),
        "add_headers": [f"Origin: {origin}"],
    }


def parse_powershell_format_list(output):
    data = {}
    current_key = None
    for line in output.splitlines():
        if ":" not in line:
            if current_key and line.startswith(" "):
                continuation = line.strip()
                if continuation:
                    data[current_key] = f"{data[current_key]}{continuation}"
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"Status", "VideoDir", "Markdown", "Subtitle", "Meta"}:
            data[key] = value.strip()
            current_key = key
        else:
            current_key = None
    return data


def compose_run_name(args):
    if args.run_name:
        return safe_name(args.run_name, "dxpx", 80)
    if args.course == "both":
        title = "DXPX"
    else:
        title = COURSES[args.course]["title"]
    return f"{datetime.now().strftime('%Y-%m-%d')}_{safe_name(title, 'DXPX', 40)}"


class MarkdownTranscriber:
    def __init__(self, args):
        self.args = args
        self.output_root = Path(args.output_root)
        self.work_root = Path(args.work_root)
        self.run_name = compose_run_name(args)
        self.run_dir = self.output_root / self.run_name
        self.log_dir = self.run_dir / "logs"
        self.manifest_path = self.log_dir / "manifest.jsonl"
        self.failed_log = self.log_dir / "failed_tasks.log"
        self.debug_dir = self.run_dir / "debug"
        self.processed = 0
        self.succeeded = 0
        self.skipped = 0
        self.failed = 0
        self.last_resource_url = None
        ensure_dir(self.log_dir)
        ensure_dir(self.work_root)
        self.resume_latest = self.load_resume_latest()
        if self.args.force or self.args.no_resume:
            self.completed_keys = set()
        else:
            self.completed_keys = {
                key for key, record in self.resume_latest.items() if is_done_status(record.get("status"))
            }
            if self.completed_keys:
                print(f"断点续跑: manifest 已记录 {len(self.completed_keys)} 个完成项，会在嗅探前跳过。")

    def limit_reached(self):
        return self.args.max_videos > 0 and self.processed >= self.args.max_videos

    def load_resume_latest(self):
        latest = {}
        if not self.manifest_path.exists():
            return latest
        with open(self.manifest_path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    print(f"忽略损坏的 manifest 行 {line_number}: {self.manifest_path}")
                    continue
                key = record_task_key(record)
                if key:
                    latest[key] = record
        return latest

    def expected_output_for_index(self, index, task):
        if not self.run_dir.exists():
            return None
        prefix = f"{index:03d}_"
        expected_title = clean_text(compose_video_title(task.topic_title, task.video_title))
        for video_dir in sorted(self.run_dir.iterdir()):
            if not video_dir.is_dir() or not video_dir.name.startswith(prefix):
                continue
            meta_path = video_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            if not is_done_status(meta.get("status")):
                continue
            meta_course = clean_text(meta.get("courseTitle"))
            meta_title = clean_text(meta.get("videoTitle"))
            if meta_course and meta_course != clean_text(task.course_title):
                continue
            if meta_title and expected_title and meta_title != expected_title:
                continue
            markdown = Path(meta.get("markdownPath") or (video_dir / "笔记.md"))
            subtitle = Path(meta.get("subtitlePath") or (video_dir / "字幕.srt"))
            if not markdown.exists() and not subtitle.exists():
                continue
            return {
                "VideoDir": str(video_dir),
                "Markdown": str(markdown) if markdown.exists() else "",
                "Subtitle": str(subtitle) if subtitle.exists() else "",
                "Meta": str(meta_path),
                "status": "resume_skipped",
            }
        return None

    def try_resume_skip(self, task):
        if self.args.force or self.args.no_resume:
            return False
        next_index = self.processed + 1
        existing = self.expected_output_for_index(next_index, task)
        key = task_key(task)
        manifest_done = key in self.completed_keys
        if manifest_done and not existing:
            print(f"断点记录显示已完成，但未找到 {next_index:03d} 成品文件，重新转写: {task.video_title}")
            return False
        if not manifest_done and not existing:
            return False

        self.processed += 1
        self.skipped += 1
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "courseId": task.course_id,
            "courseTitle": task.course_title,
            "courseIndex": task.course_index,
            "topicIndex": task.topic_index,
            "videoIndex": task.video_index,
            "courseCardTitle": task.course_card_title,
            "topicTitle": task.topic_title,
            "videoTitle": task.video_title,
            "index": self.processed,
            "pageUrl": "",
            "resourceUrl": "",
            "duration": "",
            "runName": self.run_name,
            "status": "resume_skipped",
            "outputDirectory": existing.get("VideoDir", ""),
            "markdown": existing.get("Markdown", ""),
            "subtitle": existing.get("Subtitle", ""),
            "meta": existing.get("Meta", ""),
            "attempts": [],
        }
        append_jsonl(self.manifest_path, record)
        self.resume_latest[key] = record
        self.completed_keys.add(key)
        title = compose_video_title(task.topic_title, task.video_title)
        print(f"跳过已完成 {self.processed:03d}: {title} -> {existing.get('VideoDir', self.run_dir)}")
        return True

    def required_links_or_recover(self, driver, course_id, config, course_index):
        for attempt in range(3):
            try:
                self.prepare_required_page(driver, config)
            except Exception:
                pass
            required_links = driver.find_elements(By.CSS_SELECTOR, "div.l_list_right > h2 > a")
            if required_links:
                return required_links
            if attempt == 0:
                print("没有找到必修课程列表，刷新当前页后重试。")
                driver.refresh()
                time.sleep(2)
                continue
            print("没有找到必修课程列表，重进课程专题后重试。")
            driver.get(config["base_url"])
            time.sleep(1)
            open_learning_entry_if_needed(driver, config)
            force_links_same_tab(driver)
            open_course_card(driver, config, course_index - 1)
            time.sleep(1)
        return []

    def scan_course(self, driver, course_id):
        config = COURSES[course_id]
        print(f"进入课程入口: {config['title']} {config['base_url']}")
        ensure_logged_in(driver, config["base_url"], self.args.login_timeout)
        if is_http_error_page(driver):
            raise RuntimeError(f"课程入口返回 HTTP 500：{driver.current_url}")
        open_learning_entry_if_needed(driver, config)
        force_links_same_tab(driver)
        close_other_tabs(driver)

        cards = driver.find_elements(By.CSS_SELECTOR, config["card_selector"])
        if not cards:
            print("未找到课程卡片，尝试按当前页面处理。")
            self.prepare_required_page(driver, config)
            self.process_required_page(driver, course_id, config, "当前课程", 1)
            return

        course_count = len(cards)
        for course_index in range(course_count):
            if self.limit_reached():
                return
            driver.get(config["base_url"])
            time.sleep(1)
            open_learning_entry_if_needed(driver, config)
            force_links_same_tab(driver)
            close_other_tabs(driver)
            cards = driver.find_elements(By.CSS_SELECTOR, config["card_selector"])
            if course_index >= len(cards):
                break
            card_title = clean_text(cards[course_index].text) or f"专题{course_index + 1}"
            print(f"进入专题 {course_index + 1}/{course_count}: {card_title}")
            open_course_card(driver, config, course_index)
            self.prepare_required_page(driver, config)
            self.process_required_page(driver, course_id, config, card_title, course_index + 1)

    def prepare_required_page(self, driver, config):
        if config is COURSES["jjfz"]:
            open_good_course_if_needed(driver)
        open_required_tab(driver)
        time.sleep(1)

    def process_required_page(self, driver, course_id, config, card_title, course_index):
        required_links = self.required_links_or_recover(driver, course_id, config, course_index)
        required_page = driver.current_url
        if not required_links:
            raise RuntimeError("没有找到必修课程列表。")

        required_count = len(required_links)
        for topic_index in range(required_count):
            if self.limit_reached():
                return
            driver.get(required_page)
            time.sleep(1)
            required_links = self.required_links_or_recover(driver, course_id, config, course_index)
            required_page = driver.current_url
            if topic_index >= len(required_links):
                break
            topic_title = clean_text(required_links[topic_index].text) or f"必修课程{topic_index + 1}"
            print(f"进入必修 {topic_index + 1}/{required_count}: {topic_title}")
            force_links_same_tab(driver)
            click_element(driver, required_links[topic_index])
            time.sleep(1.5)
            focus_dxpx_play_tab(driver)
            close_other_tabs(driver)
            self.process_video_page(driver, course_id, config, course_index, topic_index + 1, card_title, topic_title)

    def process_video_page(self, driver, course_id, config, course_index, topic_index, card_title, topic_title):
        close_non_dxpx_tabs_and_focus(driver)
        focus_dxpx_play_tab(driver)
        close_other_tabs(driver)
        video_links = get_video_links(driver, course_id)
        if not video_links:
            if "/play" not in (driver.current_url or ""):
                print("未找到播放链接，按当前页面尝试嗅探。")
            task = VideoTask(course_id, config["title"], course_index, topic_index, 1, card_title, topic_title, topic_title)
            if self.try_resume_skip(task):
                return
            self.capture_and_transcribe_current_video(driver, task)
            return

        video_count = len(video_links)
        print(f"侧边栏视频数量: {video_count}")
        for video_index in range(video_count):
            if self.limit_reached():
                return
            video_links = get_video_links(driver, course_id)
            if video_index >= len(video_links):
                break
            sidebar, sidebar_title, sidebar_href = video_links[video_index]
            task = VideoTask(
                course_id,
                config["title"],
                course_index,
                topic_index,
                video_index + 1,
                card_title,
                topic_title,
                sidebar_title,
            )
            if self.try_resume_skip(task):
                continue
            print(f"准备嗅探视频 {video_index + 1}/{video_count}: {sidebar_title}")
            clear_resource_timing(driver)
            drain_performance_logs(driver)
            force_links_same_tab(driver)
            click_element(driver, sidebar)
            time.sleep(self.args.trigger_wait)
            focus_dxpx_play_tab(driver)
            if "/play" not in (driver.current_url or "") and sidebar_href:
                driver.get(sidebar_href)
                time.sleep(self.args.trigger_wait)
            focus_dxpx_play_tab(driver)
            close_other_tabs(driver)
            if not self.args.no_refresh_on_miss and not video_ready(driver):
                print(f"播放器未就绪，刷新/重进播放页后再试: {sidebar_title}")
                recover_video_page(driver, fallback_url=sidebar_href, wait_seconds=self.args.trigger_wait)
            self.capture_and_transcribe_current_video(driver, task)
            close_other_tabs(driver)

    def capture_and_transcribe_current_video(self, driver, task):
        self.processed += 1
        page_url = driver.current_url
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "courseId": task.course_id,
            "courseTitle": task.course_title,
            "courseIndex": task.course_index,
            "topicIndex": task.topic_index,
            "videoIndex": task.video_index,
            "courseCardTitle": task.course_card_title,
            "topicTitle": task.topic_title,
            "videoTitle": task.video_title,
            "index": self.processed,
            "pageUrl": page_url,
            "resourceUrl": "",
            "duration": "",
            "runName": self.run_name,
            "status": "started",
            "attempts": [],
        }
        try:
            handle_popups(driver)
            trigger_video_load(driver)
            previous_resource_url = self.last_resource_url
            resource_url, candidates = sniff_resource(
                driver,
                timeout=self.args.sniff_timeout,
                previous_resource_url=previous_resource_url,
            )
            if not resource_url and not self.args.no_refresh_on_miss:
                print(f"未嗅探到资源，刷新当前视频页后重试: {task.video_title}")
                resource_url, refresh_candidates = refresh_and_sniff_resource(
                    driver,
                    timeout=self.args.sniff_timeout,
                    previous_resource_url=previous_resource_url,
                )
                candidates.extend(refresh_candidates)
                page_url = driver.current_url
                record["pageUrl"] = page_url

            if not resource_url:
                raise RuntimeError(f"未嗅探到 m3u8/mp4。候选数量: {len(candidates)}")

            self.last_resource_url = resource_url
            duration = get_video_duration(driver)
            context = get_request_context(driver, page_url)
            record["duration"] = duration

            last_error = None
            for candidate_url in ordered_resources(resource_url, candidates, previous_resource_url=previous_resource_url):
                attempt = {"resourceUrl": candidate_url, "status": "started"}
                record["attempts"].append(attempt)
                try:
                    result = self.run_transcribe(task, page_url, candidate_url, duration, context)
                    attempt.update({
                        "status": result["status"],
                        "videoDir": result.get("VideoDir", ""),
                        "markdown": result.get("Markdown", ""),
                        "subtitle": result.get("Subtitle", ""),
                        "meta": result.get("Meta", ""),
                    })
                    record.update({
                        "resourceUrl": candidate_url,
                        "status": result["status"],
                        "outputDirectory": result.get("VideoDir", ""),
                        "markdown": result.get("Markdown", ""),
                        "subtitle": result.get("Subtitle", ""),
                        "meta": result.get("Meta", ""),
                    })
                    append_jsonl(self.manifest_path, record)
                    if result["status"].startswith("skipped"):
                        self.skipped += 1
                    else:
                        self.succeeded += 1
                    print(f"转写完成: {task.video_title} -> {result.get('VideoDir', self.run_dir)}")
                    return
                except Exception as exc:
                    last_error = exc
                    attempt["status"] = "failed"
                    attempt["error"] = str(exc)
                    print(f"资源转写失败，尝试下一个候选: {task.video_title} - {exc}")

            raise RuntimeError(str(last_error) if last_error else "所有候选资源转写失败。")
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            append_jsonl(self.manifest_path, record)
            append_text(
                self.failed_log,
                f"[{record['timestamp']}] {task.course_title} | {task.topic_title} | {task.video_title} | {page_url} | {exc}",
            )
            self.failed += 1
            print(f"失败: {task.video_title} - {exc}")
            self.save_debug_screenshot(driver, task)
        finally:
            pause_video(driver)

    def run_transcribe(self, task, page_url, resource_url, duration, context):
        video_title = compose_video_title(task.topic_title, task.video_title)
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            self.args.transcribe_script,
            "-CourseTitle",
            task.course_title,
            "-VideoTitle",
            video_title,
            "-PageUrl",
            page_url,
            "-M3u8Url",
            resource_url,
            "-Index",
            str(self.processed),
            "-OutputRoot",
            self.args.output_root,
            "-WorkRoot",
            self.args.work_root,
            "-RunName",
            self.run_name,
            "-Language",
            self.args.language,
            "-Model",
            self.args.model,
            "-Video2MdScript",
            self.args.video2md_script,
        ]
        if context.get("referer"):
            command.extend(["-Referer", context["referer"]])
        if context.get("user_agent"):
            command.extend(["-UserAgent", context["user_agent"]])
        if context.get("cookie_header"):
            command.extend(["-CookieHeader", context["cookie_header"]])
        for header in context.get("add_headers") or []:
            command.extend(["-AddHeader", header])
        if duration:
            command.extend(["-Duration", duration])
        if self.args.yt_dlp:
            command.extend(["-YtDlpPath", self.args.yt_dlp])
        if self.args.whisper_exe:
            command.extend(["-WhisperExePath", self.args.whisper_exe])
        if self.args.ffmpeg_path:
            command.extend(["-FfmpegPath", self.args.ffmpeg_path])
        if self.args.keep_work:
            command.append("-KeepWork")
        if self.args.force:
            command.append("-Force")
        if self.args.no_auto_download_ytdlp:
            command.append("-NoAutoDownloadYtDlp")

        print(f"开始转写 {self.processed:03d}: {video_title}")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.args.transcribe_timeout,
        )
        parsed = parse_powershell_format_list(result.stdout)
        if result.returncode != 0:
            tail = "\n".join(result.stdout.splitlines()[-20:])
            raise RuntimeError(f"dxpx_transcribe exit {result.returncode}\n{tail}")
        status = parsed.get("Status") or "completed"
        parsed["status"] = status
        return parsed

    def save_debug_screenshot(self, driver, task):
        ensure_dir(self.debug_dir)
        screenshot = self.debug_dir / f"{self.processed:03d}_{safe_name(task.video_title, 'video')}.png"
        try:
            driver.save_screenshot(str(screenshot))
        except Exception:
            pass


def parse_args(argv):
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Transcribe DXPX videos to Markdown through a logged-in debug Chrome.")
    parser.add_argument("--course", choices=["jjfz", "fzdx", "both"], default="jjfz")
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--max-videos", type=int, default=0, help="0 means no limit.")
    parser.add_argument("--output-root", default=str(repo_root / "output" / "dxpx_notes"))
    parser.add_argument("--work-root", default=str(repo_root / ".tmp" / "dxpx_md_auto_transcribe"))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--transcribe-script", default=str(Path(__file__).resolve().parent / "dxpx_transcribe.ps1"))
    parser.add_argument("--video2md-script", default=os.environ.get("VIDEO2MD_SCRIPT", str(repo_root / "video2md" / "video2md.ps1")))
    parser.add_argument("--yt-dlp", default=os.environ.get("YTDLP_PATH", ""))
    parser.add_argument("--whisper-exe", default=os.environ.get("WHISPER_EXE_PATH", str(Path(__file__).resolve().parent / "whisper_cpp_cublas_adapter.ps1")))
    parser.add_argument("--ffmpeg-path", default=os.environ.get("FFMPEG_PATH", ""))
    parser.add_argument("--language", default="zh")
    parser.add_argument("--model", default="medium")
    parser.add_argument("--sniff-timeout", type=float, default=12)
    parser.add_argument("--trigger-wait", type=float, default=2)
    parser.add_argument("--login-timeout", type=int, default=600)
    parser.add_argument("--transcribe-timeout", type=int, default=14400)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument("--no-auto-download-ytdlp", action="store_true")
    parser.add_argument("--no-refresh-on-miss", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    fail_if_conflicting_process_running()
    ensure_dir(args.output_root)
    ensure_dir(args.work_root)

    for label, path in (
        ("transcribe script", args.transcribe_script),
        ("video2md script", args.video2md_script),
    ):
        if not Path(path).exists():
            raise SystemExit(f"{label} not found: {path}")

    try:
        driver = connect_driver(args.port)
    except WebDriverException as exc:
        raise SystemExit(f"Cannot connect to Chrome at 127.0.0.1:{args.port}. {exc}")

    transcriber = MarkdownTranscriber(args)
    try:
        courses = ["jjfz", "fzdx"] if args.course == "both" else [args.course]
        for course_id in courses:
            if transcriber.limit_reached():
                break
            transcriber.scan_course(driver, course_id)
    except InvalidSessionIdException as exc:
        raise SystemExit("Chrome 调试会话已断开。请保持调试 Chrome 窗口打开，并避免同时用同一个 profile 启动多个 Chrome。") from exc

    print(
        "完成: processed={0}, succeeded={1}, skipped={2}, failed={3}, manifest={4}".format(
            transcriber.processed,
            transcriber.succeeded,
            transcriber.skipped,
            transcriber.failed,
            transcriber.manifest_path,
        )
    )
    if transcriber.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
