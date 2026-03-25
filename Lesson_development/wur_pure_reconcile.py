#!/usr/bin/env python3
from __future__ import annotations

# Standard library imports
import argparse
import csv
import sys
import time
from typing import Any, Dict, List, Optional, Set

# Third-party library for making HTTP requests
import requests


# Default configuration values used by the CLI
DEFAULT_BASE_URL = "https://data.4tu.nl"
DEFAULT_TIMEOUT = 30
DEFAULT_SLEEP = 0.2


def normalize_str(value: Any) -> str:
    """
    Convert any value into a clean string.

    Why this is useful:
    - CSV files and JSON responses may contain None values
    - some values may have extra whitespace
    - we want to compare and export consistent text

    Example:
        None -> ""
        "  abc  " -> "abc"
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
    Send a GET request and return the JSON response.

    We use a requests.Session so the same connection can be reused across
    multiple API calls. That is more efficient than creating a new connection
    every time.

    raise_for_status() ensures that HTTP errors (404, 500, etc.) are not
    silently ignored.
    """
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def read_candidate_datasets_from_csv(csv_path: str) -> Dict[str, Dict[str, str]]:
    """
    Read the semicolon-separated Pure export CSV.

    The workshop rule is:
    - if 'UUID Research output' is empty, then Pure has no linked publication
    - those are the datasets we want to investigate in 4TU

    We return a dictionary keyed by dataset UUID so that:
    - each dataset is stored only once
    - we avoid duplicate API calls for repeated rows in the CSV

    Output shape:
        {
            "<dataset_uuid>": {
                "dataset_uuid": "...",
                "dataset_title": "...",
                "dataset_doi": "..."
            }
        }
    """
    candidates: Dict[str, Dict[str, str]] = {}

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")

        # These are the columns the script expects to find in the input CSV
        required = {
            "UUID 4TU",
            "Title Dataset",
            "DOI Dataset",
            "UUID Research output",
        }

        # Check whether any required columns are missing
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Input CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        # Process the file row by row
        for row in reader:
            dataset_uuid = normalize_str(row.get("UUID 4TU"))
            if not dataset_uuid:
                continue

            research_output_uuid = normalize_str(row.get("UUID Research output"))

            # Keep only rows where Pure has no related publication
            if research_output_uuid:
                continue

            # Store only the first occurrence of each dataset UUID
            if dataset_uuid not in candidates:
                candidates[dataset_uuid] = {
                    "dataset_uuid": dataset_uuid,
                    "dataset_title": normalize_str(row.get("Title Dataset")),
                    "dataset_doi": normalize_str(row.get("DOI Dataset")),
                }

    return candidates


def get_v3_groups_payload(
    session: requests.Session,
    base_url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Request the list of groups from the /v3/groups endpoint.

    We will use this endpoint to find the numeric group id for WUR.
    Later, we compare the dataset's group_id with that WUR group id.
    """
    url = f"{base_url.rstrip('/')}/v3/groups"
    return get_json(session, url, timeout=timeout)


def extract_groups(groups_payload: Any) -> List[Dict[str, Any]]:
    """
    Extract the list of groups from the JSON payload returned by /v3/groups.

    APIs sometimes wrap lists in different keys such as:
    - items
    - data
    - groups
    - results

    This helper makes the script more robust to small variations in the
    response structure.
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
    Find the numeric id of a group by its name.

    We do a case-insensitive exact match on the group name.

    Example:
        'Wageningen University & Research' -> 1234
    """
    wanted = group_name.casefold()
    matches = []

    for group in groups:
        name = normalize_str(group.get("name"))
        if name.casefold() == wanted:
            matches.append(group)

    if not matches:
        sample_names = [normalize_str(g.get("name")) for g in groups if normalize_str(g.get("name"))]
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
    Collect the root group id and all of its child groups.

    This is useful when a parent institution has subgroups and we want to
    include them as part of the same institution.

    The function uses parent_id relationships to walk through the hierarchy.
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

    result: Set[int] = set()
    stack = [root_group_id]

    # Depth-first traversal of the group tree
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(by_parent.get(current, []))

    return result


def get_article_details(
    session: requests.Session,
    base_url: str,
    dataset_uuid: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Request the full metadata for one dataset using /v2/articles/<uuid>.

    This endpoint gives us access to the fields we need to inspect:
    - resource_title
    - resource_doi
    - references
    - group_id
    """
    url = f"{base_url.rstrip('/')}/v2/articles/{dataset_uuid}"
    data = get_json(session, url, timeout=timeout)

    if not isinstance(data, dict):
        raise ValueError(f"Expected object from /v2/articles/{dataset_uuid}")

    return data


def is_nonempty_references(value: Any) -> bool:
    """
    Decide whether the references field should be considered non-empty.

    Why we need this helper:
    - references might be a list
    - or a string
    - or a dictionary
    - or None

    We want a single yes/no check regardless of the exact shape.
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
    Check whether a dataset belongs to WUR.

    The most common case is that the dataset detail has a top-level group_id.
    We also check a couple of fallback shapes in case the API embeds group
    information differently.
    """
    candidate_ids: List[int] = []

    # Most likely location of the group id
    if "group_id" in article_details:
        try:
            candidate_ids.append(int(article_details["group_id"]))
        except (TypeError, ValueError):
            pass

    # Fallbacks in case the API includes group information as a nested object
    for group_obj in (article_details.get("group"), article_details.get("institution_group")):
        if isinstance(group_obj, dict) and "id" in group_obj:
            try:
                candidate_ids.append(int(group_obj["id"]))
            except (TypeError, ValueError):
                pass

    return any(gid in allowed_group_ids for gid in candidate_ids)


def has_required_4tu_publication_fields(article_details: Dict[str, Any]) -> bool:
    """
    Apply the workshop rule for deciding whether 4TU contains enough
    publication information.

    A dataset qualifies only if all three are non-empty:
    - resource_title
    - resource_doi
    - references
    """
    resource_title = normalize_str(article_details.get("resource_title"))
    resource_doi = normalize_str(article_details.get("resource_doi"))
    references = article_details.get("references")

    return (
    bool(resource_doi) or is_nonempty_references(references)
    )



def build_output_row(
    dataset_uuid: str,
    candidate: Dict[str, str],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build one output row for the result CSV.

    We take title and DOI from the input CSV when available, and fall back
    to the API response if needed.
    """
    return {
        "dataset_uuid": dataset_uuid,
        "dataset_title": candidate.get("dataset_title") or normalize_str(details.get("title")),
        "dataset_doi": candidate.get("dataset_doi") or normalize_str(details.get("doi")),
        "group_id": details.get("group_id"),
        "fourtu_resource_title": normalize_str(details.get("resource_title")),
        "fourtu_resource_doi": normalize_str(details.get("resource_doi")),
        "fourtu_references": repr(details.get("references")),
    }


def reconcile(
    session: requests.Session,
    base_url: str,
    candidates: Dict[str, Dict[str, str]],
    wur_group_name: str,
    include_descendants: bool,
    sleep_seconds: float,
    timeout: int,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Main reconciliation workflow.

    Steps:
    1. Resolve the WUR group id
    2. Loop through candidate dataset UUIDs from the CSV
    3. Fetch each dataset from /v2/articles/<uuid>
    4. Check whether it belongs to WUR
    5. Check whether it has the required publication metadata in 4TU
    6. If yes, add it to the output list
    """
    groups_payload = get_v3_groups_payload(session, base_url, timeout=timeout)
    groups = extract_groups(groups_payload)

    wur_group_id = resolve_group_id(groups, wur_group_name)

    if include_descendants:
        allowed_group_ids = collect_descendant_group_ids(groups, wur_group_id)
    else:
        allowed_group_ids = {wur_group_id}

    if verbose:
        print(
            f"Resolved group '{wur_group_name}' to id(s): {sorted(allowed_group_ids)}",
            file=sys.stderr,
        )

    results: List[Dict[str, Any]] = []
    total = len(candidates)

    for index, (dataset_uuid, candidate) in enumerate(candidates.items(), start=1):
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
            # Do not stop the whole script for one failed dataset
            print(f"Warning: could not fetch dataset {dataset_uuid}: {exc}", file=sys.stderr)
            time.sleep(sleep_seconds)
            continue

        # Check whether this dataset belongs to WUR
        if not dataset_belongs_to_wur(details, allowed_group_ids):
            time.sleep(sleep_seconds)
            continue

        # Check whether the required publication fields are present in 4TU
        if has_required_4tu_publication_fields(details):
            results.append(build_output_row(dataset_uuid, candidate, details))

        # Small pause between requests to be polite to the API
        time.sleep(sleep_seconds)

    return results


def write_output_csv(rows: List[Dict[str, Any]], output_csv: str) -> None:
    """
    Write the reconciliation results to a CSV file.
    """
    fieldnames = [
        "dataset_uuid",
        "dataset_title",
        "dataset_doi",
        "group_id",
        "fourtu_resource_title",
        "fourtu_resource_doi",
        "fourtu_references",
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    """
    Define the command-line interface.

    This allows the script to be run from a terminal with options like:
        --output-csv
        --wur-group-name
        --verbose
    """
    parser = argparse.ArgumentParser(
        description=(
            "Read a Pure export CSV, keep only rows where 'UUID Research output' is empty, "
            "check each dataset in 4TU by UUID, validate whether it belongs to WUR, "
            "and export datasets that have resource_title, resource_doi, and references in 4TU."
        )
    )
    parser.add_argument("input_csv", help="Path to the semicolon-separated Pure export CSV")
    parser.add_argument(
        "--output-csv",
        default="wur_datasets_missing_pure_related_publication.csv",
        help="Output CSV path",
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


def main() -> int:
    """
    Entry point of the program.

    Responsibilities:
    - parse command-line arguments
    - read the CSV
    - run the reconciliation workflow
    - write the output CSV
    - handle errors cleanly
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        candidates = read_candidate_datasets_from_csv(args.input_csv)
        print(
            f"Loaded {len(candidates)} candidate datasets with empty 'UUID Research output'",
            file=sys.stderr,
        )

        with requests.Session() as session:
            rows = reconcile(
                session=session,
                base_url=args.base_url,
                candidates=candidates,
                wur_group_name=args.wur_group_name,
                include_descendants=args.include_descendants,
                sleep_seconds=args.sleep,
                timeout=args.timeout,
                verbose=args.verbose,
            )

        write_output_csv(rows, args.output_csv)
        print(f"Wrote {args.output_csv} with {len(rows)} rows", file=sys.stderr)
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

