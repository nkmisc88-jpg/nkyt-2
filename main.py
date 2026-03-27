import requests
import json

def generate_m3u():
    url = "https://zstar.pfy.workers.dev"
    output_file = "playlist.m3u"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in data:
                name = item.get("name", "Unknown")
                logo = item.get("logo", "")
                group = item.get("groupTitle", "General")
                link = item.get("link", "")
                # ClearKey DRM info
                license = item.get("drmLicense", "")

                f.write(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}",{name}\n')
                if license:
                    f.write(f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n')
                    f.write(f'#KODIPROP:inputstream.adaptive.license_key={license}\n')
                f.write(f"{link}\n\n")
        print("Playlist updated successfully.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_m3u()
