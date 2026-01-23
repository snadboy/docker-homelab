# Placeholdarr Setup Guide

## Overview

Set up Placeholdarr to create phantom/placeholder entries in Plex for:
1. **Missing episodes** - Episodes that exist but aren't downloaded (show as "Request")
2. **Upcoming episodes** - Episodes that haven't aired yet (show as "Coming Soon")

This integrates with the existing media stack (Sonarr, Overseerr, Plex) and runs alongside Agregarr which handles collections.

## Project Repository

- **GitHub:** https://github.com/TheIndieArmy/placeholdarr
- **Documentation:** See README in repository for latest configuration options

## Goals

- Create placeholder video files for missing TV episodes in Sonarr
- Create placeholder video files for upcoming/unaired episodes from Sonarr calendar
- Display status in Plex (e.g., "Request", "Searching...", "Coming Soon")
- Allow users to request missing episodes via Overseerr
- Automatically update statuses as episodes move through the download queue

## Prerequisites

The following services should already be running and accessible:
- Sonarr (TV show management)
- Plex (media server)
- Overseerr (request management)
- Existing Docker/Docker Compose infrastructure

## Directory Structure

Create dedicated placeholder directories that will be:
- Added to Plex libraries
- **NOT** added to Sonarr (Sonarr should not manage these folders)

```bash
# Create placeholder directories
mkdir -p /mnt/media/placeholders/tv
mkdir -p /mnt/media/placeholders/movies  # Optional, if also doing movies

# Create config directory for Placeholdarr
mkdir -p /path/to/configs/placeholdarr
```

Adjust paths based on the actual media storage layout.

## Docker Compose Configuration

Add Placeholdarr to the existing docker-compose setup:

```yaml
services:
  placeholdarr:
    image: theindearmy/placeholdarr:latest
    container_name: placeholdarr
    restart: unless-stopped
    environment:
      # Plex Configuration
      - PLEX_URL=http://plex:32400  # Adjust to actual Plex URL
      - PLEX_TOKEN=your_plex_token_here
      - PLEX_TV_SECTION_ID=2  # Get from Plex library settings
      - PLEX_MOVIE_SECTION_ID=1  # Optional, for movies
      
      # Sonarr Configuration
      - SONARR_URL=http://sonarr:8989  # Adjust to actual Sonarr URL
      - SONARR_API_KEY=your_sonarr_api_key_here
      
      # Radarr Configuration (Optional - for movies)
      # - RADARR_URL=http://radarr:7878
      # - RADARR_API_KEY=your_radarr_api_key_here
      
      # Overseerr Configuration
      - OVERSEERR_URL=http://overseerr:5055  # Adjust to actual Overseerr URL
      - OVERSEERR_API_KEY=your_overseerr_api_key_here
      
      # Calendar/Coming Soon Settings
      - CALENDAR_LOOKAHEAD_DAYS=14
      - CALENDAR_PLACEHOLDER_MODE=episode  # "episode" or "season"
      - ENABLE_COMING_SOON=true
      
      # Placeholder File Paths (inside container)
      - DUMMY_FILE_PATH=/dummy/placeholder.mp4
      - COMING_SOON_DUMMY_FILE_PATH=/dummy/coming-soon.mp4  # Optional different video
      
      # Placeholder Output Paths
      - TV_PLACEHOLDER_PATH=/placeholders/tv
      - MOVIE_PLACEHOLDER_PATH=/placeholders/movies
      
      # Sync Intervals (in minutes)
      - CALENDAR_SYNC_INTERVAL=60
      - QUEUE_SYNC_INTERVAL=5
      
      # Timezone
      - TZ=America/Chicago  # Adjust to local timezone
      
    volumes:
      # Placeholder output directories
      - /mnt/media/placeholders/tv:/placeholders/tv
      - /mnt/media/placeholders/movies:/placeholders/movies
      
      # Dummy video files (create these or mount existing)
      - /path/to/configs/placeholdarr/dummy:/dummy
      
      # Config persistence
      - /path/to/configs/placeholdarr:/config
```

## Dummy Video Files

Placeholdarr needs dummy video files to use as placeholders. Create simple MP4 files:

**Option 1:** Create with FFmpeg
```bash
# Basic placeholder (black screen with text)
ffmpeg -f lavfi -i color=c=black:s=1920x1080:d=10 -vf "drawtext=text='Content Not Available - Use Overseerr to Request':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" -c:v libx264 -t 10 placeholder.mp4

# Coming soon variant
ffmpeg -f lavfi -i color=c=black:s=1920x1080:d=10 -vf "drawtext=text='Coming Soon':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" -c:v libx264 -t 10 coming-soon.mp4
```

**Option 2:** Use any short MP4 video file as the placeholder

Place these files in the dummy video mount path (e.g., `/path/to/configs/placeholdarr/dummy/`).

## Plex Library Configuration

After Placeholdarr is running:

1. In Plex, edit your TV library settings
2. Add the placeholder TV folder (`/mnt/media/placeholders/tv`) as an additional folder
3. The placeholder folder should be alongside your real media folder in the same library
4. Run a library scan

**Important:** Plex will now show both real episodes and placeholder episodes. Placeholdarr updates the summary/description field with status information.

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `PLEX_URL` | Plex server URL | `http://192.168.1.100:32400` |
| `PLEX_TOKEN` | Plex authentication token | Get from Plex XML or browser dev tools |
| `PLEX_TV_SECTION_ID` | Plex TV library section ID | `2` |
| `SONARR_URL` | Sonarr URL | `http://192.168.1.100:8989` |
| `SONARR_API_KEY` | Sonarr API key | Found in Sonarr Settings → General |
| `OVERSEERR_URL` | Overseerr URL | `http://192.168.1.100:5055` |
| `OVERSEERR_API_KEY` | Overseerr API key | Found in Overseerr Settings |
| `CALENDAR_LOOKAHEAD_DAYS` | Days ahead to create coming soon placeholders | `14` |
| `CALENDAR_PLACEHOLDER_MODE` | Create per episode or entire season | `episode` or `season` |
| `ENABLE_COMING_SOON` | Enable coming soon placeholders | `true` or `false` |
| `TV_PLACEHOLDER_PATH` | Container path for TV placeholders | `/placeholders/tv` |
| `CALENDAR_SYNC_INTERVAL` | Minutes between calendar syncs | `60` |
| `QUEUE_SYNC_INTERVAL` | Minutes between queue status checks | `5` |

## Getting API Keys and Tokens

### Plex Token
1. Sign into Plex web app
2. Open browser dev tools (F12)
3. Go to any media item
4. Look in Network tab for requests containing `X-Plex-Token`

Or use: https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/

### Plex Library Section ID
1. In Plex, go to your TV library
2. Look at the URL: `https://app.plex.tv/desktop#!/media/xxx/com.plexapp.plugins.library?source=2`
3. The `source=2` indicates section ID is `2`

### Sonarr API Key
Settings → General → Security → API Key

### Overseerr API Key
Settings → General → API Key

## Status Indicators

Placeholdarr prepends status to the episode summary/description in Plex:

- **"Request"** - Episode is available but not downloaded, user can request
- **"Searching..."** - Sonarr is actively searching for the episode
- **"Downloading..."** - Episode is currently downloading
- **"Coming Soon"** - Episode hasn't aired yet

## Integration Notes

### Agregarr Compatibility
- Placeholdarr and Agregarr serve different purposes and don't conflict
- Agregarr: Manages collections and lists
- Placeholdarr: Creates episode-level placeholders
- Both can run simultaneously

### Overseerr Considerations
- Users can request missing episodes through Overseerr as normal
- Placeholdarr will update the status as the request progresses

### Maintainerr Integration (Optional)
If using Maintainerr for storage management:
- Enable "On File Delete" webhook trigger in Sonarr
- Placeholdarr can recreate placeholders when real files are deleted
- Keeps content visible for re-requesting

## Verification Steps

After setup, verify:

1. [ ] Placeholdarr container starts without errors
2. [ ] Check container logs: `docker logs placeholdarr`
3. [ ] Placeholder files appear in `/mnt/media/placeholders/tv/`
4. [ ] Plex shows placeholder episodes with status in description
5. [ ] Upcoming episodes show "Coming Soon" status
6. [ ] Missing episodes show "Request" status
7. [ ] Requesting via Overseerr updates the status

## Troubleshooting

**No placeholders appearing:**
- Check container logs for API connection errors
- Verify API keys are correct
- Ensure Sonarr has shows with missing episodes

**Plex not showing placeholders:**
- Verify placeholder folder is added to Plex library
- Run a manual library scan
- Check file permissions on placeholder directory

**Status not updating:**
- Check `QUEUE_SYNC_INTERVAL` setting
- Verify Overseerr/Sonarr webhooks if configured

## File Logging

Consider adding a log volume for debugging:
```yaml
volumes:
  - /path/to/configs/placeholdarr/logs:/app/logs
```

## Additional Resources

- Placeholdarr GitHub: https://github.com/TheIndieArmy/placeholdarr
- Sonarr Wiki: https://wiki.servarr.com/sonarr
- Overseerr Docs: https://docs.overseerr.dev/
