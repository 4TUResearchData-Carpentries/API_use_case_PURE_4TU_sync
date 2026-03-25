

# Sync Pure ↔ 4TU (WUR)

## Overview

This project provides a **reconciliation workflow** between Pure and 4TU.ResearchData for datasets affiliated with Wageningen University & Research.

It identifies inconsistencies in **dataset–publication relationships** across both systems and generates actionable outputs for correction.



## Purpose

The goal of this project is to support **data consistency and interoperability** between institutional systems by:

* Detecting datasets where **publication links are missing in Pure but exist in 4TU**
* Detecting datasets where **publication links exist in Pure but are missing in 4TU**
* Producing structured CSV outputs for:

  * manual validation
  * downstream automation (e.g., API updates)



## Conceptual Workflow

The script performs a **bidirectional reconciliation**:

```
Pure CSV export
        ↓
Split datasets into two groups
        ↓
Query 4TU API (/v2/articles/{uuid})
        ↓
Filter WUR datasets
        ↓
Compare publication metadata
        ↓
Generate two outputs:
   1. Missing in Pure
   2. Missing in 4TU
```



## Outputs

The script generates two CSV files:

### 1. `missing_in_pure`

Datasets where:

* Pure has **no linked research output**
* 4TU **does contain publication metadata**

👉 Use case: update Pure records



### 2. `missing_in_4tu`

Datasets where:

* Pure **has a linked research output**
* 4TU **lacks publication metadata**

👉 Use case: input for update script using:

```
PUT /v2/account/articles/{uuid}
```

This file includes:

* UUID Research output
* Type Research output
* DOI Research output
* Title Research output



## Getting Started

### Prerequisites

* Python **3.10+** (recommended)
* Access to:

  * Pure export CSV
  * 4TU API (public endpoints for this script)


### Installation

```bash
mkdir Sync_Pure_4TU_WUR
cd Sync_Pure_4TU_WUR

python -m venv .venv
source .venv/bin/activate
```

Create a `requirements.txt`:

```
requests>=2.31
```

Install dependencies:

```bash
pip install -r requirements.txt
```



## Usage

Run the reconciliation script:

```bash
python wur_pure_4tu_reconcile.py input.csv --include-descendants --verbose
```

### Example

```bash
python Lesson_development/wur_pure_4tu_reconcile.py \
    Lesson_development/merged_dataset_ref_with_doi.csv \
    --include-descendants \
    --verbose
```



## Key Features

* ✔️ **Two-way reconciliation** between Pure and 4TU
* ✔️ **WUR-specific filtering** using group hierarchy
* ✔️ **API-driven validation** via `/v2/articles/{uuid}`
* ✔️ **Structured outputs** for audit and automation
* ✔️ **CLI-based workflow** for reproducibility
* ✔️ Designed for **data stewards and research support staff**



## Design Principles

* **Separation of concerns**
  Reading, API access, reconciliation, and output are modular

* **Reproducibility**
  CLI-based execution with explicit inputs and outputs

* **Extensibility**
  Output CSV (`missing_in_4tu`) is directly reusable for update scripts



## Next Step (Optional)

This repository is designed to integrate with a second script that:

* reads `missing_in_4tu.csv`
* performs updates via:

  ```
  PUT /v2/account/articles/{uuid}
  ```
* synchronizes publication metadata into 4TU



## License

MIT


