import streamlit as st
import pandas as pd
import numpy as np
import numpy_financial as npf  # Needed for IRR calculation
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Cal-B/C Transport Analyst", layout="wide")
st.title("🛣️ Cal-B/C Results Dashboard")
st.markdown("Replicating standard Caltrans Benefit-Cost Analysis outputs.")

# --- SIDEBAR: INPUTS ---
tab_project, tab_params = st.sidebar.tabs(["1. Project Data", "2. Economic Parameters"])

with tab_project:
    st.header("Project Config")
    horizon = st.slider("Analysis Period (Years)", 10, 30, 20)
    
    st.subheader("Traffic & Operations")
    truck_pct = st.slider("Truck Traffic (%)", 0, 30, 10) / 100
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Base Case (No-Build)")
        base_adt = st.number_input("Base ADT (Veh/Day)", value=25000)
        base_speed = st.number_input("Base Speed (mph)", value=35)
        base_length = st.number_input("Base Length (mi)", value=5.0)
        base_acc_rate = st.number_input("Base Crash Rate (per MVM)", value=1.50)
        
    with col2:
        st.markdown("### Build Case (Project)")
        build_adt = st.number_input("Build ADT (Veh/Day)", value=28000)
        build_speed = st.number_input("Build Speed (mph)", value=50)
        build_length = st.number_input("Build Length (mi)", value=5.0)
        build_acc_rate = st.number_input("Build Crash Rate (per MVM)", value=1.20)

    st.subheader("Project Costs")
    cost_construct = st.number_input("Total Capital Cost ($M)", value=45.0) * 1_000_000
    cost_maint_base = st.number_input("Base Annual Maint. ($)", value=50000)
    cost_maint_build = st.number_input("Build Annual Maint. ($)", value=75000)

with tab_params:
    st.header("Economic Parameters (2024)")
    discount_rate = st.number_input("Real Discount Rate (%)", value=7.0) / 100
    
    st.subheader("Monetization Values")
    vot_auto = st.number_input("Auto VOT ($/hr)", value=18.60)
    vot_truck = st.number_input("Truck VOT ($/hr)", value=54.30)
    voc_auto = st.number_input("Auto VOC ($/mi)", value=0.28)
    voc_truck = st.number_input("Truck VOC ($/mi)", value=0.85)
    
    st.subheader("Externalities")
    avg_acc_cost = st.number_input("Avg Cost per Crash ($)", value=156_000, help="Weighted average of Fatal, Injury, and PDO")
    # Simplified emission cost per mile (Caltrans typically calculates tons of CO2/NOx, here simplified to $/mile)
    emission_cost_per_mile = st.number_input("Emission Cost ($/VMT)", value=0.03, help="Proxy for CO2, NOx, PM10 costs")

# --- CALCULATION ENGINE ---
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
    # Note: If VMT increases (Induced Demand), this benefit might be negative!
    ben_emission_annual = (vmt_base_annual - vmt_build_annual) * emission_cost_per_mile

    # E. Net Maintenance Cost (This is a COST, but in CBA often treated as negative benefit or separate cost line)
    # We will treat it as a cost item to match Cal-B/C structure
    cost_maint_net_annual = cost_maint_build - cost_maint_base

    # 4. CASH FLOW ARRAYS
    years = range(horizon + 1)
    # Initialize arrays
    flow_benefits = [] 
    flow_costs = []
    net_flows = []
    
    cumulative_benefits_pv = 0
    cumulative_costs_pv = 0
    
    results_breakdown = {
        "Time": 0, "VOC": 0, "Safety": 0, "Emissions": 0, 
        "Capital": 0, "O&M": 0
    }

    for t in years:
        df_factor = 1 / ((1 + discount_rate) ** t)
        
        if t == 0:
            # Year 0: Construction only
            yr_ben = 0
            yr_cost = cost_construct
            
            results_breakdown["Capital"] += cost_construct  # PV of Year 0 is just Cost
        else:
            # Operating Years
            yr_ben = ben_time_annual + ben_voc_annual + ben_safety_annual + ben_emission_annual
            yr_cost = cost_maint_net_annual
            
            # Add to PV totals
            results_breakdown["Time"] += ben_time_annual * df_factor
            results_breakdown["VOC"] += ben_voc_annual * df_factor
            results_breakdown["Safety"] += ben_safety_annual * df_factor
            results_breakdown["Emissions"] += ben_emission_annual * df_factor
            results_breakdown["O&M"] += cost_maint_net_annual * df_factor

        # PV Calculations for Year t
        pv_ben = yr_ben * df_factor
        pv_cost = yr_cost * df_factor
        
        cumulative_benefits_pv += pv_ben
        cumulative_costs_pv += pv_cost
        
        flow_benefits.append(yr_ben)
        flow_costs.append(yr_cost)
        net_flows.append(yr_ben - yr_cost)

    # 5. ECONOMIC INDICATORS
    total_pv_ben = sum(results_breakdown[k] for k in ["Time", "VOC", "Safety", "Emissions"])
    total_pv_cost = results_breakdown["Capital"] + results_breakdown["O&M"]
    
    npv = total_pv_ben - total_pv_cost
    bcr = total_pv_ben / total_pv_cost if total_pv_cost != 0 else 0
    
    # Payback Period Calculation
    payback_year = "Not Reached"
    cum_cash = 0
    for i, flow in enumerate(net_flows):
        cum_cash += flow
        if cum_cash >= 0:
            payback_year = i
            break
            
    # IRR Calculation
    try:
        irr = npf.irr(net_flows)
    except:
        irr = 0

    return results_breakdown, npv, bcr, irr, payback_year, flow_benefits, flow_costs

# --- EXECUTION ---
res, npv, bcr, irr, payback, stream_b, stream_c = run_cba()

# --- DISPLAY THE "RESULTS SHEET" ---
st.header("Results Summary")

# Top Level Cards
k1, k2, k3, k4 = st.columns(4)
k1.metric("Net Present Value (NPV)", f"${npv/1e6:,.1f} M")
k2.metric("Benefit/Cost Ratio", f"{bcr:.2f}")
k3.metric("Internal Rate of Return", f"{irr:.1%}")
k4.metric("Payback Period", f"{payback} Years")

st.divider()

# THE DETAILED RESULTS TABLE (Matching Excel Layout)
st.subheader("Itemized Results (Present Value in Millions)")

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("#### 1. Project Costs (PV)")
    df_costs = pd.DataFrame([
        {"Item": "Capital Construction", "Value ($M)": res["Capital"] / 1e6},
        {"Item": "Net O&M Costs", "Value ($M)": res["O&M"] / 1e6},
        {"Item": "TOTAL COSTS", "Value ($M)": (res["Capital"] + res["O&M"]) / 1e6}
    ])
    st.dataframe(df_costs.style.format({"Value ($M)": "{:,.2f}"}), hide_index=True, use_container_width=True)

with col_right:
    st.markdown("#### 2. Project Benefits (PV)")
    df_bens = pd.DataFrame([
        {"Item": "Travel Time Savings", "Value ($M)": res["Time"] / 1e6},
        {"Item": "Veh. Operating Cost Savings", "Value ($M)": res["VOC"] / 1e6},
        {"Item": "Accident Cost Savings", "Value ($M)": res["Safety"] / 1e6},
        {"Item": "Emission Reductions", "Value ($M)": res["Emissions"] / 1e6},
        {"Item": "TOTAL BENEFITS", "Value ($M)": (res["Time"] + res["VOC"] + res["Safety"] + res["Emissions"]) / 1e6}
    ])
    st.dataframe(df_bens.style.format({"Value ($M)": "{:,.2f}"}), hide_index=True, use_container_width=True)

# Visualizing the Flows
st.divider()
st.subheader("Cash Flow Analysis")
chart_data = pd.DataFrame({
    "Year": range(horizon + 1),
    "Benefits": stream_b,
    "Costs": stream_c,
    "Net Flow": [b - c for b, c in zip(stream_b, stream_c)]
})
st.line_chart(chart_data.set_index("Year")[["Benefits", "Costs", "Net Flow"]])

# --- EXPORT TO EXCEL ---
def to_excel():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Create Summary Sheet
        summary_df = pd.DataFrame({
            "Metric": ["NPV", "B/C Ratio", "IRR", "Payback"],
            "Value": [npv, bcr, irr, payback]
        })
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Create Detailed Flows Sheet
        flows_df = pd.DataFrame({
            "Year": range(horizon + 1),
            "Benefits": stream_b,
            "Costs": stream_c,
            "Net Flow": chart_data["Net Flow"]
        })
        flows_df.to_excel(writer, sheet_name='Cash_Flows', index=False)
    return output.getvalue()

st.download_button("📥 Download Excel Report", data=to_excel(), file_name="CalBC_Results_Sheet.xlsx")
