import json
import httpx
import time
from geopy.distance import geodesic
from bs4 import BeautifulSoup
import logging

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Buffer size in meters
BUFFER_SIZE = 500

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def query_amenities(lat, lon, radius):
    """
    Query nearby amenities using Overpass API.
    """
    query = f"""
    [out:json];
    (
        node["amenity"](around:{radius},{lat},{lon});
        way["amenity"](around:{radius},{lat},{lon});
        relation["amenity"](around:{radius},{lat},{lon});
    );
    out center;
    """
    retries = 3
    for attempt in range(retries):
        try:
            response = httpx.post(OVERPASS_URL, data={"data": query}, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logging.warning(f"Failed to fetch amenities, attempt {attempt + 1}")
        except httpx.ReadTimeout:
            logging.warning(f"Timeout for amenities query, attempt {attempt + 1}")
            time.sleep(2)
    return None


def extract_zimmo_details(soup):
    """
    Extract details from Zimmo HTML page.
    """
    def extract_table_attributes(section_id):
        attributes = {}
        section = soup.find("section", id=section_id)
        if section:
            rows = section.find_all("div", class_="row table-row")
            for row in rows:
                key = row.find(class_="info-name").get_text(strip=True)
                value = row.find(class_="info-value").get_text(strip=True)
                key = key.replace("Aantal ", "").lower().replace(" ", "_")  # Normalize key
                attributes[key] = value
        return attributes

    # Extract project details
    construction = extract_table_attributes("construction")
    certificates = extract_table_attributes("certificates")

    # Basic details
    description = soup.find("section", id="description").get_text(strip=True) if soup.find("section", id="description") else "Not Specified"
    price = soup.find("strong", string="Prijs").find_next("span", class_="feature-value").get_text(strip=True) if soup.find("strong", string="Prijs") else "Not Specified"

    return {
        "description": description,
        "price": price,
        **construction,
        **certificates
    }


def enrich_amenities_data(input_file, output_file):
    """
    Enrich building site data with nearby amenities from OpenStreetMap.
    
    Args:
    - input_file: Path to the JSON file containing enriched building sites.
    - output_file: Path where the final enriched dataset will be saved.
    """
    logging.info(f"Loading cleaned dataset from {input_file}...")
    
    with open(input_file, "r") as file:
        data = json.load(file)

    total_features = len(data)
    features_with_amenities = 0

    for i, feature in enumerate(data):
        logging.info(f"Processing feature {i+1}/{total_features}")

        for addr in feature.get('all_addresses', []):
            lat, lon = float(addr['lat']), float(addr['lon'])

            logging.info(f"Querying amenities for: {addr.get('road', 'Unknown Road')}, {addr.get('postcode', 'Unknown Postal Code')}")

            # Query nearby amenities
            amenities = query_amenities(lat, lon, BUFFER_SIZE)

            if amenities and 'elements' in amenities and len(amenities['elements']) > 0:
                features_with_amenities += 1
                addr['amenities'] = {}
                closest_amenities = {}

                for amenity in amenities['elements']:
                    if 'tags' in amenity:
                        # Extract coordinates
                        if 'lat' in amenity and 'lon' in amenity:
                            amenity_lat, amenity_lon = amenity['lat'], amenity['lon']
                        elif 'center' in amenity:  # Use 'center' for ways or relations
                            amenity_lat, amenity_lon = amenity['center']['lat'], amenity['center']['lon']
                        else:
                            continue  # Skip if coordinates are missing

                        # Calculate distance
                        distance = geodesic((lat, lon), (amenity_lat, amenity_lon)).meters
                        amenity_type = amenity['tags'].get('amenity', 'unknown')

                        # Update only if closer
                        if amenity_type not in closest_amenities or distance < closest_amenities[amenity_type]['distance_meters']:
                            closest_amenities[amenity_type] = {
                                **amenity['tags'],
                                "distance_meters": round(distance, 2)
                            }

                addr['amenities'] = closest_amenities
            else:
                addr['amenities'] = "No amenities found"

        # Combine with Zimmo details if available
        zimmo_details = extract_zimmo_details(BeautifulSoup("<html></html>", "html.parser"))
        feature.update(zimmo_details)

    # Save the enriched dataset
    with open(output_file, "w") as outfile:
        json.dump(data, outfile, indent=4)

    logging.info(f"Enrichment completed. {features_with_amenities}/{total_features} features contain amenities.")
    logging.info(f"Enriched data saved to {output_file}")


# For standalone execution
if __name__ == "__main__":
    input_file = "data/cleaned_buildingsites_with_attributes.json"
    output_file = "data/enriched_amenities_results.json"
    enrich_amenities_data(input_file, output_file)
