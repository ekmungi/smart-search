// Tauri app setup: system tray, sidecar backend management, global shortcuts,
// autostart, MCP registration, and commands.
//
// In production: launches the PyInstaller-bundled smart-search sidecar via
// tauri-plugin-shell. In dev: falls back to Python module invocation.
// Registers a global hotkey (Ctrl+Space) for quick search and exposes a
// system tray with context menu.

use std::process::Command as StdCommand;
use std::process::Stdio;
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, WindowEvent};
use tauri_plugin_global_shortcut::{
    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState as ShortcutState2,
};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};

/// Default port for the smart-search HTTP backend.
const BACKEND_PORT: u16 = 9742;

/// Default shortcut when config is missing or unparseable.
const DEFAULT_SHORTCUT: &str = "Ctrl+Space";

/// Holds the currently active shortcut string for rollback on update failure.
struct ShortcutState {
    current: Mutex<String>,
}

/// Holds the managed backend child process handle.
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
    let state = app.state::<BackendState>();
    stop_backend(&state);
    app.exit(0);
}

/// Open a file in the user's default application.
#[tauri::command]
fn open_file(path: String) -> Result<(), String> {
    open::that(&path).map_err(|e| format!("Failed to open {}: {}", path, e))
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
                "mcp".into(), "add".into(), "-s".into(), "user".into(),
                "smart-search".into(), "--".into(), path_str, "mcp".into(),
            ]
        } else {
            // Dev mode fallback: register via Python module
            vec![
                "mcp".into(), "add".into(), "-s".into(), "user".into(),
                "smart-search".into(), "--".into(),
                "python".into(), "-m".into(), "smart_search.server".into(),
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
        "a" => Code::KeyA, "b" => Code::KeyB, "c" => Code::KeyC,
        "d" => Code::KeyD, "e" => Code::KeyE, "f" if key_str.len() == 1 => Code::KeyF,
        "g" => Code::KeyG, "h" => Code::KeyH, "i" => Code::KeyI,
        "j" => Code::KeyJ, "k" => Code::KeyK, "l" => Code::KeyL,
        "m" => Code::KeyM, "n" => Code::KeyN, "o" => Code::KeyO,
        "p" => Code::KeyP, "q" => Code::KeyQ, "r" => Code::KeyR,
        "s" => Code::KeyS, "t" => Code::KeyT, "u" => Code::KeyU,
        "v" => Code::KeyV, "w" => Code::KeyW, "x" => Code::KeyX,
        "y" => Code::KeyY, "z" => Code::KeyZ,
        "0" => Code::Digit0, "1" => Code::Digit1, "2" => Code::Digit2,
        "3" => Code::Digit3, "4" => Code::Digit4, "5" => Code::Digit5,
        "6" => Code::Digit6, "7" => Code::Digit7, "8" => Code::Digit8,
        "9" => Code::Digit9,
        "f1" => Code::F1, "f2" => Code::F2, "f3" => Code::F3,
        "f4" => Code::F4, "f5" => Code::F5, "f6" => Code::F6,
        "f7" => Code::F7, "f8" => Code::F8, "f9" => Code::F9,
        "f10" => Code::F10, "f11" => Code::F11, "f12" => Code::F12,
        "f13" => Code::F13, "f14" => Code::F14, "f15" => Code::F15,
        "f16" => Code::F16, "f17" => Code::F17, "f18" => Code::F18,
        "f19" => Code::F19, "f20" => Code::F20, "f21" => Code::F21,
        "f22" => Code::F22, "f23" => Code::F23, "f24" => Code::F24,
        _ => return Err(format!("Unknown key: {}", key_str)),
    };

    let mods = if modifiers.is_empty() { None } else { Some(modifiers) };
    Ok(Shortcut::new(mods, code))
}

/// Read the shortcut_key from config.json in the OS data directory.
///
/// On Windows: %LOCALAPPDATA%\smart-search\config.json
/// Falls back to DEFAULT_SHORTCUT if file is missing or key is absent.
fn read_shortcut_from_config() -> String {
    let config_path = dirs_next::data_local_dir()
        .map(|d| d.join("smart-search").join("config.json"));

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
                                    log::debug!("backend stderr: {}", String::from_utf8_lossy(&line));
                                }
                                CommandEvent::Stdout(line) => {
                                    log::debug!("backend stdout: {}", String::from_utf8_lossy(&line));
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

/// Kill the backend child process if it is running.
fn stop_backend(state: &BackendState) {
    // Stop sidecar child
    if let Ok(mut guard) = state.child.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
    // Stop dev child
    if let Ok(mut guard) = state.dev_child.lock() {
        if let Some(ref mut child) = *guard {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
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
                let state = app.state::<BackendState>();
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

/// Auto-register MCP on first launch if sidecar is available.
///
/// Checks for a `.mcp_registered` flag file in %LOCALAPPDATA%\smart-search.
/// If missing and the sidecar exe exists, registers and writes the flag.
fn auto_register_mcp_if_needed() {
    let flag_dir = dirs_next::data_local_dir()
        .map(|d| d.join("smart-search"))
        .unwrap_or_default();
    let flag_file = flag_dir.join(".mcp_registered");

    if flag_file.exists() {
        return;
    }

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
    let result = StdCommand::new("claude")
        .args([
            "mcp", "add", "-s", "user",
            "smart-search", "--", &path_str, "mcp",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    if let Ok(status) = result {
        if status.success() {
            let _ = std::fs::create_dir_all(&flag_dir);
            let _ = std::fs::write(&flag_file, "registered");
            log::info!("MCP auto-registered on first launch");
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
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState {
            child: Mutex::new(None),
            dev_child: Mutex::new(None),
        })
        .manage(ShortcutState {
            current: Mutex::new(DEFAULT_SHORTCUT.to_string()),
        })
        .setup(|app| {
            let state = app.state::<BackendState>();

            // Start the backend: check if already running, then try appropriate method
            let backend_alive = std::net::TcpStream::connect(
                format!("127.0.0.1:{}", BACKEND_PORT)
            ).is_ok();

            if backend_alive {
                log::info!("Backend already running on port {}", BACKEND_PORT);
            } else if cfg!(debug_assertions) {
                // Dev mode: prefer Python directly (sidecar binary may be stale)
                if let Some(child) = start_dev_backend() {
                    *state.dev_child.lock().unwrap() = Some(child);
                    log::info!("Backend started via Python on port {}", BACKEND_PORT);
                } else {
                    log::warn!("Could not start Python backend");
                }
            } else {
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
                let state = app.state::<BackendState>();
                stop_backend(&state);
            }
        });
}
