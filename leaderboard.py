import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime as dt

st.set_page_config(page_title="Leaderboard", page_icon="🏆", layout="centered")

st.title("🏆 Leaderboard")

uploaded_file = st.file_uploader("Upload Memebrship XLSX file", type=["xlsx"])
uploaded_file_ny = st.file_uploader("Upload New Youth XLSX file", type=["xlsx"])


months = ['January','February','March','April','May','June','July','August','September','October','November','December']
mon_dict = dict(zip([i for i in range(1,13)],months))

if uploaded_file == None:
        df = pd.read_csv('Monthly Membership by unit.csv')
        #df = df.drop('Unnamed: 0')
        df_net = pd.read_csv('Net change by month.csv')
        df_net = df_net.set_index('Unique')
        df_ny = pd.read_csv('New Youth.csv')
        month = mon_dict[dt.today().month]


if uploaded_file != None:
    full = pd.read_excel(uploaded_file,skiprows=2)
    month = pd.read_excel(uploaded_file).columns[0].split('\n')[2].split(' ')[3]
    curr_mon = dt.today().month

    if month == 'Current':
        month = mon_dict[curr_mon]
    
    re_name = {"CouncilNumber Hierarchy - District":'District',	
            'CouncilNumber Hierarchy - SubDistrictName':'Boro', 
            'Current Month':month,
            'CouncilNumber Hierarchy - Unit':'Unit'}

    full = full.rename(re_name,axis=1)
    full = full[['Boro','District','Unit','Order',month]]
    full= full[~full['Boro'].isna()]
    full['Boro'] = full['Boro'].apply(lambda x: x.split(' (')[0].split(' 6')[0])
    full['Unique'] = full['Boro']+full['District']+full['Unit']

    if len(df) == 0:
        df = pd.concat([df,full],axis = 0)
        df_net = pd.concat([df_net,df[['Unique','Boro','District','Unit','Order']]],axis = 0)
        df_net = df_net.set_index('Unique')
    else:
        df[month] = df['Unique'].map(full.set_index('Unique')[month])
        df = df.fillna(0.0)

    newbies = pd.read_excel(uploaded_file_ny,skiprows=2)
    newbies = newbies.rename(re_name,axis=1)
    newbies = newbies[['Boro','District','Unit','RegStatusxMonth','Month Year']]
    newbies= newbies[~newbies['Boro'].isna()]
    newbies['Boro'] = newbies['Boro'].apply(lambda x: x.split(' (')[0].split(' 6')[0])
    newbies['Unique'] = newbies['Boro']+newbies['District']+newbies['Unit']

    df_ny['Unique'] = df['Unique']
    df_ny['Boro'] = df['Boro']
    df_ny['District'] = df['District']
    df_ny['Order'] = df['Order']
    df_ny['Unit']= df['Unit']
    df_ny = df_ny.set_index('Unique').fillna(0.0)

    for col in months:
        frame = newbies[newbies['Month Year']==col]
        for _,row in frame.iterrows():
            df_ny.loc[row.Unique,col] = row['RegStatusxMonth']
            

    #curr_mon=2
    for _,row in df.iterrows():
        curr = mon_dict[curr_mon]
        if curr_mon != 1:
            past = mon_dict[curr_mon-1]
        else:
            past = curr
        net = row[curr] - row[past]
        r=row.Unique
        c=curr
        df_net.loc[r,c] = net
    
df_ny['Total New Youth'] = df_ny[months].sum(axis=1)
df_ny = df_ny.reset_index()
df_net = df_net.reset_index()
df_ny['Net Change from January'] = df_net[months].sum(axis=1)
df_ny['Current Size'] = df[month]

display = df_ny[['District', 'Unit','Order','Total New Youth','Net Change from January','Current Size']].reset_index()#.drop('Unique',axis=1)

df.to_csv('Monthly Membership by unit.csv')
df_net.to_csv('Net change by month.csv')
df_ny.to_csv('New Youth.csv')

tab1, tab2, tab3 = st.tabs(['Leaderboard','Full List','Upload'])
#st.write("Leaders")
col_sort = st.sidebar.selectbox(label = 'Select Column to sort', options = ['Total New Youth','Net Change from January','Current Size'])
with tab2:
    st.dataframe(display.sort_values(col_sort,ascending=False))
    #st.dataframe(df_ny)

with tab1:
    col1, col2, col3 = st.columns(3)
    frame = display.sort_values(col_sort,ascending=False).reset_index()
    st.write(col_sort)
    with col1:
        st.write(frame['Unit'][0])
        st.write(frame['District'][0])
        st.metric(label = '1st Place', value = frame[col_sort][0])
    with col2:
        st.write(frame['Unit'][1])
        st.write(frame['District'][1])
        st.metric(label = '2nd Place', value = frame[col_sort][1])
    with col3:
        st.write(frame['Unit'][2])
        st.write(frame['District'][2])
        st.metric(label = '3rd Place', value = frame[col_sort][2])

with tab3:
    pass