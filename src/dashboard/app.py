import streamlit as st
import pandas as pd
import boto3
import uuid
import json
import os
import requests
import time
from io import StringIO

# --- Page Configuration ---
st.set_page_config(
    page_title="ReviewLens AI",
    layout="wide"
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
API_URL = st.secrets["API_URL"]

@st.cache_resource
def get_s3_client():
    s3 = boto3.client(
        's3',
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_DEFAULT_REGION"]
    )
    return s3

# =====================================================================================
# Backend Communication Functions
# =====================================================================================

def check_job_status(job_id):
    """Calls the API Gateway to get the status of a specific job."""
    try:
        url = f"{API_URL}/status/{job_id}"
        print(f"Checking status at URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error checking job status: {e}")
        return None

def trigger_stitcher(job_id):
    """Calls the API Gateway to trigger the Stitcher Lambda."""
    try:
        url = f"{API_URL}/stitch"
        print(f"Triggering stitcher at URL: {url}")
        payload = {"job_id": job_id}
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error triggering finalization: {e}")
        return None

# =====================================================================================
# UI Rendering Functions
# =====================================================================================

def render_upload_page():
    st.title("Welcome to ReviewLens AI! 🚀")
    st.header("1. Upload Your Review Data")
    st.write("Upload a CSV file containing your customer reviews.")

    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

    if uploaded_file is not None:
        try:
            df_preview = pd.read_csv(uploaded_file, nrows=5)
            st.write("File Preview:")
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
        except Exception as e:
            st.error(f"An error occurred while reading the file: {e}")

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
                with status_details:
                    st.json(status)
                
                if current_status in ['PROCESSING_COMPLETE', 'COMPLETED', 'STITCHING_FAILED']:
                    st.success("Batch processing complete! Ready to generate the final report.")
                    break
            
            time.sleep(5)
        
        if st.session_state.job_status.get('status') == 'PROCESSING_COMPLETE':
            if st.button("🔗 Generate Final Report"):
                with st.spinner("Finalizing results... This may take a minute."):
                    response = trigger_stitcher(job_id)
                    if response:
                        st.success("Stitching process started! The final report will be available shortly.")
                        time.sleep(5)
                        st.rerun()
                        
        if st.session_state.job_status.get('status') == 'COMPLETED':
             st.balloons()
             st.success("Your report is ready! (Next step: view results)")

    else:
        st.warning("No active job found.")

def start_backend_pipeline(uploaded_file, column_map):
    s3_client = get_s3_client()
    job_id = str(uuid.uuid4())
    
    column_mapping = {
        "Review Text": column_map.get("review_text_col"),
        "Rating": column_map.get("rating_col"),
        "Clothing ID": column_map.get("product_id_col"),
        "Title": column_map.get("title_col"),
        "Age": column_map.get("age_col"),
    }
    
    metadata = {
        "job_id": job_id,
        "column_mapping": json.dumps({k: v for k, v in column_mapping.items() if v is not None})
    }
    with st.spinner(f"Uploading file and starting job {job_id}..."):
        try:
            uploaded_file.seek(0)
            s3_client.put_object(
                Bucket=S3_BRONZE_BUCKET,
                Key=f"{job_id}/{uploaded_file.name}",
                Body=uploaded_file,
                Metadata=metadata
            )
            st.success(f"Job {job_id} started successfully!")
            st.session_state.job_id = job_id
            st.session_state.page = 'monitoring'
            st.rerun()
        except Exception as e:
            st.error(f"Failed to upload file to S3. Please check app secrets and IAM permissions.")
            st.error(f"Details: {e}")

# --- Page Router ---
if st.session_state.page == 'upload':
    render_upload_page()
elif st.session_state.page == 'monitoring':
    render_monitoring_page()
else:
    render_upload_page()
