import csv
import requests

# -------------------------------------------------------------------
# Goal of this script
# -------------------------------------------------------------------
# We want to identify datasets that:
#
# 1. Exist in 4TU.ResearchData
# 2. Do NOT have a related research output/publication recorded in Pure
# 3. But DO have publication-related metadata in 4TU.ResearchData
#
# In other words:
# "Pure says there is no related publication, but 4TU may contain one."
# -------------------------------------------------------------------

input_csv = "Lesson_development/input_data/wur_missing_in_pure_input_dataset.csv"
base_url = "https://data.4tu.nl"

# Open the CSV exported/prepared from the reconciliation process.
# The file uses semicolons as separators.
with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")

    # Process each dataset row by row
    for row in reader:

        # UUID of the dataset in 4TU.ResearchData
        dataset_uuid = str(row.get("UUID 4TU", "")).strip()

        # UUID of the related research output in Pure, if available
        pure_output_uuid = str(row.get("UUID Research output", "")).strip()

        # ------------------------------------------------------------
        # Filtering step
        # ------------------------------------------------------------
        # We only want datasets that:
        # - have a 4TU UUID
        # - do NOT already have a related research output in Pure
        #
        # If there is no 4TU UUID, we cannot query the 4TU API.
        # If Pure already has a related research output, this dataset is
        # not relevant for this specific check.
        # ------------------------------------------------------------
        if not dataset_uuid or pure_output_uuid:
            continue

        # Build the API endpoint for this specific 4TU dataset
        url = f"{base_url}/v2/articles/{dataset_uuid}"

        # ------------------------------------------------------------
        # API request step
        # ------------------------------------------------------------
        # Ask the 4TU.ResearchData API for the full metadata record
        # of this dataset.
        # ------------------------------------------------------------
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            article = response.json()

        except requests.RequestException as e:
            print(f"Error fetching {dataset_uuid}: {e}")
            continue

        # ------------------------------------------------------------
        # Extract publication-related metadata from the 4TU record
        # ------------------------------------------------------------
        # These fields may indicate that the dataset is linked to a
        # publication or other scholarly output in 4TU.ResearchData.
        # ------------------------------------------------------------
        resource_title = str(article.get("resource_title", "")).strip()
        resource_doi = str(article.get("resource_doi", "")).strip()
        references = article.get("references")

        # ------------------------------------------------------------
        # Check whether the references field contains useful content
        # ------------------------------------------------------------
        # The API may return references in different forms:
        # - as a list
        # - as a string
        # - as another non-empty value
        #
        # This block normalizes that logic into a simple True/False value.
        # ------------------------------------------------------------
        has_references = False

        if isinstance(references, list):
            has_references = any(str(x).strip() for x in references)

        elif isinstance(references, str):
            has_references = bool(references.strip())

        elif references:
            has_references = True

        # ------------------------------------------------------------
        # Reporting step
        # ------------------------------------------------------------
        # If 4TU contains any publication-related metadata, print the
        # dataset as a possible reconciliation case.
        #
        # This means:
        # Pure has no related publication,
        # but 4TU seems to know about one.
        # ------------------------------------------------------------
        if resource_title or resource_doi or has_references:
            print("\n--- MATCH FOUND ---")
            print(f"Dataset UUID: {dataset_uuid}")
            print(f"Title: {row.get('Title Dataset', '')}")
            print(f"DOI: {row.get('DOI Dataset', '')}")
            print(f"4TU resource_title: {resource_title}")
            print(f"4TU resource_doi: {resource_doi}")
            print(f"4TU references: {references}")