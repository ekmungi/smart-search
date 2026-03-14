// Tauri app setup: system tray, backend process management, and commands.
//
// Starts the smart-search HTTP backend as a child process and exposes
// a system tray with status indicator and context menu.

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::Manager;

/// Default port for the smart-search HTTP backend.
const BACKEND_PORT: u16 = 9742;

/// Holds the managed backend child process.
struct BackendState {
    process: Mutex<Option<Child>>,
}

/// Returns the backend API base URL for the frontend to use.
#[tauri::command]
fn get_backend_url() -> String {
    format!("http://127.0.0.1:{}/api", BACKEND_PORT)
}

/// Attempt to start the smart-search HTTP backend.
///
/// Tries the bundled exe first, then falls back to the Python module.
/// Returns None if both fail (user must start manually).
fn start_backend() -> Option<Child> {
    let port = BACKEND_PORT.to_string();

    // Try bundled smart-search.exe first
    Command::new("smart-search")
        .args(["serve", "--port", &port])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .or_else(|_| {
            // Fall back to Python module (development mode)
            Command::new("python")
                .args(["-m", "smart_search.cli", "serve", "--port", &port])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
        })
        .ok()
}

/// Kill the backend child process if it is running.
fn stop_backend(state: &BackendState) {
    if let Ok(mut guard) = state.process.lock() {
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
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Smart Search", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &separator, &quit])?;

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendState {
            process: Mutex::new(None),
        })
        .setup(|app| {
            // Start the Python backend process
            let state = app.state::<BackendState>();
            if let Some(child) = start_backend() {
                *state.process.lock().unwrap() = Some(child);
                log::info!("Backend started on port {}", BACKEND_PORT);
            } else {
                log::warn!("Could not start backend -- start manually with: smart-search serve");
            }

            // Set up system tray
            setup_tray(app)?;

            // Plugins
            app.handle().plugin(tauri_plugin_dialog::init())?;
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_url])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
