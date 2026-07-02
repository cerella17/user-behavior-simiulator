from __future__ import annotations

import dataclasses
import logging
import os
import platform
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import psutil
except ImportError:  # pragma: no cover - handled at runtime with a clear error.
    psutil = None

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - handled at runtime with a clear warning.
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None


@dataclass(frozen=True)
class ModuleRoute:
    module_name: str
    process_keywords: Tuple[str, ...] = ()
    path_keywords: Tuple[str, ...] = ()
    path_prefixes: Tuple[str, ...] = ()
    priority: int = 0


@dataclass(frozen=True)
class DetectedEvent:
    module_name: str
    source: str
    reason: str
    path: str = ""
    process_name: str = ""
    pid: int = 0
    timestamp: float = field(default_factory=time.monotonic)


class SandboxFileEventHandler(FileSystemEventHandler):
    def __init__(self, orchestrator: "SandboxOrchestrator"):
        self.orchestrator = orchestrator

    def on_any_event(self, event):  # pragma: no cover - exercised in real runtime.
        if getattr(event, "is_directory", False):
            return

        path = getattr(event, "src_path", "") or getattr(event, "dest_path", "") or ""
        if path:
            self.orchestrator.handle_filesystem_signal(path, source=f"watchdog:{getattr(event, 'event_type', 'event')}")


class SandboxOrchestrator:
    def __init__(self, simulator):
        self.simulator = simulator
        self.config = simulator.config.get("sandbox_orchestrator", {}) or {}
        self.logger = self._build_logger()
        self.running = False
        self.event_queue: "queue.Queue[DetectedEvent]" = queue.Queue()
        self.pending_events: List[DetectedEvent] = []
        self.route_definitions = self._load_routes()
        self.monitored_paths = self._resolve_monitored_paths()
        self.process_state: Dict[int, str] = {}
        self.recent_signatures: Dict[str, float] = {}
        self.active_module: Optional[str] = None
        self.active_lock = threading.Lock()
        self.observer = None
        self.threads: List[threading.Thread] = []
        self._last_relevant_event_at = time.monotonic()
        self._fallback_dispatched_at = 0.0

    def _build_logger(self) -> logging.Logger:
        logger = logging.getLogger("user_behavior_simulator.sandbox")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger

    def _load_routes(self) -> List[ModuleRoute]:
        configured_routes = self.config.get("rules", [])
        routes: List[ModuleRoute] = []

        if isinstance(configured_routes, list):
            for item in configured_routes:
                if not isinstance(item, dict):
                    continue
                module_name = str(item.get("module", "")).strip()
                if not module_name:
                    continue
                routes.append(
                    ModuleRoute(
                        module_name=module_name,
                        process_keywords=self._normalize_keywords(item.get("process_keywords", [])),
                        path_keywords=self._normalize_keywords(item.get("path_keywords", [])),
                        path_prefixes=tuple(self._expand_paths(item.get("path_prefixes", []))),
                        priority=int(item.get("priority", 0) or 0),
                    )
                )

        if routes:
            return sorted(routes, key=lambda route: route.priority, reverse=True)

        return [
            ModuleRoute(
                module_name="browse_websites",
                process_keywords=("firefox", "chrome", "chromium", "brave", "edge", "opera", "vivaldi", "safari", "browser"),
                path_keywords=("firefox", "chrome", "chromium", "browser", "mozilla", "safari", "brave"),
                path_prefixes=(
                    os.path.expanduser("~/Library/Application Support/Firefox"),
                    os.path.expanduser("~/Library/Application Support/Google/Chrome"),
                    os.path.expanduser("~/Library/Application Support/BraveSoftware"),
                    os.path.expanduser("~/.mozilla"),
                    os.path.expanduser("~/.config/google-chrome"),
                    os.path.expanduser("~/.config/chromium"),
                ),
                priority=100,
            ),
            ModuleRoute(
                module_name="browse_filesystem",
                process_keywords=("finder", "nautilus", "dolphin", "thunar", "pcmanfm", "file manager", "files"),
                path_keywords=("desktop", "documents", "downloads", "home", "library", "folder"),
                path_prefixes=(
                    os.path.expanduser("~/Desktop"),
                    os.path.expanduser("~/Documents"),
                    os.path.expanduser("~/Downloads"),
                    os.path.expanduser("~"),
                ),
                priority=10,
            ),
        ]

    def _normalize_keywords(self, values: Iterable[str]) -> Tuple[str, ...]:
        if not isinstance(values, (list, tuple)):
            return ()
        normalized = []
        for value in values:
            text = str(value).strip().lower()
            if text:
                normalized.append(text)
        return tuple(dict.fromkeys(normalized))

    def _expand_paths(self, values: Iterable[str]) -> List[str]:
        if not isinstance(values, (list, tuple)):
            return []
        expanded: List[str] = []
        for value in values:
            path = os.path.expanduser(str(value).strip())
            if path:
                expanded.append(path)
        return expanded

    def _resolve_monitored_paths(self) -> List[str]:
        configured_paths = self.config.get("monitored_paths", [])
        candidate_paths = self._expand_paths(configured_paths)

        if not candidate_paths:
            candidate_paths = [
                os.path.expanduser("~/Desktop"),
                os.path.expanduser("~/Documents"),
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~"),
            ]

        unique_paths: List[str] = []
        for candidate in candidate_paths:
            if os.path.exists(candidate) and candidate not in unique_paths:
                unique_paths.append(candidate)
        return unique_paths

    def _parse_seconds_range(self, value, default_low: float, default_high: float) -> Tuple[float, float]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            low = float(value[0])
            high = float(value[1])
            if low > high:
                low, high = high, low
            return max(0.0, low), max(0.0, high)
        return float(default_low), float(default_high)

    def _build_module_dispatch(self):
        def dispatch_with_budget(module_name: str):
            duration_minutes = self._pick_module_duration_minutes()
            return self.simulator.run_module_for_duration(module_name, duration_minutes)

        return {
            "browse_websites": lambda: dispatch_with_budget("browse_websites"),
            "browse_filesystem": lambda: dispatch_with_budget("browse_filesystem"),
        }

    def _module_duration_range(self) -> Tuple[int, int]:
        sandbox_range = self.config.get("module_duration_minutes")
        task_orchestration_range = (
            self.simulator.config.get("task_orchestration", {}) or {}
        ).get("module_duration_minutes", [1, 3])
        configured = sandbox_range if sandbox_range is not None else task_orchestration_range

        if isinstance(configured, (list, tuple)) and len(configured) == 2:
            try:
                min_minutes = max(1, int(configured[0]))
                max_minutes = max(min_minutes, int(configured[1]))
                return min_minutes, max_minutes
            except Exception:
                pass

        return 1, 3

    def _pick_module_duration_minutes(self) -> int:
        min_minutes, max_minutes = self._module_duration_range()
        return random.randint(min_minutes, max_minutes)

    def start(self):
        if psutil is None:
            raise RuntimeError("Sandbox orchestrator requires psutil. Install it with: pip install psutil")

        self.running = True
        self.simulator.is_running = True
        self.simulator.detect_runtime_os()
        self.simulator.configure_session_speed()
        self.simulator.start_stop_hotkey_listener()

        self.logger.info("Sandbox orchestrator started")
        self.logger.info("Monitored paths: %s", ", ".join(self.monitored_paths))
        self._start_filesystem_monitor()

        process_thread = threading.Thread(target=self._process_monitor_loop, daemon=True)
        process_thread.start()
        self.threads.append(process_thread)

        try:
            self._main_loop()
        finally:
            self.stop()

    def stop(self):
        self.running = False
        self.simulator.is_running = False
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=5)
            except Exception:
                pass
            self.observer = None

        self.logger.info("Sandbox orchestrator stopped")

    def _start_filesystem_monitor(self):
        if Observer is None:
            self.logger.info("watchdog not available, filesystem events will rely on process scans only")
            return

        try:
            observer = Observer()
            handler = SandboxFileEventHandler(self)
            for path in self.monitored_paths:
                try:
                    observer.schedule(handler, path, recursive=True)
                except Exception as exc:
                    self.logger.info("Skipping filesystem watch for %s: %s", path, exc)

            observer.start()
            self.observer = observer
            self.logger.info("Filesystem watcher active")
        except Exception as exc:
            self.logger.info("Filesystem watcher unavailable: %s", exc)

    def _process_monitor_loop(self):
        poll_interval = self._process_poll_interval()
        while self.running:
            try:
                self._scan_processes()
            except Exception as exc:
                self.logger.info("Process monitor error: %s", exc)

            self._sleep_with_stop(poll_interval)

    def _process_poll_interval(self) -> float:
        interval = self.config.get("process_poll_interval_seconds", 4)
        try:
            return max(1.0, float(interval))
        except Exception:
            return 4.0

    def _fallback_timeout(self) -> float:
        timeout = self.config.get("idle_timeout_seconds", 120)
        try:
            return max(1.0, float(timeout))
        except Exception:
            return 120.0

    def _delay_range(self) -> Tuple[float, float]:
        return self._parse_seconds_range(self.config.get("trigger_delay_seconds", [5, 25]), 5, 25)

    def _cooldown_range(self) -> Tuple[float, float]:
        return self._parse_seconds_range(self.config.get("module_cooldown_seconds", [20, 60]), 20, 60)

    def _dedupe_seconds(self) -> float:
        try:
            return max(1.0, float(self.config.get("dedupe_seconds", 15)))
        except Exception:
            return 15.0

    def _sleep_with_stop(self, seconds: float):
        end_time = time.monotonic() + max(0.0, seconds)
        while self.running and time.monotonic() < end_time:
            time.sleep(min(0.5, end_time - time.monotonic()))

    def _main_loop(self):
        while self.running:
            try:
                event = self.event_queue.get(timeout=1.0)
            except queue.Empty:
                event = None

            if event is not None:
                self.pending_events.append(event)

            if self.active_module is None and self.pending_events:
                next_event = self.pending_events.pop(0)
                self._dispatch_event(next_event)
                continue

            if self.active_module is None and self._is_idle_timeout_reached():
                fallback_event = self._build_fallback_event()
                if fallback_event is not None:
                    self._dispatch_event(fallback_event)

    def _is_idle_timeout_reached(self) -> bool:
        return (time.monotonic() - self._last_relevant_event_at) >= self._fallback_timeout()

    def _build_fallback_event(self) -> Optional[DetectedEvent]:
        if time.monotonic() - self._fallback_dispatched_at < self._fallback_timeout():
            return None

        fallback_mode = str(self.config.get("fallback_module", "random") or "random").strip().lower()
        if fallback_mode == "browse_websites":
            module_name = "browse_websites"
        elif fallback_mode == "browse_filesystem":
            module_name = "browse_filesystem"
        else:
            module_name = random.choice(["browse_websites", "browse_filesystem"])

        self._fallback_dispatched_at = time.monotonic()
        return DetectedEvent(
            module_name=module_name,
            source="fallback",
            reason=f"no relevant activity detected for {int(self._fallback_timeout())}s",
        )

    def _dispatch_event(self, event: DetectedEvent):
        dispatch = self._build_module_dispatch().get(event.module_name)
        if dispatch is None:
            self.logger.info("Ignoring unsupported module '%s' from %s", event.module_name, event.source)
            return

        if self.active_module == event.module_name:
            return

        with self.active_lock:
            self.active_module = event.module_name

        try:
            self._log_event(event)
            delay_low, delay_high = self._delay_range()
            delay = random.uniform(delay_low, delay_high)
            self.logger.info("Waiting %.1fs before starting %s", delay, event.module_name)
            self._sleep_with_stop(delay)

            if not self.running:
                return

            self.logger.info("Starting module %s", event.module_name)
            dispatch()
            cooldown_low, cooldown_high = self._cooldown_range()
            cooldown = random.uniform(cooldown_low, cooldown_high)
            self.logger.info("Cooling down for %.1fs after %s", cooldown, event.module_name)
            self._sleep_with_stop(cooldown)
        finally:
            self._last_relevant_event_at = time.monotonic()
            with self.active_lock:
                self.active_module = None

    def _log_event(self, event: DetectedEvent):
        details = [f"source={event.source}", f"module={event.module_name}"]
        if event.process_name:
            details.append(f"process={event.process_name}")
        if event.pid:
            details.append(f"pid={event.pid}")
        if event.path:
            details.append(f"path={event.path}")
        details.append(f"reason={event.reason}")
        self.logger.info("Detected event: %s", " | ".join(details))

    def handle_filesystem_signal(self, path: str, source: str = "filesystem"):
        module_name, reason = self._classify_path(path)
        if module_name is None:
            return

        self._queue_event(
            DetectedEvent(
                module_name=module_name,
                source=source,
                reason=reason,
                path=path,
            )
        )

    def _scan_processes(self):
        matched_groups: Dict[str, List[Tuple[int, str, str]]] = {}

        for proc in psutil.process_iter(attrs=["pid", "name", "exe", "cmdline", "cwd"]):
            try:
                pid = proc.info.get("pid") or proc.pid
                if pid == os.getpid():
                    continue

                module_name, reason, path = self._classify_process(proc)
                if module_name is None:
                    continue

                process_name = str(proc.info.get("name") or proc.name() or "")
                matched_groups.setdefault(module_name, []).append((pid, process_name, path))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as exc:
                self.logger.info("Process classification error: %s", exc)

        for module_name, matches in matched_groups.items():
            if not matches:
                continue

            match_signature = ",".join(sorted(f"{pid}:{process_name}:{path}" for pid, process_name, path in matches))
            signature = f"proc-group:{module_name}:{match_signature}"
            if self._is_recent_signature(signature):
                continue

            self.recent_signatures[signature] = time.monotonic()
            process_names = sorted({process_name for _, process_name, _ in matches if process_name})
            pids = sorted({pid for pid, _, _ in matches})
            paths = sorted({path for _, _, path in matches if path})
            summary_process = ", ".join(process_names) if process_names else "multiple processes"
            summary_path = ", ".join(paths[:3])
            reason = f"matched {len(matches)} process(es): {summary_process}"
            if summary_path:
                reason = f"{reason} | paths: {summary_path}"

            self._queue_event(
                DetectedEvent(
                    module_name=module_name,
                    source="process-scan",
                    reason=reason,
                    path=summary_path,
                    process_name=summary_process,
                    pid=pids[0] if pids else 0,
                )
            )

    def _classify_process(self, proc) -> Tuple[Optional[str], str, str]:
        try:
            info = proc.info if hasattr(proc, "info") else {}
            metadata_parts = [
                str(info.get("name") or ""),
                str(info.get("exe") or ""),
                " ".join(info.get("cmdline") or []),
                str(info.get("cwd") or ""),
            ]
            metadata = " ".join(part for part in metadata_parts if part).lower()

            module_name = self._match_route_by_text(metadata)
            if module_name == "browse_websites":
                return module_name, "browser process metadata matched", str(info.get("exe") or info.get("name") or "")

            if module_name == "browse_filesystem":
                return module_name, "filesystem process metadata matched", str(info.get("cwd") or info.get("exe") or info.get("name") or "")

            open_files = []
            try:
                open_files = proc.open_files()
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                open_files = []

            for file_info in open_files:
                path = str(getattr(file_info, "path", "") or "")
                module_name, reason = self._classify_path(path)
                if module_name is not None:
                    return module_name, reason, path

            cwd = str(info.get("cwd") or "")
            module_name, reason = self._classify_path(cwd)
            if module_name is not None:
                return module_name, reason, cwd

            return None, "", ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None, "", ""

    def _match_route_by_text(self, text: str) -> Optional[str]:
        best_route: Optional[ModuleRoute] = None
        for route in self.route_definitions:
            if route.module_name == "browse_websites" and self._text_contains_any(text, route.process_keywords):
                best_route = route
                break

            if route.module_name == "browse_filesystem" and self._text_contains_any(text, route.process_keywords):
                best_route = route

        return best_route.module_name if best_route else None

    def _classify_path(self, path: str) -> Tuple[Optional[str], str]:
        normalized = os.path.expanduser(path or "")
        if not normalized:
            return None, ""

        lowered = normalized.lower()
        browser_keywords = (
            "firefox",
            "chrome",
            "chromium",
            "brave",
            "edge",
            "opera",
            "vivaldi",
            "browser",
            "mozilla",
        )
        filesystem_keywords = (
            "desktop",
            "documents",
            "downloads",
            "home",
            "finder",
            "nautilus",
            "dolphin",
            "thunar",
            "pcmanfm",
        )

        if self._text_contains_any(lowered, browser_keywords):
            return "browse_websites", f"browser path matched: {normalized}"

        if self._path_is_monitored(normalized) or self._text_contains_any(lowered, filesystem_keywords):
            return "browse_filesystem", f"filesystem path matched: {normalized}"

        return None, ""

    def _path_is_monitored(self, path: str) -> bool:
        expanded = os.path.expanduser(path)
        home_root = os.path.expanduser("~")
        for monitored in self.monitored_paths:
            if monitored == home_root:
                continue
            if expanded == monitored or expanded.startswith(monitored.rstrip(os.sep) + os.sep):
                return True
        return False

    def _text_contains_any(self, text: str, keywords: Sequence[str]) -> bool:
        return any(keyword and keyword in text for keyword in keywords)

    def _queue_event(self, event: DetectedEvent):
        signature = self._event_signature(event)
        now = time.monotonic()
        expiry = self.recent_signatures.get(signature)
        if expiry is not None and (now - expiry) < self._dedupe_seconds():
            return

        self.recent_signatures[signature] = now
        self._cleanup_recent_signatures(now)
        self._last_relevant_event_at = now
        self.event_queue.put(event)

    def _event_signature(self, event: DetectedEvent) -> str:
        return "|".join([
            event.module_name,
            event.source,
            event.path,
            event.process_name,
            str(event.pid),
            event.reason,
        ])

    def _cleanup_recent_signatures(self, now: float):
        dedupe_window = self._dedupe_seconds()
        stale_keys = [signature for signature, created_at in self.recent_signatures.items() if (now - created_at) > dedupe_window]
        for signature in stale_keys:
            self.recent_signatures.pop(signature, None)

    def _is_recent_signature(self, signature: str) -> bool:
        created_at = self.recent_signatures.get(signature)
        return created_at is not None and (time.monotonic() - created_at) <= self._dedupe_seconds()
