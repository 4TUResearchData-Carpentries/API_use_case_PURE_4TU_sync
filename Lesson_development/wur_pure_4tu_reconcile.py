#!/usr/bin/env python3
from __future__ import annotations
"""

Goal of this script
-------------------
This script compares information coming from a Pure export CSV with metadata
retrieved from 4TU.ResearchData through the API.

It creates TWO output CSV files:

1. missing_in_pure
   These are datasets where:
   - the input CSV shows that Pure has NO related publication UUID
   - but 4TU DOES contain publication-related metadata
     (resource_title and/or resource_doi and/or references)

   Interpretation:
   Pure may be missing a related publication link that already exists in 4TU.

2. missing_in_4tu
   These are datasets where:
   - the input CSV shows that Pure DOES have a related publication UUID
   - but 4TU has NO publication-related metadata
     (resource_title, resource_doi, and references are all empty)

   Interpretation:
   4TU may need to be updated with publication information that exists in Pure.

Why this is useful
------------------
This script supports reconciliation between two systems:
- Pure = institutional research information system
- 4TU.ResearchData = repository where datasets are stored

By comparing both sides, we can identify records that may need manual review
or automated update.

"""

import argparse
import csv
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


# ---------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------
# These values can be overridden from the command line, but they provide
# sensible defaults for most runs.

DEFAULT_BASE_URL = "https://data.4tu.nl"
DEFAULT_TIMEOUT = 30
DEFAULT_SLEEP = 0.2


# ---------------------------------------------------------------------
# Small utility helpers
# ---------------------------------------------------------------------
def normalize_str(value: Any) -> str:
    """
    Convert any value into a clean string.

    Why do we need this?
    - CSV files and JSON responses often contain None values
    - strings may contain extra spaces
    - we want consistent comparisons throughout the script

    Examples:
        None        -> ""
        "  abc  "   -> "abc"
        123         -> "123"
    """
    if value is None:
        return ""
    return str(value).strip()


def get_json(
    session: requests.Session,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Perform a GET request and return the parsed JSON response.

    We keep this in one helper function so that:
    - all GET requests are consistent
    - timeout handling is centralized
    - HTTP errors are raised immediately if something goes wrong
    """
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------
# Reading and splitting the input CSV
# ---------------------------------------------------------------------
def read_candidate_datasets_from_csv(
    csv_path: str,
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """
    Read the semicolon-separated input CSV and split rows into two groups.

    Group 1: pure_missing_candidates
    --------------------------------
    These are rows where "UUID Research output" is empty.
    This means the Pure export does not currently show a linked publication.

    Group 2: fourtu_missing_candidates
    ----------------------------------
    These are rows where "UUID Research output" is non-empty.
    This means Pure DOES know about a linked publication.

    Why split the rows here?
    ------------------------
    Because later we want to build two different outputs:
    - datasets potentially missing publication links in Pure
    - datasets potentially missing publication metadata in 4TU

    Each candidate is stored in a dictionary keyed by dataset UUID.
    That makes it easy to avoid processing the same dataset multiple times.
    """
    pure_missing_candidates: Dict[str, Dict[str, str]] = {}
    fourtu_missing_candidates: Dict[str, Dict[str, str]] = {}

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")

        # These are the columns we expect in the input file.
        # If one is missing, the script should fail early with a clear message.
        required = {
            "UUID 4TU",
            "Title Dataset",
            "DOI Dataset",
            "UUID Research output",
            "Type Research output",
            "DOI Research output",
            "Title Research output",
        }

        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Input CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        for row in reader:
            dataset_uuid = normalize_str(row.get("UUID 4TU"))
            if not dataset_uuid:
                # Without a 4TU dataset UUID, we cannot query the API,
                # so that row cannot be used for reconciliation.
                continue

            research_output_uuid = normalize_str(row.get("UUID Research output"))

            # We collect the Pure-side metadata here so it can later be reused
            # in the output CSVs, especially in the "missing_in_4tu" file.
            row_data = {
                "dataset_uuid": dataset_uuid,
                "dataset_title": normalize_str(row.get("Title Dataset")),
                "dataset_doi": normalize_str(row.get("DOI Dataset")),
                "pure_research_output_uuid": research_output_uuid,
                "pure_research_output_type": normalize_str(row.get("Type Research output")),
                "pure_research_output_doi": normalize_str(row.get("DOI Research output")),
                "pure_research_output_title": normalize_str(row.get("Title Research output")),
            }

            # Logic:
            # - empty UUID Research output  -> candidate for "missing in Pure"
            # - non-empty UUID Research output -> candidate for "missing in 4TU"
            #
            # setdefault() ensures that if the same dataset UUID appears more than once,
            # we only keep the first occurrence.
            if not research_output_uuid:
                pure_missing_candidates.setdefault(dataset_uuid, row_data)
            else:
                fourtu_missing_candidates.setdefault(dataset_uuid, row_data)

    return pure_missing_candidates, fourtu_missing_candidates


# ---------------------------------------------------------------------
# Group lookup utilities
# ---------------------------------------------------------------------
def get_v3_groups_payload(
    session: requests.Session,
    base_url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Retrieve the list of groups from the 4TU API.

    Why do we need this?
    --------------------
    The input CSV may include many datasets, but we only want to keep those
    belonging to WUR (or optionally its descendant groups).
    """
    url = f"{base_url.rstrip('/')}/v3/groups"
    return get_json(session, url, timeout=timeout)


def extract_groups(groups_payload: Any) -> List[Dict[str, Any]]:
    """
    Interpret the /v3/groups response.

    APIs sometimes return lists directly, but sometimes wrap lists inside
    keys like 'items', 'data', 'groups', or 'results'.

    This helper makes the script more robust to slightly different response
    shapes.
    """
    if isinstance(groups_payload, list):
        return groups_payload

    if isinstance(groups_payload, dict):
        for key in ("items", "data", "groups", "results"):
            value = groups_payload.get(key)
            if isinstance(value, list):
                return value

    raise ValueError("Could not interpret /v3/groups response shape.")


def resolve_group_id(groups: List[Dict[str, Any]], group_name: str) -> int:
    """
    Find the numeric group ID corresponding to the given group name.

    Why is this needed?
    -------------------
    The article details usually contain group IDs, not just names.
    So first we resolve the WUR group name to its ID, then compare dataset
    group IDs against that.

    This function also checks:
    - whether the group exists
    - whether the name matched more than once
    """
    wanted = group_name.casefold()
    matches = []

    for group in groups:
        name = normalize_str(group.get("name"))
        if name.casefold() == wanted:
            matches.append(group)

    if not matches:
        sample_names = [
            normalize_str(g.get("name"))
            for g in groups
            if normalize_str(g.get("name"))
        ]
        raise ValueError(
            f"Could not find group '{group_name}' in /v3/groups. "
            f"Available examples: {', '.join(sample_names[:20])}"
        )

    if len(matches) > 1:
        ids = [str(m.get("id")) for m in matches]
        raise ValueError(
            f"Group '{group_name}' matched multiple entries with ids: {', '.join(ids)}"
        )

    group_id = matches[0].get("id")
    if group_id is None:
        raise ValueError(f"Group '{group_name}' has no 'id' field")

    return int(group_id)


def collect_descendant_group_ids(
    groups: List[Dict[str, Any]],
    root_group_id: int,
) -> Set[int]:
    """
    Collect all descendant group IDs starting from one parent group.

    Why is this useful?
    -------------------
    Sometimes a dataset belongs not directly to the top-level WUR group,
    but to a child group below it.

    If --include-descendants is used, we want to accept:
    - the main WUR group
    - all groups below it in the hierarchy
    """
    by_parent: Dict[Optional[int], List[int]] = {}

    for group in groups:
        gid = group.get("id")
        parent_id = group.get("parent_id")

        if gid is None:
            continue

        try:
            gid_int = int(gid)
        except (TypeError, ValueError):
            continue

        try:
            parent_int = int(parent_id) if parent_id is not None else None
        except (TypeError, ValueError):
            parent_int = None

        by_parent.setdefault(parent_int, []).append(gid_int)

    # We perform a simple depth-first traversal using a stack.
    result: Set[int] = set()
    stack = [root_group_id]

    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(by_parent.get(current, []))

    return result


# ---------------------------------------------------------------------
# Article retrieval and classification helpers
# ---------------------------------------------------------------------
def get_article_details(
    session: requests.Session,
    base_url: str,
    dataset_uuid: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Retrieve one dataset record from /v2/articles/{uuid}.

    This endpoint gives us the 4TU-side metadata we need to compare against Pure.
    """
    url = f"{base_url.rstrip('/')}/v2/articles/{dataset_uuid}"
    data = get_json(session, url, timeout=timeout)

    if not isinstance(data, dict):
        raise ValueError(f"Expected object from /v2/articles/{dataset_uuid}")

    return data


def is_nonempty_references(value: Any) -> bool:
    """
    Check whether the 'references' field should be treated as non-empty.

    Why not just do bool(value)?
    ----------------------------
    Because the field may come as:
    - an empty list
    - a list with blank strings
    - a string
    - a dictionary
    - or some other structure

    We want a slightly more careful interpretation.
    """
    if not value:
        return False

    if isinstance(value, list):
        return any(str(v).strip() for v in value)

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, dict):
        return len(value) > 0

    return True


def dataset_belongs_to_wur(
    article_details: Dict[str, Any],
    allowed_group_ids: Set[int],
) -> bool:
    """
    Check whether the dataset belongs to WUR.

    The exact group information may appear in different places in the response:
    - article_details["group_id"]
    - article_details["group"]["id"]
    - article_details["institution_group"]["id"]

    We collect all candidate IDs we can find and then test whether any of them
    matches the allowed WUR group IDs.
    """
    candidate_ids: List[int] = []

    if "group_id" in article_details:
        try:
            candidate_ids.append(int(article_details["group_id"]))
        except (TypeError, ValueError):
            pass

    for group_obj in (
        article_details.get("group"),
        article_details.get("institution_group"),
    ):
        if isinstance(group_obj, dict) and "id" in group_obj:
            try:
                candidate_ids.append(int(group_obj["id"]))
            except (TypeError, ValueError):
                pass

    return any(gid in allowed_group_ids for gid in candidate_ids)


def has_any_4tu_publication_fields(article_details: Dict[str, Any]) -> bool:
    """
    Return True if 4TU contains ANY publication-related metadata.

    Used for the first output CSV:
    - Pure is missing a research output UUID
    - but 4TU already has at least some publication information

    We interpret "has publication info" broadly:
    - resource_title is non-empty OR
    - resource_doi is non-empty OR
    - references is non-empty
    """
    resource_title = normalize_str(article_details.get("resource_title"))
    resource_doi = normalize_str(article_details.get("resource_doi"))
    references = article_details.get("references")

    return bool(resource_title) or bool(resource_doi) or is_nonempty_references(references)


def has_empty_4tu_publication_fields(article_details: Dict[str, Any]) -> bool:
    """
    Return True if 4TU has NO publication-related metadata.

    Used for the second output CSV:
    - Pure has a research output UUID
    - but 4TU has no related publication information

    Here we use a strict definition of "empty":
    - resource_title is empty
    - resource_doi is empty
    - references is empty
    """
    resource_title = normalize_str(article_details.get("resource_title"))
    resource_doi = normalize_str(article_details.get("resource_doi"))
    references = article_details.get("references")

    return (
        not resource_title
        and not resource_doi
        and not is_nonempty_references(references)
    )


# ---------------------------------------------------------------------
# Output row builders
# ---------------------------------------------------------------------
def build_row_missing_in_pure(
    dataset_uuid: str,
    candidate: Dict[str, str],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a row for the "missing_in_pure" output CSV.

    Context
    -------
    This output captures datasets where:
    - the input CSV (Pure export) has NO "UUID Research output"
    - but 4TU DOES contain publication-related metadata

    Interpretation
    --------------
    These datasets may indicate that:
    - a related publication exists in 4TU
    - but the link has not been registered in Pure

    Purpose of this row
    -------------------
    The goal of this output is primarily:
    - auditing
    - manual review
    - potential back-propagation of information into Pure

    Field selection rationale
    -------------------------
    This row includes:
    - Dataset identifiers (UUID, title, DOI)
    - The (empty) Pure research output UUID for reference
    - The current 4TU publication-related fields

    It intentionally does NOT include full Pure publication metadata,
    because by definition this set lacks that information.

    Parameters
    ----------
    dataset_uuid : str
        The UUID of the dataset in 4TU.

    candidate : dict
        Row extracted from the input CSV, containing:
        - dataset_title
        - dataset_doi
        - pure_research_output_uuid (expected to be empty here)

    details : dict
        JSON response from /v2/articles/{uuid}, containing 4TU metadata.

    Returns
    -------
    dict
        A dictionary matching the schema of the "missing_in_pure" CSV,
        ready to be written using csv.DictWriter.
    """
    return {
        "UUID Dataset": dataset_uuid,
        "Title Dataset": candidate.get("dataset_title") or normalize_str(details.get("title")),
        "DOI Dataset": candidate.get("dataset_doi") or normalize_str(details.get("doi")),
        "UUID Research output": candidate.get("pure_research_output_uuid", ""),
        "group_id": details.get("group_id"),
        "4TU resource_title": normalize_str(details.get("resource_title")),
        "4TU resource_doi": normalize_str(details.get("resource_doi")),
        "4TU references": repr(details.get("references")),
    }

def build_row_missing_in_4tu(dataset_uuid, candidate, details):
    """
    Build a row for the "missing_in_4tu" output CSV.

    Context
    -------
    This output captures datasets where:
    - the input CSV (Pure export) HAS a "UUID Research output"
    - but 4TU lacks publication-related metadata
      (resource_title, resource_doi, references are empty)

    Interpretation
    --------------
    These datasets represent actionable cases where:
    - Pure already contains a linked research output
    - but 4TU has not yet been updated with that information

    Purpose of this row
    -------------------
    This output is designed for:
    - reuse in an automated update workflow
    - specifically for PUT requests to:
        /v2/account/articles/{uuid}

    Therefore, it includes all necessary publication metadata from Pure.

    Field selection rationale
    -------------------------
    This row includes:
    - Pure publication fields:
        * UUID Research output
        * Type Research output
        * DOI Research output
        * Title Research output
    - Dataset identifiers:
        * UUID Dataset
        * Title Dataset
        * DOI Dataset
    - Current 4TU publication fields (for auditing/debugging)

    This makes the CSV suitable as a direct input for a follow-up script
    that updates 4TU records.

    Parameters
    ----------
    dataset_uuid : str
        The UUID of the dataset in 4TU.

    candidate : dict
        Row extracted from the input CSV, containing:
        - Pure publication metadata
        - Dataset metadata

    details : dict
        JSON response from /v2/articles/{uuid}, containing current 4TU metadata.

    Returns
    -------
    dict
        A dictionary matching the schema of the "missing_in_4tu" CSV,
        ready to be written using csv.DictWriter and reused in update pipelines.
    """
    return {
        "UUID Research output": candidate.get("pure_research_output_uuid", ""),
        "Type Research output": candidate.get("pure_research_output_type", ""),
        "UUID Dataset": dataset_uuid,
        "DOI Research output": candidate.get("pure_research_output_doi", ""),
        "Title Research output": candidate.get("pure_research_output_title", ""),
        "Title Dataset": candidate.get("dataset_title") or normalize_str(details.get("title")),
        "DOI Dataset": candidate.get("dataset_doi") or normalize_str(details.get("doi")),
        "group_id": details.get("group_id"),
        "4TU resource_title": normalize_str(details.get("resource_title")),
        "4TU resource_doi": normalize_str(details.get("resource_doi")),
        "4TU references": repr(details.get("references")),
    }

# ---------------------------------------------------------------------
# Main reconciliation logic
# ---------------------------------------------------------------------
def reconcile_both_outputs(
    session: requests.Session,
    base_url: str,
    pure_missing_candidates: Dict[str, Dict[str, str]],
    fourtu_missing_candidates: Dict[str, Dict[str, str]],
    wur_group_name: str,
    include_descendants: bool,
    sleep_seconds: float,
    timeout: int,
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Core reconciliation function.

    What happens here?
    ------------------
    1. Resolve the WUR group ID from /v3/groups
    2. Optionally include descendant groups
    3. Combine both candidate sets so each dataset UUID is fetched at most once
    4. Retrieve article details from /v2/articles/{uuid}
    5. Keep only datasets belonging to WUR
    6. Classify each dataset into one or both outputs

    Output 1: missing_in_pure
    -------------------------
    Candidate came from rows where Pure had no research output UUID,
    and 4TU has publication-related metadata.

    Output 2: missing_in_4tu
    ------------------------
    Candidate came from rows where Pure had a research output UUID,
    and 4TU has no publication-related metadata.
    """
    groups_payload = get_v3_groups_payload(session, base_url, timeout=timeout)
    groups = extract_groups(groups_payload)

    wur_group_id = resolve_group_id(groups, wur_group_name)
    allowed_group_ids = (
        collect_descendant_group_ids(groups, wur_group_id)
        if include_descendants
        else {wur_group_id}
    )

    if verbose:
        print(
            f"Resolved group '{wur_group_name}' to id(s): {sorted(allowed_group_ids)}",
            file=sys.stderr,
        )

    # Merge both candidate dictionaries into one master dictionary.
    # This avoids fetching the same dataset twice if it appears in both groups.
    all_candidates: Dict[str, Dict[str, str]] = {}
    all_candidates.update(pure_missing_candidates)
    all_candidates.update(fourtu_missing_candidates)

    output_missing_in_pure: List[Dict[str, Any]] = []
    output_missing_in_4tu: List[Dict[str, Any]] = []

    total = len(all_candidates)

    for index, (dataset_uuid, candidate) in enumerate(all_candidates.items(), start=1):
        if verbose and index % 25 == 0:
            print(f"Processed {index}/{total} candidate dataset UUIDs", file=sys.stderr)

        try:
            details = get_article_details(
                session=session,
                base_url=base_url,
                dataset_uuid=dataset_uuid,
                timeout=timeout,
            )
        except requests.HTTPError as exc:
            # If one dataset fails, we log it and continue with the rest.
            print(f"Warning: could not fetch dataset {dataset_uuid}: {exc}", file=sys.stderr)
            time.sleep(sleep_seconds)
            continue

        # Only keep WUR datasets.
        if not dataset_belongs_to_wur(details, allowed_group_ids):
            time.sleep(sleep_seconds)
            continue

        # Case 1: dataset is a candidate for "missing in Pure"
        if dataset_uuid in pure_missing_candidates:
            if has_any_4tu_publication_fields(details):
                output_missing_in_pure.append(build_row_missing_in_pure(dataset_uuid, candidate, details))

        # Case 2: dataset is a candidate for "missing in 4TU"
        if dataset_uuid in fourtu_missing_candidates:
            if has_empty_4tu_publication_fields(details):
                output_missing_in_4tu.append(build_row_missing_in_4tu(dataset_uuid, candidate, details))

        # Gentle pause between requests to avoid hammering the API.
        time.sleep(sleep_seconds)

    return output_missing_in_pure, output_missing_in_4tu


# ---------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------
def write_output_csv_missing_in_pure(rows: List[Dict[str, Any]], output_csv: str) -> None:
    """
    Write the first output CSV:
    datasets where Pure is missing a publication link, but 4TU has one.

    This output does not strictly need all Pure publication fields, because
    by definition the Pure publication UUID is empty in this set.
    """
    fieldnames = [
        "UUID Dataset",
        "Title Dataset",
        "DOI Dataset",
        "UUID Research output",
        "group_id",
        "4TU resource_title",
        "4TU resource_doi",
        "4TU references",
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_output_csv_missing_in_4tu(rows: List[Dict[str, Any]], output_csv: str) -> None:
    """
    Write the second output CSV:
    datasets where Pure has publication information, but 4TU does not.

    This CSV intentionally includes the Pure publication fields so it can be
    reused later as input for a separate update script using:
        PUT /v2/account/articles/{uuid}

    In other words, this file is designed not only for review, but also for
    downstream action.
    """
    fieldnames = [
        "UUID Research output",
        "Type Research output",
        "UUID Dataset",
        "DOI Research output",
        "Title Research output",
        "Title Dataset",
        "DOI Dataset",
        "group_id",
        "4TU resource_title",
        "4TU resource_doi",
        "4TU references",
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """
    Define the CLI arguments.

    This makes the script reusable from the command line without editing
    the Python file itself.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Read a Pure export CSV and create two reconciliation outputs: "
            "(1) datasets where Pure lacks a related publication but 4TU has one, and "
            "(2) datasets where Pure has a related publication but 4TU lacks it."
        )
    )
    parser.add_argument("input_csv", help="Path to the semicolon-separated Pure export CSV")
    parser.add_argument(
        "--output-csv-missing-in-pure",
        default="wur_datasets_missing_pure_related_publication.csv",
        help="Output CSV for datasets where Pure is missing related-publication links",
    )
    parser.add_argument(
        "--output-csv-missing-in-4tu",
        default="wur_datasets_missing_4tu_related_publication.csv",
        help="Output CSV for datasets where 4TU is missing related-publication links",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL of the 4TU ResearchData instance",
    )
    parser.add_argument(
        "--wur-group-name",
        default="Wageningen University and Research",
        help="Exact WUR group name as it appears in /v3/groups",
    )
    parser.add_argument(
        "--include-descendants",
        action="store_true",
        help="Also accept child groups of the resolved WUR group",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP,
        help="Sleep interval between requests in seconds",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information to stderr",
    )
    return parser


# ---------------------------------------------------------------------
# Main program entry point
# ---------------------------------------------------------------------
def main() -> int:
    """
    Main execution flow of the script.

    High-level logic:
    -----------------
    1. Parse CLI arguments
    2. Read and split the input CSV into two candidate groups
    3. Query the API and reconcile the metadata
    4. Write the two output CSVs
    5. Return exit code 0 on success, 1 on failure
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        pure_missing_candidates, fourtu_missing_candidates = read_candidate_datasets_from_csv(
            args.input_csv
        )

        print(
            f"Loaded {len(pure_missing_candidates)} candidates with empty 'UUID Research output'",
            file=sys.stderr,
        )
        print(
            f"Loaded {len(fourtu_missing_candidates)} candidates with non-empty 'UUID Research output'",
            file=sys.stderr,
        )

        with requests.Session() as session:
            rows_missing_in_pure, rows_missing_in_4tu = reconcile_both_outputs(
                session=session,
                base_url=args.base_url,
                pure_missing_candidates=pure_missing_candidates,
                fourtu_missing_candidates=fourtu_missing_candidates,
                wur_group_name=args.wur_group_name,
                include_descendants=args.include_descendants,
                sleep_seconds=args.sleep,
                timeout=args.timeout,
                verbose=args.verbose,
            )

        write_output_csv_missing_in_pure(
            rows_missing_in_pure,
            args.output_csv_missing_in_pure,
        )
        write_output_csv_missing_in_4tu(
            rows_missing_in_4tu,
            args.output_csv_missing_in_4tu,
        )

        print(
            f"Wrote {args.output_csv_missing_in_pure} with {len(rows_missing_in_pure)} rows",
            file=sys.stderr,
        )
        print(
            f"Wrote {args.output_csv_missing_in_4tu} with {len(rows_missing_in_4tu)} rows",
            file=sys.stderr,
        )

        return 0

    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        if exc.response is not None:
            print(exc.response.text[:1000], file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())