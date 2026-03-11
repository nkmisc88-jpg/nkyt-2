import yt_dlp
import time
import random
import re
import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
from xml.dom import minidom

# ============= CONFIGURATION =============
QUALITY_PROFILES = {
    'hd': {'min_height': 720, 'suffix': '[HD]', 'priority': [1080, 720]},
    'mobile': {'max_height': 480, 'suffix': '[Mobile]', 'priority': [480, 360]},
    'audio': {'format': 'bestaudio', 'suffix': '[Audio]', 'priority': []}
}
# =========================================

class YouTubePlaylistGenerator:
    def __init__(self, cookies_file='cookies.txt'):
        self.cookies_file = cookies_file
        self.cache_file = '.channel_cache.json'
        self.logos_dir = 'logos'
        self.channels_dir = 'channels'
        self.load_cache()

        for directory in [self.logos_dir, self.channels_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

    def load_cache(self):
        try:
            with open(self.cache_file, 'r') as f:
                self.cache = json.load(f)
        except:
            self.cache = {'channels': {}, 'logos': {}}

    def save_cache(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f)

    def safe_filename(self, name):
        safe = re.sub(r'[^\w\s-]', '', name).strip()
        safe = re.sub(r'[-\s]+', '_', safe)
        return safe.lower()

    def detect_channel_country(self, channel_name):
        channel_name_lower = channel_name.lower()
        nigerian = ['nigeria', 'lagos', 'abuja', 'naija', 'channels television', 'arise news', 'nta']
        ghanaian = ['ghana', 'accra', 'tv3 ghana', 'joy news', 'utv ghana']
        
        for k in nigerian:
            if k in channel_name_lower: return 'NG'
        for k in ghanaian:
            if k in channel_name_lower: return 'GH'
        return 'US'

    def fetch_channel_logo(self, channel_id, channel_name):
        logo_path = f"{self.logos_dir}/{channel_id}.jpg"
        if os.path.exists(logo_path): return logo_path
        try:
            if channel_id in self.cache['channels']:
                video_id = self.cache['channels'][channel_id].get('video_id')
                url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                res = requests.get(url, timeout=10)
                if res.status_code == 200:
                    with open(logo_path, 'wb') as f: f.write(res.content)
                    return logo_path
            return None
        except: return None

    def get_stream_info(self, url):
        # Quick pre-check for channel name
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info_pre = ydl.extract_info(url, download=False, process=False)
                channel_name = info_pre.get('channel', '') if info_pre else ''
        except: channel_name = ''

        country = self.detect_channel_country(channel_name)
        
        ydl_opts = {
            'cookies': self.cookies_file if os.path.exists(self.cookies_file) else None,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'socket_timeout': 30,
            'geo_bypass': True,
            'geo_bypass_country': country,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                    'skip': ['webpage', 'configs']
                }
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info: return None

                video_id = info.get('id')
                channel_id = info.get('channel_id', video_id)
                title = info.get('title', 'Unknown')
                channel_name = info.get('channel', 'Unknown')
                
                self.cache['channels'][channel_id] = {
                    'name': channel_name,
                    'video_id': video_id,
                    'last_seen': datetime.now().isoformat()
                }

                # Improved Live Detection
                is_live = info.get('is_live') or info.get('live_status') == 'is_live'
                
                formats = [f for f in info.get('formats', []) if f.get('height') and f.get('url')]
                if not formats: return None
                
                formats.sort(key=lambda x: x['height'], reverse=True)
                
                streams = {}
                # Extract HD (>=720p)
                hd = next((f for f in formats if f['height'] >= 720), formats[0])
                streams['hd'] = {'url': hd['url'], 'quality_tag': f"{hd['height']}p"}
                
                # Extract Mobile (<=480p)
                mobile = next((f for f in formats if f['height'] <= 480), formats[-1])
                streams['mobile'] = {'url': mobile['url'], 'quality_tag': f"{mobile['height']}p"}

                return {
                    'status': 'live' if is_live else 'offline',
                    'video_id': video_id,
                    'channel_id': channel_id,
                    'name': re.sub(r'[^\w\s-]', '', channel_name).strip(),
                    'title': title,
                    'streams': streams,
                    'logo': self.fetch_channel_logo(channel_id, channel_name),
                    'is_live': is_live,
                    'country': country,
                    'channel_url': url
                }
        except Exception as e:
            print(f"  ⚠️ Error extraction: {str(e)[:100]}")
            return None

    def generate_individual_playlists(self, channels_data):
        individual_channels = []
        for ch in channels_data:
            safe_name = self.safe_filename(ch['name'])
            filename = f"{self.channels_dir}/{safe_name}.m3u8"
            
            if ch.get('status') == 'live' and 'streams' in ch:
                stream = ch['streams'].get('hd', list(ch['streams'].values())[0])
                logo_attr = f' tvg-logo="../{ch["logo"]}"' if ch.get('logo') else ''
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"#EXTM3U\n#EXTINF:-1 tvg-id=\"{ch['channel_id']}\"{logo_attr},{ch['name']} 🔴 LIVE\n{stream['url']}\n")
                
                individual_channels.append({
                    'name': ch['name'], 'file': filename, 'quality': stream['quality_tag'], 'status': 'live', 'country': ch['country']
                })
        
        # Save JSON index for web view
        with open(f"{self.channels_dir}/channels.json", 'w') as f:
            json.dump({'channels': individual_channels}, f, indent=2)
        return individual_channels

    def generate_epg(self, channels_data):
        tv = ET.Element("tv")
        for ch in channels_data:
            if ch.get('status') == 'live':
                channel_elem = ET.SubElement(tv, "channel", {"id": ch['channel_id']})
                ET.SubElement(channel_elem, "display-name").text = ch['name']
                if ch.get('logo'): ET.SubElement(channel_elem, "icon", {"src": ch['logo']})
                
                prog = ET.SubElement(tv, "programme", {
                    "start": datetime.now().strftime("%Y%m%d%H%M%S +0000"),
                    "stop": (datetime.now() + timedelta(hours=6)).strftime("%Y%m%d%H%M%S +0000"),
                    "channel": ch['channel_id']
                })
                ET.SubElement(prog, "title").text = ch.get('title', 'Live Stream')
        
        with open('epg.xml', 'w', encoding='utf-8') as f:
            f.write(minidom.parseString(ET.tostring(tv)).toprettyxml(indent="  "))

    def generate_playlists(self, channels_data):
        stats = {'total': len(channels_data), 'live': 0, 'offline': 0, 'qualities': {'1080p': 0, '720p': 0, '480p': 0}}
        m3u_content = ["#EXTM3U", f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"]

        for ch in channels_data:
            logo_attr = f' tvg-logo="{ch["logo"]}"' if ch.get('logo') else ''
            if ch.get('status') == 'live':
                stats['live'] += 1
                stream = ch['streams'].get('hd')
                q = stream['quality_tag']
                if '1080' in q: stats['qualities']['1080p'] += 1
                elif '720' in q: stats['qualities']['720p'] += 1
                else: stats['qualities']['480p'] += 1
                
                m3u_content.append(f'#EXTINF:-1 tvg-id="{ch["channel_id"]}"{logo_attr} group-title="Live",{ch["name"]} [{q}]')
                m3u_content.append(stream['url'])
            else:
                stats['offline'] += 1

        with open('streams.m3u8', 'w', encoding='utf-8') as f: f.write('\n'.join(m3u_content))
        with open('stats.json', 'w') as f: json.dump(stats, f)
        return stats

def main():
    if not os.path.exists('streams.txt'): return
    with open('streams.txt', 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    gen = YouTubePlaylistGenerator()
    results = []
    for url in urls:
        print(f"📡 Processing: {url}")
        info = gen.get_stream_info(url)
        if info: results.append(info)
        time.sleep(2)

    gen.generate_epg(results)
    gen.generate_playlists(results)
    gen.generate_individual_playlists(results)
    gen.save_cache()
    print("✅ All done!")

if __name__ == "__main__":
    main()
