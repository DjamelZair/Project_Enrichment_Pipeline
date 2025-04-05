# filter_buildingsites.py
import json
import logging

def filter_buildingsites(input_file_path, output_clean_path, output_failed_path):
    """Filters building site data based on project type validity."""

    # Load the dataset
    with open(input_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    cleaned_data = []
    failed_attempts = []

    total_vertices = 0
    removed_vertices = 0
    polygons_removed = 0
    total_failed_vertices_percentage = 0
    failed_address_count = 0

    # Process each polygon entry
    for entry in data:
        polygon_id = entry["id"]
        polygon_timestamp = entry["timestamp"]
        all_addresses = entry["all_addresses"]

        # Calculate total vertices for this polygon
        polygon_total_vertices = sum(address.get("Vertices", 0) for address in all_addresses)
        total_vertices += polygon_total_vertices

        valid_addresses = []
        invalid_addresses = []

        for addr in all_addresses:
            if addr.get("project_type") and addr["project_type"] != "Not specified":
                addr["Vertices"] = f"{addr['Vertices']} ({round((addr['Vertices'] / polygon_total_vertices) * 100, 2)}%)"
                valid_addresses.append(addr)
            else:
                invalid_addresses.append(addr)

        if valid_addresses:
            cleaned_data.append({
                "id": polygon_id,
                "timestamp": polygon_timestamp,
                "all_addresses": valid_addresses
            })

            if invalid_addresses:
                for addr in invalid_addresses:
                    raw_vertices = addr["Vertices"] if isinstance(addr["Vertices"], int) else int(addr["Vertices"].split(" ")[0])
                    percentage = round((raw_vertices / polygon_total_vertices) * 100, 2)
                    addr["Vertices"] = f"{raw_vertices} ({percentage}%)"
                    total_failed_vertices_percentage += percentage
                    failed_address_count += 1

                failed_attempts.append({
                    "id": polygon_id,
                    "timestamp": polygon_timestamp,
                    "all_addresses": invalid_addresses
                })
        else:
            polygons_removed += 1
            for addr in all_addresses:
                raw_vertices = addr["Vertices"] if isinstance(addr["Vertices"], int) else int(addr["Vertices"].split(" ")[0])
                percentage = round((raw_vertices / polygon_total_vertices) * 100, 2)
                addr["Vertices"] = f"{raw_vertices} ({percentage}%)"
                total_failed_vertices_percentage += percentage
                failed_address_count += 1

            failed_attempts.append({
                "id": polygon_id,
                "timestamp": polygon_timestamp,
                "all_addresses": all_addresses
            })
            removed_vertices += polygon_total_vertices

    # Compute additional metrics
    average_failed_vertices_percentage = (total_failed_vertices_percentage / failed_address_count) if failed_address_count > 0 else 0

    summary_stats = {
        "total_polygons": len(data),
        "polygons_with_valid_addresses": len(cleaned_data),
        "polygons_removed_due_to_no_project_type": polygons_removed,
        "total_failed_addresses": failed_address_count,
        "average_failed_vertices_percentage": round(average_failed_vertices_percentage, 2)
    }

    # Save results
    with open(output_clean_path, "w", encoding="utf-8") as file:
        json.dump(cleaned_data, file, indent=4)

    with open(output_failed_path, "w", encoding="utf-8") as file:
        json.dump(failed_attempts, file, indent=4)

    logging.info("Filtering complete!")
    logging.info(json.dumps(summary_stats, indent=4))

    return summary_stats
