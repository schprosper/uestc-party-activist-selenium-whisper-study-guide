import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


FALSE_VALUES = {"0", "false", "no", "off", "disabled", "否", "关闭"}


def env_enabled(name, default=True):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in FALSE_VALUES


def env_float(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def clean_text(value):
    return " ".join((value or "").split())


def compose_video_title(lesson_title, video_title):
    lesson = clean_text(lesson_title)
    video = clean_text(video_title)
    if lesson and video and lesson not in video and video not in lesson:
        return f"{lesson}_{video}"
    return video or lesson or "DXPX视频"


def clear_resource_timing(driver):
    try:
        driver.execute_script(
            "if (window.performance && performance.clearResourceTimings) { performance.clearResourceTimings(); }"
        )
    except Exception:
        pass


def enable_network_capture(driver):
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    try:
        driver.get_log("performance")
    except Exception:
        pass


def is_m3u8_url(value):
    return isinstance(value, str) and ".m3u8" in value.lower()


def get_m3u8_from_page(driver):
    return driver.execute_script(
        """
        const urls = [];
        const push = (value) => {
            if (!value) {
                return;
            }
            try {
                urls.push(new URL(value, document.baseURI).href);
            } catch (error) {
                urls.push(String(value));
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

        const matches = Array.from(new Set(urls)).filter((url) => {
            return typeof url === 'string' && url.toLowerCase().includes('.m3u8');
        });
        return matches.length ? matches[matches.length - 1] : null;
        """
    )


def get_m3u8_from_performance_log(driver):
    matches = []
    try:
        entries = driver.get_log("performance")
    except Exception:
        return None

    for entry in entries:
        try:
            message = json.loads(entry.get("message", "{}")).get("message", {})
            params = message.get("params", {})
            candidates = []
            request = params.get("request") or {}
            response = params.get("response") or {}
            candidates.extend([
                request.get("url"),
                response.get("url"),
                params.get("documentURL"),
            ])
            headers = response.get("headers") or {}
            candidates.extend([
                headers.get("Location"),
                headers.get("location"),
            ])
            for candidate in candidates:
                if is_m3u8_url(candidate):
                    matches.append(candidate)
        except Exception:
            continue

    return matches[-1] if matches else None


def find_current_m3u8_url(driver):
    network_url = get_m3u8_from_performance_log(driver)
    if network_url:
        return network_url
    return get_m3u8_from_page(driver)


def wait_for_m3u8_url(driver, timeout=12, previous_url=None):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            url = find_current_m3u8_url(driver)
            if url and url != previous_url:
                return url
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    if last_error:
        print(f"未能读取 m3u8: {last_error}")
    return None


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
        if duration is None:
            return ""
        return str(int(duration))
    except Exception:
        return ""


def resume_video_after_refresh(driver):
    try:
        driver.execute_script(
            """
            const selectors = [
                'a.public_cancel',
                'a.public_submit',
                'button[aria-label="Play"]',
                'button.plyr__control--overlaid'
            ];
            for (const selector of selectors) {
                for (const element of document.querySelectorAll(selector)) {
                    const visible = element.offsetParent !== null;
                    if (visible && !element.disabled) {
                        element.click();
                    }
                }
            }
            const video = document.querySelector('video');
            if (video && video.paused && !video.ended) {
                const promise = video.play();
                if (promise && promise.catch) {
                    promise.catch(() => {});
                }
            }
            """
        )
    except Exception:
        pass


def get_browser_request_context(driver, page_url):
    user_agent = ""
    try:
        user_agent = driver.execute_script("return navigator.userAgent || '';") or ""
    except Exception:
        user_agent = ""

    cookies = []
    try:
        for cookie in driver.get_cookies():
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                cookies.append(f"{name}={value}")
    except Exception:
        pass

    add_headers = []
    try:
        parsed = urlsplit(page_url)
        if parsed.scheme and parsed.netloc:
            add_headers.append(f"Origin: {parsed.scheme}://{parsed.netloc}")
    except Exception:
        pass

    return {
        "referer": page_url or "",
        "user_agent": user_agent,
        "cookie_header": "; ".join(cookies),
        "add_headers": add_headers,
    }


class DxpxTranscriber:
    def __init__(self, course_title):
        self.course_title = course_title
        self.enabled = env_enabled("DXPX_TRANSCRIBE", True)
        self.root = Path(__file__).resolve().parent
        self.script_path = Path(os.environ.get("DXPX_TRANSCRIBE_SCRIPT", self.root / "dxpx_transcribe.ps1"))
        self.repo_root = self.root.parent
        self.output_root = os.environ.get("DXPX_TRANSCRIBE_OUTPUT", str(self.repo_root / "output" / "dxpx_notes"))
        self.work_root = os.environ.get("DXPX_TRANSCRIBE_WORK", str(self.repo_root / ".tmp" / "dxpx_auto_play_transcribe"))
        self.video2md_script = os.environ.get("DXPX_TRANSCRIBE_VIDEO2MD_SCRIPT", os.environ.get("VIDEO2MD_SCRIPT", ""))
        self.language = os.environ.get("DXPX_TRANSCRIBE_LANGUAGE", "zh")
        self.model = os.environ.get("DXPX_TRANSCRIBE_MODEL", "medium")
        self.run_name = os.environ.get(
            "DXPX_TRANSCRIBE_RUN_NAME",
            f"{datetime.now().strftime('%Y-%m-%d')}_{course_title}",
        )
        self.keep_work = env_enabled("DXPX_TRANSCRIBE_KEEP_WORK", False)
        self.force = env_enabled("DXPX_TRANSCRIBE_FORCE", False)
        self.no_auto_download_ytdlp = env_enabled("DXPX_TRANSCRIBE_NO_AUTO_DOWNLOAD_YTDLP", False)
        self.refresh_on_miss = env_enabled("DXPX_TRANSCRIBE_REFRESH_ON_MISS", False)
        self.m3u8_timeout = env_float("DXPX_TRANSCRIBE_M3U8_TIMEOUT", 4)
        self.refresh_timeout = env_float("DXPX_TRANSCRIBE_REFRESH_TIMEOUT", 8)
        self.whisper_exe = os.environ.get("DXPX_TRANSCRIBE_WHISPER_EXE", "")
        self.ffmpeg_exe = os.environ.get("DXPX_TRANSCRIBE_FFMPEG_EXE", "")
        self.yt_dlp = os.environ.get("DXPX_TRANSCRIBE_YT_DLP", "")
        self.task_queue = queue.Queue()
        self.worker = None
        self.next_index = 1
        self.seen = set()

        if self.enabled and not self.script_path.exists():
            print(f"转写脚本不存在，已禁用转写: {self.script_path}")
            self.enabled = False

        if self.enabled:
            self.worker = threading.Thread(target=self._worker_loop, name="dxpx-transcribe-worker")
            self.worker.start()

    def submit_from_driver(self, driver, lesson_title, video_title, timeout=None, previous_m3u8_url=None):
        if not self.enabled:
            return

        title = compose_video_title(lesson_title, video_title)
        page_url = driver.current_url
        if timeout is None:
            timeout = self.m3u8_timeout
        print(f"正在嗅探 m3u8，最多等待 {timeout:g} 秒: {title}")
        m3u8_url = wait_for_m3u8_url(driver, timeout=timeout, previous_url=previous_m3u8_url)
        if not m3u8_url and self.refresh_on_miss:
            print(f"未发现 m3u8，刷新当前视频页后再尝试一次: {title}")
            try:
                clear_resource_timing(driver)
                driver.refresh()
                time.sleep(2)
                resume_video_after_refresh(driver)
                m3u8_url = wait_for_m3u8_url(driver, timeout=self.refresh_timeout, previous_url=None)
                page_url = driver.current_url
            except Exception as exc:
                print(f"刷新后重新嗅探失败: {exc}")
        if not m3u8_url:
            print(f"未发现 m3u8，跳过转写: {title}")
            return

        duration = get_video_duration(driver)
        request_context = get_browser_request_context(driver, page_url)
        self.submit(title, page_url, m3u8_url, duration, request_context)

    def submit(self, video_title, page_url, m3u8_url, duration="", request_context=None):
        key = m3u8_url or f"{page_url}|{video_title}"
        if key in self.seen:
            print(f"转写任务已提交过，跳过: {video_title}")
            return

        index = self.next_index
        self.next_index += 1
        self.seen.add(key)

        task = {
            "index": index,
            "video_title": video_title,
            "page_url": page_url,
            "m3u8_url": m3u8_url,
            "duration": duration,
            "request_context": request_context or {},
        }
        self.task_queue.put(task)
        print(f"已提交转写任务 {index:03d}: {video_title}")

    def close(self, wait=True):
        if not self.enabled or not self.worker:
            return
        if wait:
            self.task_queue.join()
        self.task_queue.put(None)
        self.worker.join(timeout=10)

    def _worker_loop(self):
        while True:
            task = self.task_queue.get()
            if task is None:
                self.task_queue.task_done()
                return
            try:
                self._run_task(task)
            except Exception as exc:
                print(f"后台转写线程异常: {exc}")
            finally:
                self.task_queue.task_done()

    def _run_task(self, task):
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            "-CourseTitle",
            self.course_title,
            "-VideoTitle",
            task["video_title"],
            "-PageUrl",
            task["page_url"],
            "-M3u8Url",
            task["m3u8_url"],
            "-Index",
            str(task["index"]),
            "-OutputRoot",
            self.output_root,
            "-WorkRoot",
            self.work_root,
            "-RunName",
            self.run_name,
            "-Language",
            self.language,
            "-Model",
            self.model,
        ]

        context = task.get("request_context") or {}
        if context.get("referer"):
            command.extend(["-Referer", context["referer"]])
        if context.get("user_agent"):
            command.extend(["-UserAgent", context["user_agent"]])
        if context.get("cookie_header"):
            command.extend(["-CookieHeader", context["cookie_header"]])
        for header in context.get("add_headers") or []:
            command.extend(["-AddHeader", header])
        if task["duration"]:
            command.extend(["-Duration", task["duration"]])
        if self.video2md_script:
            command.extend(["-Video2MdScript", self.video2md_script])
        if self.whisper_exe:
            command.extend(["-WhisperExePath", self.whisper_exe])
        if self.ffmpeg_exe:
            command.extend(["-FfmpegPath", self.ffmpeg_exe])
        if self.yt_dlp:
            command.extend(["-YtDlpPath", self.yt_dlp])
        if self.keep_work:
            command.append("-KeepWork")
        if self.force:
            command.append("-Force")
        if self.no_auto_download_ytdlp:
            command.append("-NoAutoDownloadYtDlp")

        print(f"开始后台转写 {task['index']:03d}: {task['video_title']}")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode == 0:
            print(f"后台转写完成 {task['index']:03d}: {task['video_title']}")
            return

        tail = "\n".join(result.stdout.splitlines()[-20:])
        print(f"后台转写失败 {task['index']:03d}: {task['video_title']}")
        if tail:
            print(tail)
