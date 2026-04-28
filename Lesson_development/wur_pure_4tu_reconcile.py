#!/usr/bin/env python3


# -------------------------------------------------------------------
# Goal of this script
# -------------------------------------------------------------------
# Reconcile related-publication metadata between Pure and 4TU.ResearchData.

# This script creates two CSV reports:

# 1. missing_in_pure
#    Pure has no related research output UUID,
#    but 4TU already contains publication-related metadata.

# 2. missing_in_4tu
#    Pure has a related research output UUID,
#    but 4TU does not contain publication-related metadata.

# The script is meant for review/reconciliation, not for directly updating either system.


from __future__ import annotations

import argparse
import csv
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


# ---------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------

DEFAULT_BASE_URL = "https://data.4tu.nl"
DEFAULT_TIMEOUT = 30
DEFAULT_SLEEP = 0.2


# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

def normalize_str(value: Any) -> str:
    """
    Convert a value to a clean string.

    This avoids problems with:
    - None values
    - leading/trailing spaces
    - non-string values such as numbers
    """
    if value is None:
        return ""
    return str(value).strip()


def get_json(
    session: requests.Session,
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Send a GET request and return the JSON response.

    If the API returns an error status code, raise an exception.
    """
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def is_nonempty_references(value: Any) -> bool:
    """
    Decide whether the 4TU 'references' field contains useful content.

    The API may return references as:
    - a list
    - a string
    - a dictionary
    - None
    """
    if not value:
        return False

    if isinstance(value, list):
        return any(normalize_str(item) for item in value)

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, dict):
        return len(value) > 0

    return True


def has_any_4tu_publication_metadata(article: Dict[str, Any]) -> bool:
    """
    Return True when 4TU contains at least one publication-related field.
    """
    resource_title = normalize_str(article.get("resource_title"))
    resource_doi = normalize_str(article.get("resource_doi"))
    references = article.get("references")

    return (
        bool(resource_title)
        or bool(resource_doi)
        or is_nonempty_references(references)
    )


def has_no_4tu_publication_metadata(article: Dict[str, Any]) -> bool:
    """
    Return True when 4TU contains no publication-related metadata.
    """
    return not has_any_4tu_publication_metadata(article)


# ---------------------------------------------------------------------
# Read input CSV
# ---------------------------------------------------------------------

def read_candidates_from_csv(
    input_csv: str,
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """
    Read the Pure export CSV and split records into two candidate groups.

    Group 1: candidates_missing_in_pure
    -----------------------------------
    Dataset has a 4TU UUID, but no Pure research output UUID.

    Group 2: candidates_missing_in_4tu
    ----------------------------------
    Dataset has a 4TU UUID and also has a Pure research output UUID.
    """

    candidates_missing_in_pure: Dict[str, Dict[str, str]] = {}
    candidates_missing_in_4tu: Dict[str, Dict[str, str]] = {}

    required_columns = {
        "UUID 4TU",
        "Title Dataset",
        "DOI Dataset",
        "UUID Research output",
        "Type Research output",
        "DOI Research output",
        "Title Research output",
    }

    with open(input_csv, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")

        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                "Input CSV is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            dataset_uuid = normalize_str(row.get("UUID 4TU"))

            # Without a 4TU UUID, we cannot query the 4TU API.
            if not dataset_uuid:
                continue

            pure_output_uuid = normalize_str(row.get("UUID Research output"))

            row_data = {
                "dataset_uuid": dataset_uuid,
                "dataset_title": normalize_str(row.get("Title Dataset")),
                "dataset_doi": normalize_str(row.get("DOI Dataset")),
                "pure_output_uuid": pure_output_uuid,
                "pure_output_type": normalize_str(row.get("Type Research output")),
                "pure_output_doi": normalize_str(row.get("DOI Research output")),
                "pure_output_title": normalize_str(row.get("Title Research output")),
            }

            if pure_output_uuid:
                candidates_missing_in_4tu.setdefault(dataset_uuid, row_data)
            else:
                candidates_missing_in_pure.setdefault(dataset_uuid, row_data)

    return candidates_missing_in_pure, candidates_missing_in_4tu


# ---------------------------------------------------------------------
# 4TU API functions
# ---------------------------------------------------------------------

def get_article_details(
    session: requests.Session,
    base_url: str,
    dataset_uuid: str,
    timeout: int,
) -> Dict[str, Any]:
    """
    Retrieve the metadata record for one dataset from the 4TU API.
    """
    url = f"{base_url.rstrip('/')}/v2/articles/{dataset_uuid}"
    data = get_json(session, url, timeout=timeout)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object for dataset {dataset_uuid}")

    return data


def get_groups(
    session: requests.Session,
    base_url: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    """
    Retrieve all groups from the 4TU API.

    This is used to identify the WUR group and optionally its child groups.
    """
    url = f"{base_url.rstrip('/')}/v3/groups"
    payload = get_json(session, url, timeout=timeout)

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("items", "data", "groups", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]

    raise ValueError("Could not understand the /v3/groups API response.")


def resolve_group_id(groups: List[Dict[str, Any]], group_name: str) -> int:
    """
    Find the numeric group ID for a group name.
    """
    matches = [
        group
        for group in groups
        if normalize_str(group.get("name")).casefold() == group_name.casefold()
    ]

    if not matches:
        available_names = [
            normalize_str(group.get("name"))
            for group in groups
            if normalize_str(group.get("name"))
        ]

        raise ValueError(
            f"Could not find group '{group_name}'. "
            f"Some available group names are: {', '.join(available_names[:20])}"
        )

    if len(matches) > 1:
        ids = [str(match.get("id")) for match in matches]
        raise ValueError(
            f"Group name '{group_name}' matched multiple IDs: {', '.join(ids)}"
        )

    return int(matches[0]["id"])


def collect_descendant_group_ids(
    groups: List[Dict[str, Any]],
    root_group_id: int,
) -> Set[int]:
    """
    Collect the root group ID and all child group IDs below it.

    This is useful when datasets may belong to subgroups of WUR.
    """
    children_by_parent: Dict[Optional[int], List[int]] = {}

    for group in groups:
        group_id = group.get("id")
        parent_id = group.get("parent_id")

        if group_id is None:
            continue

        try:
            group_id_int = int(group_id)
            parent_id_int = int(parent_id) if parent_id is not None else None
        except (TypeError, ValueError):
            continue

        children_by_parent.setdefault(parent_id_int, []).append(group_id_int)

    result: Set[int] = set()
    stack = [root_group_id]

    while stack:
        current_id = stack.pop()

        if current_id in result:
            continue

        result.add(current_id)
        stack.extend(children_by_parent.get(current_id, []))

    return result


def dataset_belongs_to_allowed_group(
    article: Dict[str, Any],
    allowed_group_ids: Set[int],
) -> bool:
    """
    Check whether a dataset belongs to one of the allowed group IDs.

    4TU metadata may expose the group ID in slightly different places,
    so we check several possible fields.
    """
    candidate_group_ids: List[int] = []

    if article.get("group_id") is not None:
        try:
            candidate_group_ids.append(int(article["group_id"]))
        except (TypeError, ValueError):
            pass

    for possible_group_object in (
        article.get("group"),
        article.get("institution_group"),
    ):
        if isinstance(possible_group_object, dict):
            try:
                candidate_group_ids.append(int(possible_group_object["id"]))
            except (KeyError, TypeError, ValueError):
                pass

    return any(group_id in allowed_group_ids for group_id in candidate_group_ids)


# ---------------------------------------------------------------------
# Output row builders
# ---------------------------------------------------------------------

def build_missing_in_pure_row(
    dataset_uuid: str,
    candidate: Dict[str, str],
    article: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build one output row for the 'missing in Pure' report.
    """
    return {
        "UUID Dataset": dataset_uuid,
        "Title Dataset": candidate.get("dataset_title") or normalize_str(article.get("title")),
        "DOI Dataset": candidate.get("dataset_doi") or normalize_str(article.get("doi")),
        "UUID Research output": candidate.get("pure_output_uuid", ""),
        "group_id": article.get("group_id"),
        "4TU resource_title": normalize_str(article.get("resource_title")),
        "4TU resource_doi": normalize_str(article.get("resource_doi")),
        "4TU references": repr(article.get("references")),
    }


def build_missing_in_4tu_row(
    dataset_uuid: str,
    candidate: Dict[str, str],
    article: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build one output row for the 'missing in 4TU' report.
    """
    return {
        "UUID Research output": candidate.get("pure_output_uuid", ""),
        "Type Research output": candidate.get("pure_output_type", ""),
        "UUID Dataset": dataset_uuid,
        "DOI Research output": candidate.get("pure_output_doi", ""),
        "Title Research output": candidate.get("pure_output_title", ""),
        "Title Dataset": candidate.get("dataset_title") or normalize_str(article.get("title")),
        "DOI Dataset": candidate.get("dataset_doi") or normalize_str(article.get("doi")),
        "group_id": article.get("group_id"),
        "4TU resource_title": normalize_str(article.get("resource_title")),
        "4TU resource_doi": normalize_str(article.get("resource_doi")),
        "4TU references": repr(article.get("references")),
    }


# ---------------------------------------------------------------------
# Main reconciliation logic
# ---------------------------------------------------------------------

def reconcile(
    session: requests.Session,
    base_url: str,
    candidates_missing_in_pure: Dict[str, Dict[str, str]],
    candidates_missing_in_4tu: Dict[str, Dict[str, str]],
    group_name: str,
    include_descendants: bool,
    sleep_seconds: float,
    timeout: int,
    verbose: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compare Pure-side information with 4TU-side metadata.

    Important implementation detail
    -------------------------------
    We fetch each dataset only once, but we do NOT merge the candidate rows.

    Why?
    Because the same dataset UUID could theoretically appear in both groups.
    If we merged the dictionaries, one candidate row could overwrite the other.
    """

    groups = get_groups(session, base_url, timeout)
    root_group_id = resolve_group_id(groups, group_name)

    if include_descendants:
        allowed_group_ids = collect_descendant_group_ids(groups, root_group_id)
    else:
        allowed_group_ids = {root_group_id}

    if verbose:
        print(
            f"Allowed group IDs for '{group_name}': {sorted(allowed_group_ids)}",
            file=sys.stderr,
        )

    all_dataset_uuids = set(candidates_missing_in_pure) | set(candidates_missing_in_4tu)

    rows_missing_in_pure: List[Dict[str, Any]] = []
    rows_missing_in_4tu: List[Dict[str, Any]] = []

    total = len(all_dataset_uuids)

    for index, dataset_uuid in enumerate(sorted(all_dataset_uuids), start=1):
        if verbose:
            print(f"Processing {index}/{total}: {dataset_uuid}", file=sys.stderr)

        try:
            article = get_article_details(
                session=session,
                base_url=base_url,
                dataset_uuid=dataset_uuid,
                timeout=timeout,
            )
        except requests.RequestException as error:
            print(
                f"Warning: could not fetch dataset {dataset_uuid}: {error}",
                file=sys.stderr,
            )
            time.sleep(sleep_seconds)
            continue

        if not dataset_belongs_to_allowed_group(article, allowed_group_ids):
            time.sleep(sleep_seconds)
            continue

        # Case 1:
        # Pure has no related publication UUID,
        # but 4TU has publication-related metadata.
        if dataset_uuid in candidates_missing_in_pure:
            if has_any_4tu_publication_metadata(article):
                candidate = candidates_missing_in_pure[dataset_uuid]
                rows_missing_in_pure.append(
                    build_missing_in_pure_row(dataset_uuid, candidate, article)
                )

        # Case 2:
        # Pure has a related publication UUID,
        # but 4TU has no publication-related metadata.
        if dataset_uuid in candidates_missing_in_4tu:
            if has_no_4tu_publication_metadata(article):
                candidate = candidates_missing_in_4tu[dataset_uuid]
                rows_missing_in_4tu.append(
                    build_missing_in_4tu_row(dataset_uuid, candidate, article)
                )

        time.sleep(sleep_seconds)

    return rows_missing_in_pure, rows_missing_in_4tu


# ---------------------------------------------------------------------
# Write output CSV files
# ---------------------------------------------------------------------

def write_missing_in_pure_csv(rows: List[Dict[str, Any]], output_csv: str) -> None:
    """
    Write the report for datasets where Pure may be missing publication links.
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


def write_missing_in_4tu_csv(rows: List[Dict[str, Any]], output_csv: str) -> None:
    """
    Write the report for datasets where 4TU may be missing publication metadata.
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
    Define the command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Compare a Pure export CSV with 4TU.ResearchData metadata "
            "and create two reconciliation reports."
        )
    )

    parser.add_argument(
        "input_csv",
        help="Path to the semicolon-separated Pure export CSV.",
    )

    parser.add_argument(
        "--output-csv-missing-in-pure",
        default="wur_datasets_missing_pure_related_publication.csv",
        help="Output CSV for records where Pure may be missing a publication link.",
    )

    parser.add_argument(
        "--output-csv-missing-in-4tu",
        default="wur_datasets_missing_4tu_related_publication.csv",
        help="Output CSV for records where 4TU may be missing publication metadata.",
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL of the 4TU.ResearchData instance.",
    )

    parser.add_argument(
        "--group-name",
        default="Wageningen University and Research",
        help="Exact group name as used in the 4TU /v3/groups API.",
    )

    parser.add_argument(
        "--include-descendants",
        action="store_true",
        help="Also include child groups below the selected group.",
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP,
        help="Pause between API requests, in seconds.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout, in seconds.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information.",
    )

    return parser


# ---------------------------------------------------------------------
# Program entry point
# ---------------------------------------------------------------------

def main() -> int:
    """
    Run the complete reconciliation workflow.
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        candidates_missing_in_pure, candidates_missing_in_4tu = read_candidates_from_csv(
            args.input_csv
        )

        print(
            f"Loaded {len(candidates_missing_in_pure)} candidates for missing_in_pure.",
            file=sys.stderr,
        )
        print(
            f"Loaded {len(candidates_missing_in_4tu)} candidates for missing_in_4tu.",
            file=sys.stderr,
        )

        with requests.Session() as session:
            rows_missing_in_pure, rows_missing_in_4tu = reconcile(
                session=session,
                base_url=args.base_url,
                candidates_missing_in_pure=candidates_missing_in_pure,
                candidates_missing_in_4tu=candidates_missing_in_4tu,
                group_name=args.group_name,
                include_descendants=args.include_descendants,
                sleep_seconds=args.sleep,
                timeout=args.timeout,
                verbose=args.verbose,
            )

        write_missing_in_pure_csv(
            rows_missing_in_pure,
            args.output_csv_missing_in_pure,
        )

        write_missing_in_4tu_csv(
            rows_missing_in_4tu,
            args.output_csv_missing_in_4tu,
        )

        print(
            f"Wrote {args.output_csv_missing_in_pure} "
            f"with {len(rows_missing_in_pure)} rows.",
            file=sys.stderr,
        )

        print(
            f"Wrote {args.output_csv_missing_in_4tu} "
            f"with {len(rows_missing_in_4tu)} rows.",
            file=sys.stderr,
        )

        return 0

    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())