
import os
import re
import spacy
from langdetect import detect
from transformers import pipeline
from rapidfuzz import fuzz
import torch
import torchvision
print("PyTorch version:", torch.__version__)
print("TorchVision version:", torchvision.__version__)

#############################
# 1. Load Models and Pipelines
#############################
# Load spaCy NER/language model (English) for sentence splitting
nlp = spacy.load("en_core_web_sm")

# Load a translation pipeline (Marian or Helsinki-NLP model)
translator = pipeline("translation", model="Helsinki-NLP/opus-mt-mul-en")

#############################
# 2. Utility Functions
#############################

def translate_in_spacy_chunks(text, target_lang="en", chunk_tokens=200):
    """
    Split 'text' into smaller chunks (by sentence) using spaCy, ensuring
    each chunk is below 'chunk_tokens' tokens (roughly).
    Then translate each chunk with the translator pipeline.
    Concatenate and return the full translated text.
    """
    detected_lang = detect(text)
    if detected_lang == target_lang:
        return text  # no translation needed

    print(f"Translating from {detected_lang} to {target_lang} ...")

    doc = nlp(text)
    chunks = []
    current_chunk_sents = []
    current_token_count = 0

    for sent in doc.sents:
        sent_len = len(sent)  # number of tokens in this sentence
        # If adding this sentence exceeds chunk size, we translate what we have so far
        if current_token_count + sent_len > chunk_tokens:
            chunk_str = " ".join([s.text for s in current_chunk_sents])
            # Translate chunk
            translation = translator(chunk_str, max_length=512)[0]["translation_text"]
            chunks.append(translation)
            # Reset
            current_chunk_sents = []
            current_token_count = 0

        current_chunk_sents.append(sent)
        current_token_count += sent_len

    # Translate any leftover chunk
    if current_chunk_sents:
        chunk_str = " ".join([s.text for s in current_chunk_sents])
        translation = translator(chunk_str, max_length=512)[0]["translation_text"]
        chunks.append(translation)

    # Combine all translated fragments
    return " ".join(chunks)


def split_text(text, max_tokens=512):
    """
    Split text into chunks that are within the token limit (for attribute extraction).
    Uses spaCy sentence splitting again, but you could also do word-based splitting.
    """
    doc = nlp(text)
    chunks = []
    current_chunk = []
    current_length = 0

    for sent in doc.sents:
        sent_len = len(sent)
        if current_length + sent_len > max_tokens:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0
        current_chunk.append(sent.text)
        current_length += sent_len

    # Add the last chunk if it exists
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

#############################
# 3. Extraction Functions
#############################

def merge_results(results):
    """
    Combine results from multiple text chunks into a single cohesive output.
    """
    combined = {
        "project_type": "Not Specified",
        "delivery_date": "Not Specified",
        "investment_option": "Not Specified",
        "available_sizes": [],
        "price_from": [],
        "bathrooms": 0,
        "bedrooms": 0,
        "wc_count": 0,
        "parkings": [],
        "description": [],
        "detail_link": "Not Specified",
    }

    for result in results:
        # Only overwrite if the chunk found a non-default value
        if result["project_type"] != "Not Specified":
            combined["project_type"] = result["project_type"]
        if result["delivery_date"] != "Not Specified":
            combined["delivery_date"] = result["delivery_date"]
        if result["investment_option"] != "Not Specified":
            combined["investment_option"] = result["investment_option"]

        # Extend lists
        combined["available_sizes"].extend(result["available_sizes"])
        combined["price_from"].extend(result["price_from"])

        # Sum numeric values if found
        if result["bathrooms"] != "Not Specified":
            combined["bathrooms"] += int(result["bathrooms"])
        if result["bedrooms"] != "Not Specified":
            combined["bedrooms"] += int(result["bedrooms"])
        if result["wc_count"] != "Not Specified":
            combined["wc_count"] += int(result["wc_count"])

        # Parkings
        if result["parkings"] != "Not Specified":
            combined["parkings"].append(result["parkings"])

        # Merge descriptions
        combined["description"].append(result["description"])

    # Deduplicate
    combined["available_sizes"] = list(set(combined["available_sizes"]))
    combined["price_from"] = list(set(combined["price_from"]))
    combined["parkings"] = list(set(combined["parkings"]))

    # Merge descriptions into one string
    combined["description"] = " ".join(combined["description"])

    return combined

def translate_text(text, target_lang="en"):
    """
    Wrapper to call our chunk-based translator.
    """
    return translate_in_spacy_chunks(text, target_lang=target_lang, chunk_tokens=200)

def rule_based_extract_attributes(text):
    """
    Main entry point: translate if needed, then chunk for extraction, then merge.
    """
    # 1) Translate to English (if not already)
    text = translate_text(text)

    # 2) Split into smaller chunks for attribute extraction
    chunks = split_text(text, max_tokens=512)

    # 3) Extract from each chunk
    results = []
    for chunk in chunks:
        results.append(extract_attributes_chunk(chunk))

    # 4) Merge the chunk-based results
    final = merge_results(results)
    return final

#############################
# 4. Helper Extractors for Each Attribute
#############################

def extract_attributes_chunk(text):
    """
    Process a single chunk of text, extracting various attributes.
    """
    return {
        "project_type": extract_project_type(text),
        "delivery_date": extract_delivery_date(text),
        "investment_option": extract_investment_option(text),
        "available_sizes": extract_surface_area(text),
        "price_from": extract_price(text),
        "bathrooms": extract_bathrooms(text),
        "bedrooms": extract_bedrooms(text),
        "wc_count": extract_wc_count(text),
        "parkings": extract_parkings(text),
        "description": text,  # fallback
        "detail_link": "Not Specified",
    }


def extract_project_type(text):
    project_keywords = [
        "apartment", "house", "commercial property", "villa",
        "studio", "office", "new construction", "appartement"
    ]
    for keyword in project_keywords:
        if keyword.lower() in text.lower():
            return keyword.capitalize()
    return "Not Specified"


def extract_delivery_date(text):
    date_patterns = [
        r"\b\d{1,2}-\d{1,2}(?:-\d{2,4})?\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s\d{4}\b",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return "Not Specified"

def extract_investment_option(text):
    if re.search(r"\b(no|not)\s+(invest|investment)\b", text, flags=re.IGNORECASE):
        return "No"
    elif re.search(r"\b(invest|investment)\b", text, flags=re.IGNORECASE):
        return "Yes"
    return "Not Specified"

def extract_surface_area(text):
    matches = re.findall(r"(\d{1,4}\s?(?:m²|m2|m\^2))", text, flags=re.IGNORECASE)
    return matches if matches else ["Not Specified"]

def extract_price(text):
    matches = re.findall(r"€\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?", text)
    return matches if matches else ["Not Specified"]

def extract_bathrooms(text):
    match = re.search(r"(\d+)\s*(?:bathroom)s?", text, flags=re.IGNORECASE)
    return match.group(1) if match else "Not Specified"

def extract_bedrooms(text):
    match = re.search(r"(\d+)\s*(?:bedroom)s?", text, flags=re.IGNORECASE)
    return match.group(1) if match else "Not Specified"

def extract_wc_count(text):
    match = re.search(r"(\d+)\s*(?:toilet|wc)s?", text, flags=re.IGNORECASE)
    return match.group(1) if match else "Not Specified"

def extract_parkings(text):
    count_match = re.search(r"(\d+)\s*(?:parking|garage|spot)", text, flags=re.IGNORECASE)
    if count_match:
        return count_match.group(1)
    elif re.search(r"parking|garage|spot", text, flags=re.IGNORECASE):
        return "Yes"
    return "Not Specified"

#############################
# 5. Validation / Test
#############################

def validate_extraction():
    """
    Test the extraction pipeline with a sample text that is intentionally longer than 512 tokens.
    We'll artificially replicate content to exceed the limit.
    """
    # Some French text snippet to force translation
    # We'll replicate it multiple times to exceed 512 tokens
    description= ( 
        """
  "130 nouveaux logements sociaux pour Evere et de nouveaux ...",
        130 nouveaux logements sociaux pour Evere et de nouveaux ...",

        "snippet": "Feb 21, 2024 ... Le nouveau projet Destrier, qui cadre dans le Plan Régional du Logement ... Avenue du Destrier 3-43. Chaussée de Louvain 751-755 1140 Evere",
        "htmlSnippet": "Feb 21, 2024 <b>...</b> Le <b>nouveau projet</b> Destrier, qui cadre dans le Plan Régional du Logement ... <b>Avenue du Destrier</b> 3-43. Chaussée de Louvain 751-755 <b>1140</b> Evere",

                {
    """
    )


    # Now run extraction
    extracted_data = rule_based_extract_attributes(description)
    print("\n=== Validation Test ===")
    print("Input length:", len(description.split()), "words")
    print("Extraction result:", extracted_data)

#############################
# Main
#############################

if __name__ == "__main__":
    validate_extraction()
