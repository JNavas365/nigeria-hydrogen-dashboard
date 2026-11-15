import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from branca.colormap import LinearColormap

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Nigeria H2 Dashboard", layout="wide")
st.title("🇳🇬 Nigeria Hydrogen LCOH Dashboard")
st.markdown("Interactive spatial and techno-economic assessment.")

# --- 2. SIDEBAR CONTROLS ---
st.sidebar.header("Main Controls")
pathway = st.sidebar.radio("Select Pathway", ["Green Hydrogen", "Blue Hydrogen"])

st.sidebar.markdown("---")

# Financial Controls (Shared)
st.sidebar.header("Financial Assumptions")
discount_rate = st.sidebar.slider("Discount Rate (%)", min_value=3.0, max_value=15.0, value=8.0, step=0.5)
plant_size = st.sidebar.slider("Plant Size (MW)", min_value=10, max_value=1000, value=100, step=10)

# Pathway-Specific Controls
if pathway == "Green Hydrogen":
    st.sidebar.header("Green Tech & Efficiency")
    scenario = st.sidebar.radio("Select Scenario", ["Solar Only", "Wind Only", "Hybrid"])
    electrolyser_eff = st.sidebar.slider("Electrolyser Efficiency (kWh/kg)", min_value=40, max_value=60, value=55, step=1)
    solar_capex = st.sidebar.slider("Solar CAPEX ($/kW)", min_value=300, max_value=1500, value=700, step=50)
    wind_capex = st.sidebar.slider("Wind CAPEX ($/kW)", min_value=800, max_value=2500, value=1800, step=50)
    elec_capex = st.sidebar.slider("Electrolyser CAPEX ($/kW)", min_value=200, max_value=1500, value=800, step=50)
else:
    st.sidebar.header("Blue Tech & Fuel")
    smr_capex = st.sidebar.slider("SMR CAPEX ($/kW)", min_value=400, max_value=1500, value=800, step=50)
    ccs_capex = st.sidebar.slider("CCS CAPEX ($/kW)", min_value=200, max_value=1000, value=400, step=50)
    gas_price = st.sidebar.slider("Natural Gas Price ($/MMBtu)", min_value=1.0, max_value=8.0, value=2.63, step=0.1)
    pipeline_cost = st.sidebar.slider("Pipeline Cost ($/km)", min_value=100000, max_value=1000000, value=500000, step=50000)

st.sidebar.markdown("---")
st.sidebar.header("Map View Mode")
map_view = st.sidebar.radio("Select View", ["Show All Sites", "Show Best Site per LGA (Cheapest)"])

# --- 3. LOAD DATA & CALCULATE ---
r = discount_rate / 100
n = 20
crf = (r * (1 + r)**n) / ((1 + r)**n - 1)
opex_rate = 0.02
size_kw = plant_size * 1000

if pathway == "Green Hydrogen":
    df = pd.read_csv("green_master.csv")
    scale_factor = (plant_size / 100) ** -0.05
    
    def calc_green(row):
        cf_solar = max(row['Capacity Factor'], 0.01)
        cf_wind = max(min((row['SAMPLE_wind1'] / 11.0) ** 3, 0.45), 0.01)
        
        if scenario == "Solar Only":
            cf = cf_solar
            annual_h2 = (size_kw * 8760 * cf) / electrolyser_eff
            renew_capex = (size_kw / cf) * (solar_capex * scale_factor)
        elif scenario == "Wind Only":
            cf = cf_wind
            annual_h2 = (size_kw * 8760 * cf) / electrolyser_eff
            renew_capex = (size_kw / cf) * (wind_capex * scale_factor)
        else:
            cf = cf_solar + cf_wind
            annual_h2 = (size_kw * 8760 * cf) / electrolyser_eff
            renew_capex = ((size_kw / cf_solar) * (solar_capex * scale_factor)) + ((size_kw / cf_wind) * (wind_capex * scale_factor))
            
        elec_capex_total = size_kw * (elec_capex * scale_factor)
        grid_capex = row['Distance (km)'] * 150000
        total_capex = renew_capex + elec_capex_total + grid_capex
        annual_cost = (total_capex * crf) + (total_capex * opex_rate)
        lcoh = annual_cost / annual_h2
        return lcoh, total_capex, annual_h2, cf
        
    df[['Calculated LCOH', 'Calculated CAPEX', 'Calculated H2', 'Calculated CF']] = df.apply(lambda row: pd.Series(calc_green(row)), axis=1)
    
else: # Blue Hydrogen
    df = pd.read_csv("blue_master.csv")
    
    def calc_blue(row):
        annual_h2 = (size_kw * 8760 * 0.90) / 50 
        
        smr_capex_total = size_kw * smr_capex
        ccs_capex_total = size_kw * ccs_capex
        gas_pipe_capex = row['gas pipeline (km)'] * pipeline_cost
        co2_pipe_capex = row['Storage distance (km)'] * pipeline_cost
        grid_capex = row['Distance (km)'] * 150000
        
        total_capex = smr_capex_total + ccs_capex_total + gas_pipe_capex + co2_pipe_capex + grid_capex
        
        annual_gas_cost = annual_h2 * 0.15 * gas_price
        annual_opex = (total_capex * 0.02) + annual_gas_cost
        
        lcoh = ((total_capex * crf) + annual_opex) / annual_h2
        return lcoh, total_capex, annual_h2, 0.90
        
    df[['Calculated LCOH', 'Calculated CAPEX', 'Calculated H2', 'Calculated CF']] = df.apply(lambda row: pd.Series(calc_blue(row)), axis=1)

# Filter for "Best Site per LGA"
if map_view == "Show Best Site per LGA (Cheapest)":
    df_display = df.loc[df.groupby('NAME_2')['Calculated LCOH'].idxmin()]
else:
    df_display = df

df_display = df_display[df_display['Calculated LCOH'].apply(lambda x: pd.notna(x) and x != float('inf'))]

# --- 4. CREATE MAP ---
m = folium.Map(location=[9.0820, 8.6753], zoom_start=6)

# --- 5. FIXED COLOR GRADIENT & DOTS ---
if pathway == "Green Hydrogen":
    # 12 is the midpoint (Yellow). 0 is Green. 24 is Red.
    colormap = LinearColormap(colors=['green', 'yellow', 'red'], vmin=0, vmax=24)
else:
    # 3 is the midpoint (Yellow). 0 is Green. 6 is Red.
    colormap = LinearColormap(colors=['green', 'yellow', 'red'], vmin=0, vmax=6)

colormap.caption = "LCOH ($/kg)"
m.add_child(colormap)

for index, row in df_display.iterrows():
    current_lcoh = row['Calculated LCOH']
    dot_color = colormap(current_lcoh)
    radius = 8 if map_view == "Show Best Site per LGA (Cheapest)" else 5
    
    if pathway == "Green Hydrogen":
        popup_html = f"""
        <div style="font-family: Arial; width: 250px;">
            <h4 style="margin-bottom: 5px;">{row['NAME_2']} (ID: {row['id']})</h4>
            <hr style="margin: 5px 0;">
            <b>Scenario:</b> {scenario}<br>
            <b>LCOH:</b> ${current_lcoh:.2f}/kg<br>
            <b>Wind Speed:</b> {row['SAMPLE_wind1']:.1f} m/s<br>
            <b>CF:</b> {row['Calculated CF']*100:.1f}%<br>
            <b>Grid Distance:</b> {row['Distance (km)']:.1f} km<br>
            <b>CAPEX:</b> ${row['Calculated CAPEX']:,.0f}
        </div>
        """
    else:
        popup_html = f"""
        <div style="font-family: Arial; width: 250px;">
            <h4 style="margin-bottom: 5px;">{row['NAME_2']} (ID: {row['id']})</h4>
            <hr style="margin: 5px 0;">
            <b>LCOH:</b> ${current_lcoh:.2f}/kg<br>
            <b>Gas Dist:</b> {row['gas pipeline (km)']:.1f} km<br>
            <b>CO2 Dist:</b> {row['Storage distance (km)']:.1f} km<br>
            <b>Grid Dist:</b> {row['Distance (km)']:.1f} km<br>
            <b>CAPEX:</b> ${row['Calculated CAPEX']:,.0f}
        </div>
        """
        
    folium.CircleMarker(
        location=[row['Latitude'], row['Longitude']], radius=radius, color=dot_color,
        fill=True, fill_color=dot_color, fill_opacity=0.8,
        popup=folium.Popup(popup_html, max_width=300)
    ).add_to(m)

st_folium(m, width=1200, height=600)