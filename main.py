import requests
import json

def generate_m3u():
    # Using the URL you provided
    url = "https://raw.githubusercontent.com/sptvhelpdesk-ship-it/jstar-aoi/refs/heads/main/channels.json"
    output_file = "playlist.m3u"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            
            for item in data:
                # 1. Basic Metadata
                name = item.get("name", "Unknown")
                logo = item.get("logo", "")
                group = item.get("category", "General")
                mpd_url = item.get("mpd", "")
                
                # Skip entries that don't have a stream link (like the Telegram info block)
                if not mpd_url:
                    continue

                # 2. Extract DRM ClearKey
                # The JSON uses a dict: {"KID": "KEY"}
                drm_data = item.get("drm", {})
                license_key = ""
                if drm_data:
                    # Formats it as KID:KEY for ClearKey standards
                    license_key = ",".join([f"{k}:{v}" for k, v in drm_data.items()])

                # 3. Headers (User-Agent and Token)
                # TiviMate and OTT Navigator use the | symbol to append headers to the URL
                user_agent = item.get("userAgent", "Mozilla/5.0")
                token = item.get("token", "")
                
                # Append token to URL if it exists
                final_url = f"{mpd_url}{token}" if token else mpd_url
                # Append User-Agent for the player
                final_link = f"{final_url}|User-Agent={user_agent}"

                # 4. Writing to File
                f.write(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}",{name}\n')
                
                if license_key:
                    # Standard ClearKey properties for advanced players
                    f.write(f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n')
                    f.write(f'#KODIPROP:inputstream.adaptive.license_key={license_key}\n')
                
                f.write(f"{final_link}\n\n")

        print(f"Successfully generated {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_m3u()
