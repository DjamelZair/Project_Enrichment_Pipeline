#reversgeo.py
import time
import requests
import geopandas as gpd
import json
import logging
import time


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Nominatim API URL
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

def nominatim_reverse_geocode(lat, lon, zoom=18, retries=3):
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": zoom,
        "addressdetails": 1
    }
    headers = {
        "User-Agent": "BuildingSitesReverseGeocodeBot/1.0 (djamel93-@hotmail.com)"
    }

    for attempt in range(retries):
        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            address_data = response.json()

            if "display_name" in address_data:
                # Extract relevant address details
                address = address_data.get("address", {})
                flat_address = {
                    "place_id": address_data.get("place_id", "not specified"),
                    "osm_type": address_data.get("osm_type", "not specified"),
                    "osm_id": address_data.get("osm_id", "not specified"),
                    "lat": address_data.get("lat", "not specified"),
                    "lon": address_data.get("lon", "not specified"),
                    "display_name": address_data.get("display_name", "not specified"),
                    "road": address.get("road", "not specified"),
                    "neighbourhood": address.get("neighbourhood", "not specified"),
                    "village": address.get("village", "not specified"),
                    "town": address.get("town", "not specified"),
                    "county": address.get("county", "not specified"),
                    "state": address.get("state", "not specified"),
                    "postcode": address.get("postcode", "not specified"),
                    "country": address.get("country", "not specified"),
                    "country_code": address.get("country_code", "not specified"),
                }
                logging.info("Address returned successfully.")
                return flat_address
            time.sleep(1)
        except requests.RequestException as e:
            logging.error(f"Error querying Nominatim for (lat={lat}, lon={lon}): {e}")
            time.sleep(1)
    return None

def get_all_addresses_from_vertices(polygon):
    vertices = list(polygon.exterior.coords)
    address_count = {}
    all_addresses = []

    for lat, lon in vertices:
        address_dict = nominatim_reverse_geocode(lat, lon, zoom=16)
        if address_dict:
            for key in ["road", "village", "town", "neighbourhood", "county"]:
                value = address_dict.get(key, "not specified")
                address_dict[key] = [p.strip() for p in value.split(" - ")] if " - " in value else [value]

            address_key = (address_dict['osm_id'], address_dict['postcode'])
            if address_key not in address_count:
                address_count[address_key] = 0
            address_count[address_key] += 1

            existing_address = next((addr for addr in all_addresses if addr['osm_id'] == address_dict['osm_id']), None)
            if existing_address:
                existing_address['Vertices'] += 1
            else:
                address_dict['Vertices'] = 1
                all_addresses.append(address_dict)

    logging.info(f"Processed {len(all_addresses)} unique addresses.")
    return all_addresses

def get_nearest_address(all_addresses):
    return max(all_addresses, key=lambda x: x['Vertices'], default=None)

def process_geojson(input_path, output_path):
    start_time = time.time()

    logging.info("Loading GeoJSON data...")
    gdf = gpd.read_file(input_path)
    total_polygons = len(gdf)
    logging.info(f"Loaded {total_polygons} polygons.")

    gdf['id'] = range(1, len(gdf) + 1)
    gdf['all_addresses'] = gdf['geometry'].apply(get_all_addresses_from_vertices)
    gdf['nearest_address'] = gdf['all_addresses'].apply(get_nearest_address)

    # Define the total possible attributes per address
    attribute_keys = [
        "place_id", "osm_type", "osm_id", "lat", "lon", "display_name",
        "road", "neighbourhood", "village", "town", "county", "state",
        "postcode", "country", "country_code"
    ]
    total_possible_attributes = len(attribute_keys) * sum(len(addresses) for addresses in gdf['all_addresses'])
    total_found_attributes = 0

    # Count found attributes
    for addresses in gdf['all_addresses']:
        for address in addresses:
            total_found_attributes += sum(1 for key in attribute_keys if address.get(key) != "not specified")

    # Calculate success metrics
    success_rate = (total_found_attributes / total_possible_attributes) * 100 if total_possible_attributes > 0 else 0
    average_attributes_per_polygon = total_found_attributes / total_polygons if total_polygons > 0 else 0

    # Filter out polygons with no valid road names
    valid_polygons = gdf[gdf['all_addresses'].apply(lambda addresses: any(
        "road" in addr and addr["road"] != ["not specified"] for addr in addresses))]
    omitted_polygons = total_polygons - len(valid_polygons)
    percentage_omitted = (omitted_polygons / total_polygons) * 100

    # Log results
    logging.info(f"Total polygons: {total_polygons}")
    logging.info(f"Polygons with valid addresses: {len(valid_polygons)}")
    logging.info(f"Polygons omitted due to no valid addresses: {omitted_polygons} ({percentage_omitted:.2f}%)")
    logging.info(f"Total possible attributes: {total_possible_attributes}")
    logging.info(f"Total found attributes: {total_found_attributes}")
    logging.info(f"Overall success rate: {success_rate:.2f}%")
    logging.info(f"Average attributes found per polygon: {average_attributes_per_polygon:.2f}")

    # Save results
    valid_polygons['timestamp'] = int(time.time())
    logging.info(f"Saving enriched data to {output_path}...")
    valid_polygons.drop(columns="geometry").to_json(output_path, orient="records", indent=4)
    end_time = time.time()
    elapsed_time = end_time - start_time
    logging.info(f"Processing completed successfully in {elapsed_time:.2f} seconds.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process GeoJSON file and enrich with address data.")
    parser.add_argument("input", help="Path to the input GeoJSON file.")
    parser.add_argument("output", help="Path to the output JSON file.")
    args = parser.parse_args()

    process_geojson(args.input, args.output)
