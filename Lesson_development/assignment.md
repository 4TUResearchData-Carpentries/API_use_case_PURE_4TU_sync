## Assigment/ Use Case

Step 1: Update Pure metadata

-   *Search API for datasets that are registered in Pure*

-   *Filter on datasets that have a related publication, but no related
    publication in Pure*

-   *Export list of datasets and related publication title and DOI*

-   *Update Pure metadata*

Step 2: Update 4TU metadata

-   *Search API for datasets that are registered in Pure*

-   *Filter on datasets without related publication, that have a related
    publication in Pure*

-   *Update 4TU metadata with related publication title and DOI*

A spreadsheet with 4TU Datasets and their respective related
publications in Pure is available


## Questions



## Suggested solutions

Step 1: Update Pure metadata

- Use the endpoint '/v2/articles/uuid' of the datasets registered in Pure.
- Check the field 'references', 'resource_title' and 'resource_doi' are non-empty.
- If there is a related publication but no related publication in Pure, export the dataset id, related publication title and DOI to update Pure metadata.

Step 2: Update 4TU metadata
- Use the endpoint '/v2/articles/uuid' of the datasets registered in Pure, that have a related publication in Pure.
- Check for these datasets that the field 'references', 'resource_title' and 'resource_doi' are empty.
- If there is no related publication but a related publication in Pure, update 4TU metadata with related publication title and DOI. (v2/account/articles/dataset-id PUT method requires TOKEN authentication)

## Languages

Bash or Python