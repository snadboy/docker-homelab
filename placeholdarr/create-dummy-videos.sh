#!/bin/bash

# Create dummy placeholder videos for Placeholdarr
# Run this on the arr host

set -e

echo "Creating dummy video files for Placeholdarr..."

# Create output directory
mkdir -p ~/placeholdarr-dummy

# Create "Not Available" placeholder video
echo "Creating placeholder.mp4..."
docker run --rm -v ~/placeholdarr-dummy:/output jrottenberg/ffmpeg:latest \
  -f lavfi -i color=c=black:s=1920x1080:d=10 \
  -vf "drawtext=text='Content Not Available - Request via Overseerr':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -t 10 /output/placeholder.mp4

# Create "Coming Soon" placeholder video
echo "Creating coming-soon.mp4..."
docker run --rm -v ~/placeholdarr-dummy:/output jrottenberg/ffmpeg:latest \
  -f lavfi -i color=c=black:s=1920x1080:d=10 \
  -vf "drawtext=text='Coming Soon':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -t 10 /output/coming-soon.mp4

echo "Done! Dummy videos created in ~/placeholdarr-dummy/"
ls -lh ~/placeholdarr-dummy/
