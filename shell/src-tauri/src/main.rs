// RotLab TV: a see-through, borderless window over the screen's work area. The page (served by the
// RotLab hub on this PC) draws the TV, drawers, messages and stubs, and tells us where they are; mouse
// clicks anywhere else go straight through to whatever is behind.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

#[derive(Default)]
struct Hit {
    rects: Vec<[f64; 4]>,
    scale: f64,
}
type Shared = Arc<Mutex<Hit>>;

fn arg(name: &str) -> Option<String> {
    let a: Vec<String> = std::env::args().collect();
    a.iter().position(|x| x == name).and_then(|i| a.get(i + 1).cloned())
}

fn port() -> u16 {
    arg("--port").and_then(|p| p.parse().ok()).unwrap_or(8765)
}

#[tauri::command]
fn region(state: tauri::State<Shared>, rects: Vec<[f64; 4]>, dpr: f64) {
    let mut h = state.lock().unwrap();
    h.rects = rects;
    h.scale = if dpr > 0.0 { dpr } else { 1.0 };
}

#[tauri::command]
fn ready() -> serde_json::Value {
    serde_json::json!({ "ok": true, "shell": env!("CARGO_PKG_VERSION") })
}

#[tauri::command]
fn minimize(window: WebviewWindow) {
    let _ = window.minimize();
}

#[tauri::command]
fn close(app: tauri::AppHandle) {
    app.exit(0);
}

#[tauri::command]
fn on_top(window: WebviewWindow, v: bool) {
    let _ = window.set_always_on_top(v);
}

// async: creating a window from a synchronous command can deadlock on Windows
#[tauri::command]
async fn classic(app: tauri::AppHandle, hash: String) -> Result<(), String> {
    let url = format!(
        "http://localhost:{}/classic{}",
        port(),
        if hash.is_empty() { String::new() } else { format!("#{}", hash) }
    );
    if let Some(w) = app.get_webview_window("classic") {
        let _ = w.eval(&format!("location.href={}", serde_json::to_string(&url).unwrap()));
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
        return Ok(());
    }
    WebviewWindowBuilder::new(&app, "classic", WebviewUrl::External(url.parse().map_err(|e| format!("{e}"))?))
        .title("RotLab (full window)")
        .inner_size(1320.0, 900.0)
        .min_inner_size(760.0, 560.0)
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(windows)]
fn work_area() -> Option<(i32, i32, u32, u32)> {
    use windows_sys::Win32::Foundation::RECT;
    use windows_sys::Win32::UI::WindowsAndMessaging::{SystemParametersInfoW, SPI_GETWORKAREA};
    let mut r = RECT { left: 0, top: 0, right: 0, bottom: 0 };
    let ok = unsafe { SystemParametersInfoW(SPI_GETWORKAREA, 0, &mut r as *mut RECT as *mut _, 0) };
    if ok == 0 || r.right <= r.left || r.bottom <= r.top {
        return None;
    }
    Some((r.left, r.top, (r.right - r.left) as u32, (r.bottom - r.top) as u32))
}

#[cfg(not(windows))]
fn work_area() -> Option<(i32, i32, u32, u32)> {
    None
}

#[cfg(windows)]
fn cursor_and_button() -> Option<(i32, i32, bool)> {
    use windows_sys::Win32::Foundation::POINT;
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON};
    use windows_sys::Win32::UI::WindowsAndMessaging::GetCursorPos;
    let mut p = POINT { x: 0, y: 0 };
    if unsafe { GetCursorPos(&mut p) } == 0 {
        return None;
    }
    let down = unsafe { (GetAsyncKeyState(VK_LBUTTON as i32) as u16 & 0x8000) != 0 || (GetAsyncKeyState(VK_RBUTTON as i32) as u16 & 0x8000) != 0 };
    Some((p.x, p.y, down))
}

#[cfg(not(windows))]
fn cursor_and_button() -> Option<(i32, i32, bool)> {
    None
}

/// Let the mouse through everywhere except over the parts the page reported.
fn click_through(w: WebviewWindow, sh: Shared) {
    let mut ignoring = true;
    let _ = w.set_ignore_cursor_events(true);
    loop {
        std::thread::sleep(Duration::from_millis(16));
        let Some((cx, cy, down)) = cursor_and_button() else { continue };
        let Ok(origin) = w.outer_position() else { continue };
        let inside = {
            let h = sh.lock().unwrap();
            let s = if h.scale > 0.0 { h.scale } else { 1.0 };
            let x = (cx - origin.x) as f64 / s;
            let y = (cy - origin.y) as f64 / s;
            h.rects.iter().any(|r| x >= r[0] && y >= r[1] && x < r[0] + r[2] && y < r[1] + r[3])
        };
        // while a button is held (dragging the TV, selecting text) keep the window listening
        let want_ignore = !inside && !(down && !ignoring);
        if want_ignore != ignoring {
            ignoring = want_ignore;
            let _ = w.set_ignore_cursor_events(ignoring);
        }
    }
}

fn main() {
    let shared: Shared = Arc::new(Mutex::new(Hit { rects: vec![], scale: 1.0 }));
    let sh2 = shared.clone();
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("tv") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .manage(shared)
        .invoke_handler(tauri::generate_handler![region, ready, minimize, close, on_top, classic])
        .setup(move |app| {
            let extra = arg("--query").unwrap_or_default();
            let url = format!("http://localhost:{}/tv?float=2{}", port(), extra);
            let on_top = !std::env::args().any(|a| a == "--not-on-top");
            let w = WebviewWindowBuilder::new(app, "tv", WebviewUrl::External(url.parse()?))
                .title("RotLab TV")
                .transparent(true)
                .decorations(false)
                .shadow(false)
                .resizable(false)
                .always_on_top(on_top)
                .visible(false)
                .build()?;
            if let Some((x, y, ww, hh)) = work_area() {
                w.set_position(PhysicalPosition::new(x, y))?;
                w.set_size(PhysicalSize::new(ww, hh))?;
            } else if let Ok(Some(m)) = w.primary_monitor() {
                w.set_position(*m.position())?;
                w.set_size(*m.size())?;
            }
            w.show()?;
            std::thread::spawn(move || click_through(w, sh2));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("RotLab TV failed to start");
}
