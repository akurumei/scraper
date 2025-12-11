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
    
    # Navigate and wait for network to be idle
    await page.goto(url, wait_until='networkidle', timeout=30000)
    
    # Wait extra time for JavaScript to execute
    print("   ⏳ Waiting for dynamic content...")
    await page.wait_for_timeout(8000)
    
    # Try clicking on "Stories" tab if it exists
    try:
        stories_tab = page.locator('text=Stories').first
        if await stories_tab.is_visible():
            await stories_tab.click()
            await page.wait_for_timeout(2000)
            print("   ✓ Clicked Stories tab")
    except:
        print("   ℹ️  Stories tab not found or already active")
    
    # Get page content
    page_content = await page.content()
    
    # Check for "No new stories" text
    has_no_stories = 'No new stories' in page_content
    print(f"   'No new stories' found: {has_no_stories}")
    
    # Check what's actually visible
    all_images = await page.locator('img').all()
    print(f"   Total images on page: {len(all_images)}")
    
    stories = []
    
    # Look through all images
    for idx, img in enumerate(all_images):
        try:
            src = await img.get_attribute('src')
            if not src:
                continue
            
            # Check if it's likely a story image
            is_cdn = any(domain in src for domain in [
                'cdn.insta-stories-viewer.com',
                'cdninstagram',
                'fbcdn.net',
                'scontent'
            ])
            
            if is_cdn:
                # Check if element is visible
                is_visible = await img.is_visible()
                if not is_visible:
                    continue
                
                # Get bounding box
                box = await img.bounding_box()
                if box:
                    width = box['width']
                    height = box['height']
                    
                    # Filter small images
                    if width >= 100 and height >= 100:
                        print(f"   📷 Image {len(stories)}: {int(width)}x{int(height)}px")
                        print(f"      URL: {src[:80]}...")
                        
                        stories.append({
                            'type': 'image',
                            'url': src,
                            'index': len(stories)
                        })
        except Exception as e:
            pass
    
    # Look for videos
    videos = await page.locator('video').all()
    print(f"   Total videos on page: {len(videos)}")
    
    for video in videos:
        try:
            src = await video.get_attribute('src')
            if src and await video.is_visible():
                print(f"   🎥 Video: {src[:80]}...")
                stories.append({
                    'type': 'video',
                    'url': src,
                    'index': len(stories)
                })
        except:
            pass
    
    if not stories and not has_no_stories:
        # If we didn't find stories but also didn't see "no stories", page might not have loaded
        print(f"   ⚠️  Page may not have loaded correctly")
        print(f"   📄 Saving page HTML for debugging...")
        
        # Save HTML for inspection
        debug_dir = os.path.join(DOWNLOAD_DIR, 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = os.path.join(debug_dir, f'{username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html')
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(page_content)
        print(f"   💾 Saved to: {debug_file}")
        
        # Take a screenshot
        screenshot_file = debug_file.replace('.html', '.png')
        await page.screenshot(path=screenshot_file, full_page=True)
        print(f"   📸 Screenshot: {screenshot_file}")
    
    if stories:
        print(f"  ✅ Found {len(stories)} stories")
    else:
        print(f"  ❌ No stories found")
    
    return stories

async def download_media(page, media_item, username, existing_hashes):
    """Download a single media file"""
    url = media_item['url']
    media_type = media_item['type']
    
    try:
        print(f"   📥 Downloading...")
        
        response = await page.request.get(url)
        content = await response.body()
        
        content_hash = hashlib.md5(content).hexdigest()
        
        if content_hash in existing_hashes:
            print(f"      ⏭ Duplicate")
            return None
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = 'mp4' if media_type == 'video' else 'jpg'
        filename = f"{username}_{timestamp}_{content_hash[:8]}.{ext}"
        filepath = os.path.join(DOWNLOAD_DIR, username, filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(content)
        
        print(f"      ✅ {filename} ({len(content)//1024}KB)")
        
        existing_hashes.add(content_hash)
        
        return {
            'filepath': filepath,
            'hash': content_hash,
            'size': len(content),
            'url': url
        }
        
    except Exception as e:
        print(f"      ❌ Error: {e}")
        return None

def load_existing_hashes(username):
    """Load hashes of previously downloaded files"""
    hashes = set()
    user_dir = os.path.join(DOWNLOAD_DIR, username)
    
    if os.path.exists(user_dir):
        for filename in os.listdir(user_dir):
            filepath = os.path.join(user_dir, filename)
            if os.path.isfile(filepath) and not filename.endswith('.html'):
                try:
                    with open(filepath, 'rb') as f:
                        hashes.add(hashlib.md5(f.read()).hexdigest())
                except:
                    pass
    
    return hashes

async def main():
    """Main scraping function"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    print("🚀 Instagram Stories Scraper")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 Accounts: {', '.join(ACCOUNTS)}")
    
    async with async_playwright() as p:
        print("\n🌐 Launching browser with stealth mode...")
        
        # Launch with more realistic settings
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York'
        )
        
        # Add stealth scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        page = await context.new_page()
        
        all_downloads = []
        
        for username in ACCOUNTS:
            existing_hashes = load_existing_hashes(username)
            if existing_hashes:
                print(f"  📁 {len(existing_hashes)} existing files")
            
            stories = await scrape_account(page, username)
            
            if stories:
                print(f"\n  📥 Downloading {len(stories)} items...")
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
            
            await asyncio.sleep(5)
        
        await browser.close()
        
        if all_downloads:
            manifest = os.path.join(DOWNLOAD_DIR, f'manifest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            with open(manifest, 'w') as f:
                json.dump(all_downloads, f, indent=2)
            print(f"\n📄 Manifest: {manifest}")
        
        print(f"\n{'='*60}")
        print(f"✅ DONE! Downloaded {len(all_downloads)} files")
        if not all_downloads:
            print("   ℹ️  Check debug/ folder for HTML/screenshots")
        print(f"{'='*60}")

if __name__ == '__main__':
    asyncio.run(main())
