import streamlit as st
import pandas as pd
import boto3
import uuid
import json
import os
import requests
import time
import plotly.express as px

# --- Page Configuration ---
st.set_page_config(
    page_title="ReviewLens AI",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- App State Management ---
if 'page' not in st.session_state:
    st.session_state.page = 'upload'
if 'job_id' not in st.session_state:
    st.session_state.job_id = None
if 'job_status' not in st.session_state:
    st.session_state.job_status = {}

# --- AWS Configuration using Streamlit Secrets ---
S3_BRONZE_BUCKET = "reviewlens-bronze-bucket-kevin"
GOLD_BUCKET_NAME = "reviewlens-gold-bucket-kevin"
API_URL = st.secrets.get("API_URL", "")

@st.cache_resource
def get_s3_client():
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
            region_name=st.secrets["AWS_DEFAULT_REGION"]
        )
        return s3
    except KeyError:
        st.error("AWS secrets not found in Streamlit configuration. Please add them.")
        return None

# =====================================================================================
# Backend Communication Functions
# =====================================================================================

def check_job_status(job_id):
    if not API_URL: return None
    try:
        response = requests.get(f"{API_URL}/status/{job_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error checking job status: {e}")
        return None

def trigger_stitcher(job_id):
    if not API_URL: return None
    try:
        payload = {"job_id": job_id}
        response = requests.post(f"{API_URL}/stitch", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error triggering finalization: {e}")
        return None

# =====================================================================================
# Data Loading for Results
# =====================================================================================
@st.cache_data(ttl=600)
def load_gold_data(job_id):
    """Loads the final Parquet file from the Gold S3 bucket."""
    gold_path = f"s3://{GOLD_BUCKET_NAME}/{job_id}.parquet"
    print(f"Loading data from: {gold_path}")
    try:
        df = wr.s3.read_parquet(path=gold_path)
        return df
    except Exception as e:
        st.error(f"Could not load the final report. It may not be ready yet. Error: {e}")
        return pd.DataFrame()
        
# =====================================================================================
# UI Rendering Functions
# =====================================================================================
def render_upload_page():
    st.title("Welcome to ReviewLens AI! 🚀")
    st.header("1. Upload Your Review Data")
    st.write("Upload a CSV file containing your customer reviews.")
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    if uploaded_file is not None:
        df_preview = pd.read_csv(uploaded_file, nrows=5)
        st.dataframe(df_preview, use_container_width=True)
        file_columns = df_preview.columns.tolist()
        st.header("2. Map Your Columns (Data Contract)")
        with st.form("mapping_form"):
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Required Fields")
                review_text_col = st.selectbox("Column with Review Text:", [None] + file_columns)
                rating_col = st.selectbox("Column with Rating:", [None] + file_columns)
                product_id_col = st.selectbox("Column with Product ID:", [None] + file_columns)
            with col2:
                st.subheader("Optional Fields")
                title_col = st.selectbox("Column with Review Title:", [None] + file_columns)
                age_col = st.selectbox("Column with Customer Age:", [None] + file_columns)
            submitted = st.form_submit_button("Start Analysis")
            if submitted:
                if not all([review_text_col, rating_col, product_id_col]):
                    st.error("Please map all 'Required Fields'.")
                else:
                    start_backend_pipeline(uploaded_file, locals())

def render_monitoring_page():
    st.title("Analysis in Progress... ⚙️")
    if st.session_state.job_id:
        job_id = st.session_state.job_id
        st.header(f"Job ID: `{job_id}`")
        status_text = st.empty()
        progress_bar = st.progress(0)
        status_details = st.expander("Show Raw Status", expanded=False)
        
        while True:
            status = check_job_status(job_id)
            if status:
                st.session_state.job_status = status
                processed = status.get('processed_batches', 0)
                total = status.get('total_batches', 1)
                progress_percentage = status.get('progress_percentage', 0)
                current_status = status.get('status', 'LOADING...')
                status_text.info(f"Status: **{current_status}** | Processed Batches: **{processed} / {total}**")
                progress_bar.progress(int(progress_percentage))
                with status_details: st.json(status)
                
                if current_status in ['PROCESSING_COMPLETE', 'COMPLETED', 'STITCHING_FAILED']:
                    break
            time.sleep(5)
        
        current_status = st.session_state.job_status.get('status')
        if current_status == 'PROCESSING_COMPLETE':
            if st.button("🔗 Generate Final Report"):
                with st.spinner("Finalizing results..."):
                    response = trigger_stitcher(job_id)
                    if response: st.rerun()
        
        if current_status == 'COMPLETED':
            st.balloons()
            st.success("Your report is ready!")
            if st.button("📊 View Results"):
                st.session_state.page = 'results'
                st.rerun()

    else:
        st.warning("No active job found.")

def render_results_page():
    """Renders the final results page with interactive charts."""
    st.title("Analysis Results 📊")
    job_id = st.session_state.get('job_id')
    
    if not job_id:
        st.warning("No job has been processed yet. Please go to the Upload page.")
        if st.button("Go to Upload"):
            st.session_state.page = 'upload'
            st.rerun()
        return

    st.header(f"Showing results for Job ID: `{job_id}`")
    df = load_gold_data(job_id)

    if not df.empty:
        # --- Sidebar Filters ---
        st.sidebar.header("Filters")
        
        # Sentiment Filter
        sentiment_options = ['All'] + df['sentiment_label'].unique().tolist()
        selected_sentiment = st.sidebar.selectbox("Filter by Sentiment", sentiment_options)

        # Age Filter (if Age column exists)
        if 'Age' in df.columns:
            min_age, max_age = int(df['Age'].min()), int(df['Age'].max())
            selected_age = st.sidebar.slider("Filter by Age", min_age, max_age, (min_age, max_age))
        
        # --- Filtering Logic ---
        filtered_df = df.copy()
        if selected_sentiment != 'All':
            filtered_df = filtered_df[filtered_df['sentiment_label'] == selected_sentiment]
        if 'Age' in df.columns:
            filtered_df = filtered_df[(filtered_df['Age'] >= selected_age[0]) & (filtered_df['Age'] <= selected_age[1])]

        # --- Display KPIs and Charts ---
        st.subheader("Key Metrics")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Reviews Analyzed", len(filtered_df))
        
        positive_percentage = 0
        if len(filtered_df) > 0:
            positive_percentage = (filtered_df['sentiment_label'] == 'POSITIVE').mean() * 100
        col2.metric("Positive Sentiment", f"{positive_percentage:.1f}%")
        
        avg_rating = 0
        if 'Rating' in filtered_df.columns and len(filtered_df) > 0:
            avg_rating = filtered_df['Rating'].mean()
        col3.metric("Average Rating", f"{avg_rating:.2f} ★")

        st.subheader("Sentiment Distribution")
        if not filtered_df.empty:
            fig = px.pie(filtered_df, names='sentiment_label', title='Sentiment Breakdown', color='sentiment_label',
                         color_discrete_map={'POSITIVE':'green', 'NEGATIVE':'red'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No data to display for the selected filters.")

        st.subheader("Data Explorer")
        st.dataframe(filtered_df, use_container_width=True)

    else:
        st.error("Could not load data for the specified job.")
        
def start_backend_pipeline(uploaded_file, column_map):
    s3_client = get_s3_client()
    job_id = str(uuid.uuid4())
    column_mapping = {"Review Text": column_map.get("review_text_col"), "Rating": column_map.get("rating_col"), "Clothing ID": column_map.get("product_id_col"), "Title": column_map.get("title_col"), "Age": column_map.get("age_col")}
    metadata = {"job_id": job_id, "column_mapping": json.dumps({k: v for k, v in column_mapping.items() if v is not None})}
    with st.spinner(f"Uploading file and starting job {job_id}..."):
        try:
            uploaded_file.seek(0)
            s3_client.put_object(Bucket=S3_BRONZE_BUCKET, Key=f"{job_id}/{uploaded_file.name}", Body=uploaded_file, Metadata=metadata)
            st.success(f"Job {job_id} started successfully!")
            st.session_state.job_id = job_id
            st.session_state.page = 'monitoring'
            st.rerun()
        except Exception as e:
            st.error(f"Failed to upload file to S3. Please check app secrets and IAM permissions.")
            st.error(f"Details: {e}")

# --- Page Router ---
if 'page' not in st.session_state:
    st.session_state.page = 'upload'

if st.session_state.page == 'upload':
    render_upload_page()
elif st.session_state.page == 'monitoring':
    render_monitoring_page()
elif st.session_state.page == 'results':
    render_results_page()
else:
    render_upload_page()