# Placeholdarr Setup

## Quick Start

This setup creates episode-level placeholders for missing and upcoming TV episodes in Plex.

### 1. Get Plex Token

Get your Plex authentication token:

**Method 1: From Plex Web App**
1. Sign into Plex web app at https://app.plex.tv
2. Open browser dev tools (F12)
3. Go to Network tab
4. Click on any media item
5. Look for requests containing `X-Plex-Token` parameter

**Method 2: From Agregarr Config**
```bash
ssh snadboy@arr "docker exec agregarr cat /app/config/settings.json" | jq -r '.plex.token // empty'
```

### 2. Create .env File

```bash
cp .env.example .env
# Edit .env and add your Plex token
```

### 3. Create Dummy Video Files

SSH to arr host and create placeholder videos:

```bash
ssh snadboy@arr

# Create directory for dummy files (if using bind mount instead of volume)
mkdir -p ~/placeholdarr-dummy

# Create placeholder video (requires ffmpeg)
docker run --rm -v ~/placeholdarr-dummy:/output jrottenberg/ffmpeg:latest \
  -f lavfi -i color=c=black:s=1920x1080:d=10 \
  -vf "drawtext=text='Content Not Available - Request via Overseerr':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -t 10 /output/placeholder.mp4

# Create coming soon video
docker run --rm -v ~/placeholdarr-dummy:/output jrottenberg/ffmpeg:latest \
  -f lavfi -i color=c=black:s=1920x1080:d=10 \
  -vf "drawtext=text='Coming Soon':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -t 10 /output/coming-soon.mp4
```

**Alternative:** Use any short MP4 video as placeholder files.

### 4. Deploy to arr via Portainer

The stack will be deployed via Portainer from the GitHub repository.

### 5. Add Placeholder Folder to Plex

After deployment:
1. In Plex, edit your **TV Shows** library settings
2. Click "Add Folder"
3. Add `/mnt/media/placeholders/tv` as an additional library folder
4. Run a library scan

The placeholder folder should be alongside your real media folder in the same library.

## Configuration

### Placeholder Directories Created
- `/mnt/media/placeholders/tv` - TV episode placeholders
- `/mnt/media/placeholders/movies` - Movie placeholders (optional)

### Current Settings
- **Calendar Lookahead:** 30 days
- **Placeholder Mode:** Per-episode
- **Coming Soon:** Enabled
- **Calendar Sync:** Every 60 minutes
- **Queue Sync:** Every 5 minutes

## How It Works

1. **Placeholdarr** syncs with Sonarr to find:
   - Missing episodes (exist but not downloaded)
   - Upcoming episodes (not yet aired)

2. Creates dummy video files in `/mnt/media/placeholders/tv/` with Plex-friendly naming

3. **Plex scans** the placeholder folder and shows the episodes

4. **Episode descriptions** show status:
   - "Request" - Available but not downloaded
   - "Searching..." - Sonarr is searching
   - "Downloading..." - Currently downloading
   - "Coming Soon" - Not yet aired

5. Users can request via **Overseerr** as normal

## Verification

After deployment:
```bash
# Check container is running
ssh snadboy@arr "docker ps | grep placeholdarr"

# Check logs
ssh snadboy@arr "docker logs placeholdarr"

# Verify placeholder files are created
ssh snadboy@arr "ls -la /mnt/media/placeholders/tv/ | head -20"
```

## Compatibility with Agregarr

- **Agregarr:** Creates collections with visual overlays, manages lists
- **Placeholdarr:** Creates individual episode placeholders with status in descriptions
- Both work together - Agregarr for collections, Placeholdarr for episode-level visibility

## Troubleshooting

**No placeholders appearing:**
- Check container logs for API errors
- Verify API keys and Plex token are correct
- Ensure Sonarr has monitored shows with missing episodes

**Plex not showing placeholders:**
- Verify `/mnt/media/placeholders/tv` is added to Plex TV library
- Run manual library scan in Plex
- Check file permissions on placeholder directory
