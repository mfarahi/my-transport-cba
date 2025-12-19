import streamlit as st
import pandas as pd
import numpy as np
import numpy_financial as npf
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Cal-B/C Transport Analyst", layout="wide")

# --- MAIN TAB LAYOUT ---
# We create the structure first, then fill each tab with content
tab_intro, tab_econ, tab_inputs, tab_results = st.tabs([
    "📖 Start Here: Instructions", 
    "💲 1. Economic Parameters & Costs", 
    "🛣️ 2. Model Inputs", 
    "📊 3. Final Results"
])

# ==========================================
# TAB 1: INSTRUCTIONS (THEORY & SCOPE)
# ==========================================
with tab_intro:
    st.title("Transport Cost-Benefit Analysis Tool")
    st.markdown("""
    ### **Welcome to the Cal-B/C Transport Model**
    This tool evaluates the economic viability of transportation infrastructure projects using the **Incremental Benefit-Cost** method.
    
    #### **How It Works (The Logic)**
    We compare two futures to determine the project's value:
    1.  **Base Case (No-Build):** The "Do Nothing" scenario where traffic grows and congestion worsens.
    2.  **Build Case (Alternative):** The scenario where the project is built, improving speed or safety.
    
    The difference between these two scenarios ($\Delta$) creates the economic benefit.
    
    #### **What is Modeled?**
    | **Benefit Category** | **How it is Calculated** |
    | :--- | :--- |
    | **Travel Time Savings** | Valuation of hours saved for Cars and Trucks. Uses the **Rule of Half** to account for induced demand. |
    | **Vehicle Operating Costs** | Savings in fuel, tires, and depreciation due to smoother flow or shorter distances. |
    | **Safety Benefits** | The social value of preventing accidents (Fatalities, Injuries, Property Damage). |
    | **Emission Reductions** | The monetary value of reduced pollutants ($CO_2, NO_x, PM_{10}$) based on VMT changes. |
    
    #### **Cost Model**
    * **Capital Costs:** Initial construction and right-of-way costs.
    * **O&M Costs:** The *net difference* in maintenance between the old road and the new road.
    """)
    
    st.info("👉 **Next Step:** Go to the **'1. Economic Parameters & Costs'** tab to set your valuation rules.")

# ==========================================
# TAB 2: ECONOMIC PARAMETERS & COSTS
# ==========================================
with tab_econ:
    st.header("1. Economic Parameters & Project Costs")
    st.markdown("Define the financial rules and the project's price tag.")
    
    col_econ_1, col_econ_2 = st.columns(2)
    
    with col_econ_1:
        st.subheader("Global Parameters")
        horizon = st.slider("Analysis Period (Years)", 10, 50, 20)
        discount_rate = st.number_input("Real Discount Rate (%)", value=7.0, step=0.5) / 100
        
        st.subheader("Monetization Values (2024 $)")
        vot_auto = st.number_input("Value of Time - Auto ($/hr)", value=18.60)
        vot_truck = st.number_input("Value of Time - Truck ($/hr)", value=54.30)
        voc_auto = st.number_input("Operating Cost - Auto ($/mi)", value=0.28)
        voc_truck = st.number_input("Operating Cost - Truck ($/mi)", value=0.85)

    with col_econ_2:
        st.subheader("Externalities (Social Costs)")
        avg_acc_cost = st.number_input("Avg Cost per Crash ($)", value=156_000, help="Weighted average of Fatal, Injury, and PDO")
        emission_cost_per_mile = st.number_input("Emission Cost ($/VMT)", value=0.03, help="Proxy for CO2, NOx, PM10 costs")
        
        st.divider()
        st.subheader("Project Costs (Financial)")
        cost_construct = st.number_input("Total Capital Construction Cost ($M)", value=45.0) * 1_000_000
        st.caption("Enter the total upfront investment.")
        
        st.markdown("**Annual Maintenance (O&M)**")
        c1, c2 = st.columns(2)
        with c1:
            cost_maint_base = st.number_input("Base Case O&M ($/yr)", value=50000)
        with c2:
            cost_maint_build = st.number_input("Build Case O&M ($/yr)", value=75000)

# ==========================================
# TAB 3: MODEL INPUTS (TRAFFIC & PHYSICAL)
# ==========================================
with tab_inputs:
    st.header("2. Traffic & Physical Data")
    st.markdown("Define the physical characteristics of the road for both scenarios.")
    
    truck_pct = st.slider("Truck Traffic Mix (%)", 0, 40, 10) / 100
    
    col_input_1, col_input_2 = st.columns(2)
    
    with col_input_1:
        st.markdown("### 🔴 Base Case (No-Build)")
        st.write("Existing conditions without the project.")
        base_adt = st.number_input("Base ADT (Vehicles/Day)", value=25000)
        base_speed = st.number_input("Base Speed (mph)", value=35)
        base_length = st.number_input("Base Segment Length (miles)", value=5.0)
        base_acc_rate = st.number_input("Base Crash Rate (per Million VMT)", value=1.50)
        
    with col_input_2:
        st.markdown("### 🟢 Build Case (Project)")
        st.write("Future conditions if project is built.")
        build_adt = st.number_input("Build ADT (Vehicles/Day)", value=28000, help="Higher ADT here implies Induced Demand.")
        build_speed = st.number_input("Build Speed (mph)", value=50)
        build_length = st.number_input("Build Segment Length (miles)", value=5.0)
        build_acc_rate = st.number_input("Build Crash Rate (per Million VMT)", value=1.20)

# ==========================================
# CALCULATION ENGINE (Runs hidden in background)
# ==========================================
def run_cba():
    # 1. SETUP PARAMETERS
    avg_vot = (vot_truck * truck_pct) + (vot_auto * (1 - truck_pct))
    avg_voc = (voc_truck * truck_pct) + (voc_auto * (1 - truck_pct))
    
    # 2. INTERMEDIATE TRAFFIC METRICS (Annual)
    # Average Daily Volume (Rule of Half applies to Time/VOC)
    daily_vol_avg = (base_adt + build_adt) / 2
    
    # Total Annual VMT (For Safety/Emissions)
    vmt_base_annual = base_adt * 365 * base_length
    vmt_build_annual = build_adt * 365 * build_length
    
    # 3. BENEFIT STREAMS (Annual)
    # A. Time Savings (Rule of Half)
    time_cost_base = (base_length / base_speed) * avg_vot
    time_cost_build = (build_length / build_speed) * avg_vot
    ben_time_annual = (time_cost_base - time_cost_build) * daily_vol_avg * 365
    
    # B. VOC Savings (Rule of Half)
    voc_cost_base = base_length * avg_voc
    voc_cost_build = build_length * avg_voc
    ben_voc_annual = (voc_cost_base - voc_cost_build) * daily_vol_avg * 365
    
    # C. Safety Savings (Total VMT difference)
    crashes_base = (vmt_base_annual / 1_000_000) * base_acc_rate
    crashes_build = (vmt_build_annual / 1_000_000) * build_acc_rate
    ben_safety_annual = (crashes_base - crashes_build) * avg_acc_cost
    
    # D. Emission Savings (Total VMT difference)
    ben_emission_annual = (vmt_base_annual - vmt_build_annual) * emission_cost_per_mile

    # E. Net Maintenance Cost
    cost_maint_net_annual = cost_maint_build - cost_maint_base

    # 4. CASH FLOW ARRAYS
    years = range(horizon + 1)
    
    results_breakdown = {
        "Time": 0, "VOC": 0, "Safety": 0, "Emissions": 0, 
        "Capital": 0, "O&M": 0
    }
    
    flow_net = []

    for t in years:
        df_factor = 1 / ((1 + discount_rate) ** t)
        
        if t == 0:
            yr_net = -cost_construct
            results_breakdown["Capital"] += cost_construct
        else:
            yr_ben = ben_time_annual + ben_voc_annual + ben_safety_annual + ben_emission_annual
            yr_cost = cost_maint_net_annual
            yr_net = yr_ben - yr_cost
            
            # PV Accumulation
            results_breakdown["Time"] += ben_time_annual * df_factor
            results_breakdown["VOC"] += ben_voc_annual * df_factor
            results_breakdown["Safety"] += ben_safety_annual * df_factor
            results_breakdown["Emissions"] += ben_emission_annual * df_factor
            results_breakdown["O&M"] += cost_maint_net_annual * df_factor
        
        flow_net.append(yr_net)

    # 5. INDICATORS
    total_pv_ben = sum(results_breakdown[k] for k in ["Time", "VOC", "Safety", "Emissions"])
    total_pv_cost = results_breakdown["Capital"] + results_breakdown["O&M"]
    
    npv = total_pv_ben - total_pv_cost
    bcr = total_pv_ben / total_pv_cost if total_pv_cost != 0 else 0
    
    # IRR
    try:
        irr = npf.irr(flow_net)
    except:
        irr = 0
        
    # Payback
    payback = "Not Reached"
    cum = 0
    for i, f in enumerate(flow_net):
        cum += f
        if cum >= 0:
            payback = i
            break

    return results_breakdown, npv, bcr, irr, payback

# Execute Logic
res, npv, bcr, irr, payback = run_cba()

# ==========================================
# TAB 4: FINAL RESULTS (DASHBOARD)
# ==========================================
with tab_results:
    st.header("3. Analysis Results")
    
    # Top Level Cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Net Present Value (NPV)", f"${npv/1e6:,.1f} M", help="Total Economic Value generated minus costs.")
    k2.metric("Benefit/Cost Ratio", f"{bcr:.2f}", help="Value returned for every $1 spent. >1.0 is good.")
    k3.metric("Internal Rate of Return", f"{irr:.1%}", help="The effective interest rate earned by the project.")
    k4.metric("Payback Period", f"{payback} Years", help="Time to recover the initial investment.")

    st.divider()

    # DETAILED TABLES
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Investment Analysis (PV)")
        df_costs = pd.DataFrame([
            {"Category": "Capital Construction", "Value ($M)": res["Capital"] / 1e6},
            {"Category": "Net O&M Costs", "Value ($M)": res["O&M"] / 1e6},
            {"Category": "TOTAL COSTS", "Value ($M)": (res["Capital"] + res["O&M"]) / 1e6}
        ])
        st.dataframe(df_costs.style.format({"Value ($M)": "{:,.2f}"}), hide_index=True, use_container_width=True)

    with col_right:
        st.subheader("Benefit Analysis (PV)")
        df_bens = pd.DataFrame([
            {"Category": "Travel Time Savings", "Value ($M)": res["Time"] / 1e6},
            {"Category": "Vehicle Op. Cost Savings", "Value ($M)": res["VOC"] / 1e6},
            {"Category": "Accident Cost Savings", "Value ($M)": res["Safety"] / 1e6},
            {"Category": "Emission Reductions", "Value ($M)": res["Emissions"] / 1e6},
            {"Category": "TOTAL BENEFITS", "Value ($M)": (res["Time"] + res["VOC"] + res["Safety"] + res["Emissions"]) / 1e6}
        ])
        st.dataframe(df_bens.style.format({"Value ($M)": "{:,.2f}"}), hide_index=True, use_container_width=True)

    # EXCEL EXPORT
    st.divider()
    def to_excel():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Summary Sheet
            pd.DataFrame({
                "Metric": ["NPV", "B/C Ratio", "IRR", "Payback"],
                "Value": [npv, bcr, irr, payback]
            }).to_excel(writer, sheet_name='Summary', index=False)
            
            # Detailed PV Sheet
            pd.concat([df_costs, df_bens]).to_excel(writer, sheet_name='Detailed_PV', index=False)
            
        return output.getvalue()

    st.download_button("📥 Download Full Results (Excel)", data=to_excel(), file_name="CalBC_Analysis_Report.xlsx")
