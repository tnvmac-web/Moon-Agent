"""
Desktop app using PyWebView - wraps the web UI in a native window.
"""
import os
import sys
import threading
import time
import webview
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from web.server import run_server


def start_web_server():
    """Start the FastAPI server in a background thread"""
    settings = get_settings()
    run_server(host=settings.settings.web.host, port=settings.settings.web.port)


def create_desktop_app():
    """Create and run the desktop application"""
    settings = get_settings()

    # Start web server in background
    server_thread = threading.Thread(target=start_web_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    time.sleep(2)

    # Create webview window
    window = webview.create_window(
        title=settings.settings.desktop.title,
        url=f"http://{settings.settings.web.host}:{settings.settings.web.port}",
        width=settings.settings.desktop.width,
        height=settings.settings.desktop.height,
        min_size=(800, 600),
        text_select=True,
        zoomable=True,
        draggable=True,
        resizable=True,
        frameless=False,
        easy_drag=True,
        on_top=False,
        shadow=True,
        focus=True,
        hidden=False,
        minimized=False,
        maximized=False,
        fullscreen=False,
    )

    # Start the webview event loop
    webview.start(debug=settings.settings.desktop.debug)


if __name__ == "__main__":
    create_desktop_app()