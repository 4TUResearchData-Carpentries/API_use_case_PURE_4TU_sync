import tempfile

import pandas as pd
import requests
import streamlit as st

from wur_pure_4tu_reconcile import (
    read_candidates_from_csv,
    reconcile,
)


st.set_page_config(
    page_title="Pure ↔ 4TU reconciliation",
    layout="wide",
)

st.title("Pure ↔ 4TU reconciliation dashboard")

st.write(
    "Upload a semicolon-separated Pure export CSV, run the reconciliation, "
    "preview the results, and download the output CSV files."
)


# ---------------------------------------------------------------------
# Sidebar settings
# ---------------------------------------------------------------------

st.sidebar.header("Settings")

base_url = st.sidebar.text_input(
    "4TU base URL",
    value="https://data.4tu.nl",
)

group_name = st.sidebar.text_input(
    "4TU group name",
    value="Wageningen University and Research",
)

include_descendants = st.sidebar.checkbox(
    "Include descendant groups",
    value=False,
)

sleep_seconds = st.sidebar.number_input(
    "Sleep between API requests, in seconds",
    min_value=0.0,
    max_value=5.0,
    value=0.2,
    step=0.1,
)

timeout = st.sidebar.number_input(
    "HTTP timeout, in seconds",
    min_value=5,
    max_value=120,
    value=30,
    step=5,
)


# ---------------------------------------------------------------------
# Upload input file
# ---------------------------------------------------------------------

uploaded_file = st.file_uploader(
    "Upload input CSV",
    type=["csv"],
    help=(
        "The file must be semicolon-separated and contain the expected "
        "Pure export columns."
    ),
)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """
    Convert a dataframe to CSV bytes for Streamlit download buttons.
    """
    return df.to_csv(index=False).encode("utf-8")


if uploaded_file is not None:
    st.subheader("Input preview")

    try:
        preview_df = pd.read_csv(uploaded_file, sep=";", encoding="utf-8-sig")
        st.dataframe(preview_df.head(20), use_container_width=True)
        st.caption(f"Rows in uploaded file: {len(preview_df)}")

    except Exception as exc:
        st.error(f"Could not read the uploaded CSV: {exc}")
        st.stop()

    uploaded_file.seek(0)

    if st.button("Run reconciliation", type="primary"):
        try:
            with st.spinner("Reading CSV and reconciling records..."):

                # The command-line function expects a file path.
                # Therefore, we save the uploaded Streamlit file to a temporary file.
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    suffix=".csv",
                    delete=False,
                ) as temp_file:
                    temp_file.write(uploaded_file.getbuffer())
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
                        sleep_seconds=sleep_seconds,
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