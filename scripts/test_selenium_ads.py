"""Standalone Selenium scraper for Google Ads Transparency Center."""

import time
import logging
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("google-ads-scraper")

class GoogleAdsSeleniumScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None

    def _init_driver(self):
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        # User agent to avoid detection
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Driver init failed: {e}. Trying default...")
            self.driver = webdriver.Chrome(options=chrome_options)

    def check_ads(self, company_name: str) -> dict:
        if not self.driver:
            self._init_driver()

        try:
            # Construct URL for direct search
            # region=2826 is UK
            encoded_name = urllib.parse.quote(company_name)
            url = f"https://adstransparency.google.com/?region=2826&query={encoded_name}"
            
            logger.info(f"Navigating to: {url}")
            self.driver.get(url)
            
            # Allow time for dynamic content to load
            # Google Ads Transparency center is heavy
            time.sleep(5)
            
            # Check for "0 ads" or "No ads found" text
            # The structure is complex (Shadow DOM), but text content usually leaks through or is accessible
            
            # Strategy: Look for ad cards.
            # If we see elements that look like ad creatives, it's a positive.
            
            # We need to detect if we are on a "Search Results" page (list of advertisers)
            # OR if it took us directly to an advertiser page (unlikely with ?query= parameter, usually shows list)
            
            # Wait for something to load
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Take a screenshot for debug
            self.driver.save_screenshot(f"logs/debug_{company_name.replace(' ', '_')}.png")
            
            # Quick check of page source
            page_source = self.driver.page_source.lower()
            
            if "no ads found" in page_source or "0 ads" in page_source:
                return {"running_ads": False, "status": "No ads text found"}

            # If we see "Advertisers" header, it means we have a list of matches
            # We need to click the first one? Or just say "Potential match"
            
            # This is a quick POC.
            # If "Any time" and "Shown in" filters appear, we are viewing ads.
            
            return {"running_ads": "Unknown - Check Screenshot", "details": "Page loaded"}

        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return {"error": str(e)}
        
    def quit(self):
        if self.driver:
            self.driver.quit()

if __name__ == "__main__":
    scraper = GoogleAdsSeleniumScraper(headless=True)
    try:
        # Test with known advertiser
        result = scraper.check_ads("Octopus Energy")
        print(f"Result for Octopus Energy: {result}")
        
        # Test with known non-advertiser
        # result = scraper.check_ads("Some Random Plumber 12345")
        # print(f"Result for Random: {result}")
    finally:
        scraper.quit()
