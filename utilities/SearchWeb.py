#SearchWeb
import requests
import json
import logging
import os
import time
from fuzzywuzzy import fuzz

# ---------------------
# CONFIGURATION
# ---------------------


# Replace below with you own keys:
API_KEY = "AIzaSyCxbqZvPl5zInaLBOuy4-Ts0Lw76swJ7_Q"
CX_ID = "e6bd15010ab5a410d"
NUM_RESULTS = 50  # Total results needed per query (You can lower it because rarely more than 10 are found)
RESULTS_PER_CALL = 10
SEARCH_URL = "https://www.googleapis.com/customsearch/v1"  # Google Custom Search API URL

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------
# QUERY BUILDERS
# ---------------------
def construct_query(road, postal_code, language, is_french):
    """Construct main query string."""
    if is_french:
        return f'+("{road}") {postal_code} (nouveau projet OR projet immobilier) -hotel -lour'
    return f'+("{road}") {postal_code} (nieuwbouw OR bouwproject) -hotel -huur'

def construct_fallback_query(road, postal_code, language, is_french):
    """Construct a fallback query with reduced complexity."""
    if is_french:
        return f'+("{road}") {postal_code} "\u00e0 vendre"'
    return f'+("{road}") {postal_code} "te koop"'

# ---------------------
# GOOGLE SEARCH FUNCTION WITH RATE LIMIT HANDLING
# ---------------------
def google_search(query, num_results=NUM_RESULTS, retries=3):
    """Fetch search results with pagination and retry logic."""
    results = []
    start = 1

    while len(results) < num_results and start <= 91:  # Enforce 100 results max
        params = {"key": API_KEY, "cx": CX_ID, "q": query, "num": RESULTS_PER_CALL, "start": start}

        for attempt in range(retries):
            try:
                response = requests.get(SEARCH_URL, params=params)
                response.raise_for_status()
                items = response.json().get('items', [])
                results.extend(items)
                start += RESULTS_PER_CALL

                # Stop if fewer than RESULTS_PER_CALL are returned
                if len(items) < RESULTS_PER_CALL:
                    break

                time.sleep(2)  # Delay between requests (2 seconds to avoid limits)
                break
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Too many requests
                    logger.warning(f"Rate limit hit. Retrying in {2**attempt} seconds...")
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    logger.error(f"HTTP error: {e}")
                    return results
            except Exception as e:
                logger.error(f"Error fetching results: {e}")
                return results

    return results

# ---------------------
# MAIN SEARCH PROCESS
# ---------------------
def search_addresses(input_file, output_dir_found, output_dir_not_found, round_size=5, delay_between_rounds=15):
    """Search for addresses using Google API with performance metrics, including fallback effectiveness."""
    os.makedirs(output_dir_found, exist_ok=True)
    os.makedirs(output_dir_not_found, exist_ok=True)

    # Load input data
    with open(input_file, "r") as file:
        data = json.load(file)

    # Initialize performance metrics
    total_queries = 0
    total_time = 0
    successful_queries = 0
    total_fallback_queries = 0
    successful_fallback_queries = 0
    failed_fallback_queries = 0
    queries_not_needing_fallback = 0

    # Start the overall timer
    overall_start_time = time.time()

    for round_idx in range(0, len(data), round_size):
        logger.info(f"Starting round {round_idx // round_size + 1}...")

        for entry in data[round_idx:round_idx + round_size]:
            addresses = entry.get('all_addresses', [])

            for address in addresses:
                roads = address.get('road', [])
                postal_code = address.get('postcode', 'Not Specified')
                display_name = ' '.join(roads).lower()

                # Detect language
                is_french = any(fuzz.partial_ratio(keyword, display_name) > 85
                                for keyword in ['avenue', 'rue', 'walonie', 'brussels', 'chemin'])
                language = 'fr' if is_french else 'nl'

                if not roads or 'not specified' in roads:
                    logger.warning(f"Skipping entry ID {entry['id']} due to missing road.")
                    continue

                for road in roads:
                    query = construct_query(road, postal_code, language, is_french)
                    query_start_time = time.time()  # Start timer for query

                    results = google_search(query)
                    query_time = time.time() - query_start_time  # Time for this query
                    total_time += query_time
                    total_queries += 1
                    logger.info(f"Query for '{road}' completed in {query_time:.2f} seconds.")

                    # Check if results were retrieved
                    if results:
                        successful_queries += 1
                        queries_not_needing_fallback += 1
                    else:
                        # Fallback query logic
                        total_fallback_queries += 1
                        fallback_query = construct_fallback_query(road, postal_code, language, is_french)
                        fallback_results = google_search(fallback_query)

                        if fallback_results:
                            successful_fallback_queries += 1
                        else:
                            failed_fallback_queries += 1

                    # Save results (whether from primary or fallback query)
                    filtered_results = [
                        result for result in (results if results else fallback_results)
                        if fuzz.partial_ratio(road.lower(), result.get('title', '').lower()) >= 50
                    ]
                    safe_road = road.replace(' ', '_').replace('/', '_')
                    output_dir = output_dir_found if filtered_results else output_dir_not_found
                    output_file = os.path.join(output_dir, f"{entry['id']}_{safe_road}_{postal_code}.json")

                    with open(output_file, "w") as outfile:
                        json.dump(filtered_results, outfile, indent=4)

        time.sleep(delay_between_rounds)

    # End overall timer
    overall_end_time = time.time()
    overall_time = overall_end_time - overall_start_time

    # Compute metrics
    fallback_success_rate = (successful_fallback_queries / total_fallback_queries * 100) if total_fallback_queries > 0 else 0
    fallback_failure_rate = (failed_fallback_queries / total_fallback_queries * 100) if total_fallback_queries > 0 else 0
    overall_query_success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
    query_failure_rate = (1 - successful_queries / total_queries) * 100 if total_queries > 0 else 0
    fallback_contribution_to_total_success = (successful_fallback_queries / successful_queries * 100) if successful_queries > 0 else 0
    fallback_ratio_to_total_queries = (total_fallback_queries / total_queries * 100) if total_queries > 0 else 0

    # Log performance metrics
    logger.info(f"Processing completed!")
    logger.info(f"Total Queries: {total_queries}")
    logger.info(f"Successful Queries: {successful_queries} ({overall_query_success_rate:.2f}%)")
    logger.info(f"Total Time Taken: {overall_time:.2f} seconds")
    logger.info(f"Average Time per Query: {total_time / total_queries:.2f} seconds")
    logger.info(f"Total Queries Not Needing Fallback: {queries_not_needing_fallback}")
    logger.info(f"Total Fallback Queries: {total_fallback_queries}")
    logger.info(f"Successful Fallback Queries: {successful_fallback_queries}")
    logger.info(f"Failed Fallback Queries: {failed_fallback_queries}")
    logger.info(f"Fallback Success Rate: {fallback_success_rate:.2f}%")
    logger.info(f"Fallback Failure Rate: {fallback_failure_rate:.2f}%")
    logger.info(f"Ratio of Fallback Queries to Total Queries: {fallback_ratio_to_total_queries:.2f}%")
    logger.info(f"Fallback Contribution to Total Success: {fallback_contribution_to_total_success:.2f}%")
