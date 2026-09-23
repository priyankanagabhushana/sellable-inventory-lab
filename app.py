"""Application router with explicit public page names."""
from __future__ import annotations

import streamlit as st


page = st.navigation(
    [
        st.Page("home_page.py", title="Guided home", icon=":material/home:", default=True),
        st.Page("pages/1_Data_and_SQL.py", title="Data & SQL", icon=":material/database:", url_path="data"),
        st.Page(
            "pages/2_Forecasting_Workbench.py",
            title="Forecasting",
            icon=":material/insights:",
            url_path="forecasting",
        ),
        st.Page(
            "pages/3_Allocation_Lab.py",
            title="Allocation",
            icon=":material/account_tree:",
            url_path="allocation",
        ),
    ],
    position="sidebar",
)
page.run()
