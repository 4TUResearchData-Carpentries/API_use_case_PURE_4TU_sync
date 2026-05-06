# Import Python's built-in csv module.
# This module allows us to read structured tabular data from CSV files.
import csv

# Import the requests library.
# This is used to communicate with web APIs (in this case, the 4TU.ResearchData API).
import requests


# Path to the input CSV file.
# This dataset contains records where links between Pure and 4TU may be incomplete.
input_csv = "Lesson_development/input_data/wur_missing_in_4tu_input_dataset.csv"

# Base URL for the 4TU.ResearchData API.
# We will dynamically append dataset UUIDs to this base URL.
base_url = "https://data.4tu.nl"


# Open the CSV file for reading.
#
# Arguments:
# - input_csv: path to the file.
# - "r": read mode.
# - encoding="utf-8-sig": ensures compatibility with files exported from Excel
#   (removes potential Byte Order Mark).
# - newline="": ensures correct handling of line endings across platforms.
with open(input_csv, "r", encoding="utf-8-sig", newline="") as file:

    # Create a DictReader object.
    # Each row in the CSV will be represented as a dictionary.
    #
    # Arguments:
    # - file: the opened CSV file.
    # - delimiter=";": specifies that columns are separated by semicolons.
    reader = csv.DictReader(file, delimiter=";")

    # Iterate over each row (dictionary) in the CSV file.
    for row in reader:

        # Extract the dataset UUID from 4TU.
        # .strip() removes leading/trailing whitespace.
        dataset_uuid = row["UUID 4TU"].strip()

        # Extract the UUID of the related research output in Pure.
        pure_output_uuid = row["UUID Research output"].strip()

        # Filter condition:
        # We only want rows where:
        # 1. A dataset exists in 4TU (dataset_uuid is not empty),
        # 2. AND there is a related research output in Pure (pure_output_uuid is not empty).
        #
        # Rows that do not satisfy both conditions are skipped.
        if not dataset_uuid or not pure_output_uuid:
            continue

        # Construct the API endpoint URL for retrieving dataset metadata.
        #
        # The dataset UUID is inserted dynamically into the URL using an f-string.
        url = f"{base_url}/v2/articles/{dataset_uuid}"

        # Send an HTTP GET request to the API endpoint.
        #
        # Arguments:
        # - url: the endpoint from which we retrieve metadata.
        response = requests.get(url)

        # Convert the API response (JSON format) into a Python dictionary.
        # This dictionary contains metadata fields for the dataset.
        article = response.json()

        # Extract the publication/resource title from the 4TU metadata.
        #
        # article.get("resource_title", ""):
        # - Returns the value associated with "resource_title" if present,
        # - Otherwise returns an empty string to avoid errors.
        #
        # str(...): ensures the value is treated as a string.
        # .strip(): removes surrounding whitespace.
        resource_title = str(article.get("resource_title", "")).strip()

        # Extract the publication/resource DOI from the 4TU metadata.
        #
        # Same pattern as above:
        # - Safe retrieval with .get()
        # - Convert to string
        # - Clean whitespace
        resource_doi = str(article.get("resource_doi", "")).strip()

        # Core logic of this script:
        #
        # We are interested in cases where:
        # - Pure HAS publication metadata (we already ensured this earlier),
        # - BUT 4TU does NOT contain this publication metadata.
        #
        # Therefore, we check if both resource_title AND resource_doi are empty.
        if not resource_title and not resource_doi:

            # Print a separator for readability.
            print("\n--- MATCH FOUND ---")

            # Print dataset-level information from the CSV.
            print(f"Dataset UUID: {dataset_uuid}")
            print(f"Dataset title: {row['Title Dataset']}")
            print(f"Dataset DOI: {row['DOI Dataset']}")

            # Print information about the related research output in Pure.
            print(f"Pure output UUID: {pure_output_uuid}")
            print(f"Pure output type: {row['Type Research output']}")
            print(f"Pure output DOI: {row['DOI Research output']}")
            print(f"Pure output title: {row['Title Research output']}")

            # Print the (missing) publication metadata in 4TU.
            # These will typically be empty strings in this condition.
            print(f"4TU resource title: {resource_title}")
            print(f"4TU resource DOI: {resource_doi}")