"""
Medical Bill Analyzer - Streamlit Frontend
Beautiful UI for CGHS bill analysis
"""

import streamlit as st
import requests
import json
from pathlib import Path
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px

# ============================================================================
# CONFIGURATION
# ============================================================================

# Backend API URL
API_BASE_URL = "http://localhost:8000"

# Page config
st.set_page_config(
    page_title="Medical Bill Analyzer",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stAlert {
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
        margin: 0.5rem 0;
    }
    .violation-high {
        background-color: #fee;
        border-left: 4px solid #f44;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.5rem;
    }
    .violation-medium {
        background-color: #fff4e6;
        border-left: 4px solid #ff9800;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.5rem;
    }
    .violation-info {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.5rem;
    }
    .compliant {
        background-color: #e8f5e9;
        border-left: 4px solid #4caf50;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.5rem;
    }
    h1 {
        color: #1e88e5;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem;
        border-radius: 0.5rem;
        font-weight: 600;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_backend_health():
    """Check if backend is running"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def get_statistics():
    """Get statistics from backend"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/stats")
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def search_hospitals(nabh_only=False, name_query=None):
    """Search hospitals"""
    try:
        params = {
            "nabh_only": nabh_only,
            "limit": 100
        }
        if name_query:
            params["name_query"] = name_query
        
        response = requests.get(f"{API_BASE_URL}/api/v1/hospitals/list", params=params)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error searching hospitals: {e}")
        return None

def analyze_bill(file):
    """Upload and analyze bill"""
    try:
        files = {"file": (file.name, file, file.type)}
        response = requests.post(
            f"{API_BASE_URL}/api/v1/bills/upload-and-analyze",
            files=files,
            timeout=120
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            error_detail = response.json().get("detail", "Unknown error")
            st.error(f"Analysis failed: {error_detail}")
            return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None

def display_severity_badge(severity):
    """Display colored severity badge"""
    colors = {
        "high": "🔴",
        "medium": "🟠",
        "low": "🟡",
        "compliant": "🟢",
        "info": "🔵"
    }
    return f"{colors.get(severity, '⚪')} {severity.upper()}"

def create_price_comparison_chart(price_comparisons):
    """Create price comparison chart"""
    if not price_comparisons:
        return None
    
    df = pd.DataFrame([
        {
            "Item": pc["item"][:30] + "..." if len(pc["item"]) > 30 else pc["item"],
            "Charged": pc["charged_amount"],
            "CGHS Rate": pc["cghs_rate"],
            "Deviation %": pc["deviation_percentage"]
        }
        for pc in price_comparisons[:10]  # Top 10 items
    ])
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name='Charged Amount',
        x=df['Item'],
        y=df['Charged'],
        marker_color='#ef5350'
    ))
    
    fig.add_trace(go.Bar(
        name='CGHS Rate',
        x=df['Item'],
        y=df['CGHS Rate'],
        marker_color='#66bb6a'
    ))
    
    fig.update_layout(
        title="Price Comparison: Charged vs CGHS Rates",
        xaxis_title="Items",
        yaxis_title="Amount (₹)",
        barmode='group',
        height=400,
        hovermode='x unified'
    )
    
    return fig

def create_deviation_chart(price_comparisons):
    """Create deviation percentage chart"""
    if not price_comparisons:
        return None
    
    df = pd.DataFrame([
        {
            "Item": pc["item"][:30] + "..." if len(pc["item"]) > 30 else pc["item"],
            "Deviation %": pc["deviation_percentage"]
        }
        for pc in sorted(price_comparisons, key=lambda x: x["deviation_percentage"], reverse=True)[:10]
    ])
    
    colors = ['#f44336' if x > 50 else '#ff9800' if x > 20 else '#4caf50' for x in df["Deviation %"]]
    
    fig = go.Figure(go.Bar(
        x=df["Deviation %"],
        y=df["Item"],
        orientation='h',
        marker_color=colors,
        text=df["Deviation %"].apply(lambda x: f"{x:.1f}%"),
        textposition='outside'
    ))
    
    fig.update_layout(
        title="Top 10 Items by Price Deviation",
        xaxis_title="Deviation from CGHS Rate (%)",
        yaxis_title="",
        height=400,
        showlegend=False
    )
    
    return fig

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.image("https://img.icons8.com/clouds/200/hospital.png", width=150)
    st.title("🏥 Medical Bill Analyzer")
    st.markdown("---")
    
    # Backend status
    if check_backend_health():
        st.success("✅ Backend Online")
        
        # Get statistics
        stats = get_statistics()
        if stats:
            st.metric("CGHS Hospitals", stats["hospitals"]["total"])
            st.metric("NABH Hospitals", stats["hospitals"]["nabh"])
            st.metric("Procedures in DB", stats["procedures"]["total"])
    else:
        st.error("❌ Backend Offline")
        st.warning("Please start the backend server:\n```bash\npython backend.py\n```")
    
    st.markdown("---")
    
    # Navigation
    st.subheader("Navigation")
    page = st.radio(
        "Select Page",
        ["🏠 Home", "📤 Upload Bill", "🏥 Hospital Search", "📊 Analytics"],
        label_visibility="collapsed"
    )

# ============================================================================
# HOME PAGE
# ============================================================================

if page == "🏠 Home":
    st.title("Welcome to Medical Bill Analyzer")
    
    st.markdown("""
    ### 🎯 What We Do
    
    This system analyzes medical bills against **CGHS (Central Government Health Scheme)** approved rates 
    to detect overcharging, fraud, and non-compliance.
    
    ### ✨ Key Features
    """)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("""
        **🔍 Smart OCR**
        - Google Vision OCR
        - Gemini AI Structuring
        - Handles poor quality bills
        """)
    
    with col2:
        st.success("""
        **✅ CGHS Validation**
        - NABH vs Non-NABH rates
        - Package rate violations
        - BIS standard compliance
        """)
    
    with col3:
        st.warning("""
        **⚖️ Legal Analysis**
        - CGHS vs Non-CGHS hospitals
        - Actionable recommendations
        - Complaint generation
        """)
    
    st.markdown("---")
    
    # How it works
    st.subheader("🔄 How It Works")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        **1️⃣ Upload Bill**
        
        Upload your medical bill image or PDF
        """)
    
    with col2:
        st.markdown("""
        **2️⃣ OCR Extraction**
        
        Google Vision + Gemini extract data
        """)
    
    with col3:
        st.markdown("""
        **3️⃣ Analysis**
        
        Compare against CGHS rates
        """)
    
    with col4:
        st.markdown("""
        **4️⃣ Report**
        
        Get detailed violation report
        """)
    
    st.markdown("---")
    
    # Quick stats
    if check_backend_health():
        stats = get_statistics()
        if stats:
            st.subheader("📊 Database Statistics")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Total CGHS Hospitals",
                    stats["hospitals"]["total"],
                    help="Number of CGHS-empanelled hospitals in database"
                )
            
            with col2:
                st.metric(
                    "NABH Accredited",
                    stats["hospitals"]["nabh"],
                    f"{(stats['hospitals']['nabh'] / stats['hospitals']['total'] * 100):.1f}%"
                )
            
            with col3:
                st.metric(
                    "Procedure Rates",
                    stats["procedures"]["total"],
                    help="Number of CGHS package rates in database"
                )

# ============================================================================
# UPLOAD BILL PAGE
# ============================================================================

elif page == "📤 Upload Bill":
    st.title("📤 Upload & Analyze Medical Bill")
    
    if not check_backend_health():
        st.error("❌ Backend server is not running. Please start it first.")
        st.code("python backend.py", language="bash")
        st.stop()
    
    st.markdown("""
    Upload your medical bill image or PDF to get a comprehensive CGHS compliance analysis.
    
    **Supported formats:** JPG, PNG, WEBP, PDF
    """)
    
    uploaded_file = st.file_uploader(
        "Choose a bill file",
        type=['jpg', 'jpeg', 'png', 'webp', 'pdf'],
        help="Upload medical bill image or PDF"
    )
    
    if uploaded_file:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📄 Uploaded File")
            
            if uploaded_file.type.startswith('image'):
                st.image(uploaded_file, caption=uploaded_file.name, use_column_width=True)
            else:
                st.info(f"📄 PDF File: {uploaded_file.name}")
            
            st.write(f"**File size:** {uploaded_file.size / 1024:.2f} KB")
        
        with col2:
            st.subheader("⚙️ Processing Options")
            
            st.info("""
            **Analysis will include:**
            - Hospital CGHS empanelment check
            - NABH status detection
            - Package rate validation
            - BIS billing standard compliance
            - Price comparison with CGHS rates
            - Violation detection
            - Legal recommendations
            """)
        
        if st.button("🔍 Analyze Bill", type="primary", use_container_width=True):
            with st.spinner("🔄 Processing bill... This may take 30-60 seconds..."):
                result = analyze_bill(uploaded_file)
            
            if result and result.get("success"):
                st.success("✅ Analysis Complete!")
                
                # Extract data
                bill_data = result["extracted_bill_data"]
                hospital_match = result["hospital_match"]
                analysis = result["analysis"]
                
                st.markdown("---")
                
                # ============================================================
                # ANALYSIS RESULTS
                # ============================================================
                
                st.header("📊 Analysis Results")
                
                # Hospital Information
                st.subheader("🏥 Hospital Information")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Hospital", bill_data["hospital_name"])
                
                with col2:
                    if hospital_match["is_cghs_empanelled"]:
                        st.success(f"✅ CGHS Empanelled\n\n{hospital_match['nabh_status']}")
                    else:
                        st.warning("⚠️ Not CGHS Empanelled")
                
                with col3:
                    st.metric("Can File CGHS Complaint", 
                             "✅ Yes" if analysis["can_file_cghs_complaint"] else "❌ No")
                
                if hospital_match["hospital"]:
                    with st.expander("📍 Hospital Details"):
                        h = hospital_match["hospital"]
                        st.write(f"**Address:** {h['address']}")
                        st.write(f"**Contact:** {h['contact_no']}")
                        st.write(f"**NABH Status:** {h['nabh_status']}")
                
                st.markdown("---")
                
                # Bill Summary
                st.subheader("💰 Bill Summary")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Amount", f"₹{bill_data['total_amount']:,.2f}")
                
                with col2:
                    st.metric("Items", len(bill_data['items']))
                
                with col3:
                    if bill_data.get('advance_paid'):
                        st.metric("Advance Paid", f"₹{bill_data['advance_paid']:,.2f}")
                
                with col4:
                    if bill_data.get('bill_date'):
                        st.metric("Bill Date", bill_data['bill_date'])
                
                # Bill Items Table
                if bill_data['items']:
                    with st.expander("📋 View All Bill Items", expanded=False):
                        items_df = pd.DataFrame([
                            {
                                "Description": item["description"],
                                "Quantity": item.get("quantity", 1),
                                "Unit Price": f"₹{item.get('unit_price', 0):,.2f}" if item.get('unit_price') else "-",
                                "Total": f"₹{item['total_price']:,.2f}",
                                "Category": item.get("category", "Other")
                            }
                            for item in bill_data['items']
                        ])
                        st.dataframe(items_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # Risk Assessment
                st.subheader("⚠️ Risk Assessment")
                
                risk_color = {
                    "high": "🔴",
                    "medium": "🟠",
                    "low": "🟡",
                    "compliant": "🟢"
                }
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "Overall Risk",
                        f"{risk_color.get(analysis['overall_risk'], '⚪')} {analysis['overall_risk'].upper()}"
                    )
                
                with col2:
                    st.metric("Total Violations", analysis['total_violations'])
                
                with col3:
                    st.metric("High Severity", analysis['high_severity_count'])
                
                st.markdown("---")
                
                # Summary
                st.subheader("📝 Summary")
                
                if analysis['is_cghs_empanelled']:
                    if analysis['overall_risk'] == 'compliant':
                        st.success(analysis['summary'])
                    else:
                        st.error(analysis['summary'])
                else:
                    st.info(analysis['summary'])
                
                st.markdown("---")
                
                # Violations
                if analysis['violations']:
                    st.subheader("🚨 Violations Detected")
                    
                    for violation in analysis['violations']:
                        severity = violation['severity']
                        
                        if severity == 'high':
                            container = st.container()
                            with container:
                                st.markdown(f"""
                                <div class="violation-high">
                                    <strong>🔴 HIGH SEVERITY: {violation['description']}</strong><br>
                                    <small><strong>Legal Reference:</strong> {violation.get('legal_reference', 'N/A')}</small>
                                """, unsafe_allow_html=True)
                                
                                if violation.get('item'):
                                    st.write(f"**Item:** {violation['item']}")
                                if violation.get('charged_amount'):
                                    st.write(f"**Charged:** ₹{violation['charged_amount']:,.2f}")
                                if violation.get('expected_amount'):
                                    st.write(f"**CGHS Rate:** ₹{violation['expected_amount']:,.2f}")
                                if violation.get('deviation_percentage'):
                                    st.write(f"**Overcharge:** {violation['deviation_percentage']:.1f}%")
                                
                                st.markdown("</div>", unsafe_allow_html=True)
                        
                        elif severity == 'medium':
                            st.markdown(f"""
                            <div class="violation-medium">
                                <strong>🟠 MEDIUM: {violation['description']}</strong><br>
                                <small>{violation.get('legal_reference', '')}</small>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        else:
                            st.markdown(f"""
                            <div class="violation-info">
                                <strong>🔵 INFO: {violation['description']}</strong><br>
                                <small>{violation.get('legal_reference', '')}</small>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.success("✅ No violations detected!")
                
                st.markdown("---")
                
                # Price Comparisons
                if analysis['price_comparisons']:
                    st.subheader("💵 Price Comparison Analysis")
                    
                    # Charts
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig1 = create_price_comparison_chart(analysis['price_comparisons'])
                        if fig1:
                            st.plotly_chart(fig1, use_container_width=True)
                    
                    with col2:
                        fig2 = create_deviation_chart(analysis['price_comparisons'])
                        if fig2:
                            st.plotly_chart(fig2, use_container_width=True)
                    
                    # Detailed table
                    with st.expander("📊 View Detailed Price Comparison Table"):
                        comparison_df = pd.DataFrame([
                            {
                                "Item": pc["item"],
                                "Charged (₹)": f"{pc['charged_amount']:,.2f}",
                                "CGHS Rate (₹)": f"{pc['cghs_rate']:,.2f}" if pc['cghs_rate'] else "N/A",
                                "Deviation (%)": f"{pc['deviation_percentage']:.1f}%",
                                "Status": "⚠️ Abnormal" if pc['is_abnormal'] else "✅ Normal"
                            }
                            for pc in analysis['price_comparisons']
                        ])
                        st.dataframe(comparison_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # Recommendations
                if analysis.get('recommendations'):
                    st.subheader("💡 Recommendations")
                    
                    for i, rec in enumerate(analysis['recommendations'], 1):
                        st.info(f"**{i}.** {rec}")
                
                st.markdown("---")
                
                # Download Report
                st.subheader("📥 Download Report")
                
                report_json = json.dumps(result, indent=2)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        label="📄 Download JSON Report",
                        data=report_json,
                        file_name=f"bill_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                
                with col2:
                    # Create text report
                    text_report = f"""
MEDICAL BILL ANALYSIS REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

HOSPITAL INFORMATION
Hospital: {bill_data['hospital_name']}
CGHS Status: {'Empanelled' if hospital_match['is_cghs_empanelled'] else 'Not Empanelled'}
NABH Status: {hospital_match['nabh_status']}

BILL SUMMARY
Total Amount: ₹{bill_data['total_amount']:,.2f}
Bill Number: {bill_data.get('bill_number', 'N/A')}
Bill Date: {bill_data.get('bill_date', 'N/A')}

RISK ASSESSMENT
Overall Risk: {analysis['overall_risk'].upper()}
Total Violations: {analysis['total_violations']}
High Severity: {analysis['high_severity_count']}

SUMMARY
{analysis['summary']}

VIOLATIONS
"""
                    for i, v in enumerate(analysis['violations'], 1):
                        text_report += f"{i}. [{v['severity'].upper()}] {v['description']}\n"
                    
                    st.download_button(
                        label="📝 Download Text Report",
                        data=text_report,
                        file_name=f"bill_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )

# ============================================================================
# HOSPITAL SEARCH PAGE
# ============================================================================

elif page == "🏥 Hospital Search":
    st.title("🏥 Search CGHS Hospitals")
    
    if not check_backend_health():
        st.error("❌ Backend server is not running.")
        st.stop()
    
    st.markdown("Search and explore CGHS-empanelled hospitals in the database.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        search_query = st.text_input(
            "🔍 Search by hospital name",
            placeholder="Enter hospital name...",
            help="Search for hospitals by name"
        )
    
    with col2:
        nabh_filter = st.checkbox("Show only NABH hospitals", value=False)
    
    if st.button("🔍 Search", use_container_width=True):
        with st.spinner("Searching..."):
            results = search_hospitals(nabh_only=nabh_filter, name_query=search_query if search_query else None)
        
        if results:
            st.success(f"Found {results['total_count']} hospitals")
            
            # Statistics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Results", results['total_count'])
            
            with col2:
                st.metric("NABH Hospitals", results['nabh_count'])
            
            with col3:
                st.metric("Non-NABH Hospitals", results['non_nabh_count'])
            
            st.markdown("---")
            
            # Display hospitals
            if results['hospitals']:
                for hospital in results['hospitals']:
                    with st.expander(f"🏥 {hospital['hospital_name']}", expanded=False):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.write(f"**Address:** {hospital['address']}")
                            st.write(f"**Contact:** {hospital['contact_no']}")
                        
                        with col2:
                            if hospital['nabh_status'] == 'NABH/ NABL':
                                st.success("✅ NABH Accredited")
                            else:
                                st.info("📋 Non-NABH")
            else:
                st.warning("No hospitals found matching your criteria.")
    
    else:
        # Show all hospitals by default
        st.subheader("📊 All CGHS Hospitals")
        
        with st.spinner("Loading hospitals..."):
            results = search_hospitals()
        
        if results:
            # Statistics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Hospitals", results['total_count'])
            
            with col2:
                st.metric("NABH Accredited", results['nabh_count'])
            
            with col3:
                st.metric("Non-NABH", results['non_nabh_count'])
            
            # Create DataFrame
            if results['hospitals']:
                df = pd.DataFrame([
                    {
                        "Hospital Name": h['hospital_name'],
                        "Address": h['address'][:50] + "..." if len(h['address']) > 50 else h['address'],
                        "NABH Status": h['nabh_status'],
                        "Contact": h['contact_no']
                    }
                    for h in results['hospitals'][:50]  # Show first 50
                ])
                
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                if results['total_count'] > 50:
                    st.info(f"Showing 50 of {results['total_count']} hospitals. Use search to filter.")

# ============================================================================
# ANALYTICS PAGE
# ============================================================================

elif page == "📊 Analytics":
    st.title("📊 System Analytics")
    
    if not check_backend_health():
        st.error("❌ Backend server is not running.")
        st.stop()
    
    stats = get_statistics()
    
    if stats:
        # Overview metrics
        st.subheader("📈 Database Overview")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Hospitals", stats["hospitals"]["total"])
        
        with col2:
            st.metric("NABH Hospitals", stats["hospitals"]["nabh"])
        
        with col3:
            st.metric("Procedure Rates", stats["procedures"]["total"])
        
        st.markdown("---")
        
        # NABH Distribution
        st.subheader("🏥 Hospital Distribution")
        
        fig = go.Figure(data=[go.Pie(
            labels=['NABH', 'Non-NABH'],
            values=[stats["hospitals"]["nabh"], stats["hospitals"]["non_nabh"]],
            hole=.3,
            marker_colors=['#4caf50', '#ff9800']
        )])
        
        fig.update_layout(
            title="NABH vs Non-NABH Distribution",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        
        # System Status
        st.subheader("🔧 System Status")
        
        health = requests.get(f"{API_BASE_URL}/api/v1/health").json()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Services Status:**")
            for service, status in health["services"].items():
                if status:
                    st.success(f"✅ {service.replace('_', ' ').title()}")
                else:
                    st.error(f"❌ {service.replace('_', ' ').title()}")
        
        with col2:
            st.write("**Data Loaded:**")
            st.info(f"🏥 Hospitals: {health['data_loaded']['hospitals']}")
            st.info(f"💊 Procedures: {health['data_loaded']['rates']}")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem;'>
    <p><strong>Medical Bill Analyzer</strong> v2.0</p>
    <p>Powered by Google Cloud Vision OCR + Gemini 2.0 Flash</p>
    <p>© 2024 | CGHS Compliance Analysis System</p>
</div>
""", unsafe_allow_html=True)