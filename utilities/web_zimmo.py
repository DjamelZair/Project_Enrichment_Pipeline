import httpx
from bs4 import BeautifulSoup
import json
from urllib.parse import quote
from rapidfuzz import fuzz
import logging
from validation.extract_text import rule_based_extract_attributes  # Import fallback attribute extraction
from utilities.Attributes_RAG import translate_text, extract_attributes_chunk
from customLLM.extract_mistral import extract_attributes_with_mistral
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global counters
zimmo_count = 0
successful_enrichments = 0
attribute_counts = []
fallback_usage = {}

complementary_metrics = {
    "pre_enriched_found": 0,       # When Zimmo confirms a pre-enriched value
    "not_specified_to_value": 0,   # When Zimmo replaces 'Not Specified' with a value
    "zimmo_skipped_due_to_pre_enrichment": 0  # When Zimmo finds a different value but cannot overwrite
}

# Initialize fallback tracking
attribute_keys = [
    "project_type", "delivery_date", "investment_option",
    "available_sizes", "ground_area", "price_from",
    "number_of_bathrooms", "number-of_bedrooms", "number_of_wcs", "parking"
]
for key in attribute_keys:
    fallback_usage[key] = {"used": 0, "success": 0}


def enrich_zimmo_data(input_file, output_file, stats_file, zimmo_cookie):
    """
    Main function to scrape data from Zimmo, enrich the input JSON entries,
    and track global metrics.
    """
    global zimmo_count, successful_enrichments, attribute_counts

    # Headers for Zimmo
    zimmo_headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": zimmo_cookie,
    }

    # Load input data
    with open(input_file, "r") as file:
        original_data = json.load(file)

    # Zimmo scraping
    with httpx.Client(headers=zimmo_headers) as zimmo_session:
        for entry in original_data:
            all_addresses = entry["all_addresses"]

            for address in all_addresses:
                # Combine village and town into a single set of possible locations
                location_combinations = set(address.get("village", []) + address.get("town", []))
                postcode = address.get("postcode", "").strip()
                road = " ".join(address.get("road", [])).strip()

                for location in location_combinations:
                    zimmo_properties = scrape_zimmo_main_page(location, postcode, zimmo_session)

                    for property_item in zimmo_properties:
                        property_address = property_item["address"].lower()

                        # Fuzzy match on road name in the property address
                        if (road.lower() in property_address 
                            or fuzz.partial_ratio(road.lower(), property_address) > 95):
                            logger.info(f"Match found: {road} in {property_address}")
                            logger.info(f"Project link: https://www.zimmo.be{property_item['link']}")

                            zimmo_details = scrape_zimmo_detail_page(property_item["link"], zimmo_session)
                            if zimmo_details:
                                enrich_address(entry, zimmo_details, address)
                                break  # proceed to next address

    # Save enriched data
    with open(output_file, "w") as file:
        json.dump(original_data, file, indent=4, ensure_ascii=False)

    # Save fallback statistics
    save_fallback_statistics(stats_file)

    # Final logging
    logger.info(f"Enriched data saved to {output_file}")
    logger.info(f"Total Zimmo enrichments: {zimmo_count}")
    logger.info(f"Success ratio: {successful_enrichments}/{zimmo_count}")
    avg_attributes = sum(attribute_counts) / len(attribute_counts) if attribute_counts else 0
    logger.info(f"Average enriched attributes per entry: {avg_attributes}")

    logger.info("Complementary Metrics:")
    logger.info(f"Pre-enriched values confirmed by Zimmo: {complementary_metrics['pre_enriched_found']}")
    logger.info(f"Attributes updated from 'Not Specified': {complementary_metrics['not_specified_to_value']}")
    logger.info(f"Zimmo skipped updates due to pre-enrichment: {complementary_metrics['zimmo_skipped_due_to_pre_enrichment']}")


def enrich_address(entry, new_data, match_address):
    """
    Enriches the given match_address within the entry using new_data from Zimmo.
    Increments global counters only if actual enrichment occurs (total_enriched_count > 0).
    """
    global zimmo_count, successful_enrichments, attribute_counts, complementary_metrics

    total_enriched_count = 0

    for addr in entry["all_addresses"]:
        if addr == match_address:
            logger.info(f"Enriching address: {addr.get('road', 'Unknown Road')}")

            for key, new_value in new_data.items():
                if key not in addr:
                    addr[key] = None

                current_value = addr.get(key)

                if current_value in [None, "Not Specified", "Not mentioned"] and new_value != "Not Specified":
                    addr[key] = new_value
                    total_enriched_count += 1
                    complementary_metrics["not_specified_to_value"] += 1
                    logger.info(f"Updated {key}: {current_value} -> {new_value}")

                elif current_value == new_value and current_value not in [None, "Not Specified"]:
                    complementary_metrics["pre_enriched_found"] += 1

                elif (current_value not in [None, "Not Specified"] 
                      and current_value != new_value 
                      and new_value != "Not Specified"):
                    complementary_metrics["zimmo_skipped_due_to_pre_enrichment"] += 1

    if total_enriched_count > 0:
        zimmo_count += 1
        successful_enrichments += 1
        attribute_counts.append(total_enriched_count)


def scrape_zimmo_main_page(location, postcode, session, base_url="https://www.zimmo.be"):
    """
    Scrapes the main page based on a location+postcode and returns a list of properties
    with 'address' and 'link'.
    """
    if location.lower() == "unknown location":
        return []

    properties = []
    location_encoded = quote(location)
    url = f"{base_url}/nl/{location_encoded}-{postcode}/te-koop/#gallery"

    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for item in soup.find_all("div", class_="property-item"):
            address_div = item.find("div", class_="property-item_address")
            link_tag = item.find("a", class_="property-item_link")
            if address_div and link_tag:
                address = address_div.get_text(strip=True).replace("\n", " ")
                detail_link = link_tag["href"]
                properties.append({"address": address, "link": detail_link})

    except Exception as e:
        logger.error(f"Error scraping Zimmo main page {url}: {e}")

    return properties


def scrape_zimmo_detail_page(detail_url, session, base_url="https://www.zimmo.be"):
    """
    Scrapes the detail page for a specific property. Extracts attributes using Mistral AI.You 
    change the language model here.
    """
    try:
        response = session.get(f"{base_url}{detail_url}", timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        description_section = soup.find("section", id="description")
        description = description_section.get_text(strip=True) if description_section else "Not Specified"
        logger.info(f"🔍 Description found: {description[:300]}...")  # Log first 300 chars for debugging

        # 🔹 Use Mistral AI for extraction
        main_attributes = extract_attributes_with_mistral(description) # Change the language modeland its function depending on your wishes. 

        # Log the full structured response
        logger.info(f"📩 Mistral Extracted Attributes: {json.dumps(main_attributes, indent=2)}")

        def extract_table_value(attribute_key):
            """
            Retrieves extracted values from Mistral AI results, ensuring 'Not Specified' for missing values.
            """
            value = main_attributes.get(attribute_key, "Not Specified")
            if value == "Not Specified":
                logger.warning(f"⚠ Warning: Mistral did not return {attribute_key}")
            return value

        return {
            "project_type": extract_table_value("project_type"),
            "delivery_date": extract_table_value("delivery_date"),
            "investment_option": extract_table_value("investment_option"),
            "available_sizes": extract_table_value("available_sizes"),
            "price_from": extract_table_value("price_from"),
            "number_of_bathrooms": extract_table_value("number_of_bathrooms"),
            "number_of_bedrooms": extract_table_value("number_of_bedrooms"),
            "number_of_wcs": extract_table_value("number_of_wcs"),
            "parking": extract_table_value("parking"),
            "description": description,
        }

    except Exception as e:
        logger.error(f"🔥 Error scraping Zimmo detail page {detail_url}: {e}")
        return {"error": str(e)}

def save_fallback_statistics(file_path):
    """
    Saves the fallback usage statistics (how many times it was used, how many successes)
    to a JSON stats file.
    """
    with open(file_path, "w") as stats_file:
        json.dump(fallback_usage, stats_file, indent=4)
