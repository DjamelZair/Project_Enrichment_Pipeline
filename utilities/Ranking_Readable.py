import os
import json
import time
from openai import OpenAI
from dotenv import load_dotenv

# API Key Setup
# Set OpenAI API Key directly
api_key = "YOUR KEY HERE"
client = OpenAI(api_key=api_key)

# or try (change if keys are in other file, I had a " keys" folder in the main directory ):

dotenv_path = os.path.join(os.path.dirname(__file__), '../../keys/.env')
load_dotenv(dotenv_path)

# Then retrieve your openAI keys, example: 
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OpenAI API-sleutel niet gevonden. Controleer je .env-bestand.")

def generate_real_estate_summary(entry, model="gpt-3.5-turbo"):
    """Generate real estate summaries and extract key details."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a real estate analyst. Your job is to make text more readable and "
                "highlight building relevant information for real estate investors. Focus on location, "
                "property type, availability for sale or rent, amenities, price range, and other key insights. "
                "Give special importance to whether the property is for sale and its type (e.g., house, apartment, etc.)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Title: {entry.get('title', 'No title')}\n"
                f"Description: {entry.get('snippet', 'No description')}\n\n"
                "Extract the following:\n"
                "- Property type (house, apartment, etc.)\n"
                "- Sale status (for sale, for rent, or not specified)\n"
                "- Any key insights for investors."
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=200,
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"API Error: {e}")
        return "Error generating summary"

def score_results(results):
    """Score and sort results."""
    def score(item):
        processed_text = item.get("processed_text", "").lower()
        score = 0
        if "for sale" in processed_text:
            score += 2
        if any(bt in processed_text for bt in ["house", "apartment", "villa", "townhouse"]):
            score += 1
        return score

    return sorted(results, key=score, reverse=True)

def process_folder(input_folder, output_folder, model="gpt-3.5-turbo"):
    """Process JSON files, re-rank, and summarize."""
    os.makedirs(output_folder, exist_ok=True)
    total_start_time = time.time()

    for filename in os.listdir(input_folder):
        if filename.endswith(".json"):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)

            with open(input_path, "r") as file:
                data = json.load(file)
                data = data[:10]  # Beperk tot de eerste 10 resultaten voor snelheid

            results = []
            for item in data:
                try:
                    summary = generate_real_estate_summary(item, model=model)
                    results.append({
                        "id": item.get("id", "No ID"),
                        "processed_text": summary,
                    })
                except Exception as e:
                    print(f"Error processing item {item.get('id', 'Unknown')}: {e}")

            ranked_results = score_results(results)

            with open(output_path, "w") as file:
                json.dump(ranked_results, file, indent=4, ensure_ascii=False)

    total_elapsed_time = time.time() - total_start_time
    print(f"Total processing time: {total_elapsed_time:.2f} seconds")
