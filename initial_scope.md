MCS Heat Pump Installer List Scraper - Requirements

  Project: PPL List Builder
  Purpose: Scrape UK heat pump installers from MCS Directory and export to
  CSV

  Functional Requirements

  1. Web Scraping
    - Navigate to: https://www.mcscertified.com/find-an-installer
    - Filter: Air Source Heat Pump, Exhaust Air Heat Pump, Ground/Water
  Source Heat Pump
    - Handle JavaScript pagination (186 pages, 12 results per page = ~2,200
  installers)
  2. Data Extraction (per installer)
    - Company name
    - Website URL
    - Phone number
    - Location/Address
    - BUS (Boiler Upgrade Scheme) registration status (Yes/No)
    - Heat pump type(s) certified for (Air Source, Ground/Water, Exhaust)
  3. Data Collection Method
    - Iterate through all pagination pages
    - For each company card: Extract visible data
    - Click "VIEW DETAILS" link to access: website, phone, address, BUS
  status
    - Return to list and continue to next page
  4. Output
    - CSV file: heat-pump-installers.csv
    - Columns: Company Name | Website | Phone | Location | BUS Registered |
  Certifications
    - No duplicates
    - Sorted by company name (optional)

  Technical Requirements

  - Language: Python
  - Browser automation: Selenium + ChromeDriver
  - Dependencies: selenium, webdriver-manager, pandas (for CSV export)
  - Error handling: Skip broken links, retry on timeout, log errors
  - Performance: Complete 2,200 scrapers in ~10-15 minutes
  - Testing: Verify first 5 pages manually before full run

  Constraints

  - Respect rate limiting (add delays between requests)
  - Don't hammer the server (1-2 sec delay between page clicks)
  - Headless browser (optional - for speed)
  - Should be able to restart mid-run if it fails