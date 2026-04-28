import csv
import requests

# -------------------------------------------------------------------
# Goal of this script
# -------------------------------------------------------------------
# We want to identify datasets that:
#
# 1. Exist in 4TU.ResearchData
# 2. DO have a related research output/publication recorded in Pure
# 3. But do NOT have publication-related metadata in 4TU.ResearchData
#
# In other words:
# "Pure knows about a related publication, but 4TU does not."
# -------------------------------------------------------------------

input_csv = "Lesson_development/input_data/wur_missing_in_4tu_input_dataset.csv"
base_url = "https://data.4tu.nl"

# Open the CSV file prepared from the reconciliation process.
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
        # We only want datasets where:
        # - the dataset exists in 4TU
        # - Pure already has a related research output
        #
        # These are candidates where 4TU may be missing publication
        # metadata that is already available in Pure.
        # ------------------------------------------------------------
        if not dataset_uuid or not pure_output_uuid:
            continue

        # Build the 4TU API endpoint for this dataset
        url = f"{base_url}/v2/articles/{dataset_uuid}"

        # ------------------------------------------------------------
        # API request step
        # ------------------------------------------------------------
        # Retrieve the current metadata record from 4TU.ResearchData.
        # This allows us to check whether publication metadata is
        # already present in the repository record.
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
        # These fields indicate whether 4TU already stores information
        # about a related publication.
        # ------------------------------------------------------------
        resource_title = str(article.get("resource_title", "")).strip()
        resource_doi = str(article.get("resource_doi", "")).strip()
        references = article.get("references")

        # ------------------------------------------------------------
        # Check whether the references field contains useful content
        # ------------------------------------------------------------
        # References may be returned as:
        # - a list
        # - a string
        # - another non-empty value
        #
        # This block converts those possibilities into one Boolean:
        # has_references = True or False.
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
        # This is the key reconciliation case:
        #
        # Pure has a related publication,
        # but the 4TU metadata record does not contain:
        # - resource_title
        # - resource_doi
        # - references
        #
        # These records are possible candidates for updating 4TU.
        # ------------------------------------------------------------
        if not resource_title and not resource_doi and not has_references:
            print("\n--- MATCH FOUND ---")
            print(f"Dataset UUID: {dataset_uuid}")
            print(f"Title Dataset: {row.get('Title Dataset', '')}")
            print(f"DOI Dataset: {row.get('DOI Dataset', '')}")
            print(f"UUID Research output: {row.get('UUID Research output', '')}")
            print(f"Type Research output: {row.get('Type Research output', '')}")
            print(f"DOI Research output: {row.get('DOI Research output', '')}")
            print(f"Title Research output: {row.get('Title Research output', '')}")
            print(f"4TU resource_title: {resource_title}")
            print(f"4TU resource_doi: {resource_doi}")
            print(f"4TU references: {references}")