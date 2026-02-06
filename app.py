import streamlit as st
import pandas as pd
from datetime import date
import os
import uuid

# --- APP CONFIG & SETUP ---
st.set_page_config(page_title="VibeCheck Productivity", layout="centered")
DATA_FILE = "tasks.csv"

# --- Helpers ---
def load_df(path=DATA_FILE):
    if os.path.exists(path):
        df_local = pd.read_csv(path)
        expected = ["id", "Task", "Subtask 1", "Subtask 2", "Due Date", "Done"]
        for col in expected:
            if col not in df_local.columns:
                df_local[col] = ""
        try:
            df_local["Due Date"] = pd.to_datetime(df_local["Due Date"], errors="coerce").dt.date
        except Exception:
            df_local["Due Date"] = df_local["Due Date"].apply(lambda v: v if isinstance(v, date) else pd.NaT)
        df_local["Done"] = df_local["Done"].astype(bool)
        if "id" not in df_local.columns or df_local["id"].isnull().any():
            df_local["id"] = df_local.get("id", pd.Series([None]*len(df_local))).fillna("").apply(
                lambda v: v if v else uuid.uuid4().hex
            )
        return df_local
    else:
        return pd.DataFrame(columns=["id", "Task", "Subtask 1", "Subtask 2", "Due Date", "Done"])

def save_df(df_local, path=DATA_FILE):
    df_to_save = df_local.copy()
    df_to_save["Due Date"] = df_to_save["Due Date"].apply(lambda d: d.isoformat() if isinstance(d, date) else "")
    df_to_save.to_csv(path, index=False)

def set_done_from_checkbox(task_id):
    checkbox_key = f"check_{task_id}"
    new_value = st.session_state.get(checkbox_key, False)
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if mask.any():
        df.loc[mask, "Done"] = bool(new_value)
        save_df(df)
        st.experimental_rerun()

def delete_task(task_id=None, *args, **kwargs):
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    if task_id is None:
        return
    df = st.session_state["df"]
    st.session_state["df"] = df[df["id"] != task_id].reset_index(drop=True)
    save_df(st.session_state["df"])
    # Clear editing state if the deleted task was being edited
    if st.session_state.get("editing") == task_id:
        st.session_state.pop("editing", None)
    st.experimental_rerun()

def save_edits(task_id, new_task, new_sub1, new_sub2, new_due):
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        st.warning("Task not found (it may have been deleted).")
        return
    df.loc[mask, "Task"] = new_task
    df.loc[mask, "Subtask 1"] = new_sub1
    df.loc[mask, "Subtask 2"] = new_sub2
    df.loc[mask, "Due Date"] = pd.to_datetime(new_due).date() if new_due else ""
    st.session_state["df"] = df
    save_df(st.session_state["df"])
    # close edit mode
    st.session_state.pop("editing", None)
    st.success("Task updated.")
    st.experimental_rerun()

# Initialize session state
if "df" not in st.session_state:
    st.session_state["df"] = load_df()
if "editing" not in st.session_state:
    st.session_state["editing"] = None

# --- SIDEBAR: INPUT ---
with st.sidebar:
    st.header("✨ New Task")
    with st.form("task_form", clear_on_submit=True):
        task_name = st.text_input("What's the big goal?", key="new_task_name")
        sub1 = st.text_input("Sub-task/Detail 1", key="new_sub1")
        sub2 = st.text_input("Sub-task/Detail 2", key="new_sub2")
        due = st.date_input("Due Date", value=date.today(), key="new_due")

        if st.form_submit_button("Add to List"):
            if task_name:
                new_row = {
                    "id": uuid.uuid4().hex,
                    "Task": task_name,
                    "Subtask 1": sub1,
                    "Subtask 2": sub2,
                    "Due Date": due,
                    "Done": False,
                }
                st.session_state["df"] = pd.concat([st.session_state["df"], pd.DataFrame([new_row])], ignore_index=True)
                save_df(st.session_state["df"])
                st.success("Task added!")

# --- MAIN VIEW: ORGANIZED LIST ---
st.title("🚀 My Focus List")

if st.session_state["df"].empty:
    st.info("Your list is empty. Add a task in the sidebar to get started!")
else:
    # Prepare display dataframe
    display_df = st.session_state["df"].copy()
    display_df["Due Date"] = pd.to_datetime(display_df["Due Date"], errors="coerce").dt.date
    display_df = display_df.sort_values(by=["Due Date", "Task"], na_position="last")

    pending = display_df[display_df["Done"] == False]
    completed = display_df[display_df["Done"] == True]

    def fmt_date_header(d):
        if pd.isna(d):
            return "No Due Date"
        if isinstance(d, date):
            return d.strftime("%A, %b %d, %Y")
        return str(d)

    def render_task_row(row, show_delete=True, allow_edit=True):
        task_id = row["id"]
        # Layout: narrow checkbox | main content | edit button | delete button
        cb_col, content_col, edit_col, del_col = st.columns([0.05, 0.78, 0.07, 0.07])
        cb_col.checkbox(
            "",
            value=bool(row["Done"]),
            key=f"check_{task_id}",
            on_change=set_done_from_checkbox,
            args=(task_id,)
        )

        with content_col:
            due_display = row["Due Date"].isoformat() if isinstance(row["Due Date"], date) else ""
            st.markdown(f"**{row['Task']}** — :calendar: `{due_display}`")
            if row.get("Subtask 1") or row.get("Subtask 2"):
                with st.expander("View Details"):
                    if row.get("Subtask 1"):
                        st.write(f"• {row['Subtask 1']}")
                    if row.get("Subtask 2"):
                        st.write(f"• {row['Subtask 2']}")

            # Inline edit form shown when this task is in edit mode
            if allow_edit and st.session_state.get("editing") == task_id:
                form_key = f"inline_edit_{task_id}"
                with st.form(form_key, clear_on_submit=False):
                    e_task = st.text_input("", value=row["Task"], key=f"inline_task_{task_id}")
                    e_sub1 = st.text_input("", value=row.get("Subtask 1", ""), key=f"inline_sub1_{task_id}")
                    e_sub2 = st.text_input("", value=row.get("Subtask 2", ""), key=f"inline_sub2_{task_id}")
                    initial_due = row["Due Date"] if isinstance(row["Due Date"], date) else date.today()
                    e_due = st.date_input("", value=initial_due, key=f"inline_due_{task_id}")
                    cols = st.columns([1,1])
                    if cols[0].form_submit_button("Save"):
                        save_edits(task_id, e_task, e_sub1, e_sub2, e_due)
                    if cols[1].form_submit_button("Cancel"):
                        st.session_state.pop("editing", None)
                        st.experimental_rerun()

        # Small edit button (emoji) in narrow column
        with edit_col:
            # clicking opens inline editor for this task
            if st.button("✏️", key=f"edit_btn_{task_id}"):
                st.session_state["editing"] = task_id
                st.experimental_rerun()

        # Small delete button (emoji) in narrow column
        with del_col:
            if st.button("🗑️", key=f"del_btn_{task_id}"):
                delete_task(task_id)

    # Group pending tasks by date and render with headers
    st.subheader("📅 Upcoming")
    if pending.empty:
        st.write("No upcoming tasks.")
    else:
        # Build ordered list of unique dates (NaT handled separately)
        # We'll put NaT (No Due Date) at the end
        pending_sorted = pending.copy()
        # Replace pd.NaT with None for grouping convenience
        pending_sorted["__due_sort"] = pending_sorted["Due Date"].apply(lambda d: d if pd.notna(d) else date.max)
        pending_sorted = pending_sorted.sort_values(by="__due_sort")
        groups = pending_sorted.groupby(pending_sorted["Due Date"].fillna(pd.NaT), sort=False)

        for due_value, group in groups:
            header = fmt_date_header(due_value)
            st.markdown(f"### {header}")
            for _, row in group.iterrows():
                render_task_row(row, show_delete=True, allow_edit=True)

    # Completed tasks
    if not completed.empty:
        st.write("---")
        with st.expander("✅ Completed Tasks"):
            # Optionally group completed by date as well (compact)
            comp_sorted = completed.copy().sort_values(by="Due Date", na_position="last")
            groups = comp_sorted.groupby(comp_sorted["Due Date"].fillna(pd.NaT), sort=False)
            for due_value, group in groups:
                header = fmt_date_header(due_value)
                st.markdown(f"#### {header}")
                for _, row in group.iterrows():
                    # show strike-through title and same compact controls
                    st.markdown(f"~~{row['Task']}~~")
                    render_task_row(row, show_delete=True, allow_edit=True)
