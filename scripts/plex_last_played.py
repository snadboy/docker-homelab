#!/app/venv/bin/python3
"""
Plex Last Played Movies
Fetches the last 3 movies played from Plex server

Uses venv with requests library
"""
import requests
import json
from datetime import datetime

# Plex configuration
PLEX_URL = "http://192.168.86.40:32400"
PLEX_TOKEN = "js1SqwFxuN2eirNGdeox"

def get_headers():
    """Return headers for Plex API requests"""
    return {
        'Accept': 'application/json',
        'X-Plex-Token': PLEX_TOKEN
    }

def get_last_played_movies(count=3):
    """Get the last played movies from Plex history"""
    # Try history endpoint first
    url = f"{PLEX_URL}/status/sessions/history/all"
    params = {
        'sort': 'viewedAt:desc',
        'librarySectionID': 1,  # Movies library
        'limit': count,
        'X-Plex-Token': PLEX_TOKEN
    }

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        movies = []
        if 'MediaContainer' in data and 'Metadata' in data['MediaContainer']:
            for item in data['MediaContainer']['Metadata'][:count]:
                viewed_at = item.get('viewedAt', 0)
                viewed_date = datetime.fromtimestamp(viewed_at).strftime('%Y-%m-%d %H:%M') if viewed_at else 'Unknown'

                movies.append({
                    'title': item.get('title', 'Unknown'),
                    'year': item.get('year', ''),
                    'viewed_at': viewed_date,
                    'user': item.get('User', {}).get('title', 'Unknown')
                })
        return movies

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return get_last_played_alternative(count)
        raise

def get_last_played_alternative(count=3):
    """Alternative: use recentlyViewed endpoint"""
    url = f"{PLEX_URL}/library/sections/1/recentlyViewed"
    params = {'X-Plex-Token': PLEX_TOKEN}

    response = requests.get(url, headers=get_headers(), params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    movies = []
    if 'MediaContainer' in data and 'Metadata' in data['MediaContainer']:
        for item in data['MediaContainer']['Metadata'][:count]:
            last_viewed = item.get('lastViewedAt', 0)
            viewed_date = datetime.fromtimestamp(last_viewed).strftime('%Y-%m-%d %H:%M') if last_viewed else 'Unknown'

            movies.append({
                'title': item.get('title', 'Unknown'),
                'year': item.get('year', ''),
                'viewed_at': viewed_date,
                'user': 'N/A'
            })
    return movies

def main():
    print("=" * 60)
    print("Plex - Last 3 Movies Played")
    print("=" * 60)
    print(f"Server: {PLEX_URL}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

    try:
        movies = get_last_played_movies(3)

        if not movies:
            print("No recently played movies found.")
        else:
            for i, movie in enumerate(movies, 1):
                year_str = f" ({movie['year']})" if movie['year'] else ""
                print(f"\n{i}. {movie['title']}{year_str}")
                print(f"   Watched: {movie['viewed_at']}")
                if movie['user'] != 'N/A':
                    print(f"   User: {movie['user']}")

        print("\n" + "-" * 60)
        print("JSON Output:")
        print(json.dumps(movies, indent=2))

    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to Plex server")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
