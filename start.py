import os
import time
import json
import shutil
import subprocess
import http.server
import socketserver
import socket
import asyncio
import websockets
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

PORT = 8000
WEBSOCKET_PORT = 8765


class Path:
    """Manages directory paths"""
    def __init__(self):
        BASE_DIR = os.path.abspath(os.path.dirname(__file__))
        index_html = "index.html"
        self.dot_dir = os.path.join(BASE_DIR, "diagrams")
        self.source_html = os.path.join(BASE_DIR, index_html)
        self.output_dir = os.path.join(BASE_DIR, "site")
        self.target_html = os.path.join(self.output_dir, index_html)

path = Path()


class WebSocketServer:
    """Manages WebSocket connections and updates"""
    def __init__(self):
        self.connected_clients = set()
        self.loop = None

    async def websocket_handler(self, websocket):
        """Handles new WebSocket connections from clients"""
        print("🟢 WebSocket client connected")
        self.connected_clients.add(websocket)
        try:
            async for _ in websocket:
                pass  # WebSocket stays open until the client disconnects
        except websockets.exceptions.ConnectionClosed as e:
            print(f"🔴 WebSocket closed: {e}")
        finally:
            self.connected_clients.remove(websocket)
            print("🔴 WebSocket client removed")

    async def notify_clients(self):
        """Send an update message to all connected WebSocket clients"""
        if self.connected_clients:
            message = "update"
            disconnected_clients = set()
            for ws in self.connected_clients:
                try:
                    await ws.send(message)
                except websockets.exceptions.ConnectionClosed:
                    print("🔴 Client disconnected, removing from list")
                    disconnected_clients.add(ws)

            for ws in disconnected_clients:
                self.connected_clients.remove(ws)

    def start_websocket_server(self):
        """Start the WebSocket server inside a separate thread with its own event loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        async def run_server():
            """Runs the WebSocket server inside the event loop."""
            async with websockets.serve(self.websocket_handler, "localhost", WEBSOCKET_PORT):
                print(f"📡 WebSocket server started on ws://localhost:{WEBSOCKET_PORT}")
                await asyncio.Future()  # Keeps the server running forever

        self.loop.run_until_complete(run_server())
        self.loop.run_forever()
        self.loop.close()


class FileManager:
    """Handles file operations for .dot and .svg files"""
    @staticmethod
    def copy_html():
        """Ensure index.html is in site/"""
        if not os.path.exists(path.target_html) or os.path.getmtime(path.source_html) > os.path.getmtime(path.target_html):
            shutil.copy(path.source_html, path.target_html)
            print(f"✅ Copied {path.source_html} → {path.target_html}")

    @staticmethod
    def generate_file_list():
        """Generate a JSON file listing expected .svg files with timestamps based on the .dot files"""
        file_list = []
        for dot_file in os.listdir(path.dot_dir):
            if dot_file.endswith(".dot"):
                svg_file = dot_file.replace(".dot", ".svg")
                svg_path = os.path.join(path.output_dir, svg_file)
                mtime = int(os.path.getmtime(svg_path)) if os.path.exists(svg_path) else 0
                file_list.append(f"{svg_file}?mtime={mtime}")

        file_list_path = os.path.join(path.output_dir, "files.json")
        with open(file_list_path, "w") as f:
            json.dump(file_list, f)
        print(f"✅ Updated file list with timestamps: {file_list_path}")

    @staticmethod
    def generate_all_svgs():
        """Convert all existing .dot files to .svg and generate the file list"""
        for file in os.listdir(path.dot_dir):
            if file.endswith(".dot"):
                dot_path = os.path.join(path.dot_dir, file)
                svg_path = os.path.join(path.output_dir, file.replace(".dot", ".svg"))
                print(f"🖼️ Generating {svg_path}")
                try:
                    subprocess.run(["dot", "-Tsvg", dot_path, "-o", svg_path], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    print(f"\n❌ Error processing {dot_path}:")
                    print(e.stderr)
        FileManager.generate_file_list()


class DotFileHandler(PatternMatchingEventHandler):
    """Watch for changes in .dot files and regenerate .svg files"""
    def __init__(self, websocket_server):
        super().__init__()
        self.websocket_server = websocket_server

    def process(self, file_path):
        """Convert a .dot file to .svg and update files.json"""
        print("Processing filesystem update")

        if file_path.endswith(".dot"):
            svg_file = os.path.join(path.output_dir, os.path.basename(file_path).replace(".dot", ".svg"))
            print(f"🔄 Processing {file_path} -> {svg_file}")

            try:
                subprocess.run(["dot", "-Tsvg", file_path, "-o", svg_file], check=True, capture_output=True, text=True)
                FileManager.generate_file_list()
                if self.websocket_server.loop:
                    asyncio.run_coroutine_threadsafe(self.websocket_server.notify_clients(), self.websocket_server.loop)

            except subprocess.CalledProcessError as e:
                print(f"\n❌ Error processing {file_path}:")
                print(e.stderr)

    def on_modified(self, event):
        print("on_modified")
        if not event.is_directory:
            self.process(event.src_path)

    def on_created(self, event):
        print("on_created")
        if not event.is_directory:
            self.process(event.src_path)


class Server:
    """Manages HTTP and file watcher servers"""
    def __init__(self, websocket_server):
        self.websocket_server = websocket_server

    def start_http_server(self):
        """Start a simple HTTP server to serve the site/ directory"""
        os.chdir(path.output_dir)
        handler = http.server.SimpleHTTPRequestHandler

        with socketserver.TCPServer(("", PORT), handler, bind_and_activate=False) as httpd:
            httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            httpd.server_bind()
            httpd.server_activate()

            print(f"🌍 Serving at http://localhost:{PORT}")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n🛑 Shutting down server gracefully...")
                httpd.shutdown()
                httpd.server_close()

    def start_file_watcher(self):
        """Start watching for .dot file changes"""
        print("👀 File watcher started. Monitoring for changes in:", path.dot_dir)
        event_handler = DotFileHandler(self.websocket_server)
        observer = Observer()
        observer.schedule(event_handler, path=path.dot_dir, recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        print("👀 File watcher stopped")
        observer.join()


if __name__ == "__main__":
    # Ensure the output directory exists
    os.makedirs(path.output_dir, exist_ok=True)

    FileManager.copy_html()
    FileManager.generate_all_svgs()

    websocket_server = WebSocketServer()
    server = Server(websocket_server)

    watcher_thread = Thread(target=server.start_file_watcher, daemon=True)
    watcher_thread.start()

    websocket_thread = Thread(target=websocket_server.start_websocket_server, daemon=True)
    websocket_thread.start()

    server.start_http_server()
