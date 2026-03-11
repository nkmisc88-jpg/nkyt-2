import yt_dlp
import time
import random
import re
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
from xml.dom import minidom

class YouTubePlaylistGenerator:
    def __init__(self, cookies_file='cookies.txt'):
        self.cookies_file = cookies_file
        self.cache_file = '.channel_cache.json'
        self.logos_dir = 'logos'
        self.channels_dir = 'channels'
        
        for d in [self.logos_dir, self.channels_dir]:
            if not os.path.exists(d): os.makedirs(d)
        
        try:
            with open(self.cache_file, 'r') as f: self.cache = json.load(f)
        except: self.cache = {'channels': {}}

    def detect_country(self, name):
        name = name.lower()
        if any(x in name for x in ['nigeria', 'naija', 'lagos', 'channels tv', 'arise']): return 'NG'
        if any(x in name for x in ['ghana', 'accra', 'tv3', 'joy news']): return 'GH'
        return 'US'

    def get_stream_info(self, url):
        country = 'US' # Default
        
        # Two attempts: Try Cookies first, then Anonymous Fallback
        attempts = [
            {'name': 'Cookie Mode', 'use_cookies': True},
            {'name': 'Anonymous (WARP) Mode', 'use_cookies': False}
        ]

        for attempt in attempts:
            cookie_path = self.cookies_file if (attempt['use_cookies'] and os.path.exists(self.cookies_file)) else None
            print(f"    🔄 Trying {attempt['name']}...")

            ydl_opts = {
                'cookies': cookie_path,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'socket_timeout': 20,
                'geo_bypass': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'web'], 'skip': ['webpage', 'configs']}}
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info: continue

                    # Update country based on real channel name
                    country = self.detect_country(info.get('channel', ''))
                    
                    formats = [f for f in info.get('formats', []) if f.get('height') and f.get('url')]
                    if not formats: continue
                    formats.sort(key=lambda x: x['height'], reverse=True)

                    hd = next((f for f in formats if f['height'] >= 720), formats[0])
                    print(f"    ✅ Success: Found {hd['height']}p stream")
                    
                    return {
                        'id': info.get('channel_id', info.get('id')),
                        'name': re.sub(r'[^\w\s-]', '', info.get('channel', 'Unknown')).strip(),
                        'title': info.get('title', 'Live Stream'),
                        'url': hd['url'],
                        'quality': f"{hd['height']}p",
                        'country': country,
                        'status': 'live' if info.get('is_live') else 'offline'
                    }
            except Exception as e:
                print(f"    ⚠️ {attempt['name']} failed: {str(e)[:50]}")
                continue
        return None

    def run(self, input_file):
        if not os.path.exists(input_file): return
        with open(input_file, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        results = []
        for url in urls:
            print(f"\n📺 Processing: {url}")
            data = self.get_stream_info(url)
            if data: results.append(data)
            time.sleep(2)

        # Generate Main M3U8
        m3u = ["#EXTM3U", f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"]
        for ch in results:
            if ch['status'] == 'live':
                m3u.append(f'#EXTINF:-1 tvg-id="{ch["id"]}" group-title="{ch["country"]}",{ch["name"]} [{ch["quality"]}]')
                m3u.append(ch['url'])
        
        with open('streams.m3u8', 'w', encoding='utf-8') as f: f.write('\n'.join(m3u))
        
        # Generate Stats
        stats = {'total': len(urls), 'live': len([x for x in results if x['status'] == 'live'])}
        with open('stats.json', 'w') as f: json.dump(stats, f, indent=2)
        print(f"\n📊 Final: {stats['live']}/{stats['total']} channels live.")

if __name__ == "__main__":
    generator = YouTubePlaylistGenerator()
    generator.run('streams.txt')
