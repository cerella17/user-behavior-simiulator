import os
import random
import subprocess
import time
from datetime import datetime


class FilesystemExplorer:
    def __init__(self, simulator):
        self.simulator = simulator
        self.config = simulator.config.get('filesystem_exploration', {}) or {}

    def explore(self, run_until=None):
        if not self.config.get('enabled', False):
            return

        roots = self.get_root_paths()
        if not roots:
            return

        rounds_range = self.config.get('explore_rounds_per_session', [2, 5])
        if isinstance(rounds_range, (list, tuple)) and len(rounds_range) == 2:
            rounds = random.randint(int(rounds_range[0]), int(rounds_range[1]))
        else:
            rounds = random.randint(2, 5)

        current_path = random.choice(roots)
        self.open_path(current_path)
        self.simulator.sleep_with_mouse_activity(random.randint(2, 5))
        self.close_opened_path_view()

        for _ in range(rounds):
            if not self.simulator.is_running:
                break

            if run_until is not None and time.time() >= run_until:
                break

            next_path = self.choose_next_path(current_path, roots)
            if not next_path:
                current_path = random.choice(roots)
                self.open_path(current_path)
                self.simulator.sleep_with_mouse_activity(random.randint(2, 4))
                continue

            current_path = next_path
            self.open_path(current_path)
            self.simulator.sleep_with_mouse_activity(random.randint(2, 6))
            self.maybe_scroll_file_manager()
            self.maybe_preview_file(current_path)
            self.close_opened_path_view()

            if run_until is not None and time.time() >= run_until:
                break

            if random.random() < float(self.config.get('go_up_probability', 0.25) or 0.25):
                parent_path = os.path.dirname(current_path.rstrip(os.sep))
                if parent_path and parent_path != current_path and os.path.exists(parent_path):
                    current_path = parent_path
                    self.open_path(current_path)
                    self.simulator.sleep_with_mouse_activity(random.randint(1, 3))
                    self.close_opened_path_view()

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Completed filesystem exploration task")

    def get_root_paths(self):
        configured_paths = self.config.get('root_paths', [])
        candidate_paths = []

        if isinstance(configured_paths, list):
            candidate_paths.extend(str(path) for path in configured_paths if path)

        candidate_paths.extend([
            self.simulator.get_desktop_path(),
            self.simulator.get_documents_path(),
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~')
        ])

        unique_paths = []
        for path in candidate_paths:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded) and expanded not in unique_paths:
                unique_paths.append(expanded)

        return unique_paths

    def choose_next_path(self, current_path, roots):
        candidates = []
        folder_probability = float(self.config.get('folder_open_probability', 0.75) or 0.75)
        file_probability = float(self.config.get('file_open_probability', 0.25) or 0.25)
        folder_probability = max(0.0, min(1.0, folder_probability))
        file_probability = max(0.0, min(1.0, file_probability))

        if os.path.isdir(current_path):
            try:
                entries = sorted(os.listdir(current_path))
            except Exception:
                entries = []

            folders = []
            files = []
            for entry in entries:
                if entry.startswith('.'):
                    continue

                full_path = os.path.join(current_path, entry)
                if os.path.isdir(full_path):
                    folders.append(full_path)
                elif os.path.isfile(full_path):
                    files.append(full_path)

            candidates.extend(folders[:10])

            previewable_extensions = {
                '.txt', '.md', '.csv', '.log', '.json', '.xml', '.py', '.html', '.htm',
                '.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf'
            }
            previewable_files = [
                path for path in files
                if os.path.splitext(path)[1].lower() in previewable_extensions
            ]
            candidates.extend(previewable_files[:8])

            parent_path = os.path.dirname(current_path.rstrip(os.sep))
            if parent_path and parent_path != current_path and os.path.exists(parent_path):
                candidates.append(parent_path)

        if not candidates:
            candidates = list(roots)

        folder_candidates = [path for path in candidates if os.path.isdir(path)]
        file_candidates = [path for path in candidates if os.path.isfile(path)]

        choice_pool = []
        if folder_candidates:
            choice_pool.extend(folder_candidates * max(1, int(folder_probability * 10)))
        if file_candidates:
            choice_pool.extend(file_candidates * max(1, int(file_probability * 10)))

        if not choice_pool:
            return random.choice(candidates) if candidates else None

        return random.choice(choice_pool)

    def open_path(self, path):
        try:
            runtime_os = self.simulator.detect_runtime_os()

            if runtime_os == 'Windows':
                subprocess.run(['explorer', path], capture_output=True, text=True, timeout=10)
            elif runtime_os == 'Darwin':
                subprocess.run(['open', path], capture_output=True, text=True, timeout=10)
            else:
                opener_candidates = [
                    ['xdg-open', path],
                    ['nautilus', path],
                    ['dolphin', path],
                    ['thunar', path],
                    ['pcmanfm', path]
                ]

                for command in opener_candidates:
                    try:
                        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            break
                    except Exception:
                        continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Exploring filesystem path: {path}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Filesystem open error for {path}: {e}")

    def maybe_scroll_file_manager(self):
        if random.random() > float(self.config.get('scroll_probability', 0.7) or 0.7):
            return

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            scroll_amount = random.randint(-350, 350)
            if scroll_amount == 0:
                scroll_amount = 160
            pyautogui.scroll(scroll_amount)
            self.simulator.sleep_with_mouse_activity(random.uniform(0.5, 1.5))
        except Exception:
            return

    def maybe_preview_file(self, path):
        if not os.path.isfile(path):
            return

        preview_probability = float(self.config.get('preview_file_probability', 0.4) or 0.4)
        preview_probability = max(0.0, min(1.0, preview_probability))
        if random.random() > preview_probability:
            return

        try:
            self.simulator.sleep_with_mouse_activity(random.uniform(0.6, 1.6))
        except Exception:
            return

    def close_opened_path_view(self):
        close_probability = float(self.config.get('close_opened_path_probability', 1.0) or 1.0)
        close_probability = max(0.0, min(1.0, close_probability))

        if random.random() > close_probability:
            return

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            self.simulator.sleep_with_mouse_activity(random.uniform(0.4, 1.2))

            runtime_os = self.simulator.detect_runtime_os()
            if runtime_os == 'Windows':
                pyautogui.hotkey('ctrl', 'w')
            elif runtime_os == 'Darwin':
                pyautogui.hotkey('command', 'w')
            else:
                pyautogui.hotkey('ctrl', 'w')

            self.simulator.sleep_with_mouse_activity(random.uniform(0.3, 0.9))
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Closed filesystem view")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Filesystem close error: {e}")