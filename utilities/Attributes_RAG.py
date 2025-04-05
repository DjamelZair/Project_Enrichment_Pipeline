import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Laad de environment variables uit het .env-bestand
dotenv_path = os.path.join(os.path.dirname(__file__), '../../keys/.env')
load_dotenv(dotenv_path)

# Haal de API-sleutel op uit de environment variables
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OpenAI API-sleutel niet gevonden. Controleer je .env-bestand.")

client = OpenAI(api_key=api_key)


# Attribute Extraction
def extract_attributes_chunk(text):
    prompt = f"""
    You are an expert in real estate data extraction. Extract the required attributes about a building project according to the schema below. Return the extracted information strictly in valid JSON format. Be concise and do not infer or hallucinate details. Use "not specified" for missing fields. Here is the schema:

    - project_type (string): The type of the project, e.g., 'office', 'residential', 'commercial', 'mixed-use', 'apartment', or 'apartment complex', try to specify the amount if possible.
    - delivery_date (string, optional): Expected delivery date of the project, if available.
    - investment_option (string): Whether the project is an investment opportunity ('Yes'/'No').
    - available_sizes (list, optional): Available sizes of buildings or units, e.g., '87m² - 119m²'. Specify the measurement after the number if available.
    - price_from (list, optional): Starting price for buildings or units, if available.
    - bathrooms (int, optional): Number of bathrooms in the project.
    - bedrooms (int, optional): Number of bedrooms in the project.
    - wc_count (int, optional): Number of WCs (toilets) in the project.
    - parking (list, optional): Details about parking availability, e.g., '1 garage per unit', 'not specified', or '[bike space, garage]'.
    - description (string): The source description or document text providing this information.

    Text: {text}

    Return the output as a JSON object.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return {}
    except Exception as e:
        print(f"API error: {e}")
        return {}

# Translation
def translate_text(text, target_lang="en"):
    prompt = f"Translate the following text to English. Preserve context and detail:\n\n{text}"

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"API error: {e}")
        return text  # Fallback

# Example Test
if __name__ == "__main__":
    text = """
[
    {
        "kind": "customsearch#result",
        "title": "Huis te koop in Chauss\u00e9e de Louvain 986 1140 Evere",
        "htmlTitle": "Huis te koop in <b>Chauss\u00e9e de Louvain</b> 986 <b>1140</b> Evere",
        "link": "https://www.immoscoop.be/te-koop/1140-evere/718568",
        "displayLink": "www.immoscoop.be",
        "snippet": "Nieuwbouw? Ja Nee. Rentevoet. 2,96 %. met KBC tarief. JKP. 3.17 %. Totale kredietbedrag. 337.500,00 EUR. Totale kredietlast. 446.018,84 EUR. Liever een voorstel\u00a0...",
        "htmlSnippet": "<b>Nieuwbouw</b>? Ja Nee. Rentevoet. 2,96 %. met KBC tarief. JKP. 3.17 %. Totale kredietbedrag. 337.500,00 EUR. Totale kredietlast. 446.018,84 EUR. Liever een voorstel&nbsp;...",
        "formattedUrl": "https://www.immoscoop.be/te-koop/1140-evere/718568",
        "htmlFormattedUrl": "https://www.immoscoop.be/te-koop/<b>1140</b>-evere/718568",
        "pagemap": {
            "metatags": [
                {
                    "og:image": "https://images.immoscoop.be/cp-09d394b750f6f4a7e990514e8651d5b7.jpg",
                    "next-head-count": "15",
                    "fb:app_id": "647284476386222",
                    "viewport": "width=device-width",
                    "og:title": "Huis te koop in Evere - \u20ac 375.000",
                    "og:description": "Huis te koop in Evere met 4 slaapkamers",
                    "pathname": "/property-detail/[...slug]"
                }
            ],
            "cse_image": [
                {
                    "src": "https://images.immoscoop.be/cp-09d394b750f6f4a7e990514e8651d5b7.jpg"
                }
            ]
        }
    }
]
    """

    translated = translate_text(text)
    attributes = extract_attributes_chunk(translated)

    print("Translated Text:", translated)
    print("Extracted Attributes:", attributes)
