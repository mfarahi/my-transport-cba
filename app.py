import streamlit as st
import pandas as pd

st.set_page_config(page_title="Transport CBA Tool", layout="wide")

st.title("🛣️ Infrastructure Cost-Benefit Analysis")
st.markdown("Evaluating the economic viability of transport projects.")

# --- SIDEBAR: INPUTS ---
with st.sidebar:
    st.header("Project Costs")
    construction_cost = st.number_input("Construction Cost ($M)", value=150.0)
    annual_maint = st.number_input("Annual Maintenance ($M)", value=2.5)
    
    st.header("Project Benefits")
    daily_traffic = st.number_input("Average Daily Traffic", value=25000)
    time_savings_val = st.number_input("Value of Time Saved ($/hour)", value=25.0)
    minutes_saved = st.slider("Minutes Saved per Trip", 1, 30, 5)
    
    st.header("Economic Factors")
    discount_rate = st.slider("Discount Rate (%)", 1, 15, 7) / 100
    horizon = st.number_input("Analysis Period (Years)", value=20)

# --- CALCULATIONS ---
# Calculate Annual Benefit from Time Savings
annual_benefit = (daily_traffic * 365 * (minutes_saved / 60) * time_savings_val) / 1_000_000 # in $Millions

years = list(range(0, horizon + 1))
cash_flows = []

for year in years:
    if year == 0:
        flow = -construction_cost
    else:
        flow = annual_benefit - annual_maint
    
    pv = flow / ((1 + discount_rate) ** year)
    cash_flows.append({"Year": year, "Cash Flow": flow, "Present Value": pv})

df = pd.DataFrame(cash_flows)
npv = df["Present Value"].sum()
bcr = (df.loc[df["Year"] > 0, "Present Value"].sum()) / construction_cost # Benefit-Cost Ratio

# --- DISPLAY RESULTS ---
col1, col2, col3 = st.columns(3)
col1.metric("Net Present Value (NPV)", f"${round(npv, 2)}M")
col2.metric("Benefit-Cost Ratio (BCR)", f"{round(bcr, 2)}")
col3.metric("Annual Benefit", f"${round(annual_benefit, 2)}M")

st.subheader("Cumulative Present Value Over Time")
df["Cumulative NPV"] = df["Present Value"].cumsum()
st.line_chart(df.set_index("Year")["Cumulative NPV"])

st.subheader("Annual Breakdown ($ Millions)")
st.dataframe(df.style.format("{:.2f}"))
