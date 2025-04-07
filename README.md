# Project_Enrichment_Pipeline

An Automated RAG-based Pipeline designed to extract real estate attributes from polygon coordinates of potential building sites by integrating Reverse Geocoding, Search, Custom Reranking, and Web-Scraping techniques. Using Schema-Based Prompting with Mistral-7B and GPT-4, the results are formatted in JSON and enhanced with nearby amenities.

## Installation & Environment Setup

This project requires a Python environment with specific dependencies. We recommend using Conda to manage your environment.

### 1. Clone the Repository

```bash
git clone https://github.com/DjamelZair/Project_Enrichment_Pipeline.git
cd Project_Enrichment_Pipeline
```

### 2. Set Up the Environment

Use the provided `geoenv.yml` file to create the environment.

```bash
conda env create -f geoenv.yml
```

Activate the environment.

```bash
conda activate geoenv
```

To verify the installation.

```bash
conda list
```

### 3. Install Additional Dependencies (if needed)

If you need to add packages, you can update the environment with:

```bash
pip install -r requirements.txt
```

---

## Configuration & API Keys

This project requires various API keys for accessing OpenAI models and conducting searches. Store all keys in a `.env` file located in the root directory of the project.

Required Keys:

```bash
OPENAI_API_KEY=your_openai_key
MISTRAL_API_KEY=your_mistral_key
GOOGLE_API_KEY=your_google_key
GOOGLE_CX_ID=your_google_cx_id
```

Make sure your `.env` file is listed in `.gitignore` to keep it private.

---

## Usage Instructions

The pipeline is executed through the `run.py` file. Ensure your `.env` file is properly configured before running.

Running the Pipeline:

```bash
python run.py
```

Pipeline Stages Overview:

1. Reverse Geocoding: Converts polygon coordinates to addresses and saves them to `data/polygon_addresses.json`.
2. Web Search & Custom Reranking: Uses OpenAI GPT-based reranker to prioritize relevant results. Scrapes the top two results and a static website.
3. Schema-Based Prompting: Extracts attributes using structured prompts with Mistral-7B and GPT-4.
4. Data Validation: Ensures completeness of extracted attributes.
5. Zimmo Enrichment: Fetches additional real estate details from the Zimmo website using Selenium.
6. Amenity Enrichment: Enhances the dataset by including nearby amenities.
7. Output Generation: Outputs are saved in various JSON files located in the `data/` directory.

---

## Output Files

The pipeline generates the following files:

- `data/polygon_addresses.json`: Contains enriched addresses from reverse geocoding.
- `data/Found_Docs/`: Directory containing successfully retrieved documents from searches.
- `data/NotFound_Docs/`: Directory containing documents not retrieved by searches.
- `data/Reranked_Docs/`: Re-ranked and summarized documents using GPT-based reranking.
- `data/Search_enriched_buildingsites_with_attributes.json`: Data enriched with attributes from web scraping.
- `data/Web&SearchRAG_enriched_buildingsites_with_attributes.json`: Enhanced with RAG processing.
- `data/cleaned_buildingsites_with_attributes.json`: Filtered and validated dataset.
- `data/failed_attempts.json`: Contains addresses where attribute extraction failed.
- `data/enriched_amenities_results.json`: Final output enriched with amenities.

---

## Troubleshooting

If you encounter issues during installation or running the pipeline, try the following:

- Ensure your `.env` file is correctly configured and placed in the root directory.
- Verify the API keys are valid and active.
- Make sure `geoenv` environment is properly activated: `conda activate geoenv`.
- Check if all dependencies are installed: `pip list` or `conda list`.
- Ensure your Python version matches the version specified in `geoenv.yml`.

---

## License (Optional)

Include a license if you want to restrict or open-source your work.

```bash
Licensed by KR&A
```

---

## Additional Notes

Make sure to add needed API keys in thw .env file in the keys folder.
