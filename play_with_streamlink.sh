#!/bin/bash
# Streamlink Player for Nigeria News

PLAYLIST="https://raw.githubusercontent.com/uticap/Youtube-to-M3u8/main/streams.m3u8"
QUALITY="${1:-best}"

echo "📺 Nigeria News Streams"
echo "======================="
echo "Usage: ./play_with_streamlink.sh [quality]"
echo "Quality options: best, 1080p, 720p, 480p"
echo ""
echo "Available channels will be listed from the playlist"
echo ""

streamlink --player="vlc" "$PLAYLIST" "$QUALITY"
