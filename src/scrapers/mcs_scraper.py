"""MCS Directory heat pump installer scraper."""

import time
import logging
from typing import List, Optional, Set
from datetime import datetime
from pathlib import Path
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from src.core.data_source import DataSource
from src.core.models import Installer, ScraperConfig
from src.core.output import OutputHandler
from src.utils.retry import retry_on_exception
from src.utils.helpers import sanitize_phone_number, sanitize_company_name, is_valid_url

logger = logging.getLogger("ppl-list-builder")


class MCScraper(DataSource):
    """Web scraper for MCS Directory heat pump installers."""

    def __init__(self, config: ScraperConfig):
        """Initialize MCS scraper.

        Args:
            config: ScraperConfig instance with scraper settings
        """
        super().__init__(config)
        self.driver: Optional[webdriver.Chrome] = None
        self.installers: List[Installer] = []
        self.processed_companies: Set[str] = set()
        self.failed_records: List[dict] = []
        self.output_path = "output/heat-pump-installers.csv"
        self.csv_initialized = False

    def _init_driver(self) -> webdriver.Chrome:
        """Initialize Selenium WebDriver.

        Returns:
            Configured Chrome WebDriver instance
        """
        chrome_options = Options()

        if self.config.headless:
            chrome_options.add_argument("--headless")

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        try:
            # Try to use webdriver-manager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except (OSError, Exception) as e:
            logger.warning(f"webdriver-manager failed: {e}. Trying system Chrome...")
            # Fallback to system Chrome
            driver = webdriver.Chrome(options=chrome_options)

        driver.set_page_load_timeout(self.config.timeout)

        return driver

    def scrape(self) -> List[Installer]:
        """Execute the scraping process.

        Returns:
            List of scraped Installer objects
        """
        try:
            self.driver = self._init_driver()
            logger.info(f"Starting MCS scraper for {self.config.url}")

            # Navigate to the website
            self.driver.get(self.config.url)
            logger.info("Page loaded, applying pre-filters...")

            # Apply pre-filter workflow (All Heat Pumps + Nationwide)
            self._apply_pre_filters()

            # Wait for filtered results page to load
            time.sleep(2)

            # Scrape all pages
            self._scrape_all_pages()

            logger.info(f"Scraping complete. Total installers: {len(self.installers)}")
            if self.failed_records:
                logger.warning(f"Failed records: {len(self.failed_records)}")

            logger.info(f"CSV saved to: {self.output_path}")
            logger.info("Run 'python scripts/finalize_csv.py' to deduplicate and sort")

            return self.installers

        except Exception as e:
            logger.error(f"Scraping failed: {e}", exc_info=True)
            raise

        finally:
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver closed")

    def _apply_pre_filters(self) -> None:
        """Apply pre-filter workflow: All Heat Pumps + Nationwide region."""
        try:
            logger.info("Starting pre-filter workflow...")

            # Step 1: Click on "All Heat Pumps" image or parent
            logger.info("Step 1: Clicking 'All Heat Pumps' image...")
            try:
                # First scroll down to see the heat pump options
                self.driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)

                # Try clicking the image
                try:
                    heat_pump_img = self.driver.find_element(
                        By.XPATH,
                        "//img[contains(@src, 'All-Heat-Pumps')]"
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView();", heat_pump_img)
                    time.sleep(0.5)
                    # Use JavaScript click instead of Selenium click
                    self.driver.execute_script("arguments[0].click();", heat_pump_img)
                    logger.info("Clicked All Heat Pumps image using JavaScript")
                except Exception as e:
                    # If image click fails, try clicking the parent button/link
                    logger.debug(f"Direct image click failed: {e}, trying parent element...")
                    heat_pump_link = self.driver.find_element(
                        By.XPATH,
                        "//img[contains(@src, 'All-Heat-Pumps')]/ancestor::button | //img[contains(@src, 'All-Heat-Pumps')]/ancestor::a | //img[contains(@src, 'All-Heat-Pumps')]/ancestor::div[@role='button']"
                    )
                    self.driver.execute_script("arguments[0].click();", heat_pump_link)
                    logger.info("Clicked parent element of All Heat Pumps image")

                time.sleep(1)
            except NoSuchElementException:
                logger.warning("All Heat Pumps image not found")
                return

            # Step 2: Click "select-location" button
            logger.info("Step 2: Clicking 'select-location' button...")
            try:
                select_location_btn = self.driver.find_element(By.ID, "select-location")
                self.driver.execute_script("arguments[0].click();", select_location_btn)
                logger.info("Clicked select-location button")
                time.sleep(1)
            except NoSuchElementException:
                logger.warning("select-location button not found")
                return

            # Step 3: Check "region_nationwide" checkbox
            logger.info("Step 3: Checking 'region_nationwide' checkbox...")
            try:
                nationwide_checkbox = self.driver.find_element(By.ID, "region_nationwide")
                if not nationwide_checkbox.is_selected():
                    self.driver.execute_script("arguments[0].click();", nationwide_checkbox)
                    logger.info("Checked nationwide checkbox")
                    time.sleep(0.5)
            except NoSuchElementException:
                logger.warning("region_nationwide checkbox not found")
                return

            # Step 4: Click "submit-location-filters" button
            logger.info("Step 4: Clicking 'submit-location-filters' button...")
            try:
                submit_btn = self.driver.find_element(By.ID, "submit-location-filters")
                self.driver.execute_script("arguments[0].click();", submit_btn)
                logger.info("Clicked submit-location-filters button")
                time.sleep(2)  # Wait for page to load with results
            except NoSuchElementException:
                logger.warning("submit-location-filters button not found")
                return

            logger.info("Pre-filter workflow completed successfully")

        except Exception as e:
            logger.warning(f"Pre-filter workflow error: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def _scrape_all_pages(self) -> None:
        """Scrape all paginated pages."""
        page_number = 1

        while True:
            try:
                logger.info(f"Scraping page {page_number}...")
                self._scrape_current_page()

                # Save current page's installers to CSV incrementally
                self._save_to_csv_incremental()

                # Try to move to next page
                if not self._go_to_next_page():
                    logger.info("No more pages to scrape")
                    break

                page_number += 1
                time.sleep(self.config.request_delay)

            except Exception as e:
                logger.error(f"Error on page {page_number}: {e}")
                # Continue to next page despite errors
                if not self._go_to_next_page():
                    break
                page_number += 1

    def _scrape_current_page(self) -> None:
        """Scrape installer data from the current page."""
        try:
            wait = WebDriverWait(self.driver, 10)

            # Wait for installer tiles to appear (correct selector from MCS site)
            wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "installer-tile"))
            )

            # Get all installer cards on current page
            cards = self.driver.find_elements(By.CLASS_NAME, "installer-tile")
            logger.info(f"Found {len(cards)} installer cards on current page")

            for index, card in enumerate(cards):
                try:
                    self._scrape_installer_card(card, index)
                except StaleElementReferenceException:
                    logger.warning(f"Stale element reference at card {index}, skipping")
                except Exception as e:
                    logger.debug(f"Error scraping card {index}: {e}")
                    continue

        except TimeoutException:
            logger.error("Timeout waiting for installer cards")
        except Exception as e:
            logger.warning(f"Error during page scraping: {e}")

    def _scrape_installer_card(self, card, card_index: int) -> None:
        """Scrape data from a single installer card.

        Args:
            card: WebElement representing an installer card
            card_index: Index of card on page
        """
        try:
            # Extract company name from h3 tag within the card
            company_name = None
            try:
                company_name_elem = card.find_element(By.TAG_NAME, "h3")
                company_name = company_name_elem.text.strip()

                # Debug: log what we found
                if card_index == 0:  # Log first card only
                    logger.debug(f"H3 element text: '{company_name}'")
                    logger.debug(f"H3 HTML: {company_name_elem.get_attribute('outerHTML')}")

                # If text is empty, try getting inner HTML
                if not company_name:
                    company_name = company_name_elem.get_attribute("innerText")
                    if not company_name:
                        company_name = company_name_elem.get_attribute("textContent")

                # Try using JavaScript to get text as last resort
                if not company_name:
                    company_name = self.driver.execute_script(
                        "return arguments[0].innerText || arguments[0].textContent",
                        company_name_elem
                    )

            except NoSuchElementException:
                logger.debug(f"H3 tag not found in card {card_index}")
                return
            except Exception as e:
                logger.debug(f"Error extracting h3 text from card {card_index}: {e}")
                return

            company_name = sanitize_company_name(company_name) if company_name else ""

            if not company_name or company_name.lower() in self.processed_companies:
                logger.debug(f"Skipping duplicate or empty company: '{company_name}'")
                return

            # Get certifications from card (look for certification badges)
            certifications = []
            try:
                cert_elements = card.find_elements(By.CSS_SELECTOR, "[class*='certification'], [class*='badge']")
                certifications = [cert.text.strip() for cert in cert_elements if cert.text.strip()]
            except Exception:
                pass

            # Click "VIEW DETAILS" button (modal-toggle class)
            try:
                view_details_btn = card.find_element(By.CLASS_NAME, "modal-toggle")
                self.driver.execute_script("arguments[0].scrollIntoView();", view_details_btn)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", view_details_btn)
            except NoSuchElementException:
                logger.debug(f"View details button not found for {company_name}")
                return

            # Wait for modal to appear
            time.sleep(1.5)

            # Extract details from modal
            website = self._extract_website()
            phone = self._extract_phone()
            email = self._extract_email()
            location = self._extract_location()
            bus_registered = self._extract_bus_status()

            # Close details modal
            self._close_details_modal()

            # Create Installer object
            installer = Installer(
                company_name=company_name,
                website=website,
                phone=phone,
                email=email,
                location=location,
                bus_registered=bus_registered,
                certifications=certifications,
                scraped_at=datetime.now(),
                source="mcs"
            )

            self.installers.append(installer)
            self.processed_companies.add(company_name.lower())
            logger.info(f"Scraped: {company_name}")

        except Exception as e:
            logger.debug(f"Error scraping card {card_index}: {e}")
            self.failed_records.append({
                "card_index": card_index,
                "error": str(e)
            })

    def _extract_website(self) -> Optional[str]:
        """Extract website URL from details modal.

        Excludes MCS directory links, tracking domains, and policy pages.
        """
        try:
            # Website is in an <a> tag with href containing http(s)
            # Find all anchor tags that are not mailto and contain http
            website_links = self.driver.find_elements(
                By.XPATH,
                "//a[contains(@href, 'http') and not(contains(@href, 'mailto'))]"
            )

            # Domains to exclude (tracking, analytics, policy pages)
            excluded_domains = [
                'mcscertified.com', 'cookiedatabase.org', 'cookie', 'privacy-policy',
                'cloudflare', 'analytics', 'google-analytics', 'facebook.com',
                'twitter.com', 'linkedin.com', 'instagram.com', 'youtube.com',
                'cdn.', 'api.', 'trust-bank.com', 'trustabank.com'
            ]

            excluded_paths = [
                'cookie', 'privacy', 'terms', 'policy', 'gdpr', 'tcf/purposes'
            ]

            for link in website_links:
                href = link.get_attribute("href")
                if href and is_valid_url(href):
                    href_lower = href.lower()

                    # Skip excluded domains
                    if any(domain in href_lower for domain in excluded_domains):
                        continue

                    # Skip excluded paths
                    if any(path in href_lower for path in excluded_paths):
                        continue

                    # Prefer URLs with company-like patterns
                    if href_lower.startswith('http'):
                        return href

            return None
        except Exception as e:
            logger.debug(f"Error extracting website: {e}")
            return None

    def _extract_phone(self) -> Optional[str]:
        """Extract phone number from details modal."""
        try:
            # Phone is in a <p> tag within a div with class "w-full sm:w-3/5"
            # Look for <p> tags that contain phone number patterns
            p_tags = self.driver.find_elements(By.TAG_NAME, "p")

            for p_tag in p_tags:
                text = p_tag.text.strip()
                # Check if this looks like a phone number
                if text and any(char.isdigit() for char in text) and len(text) > 5:
                    sanitized = sanitize_phone_number(text)
                    if sanitized:
                        return sanitized

            return None
        except Exception as e:
            logger.debug(f"Error extracting phone: {e}")
            return None

    def _extract_email(self) -> Optional[str]:
        """Extract email address from details modal.

        Email is in an <a> tag with href="mailto:..."
        Excludes MCS generic/placeholder emails.
        """
        try:
            # Look for mailto links
            email_links = self.driver.find_elements(
                By.XPATH,
                "//a[contains(@href, 'mailto:')]"
            )

            # Emails to exclude (MCS placeholders and generic addresses)
            excluded_patterns = [
                'mcscertified.com',
                'info@',
                'contact@',
                'support@',
                'noreply@'
            ]

            for link in email_links:
                href = link.get_attribute("href")
                if href and href.startswith("mailto:"):
                    # Extract email from mailto: link
                    email = href.replace("mailto:", "").strip().lower()

                    if email and "@" in email:
                        # Skip MCS placeholder emails and generic addresses
                        if not any(pattern.lower() in email for pattern in excluded_patterns):
                            return email
                        # If we only found generic emails, return the first non-MCS one
                        if 'mcscertified' not in email:
                            return email

            return None
        except Exception as e:
            logger.debug(f"Error extracting email: {e}")
            return None

    def _extract_location(self) -> Optional[str]:
        """Extract location/address from details modal."""
        try:
            # Try multiple selectors for location field
            selectors = [
                (By.XPATH, "//label[contains(text(), 'Location')]/following-sibling::*"),
                (By.XPATH, "//*[contains(text(), 'Location')]/following-sibling::*"),
                (By.CSS_SELECTOR, "[class*='location'], [class*='address'], [data-field='location']"),
            ]

            for selector_type, selector_value in selectors:
                try:
                    location_elem = self.driver.find_element(selector_type, selector_value)
                    location = location_elem.text.strip()
                    if location:
                        return location
                except NoSuchElementException:
                    continue

            return None
        except Exception as e:
            logger.debug(f"Error extracting location: {e}")
            return None

    def _extract_bus_status(self) -> bool:
        """Extract BUS (Boiler Upgrade Scheme) registration status."""
        try:
            # BUS status is in a <p> tag within a div with class "w-full sm:w-3/5"
            # containing "Yes" or "No"
            p_tags = self.driver.find_elements(By.TAG_NAME, "p")

            for p_tag in p_tags:
                text = p_tag.text.strip().lower()
                # Look for Yes or No answers
                if text == "yes":
                    return True
                elif text == "no":
                    return False

            return False
        except Exception as e:
            logger.debug(f"Error extracting BUS status: {e}")
            return False

    def _close_details_modal(self) -> None:
        """Close the details modal if open."""
        try:
            # Try to find close button using various selectors
            close_selectors = [
                (By.CLASS_NAME, "close-modal"),
                (By.CSS_SELECTOR, "button[class*='close']"),
                (By.XPATH, "//button[contains(@class, 'close') or contains(@class, 'dismiss')]"),
                (By.CSS_SELECTOR, "[class*='modal'] button[class*='close']"),
            ]

            for selector_type, selector_value in close_selectors:
                try:
                    close_btn = self.driver.find_element(selector_type, selector_value)
                    self.driver.execute_script("arguments[0].click();", close_btn)
                    time.sleep(0.5)
                    return
                except NoSuchElementException:
                    continue

            # Fallback: try pressing Escape key or clicking outside modal
            try:
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.5)
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Error closing modal: {e}")

    def _go_to_next_page(self) -> bool:
        """Navigate to the next page of results.

        Returns:
            True if next page exists and was navigated to, False otherwise
        """
        try:
            # Scroll to bottom of page to ensure pagination is visible
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # The next button is inside a div with class "maybe-next"
            # Look for the next button specifically
            try:
                next_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "div.maybe-next a.pagination-link"
                )

                if next_btn:
                    data_page = next_btn.get_attribute("data-page")
                    logger.info(f"Found next button with data-page: {data_page}")

                    self.driver.execute_script("arguments[0].scrollIntoView();", next_btn)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    logger.info(f"Clicked next button to go to page {data_page}")
                    time.sleep(self.config.request_delay)
                    return True
            except NoSuchElementException:
                logger.info("No next button found in maybe-next div - last page reached")
                return False

        except Exception as e:
            logger.warning(f"Error navigating to next page: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    def _save_to_csv_incremental(self) -> None:
        """Save newly scraped installers to CSV incrementally.

        Appends the current batch of installers to the CSV file without
        deduplication or sorting to preserve performance. Deduplication
        happens in the final step.
        """
        if not self.installers:
            logger.debug("No new installers to save")
            return

        try:
            # Ensure output directory exists
            output_dir = Path(self.output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # Convert installers to DataFrame
            data = []
            for installer in self.installers:
                data.append({
                    'company_name': installer.company_name,
                    'website': installer.website,
                    'phone': installer.phone,
                    'email': installer.email,
                    'location': installer.location,
                    'bus_registered': installer.bus_registered,
                    'certifications': str(installer.certifications),
                    'scraped_at': installer.scraped_at.isoformat(),
                    'source': installer.source
                })

            df = pd.DataFrame(data)

            # If file doesn't exist, create it
            if not Path(self.output_path).exists():
                df.to_csv(self.output_path, index=False, encoding='utf-8')
                logger.info(f"Created CSV file with {len(df)} installers: {self.output_path}")
                self.csv_initialized = True
            else:
                # Append to existing file
                df.to_csv(self.output_path, mode='a', index=False, header=False, encoding='utf-8')
                logger.info(f"Appended {len(df)} installers to {self.output_path}")

            # Clear the installers list for the next page
            self.installers = []

        except Exception as e:
            logger.error(f"Error saving to CSV incrementally: {e}", exc_info=True)

    def _finalize_csv(self) -> None:
        """Finalize the CSV file by deduplicating and sorting.

        Reads the accumulated CSV file, removes duplicate company names
        (case-insensitive), sorts by company name, and writes back.
        """
        try:
            output_path = Path(self.output_path)

            if not output_path.exists():
                logger.warning(f"CSV file not found: {self.output_path}")
                return

            logger.info("Finalizing CSV: deduplicating and sorting...")

            # Read CSV file
            df = pd.read_csv(output_path, encoding='utf-8')
            logger.info(f"Read {len(df)} total records from CSV")

            # Deduplicate by company name (case-insensitive)
            df['company_name_lower'] = df['company_name'].str.lower()
            df_deduplicated = df.drop_duplicates(subset=['company_name_lower'], keep='first')
            df_deduplicated = df_deduplicated.drop(columns=['company_name_lower'])

            # Sort by company name (case-insensitive)
            df_sorted = df_deduplicated.sort_values('company_name', key=lambda x: x.str.lower())

            # Write back to CSV
            df_sorted.to_csv(output_path, index=False, encoding='utf-8')

            logger.info(f"Finalized CSV: {len(df_sorted)} unique installers in {self.output_path}")

        except Exception as e:
            logger.error(f"Error finalizing CSV: {e}", exc_info=True)
