# Import Python's built-in csv module.
# This module lets us read and write CSV files.
import csv

# Import the requests library.
# This library lets us send HTTP requests to web APIs.
import requests


# Path to the input CSV file.
# This file is expected to contain information about datasets in 4TU.ResearchData
# and their possible related research outputs in Pure.
input_csv = "Lesson_development/input_data/wur_missing_in_pure_input_dataset.csv"

# Base URL of the 4TU.ResearchData platform.
# We will use this together with dataset UUIDs to build API request URLs.
base_url = "https://data.4tu.nl"


# Open the CSV file for reading.
#
# Arguments:
# - input_csv: path to the CSV file we want to read.
# - "r": opens the file in read mode.
# - encoding="utf-8-sig": reads UTF-8 files and removes a possible Byte Order Mark.
#   This is useful when CSV files were exported from tools such as Excel.
# - newline="": lets the csv module handle line endings correctly.
with open(input_csv, "r", encoding="utf-8-sig", newline="") as file:

    # Create a DictReader object.
    # DictReader reads each CSV row as a dictionary, where column names become keys.
    #
    # Arguments:
    # - file: the opened CSV file object.
    # - delimiter=";": tells Python that columns are separated by semicolons,
    #   not commas.
    reader = csv.DictReader(file, delimiter=";")

    # Loop over every row in the CSV file.
    # Each row is a dictionary, for example:
    # row["UUID 4TU"] gives the value in the column named "UUID 4TU".
    for row in reader:

        # Get the 4TU dataset UUID from the current row.
        # .strip() removes extra spaces before or after the value.
        dataset_uuid = row["UUID 4TU"].strip()

        # Get the Pure research output UUID from the current row.
        # If this field is empty, the dataset may be missing a related output in Pure.
        pure_output_uuid = row["UUID Research output"].strip()

        # Keep only rows where:
        # 1. The dataset exists in 4TU, meaning dataset_uuid is not empty.
        # 2. There is no related research output in Pure, meaning pure_output_uuid is empty.
        #
        # This condition skips rows that are not relevant for this check.
        if not dataset_uuid or pure_output_uuid:
            continue

        # Build the API endpoint URL for this dataset.
        # The f-string inserts the dataset UUID into the URL.
        url = f"{base_url}/v2/articles/{dataset_uuid}"

        # Send a GET request to the 4TU.ResearchData API.
        #
        # Arguments:
        # - url: the API endpoint from which we want to retrieve dataset metadata.
        response = requests.get(url)

        # Convert the API response from JSON into a Python dictionary.
        # The variable article now contains metadata about the dataset.
        article = response.json()

        # Extract the title of the related publication or resource from 4TU metadata.
        #
        # article.get("resource_title", "") means:
        # - Look for the key "resource_title" in the article dictionary.
        # - If the key does not exist, return an empty string instead.
        #
        # str(...) ensures the value is treated as text.
        # .strip() removes unnecessary spaces.
        resource_title = str(article.get("resource_title", "")).strip()

        # Extract the DOI of the related publication or resource from 4TU metadata.
        #
        # The same pattern is used here:
        # - Try to get "resource_doi".
        # - Use an empty string if it is missing.
        # - Convert to text.
        # - Remove extra spaces.
        resource_doi = str(article.get("resource_doi", "")).strip()

        # Print only datasets where 4TU contains publication-related metadata.
        # This means that although Pure has no linked output, 4TU may already contain
        # information about a related publication.
        if resource_title or resource_doi:

            # Print a visual separator to make each result easier to read.
            print("\n--- MATCH FOUND ---")

            # Print the dataset UUID from the CSV file.
            print(f"Dataset UUID: {dataset_uuid}")

            # Print the dataset title from the CSV file.
            print(f"Dataset title: {row['Title Dataset']}")

            # Print the dataset DOI from the CSV file.
            print(f"Dataset DOI: {row['DOI Dataset']}")

            # Print the related publication/resource title found in 4TU metadata.
            print(f"4TU resource title: {resource_title}")

            # Print the related publication/resource DOI found in 4TU metadata.
            print(f"4TU resource DOI: {resource_doi}")

            # Print the research output type from the CSV file.
            # This can help interpret what kind of Pure output may be missing.
            print(f"Pure output type: {row['Type Research output']}")