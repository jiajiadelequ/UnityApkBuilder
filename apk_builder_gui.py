import json
import queue
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


DEFAULT_PROJECT = r"F:\UnityProjects\AR_VIWER"
DEFAULT_UNITY = r"D:\unity\2022.3.62f2c1\Editor\Unity.exe"
DEFAULT_ADB = r"E:\AndroidBuild\android-sdk\platform-tools\adb.exe"
DEFAULT_OUTPUT = r"F:\UnityProjects\AR_VIWER\Builds\Android"
SCRIPT_PATH = Path(__file__).resolve().with_name("build-and-install-android.ps1")
TOOL_DIR = Path(__file__).resolve().parent
STATE_PATH = TOOL_DIR / "app_state.json"
LAST_SESSION_PATH = TOOL_DIR / "last_session.json"
CONFIGS_DIR = TOOL_DIR / "configs"
MAX_RECENT_CONFIGS = 10


class ApkBuilderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Unity APK Builder")
        self.root.geometry("920x760")

        self.log_queue: queue.Queue[object] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.build_running = False
        self.state = self._load_state()

        self.project_var = tk.StringVar(value=DEFAULT_PROJECT)
        self.unity_var = tk.StringVar(value=DEFAULT_UNITY)
        self.adb_var = tk.StringVar(value=DEFAULT_ADB)
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)
        self.apk_name_var = tk.StringVar(value="MR_System.apk")
        self.keystore_var = tk.StringVar()
        self.keystore_pass_var = tk.StringVar()
        self.alias_var = tk.StringVar(value="zcwl")
        self.alias_pass_var = tk.StringVar()
        self.skip_install_var = tk.BooleanVar(value=False)
        self.cleanup_script_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.recent_menu: tk.Menu | None = None
        self.start_button: ttk.Button | None = None
        self.install_button: ttk.Button | None = None
        self.save_button: ttk.Button | None = None
        self.load_button: ttk.Button | None = None

        self._build_ui()
        self._load_last_session_if_available()
        self._refresh_recent_menu()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._drain_log_queue)

    def _build_ui(self) -> None:
        self._build_menu()

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)

        header = ttk.Label(
            container,
            text="Generic Unity Android APK Builder",
            font=("Segoe UI", 13, "bold"),
        )
        header.grid(row=0, column=0, columnspan=3, sticky="w")

        subheader = ttk.Label(
            container,
            textvariable=self.status_var,
            foreground="#355c7d",
        )
        subheader.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 12))

        row = 2
        row = self._add_path_row(container, row, "Project Path", self.project_var, self._browse_project)
        row = self._add_path_row(container, row, "Unity.exe", self.unity_var, self._browse_unity)
        row = self._add_path_row(container, row, "adb.exe", self.adb_var, self._browse_adb)
        row = self._add_path_row(container, row, "Output Dir", self.output_var, self._browse_output)
        row = self._add_text_row(container, row, "APK Name", self.apk_name_var)
        row = self._add_path_row(container, row, "Keystore", self.keystore_var, self._browse_keystore)
        row = self._add_text_row(container, row, "Keystore Pass", self.keystore_pass_var, show="*")
        row = self._add_text_row(container, row, "Alias Name", self.alias_var)
        row = self._add_text_row(container, row, "Alias Pass", self.alias_pass_var, show="*")

        options_frame = ttk.LabelFrame(container, text="Build Options", padding=10)
        options_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 10))
        options_frame.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            options_frame,
            text="Build only, do not install to device",
            variable=self.skip_install_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            options_frame,
            text="Cleanup injected build script after build",
            variable=self.cleanup_script_var,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            options_frame,
            text="If cleanup is off, unchanged projects can skip Sync and Precompile on the next run. The build log streams progress during Stage 3.",
            wraplength=760,
            foreground="#555555",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        row += 1

        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        btn_frame.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(btn_frame, text="Start Build", command=self._start_build)
        self.start_button.pack(side=tk.LEFT)
        self.install_button = ttk.Button(btn_frame, text="Install APK", command=self._install_apk)
        self.install_button.pack(side=tk.LEFT, padx=(8, 0))
        self.save_button = ttk.Button(btn_frame, text="Save Config", command=self._save_config_as)
        self.save_button.pack(side=tk.LEFT, padx=(8, 0))
        self.load_button = ttk.Button(btn_frame, text="Load Config", command=self._load_config_from_dialog)
        self.load_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_frame, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT, padx=(8, 0))
        row += 1

        ttk.Label(container, text="Output Log").grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        self.log_text = tk.Text(container, wrap=tk.WORD, height=24)
        self.log_text.grid(row=row, column=0, columnspan=3, sticky="nsew")
        container.rowconfigure(row, weight=1)

        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=row, column=3, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Save Config As...", command=self._save_config_as)
        file_menu.add_command(label="Load Config...", command=self._load_config_from_dialog)
        file_menu.add_command(label="Load Last Session", command=self._load_last_session_if_available)
        file_menu.add_separator()
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Configs", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        menu_bar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu_bar)

    def _add_path_row(self, parent, row: int, label: str, variable: tk.StringVar, browse_command) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=4)
        ttk.Button(parent, text="Browse", command=browse_command).grid(row=row, column=2, sticky="ew", pady=4)
        return row + 1

    def _add_text_row(self, parent, row: int, label: str, variable: tk.StringVar, show: str | None = None) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=variable, show=show if show else "")
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)
        return row + 1

    def _browse_project(self) -> None:
        path = filedialog.askdirectory(initialdir=self.project_var.get() or DEFAULT_PROJECT)
        if path:
            self.project_var.set(path)
            self.output_var.set(str(Path(path) / "Builds" / "Android"))

    def _browse_unity(self) -> None:
        path = filedialog.askopenfilename(initialdir=Path(self.unity_var.get()).parent if self.unity_var.get() else "/", filetypes=[("Unity", "Unity.exe"), ("All Files", "*.*")])
        if path:
            self.unity_var.set(path)

    def _browse_adb(self) -> None:
        path = filedialog.askopenfilename(initialdir=Path(self.adb_var.get()).parent if self.adb_var.get() else "/", filetypes=[("ADB", "adb.exe"), ("All Files", "*.*")])
        if path:
            self.adb_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_var.get() or DEFAULT_OUTPUT)
        if path:
            self.output_var.set(path)

    def _browse_keystore(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Keystore", "*.keystore"), ("All Files", "*.*")])
        if path:
            self.keystore_var.set(path)

    def _load_state(self) -> dict:
        if not STATE_PATH.exists():
            return {"recent_configs": []}
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"recent_configs": []}

    def _save_state(self) -> None:
        STATE_PATH.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snapshot(self) -> dict:
        return {
            "project_path": self.project_var.get(),
            "unity_exe": self.unity_var.get(),
            "adb_exe": self.adb_var.get(),
            "output_dir": self.output_var.get(),
            "apk_name": self.apk_name_var.get(),
            "keystore_path": self.keystore_var.get(),
            "keystore_pass": self.keystore_pass_var.get(),
            "alias_name": self.alias_var.get(),
            "alias_pass": self.alias_pass_var.get(),
            "skip_install": self.skip_install_var.get(),
            "cleanup_injected_script": self.cleanup_script_var.get(),
        }

    def _apply_snapshot(self, data: dict) -> None:
        self.project_var.set(data.get("project_path", DEFAULT_PROJECT))
        self.unity_var.set(data.get("unity_exe", DEFAULT_UNITY))
        self.adb_var.set(data.get("adb_exe", DEFAULT_ADB))
        self.output_var.set(data.get("output_dir", DEFAULT_OUTPUT))
        self.apk_name_var.set(data.get("apk_name", "MR_System.apk"))
        self.keystore_var.set(data.get("keystore_path", ""))
        self.keystore_pass_var.set(data.get("keystore_pass", ""))
        self.alias_var.set(data.get("alias_name", "zcwl"))
        self.alias_pass_var.set(data.get("alias_pass", ""))
        self.skip_install_var.set(bool(data.get("skip_install", False)))
        self.cleanup_script_var.set(bool(data.get("cleanup_injected_script", False)))

    def _save_last_session(self) -> None:
        LAST_SESSION_PATH.write_text(json.dumps(self._snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_last_session_if_available(self) -> None:
        if not LAST_SESSION_PATH.exists():
            return
        try:
            data = json.loads(LAST_SESSION_PATH.read_text(encoding="utf-8"))
            self._apply_snapshot(data)
        except Exception as exc:
            self._append_log(f"Failed to load last session: {exc}\n")

    def _add_recent_config(self, path: Path) -> None:
        config_path = str(path.resolve())
        recents = [item for item in self.state.get("recent_configs", []) if item != config_path]
        recents.insert(0, config_path)
        self.state["recent_configs"] = recents[:MAX_RECENT_CONFIGS]
        self._save_state()
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        if self.recent_menu is None:
            return
        self.recent_menu.delete(0, tk.END)
        recents = self.state.get("recent_configs", [])
        if not recents:
            self.recent_menu.add_command(label="(Empty)", state=tk.DISABLED)
            return
        for item in recents:
            self.recent_menu.add_command(label=item, command=lambda p=item: self._load_config(Path(p)))

    def _save_config_as(self) -> None:
        CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=str(CONFIGS_DIR),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Save Build Config",
        )
        if not path:
            return
        target = Path(path)
        target.write_text(json.dumps(self._snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._add_recent_config(target)
        self._save_last_session()
        self._append_log(f"Saved config: {target}\n")

    def _load_config_from_dialog(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(CONFIGS_DIR if CONFIGS_DIR.exists() else TOOL_DIR),
            filetypes=[("JSON", "*.json")],
            title="Load Build Config",
        )
        if not path:
            return
        self._load_config(Path(path))

    def _load_config(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("Missing Config", f"Config file not found:\n{path}")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Invalid Config", f"Failed to read config:\n{exc}")
            return
        self._apply_snapshot(data)
        self._add_recent_config(path)
        self._save_last_session()
        self._append_log(f"Loaded config: {path}\n")

    def _validate(self) -> bool:
        project = Path(self.project_var.get())
        unity = Path(self.unity_var.get())
        adb = Path(self.adb_var.get())
        output_dir = Path(self.output_var.get())

        if not project.exists():
            messagebox.showerror("Invalid Project", "Project path does not exist.")
            return False
        if not (project / "Assets").exists() or not (project / "ProjectSettings").exists():
            messagebox.showerror("Invalid Project", "Selected path does not look like a Unity project.")
            return False
        if not unity.exists():
            messagebox.showerror("Invalid Unity", "Unity.exe path does not exist.")
            return False
        if not adb.exists():
            messagebox.showerror("Invalid ADB", "adb.exe path does not exist.")
            return False
        if not self.apk_name_var.get().strip():
            messagebox.showerror("Invalid APK Name", "APK name is required.")
            return False
        if self.keystore_var.get().strip():
            if not Path(self.keystore_var.get()).exists():
                messagebox.showerror("Invalid Keystore", "Keystore path does not exist.")
                return False
            if not self.alias_var.get().strip():
                messagebox.showerror("Invalid Alias", "Alias name is required when keystore is provided.")
                return False
        output_dir.mkdir(parents=True, exist_ok=True)
        return True

    def _set_build_running(self, running: bool) -> None:
        self.build_running = running
        if self.start_button is not None:
            self.start_button.configure(state=(tk.DISABLED if running else tk.NORMAL))
        if self.install_button is not None:
            self.install_button.configure(state=(tk.DISABLED if running else tk.NORMAL))
        if self.save_button is not None:
            self.save_button.configure(state=(tk.DISABLED if running else tk.NORMAL))
        if self.load_button is not None:
            self.load_button.configure(state=(tk.DISABLED if running else tk.NORMAL))
        self.status_var.set("Build running..." if running else "Ready")

    def _get_apk_path(self) -> Path:
        return Path(self.output_var.get()) / self.apk_name_var.get().strip()

    def _get_connected_devices(self, adb_path: Path) -> list[str]:
        result = subprocess.run(
            [str(adb_path), "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        devices: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.endswith("\tdevice"):
                devices.append(line.split("\t", 1)[0])
        return devices

    def _install_apk(self) -> None:
        if self.build_running:
            messagebox.showinfo("Busy", "A build is already running.")
            return

        adb_path = Path(self.adb_var.get())
        if not adb_path.exists():
            messagebox.showerror("Invalid ADB", "adb.exe path does not exist.")
            return

        apk_path = self._get_apk_path()
        if not apk_path.exists():
            messagebox.showerror("Missing APK", f"APK not found:\n{apk_path}")
            return

        try:
            devices = self._get_connected_devices(adb_path)
        except Exception as exc:
            messagebox.showerror("ADB Error", f"Failed to query devices:\n{exc}")
            return

        if not devices:
            messagebox.showerror("No Device", "No Android device detected over USB.")
            return

        self._append_log(f"\nInstalling existing APK: {apk_path}\n")
        for serial in devices:
            self._append_log(f"Installing to {serial} ...\n")
            result = subprocess.run(
                [str(adb_path), "-s", serial, "install", "-r", str(apk_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            output = (result.stdout or "") + (result.stderr or "")
            if output:
                self._append_log(output)
                if not output.endswith("\n"):
                    self._append_log("\n")
            if result.returncode != 0:
                messagebox.showerror("Install Failed", f"APK install failed for device:\n{serial}")
                return

        messagebox.showinfo("Install Complete", "APK installed to connected device(s).")

    def _start_build(self) -> None:
        if self.build_running:
            messagebox.showinfo("Busy", "A build is already running.")
            return
        if not self._validate():
            return

        self._save_last_session()
        self._set_build_running(True)
        self._append_log("Starting build...\n")
        self._append_log("Flow: Sync build script -> Precompile -> Build APK")
        if not self.skip_install_var.get():
            self._append_log(" -> Install")
        self._append_log("\nIf the project is unchanged and cleanup is off, Sync/Precompile may be skipped.\n\n")
        self.worker = threading.Thread(target=self._run_build, daemon=True)
        self.worker.start()

    def _read_process_output(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        try:
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                self.log_queue.put(("log", line))
        finally:
            process.stdout.close()

    def _run_build(self) -> None:
        try:
            command = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-NoProfile",
                "-File",
                str(SCRIPT_PATH),
                "-ProjectPath",
                self.project_var.get(),
                "-UnityExe",
                self.unity_var.get(),
                "-AdbExe",
                self.adb_var.get(),
                "-OutputDir",
                self.output_var.get(),
                "-ApkName",
                self.apk_name_var.get(),
            ]

            if self.keystore_var.get().strip():
                command += [
                    "-KeystorePath",
                    self.keystore_var.get(),
                    "-KeystorePass",
                    self.keystore_pass_var.get(),
                    "-KeyaliasName",
                    self.alias_var.get(),
                    "-KeyaliasPass",
                    self.alias_pass_var.get(),
                ]

            if self.skip_install_var.get():
                command.append("-SkipInstall")
            if self.cleanup_script_var.get():
                command.append("-CleanupInjectedScript")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            reader = threading.Thread(target=self._read_process_output, args=(process,), daemon=True)
            reader.start()

            exit_code = process.wait()
            self.log_queue.put(("finished", exit_code))
            reader.join(timeout=2.0)
        except Exception as exc:
            self.log_queue.put(("log", f"\nUnhandled error: {exc}\n"))
            self.log_queue.put(("finished", -1))

    def _drain_log_queue(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(item, tuple):
                kind, payload = item
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "finished":
                    exit_code = int(payload)
                    self.worker = None
                    self._set_build_running(False)
                    if exit_code == 0:
                        self.status_var.set("Build finished")
                        self._append_log("\nDone.\n")
                    else:
                        self.status_var.set(f"Build failed ({exit_code})")
                        self._append_log(f"\nFailed. Exit code: {exit_code}\n")
            else:
                self._append_log(str(item))

        self.root.after(120, self._drain_log_queue)

    def _append_log(self, text: str) -> None:
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _on_close(self) -> None:
        if self.build_running:
            messagebox.showinfo("Busy", "A build is still running.")
            return
        self._save_last_session()
        self.root.destroy()


def main() -> None:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    app = ApkBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
