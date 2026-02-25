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
        self.load_cache()
        
        # Create logos directory
        if not os.path.exists(self.logos_dir):
            os.makedirs(self.logos_dir)
    
    def load_cache(self):
        """Load cached channel data"""
        try:
            with open(self.cache_file, 'r') as f:
                self.cache = json.load(f)
        except:
            self.cache = {'channels': {}, 'logos': {}}
    
    def save_cache(self):
        """Save channel data to cache"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f)
    
    def fetch_channel_logo(self, channel_id, channel_name):
        """Fetch and cache channel logo"""
        logo_path = f"{self.logos_dir}/{channel_id}.jpg"
        
        # Check if logo already exists and is recent (< 7 days old)
        if os.path.exists(logo_path):
            file_age = time.time() - os.path.getmtime(logo_path)
            if file_age < 604800:  # 7 days
                return logo_path
        
        # Try to fetch logo
        try:
            # Try different thumbnail qualities
            qualities = ['maxresdefault', 'sddefault', 'hqdefault', 'mqdefault']
            base_url = "https://i.ytimg.com/vi/{}/{}.jpg"
            
            # First try with a known video ID from cache
            if channel_id in self.cache['channels']:
                video_id = self.cache['channels'][channel_id].get('video_id')
                if video_id:
                    for quality in qualities:
                        url = base_url.format(video_id, quality)
                        response = requests.head(url, timeout=5)
                        if response.status_code == 200:
                            img_data = requests.get(url, timeout=10).content
                            with open(logo_path, 'wb') as f:
                                f.write(img_data)
                            print(f"  ✅ Logo saved: {quality}")
                            return logo_path
            
            # Fallback to default logo
            return None
        except Exception as e:
            print(f"  ⚠️ Logo fetch failed: {str(e)[:50]}")
            return None
    
    def get_stream_info(self, url):
        """Get stream URL and metadata with quality options"""
        ydl_opts = {
            'cookies': self.cookies_file,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': 3,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android'],
                    'player_skip': ['webpage', 'configs']
                }
            }
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return None
                
                video_id = info.get('id')
                channel_id = info.get('channel_id', video_id)
                title = info.get('title', 'Unknown')
                channel_name = info.get('channel', 'Unknown')
                
                # Clean channel name for filename
                clean_name = re.sub(r'[^\w\s-]', '', channel_name).strip()
                
                # Cache channel info
                self.cache['channels'][channel_id] = {
                    'name': channel_name,
                    'video_id': video_id,
                    'last_seen': datetime.now().isoformat()
                }
                
                # Check if live
                is_live = info.get('is_live', False)
                live_status = info.get('live_status', '')
                
                if not (is_live or live_status == 'is_live'):
                    return {
                        'status': 'offline',
                        'video_id': video_id,
                        'channel_id': channel_id,
                        'name': clean_name,
                        'title': title
                    }
                
                formats = info.get('formats', [])
                
                # Get quality-specific streams
                quality_streams = {}
                
                for profile_name, profile in QUALITY_PROFILES.items():
                    # Filter video formats
                    video_formats = [
                        f for f in formats 
                        if f.get('height') and f.get('url') and f.get('vcodec') != 'none'
                    ]
                    
                    if not video_formats:
                        continue
                    
                    # Apply profile filters
                    if 'min_height' in profile:
                        video_formats = [f for f in video_formats if f.get('height', 0) >= profile['min_height']]
                    elif 'max_height' in profile:
                        video_formats = [f for f in video_formats if f.get('height', 0) <= profile['max_height']]
                    
                    if not video_formats:
                        continue
                    
                    # Select best format based on priority
                    best_format = None
                    for target in profile.get('priority', []):
                        for fmt in video_formats:
                            if fmt.get('height') == target:
                                best_format = fmt
                                break
                        if best_format:
                            break
                    
                    if not best_format and video_formats:
                        best_format = video_formats[0]
                    
                    if best_format:
                        quality_streams[profile_name] = {
                            'url': best_format['url'],
                            'height': best_format.get('height', 0),
                            'fps': best_format.get('fps', 30),
                            'quality_tag': f"{best_format.get('height', 0)}p"
                        }
                
                # Get channel logo
                logo_path = self.fetch_channel_logo(channel_id, clean_name)
                
                return {
                    'status': 'live',
                    'video_id': video_id,
                    'channel_id': channel_id,
                    'name': clean_name,
                    'title': title,
                    'streams': quality_streams,
                    'logo': logo_path
                }
                
        except Exception as e:
            print(f"  ⚠️ Error: {str(e)[:150]}")
            return None
    
    def generate_epg(self, channels_data):
        """Generate XMLTV EPG file"""
        tv = ET.Element("tv", {
            "generator-info-name": "YouTube Live EPG Generator",
            "date": datetime.now().strftime("%Y%m%d%H%M%S %Z")
        })
        
        for channel in channels_data:
            if channel.get('status') == 'live':
                # Add channel element
                channel_elem = ET.SubElement(tv, "channel", {"id": channel['channel_id']})
                
                display_name = ET.SubElement(channel_elem, "display-name")
                display_name.text = channel['name']
                
                if channel.get('logo'):
                    icon = ET.SubElement(channel_elem, "icon", {"src": channel['logo']})
                
                # Add sample programme (current live stream)
                programme = ET.SubElement(tv, "programme", {
                    "start": datetime.now().strftime("%Y%m%d%H%M%S +0000"),
                    "stop": (datetime.now() + timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0000"),
                    "channel": channel['channel_id']
                })
                
                title = ET.SubElement(programme, "title")
                title.text = channel.get('title', 'Live Stream')
                
                desc = ET.SubElement(programme, "desc")
                desc.text = f"Live YouTube stream from {channel['name']}"
                
                category = ET.SubElement(programme, "category")
                category.text = "Live"
        
        # Pretty print XML
        rough_string = ET.tostring(tv, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')
        
        # Save EPG
        with open('epg.xml', 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        print(f"✅ EPG generated with {len(channels_data)} channels")
    
    def generate_playlists(self, all_channels):
        """Generate multiple playlists (main, HD, mobile, audio)"""
        
        # Initialize playlist containers
        playlists = {
            'main': [],
            'hd': [],
            'mobile': [],
            'audio': []
        }
        
        # Common headers
        headers = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"# Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"# Total channels: {len(all_channels)}",
            ""
        ]
        
        for playlist_name in playlists:
            playlists[playlist_name] = headers.copy()
        
        # Stats tracking
        stats = {
            'total': len(all_channels),
            'live': 0,
            'offline': 0,
            'error': 0,
            'qualities': {'1080p': 0, '720p': 0, '480p': 0, 'other': 0},
            'by_category': {}
        }
        
        # Process each channel
        for channel in all_channels:
            channel_name = channel.get('name', 'Unknown')
            channel_id = channel.get('channel_id', '')
            
            # Determine category (simple logic - customize as needed)
            category = 'General'
            if 'news' in channel_name.lower():
                category = 'News'
            elif 'sport' in channel_name.lower():
                category = 'Sports'
            elif 'entertain' in channel_name.lower():
                category = 'Entertainment'
            
            stats['by_category'][category] = stats['by_category'].get(category, 0) + 1
            
            # Add logo to EXTINF if available
            logo_attr = f' tvg-logo="{channel["logo"]}"' if channel.get('logo') else ''
            
            if channel.get('status') == 'live':
                stats['live'] += 1
                
                # Track quality
                height = 0
                for stream_data in channel.get('streams', {}).values():
                    height = max(height, stream_data.get('height', 0))
                
                if height >= 1080:
                    stats['qualities']['1080p'] += 1
                elif height >= 720:
                    stats['qualities']['720p'] += 1
                elif height >= 480:
                    stats['qualities']['480p'] += 1
                else:
                    stats['qualities']['other'] += 1
                
                # Add to main playlist (prefer HD)
                main_stream = channel.get('streams', {}).get('hd', {})
                if not main_stream:
                    # Fallback to any stream
                    for s in channel.get('streams', {}).values():
                        main_stream = s
                        break
                
                if main_stream:
                    quality_tag = main_stream.get('quality_tag', '')
                    playlists['main'].append(
                        f'#EXTINF:-1 tvg-id="{channel_id}"{logo_attr} tvg-name="{channel_name}" '
                        f'group-title="{category}",{channel_name} [{quality_tag}]'
                    )
                    playlists['main'].append(main_stream['url'])
                    playlists['main'].append("")
                
                # Add to quality-specific playlists
                for profile_name in ['hd', 'mobile', 'audio']:
                    if profile_name in channel.get('streams', {}):
                        stream = channel['streams'][profile_name]
                        suffix = QUALITY_PROFILES[profile_name]['suffix']
                        playlists[profile_name].append(
                            f'#EXTINF:-1 tvg-id="{channel_id}"{logo_attr} tvg-name="{channel_name}" '
                            f'group-title="{category}",{channel_name} {suffix}'
                        )
                        playlists[profile_name].append(stream['url'])
                        playlists[profile_name].append("")
            
            elif channel.get('status') == 'offline':
                stats['offline'] += 1
                fallback_url = f"https://www.youtube.com/watch?v={channel['video_id']}"
                
                for playlist_name in playlists:
                    playlists[playlist_name].append(
                        f'#EXTINF:-1 tvg-id="{channel_id}"{logo_attr} tvg-name="{channel_name}" '
                        f'group-title="{category}",{channel_name} [Offline]'
                    )
                    playlists[playlist_name].append(fallback_url)
                    playlists[playlist_name].append("")
            
            else:
                stats['error'] += 1
                for playlist_name in playlists:
                    playlists[playlist_name].append(
                        f'#EXTINF:-1 tvg-id="{channel_id}"{logo_attr} tvg-name="{channel_name}" '
                        f'group-title="{category}",{channel_name} [Error]'
                    )
                    playlists[playlist_name].append(f"https://youtube.com/watch?v={channel.get('video_id', '')}")
                    playlists[playlist_name].append("")
        
        # Add summary to each playlist
        summary = [
            "",
            f"# Summary: {stats['live']}/{stats['total']} streams active",
            f"# Quality: {stats['qualities']['1080p']}x1080p, {stats['qualities']['720p']}x720p",
            f"# Categories: {', '.join([f'{k}:{v}' for k, v in stats['by_category'].items()])}",
            f"# Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        ]
        
        for playlist_name in playlists:
            playlists[playlist_name].extend(summary)
        
        # Save all playlists
        playlist_files = {
            'main': 'streams.m3u8',
            'hd': 'streams_hd.m3u8',
            'mobile': 'streams_mobile.m3u8',
            'audio': 'streams_audio.m3u8'
        }
        
        for name, filename in playlist_files.items():
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(playlists[name]))
            print(f"✅ Saved: {filename}")
        
        # Save stats
        with open('stats.json', 'w') as f:
            json.dump(stats, f, indent=2)
        
        return stats, playlists

def main():
    # Read streams.txt
    if not os.path.exists('streams.txt'):
        print("❌ streams.txt not found")
        return
    
    with open('streams.txt', 'r') as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    
    if not lines:
        print("⚠️ No streams found")
        return
    
    print(f"📡 Processing {len(lines)} channels...")
    
    # Initialize generator
    generator = YouTubePlaylistGenerator()
    
    # Process each channel
    channels_data = []
    for i, url in enumerate(lines, 1):
        print(f"\n📺 [{i}/{len(lines)}] Processing: {url}")
        time.sleep(random.uniform(2, 5))  # Rate limiting
        
        channel_info = generator.get_stream_info(url)
        if channel_info:
            channels_data.append(channel_info)
            
            if channel_info['status'] == 'live':
                streams = list(channel_info.get('streams', {}).keys())
                print(f"  ✅ LIVE - Qualities: {', '.join(streams)}")
            else:
                print(f"  ⚠️ {channel_info['status'].upper()}")
    
    # Generate EPG
    print("\n📋 Generating EPG...")
    generator.generate_epg(channels_data)
    
    # Generate playlists
    print("\n🎬 Generating playlists...")
    stats, playlists = generator.generate_playlists(channels_data)
    
    # Save cache
    generator.save_cache()
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"📊 FINAL STATISTICS:")
    print(f"   Live: {stats['live']}/{stats['total']}")
    print(f"   Offline: {stats['offline']}")
    print(f"   Errors: {stats['error']}")
    print(f"\n📊 Quality Distribution:")
    for quality, count in stats['qualities'].items():
        if count > 0:
            print(f"   {quality}: {count}")
    print(f"\n📊 Categories:")
    for category, count in stats['by_category'].items():
        print(f"   {category}: {count}")
    print(f"\n📁 Generated Files:")
    print("   - streams.m3u8 (Main playlist)")
    print("   - streams_hd.m3u8 (HD only)")
    print("   - streams_mobile.m3u8 (Mobile quality)")
    print("   - streams_audio.m3u8 (Audio only)")
    print("   - epg.xml (TV Guide)")
    print("   - stats.json (Detailed statistics)")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
