import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from branca.colormap import LinearColormap

st.title("6. Interactive Web-GIS Dashboard")
st.markdown("**Dynamic spatial and techno-economic assessment.**")

# ==========================================
# 1. SIDEBAR CONTROLS
# ==========================================
st.sidebar.header("Main Controls")
pathway = st.sidebar.radio("Select Pathway", ["Green Hydrogen", "Blue Hydrogen"])

st.sidebar.markdown("---")
st.sidebar.header("Geographic Filter (Select to load map)")

# Load the raw data first so we can populate the dropdowns
if pathway == "Green Hydrogen":
    df = pd.read_csv("green_master.csv")
else:
    df = pd.read_csv("blue_master.csv")

# Find the region column robustly
region_col = next((col for col in df.columns if col.strip().lower() == 'region'), None)

# REGION FILTER
region_filter = st.sidebar.selectbox(
    "1. Select Region", 
    ["All Regions", "North West (NW)", "North East (NE)", "North Central (NC)", "South West (SW)", "South East (SE)", "South South (SS)"]
)
region_code = region_filter.split("(")[1].replace(")", "") if "(" in region_filter else "All"

# STATE MULTISELECT (Cascades from Region)
if region_code != "All" and region_col:
    temp_df_states = df[df[region_col].astype(str).str.strip().str.upper() == region_code]
else:
    temp_df_states = df.copy()

available_states = sorted(temp_df_states['NAME_1'].unique()) if 'NAME_1' in temp_df_states.columns else []
selected_states = st.sidebar.multiselect("2. Select State(s)", available_states)

# LGA MULTISELECT (Cascades from States)
temp_df_lgas = temp_df_states.copy()
if selected_states:
    temp_df_lgas = temp_df_lgas[temp_df_lgas['NAME_1'].isin(selected_states)]
    
available_lgas = sorted(temp_df_lgas['NAME_2'].unique()) if 'NAME_2' in temp_df_lgas.columns else []
selected_lgas = st.sidebar.multiselect("3. Select LGA(s)", available_lgas)

st.sidebar.markdown("---")

# FINANCIAL SLIDERS
st.sidebar.header("Financial Assumptions")
discount_rate = st.sidebar.slider("Discount Rate (WACC) %", min_value=3.0, max_value=20.0, value=10.0, step=0.5)
plant_size = st.sidebar.slider("Plant Size (MW)", min_value=10, max_value=1000, value=100, step=10)

if pathway == "Green Hydrogen":
    st.sidebar.header("Green Tech & Efficiency")
    scenario = st.sidebar.radio("Select Scenario", ["Solar Only", "Wind Only", "Hybrid"])
    electrolyser_eff = st.sidebar.slider("Electrolyser Efficiency (kWh/kg)", min_value=40, max_value=65, value=55, step=1)
    solar_capex = st.sidebar.slider("Solar CAPEX ($/kW)", min_value=500, max_value=1500, value=850, step=50)
    wind_capex = st.sidebar.slider("Wind CAPEX ($/kW)", min_value=800, max_value=2500, value=1400, step=50)
    elec_capex = st.sidebar.slider("Electrolyser CAPEX ($/kW)", min_value=400, max_value=1500, value=800, step=50)
    
    st.sidebar.header("Green Operations")
    green_opex = st.sidebar.slider("OPEX (% of CAPEX)", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
    water_capex_rate = st.sidebar.slider("Water CAPEX ($/MW)", min_value=50000, max_value=300000, value=150000, step=10000)
    water_om_rate = st.sidebar.slider("Water O&M ($/m³)", min_value=0.01, max_value=0.20, value=0.05, step=0.01)
    stack_rate = st.sidebar.slider("Stack Replacement ($/kW)", min_value=100, max_value=600, value=350, step=50)
else:
    st.sidebar.header("Blue Tech & Fuel")
    smr_capex = st.sidebar.slider("SMR CAPEX ($/kW)", min_value=400, max_value=1500, value=850, step=50)
    ccs_capex = st.sidebar.slider("CCS CAPEX ($/kW)", min_value=300, max_value=1200, value=700, step=50)
    gas_price = st.sidebar.slider("Natural Gas Price ($/MMBtu)", min_value=1.0, max_value=8.0, value=2.63, step=0.1)
    pipeline_cost = st.sidebar.slider("Pipeline Cost ($/km)", min_value=100000, max_value=1000000, value=500000, step=50000)
    
    st.sidebar.header("Blue Operations")
    gas_cons = st.sidebar.slider("Gas Consumption (MMBtu/kg)", min_value=0.10, max_value=0.25, value=0.15, step=0.01)
    co2_cost_rate = st.sidebar.slider("CO2 Transport & Storage ($/t)", min_value=10, max_value=100, value=50, step=5)
    smr_opex = st.sidebar.slider("SMR OPEX (% of CAPEX)", min_value=2.0, max_value=8.0, value=4.7, step=0.1)
    ccs_opex = st.sidebar.slider("CCS OPEX (% of CAPEX)", min_value=1.0, max_value=6.0, value=3.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("Map View Mode")
map_view = st.sidebar.radio("Select View", ["Show All Sites", "Show Best Site per LGA (Cheapest)"], index=1)


# ==========================================
# 2. FILTERING LOGIC (The Empty Map Magic)
# ==========================================
# If NO filters are selected at all, show an empty dataframe
if region_code == "All" and not selected_states and not selected_lgas:
    df_filtered = df.iloc[0:0].copy() # Empty map
else:
    df_filtered = df.copy()
    if region_code != "All" and region_col:
        df_filtered = df_filtered[df_filtered[region_col].astype(str).str.strip().str.upper() == region_code]
    if selected_states:
        df_filtered = df_filtered[df_filtered['NAME_1'].isin(selected_states)]
    if selected_lgas:
        df_filtered = df_filtered[df_filtered['NAME_2'].isin(selected_lgas)]


# ==========================================
# 3. CALCULATION ENGINE
# ==========================================
r = discount_rate / 100
n = 20
crf = (r * (1 + r)**n) / ((1 + r)**n - 1)
size_kw = plant_size * 1000
size_mw = plant_size

if pathway == "Green Hydrogen":
    scale_factor = (plant_size / 100) ** -0.05
    
    def calc_green(row):
        cf_solar = max(row['Capacity Factor'], 0.01)
        cf_wind = max(min(0.28 * (row['SAMPLE_wind1'] / 8.02) ** 3, 0.45), 0.01)
        
        if scenario == "Solar Only":
            cf = cf_solar
            annual_h2 = (size_kw * 8760 * cf) / electrolyser_eff
            renew_capex = (size_kw / cf) * (solar_capex * scale_factor)
        elif scenario == "Wind Only":
            cf = cf_wind
            annual_h2 = (size_kw * 8760 * cf) / electrolyser_eff
            renew_capex = (size_kw / cf) * (wind_capex * scale_factor)
        else: # Hybrid
            cf = cf_solar + cf_wind
            annual_h2 = (size_kw * 8760 * cf) / electrolyser_eff
            renew_capex = ((size_kw / cf_solar) * (solar_capex * scale_factor)) + ((size_kw / cf_wind) * (wind_capex * scale_factor))
            
        elec_capex_total = size_kw * (elec_capex * scale_factor)
        grid_capex = row['Distance (km)'] * 150000
        water_capex = size_mw * water_capex_rate
        total_capex = renew_capex + elec_capex_total + grid_capex + water_capex
        
        annual_water_om = (annual_h2 * 10) / 1000 * water_om_rate
        annual_opex = (total_capex * (green_opex / 100)) + annual_water_om
        stack_pv = (size_kw * stack_rate) / (1 + r)**10
        
        lcoh = ((total_capex * crf) + annual_opex + stack_pv) / annual_h2
        return lcoh, total_capex, annual_h2, cf, renew_capex, elec_capex_total, grid_capex, water_capex
        
    if not df_filtered.empty:
        df_filtered[['Calculated LCOH', 'Calculated CAPEX', 'Calculated H2', 'Calculated CF', 'Renew CAPEX', 'Elec CAPEX', 'Grid CAPEX', 'Water CAPEX']] = df_filtered.apply(lambda row: pd.Series(calc_green(row)), axis=1)
    
else: # Blue Hydrogen
    def calc_blue(row):
        annual_h2 = (size_kw * 8760 * 0.90) / 50 
        
        smr_total = size_kw * smr_capex
        ccs_total = size_kw * ccs_capex
        gas_pipe_capex = row['gas pipeline (km)'] * pipeline_cost
        co2_pipe_capex = row['Storage distance (km)'] * pipeline_cost
        grid_capex = row['Distance (km)'] * 150000
        water_capex = size_mw * 150000
        
        total_capex = smr_total + ccs_total + gas_pipe_capex + co2_pipe_capex + grid_capex + water_capex
        
        gas_cost = annual_h2 * gas_cons * gas_price
        co2_cost = (annual_h2 * 8.9 * 0.90 * co2_cost_rate) / 1000
        water_om = (annual_h2 * 7) / 1000 * 0.05
        
        annual_opex = (smr_total * (smr_opex / 100)) + (ccs_total * (ccs_opex / 100)) + gas_cost + co2_cost + water_om
        
        lcoh = ((total_capex * crf) + annual_opex) / annual_h2
        infra_capex = gas_pipe_capex + co2_pipe_capex + grid_capex
        
        return lcoh, total_capex, annual_h2, 0.90, smr_total, ccs_total, infra_capex, water_capex
        
    if not df_filtered.empty:
        df_filtered[['Calculated LCOH', 'Calculated CAPEX', 'Calculated H2', 'Calculated CF', 'SMR CAPEX', 'CCS CAPEX', 'Infrastructure', 'Water CAPEX']] = df_filtered.apply(lambda row: pd.Series(calc_blue(row)), axis=1)

# Filter for "Best Site per LGA"
if map_view == "Show Best Site per LGA (Cheapest)" and not df_filtered.empty:
    df_display = df_filtered.loc[df_filtered.groupby('NAME_2')['Calculated LCOH'].idxmin()]
else:
    df_display = df_filtered

if not df_display.empty:
    df_display = df_display[df_display['Calculated LCOH'].apply(lambda x: pd.notna(x) and x != float('inf'))]


# ==========================================
# 4. PAGE LAYOUT (MAP & CHARTS)
# ==========================================
col1, col2 = st.columns([2, 1])

with col1:
    filter_text = f"Region: {region_filter}"
    if selected_states:
        filter_text += f" | States: {', '.join(selected_states)}"
    if selected_lgas:
        filter_text += f" | LGAs: {len(selected_lgas)} selected"
        
    st.subheader(f"Interactive Map ({filter_text})")
    
    m = folium.Map(location=[9.0820, 8.6753], zoom_start=6, min_zoom=5, max_zoom=12, max_bounds=[[3.5, 2.0], [14.5, 15.5]] )
    
    if pathway == "Green Hydrogen":
        colormap = LinearColormap(colors=['green', 'yellow', 'red'], vmin=10, vmax=25)
    else:
        colormap = LinearColormap(colors=['green', 'yellow', 'red'], vmin=1.5, vmax=4.0)
    colormap.caption = "LCOH ($/kg)"
    m.add_child(colormap)

    # Add text on map if no filters are selected
    if df_display.empty:
        title_html = '''
                     <h3 align="center" style="font-size:20px; color: #31333F; margin-top: 20%;">
                     👈 Select a Region, State, or LGA from the sidebar to load sites.</h3>
                     '''
        m.get_root().html.add_child(folium.Element(title_html))
    else:
        for index, row in df_display.iterrows():
            current_lcoh = row['Calculated LCOH']
            dot_color = colormap(current_lcoh)
            radius = 8 if map_view == "Show Best Site per LGA (Cheapest)" else 3
            
            if pathway == "Green Hydrogen":
                popup_html = f"""
                <div style="font-family: Arial; width: 250px;">
                    <h4 style="margin-bottom: 5px;">{row['NAME_2']} ({row['NAME_1']})</h4>
                    <hr style="margin: 5px 0;">
                    <b>Scenario:</b> {scenario}<br>
                    <b>LCOH:</b> ${current_lcoh:.2f}/kg<br>
                    <b>Wind Speed:</b> {row['SAMPLE_wind1']:.1f} m/s<br>
                    <b>CF:</b> {row['Calculated CF']*100:.1f}%<br>
                    <b>Grid Dist:</b> {row['Distance (km)']:.1f} km<br>
                    <b>CAPEX:</b> ${row['Calculated CAPEX']:,.0f}
                </div>
                """
            else:
                popup_html = f"""
                <div style="font-family: Arial; width: 250px;">
                    <h4 style="margin-bottom: 5px;">{row['NAME_2']} ({row['NAME_1']})</h4>
                    <hr style="margin: 5px 0;">
                    <b>LCOH:</b> ${current_lcoh:.2f}/kg<br>
                    <b>Gas Dist:</b> {row['gas pipeline (km)']:.1f} km<br>
                    <b>CO2 Dist:</b> {row['Storage distance (km)']:.1f} km<br>
                    <b>CAPEX:</b> ${row['Calculated CAPEX']:,.0f}
                </div>
                """
            
            folium.CircleMarker(
                location=[row['Latitude'], row['Longitude']], radius=radius, color=dot_color,
                fill=True, fill_color=dot_color, fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=300)
            ).add_to(m)

    st_folium(m, width=800, height=500)

with col2:
    st.subheader("Economic Insights")
    
    st.markdown("**Top 10 Cheapest Sites ($/kg)**")
    if not df_display.empty:
        top_10 = df_display.nsmallest(10, 'Calculated LCOH').set_index('NAME_2')['Calculated LCOH']
        st.bar_chart(top_10, color="#2e8b57") 
    else:
        st.info("No sites loaded. Use the sidebar filters.")
    
    st.markdown("**CAPEX Breakdown for Selected Site**")
    if not df_display.empty:
        selected_site = st.selectbox("Select a site to view CAPEX:", df_display['NAME_2'].unique())
        site_row = df_display[df_display['NAME_2'] == selected_site].iloc[0]
        
        if pathway == "Green Hydrogen":
            capex_data = pd.DataFrame({
                'Component': ['Renewables', 'Electrolyser', 'Grid', 'Water'],
                'CAPEX ($)': [site_row['Renew CAPEX'], site_row['Elec CAPEX'], site_row['Grid CAPEX'], site_row['Water CAPEX']]
            })
        else:
            capex_data = pd.DataFrame({
                'Component': ['SMR Plant', 'CCS', 'Infrastructure', 'Water'],
                'CAPEX ($)': [site_row['SMR CAPEX'], site_row['CCS CAPEX'], site_row['Infrastructure'], site_row['Water CAPEX']]
            })
            
        st.bar_chart(capex_data.set_index('Component'), color="#d2691e")
    else:
        st.info("Select a site to view the CAPEX chart.")
