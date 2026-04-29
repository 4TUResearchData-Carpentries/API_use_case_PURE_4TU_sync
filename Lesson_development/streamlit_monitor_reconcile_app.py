from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import time

from wur_pure_4tu_reconcile import (
    read_candidates_from_csv,
    reconcile,
)

# ------------------------------------------------------------
# Shared configuration
# ------------------------------------------------------------

DEFAULT_BASE_URL = os.getenv("FOURTU_BASE_URL", "https://data.4tu.nl").rstrip("/")
DEFAULT_TIMEOUT = int(os.getenv("FOURTU_TIMEOUT", "30"))
TOKEN = os.getenv("FOURTU_TOKEN", "").strip()

DEFAULT_PUBLISHED_SINCE = os.getenv("UC01_PUBLISHED_SINCE", "2025-01-01")
DEFAULT_PAGE_SIZE = int(os.getenv("UC01_PAGE_SIZE", "100")) # max 11754 datasets
DEFAULT_MAX_PAGES = int(os.getenv("UC01_MAX_PAGES", "3"))


st.set_page_config(
    page_title="WUR 4TU ResearchData tools",
    layout="wide",
)


def headers() -> Dict[str, str]:
    h = {"Accept": "application/json"}
    if TOKEN:
        h["Authorization"] = f"token {TOKEN}"
    return h


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ------------------------------------------------------------
# Monitoring dashboard functions
# ------------------------------------------------------------

def get_groups(base_url: str, timeout: int) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v3/groups"
    r = requests.get(url, headers=headers(), timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def get_articles_page(
    *,
    base_url: str,
    timeout: int,
    item_type: int,
    published_since: str,
    limit: int,
    offset: int,
    max_retries: int = 5,
) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v2/articles"
    params = {
        "item_type": item_type,
        "published_since": published_since,
        "limit": limit,
        "offset": offset,
    }

    for attempt in range(max_retries):
        r = requests.get(url, headers=headers(), params=params, timeout=timeout)

        if r.status_code == 429:
            wait_seconds = 2 ** attempt
            st.warning(
                f"Rate limit reached. Waiting {wait_seconds} seconds before retrying..."
            )
            time.sleep(wait_seconds)
            continue

        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    raise RuntimeError(
        "4TU API rate limit was reached repeatedly. "
        "Try a smaller page size or a narrower published_since date."
    )

def get_recent_articles(
    *,
    base_url: str,
    timeout: int,
    item_type: int,
    published_since: str,
    page_size: int,
    max_pages: int,
) -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []

    for page in range(max_pages):
        offset = page * page_size
        batch = get_articles_page(
            base_url=base_url,
            timeout=timeout,
            item_type=item_type,
            published_since=published_since,
            limit=page_size,
            offset=offset,
        )
        all_items.extend(batch)

        if len(batch) < page_size:
            break

    return all_items


def build_group_map(groups: List[Dict[str, Any]]) -> Dict[int, str]:
    out: Dict[int, str] = {}

    for g in groups:
        gid = g.get("id")
        name = g.get("name")

        if isinstance(gid, int) and isinstance(name, str):
            out[gid] = name

    return out


def monitoring_to_dataframe(
    articles: List[Dict[str, Any]],
    group_map: Dict[int, str],
) -> pd.DataFrame:
    rows = []

    for a in articles:
        gid = a.get("group_id")
        rows.append(
            {
                "id": a.get("id"),
                "title": a.get("title"),
                "published_date": a.get("published_date"),
                "group_id": gid,
                "group_name": group_map.get(gid, "Unknown"),
                "doi": a.get("doi"),
                "uuid": a.get("uuid"),
                "url": a.get("url"),
            }
        )

    df = pd.DataFrame(rows)

    if "published_date" in df.columns:
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")

    return df


@st.cache_data(show_spinner=True)
def load_monitoring_data_cached(
    *,
    base_url: str,
    timeout: int,
    item_type: int,
    published_since: str,
    page_size: int,
    max_pages: int,
) -> pd.DataFrame:
    groups = get_groups(base_url, timeout)
    group_map = build_group_map(groups)

    articles = get_recent_articles(
        base_url=base_url,
        timeout=timeout,
        item_type=item_type,
        published_since=published_since,
        page_size=page_size,
        max_pages=max_pages,
    )

    return monitoring_to_dataframe(articles, group_map)


# ------------------------------------------------------------
# Page 1: Monitoring dashboard
# ------------------------------------------------------------

def run_monitoring_dashboard() -> None:
    st.title("4TU Dataset/Software Monitoring Dashboard")
    st.caption("Monitor datasets and software records from 4TU.ResearchData.")

    with st.sidebar:
        st.header("Monitoring settings")

        base_url = st.text_input(
            "4TU base URL",
            value=DEFAULT_BASE_URL,
            key="monitoring_base_url",
        )

        timeout = st.number_input(
            "HTTP timeout, in seconds",
            min_value=5,
            max_value=120,
            value=DEFAULT_TIMEOUT,
            step=5,
            key="monitoring_timeout",
        )

        use_cache = st.checkbox(
            "Use Streamlit cache",
            value=True,
            key="monitoring_use_cache",
        )

        refresh = st.button(
            "Refresh monitoring data",
            key="monitoring_refresh",
        )

        st.header("Query")

        item_type_label = st.selectbox(
            "Item type",
            ["Dataset (3)", "Software (9)"],
            index=0,
            key="monitoring_item_type",
        )

        item_type = 3 if item_type_label.startswith("Dataset") else 9

        PUBLISHED_SINCE_INTERNAL = "2000-01-01"

        page_size = st.number_input(
            "page_size",
            min_value=10,
            max_value=500,
            value=100,
            step=10,
            key="monitoring_page_size",
        )

        max_pages = st.number_input(
            "max_pages",
            min_value=1,
            max_value=50,
            value=DEFAULT_MAX_PAGES,
            step=1,
            key="monitoring_max_pages",
        )

    if refresh:
        load_monitoring_data_cached.clear()

    try:
        if use_cache:
            df = load_monitoring_data_cached(
                base_url=base_url,
                timeout=int(timeout),
                item_type=item_type,
                published_since=PUBLISHED_SINCE_INTERNAL,
                page_size=int(page_size),
                max_pages=int(max_pages),
            )
        else:
            groups = get_groups(base_url, int(timeout))
            group_map = build_group_map(groups)
            articles = get_recent_articles(
                base_url=base_url,
                timeout=int(timeout),
                item_type=item_type,
                published_since=published_since,
                page_size=int(page_size),
                max_pages=int(max_pages),
            )
            df = monitoring_to_dataframe(articles, group_map)

    except Exception as exc:
        st.error(f"Could not load monitoring data: {exc}")
        st.stop()

    if df.empty:
        st.warning("No results returned. Try a different date or increase max_pages.")
        st.stop()

    with st.sidebar:
        st.header("Filters")

        group_options = sorted(
            [
                g
                for g in df["group_name"].dropna().unique().tolist()
                if isinstance(g, str)
            ]
        )

        group_choice = st.selectbox(
            "Affiliation/group",
            ["All"] + group_options,
            key="monitoring_group_filter",
        )

        date_series = df["published_date"].dropna()

        if not date_series.empty:
            min_d = date_series.min().date()
            max_d = date_series.max().date()
            start_d, end_d = st.date_input(
                "Publication date range",
                value=(min_d, max_d),
                key="monitoring_date_filter",
            )
        else:
            start_d = end_d = None
            st.info("No published_date found to filter on.")

        keyword = st.text_input(
            "Keyword in title",
            value="",
            key="monitoring_keyword",
        ).strip()

    filtered = df.copy()

    if group_choice != "All":
        filtered = filtered[filtered["group_name"] == group_choice]

    if start_d and end_d and filtered["published_date"].notna().any():
        filtered = filtered[
            (filtered["published_date"].dt.date >= start_d)
            & (filtered["published_date"].dt.date <= end_d)
        ]

    if keyword:
        filtered = filtered[
            filtered["title"]
            .fillna("")
            .str.contains(keyword, case=False, na=False)
        ]

    col1, col2 = st.columns([1, 3])

    with col1:
        st.metric("Results", int(len(filtered)))

        st.download_button(
            "Download monitoring CSV",
            data=dataframe_to_csv_bytes(
                filtered.drop(columns=["group_id"], errors="ignore")
            ),
            file_name=f"4tu_monitoring_item_type_{item_type}.csv",
            mime="text/csv",
        )

    with col2:
        st.dataframe(
            filtered.drop(columns=["group_id"], errors="ignore"),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Diagnostics"):
        st.write("Loaded rows:", len(df))
        st.write("Filtered rows:", len(filtered))
        st.write("Columns:", list(df.columns))

    st.subheader("Quick plot")

    plot_choice = st.selectbox(
        "Choose a plot",
        [
            "Items per group",
            "Items per publication date",
        ],
        key="monitoring_plot_choice",
    )

    if plot_choice == "Items per group":
        plot_df = (
            filtered["group_name"]
            .fillna("Unknown")
            .value_counts()
            .rename_axis("group_name")
            .reset_index(name="count")
        )

        st.write("Number of items per affiliation/group")
        st.bar_chart(plot_df.set_index("group_name"))

    elif plot_choice == "Items per publication date":
        date_plot_df = filtered.dropna(subset=["published_date"]).copy()

        if date_plot_df.empty:
            st.info("No publication dates available for plotting.")
        else:
            date_plot_df["published_day"] = date_plot_df["published_date"].dt.date

            counts_by_day = (
                date_plot_df["published_day"]
                .value_counts()
                .sort_index()
                .rename_axis("published_day")
                .reset_index(name="count")
            )

            st.write("Number of items per publication date")
            st.bar_chart(counts_by_day.set_index("published_day"))


# ------------------------------------------------------------
# Page 2: Reconciliation workflow
# ------------------------------------------------------------

def read_csv_flexible(file) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]

    for enc in encodings:
        try:
            file.seek(0)
            return pd.read_csv(file, sep=";", encoding=enc)
        except Exception:
            continue

    raise ValueError("Could not decode CSV with supported encodings.")

def run_reconciliation_workflow() -> None:
    st.title("Pure <-> 4TU reconciliation dashboard")

    st.write(
        "Upload a semicolon-separated Pure export CSV, run the reconciliation, "
        "preview the results, and download the output CSV files."
    )

    with st.sidebar:
        st.header("Reconciliation settings")

        base_url = st.text_input(
            "4TU base URL",
            value=DEFAULT_BASE_URL,
            key="reconciliation_base_url",
        )

        group_name = st.text_input(
            "4TU group name",
            value="Wageningen University and Research",
            key="reconciliation_group_name",
        )

        include_descendants = st.checkbox(
            "Include descendant groups",
            value=False,
            key="reconciliation_include_descendants",
        )

        sleep_seconds = st.number_input(
            "Sleep between API requests, in seconds",
            min_value=0.0,
            max_value=5.0,
            value=0.2,
            step=0.1,
            key="reconciliation_sleep",
        )

        timeout = st.number_input(
            "HTTP timeout, in seconds",
            min_value=5,
            max_value=120,
            value=DEFAULT_TIMEOUT,
            step=5,
            key="reconciliation_timeout",
        )

    uploaded_file = st.file_uploader(
        "Upload input CSV",
        type=["csv"],
        help=(
            "The file must be semicolon-separated and contain the expected "
            "Pure export columns."
        ),
        key="reconciliation_upload",
    )

    if uploaded_file is None:
        st.info("Upload a Pure export CSV to start the reconciliation.")
        return

    st.subheader("Input preview")

    try:
        preview_df = read_csv_flexible(uploaded_file)
        uploaded_file.seek(0)
        st.dataframe(preview_df.head(20), use_container_width=True)
        st.caption(f"Rows in uploaded file: {len(preview_df)}")
        

    except Exception as exc:
        st.error(f"Could not read the uploaded CSV: {exc}")
        st.stop()

    uploaded_file.seek(0)

    if st.button("Run reconciliation", type="primary"):
        temp_path = None

        try:
            with st.spinner("Reading CSV and reconciling records..."):
                with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".csv",
                delete=False,
                encoding="utf-8",
                newline="",
            ) as temp_file:
                    preview_df.to_csv(temp_file, sep=";", index=False)
                    temp_path = temp_file.name
                (
                    candidates_missing_in_pure,
                    candidates_missing_in_4tu,
                ) = read_candidates_from_csv(temp_path)

                st.info(
                    f"Loaded {len(candidates_missing_in_pure)} candidates for "
                    f"`missing_in_pure` and {len(candidates_missing_in_4tu)} "
                    f"candidates for `missing_in_4tu`."
                )

                with requests.Session() as session:
                    rows_missing_in_pure, rows_missing_in_4tu = reconcile(
                        session=session,
                        base_url=base_url,
                        candidates_missing_in_pure=candidates_missing_in_pure,
                        candidates_missing_in_4tu=candidates_missing_in_4tu,
                        group_name=group_name,
                        include_descendants=include_descendants,
                        sleep_seconds=float(sleep_seconds),
                        timeout=int(timeout),
                        verbose=False,
                    )

                df_missing_in_pure = pd.DataFrame(rows_missing_in_pure)
                df_missing_in_4tu = pd.DataFrame(rows_missing_in_4tu)

            st.success("Reconciliation finished.")

            col1, col2 = st.columns(2)

            with col1:
                st.metric("Missing in Pure", len(df_missing_in_pure))

            with col2:
                st.metric("Missing in 4TU", len(df_missing_in_4tu))

            tab1, tab2 = st.tabs(["Missing in Pure", "Missing in 4TU"])

            with tab1:
                st.write(
                    "Datasets where Pure has no related publication UUID, "
                    "but 4TU contains publication-related metadata."
                )

                if df_missing_in_pure.empty:
                    st.warning("No rows found.")
                else:
                    st.dataframe(df_missing_in_pure, use_container_width=True)

                    st.download_button(
                        label="Download CSV: missing in Pure",
                        data=dataframe_to_csv_bytes(df_missing_in_pure),
                        file_name="wur_datasets_missing_pure_related_publication.csv",
                        mime="text/csv",
                    )

            with tab2:
                st.write(
                    "Datasets where Pure has a related publication UUID, "
                    "but 4TU has no publication-related metadata."
                )

                if df_missing_in_4tu.empty:
                    st.warning("No rows found.")
                else:
                    st.dataframe(df_missing_in_4tu, use_container_width=True)

                    st.download_button(
                        label="Download CSV: missing in 4TU",
                        data=dataframe_to_csv_bytes(df_missing_in_4tu),
                        file_name="wur_datasets_missing_4tu_related_publication.csv",
                        mime="text/csv",
                    )

        except Exception as exc:
            st.error(f"Error while running reconciliation: {exc}")

# ------------------------------------------------------------
# Documentation pages
# ------------------------------------------------------------

def run_markdown_documentation(title: str, markdown_path: str) -> None:
    st.title(title)

    path = Path(markdown_path)

    if not path.exists():
        st.error(f"Documentation file not found: {path}")
        return

    markdown_text = path.read_text(encoding="utf-8")
    st.markdown(markdown_text)


def run_monitoring_documentation() -> None:
    run_markdown_documentation(
        title="Documentation: 4TU monitoring dashboard",
        markdown_path="Lesson_development/Documentation/4tu_monitoring_dashboard_documentation.md",
    )


def run_reconciliation_documentation() -> None:
    run_markdown_documentation(
        title="Documentation: Pure <-> 4TU reconciliation workflow",
        markdown_path="Lesson_development/Documentation/4tu_pure_bidirectional_reconciliation_cli_do.md",
    )
# ------------------------------------------------------------
# Main integrated app
# ------------------------------------------------------------

st.title("WUR 4TU ResearchData tools")

workflow = st.radio(
    "Choose what you want to do",
    [
        "Monitor datasets/software in 4TU",
        "Reconcile Pure and 4TU publication metadata",
        "Read monitoring documentation",
        "Read reconciliation documentation",
    ],
    horizontal=True,
)

st.divider()

if workflow == "Monitor datasets/software in 4TU":
    run_monitoring_dashboard()

elif workflow == "Reconcile Pure and 4TU publication metadata":
    run_reconciliation_workflow()

elif workflow == "Read monitoring documentation":
    run_monitoring_documentation()

elif workflow == "Read reconciliation documentation":
    run_reconciliation_documentation()