import csv
import requests

input_csv = "Lesson_development/input_data/wur_missing_in_pure_input_dataset.csv"
base_url = "https://data.4tu.nl"

with open(input_csv, "r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")

    for row in reader:
        dataset_uuid = row["UUID 4TU"].strip()
        pure_output_uuid = row["UUID Research output"].strip()

        # Keep only datasets that exist in 4TU but have no related output in Pure
        if not dataset_uuid or pure_output_uuid:
            continue

        # Get metadata from 4TU
        url = f"{base_url}/v2/articles/{dataset_uuid}"
        response = requests.get(url)
        article = response.json()

        # Extract publication-related metadata from 4TU
        resource_title = str(article.get("resource_title", "")).strip()
        resource_doi = str(article.get("resource_doi", "")).strip()

        # Print only cases where 4TU has publication metadata
        if resource_title or resource_doi:
            print("\n--- MATCH FOUND ---")
            print(f"Dataset UUID: {dataset_uuid}")
            print(f"Dataset title: {row['Title Dataset']}")
            print(f"Dataset DOI: {row['DOI Dataset']}")
            print(f"4TU resource title: {resource_title}")
            print(f"4TU resource DOI: {resource_doi}")
            print(f"Pure output type: {row['Type Research output']}")