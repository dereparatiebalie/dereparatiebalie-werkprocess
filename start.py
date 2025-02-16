import os
import time
import json
import shutil
import subprocess
import http.server
import socketserver
import socket
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

PORT=8000

class Path:
    def __init__(self):
        BASE_DIR = os.path.abspath(os.path.dirname(__file__))
        index_html = "index.html"
        self.dot_dir = os.path.join(BASE_DIR, "diagrams")
        self.source_html = os.path.join(BASE_DIR, index_html)
        self.output_dir = os.path.join(BASE_DIR, "site")
        self.target_html = os.path.join(self.output_dir, index_html)
        
path = Path()

def copy_html():
    """Ensure index.html is in site/"""
    if not os.path.exists(path.target_html) or os.path.getmtime(path.source_html) > os.path.getmtime(path.target_html):
        shutil.copy(path.source_html, path.target_html)
        print(f"✅ Copied {path.source_html} → {path.target_html}")

def generate_file_list():
    """Generate a JSON file listing expected .svg files with timestamps based on the .dot files"""
    file_list = []
    
    for dot_file in os.listdir(path.dot_dir):
        if dot_file.endswith(".dot"):
            svg_file = dot_file.replace(".dot", ".svg")
            svg_path = os.path.join(path.output_dir, svg_file)

            # Get modification time (epoch timestamp) or use 0 if the file doesn't exist
            mtime = int(os.path.getmtime(svg_path)) if os.path.exists(svg_path) else 0

            # Append filename with timestamp
            file_list.append(f"{svg_file}?mtime={mtime}")

    file_list_path = os.path.join(path.output_dir, "files.json")

    with open(file_list_path, "w") as f:
        json.dump(file_list, f)

    print(f"✅ Updated file list with timestamps: {file_list_path}")


class DotFileHandler(PatternMatchingEventHandler):
    """Watch for changes in .dot files and regenerate .svg files"""

    # def __init__(self):
        # super().__init__(patterns=["*.dot"])

    def process(self, file_path):
        """Convert a .dot file to .svg and update files.json"""
        print("Processing filesystem update")

        if file_path.endswith(".dot"):
            svg_file = os.path.join(path.output_dir, os.path.basename(file_path).replace(".dot", ".svg"))
            
            print(f"🔄 Processing {file_path} -> {svg_file}")

            try:
                subprocess.run(["dot", "-Tsvg", file_path, "-o", svg_file], check=True, capture_output=True, text=True)
                generate_file_list()  # Update JSON list after successful conversion
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


class NoCacheHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        """Prevent caching of .svg files"""
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Expires", "0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

def start_http_server():
    """Start a simple HTTP server to serve the site/ directory"""
    os.chdir(path.output_dir)
    handler = NoCacheHTTPRequestHandler

    with socketserver.TCPServer(("", PORT), handler, bind_and_activate=False) as httpd:
        httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ✅ Allow immediate reuse
        httpd.server_bind()
        httpd.server_activate()

        print(f"🌍 Serving at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Shutting down server gracefully...")
            httpd.shutdown()
            httpd.server_close()


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

    generate_file_list()  # Update JSON file after generating all SVGs

def start_file_watcher():
    """Start watching for .dot file changes"""
    print("👀 File watcher started. Monitoring for changes in:", path.dot_dir)

    event_handler = DotFileHandler()
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

    copy_html()

    # Generate all existing .svg files before starting the watcher
    generate_all_svgs()

    # Start file watcher in a separate thread
    watcher_thread = Thread(target=start_file_watcher, daemon=False)
    watcher_thread.start()

    # Start HTTP server
    start_http_server()
