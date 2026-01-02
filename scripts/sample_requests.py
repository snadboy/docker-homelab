#!/usr/bin/env python3
"""
Sample script using the 'requests' library.
Fetches a random joke from an API.
"""

import requests
import json
from datetime import datetime

def main():
    print("=" * 50)
    print("Random Joke Fetcher (using requests library)")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    try:
        # Fetch a random joke from the official joke API
        response = requests.get(
            "https://official-joke-api.appspot.com/random_joke",
            timeout=10
        )
        response.raise_for_status()

        joke = response.json()

        print("Here's a joke for you:")
        print("-" * 30)
        print(f"Setup: {joke.get('setup', 'N/A')}")
        print(f"Punchline: {joke.get('punchline', 'N/A')}")
        print("-" * 30)
        print()
        print("Raw JSON response:")
        print(json.dumps(joke, indent=2))

    except requests.exceptions.RequestException as e:
        print(f"Error fetching joke: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
