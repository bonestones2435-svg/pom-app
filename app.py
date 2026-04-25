import streamlit as st
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import folium
from folium.plugins import HeatMap
from streamlit.components.v1 import html
import base64

st.title("POM Heatmap Generator")

############################
# FILE UPLOAD
############################

csv_file = st.file_uploader("Upload CSV", type=["csv"])
kml_file = st.file_uploader("Upload KML", type=["kml"])

############################
# DATA INTEGRITY (ADDED - YOUR ORIGINAL LOGIC)
############################

def data_integrity(df):
    columns = [
        "Log Number","Ozone","Cell Temp","Cell Pressure","PDV",
        "BattV","Latitude","Longitude","Altitude","GPSquality"
    ]

    error_count = 0
    total = 0

    for col in columns:
        if col in df.columns:
            total += len(df[col])
            converted = pd.to_numeric(df[col], errors='coerce')
            error_count += ((converted.isnull()) & (df[col].notnull())).sum()

    if total == 0:
        return 0

    return round(100 * (1 - error_count / total), 2)

############################
# DOWNLOAD FUNCTION
############################

def download_button(file_path):
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
        href = f'<a href="data:file/html;base64,{b64}" download="ozone_map.html">📥 Download Map</a>'
        return href

############################
# MAIN
############################

if st.button("Generate"):

    if csv_file is None or kml_file is None:
        st.error("Upload both files")
        st.stop()

    ############################
    # READ CSV (UNCHANGED CORE)
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
    # DATA INTEGRITY SCORE (ADDED UI)
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
    # READ KML (UNCHANGED CORE)
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
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    coords.append((float(parts[0]), float(parts[1])))
        return coords

    for elem in root.iter():
        if "coord" in elem.tag.lower() or "coordinates" in elem.tag.lower():
            coords = parse_coord_text(elem.text)
            for lon_val, lat_val in coords:
                lon.append(lon_val)
                lat.append(lat_val)

    gps = pd.DataFrame({"lat": lat, "lon": lon})

    ############################
    # ALIGN (UNCHANGED CORE FIXED TO 1s)
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

    data = pd.concat([pom_resampled, gps_resampled], axis=1).dropna().reset_index()

    ############################
    # MAP (CLICKABLE TOOLTIP ADDED)
    ############################

    m = folium.Map(
        location=[data["lat"].mean(), data["lon"].mean()],
        zoom_start=14,
        tiles="CartoDB positron"
    )

    heat_data = []

    for _, row in data.iterrows():
        heat_data.append([row["lat"], row["lon"], row["ozone"]])

        # 🔥 CLICK POPUP ADDED (NEW FEATURE ONLY)
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=2,
            fill=True,
            fill_opacity=0.6,
            popup=f"Ozone: {row['ozone']}"
        ).add_to(m)

    HeatMap(heat_data, radius=2.5, blur=3).add_to(m)

    ############################
    # LEGEND (UNCHANGED)
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
    # SAVE + DISPLAY + DOWNLOAD
    ############################

    map_file = "ozone_map.html"
    m.save(map_file)

    html(m._repr_html_(), height=600)

    st.markdown(download_button(map_file), unsafe_allow_html=True)
