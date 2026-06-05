#!/usr/bin/env python3
import argparse
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the Vartalap browser client")
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    print(f"Opening {args.url}")
    webbrowser.open(args.url)


if __name__ == "__main__":
    main()
