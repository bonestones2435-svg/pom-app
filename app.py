import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import folium
from folium.plugins import HeatMap
import branca.colormap as cm
import streamlit as st
import base64

############################
# PAGE CONFIG
############################

st.set_page_config(page_title="Air Quality Heatmap", layout="wide")
st.title("🌬️ Air Quality Heatmap Generator")

############################
# SELECTORS
############################

col1, col2 = st.columns(2)

with col1:
    device = st.selectbox("Select Device", ["POM", "POPS"])

with col2:
    time_of_day = st.selectbox("Time of Day", ["Morning", "Midday", "Evening"])

st.markdown("---")

############################
# DOWNLOAD HELPER
############################

def get_download_link(file_path, label, filename):
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'<a href="data:file/html;base64,{b64}" download="{filename}">{label}</a>'

############################
# DATA INTEGRITY
############################

def data_integrity(df, cols):
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
# GPX PARSER (for POM)
############################

def parse_gpx(gpx_file):
    """Parse a GPX file and return a DataFrame with time, lat, lon."""
    tree = ET.parse(gpx_file)
    root = tree.getroot()

    # GPX namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    records = []
    for trkpt in root.iter(f"{ns}trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        time_elem = trkpt.find(f"{ns}time")
        if time_elem is not None:
            ts = pd.to_datetime(time_elem.text, utc=True).tz_localize(None)
            records.append({"time": ts, "lat": lat, "lon": lon})

    gps_df = pd.DataFrame(records).sort_values("time").reset_index(drop=True)
    return gps_df

############################
# POM PIPELINE
############################

def run_pom(csv_file, gpx_file, time_of_day):
    st.subheader(f"POM — {time_of_day}")

    # --- Read CSV ---
    df_raw = pd.read_csv(csv_file, skiprows=5, header=None)

    ozone = pd.to_numeric(df_raw.iloc[:, 1], errors="coerce")
    time_utc = pd.to_datetime(df_raw.iloc[:, 11], format="%H:%M:%S", errors="coerce")

    pom = pd.DataFrame({
        "time": time_utc,
        "ozone": ozone
    }).dropna()

    st.write(f"Loaded ozone points: **{len(pom)}**")

    # --- Data integrity ---
    df_raw.columns = [
        "Log Number", "Ozone", "Cell Temp", "Cell Pressure", "PDV",
        "BattV", "Latitude", "Longitude", "Altitude", "GPSquality",
        "Date", "Time"
    ]
    score = data_integrity(df_raw, [
        "Log Number", "Ozone", "Cell Temp", "Cell Pressure", "PDV",
        "BattV", "Latitude", "Longitude", "Altitude", "GPSquality"
    ])
    st.subheader(f"Data Integrity Score: {score}%")
    st.progress(score / 100)

    # --- Parse GPX with real timestamps ---
    gps = parse_gpx(gpx_file)
    st.write(f"Loaded GPS points: **{len(gps)}**")

    if gps.empty:
        st.error("No GPS points found in GPX file. Check that your file has <trkpt> elements with <time> tags.")
        st.stop()

    # --- Align using real timestamps ---
    pom = pom.set_index("time")
    gps = gps.set_index("time")

    pom_resampled = pom.resample("1s").mean()
    gps_resampled = gps.resample("1s").mean()

    pom_resampled["ozone"] = pom_resampled["ozone"].interpolate()
    gps_resampled["lat"] = gps_resampled["lat"].interpolate()
    gps_resampled["lon"] = gps_resampled["lon"].interpolate()

    data = pd.concat([pom_resampled, gps_resampled], axis=1).dropna().reset_index()

    st.write(f"Aligned data points: **{len(data)}**")

    if data.empty:
        st.error("No overlapping timestamps between ozone and GPS data. Check that both files cover the same time window.")
        st.stop()

    # --- Build map ---
    m = folium.Map(
        location=[data["lat"].mean(), data["lon"].mean()],
        zoom_start=14,
        tiles="CartoDB positron"
    )

    heat_data = [[row["lat"], row["lon"], row["ozone"]] for _, row in data.iterrows()]

    HeatMap(heat_data, radius=2.5, blur=3, max_zoom=24).add_to(m)

    # Legend
    legend_html = '''
    <div style="
    position: fixed; bottom: 50px; left: 50px; width: 320px;
    background-color: white; border:2px solid grey; z-index:9999;
    font-size:14px; padding: 10px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);">
    <b>Ozone Concentration (ppb)</b><br>
    <span style="font-size:11px;">(EPA 8-hour categories)</span><br><br>
    <div style="width:100%; height:18px;
    background: linear-gradient(to right, blue 0%, cyan 27%, yellow 42%, orange 52%, red 65%, purple 100%);
    border:1px solid black; margin-bottom:5px;"></div>
    <div style="width:100%; display:grid; grid-template-columns:repeat(6,1fr);
    font-size:11px; text-align:center;">
    <span>0</span><span>54</span><span>70</span><span>85</span><span>105</span><span>200+</span>
    </div>
    <div style="font-size:11px; text-align:center; margin-top:6px;">
    Good → Moderate → USG → Unhealthy → Very Unhealthy → Hazardous
    </div></div>'''

    m.get_root().html.add_child(folium.Element(legend_html))

    map_file = "pom_ozone_map.html"
    m.save(map_file)

    st.success("POM map generated!")
    st.markdown(get_download_link(map_file, "📥 Download Ozone Map", "pom_ozone_map.html"), unsafe_allow_html=True)

    with open(map_file, "r", encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=600)

############################
# KML PARSER (for POPS)
############################

def parse_kml_track(kml_file):
    """Parse GPS track from KML gx:Track and return DataFrame."""
    tree = ET.parse(kml_file)
    root = tree.getroot()
    ns = {
        "kml": "http://www.opengis.net/kml/2.2",
        "gx": "http://www.google.com/kml/ext/2.2"
    }

    track = root.find(".//gx:Track", ns)
    if track is None:
        raise ValueError("No gx:Track found in KML file.")

    gps_data = []
    when_elements = track.findall("kml:when", ns)
    coord_elements = track.findall("gx:coord", ns)

    for when, coord in zip(when_elements, coord_elements):
        ts = pd.to_datetime(when.text)
        if ts.tzinfo is None:
            ts = ts.tz_localize("US/Eastern").tz_convert("UTC").tz_localize(None)
        else:
            ts = ts.tz_convert("UTC").tz_localize(None)
        lon, lat, alt = map(float, coord.text.strip().split())
        gps_data.append({"time": ts, "latitude": lat, "longitude": lon, "altitude": alt})

    gps_df = pd.DataFrame(gps_data).sort_values("time").reset_index(drop=True)
    return gps_df

############################
# POPS PM2.5 CALCULATION
############################

def calculate_pm2_5(row):
    bin_cols = [f"b{i}" for i in range(16)]
    SD = row[bin_cols].values
    PF = row[" POPS_Flow"]
    if PF == 0 or np.isnan(PF):
        return np.nan
    Dp = np.array([0.14, 0.17, 0.205, 0.249, 0.302, 0.366, 0.443, 0.537,
                   0.651, 0.789, 0.956, 1.159, 1.404, 1.702, 2.062, 2.500])
    volume_term = (4 / 3) * np.pi * (Dp / 2) ** 3
    pm = 2 * np.sum(volume_term * SD / PF)
    return pm

############################
# POPS ALIGNMENT
############################

def prepare_heatmap_data(pops_df, gps_df, start_utc, end_utc, value_col):
    pops_walk = pops_df[
        (pops_df["DateTime_utc"] >= start_utc) &
        (pops_df["DateTime_utc"] <= end_utc)
    ].copy()

    gps_walk = gps_df[
        (gps_df["time"] >= start_utc) &
        (gps_df["time"] <= end_utc)
    ].copy()

    pops_walk = pops_walk.set_index("DateTime_utc")
    gps_walk = gps_walk.set_index("time")

    pops_resampled = pops_walk[[value_col]].resample("1s").mean()
    gps_resampled = gps_walk[["latitude", "longitude"]].resample("1s").mean()

    pops_resampled[value_col] = pops_resampled[value_col].interpolate()
    gps_resampled["latitude"] = gps_resampled["latitude"].interpolate()
    gps_resampled["longitude"] = gps_resampled["longitude"].interpolate()

    data = pd.concat([pops_resampled, gps_resampled], axis=1).dropna().reset_index()
    return data

############################
# POPS MAP BUILDER
############################

def plot_pops_map(data, value_col, filename, caption_text, vmin, vmax):
    m = folium.Map(
        location=[data["latitude"].mean(), data["longitude"].mean()],
        zoom_start=14,
        tiles="CartoDB positron"
    )

    heat_data = [[row["latitude"], row["longitude"], row[value_col]] for _, row in data.iterrows()]
    HeatMap(heat_data, radius=3, blur=3, max_zoom=18).add_to(m)

    colormap = cm.LinearColormap(
        colors=["blue", "cyan", "yellow", "orange", "red"],
        vmin=vmin, vmax=vmax,
        caption=caption_text
    )
    colormap.add_to(m)
    m.save(filename)
    return m

############################
# POPS PIPELINE
############################

def run_pops(csv_file, kml_file, walk_start_est, walk_end_est, time_of_day):
    st.subheader(f"POPS — {time_of_day}")

    # --- Convert times to UTC ---
    walk_start_utc = walk_start_est.tz_localize("US/Eastern").tz_convert("UTC").tz_localize(None)
    walk_end_utc = walk_end_est.tz_localize("US/Eastern").tz_convert("UTC").tz_localize(None)

    # --- Load POPS CSV ---
    pops_df = pd.read_csv(csv_file).copy()
    pops_df["DateTime_utc"] = pd.to_datetime(pops_df["DateTime"], unit="s", utc=True).dt.tz_localize(None)

    if "PM2p5_ug_m3" not in pops_df.columns:
        pops_df["PM2p5_ug_m3"] = pops_df.apply(calculate_pm2_5, axis=1)

    st.write(f"Loaded POPS points: **{len(pops_df)}**")

    # --- Data integrity ---
    score = data_integrity(pops_df, ["DateTime", "PartCon", "PM2p5_ug_m3"])
    st.subheader(f"Data Integrity Score: {score}%")
    st.progress(score / 100)

    # --- Parse KML GPS ---
    gps_df = parse_kml_track(kml_file)
    st.write(f"Loaded GPS points: **{len(gps_df)}**")

    # --- PM2.5 Heatmap ---
    pm25_data = prepare_heatmap_data(pops_df, gps_df, walk_start_utc, walk_end_utc, "PM2p5_ug_m3")
    st.write(f"PM2.5 aligned points: **{len(pm25_data)}**")

    pm25_file = "pops_pm25_map.html"
    plot_pops_map(pm25_data, "PM2p5_ug_m3", pm25_file, "PM2.5 (µg/m³)", 0, 50)

    # --- PartCon Heatmap ---
    partcon_data = prepare_heatmap_data(pops_df, gps_df, walk_start_utc, walk_end_utc, "PartCon")
    st.write(f"PartCon aligned points: **{len(partcon_data)}**")

    partcon_file = "pops_partcon_map.html"
    plot_pops_map(
        partcon_data, "PartCon", partcon_file, "Particle Concentration (#/cm³)",
        partcon_data["PartCon"].min(), partcon_data["PartCon"].max()
    )

    st.success("POPS maps generated!")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(get_download_link(pm25_file, "📥 Download PM2.5 Map", "pops_pm25_map.html"), unsafe_allow_html=True)
    with col2:
        st.markdown(get_download_link(partcon_file, "📥 Download PartCon Map", "pops_partcon_map.html"), unsafe_allow_html=True)

    st.markdown("#### PM2.5 Heatmap")
    with open(pm25_file, "r", encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=500)

    st.markdown("#### Particle Concentration Heatmap")
    with open(partcon_file, "r", encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=500)

############################
# FILE UPLOADERS
############################

if device == "POM":
    st.markdown("### Upload POM Files")
    csv_file = st.file_uploader("Upload POM CSV", type=["csv"])
    gpx_file = st.file_uploader("Upload GPX (GPS track)", type=["gpx"])

    if st.button("Generate Map"):
        if csv_file is None or gpx_file is None:
            st.error("Please upload both the CSV and GPX files.")
            st.stop()
        run_pom(csv_file, gpx_file, time_of_day)

elif device == "POPS":
    st.markdown("### Upload POPS Files")
    csv_file = st.file_uploader("Upload POPS CSV", type=["csv"])
    kml_file = st.file_uploader("Upload KML (GPS track)", type=["kml"])

    st.markdown("### Walk Time Window (Local EST)")
    col1, col2 = st.columns(2)
    with col1:
        walk_date = st.date_input("Walk Date")
        walk_start_time = st.time_input("Start Time (EST)")
    with col2:
        walk_end_time = st.time_input("End Time (EST)")

    if st.button("Generate Maps"):
        if csv_file is None or kml_file is None:
            st.error("Please upload both the CSV and KML files.")
            st.stop()

        walk_start_est = pd.Timestamp(f"{walk_date} {walk_start_time}")
        walk_end_est = pd.Timestamp(f"{walk_date} {walk_end_time}")

        run_pops(csv_file, kml_file, walk_start_est, walk_end_est, time_of_day)
