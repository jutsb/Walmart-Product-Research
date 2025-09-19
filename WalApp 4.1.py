import time, csv, re, pickle, os
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException

# ---------- Config ----------
DEFAULT_ZIP = "10009"
OUTPUT_CSV = "walmart_filtered_links.csv"
STATUS_CSV = "walmart_links_status.csv"
COOKIES_FILE = "walmart_cookies.pkl"
MAX_PAGES_SAFETY = 500

MONTHS = [
    'january','february','march','april','may','june','july','august','september','october','november','december'
]
SHORT_MONTHS = {m[:3]: i+1 for i,m in enumerate(MONTHS)}

# ---------- Cookies ----------
def save_cookies(driver, path=COOKIES_FILE):
    try:
        pickle.dump(driver.get_cookies(), open(path, "wb"))
        print(f"💾 Cookies saved to {path}")
    except Exception as e:
        print(f"⚠️ Could not save cookies: {e}")

def load_cookies(driver, path=COOKIES_FILE):
    if os.path.exists(path):
        try:
            cookies = pickle.load(open(path, "rb"))
            for cookie in cookies:
                driver.add_cookie(cookie)
            print(f"✅ Cookies loaded from {path}")
        except Exception as e:
            print(f"⚠️ Could not load cookies: {e}")
    else:
        print("ℹ️ No cookies file found, starting fresh session.")

# ---------- Utilities ----------
def clean_product_link(href: str) -> str | None:
    """Normalize Walmart product/tracking URLs into canonical https://www.walmart.com/ip/XXXXX path."""
    if not href:
        return None
    href = href.strip()
    try:
        unq = unquote(href)
        if "/ip/" in unq:
            idx = unq.find("/ip/")
            part = unq[idx:]
            if "?" in part:
                part = part.split("?", 1)[0]
            if part.startswith("/ip/"):
                return "https://www.walmart.com" + part
            return part

        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        if "rd" in qs:
            rd = unquote(qs["rd"][0])
            if "/ip/" in rd:
                idx = rd.find("/ip/")
                part = rd[idx:]
                if "?" in part:
                    part = part.split("?", 1)[0]
                return "https://www.walmart.com" + part
            return rd

        if "/ip/" in href:
            idx = href.find("/ip/")
            part = href[idx:]
            if "?" in part:
                part = part.split("?", 1)[0]
            return "https://www.walmart.com" + part
    except Exception:
        return None
    return None

def ask_target_month_year() -> tuple[int,int,str]:
    """Ask the user which month-year to use for review counting.
    Accepts: 'current' or custom like 'Aug 2025' or '2025-08'.
    Returns: (month_num, year, month_display_format)
    """
    now = datetime.now()
    raw = input("Enter target month (type 'current' for current month, or e.g. 'Aug 2025' or '2025-08'): ").strip() or "current"
    raw_l = raw.lower()
    
    if raw_l == 'current':
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        return now.month, now.year, f"{month_names[now.month-1]} {now.year}"
    
    # try YYYY-MM
    m = re.match(r"^(\d{4})-(\d{1,2})$", raw)
    if m:
        y = int(m.group(1)); mo = int(m.group(2))
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        return mo, y, f"{month_names[mo-1]} {y}"
    
    # try 'Aug 2025' or 'August 2025'
    parts = raw.split()
    if len(parts) >= 2:
        mon = parts[0].lower()
        yr = parts[1]
        try:
            y = int(yr)
            mon3 = mon[:3]
            mo = SHORT_MONTHS.get(mon3)
            if mo:
                return mo, y, f"{parts[0]} {y}"
        except Exception:
            pass
    
    print("Could not parse month. Defaulting to current month.")
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return now.month, now.year, f"{month_names[now.month-1]} {now.year}"

def format_date_for_comparison(d: datetime) -> str:
    """Convert datetime to 'Mon YYYY' format for comparison (e.g., 'Apr 2025')"""
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return f"{month_names[d.month-1]} {d.year}"

def parse_review_date(text: str) -> datetime | None:
    """Parse a date from review tile text; returns datetime or None."""
    if not text:
        return None
    t = text.strip()
    t_low = t.lower()

    # Absolute date like 'August 23, 2025' or 'Aug 23, 2025' or 'Apr 14, 2025'
    months_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    abs_match = re.search(rf"{months_pattern}\s+\d{{1,2}},?\s+\d{{4}}", t, re.IGNORECASE)
    if abs_match:
        s = abs_match.group(0)
        try:
            from datetime import datetime as _dt
            # Try both full month and abbreviated formats
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d,%Y", "%b %d,%Y"]:
                try:
                    d = _dt.strptime(s, fmt)
                    return d
                except Exception:
                    continue
        except Exception:
            pass

    # Relative like '2 days ago' or 'yesterday'
    rel = re.search(r"(\d+)\s+(day|days|week|weeks|hour|hours|month|months)\s+ago", t_low)
    if rel:
        val = int(rel.group(1)); unit = rel.group(2)
        now = datetime.now()
        if 'day' in unit:
            return now - timedelta(days=val)
        if 'week' in unit:
            return now - timedelta(weeks=val)
        if 'hour' in unit:
            return now - timedelta(hours=val)
        if 'month' in unit:
            return now - timedelta(days=30*val)
    if 'yesterday' in t_low:
        return datetime.now() - timedelta(days=1)
    if 'today' in t_low:
        return datetime.now()
    return None

# ---------- Bot verification ----------
def verify_bot_detection(driver):
    """Check if bot detection is present and wait for user verification"""
    print("\n🤖 Checking for bot detection...")
    time.sleep(3)
    
    # Check for common bot detection indicators
    bot_indicators = [
        "robot", "captcha", "verify", "human", "bot", 
        "suspicious", "blocked", "access denied"
    ]
    
    page_source_lower = driver.page_source.lower()
    page_title_lower = driver.title.lower()
    
    detected = any(indicator in page_source_lower or indicator in page_title_lower 
                  for indicator in bot_indicators)
    
    if detected:
        # print("⚠️ Potential bot detection found!")
        # print("Please manually complete any verification (CAPTCHA, etc.) in the browser window.")
        input("Press ENTER after you've completed verification and the page loads normally: ")
    else:
        #print("✅ No bot detection detected. Proceeding...")
        # Still give user a chance to verify manually if needed
        print("If you see any bot detection or verification prompts, complete them now.")
        input("Press ENTER to continue with scraping: ")

def click_close_popup(driver):
    """Try to click close (X) on open modal. Multiple X selectors tried."""
    try:
        # common close buttons
        close_selectors = [
            "button[aria-label='Close']",
            "button[aria-label='close']",
            "button[class*='close']",
            "button:has(svg[aria-hidden='true'])"
        ]
        for sel in close_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    driver.execute_script("arguments[0].click();", elems[0])
                    time.sleep(0.6)
                    return True
            except Exception:
                continue
        # fallback: try to click any svg close node ancestor button
        try:
            btns = driver.find_elements(By.XPATH, "//button[.//svg and (contains(@class,'close') or contains(@aria-label,'Close') or contains(@aria-label,'close'))]")
            if btns:
                driver.execute_script("arguments[0].click();", btns[0])
                time.sleep(0.6)
                return True
        except Exception:
            pass
    except Exception:
        pass
    return False

# ---------- Browser helpers ----------
def collect_links_from_search_page(driver):
    """Collect cleaned product links on the currently loaded search results page."""
    time.sleep(1)  # let lazy load finish
    elems = driver.find_elements(By.CSS_SELECTOR, "a[link-identifier], a[href*='/ip/']")
    links = set()
    for e in elems:
        try:
            href = e.get_attribute('href')
            cl = clean_product_link(href)
            if cl:
                links.add(cl)
        except Exception:
            continue
    return links

def click_next(driver) -> bool:
    selectors = [
        "a[data-testid='NextPage']",
        "button[aria-label='Next Page']",
        "a[aria-label='Next Page']",
    ]
    for sel in selectors:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            if btns:
                btn = btns[0]
                if btn.is_displayed():
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1.2)
                        return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False

# ---------- Enhanced Product filter ----------
def extract_brand_from_page(driver) -> str:
    """Try multiple methods to extract the product brand (ItemBrandLink or 'Visit the store Brand' text)."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, '[data-dca-name="ItemBrandLink"]')
        txt = (el.text or "").strip()
        if txt:
            return txt
    except Exception:
        pass
    # fallback: brand link selector
    try:
        el = driver.find_element(By.CSS_SELECTOR, "a[data-automation-id='brand-link'], a.brand-link")
        txt = (el.text or "").strip()
        if txt:
            return txt
    except Exception:
        pass
    # fallback: find 'Visit the store' text and extract brand following it if present on page
    try:
        # find element that contains 'Visit the store'
        nodes = driver.find_elements(By.XPATH, "//*[contains(., 'Visit the store') or contains(., 'Visit Store')]")
        for n in nodes:
            t = (n.text or "")
            if 'Visit the store' in t:
                # try to extract brand following phrase
                m = re.search(r"Visit the store\s*(.*)", t, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip()
                    # cleanup
                    candidate = re.sub(r"[^A-Za-z0-9 &-]", "", candidate).strip()
                    if candidate:
                        return candidate
    except Exception:
        pass
    return ""

def sort_reviews_by_most_recent(driver) -> bool:
    """Enhanced function to sort reviews by 'Most recent' with multiple approaches."""
    try:
        print("  📅 Attempting to sort reviews by 'Most recent'...")
        
        # Method 1: Look for dropdown button with "Most relevant" or similar text and click it
        try:
            # Your specific selector for the sort button
            sort_button = driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Sort by"]')
            if sort_button and sort_button.is_displayed():
                print("    → Found sort dropdown button, clicking...")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", sort_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", sort_button)
                time.sleep(1.0)
                
                # Now look for "Most recent" option in the dropdown
                recent_options = driver.find_elements(By.XPATH, "//*[contains(text(), 'Most recent') or contains(text(), 'Most Recent') or contains(text(), 'Newest')]")
                for opt in recent_options:
                    try:
                        if opt.is_displayed():
                            print("    → Found 'Most recent' option, selecting...")
                            driver.execute_script("arguments[0].click();", opt)
                            time.sleep(1.0)
                            return True
                    except Exception:
                        continue
        except Exception as e:
            print(f"    → Sort button method failed: {e}")
        
        # Method 2: Look for any button/element containing sort-related classes
        try:
            sort_candidates = driver.find_elements(By.CSS_SELECTOR, 
                "button[class*='sort'], div[class*='sort'], button[data-testid*='sort']")
            for candidate in sort_candidates:
                try:
                    if candidate.is_displayed() and ('sort' in candidate.get_attribute('class').lower() or 
                                                     'sort' in (candidate.get_attribute('aria-label') or '').lower()):
                        driver.execute_script("arguments[0].click();", candidate)
                        time.sleep(1.0)
                        
                        # Look for recent options after click
                        recent_options = driver.find_elements(By.XPATH, "//*[contains(text(), 'Most recent') or contains(text(), 'Newest') or contains(text(), 'Recent')]")
                        for opt in recent_options:
                            if opt.is_displayed():
                                driver.execute_script("arguments[0].click();", opt)
                                time.sleep(1.0)
                                return True
                except Exception:
                    continue
        except Exception:
            pass
        
        # Method 3: Direct search for clickable "Most recent" text (fallback from original)
        try:
            mr_candidates = driver.find_elements(By.XPATH, "//*[contains(text(), 'Most recent') or contains(text(), 'Most Recent') or contains(text(), 'Newest')]")
            for mc in mr_candidates:
                try:
                    if mc.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", mc)
                        driver.execute_script("arguments[0].click();", mc)
                        time.sleep(1.0)
                        print("    → Successfully clicked 'Most recent' text")
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        
        # Method 4: Look for select dropdowns
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            for s in selects:
                try:
                    for opt in s.find_elements(By.TAG_NAME, "option"):
                        opt_text = (opt.text or '').lower()
                        if 'most recent' in opt_text or 'newest' in opt_text or 'recent' in opt_text:
                            opt.click()
                            time.sleep(1.0)
                            print("    → Successfully selected 'Most recent' from dropdown")
                            return True
                except Exception:
                    continue
        except Exception:
            pass
            
        print("    → Could not find or click 'Most recent' sort option")
        return False
        
    except Exception as e:
        print(f"    → Error in sort_reviews_by_most_recent: {e}")
        return False

def product_passes_filters(driver, product_url: str, target_month: int, target_year: int, target_display: str) -> tuple[bool, str]:
    """
    Opens a product page and applies the requested filters.
    
    This function performs a series of checks on a product page to determine if it meets
    certain criteria, such as having multiple sellers and recent reviews.
    
    Args:
        driver (WebDriver): The Selenium WebDriver instance.
        product_url (str): The URL of the product page to check.
        target_month (int): The month (1-12) to check for reviews.
        target_year (int): The year to check for reviews.
        target_display (str): A string representing the target month/year for logging.
    
    Returns:
        Tuple[bool, str]: A tuple containing a boolean indicating if the product passes
                         the filters, and a string with a reason (or an empty string
                         if it passes).
    """
    try:
        driver.get(product_url)
        time.sleep(1.0)

        brand_name = extract_brand_from_page(driver)
        brand_l = brand_name.lower() if brand_name else ""

        # 1) Check for multiple sellers
        compare_clicked = False
        try:
            compare_candidates = driver.find_elements(By.XPATH,
                "//*[contains(@aria-label, 'Compare all') or contains(@aria-label, 'Compare all sellers') or contains(., 'Compare all sellers') or contains(., 'See all sellers') or contains(., 'See all options')]")
            
            # If no "Compare all sellers" button is found, discard the product.
            if not compare_candidates:
                return False, "Discarded: Only Single Seller Found"

            # Click the first candidate found
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", compare_candidates[0])
                driver.execute_script("arguments[0].click();", compare_candidates[0])
                compare_clicked = True
                time.sleep(1.0)
            except Exception:
                compare_clicked = False
        except Exception:
            compare_clicked = False

        # If the "Compare" popup opened, check the sellers within it.
        if compare_clicked:
            # NEW: Check for "Sold and shipped by Walmart.com" using a more reliable selector
            try:
                # This XPath looks for an element with the exact aria-label from your HTML snippet
                if driver.find_elements(By.XPATH, "//span[@aria-label='Sold and shipped by Walmart.com']"):
                    click_close_popup(driver)
                    return False, "Discarded: Walmart is Selling Itself"
            except Exception:
                pass
            
            seller_names = []
            try:
                # Try multiple selectors to find seller names
                seller_selectors = [
                    "a[data-automation-id='seller-name-link']",
                    "div[data-automation-id='seller-name']",
                    "span[class*='seller']",
                    "li.seller",
                    "div.seller"
                ]
                for sel in seller_selectors:
                    try:
                        elems = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in elems:
                            txt = (el.text or "").strip()
                            if txt:
                                seller_names.append(txt)
                    except Exception:
                        continue
                # Remove duplicates and normalize seller names
                seller_names = list(dict.fromkeys([s.strip() for s in seller_names if s.strip()]))
            except Exception:
                seller_names = []
                
            # Discard if the brand name is found in the list of sellers.
            if brand_l and any(brand_l in s.lower() for s in seller_names):
                click_close_popup(driver)
                return False, f"Discarded: brand-store seller '{brand_name}' detected in sellers list"

            # Discard if a specific "Visit the store <Brand>" link is found.
            if any(re.search(r"visit\s+the\s+store\s+" + re.escape(brand_name), s, re.IGNORECASE) for s in seller_names if brand_name):
                click_close_popup(driver)
                return False, f"Discarded: 'Visit the store {brand_name}' found in sellers popup"

            # Close the popup before proceeding.
            click_close_popup(driver)

        # 2) Navigate to the reviews section
        try:
            rev_link = None
            try:
                # Try common review link selectors
                rev_link = driver.find_element(By.CSS_SELECTOR, "[data-testid='item-review-section-link']")
            except Exception:
                try:
                    rev_link = driver.find_element(By.CSS_SELECTOR, "a[data-automation-id='reviews-link'], a.reviews-link, a[href*='#customer-reviews']")
                except Exception:
                    rev_link = None

            if not rev_link:
                return False, "Discarded: No ratings yet"

            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", rev_link)
                driver.execute_script("arguments[0].click();", rev_link)
            except Exception:
                try:
                    rev_link.click()
                except Exception:
                    pass
            time.sleep(1.0)
        except Exception:
            return False, "Discarded: failed to open reviews"

        # 3) Sort reviews by "Most recent"
        sort_success = sort_reviews_by_most_recent(driver)
        if sort_success:
            print("     → Successfully sorted by 'Most recent'")
        else:
            print("     → Warning: Could not sort by 'Most recent', continuing anyway...")

        # 4) Count reviews from the target month and year
        time.sleep(0.6)
        
        review_elements = []
        try:
            date_divs = driver.find_elements(By.CSS_SELECTOR, "div.f7.gray")
            review_elements.extend(date_divs)
        except Exception:
            pass
        
        try:
            date_pattern_divs = driver.find_elements(By.XPATH, "//div[contains(text(), '2024') or contains(text(), '2025') or contains(text(), '2026')]")
            review_elements.extend(date_pattern_divs)
        except Exception:
            pass
        
        try:
            review_tiles = driver.find_elements(By.CSS_SELECTOR, "[data-automation-id*='review'], li[class*='review'], div[class*='review'], div[data-testid*='review']")
            review_elements.extend(review_tiles)
        except Exception:
            pass

        if not review_elements:
            try:
                review_elements = driver.find_elements(By.XPATH, "//div[contains(@class,'review') or contains(@data-automation-id,'review') or contains(@data-testid,'review')]")
            except Exception:
                pass

        count_in_month = 0
        scanned = 0
        max_scan = 150
        dates_found = []
        
        unique_review_elements = list(set(review_elements))

        for elem in unique_review_elements:
            if scanned >= max_scan:
                break
            scanned += 1
            try:
                txt = elem.text or elem.get_attribute('innerText') or ''
                
                if not any(month in txt for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                    try:
                        date_elem = elem.find_element(By.CSS_SELECTOR, "div.f7.gray, .date, [class*='date']")
                        txt = date_elem.text or date_elem.get_attribute('innerText') or ''
                    except:
                        try:
                            parent = elem.find_element(By.XPATH, "..")
                            date_elem = parent.find_element(By.CSS_SELECTOR, "div.f7.gray")
                            txt = date_elem.text or date_elem.get_attribute('innerText') or ''
                        except:
                            pass
                            
            except Exception:
                txt = ''
            
            if txt.strip():
                d = parse_review_date(txt)
                if d:
                    date_format = format_date_for_comparison(d)
                    dates_found.append(date_format)
                    if d.month == target_month and d.year == target_year:
                        count_in_month += 1

        if dates_found:
            unique_dates = sorted(set(dates_found))
            print(f"     → Dates found in reviews: {', '.join(unique_dates)} (looking for {target_display})")
        else:
            print(f"     → No parseable dates found in {scanned} elements")

        # NEW LOGIC: Check for "Review from" as a separate, immediate filter
        #try:
            # Check for a specific element that contains the text "Review from" and has the class 'gray'.
           # if driver.find_elements(By.XPATH, "//span[contains(@class, 'gray') and contains(text(), 'Review from')]"):
             #   return False, "Discarded: 'Review from' phrase found."
       # except Exception:
         #   pass

        # Final check based on review count.
        if count_in_month < 5:
            return False, f"Discarded: Only {count_in_month} reviews in target {target_display}."
        else:
            return True, f"PASS: Product has {count_in_month} reviews in target {target_display}."

    except Exception as e:
        return False, f"Error during check: {e}"

# ---------- Main pipeline ----------
def run_scraper():
    print("=== Walmart Link Scraper + Filters ===")
    #keyword = input("Enter search keyword (blank for full URL): ").strip()
    #if not keyword:
        #base_url = input("Paste full Walmart search URL: ").strip()
        #use_full_url = True
    #else:
    base_url = "https://www.walmart.com/"
    use_full_url = True
    choice = input("Pages: 1=Single, 2=All, 3=Range (default 2): ").strip() or "2"
    single_page, range_start, range_end, scrape_all = None, None, None, False
    if choice == "1":
        single_page = int(input("Enter page (default 1): ") or "1")
    elif choice == "3":
        r = input("Enter range (e.g. 2-5): ")
        try:
            s,e = r.split("-"); range_start, range_end = int(s), int(e)
        except: return
    else:
        scrape_all = True

    target_month, target_year, target_display = ask_target_month_year()
    #zip_code = input(f"Enter ZIP (default {DEFAULT_ZIP}): ").strip() or DEFAULT_ZIP
    zip_code = DEFAULT_ZIP
    print("\nOpening browser...")
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--incognito")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=VizDisplayCompositor")
    
    driver = uc.Chrome(options=options, headless=False)
    driver.set_window_size(1400,900)

    def make_url(page):
        if use_full_url:
            url = base_url
            if "page=" not in url:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}page={page}"
            return url
        else:
            q = keyword.replace(" ","+")
            return f"https://www.walmart.com/search?q={q}&zipcode={zip_code}&page={page}"

    collected_all, passed_links, status_rows = [], [], []

    try:
        # Navigate to initial page for bot verification
        initial_url = make_url(1)
        print(f"\nNavigating to: {initial_url}")
        driver.get(initial_url)
        
        # Perform bot verification check at startup
        verify_bot_detection(driver)
        
        # Load cookies after verification
        load_cookies(driver)
        driver.refresh()
        time.sleep(2)

        if single_page:
            if single_page != 1:  # If not page 1, navigate to the correct page
                url = make_url(single_page)
                driver.get(url)
                time.sleep(2)
            links = collect_links_from_search_page(driver)
            collected_all.extend(links)
        elif range_start:
            for pg in range(range_start, range_end+1):
                if pg != 1:  # Skip navigation for page 1 as we're already there
                    url = make_url(pg)
                    driver.get(url)
                    time.sleep(2)
                links = collect_links_from_search_page(driver)
                collected_all.extend(links)
                print(f"Page {pg}: Found {len(links)} links")
        else:
            pg = 1
            while True:
                links = collect_links_from_search_page(driver)
                collected_all.extend(links)
                print(f"Page {pg}: Found {len(links)} links")
                if pg >= MAX_PAGES_SAFETY: 
                    print(f"Reached safety limit of {MAX_PAGES_SAFETY} pages")
                    break
                if not click_next(driver): 
                    print("No more pages found")
                    break
                pg += 1

        # Deduplicate while preserving order
        seen = set()
        ordered_links = []
        for l in collected_all:
            if l not in seen:
                seen.add(l)
                ordered_links.append(l)

        print(f"\nCollected {len(ordered_links)} unique products. Starting filtering...")

        try:
            for idx, link in enumerate(ordered_links, 1):
                print(f"\n[{idx}/{len(ordered_links)}] Checking: {link}")
                passed, reason = product_passes_filters(driver, link, target_month, target_year, target_display)
                status = "PASS" if passed else "FAIL"
                status_rows.append({'product_link':link,'status':status,'reason':reason})
                if passed: 
                    passed_links.append(link)
                    print(f"  ✅ PASSED: {reason}")
                else:
                    print(f"  ❌ FAILED: {reason}")
        except KeyboardInterrupt:
            print("\n⏸️ Interrupted! Saving partial results...")

    finally:
        save_cookies(driver)
        try: 
            driver.quit()
        except: 
            pass

    # Save results
    if passed_links:
        with open(OUTPUT_CSV,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(["product_link"])
            for l in passed_links: 
                w.writerow([l])
        print(f"✅ Saved {len(passed_links)} passing links to {OUTPUT_CSV}")
    else:
        print("❌ No links passed the filters")
        
    if status_rows:
        with open(STATUS_CSV,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=["product_link","status","reason"])
            w.writeheader()
            w.writerows(status_rows)
        print(f"📄 Status log saved to {STATUS_CSV}")
    
    print(f"\n📊 Summary:")
    print(f"   Total products found: {len(ordered_links)}")
    print(f"   Passed filters: {len(passed_links)}")
    print(f"   Failed filters: {len(status_rows) - len(passed_links)}")

if __name__=="__main__":
    run_scraper()