import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
import folium
from folium.plugins import HeatMap
import streamlit as st
import base64

st.title("POM Heatmap Generator")

############################
# FILE UPLOAD
############################

csv_file = st.file_uploader("Upload CSV", type=["csv"])
kml_file = st.file_uploader("Upload KML", type=["kml"])

############################
# DATA INTEGRITY (ADDED ONLY)
############################

def data_integrity(df):
    cols = [
        "Log Number","Ozone","Cell Temp","Cell Pressure","PDV",
        "BattV","Latitude","Longitude","Altitude","GPSquality"
    ]

    errors = 0
    total = 0

    for col in cols:
        if col in df.columns:
            total += len(df[col])
            converted = pd.to_numeric(df[col], errors="coerce")
            errors += ((converted.isnull()) & (df[col].notnull())).sum()

    if total == 0:
        return 0

    return round(100 * (1 - errors / total), 2)

############################
# DOWNLOAD FUNCTION
############################

def get_download_link(file_path):
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'<a href="data:file/html;base64,{b64}" download="ozone_map.html">📥 Download Map</a>'

############################
# RUN ONLY IF FILES UPLOADED
############################

if st.button("Generate"):

    if csv_file is None or kml_file is None:
        st.error("Upload both files")
        st.stop()

    ############################
    # READ POM CSV (UNCHANGED CORE)
    ############################

    df = pd.read_csv(csv_file, skiprows=5, header=None)

    ozone = pd.to_numeric(df.iloc[:,1], errors="coerce")
    time_utc = pd.to_datetime(df.iloc[:,11], format="%H:%M:%S", errors="coerce")

    pom = pd.DataFrame({
        "time": time_utc,
        "ozone": ozone
    }).dropna()

    st.write("Loaded ozone points:", len(pom))

    ############################
    # DATA INTEGRITY DISPLAY (ADDED)
    ############################

    df.columns = [
        "Log Number","Ozone","Cell Temp","Cell Pressure","PDV",
        "BattV","Latitude","Longitude","Altitude","GPSquality",
        "Date","Time"
    ]

    score = data_integrity(df)

    st.subheader(f"Data Integrity Score: {score}%")
    st.progress(score / 100)

    ############################
    # READ KML GPS DATA (UNCHANGED CORE)
    ############################

    tree = ET.parse(kml_file)
    root = tree.getroot()

    lat = []
    lon = []

    def parse_coord_text(text):
        coords = []
        if text:
            lines = text.strip().split()
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 2 or len(parts) == 3:
                    coords.append((float(parts[0]), float(parts[1])))
                else:
                    parts = line.strip().split(",")
                    if len(parts) >= 2:
                        coords.append((float(parts[0]), float(parts[1])))
        return coords

    for elem in root.iter():
        tag_lower = elem.tag.lower()
        if "coord" in tag_lower or "coordinates" in tag_lower:
            coords = parse_coord_text(elem.text)
            for lon_val, lat_val in coords:
                lon.append(lon_val)
                lat.append(lat_val)

    gps = pd.DataFrame({
        "lat": lat,
        "lon": lon
    })

    print("Loaded GPS points:", len(lat))

    ############################
    # ALIGN (UNCHANGED CORE)
    ############################

    gps["time"] = pd.date_range(
        start=pom["time"].min(),
        end=pom["time"].max(),
        periods=len(gps)
    )

    pom = pom.set_index("time")
    gps = gps.set_index("time")

    pom_resampled = pom.resample("1s").mean()
    gps_resampled = gps.resample("1s").mean()

    pom_resampled["ozone"] = pom_resampled["ozone"].interpolate()
    gps_resampled["lat"] = gps_resampled["lat"].interpolate()
    gps_resampled["lon"] = gps_resampled["lon"].interpolate()

    data = pd.concat([pom_resampled, gps_resampled], axis=1).dropna()
    data = data.reset_index()

    print("Aligned data points:", len(data))

    ############################
    # CREATE MAP (UNCHANGED CORE)
    ############################

    center_lat = data["lat"].mean()
    center_lon = data["lon"].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="CartoDB positron"
    )

    heat_data = [
        [row["lat"], row["lon"], row["ozone"]]
        for _, row in data.iterrows()
    ]

    HeatMap(
        heat_data,
        radius=2.5,
        blur=3,
        max_zoom=24
    ).add_to(m)

    ############################
    # LEGEND (UNCHANGED EXACTLY)
    ############################

    legend_html = '''
    <div style="
    position: fixed;
    bottom: 50px;
    left: 50px;
    width: 320px;
    background-color: white;
    border:2px solid grey;
    z-index:9999;
    font-size:14px;
    padding: 10px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
    ">
    <b>Ozone Concentration (ppb)</b>
    </div>
    '''

    m.get_root().html.add_child(folium.Element(legend_html))

    ############################
    # SAVE + DOWNLOAD + SAFE DISPLAY FIX
    ############################

    map_file = "ozone_map.html"
    m.save(map_file)

    st.success("Map generated successfully!")

    st.markdown(get_download_link(map_file), unsafe_allow_html=True)

    # FIXED RENDERING (THIS IS THE ONLY REAL FIX)
    with open(map_file, "r", encoding="utf-8") as f:
        map_html = f.read()

    st.components.v1.html(map_html, height=600)
