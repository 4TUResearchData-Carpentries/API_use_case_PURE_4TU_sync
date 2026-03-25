# Workshop: Reconciling 4TU.ResearchData and Pure Metadata using the API

## Overview

In this hands-on workshop, you will build a **command-line tool in Python** that compares datasets from **4TU.ResearchData** with a **Pure export (CSV)** and identifies datasets that:

* **Do not have a related publication in Pure**
* **But already contain publication metadata in 4TU**

This workflow supports metadata curation and helps improve links between datasets and research outputs.

---

## Learning Objectives

By the end of this workshop, you will be able to:

* Work with a real-world research data API (`/v2/articles/<uuid>`)
* Read and process structured CSV data
* Apply filtering logic based on metadata conditions
* Build a reusable **command-line interface (CLI)** in Python
* Understand a practical metadata reconciliation workflow

---

## Conceptual Workflow

We combine two sources of information:

### 1. Pure (CSV export)

* Contains datasets registered in Pure
* Indicates whether a dataset has a related research output

### 2. 4TU.ResearchData API

* Provides dataset metadata via `/v2/articles/<uuid>`
* Contains fields such as:

  * `resource_title`
  * `resource_doi`
  * `references`

---

### Goal

Identify datasets where:

* Pure → **NO related publication**
* 4TU → **HAS publication metadata**

---

## Setup Instructions

### 1. Create a project folder

```bash
mkdir wur-pure-reconcile
cd wur-pure-reconcile
```

### 2. Create a virtual environment

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install requests
```

Optional (recommended):

```bash
pip freeze > requirements.txt
```

---

## Input Data

You will use a CSV exported from Pure with the following columns:

* `UUID Dataset`
* `Title Dataset`
* `DOI Dataset`
* `UUID Research output`

### Important Rule

A dataset **has NO related publication in Pure** if:

```text
UUID Research output is empty
```

---

## Step 1 — Read and Filter the CSV

### Goal

Extract dataset UUIDs where:

* `UUID Research output` is empty

### Key idea

We only keep datasets that need reconciliation.

---

## Step 2 — Query the 4TU API

For each dataset UUID:

```text
GET /v2/articles/<uuid>
```

We extract:

* `resource_title`
* `resource_doi`
* `references`
* `group_id`

---

## Step 3 — Filter WUR Datasets

We identify WUR datasets by:

1. Calling:

```text
GET /v3/groups
```

2. Finding the group ID for:

```text
"Wageningen University & Research"
```

3. Checking:

```python
dataset.group_id == wur_group_id
```

---

## Step 4 — Apply Reconciliation Logic

Keep only datasets where:

* Pure → NO related publication
* 4TU → HAS:

  * `resource_title`
  * `resource_doi`
  * `references`

---

## Step 5 — Export Results

We generate a CSV with:

* dataset UUID
* dataset title
* dataset DOI
* 4TU publication metadata

---

## Final Script

Save the script as:

```text
wur_pure_reconcile.py
```

Run:

```bash
python wur_pure_reconcile.py "your_file.csv" --verbose
```

---

## Output

The script generates:

```text
wur_datasets_missing_pure_related_publication.csv
```

This file can be used to:

* update Pure manually
* validate metadata consistency
* support data stewardship workflows

---

## Hands-on Exercises


### Exercise 1 — Test the API manually

Pick one dataset UUID and run:

```bash
curl https://data.4tu.nl/v2/articles/<uuid>
```

Questions:

* Does it contain `resource_doi`?
* Does it contain `references`?

---

### Exercise 3 — Modify the Script

Change the logic to:

* Accept datasets even if `references` is empty
* Only require `resource_doi`

---

### Exercise 4 — Add Logging

Print:

```text
Dataset X skipped because not in WUR
Dataset Y skipped because no publication metadata
```

---

## Extensions

You can extend this workflow to:

* Automatically update 4TU metadata (`PUT /v2/account/articles/<id>`)
* Normalize DOIs before comparison
* Detect DOIs inside `references`
* Add date filtering
* Build a dashboard (e.g., Streamlit)

---

## Key Takeaways

* APIs + CSV = powerful integration workflow
* Always separate:

  * data extraction
  * filtering logic
  * output generation
* Use **UUIDs as stable identifiers**
* Start simple → iterate toward automation

---

## Summary (One Sentence)

> We identify datasets missing publication links in Pure by scanning a CSV, then verify via the 4TU API whether those datasets already contain publication metadata that can be used to improve Pure records.

---

## Instructor Notes

* Emphasize the **logic**, not just the code
* Walk through one dataset manually before coding
* Encourage participants to modify conditions
* Keep API calls visible and understandable
* Avoid premature complexity (no async, no frameworks)

---

## Next Step

Turn this script into:

* a reusable CLI tool
* a scheduled reconciliation pipeline
* or a dashboard for data stewards

---
