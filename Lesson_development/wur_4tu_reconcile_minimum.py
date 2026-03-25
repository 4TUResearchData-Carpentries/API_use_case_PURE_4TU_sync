import csv
import requests

input_csv = "Lesson_development/wur_4tu_minimum_dataset_case2.csv"
base_url = "https://data.4tu.nl"

with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")

    for row in reader:
        dataset_uuid = str(row.get("UUID 4TU", "")).strip()
        pure_output_uuid = str(row.get("UUID Research output", "")).strip()

        # Only keep datasets where Pure DOES have a related publication
        if not dataset_uuid or not pure_output_uuid:
            continue

        url = f"{base_url}/v2/articles/{dataset_uuid}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            article = response.json()
        except requests.RequestException as e:
            print(f"Error fetching {dataset_uuid}: {e}")
            continue

        resource_title = str(article.get("resource_title", "")).strip()
        resource_doi = str(article.get("resource_doi", "")).strip()
        references = article.get("references")

        # Check whether references is empty
        has_references = False
        if isinstance(references, list):
            has_references = any(str(x).strip() for x in references)
        elif isinstance(references, str):
            has_references = bool(references.strip())
        elif references:
            has_references = True

        # Case 2:
        # Pure has a related publication, but 4TU has no publication metadata
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