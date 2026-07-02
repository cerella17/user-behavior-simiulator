import os
import sys
import time
import random
import json
import socket
import threading
import subprocess
import platform
from datetime import datetime, timedelta
import webbrowser
import requests
from urllib.parse import urlparse
import tempfile
import shutil
import re

from .filesystem_explorer import FilesystemExplorer


_ORIGINAL_SLEEP = time.sleep
_SESSION_SPEED_MULTIPLIER = 1.0


def _scaled_sleep(seconds):
    try:
        multiplier = float(_SESSION_SPEED_MULTIPLIER)
    except Exception:
        multiplier = 1.0

    multiplier = max(0.1, multiplier)
    _ORIGINAL_SLEEP(max(0.0, float(seconds)) / multiplier)


class UserBehaviorSimulator:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.config = self.load_config(config_file)
        self.is_running = False
        self.threads = []
        self.current_os = None
        self.hotkey_listener = None

    def load_config(self, config_file):
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config file {config_file}: {e}")
                return self.load_default_config()
        else:
            print(f"Config file {config_file} not found, creating from default")
            default_config = self.load_default_config()
            try:
                with open(config_file, 'w') as f:
                    json.dump(default_config, f, indent=4)
            except Exception as e:
                print(f"Error creating config file {config_file}: {e}")
            return default_config

    def load_default_config(self):
        default_config_path = os.path.join(os.path.dirname(__file__), 'default-config.json')

        if os.path.exists(default_config_path):
            try:
                with open(default_config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading default config: {e}")
                return self.get_fallback_config()
        else:
            print(f"Default config file not found at {default_config_path}")
            return self.get_fallback_config()

    def get_fallback_config(self):
        return {
            "websites": ["https://www.google.com", "https://thehackernews.com/"],
            "target_ips": ["192.168.1.100"],
            "file_share_port": 8888,
            "session_speed_multiplier": 1.0,
            "mouse_activity_probability": 0.8,
            "close_tab_probability": 0.25,
            "stop_hotkey": "f12",
            "active_hours": {"enabled": False},
            "scheduled_tasks": {"enabled": False, "tasks": []},
            "save_paths": {"text_files": "", "downloads": "", "ping_logs": "", "received_files": ""},
            "page_interaction": {"scroll_enabled": False},
            "search_interaction": {
                "enabled": False,
                "query": "",
                "search_url": "https://www.google.com/",
                "wait_after_open_seconds": [3, 6],
                "click_before_typing": True,
                "press_enter": True,
                "tab_presses": 0,
                "human_mouse": {
                    "enabled": True,
                    "move_duration": [0.25, 0.7],
                    "jitter_pixels": [6, 16],
                    "hesitation_pause": [0.05, 0.2]
                },
                "click_coordinates": {
                    "x": None,
                    "y": None
                },
                "typing_interval": 0.05,
                "post_type_pause": 0.5
            },
            "task_orchestration": {
                "enabled": False,
                "modules": ["browse_websites", "browse_filesystem"],
                "initial_sequence": ["browse_websites", "browse_filesystem", "browse_websites"],
                "module_duration_minutes": [1, 3]
            },
            "link_interaction": {
                "enabled": True,
                "open_new_tab_probability": 0.65,
                "pre_open_pause_seconds": [0.4, 1.4],
                "post_open_pause_seconds": [1.0, 2.5],
                "explore_time_seconds": [12, 45]
            },
            "ftp_config": {"enabled": False},
            "smtp_config": {"enabled": False},
            "ssh_config": {"enabled": False}
        }

    def is_within_active_hours(self):
        if not self.config.get('active_hours', {}).get('enabled', False):
            return True

        current_hour = datetime.now().hour
        start_hour = self.config['active_hours'].get('start_hour', 0)
        end_hour = self.config['active_hours'].get('end_hour', 23)

        if start_hour <= end_hour:
            return start_hour <= current_hour < end_hour
        else:
            return current_hour >= start_hour or current_hour < end_hour

    def wait_for_active_hours(self):
        while not self.is_within_active_hours() and self.is_running:
            time.sleep(60)

    def get_session_speed_multiplier(self):
        try:
            multiplier = float(self.config.get('session_speed_multiplier', 1.0) or 1.0)
        except Exception:
            multiplier = 1.0

        return max(0.1, multiplier)

    def scale_duration(self, seconds):
        return max(0.0, float(seconds)) / self.get_session_speed_multiplier()

    def configure_session_speed(self):
        global _SESSION_SPEED_MULTIPLIER
        _SESSION_SPEED_MULTIPLIER = self.get_session_speed_multiplier()
        time.sleep = _scaled_sleep

    def detect_runtime_os(self):
        if not self.current_os:
            self.current_os = platform.system()

        return self.current_os

    def get_close_tab_hotkey(self):
        if self.detect_runtime_os() == "Darwin":
            return ('command', 'w')

        return ('ctrl', 'w')

    def get_stop_hotkey_name(self):
        return str(self.config.get('stop_hotkey', 'f12') or 'f12').strip().lower()

    def start_stop_hotkey_listener(self):
        try:
            from pynput import keyboard
        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Stop hotkey listener unavailable: install pynput")
            return None

        hotkey_name = self.get_stop_hotkey_name()
        key_map = {
            'f12': keyboard.Key.f12,
            'esc': keyboard.Key.esc,
            'escape': keyboard.Key.esc,
        }

        target_key = key_map.get(hotkey_name)
        if target_key is None and len(hotkey_name) == 1:
            target_key = keyboard.KeyCode.from_char(hotkey_name)

        if target_key is None:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Invalid stop hotkey '{hotkey_name}', defaulting to F12")
            target_key = keyboard.Key.f12
            hotkey_name = 'f12'

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Stop hotkey active: {hotkey_name.upper()}")

        def on_press(key):
            if key == target_key:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Stop hotkey pressed: {hotkey_name.upper()}")
                self.stop(reason=f"Stop hotkey pressed: {hotkey_name.upper()}")
                return False

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        self.hotkey_listener = listener
        return listener

    def sleep_with_mouse_activity(self, seconds):
        duration = max(
            self.scale_duration(seconds),
            min(1.8, max(0.7, float(seconds) * 0.25))
        )

        if duration <= 0:
            return

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            screen_width, screen_height = pyautogui.size()
            movement_probability = float(self.config.get('mouse_activity_probability', 0.8) or 0.8)
            movement_probability = max(0.0, min(1.0, movement_probability))
            end_time = time.time() + duration

            while time.time() < end_time and self.is_running:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break

                step = min(remaining, random.uniform(0.15, 0.45))
                if random.random() < movement_probability:
                    current_x, current_y = pyautogui.position()
                    target_x = max(0, min(screen_width - 1, current_x + random.randint(-35, 35)))
                    target_y = max(0, min(screen_height - 1, current_y + random.randint(-25, 25)))
                    pyautogui.moveTo(
                        target_x,
                        target_y,
                        duration=random.uniform(0.08, 0.28),
                        tween=pyautogui.easeInOutQuad,
                    )

                _ORIGINAL_SLEEP(step)

        except ImportError:
            _ORIGINAL_SLEEP(self.scale_duration(seconds))
        except Exception:
            _ORIGINAL_SLEEP(self.scale_duration(seconds))

    def maybe_close_current_tab(self, opened_new_tab=False):
        close_probability = float(self.config.get('close_tab_probability', 0.25) or 0.25)
        close_probability = max(0.0, min(1.0, close_probability))

        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Tab close check: opened_new_tab={opened_new_tab}, close_probability={close_probability:.2f}"
        )

        roll = random.random()
        if roll >= close_probability:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Tab not closed: random roll {roll:.2f} >= {close_probability:.2f}"
            )
            return

        try:
            import pyautogui

            pyautogui.FAILSAFE = True

            hotkey = self.get_close_tab_hotkey()
            current_os = self.detect_runtime_os()
            if opened_new_tab:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Closing tab using shortcut: {hotkey[0]}+{hotkey[1]} on {current_os}"
                )
            else:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Closing current page using shortcut: {hotkey[0]}+{hotkey[1]} on {current_os}"
                )

            pyautogui.hotkey(*hotkey)

            if current_os == "Darwin":
                try:
                    script = 'tell application "System Events" to keystroke "w" using command down'
                    subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] AppleScript close fallback sent on Darwin")
                except Exception as fallback_error:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] AppleScript close fallback failed: {fallback_error}")

            self.sleep_with_mouse_activity(0.8)

        except Exception:
            pass

    def request_stop(self, reason=None):
        self.is_running = False
        if reason:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {reason}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Stopping user behavior simulation...")

    def should_run_scheduled_task(self, task_config):
        if not task_config.get('enabled', False):
            return False
            
        current_time = datetime.now().strftime("%H:%M")
        target_time = task_config.get('time', '00:00')

        current_datetime = datetime.strptime(current_time, "%H:%M")
        target_datetime = datetime.strptime(target_time, "%H:%M")

        time_diff = abs((current_datetime - target_datetime).total_seconds())

        return time_diff <= 60

    def run_random_applications(self):
        if not self.config.get('app_execution', {}).get('enabled', False):
            return

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting random application execution")

        app_config = self.config.get('app_execution', {})
        apps_to_run = random.randint(*app_config.get('apps_per_session', [1, 3]))

        current_os = platform.system()
        if current_os == "Windows":
            available_apps = app_config.get('windows_apps', [])
            system_apps = app_config.get('windows_system_apps', [])
        elif current_os == "Linux":
            available_apps = app_config.get('linux_apps', [])
            system_apps = app_config.get('linux_system_apps', [])
        else:
            available_apps = app_config.get('macos_apps', [])
            system_apps = app_config.get('macos_system_apps', [])

        all_apps = available_apps + system_apps

        if not all_apps:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No applications configured for {current_os}")
            return

        launched_processes = []

        for _ in range(min(apps_to_run, len(all_apps))):
            app = random.choice(all_apps)

            try:
                if current_os == "Windows":
                    process = self.launch_windows_app(app)
                elif current_os == "Linux":
                    process = self.launch_linux_app(app)
                else:
                    process = self.launch_macos_app(app)

                if process:
                    run_duration = random.randint(*app_config.get('app_run_duration', [30, 300]))
                    launched_processes.append((process, app, run_duration))
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Launched {app}, will run for {run_duration} seconds")

                    time.sleep(random.randint(5, 15))

            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to launch {app}: {e}")

        if launched_processes:
            self.manage_running_applications(launched_processes)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed random application execution")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def launch_windows_app(self, app):
        try:
            if app.get('type') == 'command':
                process = subprocess.Popen(
                    app['command'],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif app.get('type') == 'executable':
                process = subprocess.Popen(
                    app['path'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif app.get('type') == 'system':
                process = subprocess.Popen(
                    f"start {app['name']}",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                process = subprocess.Popen(
                    app,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

            return process

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Windows app launch error: {e}")
            return None

    def launch_linux_app(self, app):
        try:
            if app.get('type') == 'command':
                process = subprocess.Popen(
                    app['command'],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid
                )
            elif app.get('type') == 'executable':
                process = subprocess.Popen(
                    app['path'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid
                )
            elif app.get('type') == 'desktop':
                process = subprocess.Popen(
                    ['gtk-launch', app['name']],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid
                )
            else:
                process = subprocess.Popen(
                    app,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid
                )

            return process

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Linux app launch error: {e}")
            return None

    def launch_macos_app(self, app):
        try:
            if app.get('type') == 'application':
                process = subprocess.Popen(
                    ['open', '-a', app['name']],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif app.get('type') == 'command':
                process = subprocess.Popen(
                    app['command'],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                process = subprocess.Popen(
                    ['open', '-a', app],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

            return process

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] macOS app launch error: {e}")
            return None

    def manage_running_applications(self, launched_processes):
        start_time = time.time()

        while launched_processes and self.is_running:
            current_time = time.time()

            for i, (process, app_name, duration) in enumerate(launched_processes[:]):
                elapsed = current_time - start_time

                if elapsed >= duration or process.poll() is not None:
                    try:
                        self.terminate_application(process, app_name)
                        launched_processes.remove((process, app_name, duration))
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Closed {app_name}")
                    except Exception as e:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error closing {app_name}: {e}")

            time.sleep(5)

    def terminate_application(self, process, app_name):
        try:
            current_os = platform.system()

            if current_os == "Windows":
                process.terminate()
                time.sleep(2)
                if process.poll() is None:
                    process.kill()

                if isinstance(app_name, dict) and app_name.get('type') == 'system':
                    subprocess.run(f'taskkill /f /im {app_name["process_name"]}.exe', shell=True, capture_output=True)

            elif current_os == "Linux":
                import signal
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    time.sleep(2)
                    if process.poll() is None:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except:
                    process.terminate()
                    time.sleep(2)
                    if process.poll() is None:
                        process.kill()

            else:
                process.terminate()
                time.sleep(2)
                if process.poll() is None:
                    process.kill()

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error terminating process: {e}")

    def discover_system_applications(self):
        current_os = platform.system()
        discovered_apps = []

        try:
            if current_os == "Windows":
                discovered_apps = self.discover_windows_apps()
            elif current_os == "Linux":
                discovered_apps = self.discover_linux_apps()
            else:
                discovered_apps = self.discover_macos_apps()

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Discovered {len(discovered_apps)} applications")
            return discovered_apps

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error discovering applications: {e}")
            return []

    def discover_windows_apps(self):
        apps = []

        try:
            common_apps = [
                'notepad.exe', 'calc.exe', 'mspaint.exe', 'wordpad.exe',
                'explorer.exe', 'cmd.exe', 'powershell.exe'
            ]

            for app in common_apps:
                apps.append({
                    'type': 'command',
                    'command': app,
                    'name': app.replace('.exe', '')
                })

            program_paths = [
                r"C:\Program Files",
                r"C:\Program Files (x86)",
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')
            ]

            for path in program_paths:
                if os.path.exists(path):
                    for item in os.listdir(path)[:10]:
                        item_path = os.path.join(path, item)
                        if os.path.isdir(item_path):
                            for exe_file in os.listdir(item_path):
                                if exe_file.endswith('.exe') and not exe_file.startswith('unins'):
                                    apps.append({
                                        'type': 'executable',
                                        'path': os.path.join(item_path, exe_file),
                                        'name': exe_file.replace('.exe', '')
                                    })
                                    if len(apps) > 20:
                                        break
                        if len(apps) > 20:
                            break

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Windows app discovery error: {e}")

        return apps[:15]

    def imap_operations(self):
        if not self.config.get('imap_config', {}).get('enabled', False):
            return

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting IMAP operations")

        try:
            import imaplib

            imap_config = self.config['imap_config']
            servers = imap_config.get('servers', [])
            operations_per_session_range = imap_config.get('operations_per_session', [2, 5])
            operations_count = random.randint(*operations_per_session_range)

            for server_config in servers:
                try:
                    if server_config.get('use_ssl', True):
                        mail = imaplib.IMAP4_SSL(server_config['server'], server_config.get('port', 993))
                    else:
                        mail = imaplib.IMAP4(server_config['server'], server_config.get('port', 143))

                    mail.login(server_config['username'], server_config['password'])

                    operations = imap_config.get('operations', ['list_folders', 'check_inbox', 'search_emails'])
                    selected_operations = random.sample(operations, min(operations_count, len(operations)))

                    for operation in selected_operations:
                        try:
                            if operation == 'list_folders':
                                self.imap_list_folders(mail, server_config)

                            elif operation == 'check_inbox':
                                self.imap_check_inbox(mail, server_config)

                            elif operation == 'search_emails':
                                self.imap_search_emails(mail, server_config)

                            elif operation == 'read_recent':
                                self.imap_read_recent_emails(mail, server_config)

                            elif operation == 'mark_read':
                                self.imap_mark_emails_read(mail, server_config)

                            elif operation == 'check_sent':
                                self.imap_check_sent_folder(mail, server_config)

                            time.sleep(random.randint(5, 15))

                        except Exception as e:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] IMAP operation {operation} error: {e}")

                    mail.close()
                    mail.logout()

                except Exception as e:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] IMAP connection error to {server_config['server']}: {e}")

        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IMAP operations require imaplib (should be built-in)")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IMAP operations error: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed IMAP operations")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def imap_list_folders(self, mail, server_config):
        try:
            status, folders = mail.list()
            if status == 'OK':
                folder_count = len(folders)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] IMAP LIST on {server_config['server']}: {folder_count} folders")

                log_path = self.get_save_path("ping_logs")
                if not os.path.exists(log_path):
                    os.makedirs(log_path)

                log_file = os.path.join(log_path,
                                        f"imap_folders_{server_config['server']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                with open(log_file, 'w') as f:
                    f.write(f"IMAP Folders for {server_config['server']}:\n")
                    f.write(f"User: {server_config['username']}\n")
                    f.write(f"Timestamp: {datetime.now()}\n\n")
                    for folder in folders:
                        f.write(f"{folder.decode('utf-8')}\n")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error listing folders: {e}")

    def imap_check_inbox(self, mail, server_config):
        try:
            mail.select('INBOX')
            status, messages = mail.search(None, 'ALL')

            if status == 'OK':
                message_ids = messages[0].split()
                message_count = len(message_ids)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] IMAP INBOX check on {server_config['server']}: {message_count} messages")

                status, unread = mail.search(None, 'UNSEEN')
                if status == 'OK':
                    unread_count = len(unread[0].split()) if unread[0] else 0
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] IMAP INBOX unread: {unread_count} messages")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error checking inbox: {e}")

    def imap_search_emails(self, mail, server_config):
        try:
            mail.select('INBOX')

            search_criteria = [
                'FROM "gmail.com"',
                'SUBJECT "notification"',
                'SINCE "01-Jan-2024"',
                'BEFORE "31-Dec-2024"',
                'UNSEEN'
            ]

            criteria = random.choice(search_criteria)
            status, messages = mail.search(None, criteria)

            if status == 'OK':
                message_ids = messages[0].split()
                result_count = len(message_ids)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] IMAP SEARCH '{criteria}' on {server_config['server']}: {result_count} results")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error searching emails: {e}")

    def imap_read_recent_emails(self, mail, server_config):
        try:
            mail.select('INBOX')
            status, messages = mail.search(None, 'ALL')

            if status == 'OK':
                message_ids = messages[0].split()
                if message_ids:
                    recent_count = min(3, len(message_ids))
                    recent_ids = message_ids[-recent_count:]

                    for msg_id in recent_ids:
                        status, msg_data = mail.fetch(msg_id, '(RFC822)')
                        if status == 'OK':
                            import email
                            from email.header import decode_header

                            email_body = msg_data[0][1]
                            email_message = email.message_from_bytes(email_body)

                            subject = decode_header(email_message["Subject"])[0][0]
                            if isinstance(subject, bytes):
                                subject = subject.decode()

                            sender = email_message.get("From")

                            log_path = self.get_save_path("ping_logs")
                            if not os.path.exists(log_path):
                                os.makedirs(log_path)

                            log_file = os.path.join(log_path,
                                                    f"imap_email_{msg_id.decode()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                            with open(log_file, 'w', encoding='utf-8') as f:
                                f.write(f"IMAP Email Read from {server_config['server']}:\n")
                                f.write(f"Message ID: {msg_id.decode()}\n")
                                f.write(f"From: {sender}\n")
                                f.write(f"Subject: {subject}\n")
                                f.write(f"Timestamp: {datetime.now()}\n\n")

                                if email_message.is_multipart():
                                    for part in email_message.walk():
                                        if part.get_content_type() == "text/plain":
                                            body = part.get_payload(decode=True)
                                            if body:
                                                f.write(body.decode('utf-8', errors='ignore')[:500])
                                                break
                                else:
                                    body = email_message.get_payload(decode=True)
                                    if body:
                                        f.write(body.decode('utf-8', errors='ignore')[:500])

                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] IMAP READ {recent_count} recent emails from {server_config['server']}")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error reading recent emails: {e}")

    def imap_mark_emails_read(self, mail, server_config):
        try:
            mail.select('INBOX')
            status, messages = mail.search(None, 'UNSEEN')

            if status == 'OK' and messages[0]:
                unread_ids = messages[0].split()
                if unread_ids:
                    mark_count = min(random.randint(1, 3), len(unread_ids))
                    selected_ids = random.sample(unread_ids, mark_count)

                    for msg_id in selected_ids:
                        mail.store(msg_id, '+FLAGS', '\\Seen')

                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] IMAP MARKED {mark_count} emails as read on {server_config['server']}")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error marking emails as read: {e}")

    def imap_check_sent_folder(self, mail, server_config):
        try:
            sent_folders = ['Sent', 'INBOX.Sent', '[Gmail]/Sent Mail', 'Sent Items']

            for folder_name in sent_folders:
                try:
                    status = mail.select(folder_name)
                    if status[0] == 'OK':
                        status, messages = mail.search(None, 'ALL')
                        if status == 'OK':
                            message_count = len(messages[0].split()) if messages[0] else 0
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] IMAP SENT folder '{folder_name}' on {server_config['server']}: {message_count} messages")
                        break
                except:
                    continue

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error checking sent folder: {e}")

    def discover_linux_apps(self):
        apps = []

        try:
            common_commands = [
                'gedit', 'kate', 'nano', 'vim', 'firefox', 'chromium-browser',
                'google-chrome', 'libreoffice', 'calc', 'writer', 'terminal',
                'gnome-terminal', 'konsole', 'xterm', 'nautilus', 'dolphin',
                'thunar', 'pcmanfm'
            ]

            for cmd in common_commands:
                result = subprocess.run(['which', cmd], capture_output=True, text=True)
                if result.returncode == 0:
                    apps.append({
                        'type': 'command',
                        'command': cmd,
                        'name': cmd
                    })

            desktop_paths = [
                '/usr/share/applications',
                os.path.expanduser('~/.local/share/applications')
            ]

            for path in desktop_paths:
                if os.path.exists(path):
                    for desktop_file in os.listdir(path):
                        if desktop_file.endswith('.desktop'):
                            try:
                                with open(os.path.join(path, desktop_file), 'r') as f:
                                    content = f.read()
                                    if 'Exec=' in content and 'NoDisplay=true' not in content:
                                        apps.append({
                                            'type': 'desktop',
                                            'name': desktop_file.replace('.desktop', ''),
                                            'file': desktop_file
                                        })
                                        if len(apps) > 20:
                                            break
                            except:
                                continue

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Linux app discovery error: {e}")

        return apps[:15]

    def discover_macos_apps(self):
        apps = []

        try:
            app_paths = ['/Applications', os.path.expanduser('~/Applications')]

            for path in app_paths:
                if os.path.exists(path):
                    for item in os.listdir(path):
                        if item.endswith('.app'):
                            apps.append({
                                'type': 'application',
                                'name': item.replace('.app', ''),
                                'path': os.path.join(path, item)
                            })
                            if len(apps) > 15:
                                break

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] macOS app discovery error: {e}")

        return apps[:15]

    def get_next_scheduled_task(self):
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            return None

        current_time = datetime.now().strftime("%H:%M")
        current_datetime = datetime.strptime(current_time, "%H:%M")

        upcoming_tasks = []

        for task_config in self.config['scheduled_tasks'].get('tasks', []):
            if not task_config.get('enabled', False):
                continue

            target_datetime = datetime.strptime(task_config.get('time', '00:00'), "%H:%M")

            if target_datetime > current_datetime:
                time_diff = (target_datetime - current_datetime).total_seconds()
                upcoming_tasks.append((time_diff, task_config))
            else:
                time_diff = (target_datetime + timedelta(days=1) - current_datetime).total_seconds()
                upcoming_tasks.append((time_diff, task_config))

        if upcoming_tasks:
            upcoming_tasks.sort(key=lambda x: x[0])
            return upcoming_tasks[0]

        return None

    def wait_between_tasks(self):
        task_wait_minutes = self.config.get('task_wait_minutes', [2, 8])
        wait_time = random.randint(*task_wait_minutes) * 60
        time.sleep(wait_time)

    def get_random_text_from_api(self):
        apis = self.config.get('text_apis', [])

        for _ in range(3):
            try:
                api_url = random.choice(apis)

                if "quotable.io" in api_url:
                    response = requests.get(api_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        return f"Quote: {data['content']}\nAuthor: {data['author']}"

                elif "loremipsum.io" in api_url:
                    response = requests.get(f"{api_url}?type=paragraph&amount=3", timeout=10)
                    if response.status_code == 200:
                        return response.text

                elif "jsonplaceholder.typicode.com" in api_url:
                    post_id = random.randint(1, 100)
                    response = requests.get(f"{api_url}/{post_id}", timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        return f"Title: {data['title']}\n\nContent: {data['body']}"

                else:
                    response = requests.get(api_url, timeout=10)
                    if response.status_code == 200:
                        return response.text[:1000]

            except:
                continue

        return self.generate_random_text()

    def get_save_path(self, path_type):
        configured_path = self.config.get('save_paths', {}).get(path_type, "")

        if configured_path and os.path.exists(configured_path):
            return configured_path

        if path_type == "text_files":
            return random.choice([self.get_desktop_path(), self.get_documents_path()])
        elif path_type == "downloads":
            return os.path.join(self.get_desktop_path(), "downloads")
        elif path_type == "ping_logs":
            return os.path.join(self.get_desktop_path(), "ping_logs")
        elif path_type == "received_files":
            return os.path.join(self.get_desktop_path(), "received")
        else:
            return self.get_desktop_path()

    def extract_links_from_page(self, url):
        try:
            from urllib.parse import urljoin, urlparse

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return []

            content = response.text
            base_domain = urlparse(url).netloc

            link_patterns = [
                r'href=[\'"]([^\'"]*)[\'"]',
                r'<a[^>]+href=[\'"]([^\'"]*)[\'"]'
            ]

            links = []
            for pattern in link_patterns:
                found_links = re.findall(pattern, content, re.IGNORECASE)
                links.extend(found_links)

            def is_resource_link(candidate_url):
                parsed_candidate = urlparse(candidate_url)
                path = parsed_candidate.path.lower()
                filename = os.path.basename(path)

                if not filename:
                    return False

                resource_extensions = {
                    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico',
                    '.css', '.js', '.mjs', '.json', '.xml', '.txt', '.pdf',
                    '.mp4', '.webm', '.mov', '.avi', '.mp3', '.wav', '.zip',
                    '.rar', '.7z', '.tar', '.gz', '.manifest', '.map'
                }

                extension = os.path.splitext(filename)[1].lower()
                if extension in resource_extensions:
                    return True

                resource_markers = [
                    'manifest', 'favicon', 'apple-touch-icon', 'icon', 'sprite',
                    '/images/', '/img/', '/static/', '/assets/', '/media/', '/css/', '/js/'
                ]

                return any(marker in path for marker in resource_markers)

            valid_links = []
            for link in links:
                if not link or link.startswith('#') or link.startswith('javascript:'):
                    continue

                if link.startswith('mailto:') or link.startswith('tel:'):
                    continue

                full_url = urljoin(url, link)
                parsed_url = urlparse(full_url)

                if is_resource_link(full_url):
                    continue

                if parsed_url.netloc == base_domain and parsed_url.scheme in ['http', 'https']:
                    if full_url not in valid_links and full_url != url:
                        valid_links.append(full_url)

                if len(valid_links) >= 20:
                    break

            return valid_links[:20]

        except Exception:
            return []

    def simulate_human_scrolling(self, duration, run_until=None):
        if not self.config.get('page_interaction', {}).get('scroll_enabled', False):
            return

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = self.scale_duration(0.1)

            scroll_patterns = self.config.get('page_interaction', {}).get('scroll_patterns', ['top_to_bottom'])
            scroll_speed_range = self.config.get('page_interaction', {}).get('scroll_speed', [1, 1])
            scroll_pause_range = self.config.get('page_interaction', {}).get('scroll_pauses', [4, 10])
            pre_scroll_pause_range = self.config.get('page_interaction', {}).get('initial_scroll_pause_seconds', [2, 5])

            if isinstance(pre_scroll_pause_range, (list, tuple)) and len(pre_scroll_pause_range) == 2:
                pre_scroll_low = float(pre_scroll_pause_range[0])
                pre_scroll_high = float(pre_scroll_pause_range[1])
                if pre_scroll_low > pre_scroll_high:
                    pre_scroll_low, pre_scroll_high = pre_scroll_high, pre_scroll_low
            else:
                pre_scroll_low, pre_scroll_high = 1.0, 4.0

            scroll_pattern = random.choice(scroll_patterns)
            scroll_speed = random.randint(*scroll_speed_range)

            end_time = time.time() + duration

            screen_width, screen_height = pyautogui.size()
            center_x = screen_width // 2
            center_y = screen_height // 2

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting {scroll_pattern} scrolling for {duration}s")
            time.sleep(random.uniform(pre_scroll_low, pre_scroll_high))

            if scroll_pattern == "top_to_bottom":
                while time.time() < end_time:
                    if run_until is not None and time.time() >= run_until:
                        break

                    if random.random() < 0.22:
                        scroll_amount = random.randint(20, 70) * scroll_speed * random.choice([-1, 1])
                    else:
                        scroll_amount = random.randint(35, 120) * scroll_speed
                    pyautogui.scroll(-scroll_amount, x=center_x, y=center_y)
                    pause_time = random.uniform(max(1.2, scroll_pause_range[0] * 0.7), max(2.5, scroll_pause_range[1] * 0.8))
                    time.sleep(pause_time)

            elif scroll_pattern == "bottom_to_top":
                for _ in range(3):
                    if run_until is not None and time.time() >= run_until:
                        break

                    if time.time() >= end_time:
                        break
                    scroll_amount = random.randint(90, 220) * scroll_speed
                    pyautogui.scroll(-scroll_amount, x=center_x, y=center_y)
                    time.sleep(random.uniform(0.8, 1.6))

                while time.time() < end_time:
                    if run_until is not None and time.time() >= run_until:
                        break

                    if random.random() < 0.18:
                        scroll_amount = random.randint(25, 80) * scroll_speed
                    else:
                        scroll_amount = random.randint(40, 130) * scroll_speed
                    pyautogui.scroll(scroll_amount, x=center_x, y=center_y)
                    pause_time = random.uniform(max(1.2, scroll_pause_range[0] * 0.7), max(2.5, scroll_pause_range[1] * 0.8))
                    time.sleep(pause_time)

            elif scroll_pattern == "middle_out":
                pyautogui.scroll(-1000, x=center_x, y=center_y)
                time.sleep(random.uniform(1.0, 2.0))

                while time.time() < end_time:
                    if run_until is not None and time.time() >= run_until:
                        break

                    direction = random.choice([-1, 1, 1])
                    scroll_amount = random.randint(20, 90) * scroll_speed * direction
                    pyautogui.scroll(scroll_amount, x=center_x, y=center_y)
                    pause_time = random.uniform(max(1.0, scroll_pause_range[0] * 0.7), max(2.2, scroll_pause_range[1] * 0.8))
                    time.sleep(pause_time)

            elif scroll_pattern == "random_sections":
                while time.time() < end_time:
                    if run_until is not None and time.time() >= run_until:
                        break

                    scroll_amount = random.randint(-90, 90) * scroll_speed
                    pyautogui.scroll(scroll_amount, x=center_x, y=center_y)
                    pause_time = random.uniform(max(1.0, scroll_pause_range[0] * 0.7), max(2.2, scroll_pause_range[1] * 0.8))
                    time.sleep(pause_time)

                    if random.random() < 0.42:
                        long_pause = random.uniform(1.5, 5)
                        time.sleep(long_pause)

            time.sleep(random.uniform(1, 3))

        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Page scrolling requires pyautogui: pip install pyautogui")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scrolling error: {e}")

    def interact_with_search_bar(self, query_override=None):
        search_config = self.config.get('search_interaction', {})

        if not search_config.get('enabled', False):
            return

        query = str(query_override if query_override is not None else search_config.get('query', '')).strip()
        if not query:
            return

        wait_range = search_config.get('wait_after_open_seconds', [3, 6])
        if isinstance(wait_range, (list, tuple)) and len(wait_range) == 2:
            wait_time = random.uniform(float(wait_range[0]), float(wait_range[1]))
        else:
            wait_time = 3

        time.sleep(wait_time)

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = self.scale_duration(0.1)

            search_url = str(search_config.get('search_url', 'https://www.google.com/')).strip()
            if search_url:
                webbrowser.open_new_tab(search_url)
                time.sleep(random.uniform(1.5, 3.0))

            if platform.system() == "Darwin":
                browser_names = ['Firefox', 'Google Chrome', 'Safari', 'Brave Browser', 'Opera']
                browser_activated = False

                for browser_name in browser_names:
                    try:
                        result = subprocess.run(['open', '-a', browser_name], capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            browser_activated = True
                            time.sleep(1)
                            break
                    except Exception:
                        continue

                if not browser_activated:
                    try:
                        pyautogui.hotkey('command', 'tab')
                        time.sleep(1)
                    except Exception:
                        pass

            screen_width, screen_height = pyautogui.size()
            click_coordinates = search_config.get('click_coordinates', {}) or {}
            tab_presses = int(search_config.get('tab_presses', 0) or 0)
            focus_pause = float(search_config.get('focus_pause', 0.75))
            human_mouse = search_config.get('human_mouse', {}) or {}

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Focusing search box before typing")

            def parse_range(value, default_low, default_high):
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    low = float(value[0])
                    high = float(value[1])
                    if low > high:
                        low, high = high, low
                    return low, high
                return float(default_low), float(default_high)

            move_low, move_high = parse_range(human_mouse.get('move_duration', [0.25, 0.7]), 0.25, 0.7)
            jitter_low, jitter_high = parse_range(human_mouse.get('jitter_pixels', [6, 16]), 6, 16)
            hesitation_low, hesitation_high = parse_range(human_mouse.get('hesitation_pause', [0.05, 0.2]), 0.05, 0.2)
            human_mouse_enabled = bool(human_mouse.get('enabled', True))

            def click_search_field(target_x, target_y):
                pyautogui.click(target_x, target_y)
                time.sleep(0.2)

            if search_config.get('click_before_typing', True):
                click_x = click_coordinates.get('x')
                click_y = click_coordinates.get('y')

                if click_x is not None and click_y is not None:
                    click_search_field(int(click_x), int(click_y))
                else:
                    click_search_field(screen_width // 2 - 120, screen_height // 2)

                time.sleep(focus_pause)

            if tab_presses > 0:
                for _ in range(tab_presses):
                    pyautogui.press('tab')
                    time.sleep(0.2)

            if not search_config.get('click_before_typing', True) and tab_presses <= 0:
                pyautogui.click(screen_width // 2, screen_height // 2)
                time.sleep(focus_pause)

            typing_interval = float(search_config.get('typing_interval', 0.05))
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Typing query into focused field: {query}")
            pyautogui.write(query, interval=self.scale_duration(typing_interval))

            time.sleep(float(search_config.get('post_type_pause', 0.5)))

            if search_config.get('press_enter', True):
                pyautogui.press('enter')

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Typed search query: {query}")

        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Search interaction requires pyautogui: pip install pyautogui")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Search interaction error: {e}")

    def simulate_page_reading(self, base_time, run_until=None):
        reading_time = random.randint(int(base_time * 0.7), int(base_time * 1.3))

        if run_until is not None and time.time() >= run_until:
            return

        if self.config.get('page_interaction', {}).get('scroll_enabled', False):
            total_scroll_time_range = self.config.get('page_interaction', {}).get('total_scroll_time', [30, 120])
            scroll_time = random.randint(*total_scroll_time_range)
            scroll_time = min(scroll_time, reading_time - 10)

            if scroll_time > 10:
                initial_pause = random.randint(3, 8)
                self.sleep_with_mouse_activity(initial_pause)

                if run_until is not None and time.time() >= run_until:
                    return

                self.simulate_human_scrolling(scroll_time, run_until=run_until)

                if run_until is not None and time.time() >= run_until:
                    return

                remaining_time = reading_time - initial_pause - scroll_time
                if remaining_time > 0:
                    self.sleep_with_mouse_activity(remaining_time)
            else:
                self.sleep_with_mouse_activity(reading_time)
        else:
            self.sleep_with_mouse_activity(reading_time)

    def open_link_like_human(self, url):
        link_config = self.config.get('link_interaction', {}) or {}

        def parse_range(value, default_low, default_high):
            if isinstance(value, (list, tuple)) and len(value) == 2:
                low = float(value[0])
                high = float(value[1])
                if low > high:
                    low, high = high, low
                return low, high
            return float(default_low), float(default_high)

        if not link_config.get('enabled', True):
            webbrowser.open(url)
            return False

        pre_low, pre_high = parse_range(link_config.get('pre_open_pause_seconds', [0.4, 1.4]), 0.4, 1.4)
        post_low, post_high = parse_range(link_config.get('post_open_pause_seconds', [1.0, 2.5]), 1.0, 2.5)
        open_new_tab_probability = float(link_config.get('open_new_tab_probability', 0.65) or 0.65)
        open_new_tab_probability = max(0.0, min(1.0, open_new_tab_probability))

        self.sleep_with_mouse_activity(random.uniform(pre_low, pre_high))

        if random.random() < open_new_tab_probability:
            webbrowser.open(url, new=2)
            opened_new_tab = True
        else:
            webbrowser.open(url, new=0)
            opened_new_tab = False

        self.sleep_with_mouse_activity(random.uniform(post_low, post_high))
        return opened_new_tab

    def browse_websites(self, skip_post_wait=False, run_until=None):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting website browsing task")
        websites = self.config.get('websites', ['https://www.google.com'])
        search_config = self.config.get('search_interaction', {}) or {}
        search_url = str(search_config.get('search_url', 'https://www.google.com/')).strip()
        websites_to_visit = list(dict.fromkeys(websites))
        random.shuffle(websites_to_visit)

        non_search_websites = [site for site in websites_to_visit if not self._is_search_page(site, search_url)]
        web_rounds_range = self.config.get('web_rounds_per_session', [3, 8])
        search_round_probability = float(search_config.get('search_round_probability', 0.4) or 0.4)
        search_round_probability = max(0.0, min(1.0, search_round_probability))

        if isinstance(web_rounds_range, (list, tuple)) and len(web_rounds_range) == 2:
            web_rounds = random.randint(int(web_rounds_range[0]), int(web_rounds_range[1]))
        else:
            web_rounds = random.randint(3, 8)

        site_pool = non_search_websites or websites_to_visit
        round_plan = []

        if search_config.get('enabled', False) and search_url and site_pool and web_rounds >= 2:
            round_plan.append(('search', None))
            round_plan.append(('site', random.choice(site_pool)))

            remaining_rounds = web_rounds - 2
            for _ in range(remaining_rounds):
                if random.random() < search_round_probability:
                    round_plan.append(('search', None))
                else:
                    round_plan.append(('site', random.choice(site_pool)))

            random.shuffle(round_plan)
        else:
            for _ in range(web_rounds):
                if search_config.get('enabled', False) and search_url and site_pool and random.random() < search_round_probability:
                    round_plan.append(('search', None))
                else:
                    round_plan.append(('site', random.choice(site_pool) if site_pool else None))

        def explore_site(main_site):
            if run_until is not None and time.time() >= run_until:
                return

            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Opening main site: {main_site}")
                self.open_link_like_human(main_site)

                self.sleep_with_mouse_activity(random.randint(4, 8))

                links_per_website_range = self.config.get('links_per_website', [2, 6])
                links_to_visit = random.randint(*links_per_website_range)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Finding {links_to_visit} additional links from {main_site}")

                extracted_links = self.extract_links_from_page(main_site)

                if extracted_links:
                    selected_links = random.sample(extracted_links, min(links_to_visit, len(extracted_links)))

                    for link in selected_links:
                        if run_until is not None and time.time() >= run_until:
                            break

                        try:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Opening additional link: {link}")
                            opened_new_tab = self.open_link_like_human(link)

                            self.sleep_with_mouse_activity(random.randint(2, 5))

                            link_explore_time_range = self.config.get('link_interaction', {}).get('explore_time_seconds', [15, 90])
                            link_explore_time = random.randint(*link_explore_time_range)
                            self.simulate_page_reading(link_explore_time, run_until=run_until)
                            self.maybe_close_current_tab(opened_new_tab=opened_new_tab)

                            max_crawl_depth = self.config.get('max_crawl_depth', 2)
                            if max_crawl_depth > 1:
                                sub_links = self.extract_links_from_page(link)
                                if sub_links:
                                    sub_link = random.choice(sub_links)
                                    if run_until is not None and time.time() >= run_until:
                                        break

                                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Opening sub-link: {sub_link}")
                                    opened_new_tab = self.open_link_like_human(sub_link)

                                    self.sleep_with_mouse_activity(random.randint(2, 4))

                                    sub_link_time_range = self.config.get('link_interaction', {}).get('explore_time_seconds', [10, 60])
                                    sub_link_time = random.randint(*sub_link_time_range)
                                    self.simulate_page_reading(sub_link_time, run_until=run_until)
                                    self.maybe_close_current_tab(opened_new_tab=opened_new_tab)

                        except Exception:
                            pass

                        self.sleep_with_mouse_activity(random.randint(5, 15))
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No additional links found for {main_site}")

                explore_time_range = self.config.get('explore_time_per_site', [30, 120])
                explore_time = random.randint(*explore_time_range)
                self.simulate_page_reading(explore_time, run_until=run_until)

                self.sleep_with_mouse_activity(random.randint(6, 12))

            except Exception:
                pass

        def perform_search_round():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Opening search page: {search_url}")
            opened_new_tab = self.open_link_like_human(search_url)

            self.sleep_with_mouse_activity(random.randint(4, 8))
            search_queries = search_config.get('search_queries', [])
            if isinstance(search_queries, list) and search_queries:
                query = str(random.choice(search_queries)).strip()
            else:
                query = str(search_config.get('query', '')).strip()

            self.interact_with_search_bar(query_override=query)

            post_search_range = search_config.get('post_search_read_seconds', [20, 60])
            if isinstance(post_search_range, (list, tuple)) and len(post_search_range) == 2:
                post_search_time = random.randint(int(post_search_range[0]), int(post_search_range[1]))
            else:
                post_search_time = random.randint(20, 60)

            self.simulate_page_reading(post_search_time, run_until=run_until)
            self.maybe_close_current_tab(opened_new_tab=opened_new_tab)

        for round_type, target_site in round_plan:
            if not self.is_running:
                break

            if run_until is not None and time.time() >= run_until:
                break

            if round_type == 'search':
                try:
                    perform_search_round()
                except Exception:
                    pass
            else:
                if target_site:
                    explore_site(target_site)

            if not self.is_running:
                break

            if run_until is not None and time.time() >= run_until:
                break

            time.sleep(random.randint(3, 10))

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed website browsing task")
        if not skip_post_wait and not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def browse_filesystem(self, skip_post_wait=False, run_until=None):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting filesystem exploration task")
        explorer = FilesystemExplorer(self)
        explorer.explore(run_until=run_until)

        if not skip_post_wait and not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def get_orchestration_config(self):
        orchestration_config = self.config.get('task_orchestration', {}) or {}
        modules = orchestration_config.get('modules', ['browse_websites', 'browse_filesystem'])
        if not isinstance(modules, list) or not modules:
            modules = ['browse_websites', 'browse_filesystem']

        initial_sequence = orchestration_config.get(
            'initial_sequence',
            ['browse_websites', 'browse_filesystem', 'browse_websites']
        )
        if not isinstance(initial_sequence, list):
            initial_sequence = ['browse_websites', 'browse_filesystem', 'browse_websites']

        duration_range = orchestration_config.get('module_duration_minutes', [1, 5])
        if not (isinstance(duration_range, (list, tuple)) and len(duration_range) == 2):
            duration_range = [1, 3]

        return {
            'enabled': bool(orchestration_config.get('enabled', False)),
            'modules': [str(name) for name in modules if name],
            'initial_sequence': [str(name) for name in initial_sequence if name],
            'module_duration_minutes': duration_range,
        }

    def run_module_for_duration(self, task_name, duration_minutes):
        duration_seconds = max(0.0, float(duration_minutes) * 60.0)
        run_until = time.time() + duration_seconds
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Orchestrating task '{task_name}' for {int(duration_minutes)} minute(s)"
        )

        if task_name == 'browse_websites':
            self.browse_websites(skip_post_wait=True, run_until=run_until)
            return True

        if task_name == 'browse_filesystem':
            self.config.setdefault('filesystem_exploration', {})['enabled'] = True
            self.browse_filesystem(skip_post_wait=True, run_until=run_until)
            return True

        return False

    def run_orchestrated_modules(self, single_run=False):
        orchestration_config = self.get_orchestration_config()
        if not orchestration_config['enabled']:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Task orchestration is disabled in the configuration")
            return False

        if not self.is_running:
            self.is_running = True

        iteration = 0
        modules = orchestration_config['modules']
        initial_sequence = orchestration_config['initial_sequence']
        duration_range = orchestration_config['module_duration_minutes']

        if isinstance(duration_range, (list, tuple)) and len(duration_range) == 2:
            min_minutes = max(1, int(duration_range[0]))
            max_minutes = max(min_minutes, int(duration_range[1]))
        else:
            min_minutes = 1
            max_minutes = 5

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting orchestrated module cycle")

        while self.is_running:
            self.wait_for_active_hours()

            if not self.is_running:
                break

            session_duration_range = self.config.get('session_duration_minutes', [30, 90])
            if isinstance(session_duration_range, (list, tuple)) and len(session_duration_range) == 2:
                session_duration = random.randint(int(session_duration_range[0]), int(session_duration_range[1]))
            else:
                session_duration = random.randint(30, 90)

            session_speed_multiplier = self.get_session_speed_multiplier()
            session_end_time = datetime.now() + timedelta(minutes=session_duration / session_speed_multiplier)

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Starting orchestrated session for {session_duration} minutes at {session_speed_multiplier}x speed"
            )

            while datetime.now() < session_end_time and self.is_running and self.is_within_active_hours():
                if iteration < len(initial_sequence):
                    task_name = initial_sequence[iteration]
                else:
                    task_name = random.choice(modules)

                if task_name not in modules:
                    task_name = random.choice(modules)

                duration_minutes = random.randint(min_minutes, max_minutes)
                self.run_module_for_duration(task_name, duration_minutes)
                iteration += 1

                if not self.is_running or datetime.now() >= session_end_time:
                    break

            if single_run:
                break

            if self.is_running:
                session_break = random.randint(1800, 7200)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Orchestrated session break for {int(session_break / 60)} minutes"
                )
                time.sleep(session_break)

        return True

    def run_filesystem_exploration(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Running continuous filesystem exploration task")

        while self.is_running:
            self.browse_filesystem(skip_post_wait=True)

            if not self.is_running:
                break

            pause_seconds = random.randint(2, 8)
            self.sleep_with_mouse_activity(pause_seconds)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Filesystem exploration task stopped")

    def _is_search_page(self, url, search_url):
        if not url or not search_url:
            return False

        def normalize_domain(value):
            parsed = urlparse(value)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain

        return normalize_domain(url) == normalize_domain(search_url)

    def close_browser(self):
        try:
            current_os = platform.system()

            if current_os == "Windows":
                browser_processes = [
                    'firefox.exe', 'chrome.exe', 'msedge.exe', 'iexplore.exe',
                    'brave.exe', 'opera.exe', 'vivaldi.exe'
                ]

                for process in browser_processes:
                    try:
                        subprocess.run(f'taskkill /f /im {process}', shell=True, capture_output=True, timeout=10)
                    except:
                        continue

            elif current_os == "Linux":
                browser_processes = [
                    'firefox', 'google-chrome', 'chromium-browser', 'brave-browser',
                    'opera', 'vivaldi'
                ]

                for process in browser_processes:
                    try:
                        subprocess.run(['pkill', '-f', process], capture_output=True, timeout=10)
                    except:
                        continue

            else:
                browser_processes = [
                    'Firefox', 'Google Chrome', 'Safari', 'Opera', 'Brave Browser'
                ]

                for process in browser_processes:
                    try:
                        subprocess.run(['pkill', '-f', process], capture_output=True, timeout=10)
                    except:
                        continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Closed browser applications")
            time.sleep(2)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Browser close error: {e}")

    def get_youtube_video_duration(self, video_url):
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Getting video duration for: {video_url}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            if platform.system() == "Windows":
                try:
                    response = requests.get(video_url, headers=headers, timeout=20)
                    content = response.text
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Successfully fetched video page on Windows")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Windows requests failed: {e}, trying PowerShell...")
                    try:
                        ps_command = f'(Invoke-WebRequest -Uri "{video_url}" -UserAgent "Mozilla/5.0").Content'
                        result = subprocess.run(['powershell', '-Command', ps_command],
                                                capture_output=True, text=True, timeout=30)
                        content = result.stdout
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] PowerShell fetch successful")
                    except Exception as ps_error:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] PowerShell also failed: {ps_error}")
                        raise ps_error
            else:
                try:
                    response = requests.get(video_url, headers=headers, timeout=20)
                    content = response.text
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Successfully fetched video page on Linux/Mac")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Requests failed: {e}, trying curl...")
                    try:
                        result = subprocess.run(['curl', '-s', '-A', headers['User-Agent'], video_url],
                                                capture_output=True, text=True, timeout=30)
                        content = result.stdout
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Curl fetch successful")
                    except Exception as curl_error:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Curl also failed: {curl_error}")
                        raise curl_error

            duration_patterns = [
                (r'"approxDurationMs":"(\d+)"', 'milliseconds'),
                (r'"lengthSeconds":"(\d+)"', 'seconds'),
                (r'duration":"PT(\d+)M(\d+)S"', 'minutes_seconds'),
                (r'duration":"PT(\d+)S"', 'seconds_only'),
                (r'"duration":{"simpleText":"(\d+):(\d+)"', 'mm_ss'),
                (r'contentDetails.*duration.*PT(\d+)M(\d+)S', 'api_format')
            ]

            for pattern, format_type in duration_patterns:
                match = re.search(pattern, content)
                if match:
                    if format_type == 'milliseconds':
                        duration = int(match.group(1)) / 1000
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found duration (ms): {duration} seconds")
                        return int(duration)
                    elif format_type == 'seconds':
                        duration = int(match.group(1))
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found duration (seconds): {duration} seconds")
                        return duration
                    elif format_type == 'minutes_seconds':
                        minutes = int(match.group(1))
                        seconds = int(match.group(2))
                        duration = minutes * 60 + seconds
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found duration (PT format): {duration} seconds")
                        return duration
                    elif format_type == 'seconds_only':
                        duration = int(match.group(1))
                        print(
                            f"[{datetime.now().strftime('%H:%M:%S')}] Found duration (PT seconds): {duration} seconds")
                        return duration
                    elif format_type == 'mm_ss':
                        minutes = int(match.group(1))
                        seconds = int(match.group(2))
                        duration = minutes * 60 + seconds
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found duration (mm:ss): {duration} seconds")
                        return duration

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error getting video duration: {e}")

        fallback_duration = random.randint(240, 480)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Using fallback duration: {fallback_duration} seconds")
        return fallback_duration

    def watch_youtube(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting YouTube watching task")

        # Debug: Print entire config structure
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Config keys: {list(self.config.keys())}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Looking for 'youtube_videos' in config...")

        videos = self.config.get('youtube_videos', [])
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Found {len(videos)} YouTube videos")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Videos length > 0: {len(videos) > 0}")

        if len(videos) > 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Videos list: {videos}")
            video = random.choice(videos)
            try:
                duration = self.get_youtube_video_duration(video)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Opening YouTube video: {video}")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Video duration: {duration} seconds")

                self.open_in_firefox(video)

                initial_wait = random.randint(20, 30)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Waiting {initial_wait} seconds for Firefox and page to load...")
                time.sleep(initial_wait)

                try:
                    import pyautogui
                    pyautogui.FAILSAFE = True
                    pyautogui.PAUSE = 1.0

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting video playback and ad handling...")

                    pyautogui.press('space')
                    time.sleep(3)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pressed spacebar to start video")

                    ad_skip_attempts = 0
                    max_ad_attempts = 8

                    while ad_skip_attempts < max_ad_attempts:
                        print(
                            f"[{datetime.now().strftime('%H:%M:%S')}] Ad skip attempt {ad_skip_attempts + 1}/{max_ad_attempts}")

                        try:
                            screen_width, screen_height = pyautogui.size()

                            skip_positions = [
                                (screen_width - 100, 100),
                                (screen_width - 150, 120),
                                (screen_width - 80, 80),
                                (screen_width - 120, 100),
                                (screen_width - 200, 150)
                            ]

                            for x, y in skip_positions:
                                pyautogui.click(x, y)
                                time.sleep(1)

                            pyautogui.press('tab')
                            time.sleep(0.5)
                            pyautogui.press('enter')
                            time.sleep(2)

                            pyautogui.press('tab')
                            pyautogui.press('tab')
                            pyautogui.press('enter')
                            time.sleep(2)

                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempted to skip ad")

                        except Exception as e:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ad skip attempt failed: {e}")

                        time.sleep(8)
                        ad_skip_attempts += 1

                        if ad_skip_attempts >= 5:
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] Assuming ad period is over, starting main video")
                            pyautogui.press('space')
                            time.sleep(2)
                            break

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Video should be playing now")

                except ImportError:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] PyAutoGUI not available - install with: pip install pyautogui")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-play attempt failed: {e}")

                check_interval = self.config.get('video_completion_check_interval', 30)
                total_elapsed = 0
                watch_duration = min(duration, 600)

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Watching video for {watch_duration} seconds...")

                while total_elapsed < watch_duration and self.is_running:
                    wait_time = min(check_interval, watch_duration - total_elapsed)

                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Watching... {total_elapsed}/{watch_duration} seconds")

                    if wait_time > 30 and self.config.get('page_interaction', {}).get('scroll_enabled', False):
                        scroll_duration = random.randint(5, min(15, int(wait_time * 0.3)))
                        remaining_wait = wait_time - scroll_duration

                        if remaining_wait > 5:
                            time.sleep(random.randint(5, 10))
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scrolling for {scroll_duration} seconds...")
                            self.simulate_human_scrolling(scroll_duration)
                            time.sleep(remaining_wait)
                        else:
                            time.sleep(wait_time)
                    else:
                        time.sleep(wait_time)

                    total_elapsed += wait_time

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Finished watching video")

            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] YouTube watch error: {e}")
                fallback_time = random.randint(180, 600)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Using fallback watch time: {fallback_time} seconds")
                time.sleep(fallback_time)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No YouTube videos configured or empty list")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: len(videos) = {len(videos)}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: videos = {videos}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: type(videos) = {type(videos)}")
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Config file being used: {getattr(self, 'config_file', 'unknown')}")
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Please check your config.json file has 'youtube_videos' section with URLs")

            # Show a sample of what the config should look like
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Expected format:")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: \"youtube_videos\": [")
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG:     \"https://www.youtube.com/watch?v=dQw4w9WgXcQ\",")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG:     \"https://www.youtube.com/watch?v=3JZ_D3ELwOQ\"")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: ]")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed YouTube watching task")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def open_in_firefox(self, url):
        try:
            current_os = platform.system()

            if current_os == "Windows":
                firefox_paths = [
                    r"C:\Program Files\Mozilla Firefox\firefox.exe",
                    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                    os.path.join(os.environ.get('PROGRAMFILES', ''), 'Mozilla Firefox', 'firefox.exe'),
                    os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Mozilla Firefox', 'firefox.exe')
                ]

                firefox_path = None
                for path in firefox_paths:
                    if os.path.exists(path):
                        firefox_path = path
                        break

                if firefox_path:
                    subprocess.Popen([firefox_path, url])
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Opened in Firefox: {firefox_path}")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Firefox not found, using default browser")
                    webbrowser.open(url)

            elif current_os == "Linux":
                try:
                    subprocess.Popen(['firefox', url])
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Opened in Firefox (Linux)")
                except FileNotFoundError:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Firefox not found, using default browser")
                    webbrowser.open(url)

            else:
                try:
                    subprocess.Popen(['open', '-a', 'Firefox', url])
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Opened in Firefox (macOS)")
                except:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Firefox not found, using default browser")
                    webbrowser.open(url)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Firefox launch error: {e}, using default browser")
            webbrowser.open(url)

    def create_text_files(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting text file creation task")
        save_path = self.get_save_path("text_files")

        if not os.path.exists(save_path):
            os.makedirs(save_path)

        files_to_create = self.config.get('files_to_create_per_day', 5)
        for i in range(files_to_create):
            filename = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.txt"
            content = self.get_random_text_from_api()

            filepath = os.path.join(save_path, filename)

            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Created file: {filepath}")
                time.sleep(random.randint(10, 30))
            except:
                pass
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed text file creation task")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def generate_ip_range(self):
        if not self.config.get('ip_range', {}).get('enabled', False):
            return self.config.get('target_ips', [])

        try:
            import ipaddress

            start_ip = self.config['ip_range'].get('start_ip', '192.168.1.100')
            end_ip = self.config['ip_range'].get('end_ip', '192.168.1.200')
            exclude_ips = set(self.config['ip_range'].get('exclude_ips', []))

            start = ipaddress.IPv4Address(start_ip)
            end = ipaddress.IPv4Address(end_ip)

            ip_list = []
            current = start

            while current <= end:
                ip_str = str(current)
                if ip_str not in exclude_ips:
                    ip_list.append(ip_str)
                current += 1

            return ip_list

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error generating IP range: {e}")
            return self.config.get('target_ips', [])

    def send_file_to_ip_with_retry(self, ip, filepath, max_retries=3):
        for attempt in range(max_retries):
            try:
                if not self.ping_ip_to_check_availability(ip):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] IP {ip} not reachable, skipping")
                    return False

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                file_share_port = self.config.get('file_share_port', 8888)
                sock.connect((ip, file_share_port))

                filename = os.path.basename(filepath)
                filesize = os.path.getsize(filepath)

                header = f"{filename}|{filesize}"
                sock.send(header.encode())

                time.sleep(0.1)

                with open(filepath, 'rb') as f:
                    bytes_sent = 0
                    while bytes_sent < filesize:
                        data = f.read(4096)
                        if not data:
                            break
                        sock.send(data)
                        bytes_sent += len(data)

                sock.close()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Successfully sent {filename} to {ip}")
                return True

            except socket.timeout:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Timeout sending to {ip}, attempt {attempt + 1}/{max_retries}")
            except ConnectionRefusedError:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Connection refused by {ip}, attempt {attempt + 1}/{max_retries}")
            except OSError as e:
                if "Network is unreachable" in str(e) or "No route to host" in str(e):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Network unreachable to {ip}")
                    return False
                else:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Network error to {ip}: {e}, attempt {attempt + 1}/{max_retries}")
            except Exception as e:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Error sending to {ip}: {e}, attempt {attempt + 1}/{max_retries}")

            if attempt < max_retries - 1:
                time.sleep(random.randint(2, 5))

        return False

    def ping_target_ips(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting ping task")

        target_ips = self.generate_ip_range()
        ping_count = self.config.get('ping_count', 4)

        if self.config.get('ip_range', {}).get('enabled', False):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Pinging IP range with {len(target_ips)} addresses")
            target_ips = random.sample(target_ips, min(10, len(target_ips)))

        log_path = self.get_save_path("ping_logs")
        if not os.path.exists(log_path):
            os.makedirs(log_path)

        for ip in target_ips:
            try:
                if platform.system() == "Windows":
                    cmd = ['ping', '-n', str(ping_count), ip]
                else:
                    cmd = ['ping', '-c', str(ping_count), ip]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                log_file = os.path.join(log_path, f"ping_{ip}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                with open(log_file, 'w') as f:
                    f.write(f"Ping results for {ip}:\n")
                    f.write(f"Return code: {result.returncode}\n")
                    f.write("STDOUT:\n")
                    f.write(result.stdout)
                    if result.stderr:
                        f.write("\nSTDERR:\n")
                        f.write(result.stderr)

                status = "SUCCESS" if result.returncode == 0 else "FAILED"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ping {ip}: {status}")
                time.sleep(random.randint(5, 15))
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Error pinging {ip}: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed ping task")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def get_desktop_path(self):
        if platform.system() == "Windows":
            return os.path.join(os.path.expanduser("~"), "Desktop")
        else:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if os.path.exists(desktop):
                return desktop
            return os.path.expanduser("~")

    def get_documents_path(self):
        if platform.system() == "Windows":
            return os.path.join(os.path.expanduser("~"), "Documents")
        else:
            return os.path.join(os.path.expanduser("~"), "Documents")

    def generate_random_text(self):
        sentences = [
            "This is a sample document created automatically.",
            "The weather today is quite pleasant for outdoor activities.",
            "Technology continues to evolve at an unprecedented pace.",
            "Many people enjoy reading books in their spare time.",
            "Coffee shops have become popular places for remote work.",
            "Exercise is important for maintaining good health.",
            "Travel broadens one's perspective on different cultures.",
            "Music has the power to evoke strong emotions.",
            "Learning new skills is a lifelong journey.",
            "Nature provides a peaceful escape from city life."
        ]

        num_sentences = random.randint(3, 8)
        selected_sentences = random.sample(sentences, num_sentences)
        return "\n".join(selected_sentences)

    def download_media(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting media download task")
        media_urls = self.config.get('media_urls', [])
        download_path = self.get_save_path("downloads")

        if not os.path.exists(download_path):
            os.makedirs(download_path)

        for url in media_urls:
            try:
                response = requests.get(url, stream=True, timeout=60)
                if response.status_code == 200:
                    filename = os.path.basename(urlparse(url).path)
                    if not filename:
                        filename = f"media_{int(time.time())}"

                    filepath = os.path.join(download_path, filename)
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Downloaded: {filepath}")
                    time.sleep(random.randint(5, 15))
            except:
                pass
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed media download task")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def share_files_with_network(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting file sharing task")

        target_ips = self.generate_ip_range()

        if self.config.get('ip_range', {}).get('enabled', False):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Generated {len(target_ips)} IPs from range")
            available_ips = []

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking IP availability...")
            for ip in random.sample(target_ips, min(10, len(target_ips))):
                if self.ping_ip_to_check_availability(ip):
                    available_ips.append(ip)

            if available_ips:
                target_ips = available_ips
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(available_ips)} available IPs")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No IPs responding, using configured targets")
                target_ips = self.config.get('target_ips', [])

        text_files_path = self.get_save_path("text_files")
        desktop_path = self.get_desktop_path()

        search_paths = [text_files_path, desktop_path]

        try:
            all_files = []
            for search_path in search_paths:
                if os.path.exists(search_path):
                    files = [os.path.join(search_path, f) for f in os.listdir(search_path) if f.endswith('.txt')]
                    all_files.extend(files)

            if all_files:
                file_to_share = random.choice(all_files)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Sharing file: {os.path.basename(file_to_share)}")

                successful_transfers = 0
                max_attempts = min(5, len(target_ips))

                selected_ips = random.sample(target_ips, min(max_attempts, len(target_ips)))

                for ip in selected_ips:
                    success = self.send_file_to_ip_with_retry(ip, file_to_share)
                    if success:
                        successful_transfers += 1
                        if successful_transfers >= 2:
                            break
                    time.sleep(random.randint(1, 3))

                if successful_transfers == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] File sharing failed to all targets")

                    fallback_ips = [ip for ip in self.config.get('target_ips', []) if ip not in selected_ips]
                    if fallback_ips:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Trying fallback IPs...")
                        for fallback_ip in fallback_ips[:2]:
                            if self.send_file_to_ip_with_retry(fallback_ip, file_to_share):
                                successful_transfers += 1
                                break

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Successfully shared to {successful_transfers} targets")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No files available to share")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error in file sharing: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed file sharing task")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def start_file_receiver(self):
        def receiver():
            try:
                server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                file_share_port = self.config.get('file_share_port', 8888)
                server_sock.bind(('0.0.0.0', file_share_port))
                server_sock.listen(5)
                server_sock.settimeout(1)

                while self.is_running:
                    try:
                        client_sock, addr = server_sock.accept()
                        client_sock.settimeout(30)

                        header = client_sock.recv(1024).decode()
                        filename, filesize = header.split('|')
                        filesize = int(filesize)

                        received_path = self.get_save_path("received_files")
                        if not os.path.exists(received_path):
                            os.makedirs(received_path)

                        filepath = os.path.join(received_path, filename)

                        with open(filepath, 'wb') as f:
                            received = 0
                            while received < filesize:
                                data = client_sock.recv(min(4096, filesize - received))
                                if not data:
                                    break
                                f.write(data)
                                received += len(data)

                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Received file: {filename}")
                        client_sock.close()
                    except socket.timeout:
                        continue
                    except:
                        pass

                server_sock.close()
            except:
                pass

        thread = threading.Thread(target=receiver)
        thread.daemon = True
        return thread

    def ftp_operations(self):
        if not self.config.get('ftp_config', {}).get('enabled', False):
            return

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting FTP operations")

        try:
            import ftplib

            servers = self.config['ftp_config'].get('servers', [])
            operations = self.config['ftp_config'].get('operations', ['list'])
            files_per_session_range = self.config['ftp_config'].get('files_per_session', [1, 3])
            files_count = random.randint(*files_per_session_range)

            for _ in range(files_count):
                server = random.choice(servers)
                operation = random.choice(operations)

                try:
                    ftp = ftplib.FTP()
                    ftp.connect(server['host'], server['port'], timeout=30)
                    ftp.login(server['username'], server['password'])

                    if server.get('passive', True):
                        ftp.set_pasv(True)

                    if operation == "list":
                        files = ftp.nlst()
                        print(
                            f"[{datetime.now().strftime('%H:%M:%S')}] FTP LIST on {server['host']}: {len(files)} files")

                    elif operation == "upload":
                        text_files_path = self.get_save_path("text_files")
                        if os.path.exists(text_files_path):
                            local_files = [f for f in os.listdir(text_files_path) if f.endswith('.txt')]
                            if local_files:
                                local_file = random.choice(local_files)
                                local_path = os.path.join(text_files_path, local_file)
                                remote_name = f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{local_file}"

                                with open(local_path, 'rb') as f:
                                    ftp.storbinary(f'STOR {remote_name}', f)
                                print(
                                    f"[{datetime.now().strftime('%H:%M:%S')}] FTP UPLOAD to {server['host']}: {remote_name}")

                    elif operation == "download":
                        try:
                            files = ftp.nlst()
                            if files:
                                remote_file = random.choice(files)
                                download_path = self.get_save_path("downloads")
                                if not os.path.exists(download_path):
                                    os.makedirs(download_path)

                                local_path = os.path.join(download_path, f"ftp_{remote_file}")
                                with open(local_path, 'wb') as f:
                                    ftp.retrbinary(f'RETR {remote_file}', f.write)
                                print(
                                    f"[{datetime.now().strftime('%H:%M:%S')}] FTP DOWNLOAD from {server['host']}: {remote_file}")
                        except:
                            pass

                    ftp.quit()
                    time.sleep(random.randint(10, 30))

                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] FTP error with {server['host']}: {e}")

        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] FTP operations require ftplib (should be built-in)")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] FTP operations error: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed FTP operations")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def send_smtp_email(self):
        if not self.config.get('smtp_config', {}).get('enabled', False):
            return

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting SMTP email task")

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            smtp_config = self.config['smtp_config']
            provider = smtp_config.get('provider', 'gmail')

            if provider in smtp_config:
                server_config = smtp_config[provider]
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] SMTP provider '{provider}' not configured")
                return

            recipients = smtp_config.get('recipients', [])

            if not recipients:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No SMTP recipients configured")
                return

            recipient = random.choice(recipients)

            msg = MIMEMultipart()
            msg['From'] = server_config['username']
            msg['To'] = recipient
            msg['Subject'] = f"Automated Message - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            body_text = self.get_random_text_from_api()
            msg.attach(MIMEText(body_text, 'plain'))

            attachments_per_email_range = smtp_config.get('attachments_per_email', [1, 2])
            attachments_count = random.randint(*attachments_per_email_range)
            attachment_config = smtp_config.get('attachment_sources', {})

            attached_files = []

            if attachment_config.get('use_specific_files', False):
                specific_files = attachment_config.get('specific_files', [])
                available_specific = [f for f in specific_files if os.path.exists(f)]

                if available_specific:
                    selected_files = random.sample(available_specific, min(attachments_count, len(available_specific)))
                    for filepath in selected_files:
                        self.attach_file_to_email(msg, filepath)
                        attached_files.append(os.path.basename(filepath))

            if attachment_config.get('use_generated_files', True) and len(attached_files) < attachments_count:
                remaining_attachments = attachments_count - len(attached_files)
                text_files_path = self.get_save_path("text_files")

                if os.path.exists(text_files_path):
                    file_types = attachment_config.get('file_types', ['.txt'])
                    available_files = []

                    for file_type in file_types:
                        files = [f for f in os.listdir(text_files_path) if f.endswith(file_type)]
                        available_files.extend([os.path.join(text_files_path, f) for f in files])

                    downloads_path = self.get_save_path("downloads")
                    if os.path.exists(downloads_path):
                        for file_type in file_types:
                            files = [f for f in os.listdir(downloads_path) if f.endswith(file_type)]
                            available_files.extend([os.path.join(downloads_path, f) for f in files])

                    if available_files:
                        selected_files = random.sample(available_files,
                                                       min(remaining_attachments, len(available_files)))
                        for filepath in selected_files:
                            self.attach_file_to_email(msg, filepath)
                            attached_files.append(os.path.basename(filepath))

            server = smtplib.SMTP(server_config['server'], server_config['port'])
            server.set_debuglevel(0)

            if server_config.get('use_tls', True):
                server.starttls()

            try:
                server.login(server_config['username'], server_config['password'])
                server.send_message(msg)
                server.quit()

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] SMTP email sent via {provider} to {recipient} with {len(attached_files)} attachments: {', '.join(attached_files)}")

            except smtplib.SMTPAuthenticationError as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] SMTP Authentication failed for {provider}: {e}")
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Check your username/password and enable app passwords if needed")
            except smtplib.SMTPException as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] SMTP error for {provider}: {e}")

        except ImportError as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SMTP operations require email libraries: {e}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SMTP error: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed SMTP email task")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def attach_file_to_email(self, msg, filepath):
        try:
            import mimetypes
            from email.mime.base import MIMEBase
            from email.mime.text import MIMEText
            from email.mime.image import MIMEImage
            from email.mime.audio import MIMEAudio
            from email import encoders

            filename = os.path.basename(filepath)
            content_type, encoding = mimetypes.guess_type(filepath)

            if content_type is None or encoding is not None:
                content_type = 'application/octet-stream'

            main_type, sub_type = content_type.split('/', 1)

            with open(filepath, "rb") as fp:
                if main_type == 'text':
                    attachment = MIMEText(fp.read().decode('utf-8'), _subtype=sub_type)
                elif main_type == 'image':
                    attachment = MIMEImage(fp.read(), _subtype=sub_type)
                elif main_type == 'audio':
                    attachment = MIMEAudio(fp.read(), _subtype=sub_type)
                else:
                    attachment = MIMEBase(main_type, sub_type)
                    attachment.set_payload(fp.read())
                    encoders.encode_base64(attachment)

            attachment.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(attachment)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error attaching file {filepath}: {e}")

    def ssh_operations(self):
        if not self.config.get('ssh_config', {}).get('enabled', False):
            return

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting SSH operations")

        try:
            import paramiko

            servers = self.config['ssh_config'].get('servers', [])
            commands = self.config['ssh_config'].get('commands', ['whoami'])
            commands_per_session_range = self.config['ssh_config'].get('commands_per_session', [2, 5])
            commands_count = random.randint(*commands_per_session_range)

            for server_config in servers:
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                    if server_config.get('key_file'):
                        key = paramiko.RSAKey.from_private_key_file(server_config['key_file'])
                        ssh.connect(
                            server_config['host'],
                            port=server_config['port'],
                            username=server_config['username'],
                            pkey=key,
                            timeout=30
                        )
                    else:
                        ssh.connect(
                            server_config['host'],
                            port=server_config['port'],
                            username=server_config['username'],
                            password=server_config['password'],
                            timeout=30
                        )

                    selected_commands = random.sample(commands, min(commands_count, len(commands)))

                    for command in selected_commands:
                        try:
                            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
                            output = stdout.read().decode('utf-8')
                            error = stderr.read().decode('utf-8')

                            log_path = self.get_save_path("ping_logs")
                            if not os.path.exists(log_path):
                                os.makedirs(log_path)

                            log_file = os.path.join(log_path,
                                                    f"ssh_{server_config['host']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                            with open(log_file, 'w') as f:
                                f.write(f"SSH Command: {command}\n")
                                f.write(f"Host: {server_config['host']}\n")
                                f.write(f"User: {server_config['username']}\n")
                                f.write(f"Timestamp: {datetime.now()}\n\n")
                                f.write("STDOUT:\n")
                                f.write(output)
                                if error:
                                    f.write("\nSTDERR:\n")
                                    f.write(error)

                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] SSH command '{command}' executed on {server_config['host']}")
                            time.sleep(random.randint(5, 15))

                        except Exception as e:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] SSH command error: {e}")

                    ssh.close()

                except Exception as e:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] SSH connection error to {server_config['host']}: {e}")

        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SSH operations require paramiko: pip install paramiko")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SSH operations error: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed SSH operations")
        if not self.config.get('scheduled_tasks', {}).get('enabled', False):
            self.wait_between_tasks()

    def execute_task_by_name(self, task_name, single_run=False):
        task_methods = {
            'browse_websites': self.browse_websites,
            'browse_filesystem': self.browse_filesystem,
            'orchestrate_modules': self.run_orchestrated_modules,
            'watch_youtube': self.watch_youtube,
            'create_text_files': self.create_text_files,
            'download_media': self.download_media,
            'share_files_with_network': self.share_files_with_network,
            'ping_target_ips': self.ping_target_ips,
            'ftp_operations': self.ftp_operations,
            'send_smtp_email': self.send_smtp_email,
            'ssh_operations': self.ssh_operations,
            'run_random_applications': self.run_random_applications,
            'imap_operations': self.imap_operations
        }

        if task_name in task_methods:
            try:
                if single_run and task_name == 'browse_filesystem':
                    task_methods[task_name](skip_post_wait=True)
                else:
                    task_methods[task_name]()
                return True
            except:
                return False

        return False

    def scheduled_behavior_cycle(self):
        print("Running in scheduled mode")
        while self.is_running:
            self.wait_for_active_hours()

            if not self.is_running:
                break

            next_task_info = self.get_next_scheduled_task()

            if next_task_info:
                wait_seconds, task_config = next_task_info

                if wait_seconds > 0:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Next task '{task_config['task']}' scheduled for {task_config['time']}, waiting {int(wait_seconds / 60)} minutes")

                    while wait_seconds > 0 and self.is_running:
                        sleep_time = min(60, wait_seconds)
                        time.sleep(sleep_time)
                        wait_seconds -= sleep_time

                        if not self.is_within_active_hours():
                            break

                if self.is_running and self.is_within_active_hours():
                    if self.should_run_scheduled_task(task_config):
                        print(
                            f"[{datetime.now().strftime('%H:%M:%S')}] Executing scheduled task: {task_config['task']}")
                        self.execute_task_by_name(task_config['task'])

            time.sleep(30)

    def random_behavior_cycle(self):
        print("Running in random mode")
        if self.get_orchestration_config()['enabled']:
            self.run_orchestrated_modules()
            return

        while self.is_running:
            daily_sessions = self.config.get('daily_sessions', 3)
            for session in range(daily_sessions):
                if not self.is_running:
                    break

                self.wait_for_active_hours()

                if not self.is_running:
                    break

                session_duration_range = self.config.get('session_duration_minutes', [30, 90])
                session_duration = random.randint(*session_duration_range)
                session_speed_multiplier = self.get_session_speed_multiplier()
                session_end_time = datetime.now() + timedelta(minutes=session_duration / session_speed_multiplier)

                activities = [
                    self.browse_websites,
                    self.browse_filesystem,
                    self.watch_youtube,
                    self.create_text_files,
                    self.download_media,
                    self.share_files_with_network,
                    self.ping_target_ips
                ]

                preferred_tasks = self.config.get('preferred_tasks', [])
                if preferred_tasks:
                    task_map = {
                        'browse_websites': self.browse_websites,
                        'browse_filesystem': self.browse_filesystem,
                        'watch_youtube': self.watch_youtube,
                        'create_text_files': self.create_text_files,
                        'download_media': self.download_media,
                        'share_files_with_network': self.share_files_with_network,
                        'ping_target_ips': self.ping_target_ips,
                        'ftp_operations': self.ftp_operations,
                        'send_smtp_email': self.send_smtp_email,
                        'ssh_operations': self.ssh_operations,
                        'run_random_applications': self.run_random_applications,
                        'imap_operations': self.imap_operations
                    }

                    filtered_activities = []
                    for task_name in preferred_tasks:
                        if task_name in task_map:
                            filtered_activities.append(task_map[task_name])

                    if filtered_activities:
                        activities = filtered_activities

                if self.config.get('ftp_config', {}).get('enabled', False):
                    activities.append(self.ftp_operations)
                if self.config.get('smtp_config', {}).get('enabled', False):
                    activities.append(self.send_smtp_email)
                if self.config.get('ssh_config', {}).get('enabled', False):
                    activities.append(self.ssh_operations)
                if self.config.get('app_execution', {}).get('enabled', False):
                    activities.append(self.run_random_applications)
                if self.config.get('imap_config', {}).get('enabled', False):
                    activities.append(self.imap_operations)

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Starting session {session + 1}/{daily_sessions} for {session_duration} minutes at {session_speed_multiplier}x speed")

                while datetime.now() < session_end_time and self.is_running and self.is_within_active_hours():
                    activity = random.choice(activities)
                    try:
                        activity()
                    except:
                        pass

                if self.is_running and session < daily_sessions - 1:
                    session_break = random.randint(1800, 7200)
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Session break for {int(session_break / 60)} minutes")
                    time.sleep(session_break)

            if self.is_running:
                next_day_sleep = random.randint(18000, 28800)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Daily cycle complete, sleeping for {int(next_day_sleep / 3600)} hours")
                time.sleep(next_day_sleep)

    def start(self):
        self.is_running = True
        self.detect_runtime_os()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Detected operating system: {self.current_os}")
        self.start_stop_hotkey_listener()
        self.configure_session_speed()

        receiver_thread = self.start_file_receiver()
        self.threads.append(receiver_thread)
        receiver_thread.start()

        if self.config.get('scheduled_tasks', {}).get('enabled', False):
            behavior_thread = threading.Thread(target=self.scheduled_behavior_cycle)
        else:
            behavior_thread = threading.Thread(target=self.random_behavior_cycle)

        behavior_thread.daemon = True
        self.threads.append(behavior_thread)
        behavior_thread.start()

        print(f"User behavior simulation started at {datetime.now().strftime('%H:%M:%S')}. Press Ctrl+C to stop.")

        if self.config.get('active_hours', {}).get('enabled', False):
            start_hour = self.config['active_hours'].get('start_hour', 9)
            end_hour = self.config['active_hours'].get('end_hour', 17)
            print(f"Active hours: {start_hour:02d}:00 - {end_hour:02d}:00")

        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self, reason=None):
        self.request_stop(reason)

        if self.hotkey_listener is not None:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass

        current_thread = threading.current_thread()
        for thread in self.threads:
            if thread is current_thread:
                continue
            if thread.is_alive():
                thread.join(timeout=1)