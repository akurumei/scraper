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
    print(f"   URL: {url}")
    
    await page.goto(url, wait_until='networkidle')
    
    # Wait longer for dynamic content
    await page.wait_for_timeout(5000)
    
    # Debug: Get page title
    title = await page.title()
    print(f"   Page title: {title}")
    
    # Debug: Check what's on the page
    page_text = await page.content()
    has_no_stories_text = 'No new stories' in page_text
    print(f"   'No new stories' text found: {has_no_stories_text}")
    
    if has_no_stories_text:
        print(f"  ❌ No stories available")
        return []
    
    # Try multiple strategies to find stories
    stories = []
    
    # Strategy 1: Look for all images on page
    all_images = await page.locator('img').all()
    print(f"   Total images found: {len(all_images)}")
    
    for idx, img in enumerate(all_images):
        try:
            src = await img.get_attribute('src')
            if not src:
                continue
                
            # Check if it's a CDN image (likely a story)
            if 'cdn.insta-stories-viewer.com' in src or 'cdninstagram' in src or 'fbcdn' in src:
                # Get dimensions to filter out tiny images
                box = await img.bounding_box()
                
                if box:
                    width = box['width']
                    height = box['height']
                    print(f"   Image {idx}: {width}x{height}px - {src[:100]}")
                    
                    # Skip small images (profile pics, icons)
                    if width < 100 or height < 100:
                        print(f"     ⏭ Too small")
                        continue
                    
                    stories.append({
                        'type': 'image',
                        'url': src,
                        'index': len(stories)
                    })
                    print(f"     ✅ Added!")
                    
        except Exception as e:
            print(f"   ⚠ Error with image {idx}: {e}")
    
    # Strategy 2: Look for videos
    videos = await page.locator('video').all()
    print(f"   Total videos found: {len(videos)}")
    
    for idx, video in enumerate(videos):
        try:
            src = await video.get_attribute('src')
            poster = await video.get_attribute('poster')
            
            if src:
                print(f"   Video {idx}: {src[:100]}")
                stories.append({
                    'type': 'video',
                    'url': src,
                    'index': len(stories)
                })
                print(f"     ✅ Added!")
                
        except Exception as e:
            print(f"   ⚠ Error with video {idx}: {e}")
    
    # Strategy 3: Look for specific story containers
    story_containers = await page.locator('[class*="story"], [class*="Story"]').all()
    print(f"   Story containers found: {len(story_containers)}")
    
    if stories:
        print(f"  ✅ Found {len(stories)} stories total")
    else:
        print(f"  ❌ No story media found")
        print(f"  🔍 Page HTML preview (first 500 chars):")
        print(f"     {page_text[:500]}")
    
    return stories

async def download_media(page, media_item, username, existing_hashes):
    """Download a single media file"""
    url = media_item['url']
    media_type = media_item['type']
    
    try:
        print(f"   📥 Downloading: {url[:80]}...")
        
        # Fetch the media
        response = await page.request.get(url)
        content = await response.body()
        
        # Check if we already have this file (by hash)
        content_hash = hashlib.md5(content).hexdigest()
        
        if content_hash in existing_hashes:
            print(f"      ⏭ Skipped duplicate")
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
        
        print(f"      ✅ Saved: {filename} ({len(content)//1024}KB)")
        
        existing_hashes.add(content_hash)
        
        return {
            'filepath': filepath,
            'hash': content_hash,
            'size': len(content),
            'url': url
        }
        
    except Exception as e:
        print(f"      ❌ Failed: {e}")
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
    print(f"📋 Accounts: {', '.join(ACCOUNTS)}")
    
    async with async_playwright() as p:
        print("\n🌐 Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        all_downloads = []
        
        for username in ACCOUNTS:
            existing_hashes = load_existing_hashes(username)
            if existing_hashes:
                print(f"  📁 Already have {len(existing_hashes)} files")
            
            stories = await scrape_account(page, username)
            
            if stories:
                print(f"\n  📥 Downloading {len(stories)} stories...")
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
                    await asyncio.sleep(1)
            
            await asyncio.sleep(3)
        
        await browser.close()
        
        # Save manifest
        if all_downloads:
            manifest_path = os.path.join(DOWNLOAD_DIR, f'manifest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            with open(manifest_path, 'w') as f:
                json.dump(all_downloads, f, indent=2)
            print(f"\n📄 Manifest: {manifest_path}")
        
        print(f"\n{'='*60}")
        print(f"✅ COMPLETE! Downloaded {len(all_downloads)} new files")
        if len(all_downloads) == 0:
            print("   ℹ️  No new stories found this run")
        print(f"{'='*60}")

if __name__ == '__main__':
    asyncio.run(main())
