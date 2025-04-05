import os
import json

# Importeer je GPT-functies vanuit OAI_extract_text_LLM:
from utilities.Attributes_RAG import extract_attributes_chunk, translate_text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Pad naar het JSON-bestand met polygonen (jouw brondata)
POLYGON_DATA_PATH = "data/polygon_addresses.json"

# Pad naar de directory met de FoundDocs2-bestanden
FOUNDDOCS_DIR = "data/Reranked_Docs"

def load_polygons(polygon_data_path):
    """Laadt de polygonen uit het JSON-bestand."""
    try:
        with open(polygon_data_path, "r", encoding="utf-8") as f:
            polygons = json.load(f)
        logging.info(f"Loaded {len(polygons)} polygons from {polygon_data_path}")
        return polygons
    except Exception as e:
        logging.error(f"Failed to load polygon data: {e}")
        return []


def parse_filename(filename):
    """
    Verwacht bestandsnaam als: 1_Chaussée_de_Louvain_1140.json
    Returnt (int(polygon_id), 'Chaussée de Louvain', '1140').
    """
    base, _ = os.path.splitext(filename)  # bv "1_Chaussée_de_Louvain_1140"
    parts = base.split("_")              # ["1", "Chaussée", "de", "Louvain", "1140"]
    
    polygon_id = int(parts[0])
    postcode = parts[-1]                 # "1140"
    street_parts = parts[1:-1]           # ["Chaussée", "de", "Louvain"]
    street_name = " ".join(street_parts) # "Chaussée de Louvain"
    
    return (polygon_id, street_name, postcode)

def load_found_docs(found_docs_dir):
    """Laadt FoundDocs uit een directory en structureert ze in een dict."""
    found_docs_map = {}
    try:
        for filename in os.listdir(found_docs_dir):
            if filename.endswith(".json"):
                full_path = os.path.join(found_docs_dir, filename)
                poly_id, street_name, postcode = parse_filename(filename)
                with open(full_path, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)
                found_docs_map.setdefault(poly_id, []).append((street_name, postcode, doc_data))
                logging.debug(f"Loaded file: {filename} for polygon ID: {poly_id}")
        logging.info(f"Loaded FoundDocs for {len(found_docs_map)} polygon IDs.")
    except Exception as e:
        logging.error(f"Failed to load FoundDocs: {e}")
    return found_docs_map


def find_matching_address(polygon, street_name, postcode):
    """
    Zoekt in polygon['all_addresses'] een address waar:
    - 'road' (list) de street_name bevat (case-insensitive check)
    - 'postcode' == postcode (exact)
    Returnt (address, index) of (None, None) als er geen match is.
    """
    normalized_street = street_name.replace("_", " ").lower()
    all_addresses = polygon.get("all_addresses", [])
    
    for i, address in enumerate(all_addresses):
        roads = address.get("road", [])
        address_postcode = address.get("postcode", "")
        
        # Match postcode
        if address_postcode == postcode:
            # Check of de (genormaliseerde) straatnaam in roads zit
            if any(normalized_street == r.lower() for r in roads):
                return address, i
    return None, None

def map_extracted_attributes(gpt_dict):
    """
    Convert extracted GPT attributes into a standardized dictionary, ensuring missing values are replaced with "Not Specified".
    """
    if not isinstance(gpt_dict, dict):
        return {}

    def safe_get(key):
        """ Helper function to return "Not Specified" if the key is missing or None. """
        return gpt_dict.get(key, "Not Specified") if gpt_dict.get(key) is not None else "Not Specified"

    return {
        "project_type": safe_get("Project Type"),
        "delivery_date": safe_get("Delivery Date"),
        "investment_option": safe_get("Investment Option"),
        "available_sizes": safe_get("Available Sizes"),
        "price_from": safe_get("Price From"),
        "number_of_bathrooms": safe_get("Number of Bathrooms"),
        "number_of_bedrooms": safe_get("Number of Bedrooms"),
        "number_of_wcs": safe_get("Number of WCs"),
        "parking": safe_get("Parking"),
        "description": safe_get("Description"),
    }

def read_processed_text(doc_data):
    """
    In de RERANKRESULTS lijkt doc_data meestal een lijst met dicts 
    met key 'processed_text'. 
    
    Als je alleen de éérste doc nodig hebt: return doc_data[0]["processed_text"].
    Wil je meerdere docs combineren? Combineer ze bijvoorbeeld met newline.
    """
    if isinstance(doc_data, list) and len(doc_data) > 0:
        # Hier pakken we alleen de eerste doc (gerankte).
        first_item = doc_data[0]
        return first_item.get("processed_text", "")
    elif isinstance(doc_data, dict):
        # Als het direct een dict is, pak "processed_text" als die bestaat
        return doc_data.get("processed_text", "")
    return str(doc_data)

def address_missing_essential_fields(address):
    """
    Bepaal of het adres al een 'project_type' heeft (of andere velden).
    Als je bijvoorbeeld alleen een 2e doc wilt gebruiken als 
    'project_type' == 'Not Specified', kun je dat hier checken.
    """
    # Voorbeeld: check of project_type nog op Not Specified staat
    proj_type = address.get("project_type")
    return (proj_type is None or proj_type == "Not Specified")

def enrich_polygons(polygons, found_docs_map):
    """
    Doorloopt alle polygonen, kijkt in found_docs_map of er JSON-bestanden zijn met dezelfde poly_id.
    Probeert op basis van straatnaam en postcode de juiste address te verrijken.
    
    Als je meerdere docs per (straat, postcode) hebt, kun je kiezen:
    - Alleen de eerste.
    - De eerste en daarna de tweede als er nog key info mist.
    - Alle docs.
    """
    enriched_count = 0
    
    for polygon in polygons:
        poly_id = polygon.get("id")
        if poly_id is None:
            continue
        
        # Check of we data hebben voor deze poly_id in found_docs_map
        docs_for_this_poly = found_docs_map.get(poly_id, [])
        if not docs_for_this_poly:
            continue
        
        # Voor elk doc in docs_for_this_poly
        # (Er kunnen meerdere JSON-bestanden voor dezelfde polygoon/straat/postcode-combo zijn.)
        for (street_name, postcode, doc_data) in docs_for_this_poly:
            address, address_index = find_matching_address(polygon, street_name, postcode)
            if address is None:
                print(f"[WARNING] No matching address in polygon {poly_id} for '{street_name}' {postcode}")
                continue
            
            # --- Hier bepaal je of je alle docs verwerkt of alleen de eerste/2e. ---
            # Stel: je wilt *iedere* doc_data door GPT halen en toevoegen:
            # of je wilt slechts de *eerste*, maar "Project Type" was niet gevonden, dan pas de tweede.
            # Als je echt alleen 1 doc wilt en klaar, dan stop je direct na de eerste.

            # 1) Haal tekst uit doc_data
            combined_text = read_processed_text(doc_data)
            if not combined_text.strip():
                print(f"[DEBUG] No text found in doc_data for poly_id={poly_id}, skipping.")
                continue

            # 2) Naar GPT
            print(f"[DEBUG] combined_text for poly_id={poly_id}, street='{street_name}':\n",
                  combined_text[:200], "...\n")  # eerste 200 chars
            translated = translate_text(combined_text)
            extracted_raw = extract_attributes_chunk(translated)
            
            # 3) Map de GPT-output naar uniforme keys, en sla direct in address
            mapped_attrs = map_extracted_attributes(extracted_raw)
            
            # Je kunt ze direct op address zetten (flatten):
            #   address.update(mapped_attrs)
            # Of in een aparte subdict, bv.:
            #   address["extracted_attributes"] = mapped_attrs
            #
            # Als je ze echt 'plat' wil voor latere Elasticsearch, doe:
            address.update(mapped_attrs)
            
            enriched_count += 1
            print(f"[INFO] Enriched polygon ID {poly_id}, address '{street_name}' {postcode} with {list(mapped_attrs.keys())}.")
            
            # --- Stoppen als je maar 1 doc wilt gebruiken? ---
            # Als je alleen de éérste doc wilt, kun je hier 'break' doen:
            # break

            # --- Of als je alleen de 2e wilt als er nog steeds 'Not Specified' in project_type? ---
            if address_missing_essential_fields(address):
                 print("[DEBUG] project_type was still Not Specified; continuing to next doc")
            else:
                 break  # we hebben genoeg info, stop
    
    return polygons, enriched_count

def main():
    # 1) Polygonen laden
    polygons = load_polygons(POLYGON_DATA_PATH)
    if not polygons:
        print("[ERROR] No polygons loaded. Exiting.")
        return
    
    # 2) FoundDocs laden
    found_docs_map = load_found_docs(FOUNDDOCS_DIR)
    
    # 3) Verrijken
    enriched_polygons, enriched_count = enrich_polygons(polygons, found_docs_map)
    
    # 4) Opslaan
    output_path = "data/Search_enriched_buildingsites_with_attributes.json"
    try:
        with open(output_path, "w", encoding="utf-8") as out_f:
            json.dump(enriched_polygons, out_f, indent=4, ensure_ascii=False)
        print(f"[INFO] Saved enriched polygons to {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to save enriched polygons: {e}")
    
    print(f"[INFO] Enrichment completed. {enriched_count} addresses were enriched with GPT-extracted data.")

if __name__ == "__main__":
    main()
