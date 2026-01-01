#!/usr/bin/env python3
"""
Simple test script - no external dependencies
"""
import datetime
import os
import json
import socket

def main():
    print("=" * 50)
    print("Test Script Running")
    print("=" * 50)

    # Basic info
    print(f"Timestamp: {datetime.datetime.now().isoformat()}")
    print(f"Hostname: {socket.gethostname()}")
    print(f"Python: {os.popen('python3 --version').read().strip()}")

    # Environment check
    print("\nEnvironment Variables (sample):")
    for key in ['HOME', 'USER', 'PATH', 'TZ']:
        print(f"  {key}: {os.environ.get(key, 'not set')}")

    # Simple computation
    print("\nSimple test computation:")
    result = sum(range(1, 101))
    print(f"  Sum of 1-100: {result}")

    # Output some JSON (useful for APIs later)
    output = {
        "status": "success",
        "timestamp": datetime.datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "test_result": result
    }
    print("\nJSON Output:")
    print(json.dumps(output, indent=2))

    print("\n" + "=" * 50)
    print("Script completed successfully!")
    print("=" * 50)

if __name__ == "__main__":
    main()
