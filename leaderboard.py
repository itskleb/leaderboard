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
mon_dict = dict(zip(range(1, 13), months))

# ── GitHub helpers ────────────────────────────────────────────────────────
GH_TOKEN  = st.secrets["GITHUB_TOKEN"]
GH_REPO   = st.secrets["GITHUB_REPO"]    # "owner/repo"
GH_BRANCH = st.secrets["GITHUB_BRANCH"]  # "main"
GH_API    = f"https://api.github.com/repos/{GH_REPO}/contents"
GH_HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

def gh_get(path: str) -> dict:
    """Fetch a file's metadata + content from GitHub."""
    r = requests.get(f"{GH_API}/{path}", headers=GH_HEADERS,
                     params={"ref": GH_BRANCH})
    r.raise_for_status()
    return r.json()

def gh_put(path: str, content_bytes: bytes, sha: str, message: str):
    """Create or update a file on GitHub."""
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch":  GH_BRANCH,
        "sha":     sha,
    }
    r = requests.put(f"{GH_API}/{path}", headers=GH_HEADERS,
                     json=payload)
    r.raise_for_status()
    return r.json()

def read_csv_from_gh(path: str) -> tuple[pd.DataFrame, str]:
    """Return (DataFrame, sha) for a CSV stored on GitHub."""
    data = gh_get(path)
    content = base64.b64decode(data["content"])
    return pd.read_csv(io.BytesIO(content)), data["sha"]

def write_csv_to_gh(path: str, sha: str, df: pd.DataFrame, message: str):
    """Commit a DataFrame as a CSV back to GitHub."""
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    gh_put(path, buf.getvalue(), sha, message)

def read_json_from_gh(path: str) -> tuple[list | dict, str]:
    """Return (parsed object, sha). Returns (None, sha) if file missing or empty."""
    try:
        data = gh_get(path)
        sha = data["sha"]
        content = base64.b64decode(data["content"]).strip()
        if not content:
            return None, sha
        return json.loads(content), sha
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None, ""
        raise
    except (json.JSONDecodeError, ValueError):
        # Malformed file — fetch sha so we can overwrite it cleanly
        sha = gh_get(path)["sha"]
        return None, sha

def write_json_to_gh(path: str, sha: str, obj, message: str):
    """Commit a JSON-serialisable object back to GitHub."""
    content_bytes = json.dumps(obj, indent=2).encode()
    gh_put(path, content_bytes, sha, message)

# ── Load CSVs from GitHub ─────────────────────────────────────────────────
df,     sha_df     = read_csv_from_gh("Monthly Membership by unit.csv")
df_net, sha_net    = read_csv_from_gh("Net change by month.csv")
df_ny,  sha_ny     = read_csv_from_gh("New Youth.csv")
df_net = df_net.set_index('Unique')
month  = mon_dict[dt.today().month]

# ── Load log + new-unit list from GitHub ─────────────────────────────────
_log_data, sha_log       = read_json_from_gh("upload_log.json")
upload_log: list         = _log_data if isinstance(_log_data, list) else []
sha_log                  = sha_log or ""

_nu_data, sha_nu         = read_json_from_gh("new_units.json")
_persisted_new_units     = set(_nu_data) if isinstance(_nu_data, list) else set()
sha_nu                   = sha_nu or ""

if 'new_unit_uniques' not in st.session_state:
    st.session_state.new_unit_uniques = _persisted_new_units

# ── Last upload note ──────────────────────────────────────────────────────
if upload_log:
    _last = upload_log[-1]
    st.markdown(
        f'<div style="background:#f0f4ff;border:1px solid #c0cfe8;border-radius:10px;'
        f'padding:10px 18px;margin-bottom:16px;display:inline-block">'
        f'<span style="font-size:13px;color:#555;font-weight:500">LAST UPLOAD</span><br>'
        f'<span style="font-size:20px;font-weight:700;color:#1a2e5a">{_last["timestamp"]}</span>'
        f'&nbsp;&nbsp;<span style="color:#555;font-size:14px">({_last["month"]})</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

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

            # ── Membership file ───────────────────────────────────────────────
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
                added = [u for u in new_units['Unique'].tolist()
                         if u not in st.session_state.new_unit_uniques]
                st.session_state.new_unit_uniques.update(added)
                st.info(
                    f"🆕 {new_unit_count} new unit(s) detected — added to all three datasets "
                    f"and hidden from the leaderboard."
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

            # ── New Youth file ────────────────────────────────────────────────
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

            # ── Net change ───────────────────────────────────────────────────
            for _, row in df.iterrows():
                curr = mon_dict[curr_mon]
                past = mon_dict[curr_mon - 1] if curr_mon != 1 else curr
                df_net.loc[row.Unique, curr] = row[curr] - row[past]

            # ── Commit everything to GitHub ───────────────────────────────────
            ts = dt.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M:%S EST')
            commit_msg = f"Data update: {month} ({ts})"

            with st.spinner("Saving to GitHub..."):
                write_csv_to_gh("Monthly Membership by unit.csv", sha_df,  df,                 commit_msg)
                write_csv_to_gh("Net change by month.csv",        sha_net, df_net.reset_index(), commit_msg)
                write_csv_to_gh("New Youth.csv",                  sha_ny,  df_ny.reset_index(), commit_msg)

                # Update new_units.json
                write_json_to_gh(
                    "new_units.json", sha_nu,
                    sorted(st.session_state.new_unit_uniques),
                    f"Update new_units.json ({ts})"
                )

                # Append to upload log
                upload_log.append({
                    'timestamp':       ts,
                    'month':           month,
                    'membership_file': uploaded_file.name,
                    'new_youth_file':  uploaded_file_ny.name,
                    'total_units':     len(df),
                    'new_units_added': new_unit_count,
                })
                write_json_to_gh(
                    "upload_log.json", sha_log,
                    upload_log,
                    f"Update upload_log.json ({ts})"
                )

            st.success(f"✅ Data updated for **{month}** and committed to GitHub.")

        # ── Upload log display ────────────────────────────────────────────────
        st.divider()
        st.subheader("Upload Log")
        if upload_log:
            log_df = pd.DataFrame(upload_log[::-1])
            log_df.columns = ['Timestamp', 'Month', 'Membership File', 'New Youth File', 'Total Units', 'New Units Added']
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No uploads recorded yet.")

# ── Derived display frame ─────────────────────────────────────────────────
df_ny_display  = df_ny.copy() if 'Unique' not in df_ny.columns else df_ny.set_index('Unique')
df_net_display = df_net.copy()

df_ny_display['Total New Youth']         = df_ny_display[months].sum(axis=1)
df_ny_display['Net Change from January'] = df_net_display[months].sum(axis=1)
df_ny_display['Current Size']            = df[month].values

# ── Troop net growth adjustment ───────────────────────────────────────────
is_troop     = df_ny_display['Order'] == '2 - Troops'
net_positive = df_ny_display['Net Change from January'] > 0
df_ny_display.loc[is_troop & net_positive, 'Net Change from January'] = \
    df_ny_display.loc[is_troop & net_positive, 'Total New Youth']

display = df_ny_display[
    ['District', 'Unit', 'Order', 'Total New Youth', 'Net Change from January', 'Current Size']
].reset_index()

# ── Exclude brand-new units ───────────────────────────────────────────────
if st.session_state.new_unit_uniques:
    display = display[~display['Unique'].isin(st.session_state.new_unit_uniques)]

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

frame = display.sort_values(col_sort, ascending=False)
if order is not None:
    frame = frame[frame['Order'] == order]
frame = frame.reset_index(drop=True)

ny_df = df_ny.copy() if 'Unique' not in df_ny.columns else df_ny.reset_index()
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

# ── Tab 3: New Youth Tracker ──────────────────────────────────────────────
with tab3:
    temp = ny_df.copy()
    temp.index = range(1, len(ny_df) + 1)
    st.dataframe(temp.drop('Unique', axis=1, errors='ignore'))

# ── Tab 5: Monthly Leaderboard ────────────────────────────────────────────
with tab5:
    st.write(f"{side_month} New Youth")
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