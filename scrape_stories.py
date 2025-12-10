import asyncio
from playwright.async_api import async_playwright
import os
from datetime import datetime
import json
import hashlib

ACCOUNTS = ['yaktpzhitu', 'wbvaleriy']
DOWNLOAD_DIR = 'instagram_stories'

async def scrape_account(page, username):
    """Scrape stories from a single account"""
    url = f'https://insta-stories-viewer.com/{username}/'
    
    print(f"\n📱 Checking {username}...")
    await page.goto(url, wait_until='domcontentloaded')
    
    # Wait for content to load
    await page.wait_for_timeout(3000)
    
    # Check if there are stories
    no_stories = await page.locator('text=No new stories').count()
    
    if no_stories > 0:
        print(f"  ❌ No stories available")
        return []
    
    # Find all story images - they appear to be in the Stories tab
    story_images = await page.locator('div.stories img, div[class*="story"] img').all()
    
    stories = []
    
    for idx, img in enumerate(story_images):
        try:
            src = await img.get_attribute('src')
            
            # Filter out profile pictures and icons
            if src and ('cdn.insta-stories-viewer.com' in src or 'cdninstagram' in src):
                # Skip very small images (likely icons)
                try:
                    width = await img.get_attribute('width')
                    if width and int(width) < 50:
                        continue
                except:
                    pass
                
                # Check if it's a video thumbnail
                parent = await img.locator('xpath=..').first
                is_video = await parent.locator('svg, [class*="video"], [class*="play"]').count() > 0
                
                stories.append({
                    'type': 'video' if is_video else 'image',
                    'url': src,
                    'index': idx
                })
                
        except Exception as e:
            print(f"  ⚠ Error processing image {idx}: {e}")
    
    # Also check for video elements
    video_elements = await page.locator('div.stories video, div[class*="story"] video').all()
    
    for idx, video in enumerate(video_elements):
        try:
            src = await video.get_attribute('src')
            if src:
                stories.append({
                    'type': 'video',
                    'url': src,
                    'index': len(stories)
                })
        except Exception as e:
            print(f"  ⚠ Error processing video {idx}: {e}")
    
    if stories:
        print(f"  ✓ Found {len(stories)} stories")
    else:
        print(f"  ❌ No story content found")
    
    return stories

async def download_media(page, media_item, username, existing_hashes):
    """Download a single media file"""
    url = media_item['url']
    media_type = media_item['type']
    
    try:
        # Fetch the media
        response = await page.request.get(url)
        content = await response.body()
        
        # Check if we already have this file (by hash)
        content_hash = hashlib.md5(content).hexdigest()
        
        if content_hash in existing_hashes:
            print(f"  ⏭ Skipped duplicate")
            return None
        
        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = 'mp4' if media_type == 'video' else 'jpg'
        filename = f"{username}_{timestamp}_{content_hash[:8]}.{ext}"
        filepath = os.path.join(DOWNLOAD_DIR, username, filename)
        
        # Save file
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(content)
        
        print(f"  ✓ Downloaded: {filename} ({len(content)//1024}KB)")
        
        existing_hashes.add(content_hash)
        
        return {
            'filepath': filepath,
            'hash': content_hash,
            'size': len(content),
            'url': url
        }
        
    except Exception as e:
        print(f"  ❌ Failed to download: {e}")
        return None

def load_existing_hashes(username):
    """Load hashes of previously downloaded files to avoid duplicates"""
    hashes = set()
    user_dir = os.path.join(DOWNLOAD_DIR, username)
    
    if os.path.exists(user_dir):
        for filename in os.listdir(user_dir):
            filepath = os.path.join(user_dir, filename)
            if os.path.isfile(filepath):
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                        hashes.add(hashlib.md5(content).hexdigest())
                except:
                    pass
    
    return hashes

async def main():
    """Main scraping function"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    print("🚀 Starting Instagram Stories Scraper")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        all_downloads = []
        
        for username in ACCOUNTS:
            # Load existing file hashes to avoid re-downloading
            existing_hashes = load_existing_hashes(username)
            print(f"  📁 Already have {len(existing_hashes)} files for {username}")
            
            stories = await scrape_account(page, username)
            
            if stories:
                print(f"  📥 Downloading...")
                for story in stories:
                    result = await download_media(page, story, username, existing_hashes)
                    if result:
                        all_downloads.append({
                            'username': username,
                            'filepath': result['filepath'],
                            'timestamp': datetime.now().isoformat(),
                            'size': result['size'],
                            'type': story['type']
                        })
                    
                    # Small delay between downloads
                    await asyncio.sleep(1)
            
            # Wait between accounts
            await asyncio.sleep(3)
        
        await browser.close()
        
        # Save manifest
        if all_downloads:
            manifest_path = os.path.join(DOWNLOAD_DIR, f'manifest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            with open(manifest_path, 'w') as f:
                json.dump(all_downloads, f, indent=2)
            print(f"\n✅ Saved manifest: {manifest_path}")
        
        print(f"\n✅ Complete! Downloaded {len(all_downloads)} new files")
        
        if len(all_downloads) == 0:
            print("   (No new stories found)")

if __name__ == '__main__':
    asyncio.run(main())
