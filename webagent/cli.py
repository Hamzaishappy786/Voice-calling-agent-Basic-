#!/usr/bin/env python3
"""CLI entrypoint for WebAgent voice call assistant."""

import argparse
import sys
import threading
import time
import webbrowser
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="WebAgent — Real-Time Voice Assistant & Web Client"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to bind server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run server on (default: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open web browser at launch",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    print("=" * 60)
    print(" 🎙️  WebAgent — Real-Time Voice Assistant")
    print(f" 🌐 Running on: {url}")
    print("=" * 60)

    if not args.no_browser:
        def open_browser():
            time.sleep(1.2)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        uvicorn.run(
            "webagent.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
