import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
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
        # Ensure Done is boolean
        try:
            df_local["Done"] = df_local["Done"].astype(bool)
        except Exception:
            # Fallback if values are strings
            df_local["Done"] = df_local["Done"].apply(lambda v: str(v).lower() in ("true", "1", "yes"))
        # Fill missing ids for backwards compatibility
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


def safe_rerun():
    # Some Streamlit environments may not expose experimental_rerun; call defensively.
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
        except Exception:
            # Best-effort only; if it fails, don't crash the app.
            return


def set_done_from_checkbox(task_id):
    """Callback reads the checkbox state from st.session_state and persists it."""
    checkbox_key = f"check_{task_id}"
    new_value = st.session_state.get(checkbox_key, False)
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if mask.any():
        df.loc[mask, "Done"] = bool(new_value)
        st.session_state["df"] = df
        save_df(df)
        # No hard rerun — Streamlit will re-render after callback. Use safe_rerun only if needed.
        safe_rerun()


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
    safe_rerun()


def save_edits(task_id, new_task, new_sub1, new_sub2, new_due):
    """Persist edits for a given task id."""
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
    if st.session_state.get("editing") == task_id:
        st.session_state.pop("editing", None)
    st.success("Task updated.")
    safe_rerun()


def snooze_task(task_id, days):
    """Move a task forward by `days` days (create a due date if missing)."""
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        st.warning("Task not found.")
        return
    current = df.loc[mask, "Due Date"].iat[0]
    if isinstance(current, date):
        new_due = current + timedelta(days=days)
    else:
        new_due = date.today() + timedelta(days=days)
    df.loc[mask, "Due Date"] = new_due
    st.session_state["df"] = df
    save_df(df)
    safe_rerun()


def status_indicator(due_date):
    """Return emoji and optional class for coloring based on due_date vs today."""
    today = date.today()
    if due_date is None or (isinstance(due_date, float) and pd.isna(due_date)) or due_date == "" or pd.isna(due_date):
        return "⚪", "no-date"  # no due date
    if not isinstance(due_date, date):
        try:
            due_date = pd.to_datetime(due_date).date()
        except Exception:
            return "⚪", "no-date"
    if due_date < today:
        return "🔴", "overdue"
    if due_date == today:
        return "🟡", "today"
    return "🟢", "upcoming"


# Initialize session state
if "df" not in st.session_state:
    st.session_state["df"] = load_df()
if "editing" not in st.session_state:
    st.session_state["editing"] = None
if "compact_view" not in st.session_state:
    st.session_state["compact_view"] = False

# --- SIDEBAR: INPUT & OPTIONS ---
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

    st.write("---")
    st.subheader("View")
    # compact view toggle — DO NOT manually assign to session_state here
    compact = st.checkbox("Compact view (tight rows)", value=st.session_state.get("compact_view", False), key="compact_view")

    st.caption("Snooze actions: +1d / +3d. Color: 🔴 overdue, 🟡 today, 🟢 upcoming, ⚪ no date")

# --- MAIN VIEW: ORGANIZED LIST ---
st.title("🚀 My Focus List")

df = st.session_state["df"]

if df.empty:
    st.info("Your list is empty. Add a task in the sidebar to get started!")
else:
    # Prepare display dataframe
    display_df = df.copy()
    display_df["Due Date"] = pd.to_datetime(display_df["Due Date"], errors="coerce").dt.date
    # sort by Due Date then Task
    display_df["__sort_due"] = display_df["Due Date"].apply(lambda d: d if pd.notna(d) else date.max)
    display_df = display_df.sort_values(by=["__sort_due", "Task"], na_position="last")
    pending = display_df[display_df["Done"] == False].copy()
    completed = display_df[display_df["Done"] == True].copy()

    # small helper to format headers
    def fmt_date_header(d):
        if pd.isna(d):
            return "No Due Date"
        if isinstance(d, date):
            return d.strftime("%A, %b %d, %Y")
        return str(d)

    # render a single task row in compact or normal mode
    def render_task_row(row):
        task_id = row["id"]
        compact_mode = st.session_state.get("compact_view", False)

        # Determine status emoji
        status_emoji, _ = status_indicator(row["Due Date"])

        if compact_mode:
            # tighter layout: checkbox + task text + small action buttons inline
            cb_col, txt_col, actions_col = st.columns([0.05, 0.78, 0.17])
            cb_col.checkbox("", value=bool(row["Done"]), key=f"check_{task_id}", on_change=set_done_from_checkbox, args=(task_id,))
            with txt_col:
                due_display = row["Due Date"].isoformat() if isinstance(row["Due Date"], date) else ""
                st.markdown(f"{status_emoji} **{row['Task']}**  —  `{due_display}`", unsafe_allow_html=False)
            with actions_col:
                # inline small buttons: snooze +1, snooze +3, edit (opens inline), delete
                if st.button("+1d", key=f"snooze1_{task_id}"):
                    snooze_task(task_id, 1)
                if st.button("+3d", key=f"snooze3_{task_id}"):
                    snooze_task(task_id, 3)
                if st.button("✏️", key=f"edit_{task_id}"):
                    st.session_state["editing"] = task_id
                    safe_rerun()
                if st.button("🗑️", key=f"del_{task_id}"):
                    delete_task(task_id)
            # Inline editor in compact mode (shown under the row)
            if st.session_state.get("editing") == task_id:
                with st.form(f"compact_edit_{task_id}", clear_on_submit=False):
                    e_task = st.text_input("", value=row["Task"], key=f"c_edit_task_{task_id}")
                    e_sub1 = st.text_input("", value=row.get("Subtask 1", ""), key=f"c_edit_sub1_{task_id}")
                    e_sub2 = st.text_input("", value=row.get("Subtask 2", ""), key=f"c_edit_sub2_{task_id}")
                    initial_due = row["Due Date"] if isinstance(row["Due Date"], date) else date.today()
                    e_due = st.date_input("", value=initial_due, key=f"c_edit_due_{task_id}")
                    cols = st.columns([1,1,1])
                    if cols[0].form_submit_button("Save"):
                        save_edits(task_id, e_task, e_sub1, e_sub2, e_due)
                    if cols[1].form_submit_button("Cancel"):
                        st.session_state.pop("editing", None)
                        safe_rerun()
        else:
            # Normal layout: checkbox | main content (title + expanders) | snooze | edit | delete
            cb_col, content_col, snooze_col, edit_col, del_col = st.columns([0.05, 0.66, 0.07, 0.06, 0.06])
            cb_col.checkbox("", value=bool(row["Done"]), key=f"check_{task_id}", on_change=set_done_from_checkbox, args=(task_id,))
            with content_col:
                due_display = row["Due Date"].isoformat() if isinstance(row["Due Date"], date) else ""
                st.markdown(f"{status_emoji} **{row['Task']}** — :calendar: `{due_display}`")
                if row.get("Subtask 1") or row.get("Subtask 2"):
                    with st.expander("View Details"):
                        if row.get("Subtask 1"):
                            st.write(f"• {row['Subtask 1']}")
                        if row.get("Subtask 2"):
                            st.write(f"• {row['Subtask 2']}")
                # Inline edit panel (when editing)
                if st.session_state.get("editing") == task_id:
                    with st.form(f"edit_form_{task_id}", clear_on_submit=False):
                        e_task = st.text_input("Task", value=row["Task"], key=f"edit_task_{task_id}")
                        e_sub1 = st.text_input("Sub-task 1", value=row.get("Subtask 1", ""), key=f"edit_sub1_{task_id}")
                        e_sub2 = st.text_input("Sub-task 2", value=row.get("Subtask 2", ""), key=f"edit_sub2_{task_id}")
                        initial_due = row["Due Date"] if isinstance(row["Due Date"], date) else date.today()
                        e_due = st.date_input("Due Date", value=initial_due, key=f"edit_due_{task_id}")
                        cols = st.columns([1,1])
                        if cols[0].form_submit_button("Save"):
                            save_edits(task_id, e_task, e_sub1, e_sub2, e_due)
                        if cols[1].form_submit_button("Cancel"):
                            st.session_state.pop("editing", None)
                            safe_rerun()
            with snooze_col:
                if st.button("+1d", key=f"snooze1_{task_id}"):
                    snooze_task(task_id, 1)
                if st.button("+3d", key=f"snooze3_{task_id}"):
                    snooze_task(task_id, 3)
            with edit_col:
                if st.button("✏️", key=f"edit_{task_id}"):
                    st.session_state["editing"] = task_id
                    safe_rerun()
            with del_col:
                if st.button("🗑️", key=f"del_{task_id}"):
                    delete_task(task_id)

    # Group pending tasks by due date
    st.subheader("📅 Upcoming")
    if pending.empty:
        st.write("No upcoming tasks.")
    else:
        # Group by Due Date, NaT -> "No Due Date"
        # We'll keep date order (earliest first)
        grouped_keys = pending["Due Date"].fillna(pd.NaT).unique().tolist()
        # Create an ordering by actual date
        def key_sort(v):
            if pd.isna(v):
                return date.max
            if isinstance(v, date):
                return v
            try:
                return pd.to_datetime(v).date()
            except Exception:
                return date.max
        grouped_keys = sorted(grouped_keys, key=key_sort)
        for due_value in grouped_keys:
            header = fmt_date_header(due_value)
            st.markdown(f"### {header}")
            group = pending[pending["Due Date"].fillna(pd.NaT) == (due_value if not pd.isna(due_value) else pd.NaT)]
            for _, row in group.iterrows():
                render_task_row(row)

    # Completed tasks grouped smaller
    if not completed.empty:
        st.write("---")
        with st.expander("✅ Completed Tasks"):
            comp = completed.copy()
            comp = comp.sort_values(by="Due Date", na_position="last")
            grouped_keys = comp["Due Date"].fillna(pd.NaT).unique().tolist()
            grouped_keys = sorted(grouped_keys, key=key_sort)
            for due_value in grouped_keys:
                header = fmt_date_header(due_value)
                st.markdown(f"#### {header}")
                group = comp[comp["Due Date"].fillna(pd.NaT) == (due_value if not pd.isna(due_value) else pd.NaT)]
                for _, row in group.iterrows():
                    st.markdown(f"~~{row['Task']}~~")
                    render_task_row(row)
