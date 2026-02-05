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
        # Ensure expected columns exist
        expected = ["id", "Task", "Subtask 1", "Subtask 2", "Due Date", "Done"]
        for col in expected:
            if col not in df_local.columns:
                df_local[col] = ""
        # Normalize types
        try:
            df_local["Due Date"] = pd.to_datetime(df_local["Due Date"], errors="coerce").dt.date
        except Exception:
            df_local["Due Date"] = df_local["Due Date"].apply(lambda v: v if isinstance(v, date) else pd.NaT)
        # Ensure Done is boolean
        df_local["Done"] = df_local["Done"].astype(bool)
        # Fill missing ids for backwards compatibility
        if "id" not in df_local.columns or df_local["id"].isnull().any():
            df_local["id"] = df_local.get("id", pd.Series([None]*len(df_local))).fillna("").apply(
                lambda v: v if v else uuid.uuid4().hex
            )
        return df_local
    else:
        return pd.DataFrame(columns=["id", "Task", "Subtask 1", "Subtask 2", "Due Date", "Done"])

def save_df(df_local, path=DATA_FILE):
    # Convert date objects to ISO strings for portability
    df_to_save = df_local.copy()
    df_to_save["Due Date"] = df_to_save["Due Date"].apply(lambda d: d.isoformat() if isinstance(d, date) else "")
    df_to_save.to_csv(path, index=False)

def set_done_from_checkbox(task_id):
    """Callback reads the checkbox state from st.session_state and persists it."""
    checkbox_key = f"check_{task_id}"
    new_value = st.session_state.get(checkbox_key, False)
    # Ensure session state df exists
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if mask.any():
        df.loc[mask, "Done"] = bool(new_value)
        save_df(df)
        st.experimental_rerun()

def delete_task(task_id=None, *args, **kwargs):
    # Be defensive: ensure session state df exists
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    if task_id is None:
        # Nothing to delete
        return
    df = st.session_state["df"]
    st.session_state["df"] = df[df["id"] != task_id].reset_index(drop=True)
    save_df(st.session_state["df"])
    st.experimental_rerun()

def save_edits(task_id, new_task, new_sub1, new_sub2, new_due):
    """Persist edits for a given task id."""
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        st.warning("Task not found (it may have been deleted).")
        return
    # Assign new values
    df.loc[mask, "Task"] = new_task
    df.loc[mask, "Subtask 1"] = new_sub1
    df.loc[mask, "Subtask 2"] = new_sub2
    # new_due is a date object from Streamlit; store as date
    df.loc[mask, "Due Date"] = pd.to_datetime(new_due).date() if new_due else ""
    st.session_state["df"] = df
    save_df(st.session_state["df"])
    st.success("Task updated.")
    st.experimental_rerun()

# Initialize session state
if "df" not in st.session_state:
    st.session_state["df"] = load_df()

df = st.session_state["df"]

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
    # Work on a copy for display
    display_df = st.session_state["df"].copy()
    # Ensure Due Date typed correctly for sorting
    display_df["Due Date"] = pd.to_datetime(display_df["Due Date"], errors="coerce").dt.date
    display_df = display_df.sort_values(by="Due Date", na_position="last")

    pending = display_df[display_df["Done"] == False]
    completed = display_df[display_df["Done"] == True]

    # Helper to render a single task (used for pending and completed)
    def render_task(row, show_delete=True, allow_edit=True):
        task_id = row["id"]
        col1, col2 = st.columns([0.08, 0.92])
        # Checkbox to complete (use id as key)
        col1.checkbox(
            "",
            value=bool(row["Done"]),
            key=f"check_{task_id}",
            on_change=set_done_from_checkbox,
            args=(task_id,)
        )
        with col2:
            due_display = row["Due Date"].isoformat() if isinstance(row["Due Date"], date) else ""
            st.markdown(f"**{row['Task']}** — :calendar: `{due_display}`")
            if row.get("Subtask 1") or row.get("Subtask 2"):
                with st.expander("View Details"):
                    if row.get("Subtask 1"):
                        st.write(f"• {row['Subtask 1']}")
                    if row.get("Subtask 2"):
                        st.write(f"• {row['Subtask 2']}")
            # Edit UI
            if allow_edit:
                with st.expander("✏️ Edit Task"):
                    # Use a form so inputs don't trigger multiple reruns
                    form_key = f"edit_form_{task_id}"
                    with st.form(form_key, clear_on_submit=False):
                        e_task = st.text_input("Task", value=row["Task"], key=f"edit_task_{task_id}")
                        e_sub1 = st.text_input("Sub-task 1", value=row.get("Subtask 1", ""), key=f"edit_sub1_{task_id}")
                        e_sub2 = st.text_input("Sub-task 2", value=row.get("Subtask 2", ""), key=f"edit_sub2_{task_id}")
                        # Ensure due initial value is a date object
                        initial_due = row["Due Date"] if isinstance(row["Due Date"], date) else date.today()
                        e_due = st.date_input("Due Date", value=initial_due, key=f"edit_due_{task_id}")
                        submitted = st.form_submit_button("Save Changes")
                        if submitted:
                            save_edits(task_id, e_task, e_sub1, e_sub2, e_due)
            # Delete button for completed tasks (or allow deletion for any)
            if show_delete:
                if st.button("Delete Forever", key=f"del_{task_id}"):
                    delete_task(task_id)

    st.subheader("📅 Upcoming")
    for _, row in pending.iterrows():
        render_task(row, show_delete=True, allow_edit=True)

    # --- COMPLETED SECTION ---
    if not completed.empty:
        st.write("---")
        with st.expander("✅ Completed Tasks"):
            for _, row in completed.iterrows():
                # Show completed tasks with strike-through title
                st.write(f"~~{row['Task']}~~")
                render_task(row, show_delete=True, allow_edit=True)
