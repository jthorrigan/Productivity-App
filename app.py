import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import os
import uuid
import json

# --- APP CONFIG & SETUP ---
st.set_page_config(page_title="VibeCheck Productivity", layout="centered")
DATA_FILE = "tasks.csv"

# --- Helpers ---
def load_df(path=DATA_FILE):
    """Load tasks.csv and normalize into a DataFrame with a 'Subtasks' column
    where each cell is a Python list of dicts: [{'id':..., 'text':..., 'done': bool}, ...].
    Backwards-compatibility: if 'Subtasks' column doesn't exist, build it from
    'Subtask 1'/'Subtask 2' columns (if present) or leave empty list.
    """
    if os.path.exists(path):
        df_local = pd.read_csv(path)
        expected = ["id", "Task", "Subtasks", "Due Date", "Done"]
        # Ensure legacy columns exist if present earlier
        # Normalize missing columns
        for col in expected:
            if col not in df_local.columns:
                # For Subtasks we will construct below
                if col == "Subtasks":
                    df_local[col] = ""
                else:
                    df_local[col] = ""
        # Parse Due Date into date objects
        try:
            df_local["Due Date"] = pd.to_datetime(df_local["Due Date"], errors="coerce").dt.date
        except Exception:
            df_local["Due Date"] = df_local["Due Date"].apply(lambda v: v if isinstance(v, date) else pd.NaT)
        # Done -> boolean
        try:
            df_local["Done"] = df_local["Done"].astype(bool)
        except Exception:
            df_local["Done"] = df_local["Done"].apply(lambda v: str(v).lower() in ("true", "1", "yes"))
        # Fill missing ids
        if "id" not in df_local.columns or df_local["id"].isnull().any():
            df_local["id"] = df_local.get("id", pd.Series([None]*len(df_local))).fillna("").apply(
                lambda v: v if v else uuid.uuid4().hex
            )
        # Build Subtasks column: parse JSON if present, else migrate legacy columns
        subtasks_list = []
        for idx, row in df_local.iterrows():
            subs_cell = row.get("Subtasks", "")
            subs = []
            if isinstance(subs_cell, str) and subs_cell.strip():
                # Stored as JSON string
                try:
                    parsed = json.loads(subs_cell)
                    # Ensure structure: list of dicts
                    if isinstance(parsed, list):
                        for s in parsed:
                            # normalize keys
                            sid = s.get("id") if isinstance(s, dict) and s.get("id") else uuid.uuid4().hex
                            text = s.get("text") if isinstance(s, dict) else str(s)
                            done = bool(s.get("done")) if isinstance(s, dict) and "done" in s else False
                            if text and str(text).strip():
                                subs.append({"id": sid, "text": str(text), "done": done})
                except Exception:
                    subs = []
            else:
                # Try legacy columns "Subtask 1"/"Subtask 2" (if present)
                legacy = []
                for colname in ["Subtask 1", "Subtask 2"]:
                    if colname in df_local.columns:
                        val = row.get(colname, "")
                        if pd.notna(val) and str(val).strip():
                            legacy.append(str(val).strip())
                for text in legacy:
                    subs.append({"id": uuid.uuid4().hex, "text": text, "done": False})
            subtasks_list.append(subs)
        # assign normalized Subtasks column
        df_local["Subtasks"] = subtasks_list
        return df_local
    else:
        # empty df with Subtasks as empty lists
        df = pd.DataFrame(columns=["id", "Task", "Subtasks", "Due Date", "Done"])
        return df


def save_df(df_local, path=DATA_FILE):
    """Serialize Subtasks as JSON strings and Due Date as ISO before saving CSV."""
    df_to_save = df_local.copy()
    # Ensure Subtasks are serialized
    def serialize_subs(cell):
        if isinstance(cell, list):
            # Only keep non-empty text subtasks
            cleaned = []
            for s in cell:
                text = s.get("text", "") if isinstance(s, dict) else str(s)
                if text and str(text).strip():
                    cleaned.append({"id": s.get("id", uuid.uuid4().hex), "text": text, "done": bool(s.get("done", False))})
            return json.dumps(cleaned, ensure_ascii=False)
        # If already string (older), keep as-is
        if pd.isna(cell):
            return ""
        if isinstance(cell, str):
            return cell
        return json.dumps(cell, ensure_ascii=False)

    df_to_save["Subtasks"] = df_to_save["Subtasks"].apply(serialize_subs)
    # Due Date to ISO strings
    df_to_save["Due Date"] = df_to_save["Due Date"].apply(lambda d: d.isoformat() if isinstance(d, date) else "")
    df_to_save.to_csv(path, index=False)


def safe_rerun():
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
        except Exception:
            return


def set_done_from_checkbox(task_id):
    """Update task-level Done from checkbox widget (keeps subtask state separate)."""
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
        safe_rerun()


def set_subtask_done(task_id, sub_id):
    """Callback to set subtask done state based on widget state."""
    key = f"sub_{task_id}_{sub_id}"
    new_value = st.session_state.get(key, False)
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        return
    subs = df.loc[mask, "Subtasks"].iat[0] or []
    changed = False
    for s in subs:
        if s.get("id") == sub_id:
            s["done"] = bool(new_value)
            changed = True
            break
    if changed:
        df.loc[mask, "Subtasks"] = subs
        st.session_state["df"] = df
        save_df(df)
        safe_rerun()


def add_subtask(task_id, text):
    """Add a new subtask to an existing task (immediate persist)."""
    text = (text or "").strip()
    if not text:
        return
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        return
    subs = df.loc[mask, "Subtasks"].iat[0] or []
    subs.append({"id": uuid.uuid4().hex, "text": text, "done": False})
    df.loc[mask, "Subtasks"] = subs
    st.session_state["df"] = df
    save_df(df)
    # clear any input field stored in session_state for this task
    input_key = f"new_sub_input_{task_id}"
    if input_key in st.session_state:
        st.session_state[input_key] = ""
    safe_rerun()


def delete_subtask(task_id, sub_id):
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        return
    subs = df.loc[mask, "Subtasks"].iat[0] or []
    new_subs = [s for s in subs if s.get("id") != sub_id]
    df.loc[mask, "Subtasks"] = new_subs
    st.session_state["df"] = df
    save_df(df)
    safe_rerun()


def save_edits(task_id, new_task, new_due):
    """Persist edits for title and due date (subtasks can be added/edited separately)."""
    if "df" not in st.session_state:
        st.session_state["df"] = load_df()
    df = st.session_state["df"]
    mask = df["id"] == task_id
    if not mask.any():
        st.warning("Task not found.")
        return
    df.loc[mask, "Task"] = new_task
    df.loc[mask, "Due Date"] = pd.to_datetime(new_due).date() if new_due else ""
    st.session_state["df"] = df
    save_df(df)
    if st.session_state.get("editing") == task_id:
        st.session_state.pop("editing", None)
    st.success("Task updated.")
    safe_rerun()


def snooze_task(task_id, days):
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
    today = date.today()
    if due_date is None or (isinstance(due_date, float) and pd.isna(due_date)) or due_date == "" or pd.isna(due_date):
        return "⚪", "no-date"
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
    # Creation UI uses a multiline text area for subtasks (one per line) — simple and flexible
    with st.form("task_form", clear_on_submit=True):
        task_name = st.text_input("What's the big goal?", key="new_task_name")
        subtasks_text = st.text_area("Sub-tasks (optional, one per line)", key="new_subtasks_area")
        due = st.date_input("Due Date", value=date.today(), key="new_due")
        if st.form_submit_button("Add to List"):
            if task_name:
                # Build subtasks list from lines
                subs = []
                lines = (subtasks_text or "").splitlines()
                for line in lines:
                    txt = line.strip()
                    if txt:
                        subs.append({"id": uuid.uuid4().hex, "text": txt, "done": False})
                new_row = {
                    "id": uuid.uuid4().hex,
                    "Task": task_name,
                    "Subtasks": subs,
                    "Due Date": due,
                    "Done": False,
                }
                st.session_state["df"] = pd.concat([st.session_state["df"], pd.DataFrame([new_row])], ignore_index=True)
                save_df(st.session_state["df"])
                st.success("Task added!")

    st.write("---")
    st.subheader("View")
    compact = st.checkbox("Compact view (tight rows)", value=st.session_state.get("compact_view", False), key="compact_view")
    st.caption("Snooze actions: +1d / +3d. Color: 🔴 overdue, 🟡 today, 🟢 upcoming, ⚪ no date")

# --- MAIN VIEW: ORGANIZED LIST ---
st.title("🚀 My Focus List")

df = st.session_state["df"]

if df.empty:
    st.info("Your list is empty. Add a task in the sidebar to get started!")
else:
    # Prepare DataFrame for display
    display_df = df.copy()
    display_df["Due Date"] = pd.to_datetime(display_df["Due Date"], errors="coerce").dt.date
    display_df["__sort_due"] = display_df["Due Date"].apply(lambda d: d if pd.notna(d) else date.max)
    display_df = display_df.sort_values(by=["__sort_due", "Task"], na_position="last")
    pending = display_df[display_df["Done"] == False].copy()
    completed = display_df[display_df["Done"] == True].copy()

    # header formatter
    def fmt_date_header(d):
        if pd.isna(d):
            return "No Due Date"
        if isinstance(d, date):
            return d.strftime("%A, %b %d, %Y")
        return str(d)

    # Render a task row including subtasks functionality
    def render_task_row(row):
        task_id = row["id"]
        compact_mode = st.session_state.get("compact_view", False)
        status_emoji, _ = status_indicator(row["Due Date"])
        subtasks = row.get("Subtasks") or []

        if compact_mode:
            cb_col, txt_col, actions_col = st.columns([0.05, 0.70, 0.25])
            cb_col.checkbox("", value=bool(row["Done"]), key=f"check_{task_id}", on_change=set_done_from_checkbox, args=(task_id,))
            with txt_col:
                due_display = row["Due Date"].isoformat() if isinstance(row["Due Date"], date) else ""
                st.markdown(f"{status_emoji} **{row['Task']}**  —  `{due_display}`")
                # show subtasks compactly
                if subtasks:
                    for s in subtasks:
                        sid = s.get("id")
                        text = s.get("text", "")
                        done = bool(s.get("done", False))
                        sub_key = f"sub_{task_id}_{sid}"
                        cols = st.columns([0.03, 0.90, 0.07])
                        cols[0].checkbox("", value=done, key=sub_key, on_change=set_subtask_done, args=(task_id, sid))
                        cols[1].markdown(f"{text}")
                        # delete subtask button
                        if cols[2].button("✖", key=f"del_sub_{task_id}_{sid}"):
                            delete_subtask(task_id, sid)
            with actions_col:
                if st.button("+1d", key=f"snooze1_{task_id}"):
                    snooze_task(task_id, 1)
                if st.button("+3d", key=f"snooze3_{task_id}"):
                    snooze_task(task_id, 3)
                if st.button("✏️", key=f"edit_{task_id}"):
                    st.session_state["editing"] = task_id
                    safe_rerun()
                if st.button("🗑️", key=f"del_{task_id}"):
                    delete_task(task_id)
            # add-subtask input (shown under row)
            if st.session_state.get("editing") == task_id:
                st.text_input("Add subtask", key=f"new_sub_input_{task_id}")
                if st.button("Add Subtask", key=f"add_sub_{task_id}"):
                    val = st.session_state.get(f"new_sub_input_{task_id}", "").strip()
                    if val:
                        add_subtask(task_id, val)
        else:
            cb_col, content_col, snooze_col, edit_col, del_col = st.columns([0.05, 0.64, 0.07, 0.06, 0.06])
            cb_col.checkbox("", value=bool(row["Done"]), key=f"check_{task_id}", on_change=set_done_from_checkbox, args=(task_id,))
            with content_col:
                due_display = row["Due Date"].isoformat() if isinstance(row["Due Date"], date) else ""
                st.markdown(f"{status_emoji} **{row['Task']}** — :calendar: `{due_display}`")
                # show subtasks with checkboxes and delete control
                if subtasks:
                    for s in subtasks:
                        sid = s.get("id")
                        text = s.get("text", "")
                        done = bool(s.get("done", False))
                        sub_key = f"sub_{task_id}_{sid}"
                        sub_c1, sub_c2, sub_c3 = st.columns([0.04, 0.86, 0.10])
                        sub_c1.checkbox("", value=done, key=sub_key, on_change=set_subtask_done, args=(task_id, sid))
                        with sub_c2:
                            st.write(text)
                        with sub_c3:
                            if st.button("✖", key=f"del_sub_{task_id}_{sid}"):
                                delete_subtask(task_id, sid)
                # Add new subtask input (immediate add)
                st.text_input("Add subtask", key=f"new_sub_input_{task_id}")
                if st.button("Add Subtask", key=f"add_sub_{task_id}"):
                    val = st.session_state.get(f"new_sub_input_{task_id}", "").strip()
                    if val:
                        add_subtask(task_id, val)

                # Inline edit panel for title/due when editing
                if st.session_state.get("editing") == task_id:
                    with st.form(f"edit_form_{task_id}", clear_on_submit=False):
                        e_task = st.text_input("Task", value=row["Task"], key=f"edit_task_{task_id}")
                        initial_due = row["Due Date"] if isinstance(row["Due Date"], date) else date.today()
                        e_due = st.date_input("Due Date", value=initial_due, key=f"edit_due_{task_id}")
                        cols = st.columns([1,1])
                        if cols[0].form_submit_button("Save"):
                            save_edits(task_id, e_task, e_due)
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
        grouped_keys = pending["Due Date"].fillna(pd.NaT).unique().tolist()
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
