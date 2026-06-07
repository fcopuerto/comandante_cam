#!/bin/sh
# Usage: stream-internet.sh <youtube_url> <rtsp_output>
YOUTUBE_URL="$1"
RTSP_OUT="$2"

echo "Internet stream: $YOUTUBE_URL -> $RTSP_OUT"

while true; do
    echo "Resolving stream URL via yt-dlp..."
    URL=$(yt-dlp -f 'best[height<=480][ext=mp4]/best[height<=480]/best' \
        --no-playlist -g "$YOUTUBE_URL" 2>/dev/null) || true

    if [ -z "$URL" ]; then
        echo "yt-dlp: could not resolve stream URL, retrying in 30s"
        sleep 30
        continue
    fi

    echo "Streaming to $RTSP_OUT at 360p/15fps"
    ffmpeg -loglevel warning \
        -re -i "$URL" \
        -c:v libx264 -preset ultrafast -tune zerolatency \
        -vf scale=640:360 -r 15 -g 30 \
        -an \
        -f rtsp -rtsp_transport tcp "$RTSP_OUT" 2>&1 || true

    echo "Stream ended, refreshing URL in 5s..."
    sleep 5
done
