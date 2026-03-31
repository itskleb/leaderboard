import pandas as pd
import numpy as np
import streamlit as st
from streamlit_extras.let_it_rain import *
from datetime import datetime as dt
 
st.set_page_config(page_title="Leaderboard", page_icon="🏆", layout="centered")
st.title("🏆 GNYC Membership Leaderboard")
 
months = ['January','February','March','April','May','June','July','August','September','October','November','December']
mon_dict = dict(zip(range(1, 13), months))
 
df     = pd.read_csv('Monthly Membership by unit.csv')
df_net = pd.read_csv('Net change by month.csv').set_index('Unique')
df_ny  = pd.read_csv('New Youth.csv')
month  = mon_dict[dt.today().month]
 
if 'new_unit_uniques' not in st.session_state:
    st.session_state.new_unit_uniques = set()
 
tab1, tab2, tab3 = st.tabs(['Leaderboard', 'Full List', 'Upload'])
 
with tab3:
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
 
            # Parse month from header: "Month Year is Current Month" → word index 3
            raw_header = pd.read_excel(uploaded_file).columns[0]
            month_token = raw_header.split('\n')[2].split(' ')[3]
            curr_mon = dt.today().month
            month = mon_dict[curr_mon] if month_token == 'Current' else month_token
 
            # File 2 already has 'Order' and 'Unit' columns directly; only rename District/Boro
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
 
            # ── Detect new units not yet in stored CSVs ───────────────────────
            existing_uniques = set(df['Unique'])
            new_units = full[~full['Unique'].isin(existing_uniques)]
 
            if not new_units.empty:
                # Remember new unit keys so they stay off the leaderboard
                st.session_state.new_unit_uniques.update(new_units['Unique'].tolist())
                st.info(
                    f"🆕 {len(new_units)} new unit(s) detected — added to all three datasets "
                    f"and hidden from the leaderboard."
                )
 
                # Build skeleton rows for df (one row per new unit, all month cols = 0)
                new_df_rows = new_units[['Unique', 'Boro', 'District', 'Unit', 'Order']].copy()
                for m in months:
                    new_df_rows[m] = 0.0
                df = pd.concat([df, new_df_rows], ignore_index=True)
 
                # Build skeleton rows for df_net (same shape, all month cols = 0)
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
 
            # Rebuild df_ny indexed on Unique, adding skeleton rows for new units
            identity = df[['Unique', 'Boro', 'District', 'Unit', 'Order']].set_index('Unique')
            df_ny = df_ny.set_index('Unique') if 'Unique' in df_ny.columns else df_ny
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
 
            # ── Persist ──────────────────────────────────────────────────────
            df.to_csv('Monthly Membership by unit.csv', index=False)
            df_net.to_csv('Net change by month.csv')
            df_ny.to_csv('New Youth.csv')
 
            st.success(f"✅ Data updated for **{month}**. CSVs saved.")
 
# ── Derived display frame (always computed from current CSVs) ─────────────
df_ny_display  = df_ny.copy() if 'Unique' not in df_ny.columns else df_ny.set_index('Unique')
df_net_display = df_net.copy()
 
df_ny_display['Total New Youth']         = df_ny_display[months].sum(axis=1)
df_ny_display['Net Change from January'] = df_net_display[months].sum(axis=1)
df_ny_display['Current Size']            = df[month].values
 
# ── Troop net growth adjustment ───────────────────────────────────────────
# Troops gain members via crossover (Arrow of Light → Scout BSA) which inflates
# net membership without representing genuine new recruitment. So for Troops:
#   • Net > 0  → use Total New Youth (actual recruited scouts only)
#   • Net <= 0 → keep raw net (a real loss and should be shown as-is)
is_troop     = df_ny_display['Order'] == '2 - Troops'
net_positive = df_ny_display['Net Change from January'] > 0
df_ny_display.loc[is_troop & net_positive, 'Net Change from January'] = \
    df_ny_display.loc[is_troop & net_positive, 'Total New Youth']
 
display = df_ny_display[
    ['District', 'Unit', 'Order', 'Total New Youth', 'Net Change from January', 'Current Size']
].reset_index()
 
# ── Exclude brand-new units from leaderboard & full list ─────────────────
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
 
frame = display.sort_values(col_sort, ascending=False)
if order is not None:
    frame = frame[frame['Order'] == order]
frame = frame.reset_index(drop=True)
 
# ── Tab 2: Full list ──────────────────────────────────────────────────────
with tab2:
    st.dataframe(frame.drop(columns=['Unique'], errors='ignore'))
 
# ── Tab 1: Leaderboard ────────────────────────────────────────────────────
with tab1:
    st.write(order, "|", col_sort)
    col1, col2, col3 = st.columns(3)
 
    for i, (col, medal) in enumerate(zip([col1, col2, col3], ["🥇", "🥈", "🥉"])):
        with col:
            if i < len(frame):
                st.write(frame['Unit'][i] + medal)
                st.write(frame['District'][i])
                st.metric(
                    label=f"{'1st' if i==0 else '2nd' if i==1 else '3rd'} Place",
                    value=frame[col_sort][i]
                )
            else:
                st.write("—")
    butt=st.button(label="Hooray!!")
    if butt:
        #st.balloons()
        rain(emoji="🎉",
        font_size=54,
        falling_speed=5,
        animation_length=3)