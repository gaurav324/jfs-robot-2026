#!/usr/bin/env python3
"""
BIOGLOW Robot Lab Simulator — launcher.

Usage:
    python3 run.py                 # start on http://127.0.0.1:8000 and open a browser
    python3 run.py --port 9000     # use a different port
    python3 run.py --no-browser    # don't open a browser automatically

No installation or dependencies required — just Python 3.8+.
"""

import argparse
import sys
import threading
import webbrowser

from fll_sim.server import serve


def main():
    parser = argparse.ArgumentParser(description="FLL BIOGLOW Robot Lab Simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # Find a free port if the requested one is taken.
    import socket
    port = args.port
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((args.host, port)) != 0:
                break
        port += 1

    httpd = serve(args.host, port)
    url = "http://%s:%d/" % (args.host, port)

    print("=" * 60)
    print("  BIOGLOW Robot Lab Simulator")
    print("  Open:  %s" % url)
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down. Bye!")
        httpd.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
