fn main() {
    // declare our commands so the page (served by RotLab on localhost) can be allowed to call them
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["region", "ready", "minimize", "close", "on_top", "classic"]),
    ))
    .expect("failed to run tauri-build");
}
