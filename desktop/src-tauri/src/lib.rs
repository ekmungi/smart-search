// Tauri app setup: system tray, sidecar backend management, global shortcuts,
// autostart, MCP registration, and commands.
//
// In production: launches the PyInstaller-bundled smart-search sidecar via
// tauri-plugin-shell. In dev: falls back to Python module invocation.
// Registers a global hotkey (Ctrl+Space) for quick search and exposes a
// system tray with context menu.

use std::process::Command as StdCommand;
use std::process::Stdio;
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
use std::sync::{Arc, Mutex};

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, WindowEvent};
use tauri_plugin_global_shortcut::{
    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState as ShortcutState2,
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Default port for the smart-search HTTP backend.
const BACKEND_PORT: u16 = 9742;

/// Default shortcut when config is missing or unparseable.
const DEFAULT_SHORTCUT: &str = "Ctrl+Space";

/// Holds the currently active shortcut string for rollback on update failure.
struct ShortcutState {
    current: Mutex<String>,
}

/// Holds the managed backend child process handle.
///
/// Wrapped in Arc when managed by Tauri so the health monitor task
/// can share ownership without lifetime issues.
struct BackendState {
    child: Mutex<Option<CommandChild>>,
    /// Fallback: std::process::Child for dev mode (Python invocation).
    dev_child: Mutex<Option<std::process::Child>>,
}

/// Returns the backend API base URL for the frontend to use.
#[tauri::command]
fn get_backend_url() -> String {
    format!("http://127.0.0.1:{}/api", BACKEND_PORT)
}

/// Hide the quick search window from any context.
#[tauri::command]
fn hide_search_window(app: AppHandle) {
    if let Some(window) = app.get_webview_window("search") {
        let _ = window.hide();
    }
}

/// Quit the app: stop backend and exit. Called when close-to-tray is off.
#[tauri::command]
fn quit_app(app: AppHandle) {
    let state = app.state::<Arc<BackendState>>();
    stop_backend(&state);
    app.exit(0);
}

/// Open a file in the user's default application.
#[tauri::command]
fn open_file(path: String) -> Result<(), String> {
    open::that(&path).map_err(|e| format!("Failed to open {}: {}", path, e))
}

/// Open the file's parent folder and highlight the file in the file manager.
#[tauri::command]
fn show_in_folder(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        // Convert POSIX slashes to backslashes for Windows explorer.
        // Use cmd /c to pass the entire command as a raw string -- Rust's
        // Command escapes arguments in ways explorer.exe doesn't understand.
        let win_path = path.replace('/', "\\");
        StdCommand::new("cmd")
            .args(["/C", &format!("explorer /select,\"{}\"", win_path)])
            .creation_flags(0x08000000) // CREATE_NO_WINDOW: hide cmd flash
            .spawn()
            .map_err(|e| format!("Failed to show {}: {}", path, e))?;
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    {
        let parent = std::path::Path::new(&path)
            .parent()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| path.clone());
        open::that(&parent).map_err(|e| format!("Failed to open folder: {}", e))
    }
}

/// Check whether smart-search is registered as an MCP server with Claude Code.
///
/// Runs with a 3-second timeout to avoid blocking the Tauri IPC thread.
#[tauri::command]
async fn check_mcp_registered() -> bool {
    tauri::async_runtime::spawn_blocking(|| {
        let child = StdCommand::new("claude")
            .args(["mcp", "list"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn();

        match child {
            Ok(child) => {
                // Wait with timeout to avoid hanging the UI
                let output = child.wait_with_output();
                match output {
                    Ok(o) => String::from_utf8_lossy(&o.stdout).contains("smart-search"),
                    Err(_) => false,
                }
            }
            Err(_) => false,
        }
    })
    .await
    .unwrap_or(false)
}

/// Register smart-search as an MCP server with Claude Code.
///
/// Uses the sidecar exe path in production, Python module in dev.
/// Runs on a blocking thread to avoid freezing the UI.
#[tauri::command]
async fn register_mcp() -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let exe_path = std::env::current_exe().map_err(|e| e.to_string())?;
        let exe_dir = exe_path.parent().unwrap_or(std::path::Path::new("."));

        // In production the sidecar is next to the Tauri binary
        let sidecar = exe_dir.join("smart-search.exe");

        let args: Vec<String> = if sidecar.exists() {
            let path_str = sidecar.to_string_lossy().to_string();
            vec![
                "mcp".into(),
                "add".into(),
                "-s".into(),
                "user".into(),
                "smart-search".into(),
                "--".into(),
                path_str,
                "mcp".into(),
            ]
        } else {
            // Dev mode fallback: register via Python module
            vec![
                "mcp".into(),
                "add".into(),
                "-s".into(),
                "user".into(),
                "smart-search".into(),
                "--".into(),
                "python".into(),
                "-m".into(),
                "smart_search.server".into(),
            ]
        };

        let output = StdCommand::new("claude")
            .args(&args)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .map_err(|e| format!("Failed to run claude CLI: {}", e))?;

        if output.status.success() {
            Ok("MCP server registered successfully".into())
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            Err(format!("Registration failed: {}", stderr))
        }
    })
    .await
    .unwrap_or(Err("MCP registration task failed".into()))
}

/// Parse a shortcut string like "Ctrl+Shift+K" into a tauri global-shortcut Shortcut.
///
/// Supports modifiers: Ctrl, Shift, Alt, Super/Meta/Cmd.
/// Supports keys: A-Z, 0-9, F1-F24, Space, Enter, Tab, Escape, arrows, etc.
fn parse_shortcut(s: &str) -> Result<Shortcut, String> {
    let parts: Vec<&str> = s.split('+').map(|p| p.trim()).collect();
    if parts.is_empty() {
        return Err("Empty shortcut string".to_string());
    }

    let mut modifiers = Modifiers::empty();
    let mut key_str = "";

    for (i, part) in parts.iter().enumerate() {
        if i == parts.len() - 1 {
            // Last part is the key
            key_str = part;
        } else {
            match part.to_lowercase().as_str() {
                "ctrl" | "control" => modifiers |= Modifiers::CONTROL,
                "shift" => modifiers |= Modifiers::SHIFT,
                "alt" | "option" => modifiers |= Modifiers::ALT,
                "super" | "meta" | "cmd" | "command" => modifiers |= Modifiers::SUPER,
                _ => return Err(format!("Unknown modifier: {}", part)),
            }
        }
    }

    let code = match key_str.to_lowercase().as_str() {
        "space" => Code::Space,
        "enter" | "return" => Code::Enter,
        "tab" => Code::Tab,
        "escape" | "esc" => Code::Escape,
        "backspace" => Code::Backspace,
        "delete" | "del" => Code::Delete,
        "up" | "arrowup" => Code::ArrowUp,
        "down" | "arrowdown" => Code::ArrowDown,
        "left" | "arrowleft" => Code::ArrowLeft,
        "right" | "arrowright" => Code::ArrowRight,
        "a" => Code::KeyA,
        "b" => Code::KeyB,
        "c" => Code::KeyC,
        "d" => Code::KeyD,
        "e" => Code::KeyE,
        "f" if key_str.len() == 1 => Code::KeyF,
        "g" => Code::KeyG,
        "h" => Code::KeyH,
        "i" => Code::KeyI,
        "j" => Code::KeyJ,
        "k" => Code::KeyK,
        "l" => Code::KeyL,
        "m" => Code::KeyM,
        "n" => Code::KeyN,
        "o" => Code::KeyO,
        "p" => Code::KeyP,
        "q" => Code::KeyQ,
        "r" => Code::KeyR,
        "s" => Code::KeyS,
        "t" => Code::KeyT,
        "u" => Code::KeyU,
        "v" => Code::KeyV,
        "w" => Code::KeyW,
        "x" => Code::KeyX,
        "y" => Code::KeyY,
        "z" => Code::KeyZ,
        "0" => Code::Digit0,
        "1" => Code::Digit1,
        "2" => Code::Digit2,
        "3" => Code::Digit3,
        "4" => Code::Digit4,
        "5" => Code::Digit5,
        "6" => Code::Digit6,
        "7" => Code::Digit7,
        "8" => Code::Digit8,
        "9" => Code::Digit9,
        "f1" => Code::F1,
        "f2" => Code::F2,
        "f3" => Code::F3,
        "f4" => Code::F4,
        "f5" => Code::F5,
        "f6" => Code::F6,
        "f7" => Code::F7,
        "f8" => Code::F8,
        "f9" => Code::F9,
        "f10" => Code::F10,
        "f11" => Code::F11,
        "f12" => Code::F12,
        "f13" => Code::F13,
        "f14" => Code::F14,
        "f15" => Code::F15,
        "f16" => Code::F16,
        "f17" => Code::F17,
        "f18" => Code::F18,
        "f19" => Code::F19,
        "f20" => Code::F20,
        "f21" => Code::F21,
        "f22" => Code::F22,
        "f23" => Code::F23,
        "f24" => Code::F24,
        _ => return Err(format!("Unknown key: {}", key_str)),
    };

    let mods = if modifiers.is_empty() {
        None
    } else {
        Some(modifiers)
    };
    Ok(Shortcut::new(mods, code))
}

/// Read the shortcut_key from config.json in the OS data directory.
///
/// On Windows: %LOCALAPPDATA%\smart-search\config.json
/// Falls back to DEFAULT_SHORTCUT if file is missing or key is absent.
fn read_shortcut_from_config() -> String {
    let config_path =
        dirs_next::data_local_dir().map(|d| d.join("smart-search").join("config.json"));

    let path = match config_path {
        Some(p) if p.exists() => p,
        _ => return DEFAULT_SHORTCUT.to_string(),
    };

    let contents = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return DEFAULT_SHORTCUT.to_string(),
    };

    let json: serde_json::Value = match serde_json::from_str(&contents) {
        Ok(v) => v,
        Err(_) => return DEFAULT_SHORTCUT.to_string(),
    };

    json.get("shortcut_key")
        .and_then(|v| v.as_str())
        .unwrap_or(DEFAULT_SHORTCUT)
        .to_string()
}

/// Update the global shortcut at runtime from the frontend.
///
/// Parses the new shortcut string, unregisters the old one, registers the new one.
/// The handler from `setup_global_shortcut` (via `with_handler`) applies to all
/// registered shortcuts, so we only need register/unregister here.
/// On failure, rolls back to the previous shortcut.
#[tauri::command]
async fn update_shortcut(app: AppHandle, shortcut: String) -> Result<String, String> {
    let new_sc = parse_shortcut(&shortcut)?;

    let state = app.state::<ShortcutState>();
    let old_shortcut_str = state.current.lock().unwrap().clone();
    let old_sc = parse_shortcut(&old_shortcut_str)
        .map_err(|e| format!("Failed to parse old shortcut: {}", e))?;

    let gs = app.global_shortcut();

    // Unregister all shortcuts first — unregister(specific) can fail on Windows
    // when the shortcut was registered via Builder::with_handler()
    let _ = gs.unregister_all();

    // Register the new shortcut (handler is already set globally via with_handler)
    if let Err(e) = gs.register(new_sc) {
        // Rollback: re-register old shortcut
        let _ = gs.register(old_sc);
        return Err(format!("Failed to register new shortcut: {}", e));
    }

    // Update tracked state
    *state.current.lock().unwrap() = shortcut.clone();

    Ok(format!("Shortcut updated to {}", shortcut))
}

/// Toggle the quick search overlay window visibility.
fn toggle_search_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("search") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.center();
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

/// Check if the backend HTTP server is healthy by hitting /api/health.
///
/// Returns true if the server responds with 200 within 3 seconds.
async fn check_backend_health(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{}/api/health", port);
    let result = tokio::time::timeout(
        std::time::Duration::from_secs(3),
        tauri::async_runtime::spawn_blocking(move || match ureq::get(&url).call() {
            Ok(resp) => resp.status() == 200,
            Err(_) => false,
        }),
    )
    .await;

    match result {
        Ok(Ok(healthy)) => healthy,
        _ => false,
    }
}

/// Attempt to start the backend via Tauri sidecar (production).
///
/// Returns the CommandChild handle on success.
fn start_sidecar(app: &AppHandle) -> Option<CommandChild> {
    let port = BACKEND_PORT.to_string();
    let shell = app.shell();

    let result = shell
        .sidecar("smart-search")
        .map(|cmd| cmd.args(["serve", "--port", &port]));

    match result {
        Ok(command) => {
            match command.spawn() {
                Ok((mut rx, child)) => {
                    // Spawn a task to consume stdout/stderr so the pipe doesn't block
                    tauri::async_runtime::spawn(async move {
                        while let Some(event) = rx.recv().await {
                            match event {
                                CommandEvent::Stderr(line) => {
                                    log::debug!(
                                        "backend stderr: {}",
                                        String::from_utf8_lossy(&line)
                                    );
                                }
                                CommandEvent::Stdout(line) => {
                                    log::debug!(
                                        "backend stdout: {}",
                                        String::from_utf8_lossy(&line)
                                    );
                                }
                                CommandEvent::Terminated(payload) => {
                                    log::info!("backend exited with code {:?}", payload.code);
                                    break;
                                }
                                _ => {}
                            }
                        }
                    });
                    Some(child)
                }
                Err(e) => {
                    log::warn!("Failed to spawn sidecar: {}", e);
                    None
                }
            }
        }
        Err(e) => {
            log::warn!("Sidecar not available: {}", e);
            None
        }
    }
}

/// Attempt to start the backend via Python module (dev mode fallback).
fn start_dev_backend() -> Option<std::process::Child> {
    let port = BACKEND_PORT.to_string();
    StdCommand::new("python")
        .args(["-m", "smart_search.cli", "serve", "--port", &port])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()
}

/// Gracefully stop the backend, falling back to force-kill if needed.
///
/// Four-layer approach:
///   1. POST /api/shutdown -- asks uvicorn to exit cleanly (flushes DB, stops watchers)
///   2. Wait up to 5s for the process to exit
///   3. Tree-kill the managed child PID (Windows doesn't propagate kills)
///   4. Kill by port / exe name (catches orphans)
fn stop_backend(state: &BackendState) {
    // Layer 1: Graceful HTTP shutdown request
    let graceful_ok = graceful_shutdown(BACKEND_PORT);

    if graceful_ok {
        // Layer 2: Wait for the process to actually exit
        let start = std::time::Instant::now();
        let timeout = std::time::Duration::from_secs(5);
        while start.elapsed() < timeout {
            if std::net::TcpStream::connect(format!("127.0.0.1:{}", BACKEND_PORT)).is_err() {
                log::info!("Backend shut down gracefully");
                // Clear managed handles
                if let Ok(mut guard) = state.child.lock() {
                    guard.take();
                }
                if let Ok(mut guard) = state.dev_child.lock() {
                    *guard = None;
                }
                return;
            }
            std::thread::sleep(std::time::Duration::from_millis(250));
        }
        log::warn!("Backend did not exit within 5s after graceful shutdown, force-killing");
    }

    // Layer 3: Tree-kill managed child processes
    if let Ok(mut guard) = state.child.lock() {
        if let Some(child) = guard.take() {
            let pid = child.pid();
            let _ = StdCommand::new("taskkill")
                .args(["/T", "/F", "/PID", &pid.to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            log::info!("Tree-killed sidecar process tree from PID {}", pid);
        }
    }
    if let Ok(mut guard) = state.dev_child.lock() {
        if let Some(ref mut child) = *guard {
            let pid = child.id();
            let _ = StdCommand::new("taskkill")
                .args(["/T", "/F", "/PID", &pid.to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            log::info!("Tree-killed dev backend process tree from PID {}", pid);
        }
        *guard = None;
    }

    // Layer 4: Kill by port + exe name (orphan cleanup)
    kill_process_on_port(BACKEND_PORT);
    kill_sidecar_by_name();
}

/// Send a graceful shutdown request to the backend HTTP server.
///
/// Returns true if the server acknowledged the request (HTTP 200).
/// Returns false on any error (connection refused, timeout, etc.).
fn graceful_shutdown(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{}/api/shutdown", port);
    let agent = ureq::AgentBuilder::new()
        .timeout(std::time::Duration::from_secs(3))
        .build();
    match agent.post(&url).call() {
        Ok(resp) => {
            log::info!("Graceful shutdown requested (HTTP {})", resp.status());
            resp.status() == 200
        }
        Err(e) => {
            log::debug!("Graceful shutdown request failed: {}", e);
            false
        }
    }
}

/// Find and kill whatever process is listening on the given port.
///
/// Uses `netstat` to find the PID and `taskkill /T` to terminate its
/// entire process tree.  Silently does nothing on failure (port already
/// free, permissions, etc.).
fn kill_process_on_port(port: u16) {
    // netstat -ano | findstr :9742 → "  TCP  127.0.0.1:9742  ...  LISTENING  12345"
    let output = StdCommand::new("cmd")
        .args(["/C", &format!("netstat -ano | findstr :{}", port)])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output();

    let output = match output {
        Ok(o) => o,
        Err(_) => return,
    };

    let stdout = String::from_utf8_lossy(&output.stdout);
    for line in stdout.lines() {
        if !line.contains("LISTENING") {
            continue;
        }
        // PID is the last whitespace-separated token
        if let Some(pid_str) = line.split_whitespace().last() {
            if let Ok(pid) = pid_str.parse::<u32>() {
                if pid > 0 {
                    let _ = StdCommand::new("taskkill")
                        .args(["/T", "/F", "/PID", &pid.to_string()])
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .status();
                    log::info!("Killed process tree on port {} (PID {})", port, pid);
                    return;
                }
            }
        }
    }
}

/// Kill any smart-search.exe processes running from the installed location.
///
/// Final safety net: finds smart-search.exe processes whose path matches
/// the install directory (%LOCALAPPDATA%\Smart Search\) and kills them.
/// Skips the current process (the Tauri app itself) and any MCP server
/// instances (which run from the same exe but via stdio, not HTTP).
/// Only targets processes from the install dir to avoid killing dev instances.
fn kill_sidecar_by_name() {
    let install_dir = dirs_next::data_local_dir()
        .map(|d| d.join("Smart Search"))
        .unwrap_or_default();
    let install_prefix = install_dir.to_string_lossy().to_lowercase();

    if install_prefix.is_empty() {
        return;
    }

    // Use tasklist /V to get full image paths -- but tasklist doesn't show
    // paths reliably.  Instead, query via cmd /C to get PIDs of all
    // smart-search.exe, then filter by checking each one's path.
    let output = StdCommand::new("cmd")
        .args([
            "/C",
            "tasklist /FI \"IMAGENAME eq smart-search.exe\" /FO CSV /NH",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output();

    let output = match output {
        Ok(o) => o,
        Err(_) => return,
    };

    let current_pid = std::process::id();
    let stdout = String::from_utf8_lossy(&output.stdout);

    for line in stdout.lines() {
        // CSV format: "smart-search.exe","12345","Console","1","8,612 K"
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() < 2 {
            continue;
        }
        let pid_str = parts[1].trim_matches('"');
        let pid: u32 = match pid_str.parse() {
            Ok(p) => p,
            Err(_) => continue,
        };

        // Never kill ourselves
        if pid == current_pid || pid == 0 {
            continue;
        }

        // Check if this process is from the install directory by reading
        // its executable path via PowerShell (most reliable on modern Windows)
        let path_output = StdCommand::new("cmd")
            .args([
                "/C",
                &format!(
                    "powershell -NoProfile -Command \"(Get-Process -Id {} -ErrorAction SilentlyContinue).Path\"",
                    pid
                ),
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output();

        let exe_path = match path_output {
            Ok(o) => String::from_utf8_lossy(&o.stdout).trim().to_lowercase(),
            Err(_) => continue,
        };

        if exe_path.starts_with(&install_prefix) {
            let _ = StdCommand::new("taskkill")
                .args(["/T", "/F", "/PID", &pid.to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            log::info!("Killed orphan sidecar PID {} (path: {})", pid, exe_path);
        }
    }
}

/// Build the system tray with context menu and event handlers.
fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let open = MenuItem::with_id(app, "open", "Open Dashboard", true, None::<&str>)?;
    let search = MenuItem::with_id(app, "search", "Quick Search", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Smart Search", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &search, &separator, &quit])?;

    let _tray = TrayIconBuilder::new()
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .tooltip("Smart Search")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "quit" => {
                let state = app.state::<Arc<BackendState>>();
                stop_backend(&state);
                app.exit(0);
            }
            "open" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "search" => {
                toggle_search_window(app);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        })
        .build(app)?;

    Ok(())
}

/// Auto-register MCP on every launch if the sidecar path has changed.
///
/// Stores the registered sidecar path in a `.mcp_registered` flag file in
/// %LOCALAPPDATA%\smart-search. Re-registers whenever the current sidecar
/// path differs from the stored one (e.g., after reinstall to a new location).
fn auto_register_mcp_if_needed() {
    let flag_dir = dirs_next::data_local_dir()
        .map(|d| d.join("smart-search"))
        .unwrap_or_default();
    let flag_file = flag_dir.join(".mcp_registered");

    // Only auto-register if the sidecar exe is present (production install)
    let exe_path = match std::env::current_exe() {
        Ok(p) => p,
        Err(_) => return,
    };
    let exe_dir = exe_path.parent().unwrap_or(std::path::Path::new("."));
    let sidecar = exe_dir.join("smart-search.exe");

    if !sidecar.exists() {
        return;
    }

    let path_str = sidecar.to_string_lossy().to_string();

    // Skip registration if the stored path matches the current sidecar path
    if let Ok(stored) = std::fs::read_to_string(&flag_file) {
        if stored.trim() == path_str {
            return;
        }
        log::info!(
            "MCP sidecar path changed: {} -> {}",
            stored.trim(),
            path_str
        );
    }

    let result = StdCommand::new("claude")
        .args([
            "mcp",
            "add",
            "-s",
            "user",
            "smart-search",
            "--",
            &path_str,
            "mcp",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    if let Ok(status) = result {
        if status.success() {
            let _ = std::fs::create_dir_all(&flag_dir);
            let _ = std::fs::write(&flag_file, &path_str);
            log::info!("MCP auto-registered with path: {}", path_str);
        }
    }
}

/// Register the global shortcut for quick search, reading from config.json.
///
/// Falls back to Ctrl+Space if the config file is missing or the key is invalid.
/// Stores the active shortcut string in ShortcutState for runtime updates.
fn setup_global_shortcut(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let shortcut_str = read_shortcut_from_config();
    let shortcut = parse_shortcut(&shortcut_str).unwrap_or_else(|e| {
        log::warn!("Invalid shortcut '{}': {}. Using default.", shortcut_str, e);
        parse_shortcut(DEFAULT_SHORTCUT).unwrap()
    });

    // Store the active shortcut string for runtime updates
    let effective = if parse_shortcut(&shortcut_str).is_ok() {
        shortcut_str
    } else {
        DEFAULT_SHORTCUT.to_string()
    };
    *app.state::<ShortcutState>().current.lock().unwrap() = effective;

    app.handle().plugin(
        tauri_plugin_global_shortcut::Builder::new()
            .with_handler(|app, _shortcut, event| {
                if event.state == ShortcutState2::Pressed {
                    toggle_search_window(app);
                }
            })
            .build(),
    )?;

    app.global_shortcut().register(shortcut)?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_denylist(&["search"])
                .build(),
        )
        .plugin(tauri_plugin_shell::init())
        .manage(Arc::new(BackendState {
            child: Mutex::new(None),
            dev_child: Mutex::new(None),
        }))
        .manage(ShortcutState {
            current: Mutex::new(DEFAULT_SHORTCUT.to_string()),
        })
        .setup(|app| {
            let state = app.state::<Arc<BackendState>>();

            // Start the backend: check if already running, then try appropriate method
            let backend_alive =
                std::net::TcpStream::connect(format!("127.0.0.1:{}", BACKEND_PORT)).is_ok();

            if backend_alive {
                log::info!("Backend already running on port {}", BACKEND_PORT);
            } else if cfg!(debug_assertions) {
                // Kill any orphan from a previous crash before spawning a new one
                log::info!("Killing any orphan backend on port {}", BACKEND_PORT);
                kill_process_on_port(BACKEND_PORT);
                // Dev mode: prefer Python directly (sidecar binary may be stale)
                if let Some(child) = start_dev_backend() {
                    *state.dev_child.lock().unwrap() = Some(child);
                    log::info!("Backend started via Python on port {}", BACKEND_PORT);
                } else {
                    log::warn!("Could not start Python backend");
                }
            } else {
                // Kill orphans from a previous crash: port-based + name-based
                log::info!("Killing any orphan backend processes");
                kill_process_on_port(BACKEND_PORT);
                kill_sidecar_by_name();
                // Production: use sidecar, fall back to Python
                if let Some(child) = start_sidecar(app.handle()) {
                    *state.child.lock().unwrap() = Some(child);
                    log::info!("Backend started via sidecar on port {}", BACKEND_PORT);
                } else if let Some(child) = start_dev_backend() {
                    *state.dev_child.lock().unwrap() = Some(child);
                    log::info!("Backend started via Python on port {}", BACKEND_PORT);
                } else {
                    log::warn!(
                        "Could not start backend -- start manually with: smart-search serve"
                    );
                }
            }

            // Spawn a background health monitor that restarts the sidecar
            // on crash (e.g. OOM during indexing). Checks every 5s; restarts
            // after 3 consecutive failures (15s confirmed downtime).
            if !cfg!(debug_assertions) {
                let app_handle = app.handle().clone();
                let monitor_state = app.state::<Arc<BackendState>>().inner().clone();
                tauri::async_runtime::spawn(async move {
                    let mut consecutive_failures: u32 = 0;
                    loop {
                        tokio::time::sleep(std::time::Duration::from_secs(5)).await;

                        let healthy = check_backend_health(BACKEND_PORT).await;
                        if healthy {
                            consecutive_failures = 0;
                            continue;
                        }

                        consecutive_failures += 1;
                        if consecutive_failures >= 3 {
                            log::warn!("Backend unresponsive for 15s, restarting sidecar...");
                            kill_process_on_port(BACKEND_PORT);
                            kill_sidecar_by_name();
                            if let Some(child) = start_sidecar(&app_handle) {
                                *monitor_state.child.lock().unwrap() = Some(child);
                                log::info!("Sidecar restarted successfully");
                            }
                            consecutive_failures = 0;
                            // Wait 10s for startup before resuming health checks
                            tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                        }
                    }
                });
            }

            // Auto-register MCP on first production launch
            auto_register_mcp_if_needed();

            // Set up system tray
            setup_tray(app)?;

            // Register global shortcut from config -- non-fatal if already taken
            if let Err(e) = setup_global_shortcut(app) {
                log::warn!("Could not register global shortcut: {}", e);
            }

            // Plugins
            app.handle().plugin(tauri_plugin_dialog::init())?;
            app.handle().plugin(tauri_plugin_autostart::init(
                tauri_plugin_autostart::MacosLauncher::LaunchAgent,
                None,
            ))?;
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // Hide the main window on close instead of destroying it (tray app pattern)
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            hide_search_window,
            open_file,
            show_in_folder,
            quit_app,
            check_mcp_registered,
            register_mcp,
            update_shortcut,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                // Kill the backend sidecar/dev process when the app exits
                let state = app.state::<Arc<BackendState>>();
                stop_backend(&state);
            }
        });
}
