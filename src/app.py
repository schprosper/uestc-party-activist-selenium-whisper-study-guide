"""Windows GUI entry point. Build with PyInstaller; no Python needed by recipients."""
import argparse
import ctypes
import json
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText

from core import (TRACKS, VERSION, Cancelled, UserError, Client, ensure_browser,
                  local_root, load_banks, fill_active_exam)
from playback import run_playback

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets'


class App:
    def __init__(self, root, track='fzdx'):
        self.root = root
        self.root.title('党校助手 · 积极分子 / 发展对象 · V' + VERSION)
        self.root.geometry('860x650')
        self.root.minsize(760, 590)
        self.track = tk.StringVar(value=track)
        self.status = tk.StringVar(value='就绪：选择类别，然后一键启动。')
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.running = False
        self.active_mode = None
        self.active_track = None
        self.worker = None
        self.logfile = None
        self.closing = False
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 22, 'bold'))
        style.configure('Main.TButton', font=('Microsoft YaHei UI', 12, 'bold'), padding=12)
        style.configure('TButton', padding=7)
        outer = ttk.Frame(root, padding=24)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='党校助手', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Windows 免安装版  ·  无需 Python  ·  无需复制 Cookie').pack(anchor='w', pady=(4, 16))
        choice = ttk.Frame(outer)
        choice.pack(fill='x')
        self.track_buttons = []
        for key, name in TRACKS.items():
            button = ttk.Radiobutton(choice, text=name, variable=self.track, value=key)
            button.pack(side='left', padx=(0, 28))
            self.track_buttons.append(button)
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x', pady=(16, 8))
        self.start_button = ttk.Button(buttons, text='一键启动课程任务', style='Main.TButton', command=lambda: self.start('videos'))
        self.start_button.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.check_button = ttk.Button(buttons, text='仅核验状态', command=lambda: self.start('check'))
        self.check_button.pack(side='left', padx=(0, 10))
        self.stop_button = ttk.Button(buttons, text='停止任务', command=self.request_stop, state='disabled')
        self.stop_button.pack(side='left')
        ttk.Label(outer, text='首次在官网输入自己的账号与验证码；程序自动等待。已完成课程会跳过。', wraplength=790).pack(anchor='w', pady=3)
        ttk.Label(outer, text='积极分子默认兼容播放；发展对象保留记录方式，也可选择兼容播放。完成状态以官网为准。', wraplength=790).pack(anchor='w', pady=3)
        ttk.Label(outer, text='两个类别分别登录、分别运行。网站页面不兼容时会停止并说明原因，可在下方留下反馈。', wraplength=790).pack(anchor='w', pady=3)
        tools = ttk.Frame(outer)
        tools.pack(fill='x', pady=(12, 12))
        self.exam_button = ttk.Button(tools, text='填写当前测试的已知题目', command=lambda: self.start('exam'))
        self.exam_button.pack(side='left', padx=(0, 8))
        self.compat_button = ttk.Button(tools, text='兼容播放', command=lambda: self.start('playback'))
        self.compat_button.pack(side='left', padx=(0, 8))
        ttk.Button(tools, text='打开双类别题库', command=self.open_banks).pack(side='left', padx=(0, 8))
        ttk.Button(tools, text='日志 / 反馈', command=self.feedback).pack(side='left')
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 8))
        ttk.Label(outer, textvariable=self.status, wraplength=790).pack(anchor='w', pady=(0, 8))
        self.output = ScrolledText(outer, height=11, wrap='word', font=('Microsoft YaHei UI', 10), state='disabled')
        self.output.pack(fill='both', expand=True)
        ttk.Label(outer, text='退出程序会停止后续任务，课程浏览器保持打开。登录资料留在本机，不进入分享包。', wraplength=790).pack(anchor='w', pady=(10, 0))
        self.root.after(100, self.pump)

    def emit(self, message):
        self.messages.put(('log', str(message)))

    def start(self, mode):
        if self.running:
            return
        track = self.track.get()
        self.active_track, self.active_mode = track, mode
        self.stop.clear()
        self.running = True
        folder = local_root() / track / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        self.logfile = folder / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.jsonl')
        for widget in [self.start_button, self.check_button, self.exam_button, self.compat_button] + self.track_buttons:
            widget.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.progress.start(12)
        self.emit('正在启动' + TRACKS[track] + ' · ' + {'videos': '课程任务', 'check': '只读核验', 'exam': '当前测试填写', 'playback': '兼容播放'}[mode])
        self.worker = threading.Thread(target=self.run, args=(track, mode), daemon=False)
        self.worker.start()

    def run(self, track, mode):
        client = None
        mutex = None
        try:
            # Cross-process lock prevents two copies from writing to the same account.
            kernel = ctypes.windll.kernel32
            kernel.CreateMutexW.restype = ctypes.c_void_p
            mutex = kernel.CreateMutexW(None, False, 'Local\\UESTC_DXPX_Helper_' + track)
            if not mutex:
                raise UserError('无法创建任务锁，请重试。')
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            state = kernel.WaitForSingleObject(mutex, 0)
            if state not in (0, 0x80):
                raise UserError('该类别已有任务正在运行，请查看另一个助手窗口。')
            port = ensure_browser(track, self.stop, self.emit)
            client = Client(track, port, self.stop, self.emit)
            if mode == 'exam':
                result = fill_active_exam(client, load_banks(ASSETS / 'banks.json'))
            else:
                client.connect()
                if mode == 'playback' or (mode == 'videos' and track == 'jjfz'):
                    result = run_playback(client)
                else:
                    result = client.run_videos(write=(mode == 'videos'))
            result_path = local_root() / track / 'last-result.json'
            result_path.write_text(json.dumps(dict(result, time=datetime.now().isoformat()), ensure_ascii=False, indent=2), encoding='utf-8')
            self.emit('本轮处理结束。浏览器保持打开。')
        except (UserError, Cancelled) as exc:
            self.emit(str(exc))
        except Exception as exc:
            # Avoid logging raw request/response, credentials, cookies, or exception URLs.
            self.emit('遇到未预期的问题（' + type(exc).__name__ + '），任务已停止。请通过“日志 / 反馈”留下情况。')
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            if mutex:
                kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel.ReleaseMutex(mutex)
                kernel.CloseHandle(mutex)
            self.messages.put(('done', None))

    def pump(self):
        try:
            while True:
                kind, message = self.messages.get_nowait()
                if kind == 'log':
                    row = {'time': datetime.now().isoformat(timespec='seconds'), 'version': VERSION,
                           'track': self.active_track, 'mode': self.active_mode, 'message': message}
                    if self.logfile:
                        try:
                            with self.logfile.open('a', encoding='utf-8') as stream:
                                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                        except OSError:
                            message += '（日志写入失败，请检查磁盘空间。）'
                    self.output.configure(state='normal')
                    self.output.insert('end', datetime.now().strftime('%H:%M:%S') + '  ' + message + '\n')
                    self.output.see('end')
                    self.output.configure(state='disabled')
                    self.status.set(message)
                if kind == 'done':
                    self.running = False
                    self.progress.stop()
                    self.stop_button.configure(state='disabled')
                    for widget in [self.start_button, self.check_button, self.exam_button, self.compat_button] + self.track_buttons:
                        widget.configure(state='normal')
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def request_stop(self):
        self.stop.set()
        self.status.set('正在停止：等待当前请求结束，不再发起后续请求。浏览器不会关闭。')

    def open_banks(self):
        folder = ASSETS / '题库'
        if folder.is_dir():
            os.startfile(str(folder))
        else:
            messagebox.showerror('文件不完整', '题库目录缺失，请完整解压压缩包。', parent=self.root)

    def feedback(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('日志与反馈')
        dialog.geometry('560x260')
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='日志只保存在本机，不会自动发送。\n反馈中不要填写密码、Cookie 或验证码。', wraplength=510).pack(anchor='w', pady=(0, 12))
        ttk.Button(frame, text='打开本机数据与日志目录', command=self.open_data).pack(anchor='w', pady=5)
        def save():
            content = simpledialog.askstring('留下反馈', '哪里有问题？出现了什么提示？\n不要填写账号密码或 Cookie。', parent=dialog)
            if content:
                folder = local_root()
                folder.mkdir(parents=True, exist_ok=True)
                row = {'created': datetime.now().isoformat(), 'status': 'new', 'version': VERSION,
                       'track': self.active_track or self.track.get(), 'mode': self.active_mode,
                       'message': content, 'log': self.logfile.name if self.logfile else None}
                with (folder / 'feedback.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                messagebox.showinfo('已保存', '反馈已保存到本机 feedback.jsonl，可单独发给维护者。不要发送 browser 文件夹。', parent=dialog)
        ttk.Button(frame, text='写一条反馈', command=save).pack(anchor='w', pady=5)
        ttk.Label(frame, text='分享给别人时，请发送原始 ZIP。不要发送本机数据目录或 browser 文件夹。', wraplength=510).pack(anchor='w', pady=12)

    def open_data(self):
        local_root().mkdir(parents=True, exist_ok=True)
        os.startfile(str(local_root()))

    def close(self):
        if self.running:
            self.closing = True
            self.request_stop()
        else:
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--track', choices=list(TRACKS), default='fzdx')
    parser.add_argument('--auto', action='store_true')
    parser.add_argument('--self-test', type=Path)
    parser.add_argument('--probe-port', type=int)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.probe_port:
        logs = []
        def progress(message):
            logs.append(message)
            if args.report:
                args.report.write_text(json.dumps({'state': 'running', 'messages': logs}, ensure_ascii=False, indent=2), encoding='utf-8')
        progress('开始只读验收。')
        client = Client(args.track, args.probe_port, emit=progress)
        try:
            client.connect(wait=False)
            result = client.run_videos(write=False)
            if args.report:
                args.report.write_text(json.dumps({'state': 'complete', 'result': result, 'messages': logs}, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            if args.report:
                args.report.write_text(json.dumps({'state': 'error', 'error_type': type(exc).__name__, 'error': str(exc), 'messages': logs}, ensure_ascii=False, indent=2), encoding='utf-8')
            raise SystemExit(1)
        finally:
            client.close()
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    if args.self_test:
        root.withdraw()
    app = App(root, args.track)
    if args.self_test:
        root.update()
        banks = load_banks(ASSETS / 'banks.json')
        result = {'version': VERSION, 'track': app.track.get(), 'tk': root.tk.call('info', 'patchlevel'),
                  'start_button': str(app.start_button['state']), 'bank_keys': len(banks),
                  'questions': sum(len(v) for v in banks.values()), 'bank_text_files': len(list((ASSETS / '题库').rglob('*.txt'))),
                  'network_started': app.worker is not None, 'frozen': bool(getattr(sys, 'frozen', False))}
        args.self_test.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        root.destroy()
        return
    if args.auto:
        root.after(300, lambda: app.start('videos'))
    root.mainloop()


if __name__ == '__main__':
    main()
