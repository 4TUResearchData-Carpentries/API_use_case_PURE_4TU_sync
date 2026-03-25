1. Search API for datasets that are registered in Pure
-  The datasets that are registered in Pure are known by the spreadsheet you will share? 
Which metadata from the dataset is in the spreadsheet?
> For now: DOI, Title and date made available, but this can be adjusted.
Is this spreadsheet often updated? 
> Depends on needs, it is possible to only create it for datasets that were created in a certain period
2. Filter on datasets that have a related publication, but no related publication in Pure
- By related publication you mean the resource_title and resource_doi fields from each dataset metadata? And also, any other references attached to the publication? 
> Most importantly the resource_title and resource_doi fields, but references field can be incorporated as well.
- Do you mean filter using the spreadsheet? 
> Correct, find datasets that have no related publication in the spreadsheet (Pure), but do have a resource_title and resource_doi in 4TU.ResearchData.
3. Export list of datasets and related publication title and DOI
Update Pure metadata
- Do you mean update the spreadsheet then? 
> To update the Pure metadata, it would be best to create a new spreadsheet with dataset DOI (and/or Pure UUID) and Resource title and resource DOI. This way the links can easily be made in Pure. Pure has an API itself, but for the sake of simplicity lets focus on the 4TU API for now.
- A spreadsheet with 4TU Datasets and their respective related publications in Pure is available
Can you specify the structure of this spreadsheet in terms of column names and which type of information is in there? So, I can prepare a toy dataset for the workshop . 
> Attached is a CSV file with all 4TU datasets that are registered in Pure at WUR, with their related research output (empty cell means no related research output). This is a manually generated spreadsheet. I can adjust it if necessary. It is possible to create such a spreadsheet with new datasets from a certain period, for example last quarter. Note, some datasets appear in the list multiple times, this is the case if a dataset has multiple linked research outputs, example a preprint and a journal article, or a PhD thesis and a journal article.