# Walmart Product Scraper (Python + Selenium)

## Overview
This project is a Walmart product scraper built with Python and Selenium.
It is designed for dropshippers, ecommerce researchers, and product hunters who want to:
- Collect product links from Walmart
- Filter products by sellers (exclude single-seller and Walmart-only products)
- Extract review counts and sort reviews by most recent
- Count reviews for a specific month (user input)
- Export results into structured CSV reports

## Features
- Scrapes Walmart product listings automatically
- Filters out items sold by only Walmart or single sellers
- Extracts reviews and sorts by most recent
- Counts reviews for a specific month/year
- Saves results in CSV format:
  - `passing_products.csv` → products that match criteria
  - `all_results.csv` → full scraping log

## Tech Stack
- Python 3.10+
- Selenium with undetected ChromeDriver
- Pandas for CSV export
- Time & re libraries for delays and regex parsing

## Project Structure
```
├── WalApp 4.1.py           # Main scraper script
├── passing_products.csv    # Filtered products output
├── all_results.csv         # Full scraped data
└── README.md              # Project documentation
```

## Setup & Installation

1. Clone the repo:
```bash
git clone https://github.com/your-username/walmart-product-scraper.git
cd walmart-product-scraper
```

2. Install required libraries:
```bash
pip install selenium pandas undetected-chromedriver
```

3. Run the scraper:
```bash
python "WalApp 4.1.py"
```

4. Enter your target month/year when prompted (e.g. September 2025)

## Example Output

### CSV Export (passing_products.csv)
| Product Title | Link | Seller | Review Count (Sep 2025) |
|---------------|------|--------|-------------------------|
| Wireless Bluetooth Headphones | https://walmart.com/xyz | ABC Sellers | 120 |
| Kitchen Knife Set | https://walmart.com/abc | BestMart | 95 |

## Future Improvements
- Add AliExpress + eBay integration for cross-platform product matching
- Build a GUI (Tkinter/PySide6) for easier use
- Deploy as a web dashboard for real-time product research

## Author
Developed by Muhammad

For freelancing & collaboration: https://www.linkedin.com/in/muhammadjk/  
Email: mhm.jutk@gmail.com