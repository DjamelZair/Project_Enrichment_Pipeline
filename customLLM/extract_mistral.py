import os
import json
import logging
import re
import time
from typing import Optional
from langchain_mistralai.chat_models import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")

# Load environment variables
DOTENV_PATH = os.path.join("keys", ".env")
load_dotenv(dotenv_path=DOTENV_PATH)

# Get API key
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise ValueError("Mistral API key not found. Please check your .env file.")

# Define Schema
class BuildingProjectInfo(BaseModel):
    project_type: str = Field(description="The type of the project, e.g., 'residential', 'commercial', or 'mixed-use'.")
    delivery_date: Optional[str] = Field(description="Expected delivery date of the project, if available.")
    investment_option: str = Field(description="Whether the project is an investment opportunity (Yes/No).")
    available_sizes: Optional[list] = Field(description="Available sizes, e.g., '87m² - 119m²'.")
    price_from: Optional[list] = Field(description="Starting price, if available.")
    number_of_bathrooms: Optional[int] = Field(description="Number of bathrooms.")
    number_of_bedrooms: Optional[int] = Field(description="Number of bedrooms.")
    number_of_wcs: Optional[int] = Field(description="Number of WCs.")
    parking: Optional[list] = Field(description="Details about parking availability.")
    description: str = Field(description="The source text providing this information.")

# Prompt Template
building_project_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert in real estate data extraction. Extract the required attributes about a building project "
        "according to the schema below. Return the extracted information strictly in valid JSON format and be concise. "
        "If a field is missing, use 'Not Specified'. Here is the schema:\n\n"
        
        "- project_type (string): The type of the project, e.g., 'penthouse', 'office', 'residential home', 'commercial', 'studio', 'apartment', or 'apartment complex'. If multiple project types are named, list them all (e.g., '20 apartments and 3 penthouses').\n"
        "- delivery_date (string, optional): Expected delivery date of the project, if already available, return 'Already Available'.\n"
        "- investment_option (string): Whether the project is an investment opportunity ('Yes'/'No').\n"
        "- available_sizes (list, optional): Available sizes of buildings or units (not internal components), e.g., '87m² - 119m²'. Specify the measurement after the number if available.\n"
        "- price_from (list, optional): Starting price for buildings or units, if available. Ensure currency is specified (e.g., '€340,000' instead of '340000').\n"
        "- number_of_bathrooms (int, optional): Number of bathrooms in the project.\n"
        "- number_of_bedrooms (int, optional): Number of bedrooms in the project.\n"
        "- number_of_wcs (int, optional): Number of WCs (toilets) in the project.\n"
        "- parking (list, optional): Details about parking availability, e.g., '1 garage per unit', 'Not Specified', or '[bike space, garage]'.\n"
        "- description (string): The full project description used as the source for these details."
    ),
    ("human", "{user_input}")
])

# Initialize Mistral LLM
llm = ChatMistralAI(model="mistral-small-2402", api_key=MISTRAL_API_KEY)
llm_with_tools = llm.bind_tools([BuildingProjectInfo])

def extract_attributes_with_mistral(text):
    """
    Uses Mistral AI to extract structured attributes from a real estate description dynamically.
    Ensures all expected fields are present.
    """
    user_input = building_project_prompt.format(user_input=text)

    try:
        logging.info(f"🔍 Sending description to Mistral: {text[:300]}...")

        response = llm_with_tools.invoke(user_input)
        mistral_data = json.loads(response.content)  # Ensure valid JSON

        logging.info(f"📩 Mistral Response: {json.dumps(mistral_data, indent=2)}")

        # Ensure all expected fields exist
        required_keys = [
            "project_type", "delivery_date", "investment_option", 
            "available_sizes", "price_from", "number_of_bathrooms", 
            "number_of_bedrooms", "number_of_wcs", "parking", "description"
        ]

        for key in required_keys:
            if key not in mistral_data:
                logging.warning(f"⚠ Warning: Mistral did not return {key}, setting it to 'Not Specified'")
                mistral_data[key] = "Not Specified"

        return mistral_data
    except json.JSONDecodeError:
        logging.error(f"🚨 Failed to parse Mistral response as JSON. Returning fallback for: {text[:300]}...")
        return {"error": "Failed to parse JSON response"}
    except Exception as e:
        logging.error(f"🔥 Error extracting attributes with Mistral: {e}")
        return {"error": str(e)}
