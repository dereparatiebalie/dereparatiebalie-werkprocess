import os
import time
import subprocess
import http.server
import socketserver
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Directory paths
DOT_DIR = "."       # Where .dot files are located
OUTPUT_DIR = "site" # Where .svg files should be stored

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

class DotFileHandler(FileSystemEventHandler):
    """Watch for changes in .dot files and regenerate .svg files"""

    def process(self, file_path):
        """Convert a .dot file to .svg and save it in site/ directory"""
        if file_path.endswith(".dot"):
            svg_file = os.path.join(OUTPUT_DIR, os.path.basename(file_path).replace(".dot", ".svg"))
            print(f"Processing {file_path} -> {svg_file}")

            try:
                subprocess.run(["dot", "-Tsvg", file_path, "-o", svg_file], check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"\n❌ Error processing {file_path}:")
                print(e.stderr)

    def on_modified(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.process(event.src_path)

def generate_all_svgs():
    """Convert all existing .dot files to .svg"""
    for file in os.listdir(DOT_DIR):
        if file.endswith(".dot"):
            dot_path = os.path.join(DOT_DIR, file)
            svg_path = os.path.join(OUTPUT_DIR, file.replace(".dot", ".svg"))
            print(f"Generating {svg_path}")
            try:
                subprocess.run(["dot", "-Tsvg", dot_path, "-o", svg_path], check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"\n❌ Error processing {dot_path}:")
                print(e.stderr)

def start_file_watcher():
    """Start watching for .dot file changes"""
    event_handler = DotFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=DOT_DIR, recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def start_http_server(port=8000):
    """Start a simple HTTP server to serve the site/ directory"""
    os.chdir(OUTPUT_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🌍 Serving at http://localhost:{port}")
        httpd.serve_forever()

if __name__ == "__main__":
    from threading import Thread

    # Generate all existing .svg files before starting the watcher
    generate_all_svgs()

    # Start file watcher in a separate thread
    watcher_thread = Thread(target=start_file_watcher, daemon=True)
    watcher_thread.start()

    # Start HTTP server
    start_http_server()