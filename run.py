# run.py
import logging
import json
import sys
import os

# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Optional: Print the sys.path to confirm your project root directory is included
print("Python Path:", sys.path)

from utilities.SearchWeb import search_addresses
from utilities.Ranking_Readable import process_folder
from utilities.filter_buildingsites import filter_buildingsites

from enrichment.rankedsearch_enrichment import main as enrichment_step
from enrichment.web_zimmo import enrich_zimmo_data
from enrichment.amenities_enrichment import enrich_amenities_data
from enrichment.reversegeo import process_geojson

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Paths
INPUT_GEOJSON = "data/Belgium_polygon_sample.geojson"
OUTPUT_STEP1 = "data/polygon_addresses.json"
OUTPUT_DIR_FOUND = "data/Found_Docs"
OUTPUT_DIR_NOT_FOUND = "data/NotFound_Docs"
RERANKED_OUTPUT_DIR = "data/Reranked_Docs"
OUTPUT_STEP4 = "data/Search_enriched_buildingsites_with_attributes.json"
OUTPUT_STEP5 = "data/Web&SearchRAG_enriched_buildingsites_with_attributes.json"
FILTERED_OUTPUT = "data/cleaned_buildingsites_with_attributes.json"
FAILED_OUTPUT = "data/failed_attempts.json"
FINAL_OUTPUT = "data/enriched_amenities_results.json"

# Selenium Function: Retrieve Zimmo Cookie
def get_zimmo_cookie():
    """Retrieve the Zimmo cookie using Selenium."""
    chrome_driver_path = "/home/djameldino/chromedriver-linux64/chromedriver"
    service = Service(chrome_driver_path)
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")  # Disable GPU for better compatibility
    driver = webdriver.Chrome(service=service, options=options)

    try:
        logging.info("Opening Zimmo website to fetch cookies...")
        driver.get("https://www.zimmo.be/")
        cookies = driver.get_cookies()
        cookie_string = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
        logging.info("Successfully retrieved Zimmo cookies.")
        return cookie_string

    except Exception as e:
        logging.error(f"Error fetching Zimmo cookies: {e}")
        raise
    finally:
        driver.quit()
def validate_output(file_path):
    """Check if the output JSON contains any None or null values."""
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    found_nulls = False

    for entry in data:
        for address in entry.get("all_addresses", []):
            for key, value in address.items():
                if value is None:  # Check if any value is None
                    logging.warning(f"⚠ Found None in {key} of entry ID {entry['id']}")
                    found_nulls = True

    if found_nulls:
        logging.error("❌ Validation failed: Some attributes contain None values.")
    else:
        logging.info("✅ Validation passed: No None values found in the output.")

def main():
    """Main function to orchestrate the pipeline."""
    logging.info("Starting the geocoding pipeline...")
    process_geojson(INPUT_GEOJSON, OUTPUT_STEP1)
    logging.info(f"Address enrichment completed. Output saved to {OUTPUT_STEP1}")

    logging.info("Starting the web search process...")
    search_addresses(OUTPUT_STEP1, OUTPUT_DIR_FOUND, OUTPUT_DIR_NOT_FOUND)
    logging.info("Web search completed.")

    logging.info("Starting the re-ranking and summarization process...")
    process_folder(OUTPUT_DIR_FOUND, RERANKED_OUTPUT_DIR, model="gpt-3.5-turbo")
    logging.info("Re-ranking and summarization completed.")

    logging.info("Starting attribute enrichment step...")
    enrichment_step()
    logging.info("Attribute enrichment step completed.")

    logging.info("Validating enriched output...")
    validate_output(OUTPUT_STEP4)

    logging.info("Fetching Zimmo cookies...")
    zimmo_cookie = get_zimmo_cookie()

    logging.info("Starting Zimmo enrichment process...")
    enrich_zimmo_data(
        input_file=OUTPUT_STEP4,
        output_file=OUTPUT_STEP5,
        stats_file="data/zimmostatsrag.txt",
        zimmo_cookie=zimmo_cookie,
    )

    logging.info("Zimmo enrichment completed.")
    validate_output(OUTPUT_STEP5)

    # Filter the enriched dataset to create a cleaned dataset
    logging.info("Filtering enriched dataset...")
    summary = filter_buildingsites(OUTPUT_STEP5, FILTERED_OUTPUT, FAILED_OUTPUT)
    logging.info(f"Filtering completed with stats: {summary}")

    # FINAL STEP: Address & Amenities Matching using CLEANED DATASET
    logging.info("Starting address-amenities enrichment...")
    enrich_amenities_data(FILTERED_OUTPUT, FINAL_OUTPUT)
    logging.info("Final enrichment completed.")

if __name__ == "__main__":
    main()

