import pandas as pd
import numpy as np
import streamlit as st
from streamlit_extras.let_it_rain import rain
from datetime import datetime as dt
from zoneinfo import ZoneInfo
import json
import base64
import io
import requests

st.set_page_config(page_title="Leaderboard", page_icon="🏆", layout="centered")
st.title("🏆 GNYC Membership Leaderboard")

months = ['January','February','March','April','May','June','July','August','September','October','November','December']
mon_dict   = dict(zip(range(1, 13), months))
month_idx  = {m: i for i, m in enumerate(months)}  # January→0, February→1 …

EXCLUDED_UNITS = {'Pack 0015 FP', 'Pack 0015', 'Pack 0015 BP'}

# ── GitHub config ─────────────────────────────────────────────────────────
GH_TOKEN  = st.secrets["GITHUB_TOKEN"]
GH_REPO   = st.secrets["GITHUB_REPO"]
GH_BRANCH = st.secrets["GITHUB_BRANCH"]
GH_API    = f"https://api.github.com/repos/{GH_REPO}/contents"
GH_HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

def gh_get(path: str) -> dict:
    r = requests.get(f"{GH_API}/{path}", headers=GH_HEADERS,
                     params={"ref": GH_BRANCH})
    r.raise_for_status()
    return r.json()

def gh_put(path: str, content_bytes: bytes, sha: str, message: str):
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch":  GH_BRANCH,
        "sha":     sha,
    }
    r = requests.put(f"{GH_API}/{path}", headers=GH_HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def write_csv_to_gh(path: str, sha: str, df: pd.DataFrame, message: str):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    gh_put(path, buf.getvalue(), sha, message)

def write_json_to_gh(path: str, sha: str, obj, message: str):
    gh_put(path, json.dumps(obj, indent=2).encode(), sha, message)

# ── Cached loader ─────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading data from GitHub...")
def load_all_data():
    def _read_csv(path):
        data = gh_get(path)
        return pd.read_csv(io.BytesIO(base64.b64decode(data["content"]))), data["sha"]

    def _read_json(path):
        try:
            data = gh_get(path)
            sha  = data["sha"]
            content = base64.b64decode(data["content"]).strip()
            if not content:
                return None, sha
            return json.loads(content), sha
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None, ""
            raise
        except (json.JSONDecodeError, ValueError):
            return None, gh_get(path)["sha"]

    df,     sha_df  = _read_csv("Monthly Membership by unit.csv")
    df_net, sha_net = _read_csv("Net change by month.csv")
    df_ny,  sha_ny  = _read_csv("New Youth.csv")
    log_data, sha_log = _read_json("upload_log.json")
    nu_data,  sha_nu  = _read_json("new_units.json")

    return (df, sha_df, df_net, sha_net, df_ny, sha_ny,
            log_data, sha_log, nu_data, sha_nu)

(df, sha_df, df_net, sha_net, df_ny, sha_ny,
 _log_data, sha_log, _nu_data, sha_nu) = load_all_data()

df_net = df_net.set_index('Unique')
month  = mon_dict[dt.today().month]

upload_log = _log_data if isinstance(_log_data, list) else []
sha_log    = sha_log or ""

# new_units.json is now a dict: { unique_key: start_month_name }
# Support legacy flat-list format by migrating on load
if isinstance(_nu_data, dict):
    _persisted_new_units = _nu_data           # {unique: start_month}
elif isinstance(_nu_data, list):
    _persisted_new_units = {u: None for u in _nu_data}  # migrate; start_month unknown
else:
    _persisted_new_units = {}
sha_nu = sha_nu or ""

if 'new_unit_uniques' not in st.session_state:
    st.session_state.new_unit_uniques = _persisted_new_units  # {unique: start_month}
elif isinstance(st.session_state.new_unit_uniques, set):
    # Migrate legacy set → dict
    st.session_state.new_unit_uniques = {u: None for u in st.session_state.new_unit_uniques}

if upload_log:
    _last = upload_log[-1]
    st.caption(f"Last updated: **{_last['timestamp']}** · {_last['month']}")

tab5, tab1, tab2, tab3, tab4 = st.tabs(['Monthly Leaderboard', 'Yearly Leaderboard', 'Yearly Tracker', 'New Youth Tracker', 'Upload'])

with tab4:
    if 'upload_auth' not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        pw = st.text_input("Enter password to access uploads", type="password")
        if pw == "bsa640gnyc":
            st.session_state.upload_auth = True
            st.rerun()
        elif pw:
            st.error("Incorrect password.")
    else:
        uploaded_file    = st.file_uploader("Upload Membership XLSX file", type=["xlsx"])
        uploaded_file_ny = st.file_uploader("Upload New Youth XLSX file", type=["xlsx"])

        if uploaded_file is not None and uploaded_file_ny is not None:

            full = pd.read_excel(uploaded_file, skiprows=2)
            raw_header  = pd.read_excel(uploaded_file).columns[0]
            month_token = raw_header.split('\n')[2].split(' ')[3]
            curr_mon    = dt.today().month
            month       = mon_dict[curr_mon] if month_token == 'Current' else month_token

            rename_membership = {
                'CouncilNumber Hierarchy - District':        'District',
                'CouncilNumber Hierarchy - SubDistrictName': 'Boro',
                'Current Month':                              month,
            }
            full = full.rename(rename_membership, axis=1)
            full = full[['Boro', 'District', 'Unit', 'Order', month]]
            full = full[~full['Boro'].isna()]
            full['Boro']   = full['Boro'].apply(lambda x: x.split(' (')[0].split(' 6')[0])
            full['Unique'] = full['Boro'] + full['District'] + full['Unit']

            # ── Detect new units ──────────────────────────────────────────────
            existing_uniques = set(df['Unique'])
            new_units        = full[~full['Unique'].isin(existing_uniques)]
            new_unit_count   = len(new_units)

            if not new_units.empty:
                for u in new_units['Unique'].tolist():
                    if u not in st.session_state.new_unit_uniques:
                        # Record unique → start month
                        st.session_state.new_unit_uniques[u] = month
                st.info(
                    f"🆕 {new_unit_count} new unit(s) detected — added to all datasets. "
                    f"They will appear in the monthly leaderboard starting next month."
                )
                new_df_rows = new_units[['Unique', 'Boro', 'District', 'Unit', 'Order']].copy()
                for m in months:
                    new_df_rows[m] = 0.0
                df = pd.concat([df, new_df_rows], ignore_index=True)

                new_net_rows = new_units[['Unique']].copy().set_index('Unique')
                for m in months:
                    new_net_rows[m] = 0.0
                df_net = pd.concat([df_net, new_net_rows])

            df[month] = df['Unique'].map(full.set_index('Unique')[month])
            df = df.fillna(0.0)

            newbies = pd.read_excel(uploaded_file_ny, skiprows=2)
            rename_ny = {
                'CouncilNumber Hierarchy - District':        'District',
                'CouncilNumber Hierarchy - SubDistrictName': 'Boro',
                'CouncilNumber Hierarchy - Unit':             'Unit',
            }
            newbies = newbies.rename(rename_ny, axis=1)
            newbies = newbies[['Boro', 'District', 'Unit', 'RegStatusxMonth', 'Month Year']]
            newbies = newbies[~newbies['Boro'].isna()]
            newbies['Boro']   = newbies['Boro'].apply(lambda x: x.split(' (')[0].split(' 6')[0])
            newbies['Unique'] = newbies['Boro'] + newbies['District'] + newbies['Unit']

            identity      = df[['Unique', 'Boro', 'District', 'Unit', 'Order']].set_index('Unique')
            df_ny         = df_ny.set_index('Unique') if 'Unique' in df_ny.columns else df_ny
            missing_in_ny = identity.index.difference(df_ny.index)
            if not missing_in_ny.empty:
                new_ny_rows = pd.DataFrame(0.0, index=missing_in_ny, columns=df_ny.columns)
                df_ny = pd.concat([df_ny, new_ny_rows])
            df_ny[['Boro', 'District', 'Unit', 'Order']] = identity
            df_ny = df_ny.fillna(0.0)

            for col in months:
                frame_ny = newbies[newbies['Month Year'] == col]
                for _, row in frame_ny.iterrows():
                    df_ny.loc[row.Unique, col] = row['RegStatusxMonth']

            for _, row in df.iterrows():
                curr = mon_dict[curr_mon]
                past = mon_dict[curr_mon - 1] if curr_mon != 1 else curr
                df_net.loc[row.Unique, curr] = row[curr] - row[past]

            ts         = dt.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M:%S EST')
            commit_msg = f"Data update: {month} ({ts})"

            with st.spinner("Saving to GitHub..."):
                write_csv_to_gh("Monthly Membership by unit.csv", sha_df,  df,                  commit_msg)
                write_csv_to_gh("Net change by month.csv",        sha_net, df_net.reset_index(), commit_msg)
                write_csv_to_gh("New Youth.csv",                  sha_ny,  df_ny.reset_index(),  commit_msg)
                write_json_to_gh("new_units.json", sha_nu,
                                 st.session_state.new_unit_uniques,
                                 f"Update new_units.json ({ts})")
                upload_log.append({
                    'timestamp':       ts,
                    'month':           month,
                    'membership_file': uploaded_file.name,
                    'new_youth_file':  uploaded_file_ny.name,
                    'total_units':     len(df),
                    'new_units_added': new_unit_count,
                })
                write_json_to_gh("upload_log.json", sha_log, upload_log,
                                 f"Update upload_log.json ({ts})")

            load_all_data.clear()
            st.success(f"✅ Data updated for **{month}** and committed to GitHub.")

        # ── Upload log + new unit log ─────────────────────────────────────────
        st.divider()
        st.subheader("Upload Log")
        if upload_log:
            log_df = pd.DataFrame(upload_log[::-1])
            log_df.columns = ['Timestamp', 'Month', 'Membership File', 'New Youth File', 'Total Units', 'New Units Added']
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No uploads recorded yet.")

        if st.session_state.new_unit_uniques:
            st.divider()
            st.subheader("New Unit Log")
            nu_rows = [
                {'Unique': u, 'Start Month': sm if sm else 'Unknown'}
                for u, sm in st.session_state.new_unit_uniques.items()
            ]
            st.dataframe(pd.DataFrame(nu_rows), use_container_width=True, hide_index=True)

# ── Derived display frame ─────────────────────────────────────────────────
df_ny_display  = df_ny.copy() if 'Unique' not in df_ny.columns else df_ny.set_index('Unique')
df_net_display = df_net.copy()

# new_unit_uniques: {unique: start_month}
nu_map = st.session_state.new_unit_uniques  # {unique: start_month_name | None}

# For yearly: zero out new-youth months on or before start month for new units
df_ny_adj = df_ny_display[months].copy()
for unique, start_month in nu_map.items():
    if unique in df_ny_adj.index and start_month in month_idx:
        start_i = month_idx[start_month]
        # Zero months up to and including start month
        zero_cols = months[:start_i + 1]
        df_ny_adj.loc[unique, zero_cols] = 0.0

df_ny_display['Total New Youth']         = df_ny_adj.sum(axis=1)
df_ny_display['Net Change from January'] = df_net_display[months].sum(axis=1)

# Current Size: use the most recently uploaded month that has any non-zero data
_month_totals = df[months].sum()
_populated    = _month_totals[_month_totals > 0]
_latest_month = _populated.index[-1] if not _populated.empty else month
df_ny_display['Current Size'] = df.set_index('Unique')[_latest_month]

# ── Troop net growth adjustment ───────────────────────────────────────────
is_troop     = df_ny_display['Order'] == '2 - Troops'
net_positive = df_ny_display['Net Change from January'] > 0
df_ny_display.loc[is_troop & net_positive, 'Net Change from January'] = \
    df_ny_display.loc[is_troop & net_positive, 'Total New Youth']

display = df_ny_display[
    ['District', 'Unit', 'Order', 'Total New Youth', 'Net Change from January', 'Current Size']
].reset_index()

# ── Exclusions ────────────────────────────────────────────────────────────
# Yearly: exclude all new units entirely
display = display[~display['Unique'].isin(nu_map.keys())]
display = display[~display['Unit'].isin(EXCLUDED_UNITS)]

# ── Sidebar controls ──────────────────────────────────────────────────────
col_sort = st.sidebar.selectbox(
    'Select Column to sort',
    ['Total New Youth', 'Net Change from January', 'Current Size']
)
order = st.sidebar.selectbox(
    'Choose Order',
    options=display['Order'].unique().tolist(),
    index=None
)
side_month = st.sidebar.selectbox(
    'Choose Month',
    options=months,
    index=dt.today().month - 1
)
side_month_idx = month_idx[side_month]

display['Percent New Youth'] = (
    display['Total New Youth'] / display['Current Size'].replace(0, np.nan) * 100
).round(2)

frame = display.sort_values('Percent New Youth', ascending=False)
if order is not None:
    frame = frame[frame['Order'] == order]
frame = frame.reset_index(drop=True)

# ── Monthly leaderboard: include new units only after their start month ───
ny_df = df_ny.reset_index() if 'Unique' not in df_ny.columns else df_ny.copy()
ny_df = ny_df[~ny_df['Unit'].isin(EXCLUDED_UNITS)]

# Filter new units: only show if side_month comes AFTER their start month
def _monthly_eligible(row):
    u = row['Unique']
    if u not in nu_map:
        return True  # established unit — always show
    start = nu_map[u]
    if start is None or start not in month_idx:
        return False  # unknown start — keep hidden
    return side_month_idx > month_idx[start]  # strictly after start month

ny_df = ny_df[ny_df.apply(_monthly_eligible, axis=1)]

if order is not None:
    ny_df = ny_df[ny_df['Order'] == order]
ny_df['Percent New Youth'] = round((ny_df[side_month] / ny_df['Current Size']) * 100, 2)
ny_df = ny_df.sort_values(by=[side_month, 'Percent New Youth'], ascending=False).reset_index(drop=True)

# ── Tab 2: Yearly Tracker ─────────────────────────────────────────────────
with tab2:
    st.dataframe(frame.drop(columns=['Unique'], errors='ignore'))

# ── Tab 1: Yearly Leaderboard ─────────────────────────────────────────────
with tab1:
    st.write(order, "|", col_sort)
    col1, col2, col3 = st.columns(3)

    lead = None
    for i, (col, medal) in enumerate(zip([col1, col2, col3], ["🥇", "🥈", "🥉"])):
        with col:
            if i < len(frame):
                if i == 0:
                    lead = frame['Unit'][i]
                st.write(frame['Unit'][i] + medal)
                st.write(frame['District'][i])
                st.metric(
                    label=f"{'1st' if i==0 else '2nd' if i==1 else '3rd'} Place",
                    value=frame[col_sort][i]
                )
            else:
                st.write("—")

    if st.button(label="Hooray!!", key="button1"):
        if lead:
            rain(emoji=f"🎉{lead}🎉", font_size=54, falling_speed=3, animation_length=1)

# ── Tab 3: New Youth Tracker (yearly, sorted by Percent New Youth) ────────
with tab3:
    yearly_cols = ['District', 'Unit', 'Order', 'Total New Youth',
                   'Percent New Youth', 'Net Change from January', 'Current Size']
    temp = frame[[c for c in yearly_cols if c in frame.columns]].copy()
    temp.index = range(1, len(temp) + 1)
    st.dataframe(temp, use_container_width=True)

# ── Tab 5: Monthly Leaderboard ────────────────────────────────────────────
with tab5:
    st.write(f"{side_month} New Youth" + (f" · {order}" if order else ""))
    col1, col2, col3 = st.columns(3)

    lead_monthly = None
    for i, (col, medal) in enumerate(zip([col1, col2, col3], ["🥇", "🥈", "🥉"])):
        with col:
            if i < len(ny_df):
                if i == 0:
                    lead_monthly = ny_df['Unit'].tolist()[i]
                st.write(ny_df['Unit'].tolist()[i] + medal)
                st.write(ny_df['District'].tolist()[i])
                st.metric(
                    label=f"{'1st' if i==0 else '2nd' if i==1 else '3rd'} Place",
                    value=ny_df[side_month].tolist()[i]
                )
            else:
                st.write("—")

    if st.button(label="Hooray!!", key="button2"):
        if lead_monthly:
            rain(emoji=f"🎉{lead_monthly}🎉", font_size=54, falling_speed=3, animation_length=1)