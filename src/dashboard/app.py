import streamlit as st
import pandas as pd
import boto3
import uuid
import json
import os
from io import StringIO

# --- Page Configuration ---
st.set_page_config(
    page_title="ReviewLens AI",
    layout="wide"
)

# --- App State Management ---
# Use session_state to remember variables across reruns
if 'page' not in st.session_state:
    st.session_state.page = 'upload'
if 'job_id' not in st.session_state:
    st.session_state.job_id = None

# --- AWS Configuration ---
# Cache the S3 client for performance
@st.cache_resource
def get_s3_client():
    # In a real production app, you would configure credentials securely
    return boto3.client('s3')

# IMPORTANT: Use your exact bucket name
S3_BRONZE_BUCKET = "reviewlens-bronze-bucket-kevin" 

# =====================================================================================
# UI Rendering Functions
# =====================================================================================

def render_upload_page():
    """Renders the UI for file upload and column mapping."""
    st.title("Welcome to ReviewLens AI! 🚀")
    st.header("1. Upload Your Review Data")
    st.write("Upload a CSV file containing customer reviews. The file must contain columns for the review text and a numeric rating.")

    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

    if uploaded_file is not None:
        try:
            # Read only the first few rows to get column headers
            df_preview = pd.read_csv(uploaded_file, nrows=5)
            st.write("File Preview:")
            st.dataframe(df_preview, use_container_width=True)
            
            file_columns = df_preview.columns.tolist()

            st.header("2. Map Your Columns (Data Contract)")
            st.write("Tell us which of your columns correspond to our required fields.")

            with st.form("mapping_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Required Fields")
                    # Use a 'None' option and set it as default
                    review_text_col = st.selectbox("Column with Review Text:", [None] + file_columns)
                    rating_col = st.selectbox("Column with Rating (1-5):", [None] + file_columns)

                with col2:
                    st.subheader("Optional Fields (improves analysis)")
                    title_col = st.selectbox("Column with Review Title:", [None] + file_columns)
                    age_col = st.selectbox("Column with Customer Age:", [None] + file_columns)
                    department_col = st.selectbox("Column with Department Name:", [None] + file_columns)
                    class_col = st.selectbox("Column with Class Name:", [None] + file_columns)

                submitted = st.form_submit_button("Start Analysis")

                if submitted:
                    if not review_text_col or not rating_col:
                        st.error("Please map all 'Required Fields' before starting the analysis.")
                    else:
                        start_backend_pipeline(uploaded_file, review_text_col, rating_col, title_col, age_col, department_col, class_col)

        except Exception as e:
            st.error(f"An error occurred while reading the file: {e}")

def render_monitoring_page():
    """Renders the UI for monitoring job progress."""
    st.title("Analysis in Progress... ⚙️")
    
    if st.session_state.job_id:
        st.header(f"Job ID: `{st.session_state.job_id}`")
        st.write("Your file is being processed. The status will update automatically below.")
        
        st.info("The monitoring UI with the progress bar will be built here.")
        
        if st.button("Start a New Analysis"):
            st.session_state.page = 'upload'
            st.session_state.job_id = None
            st.rerun()
    else:
        st.warning("No active job found. Please upload a file to start.")
        if st.button("Go to Upload Page"):
            st.session_state.page = 'upload'
            st.rerun()

def start_backend_pipeline(uploaded_file, review_text_col, rating_col, title_col, age_col, department_col, class_col):
    """Generates a job ID and uploads the file to S3 with metadata."""
    s3_client = get_s3_client()
    job_id = str(uuid.uuid4())
    
    column_mapping = {
        "Review Text": review_text_col,
        "Rating": rating_col,
        "Title": title_col,
        "Age": age_col,
        "Department Name": department_col,
        "Class Name": class_col
    }
    
    # Filter out None values from the mapping
    metadata = {
        "job_id": job_id,
        "column_mapping": json.dumps({k: v for k, v in column_mapping.items() if v is not None})
    }

    with st.spinner(f"Uploading file and starting job {job_id}..."):
        try:
            # Rewind file to the beginning before uploading
            uploaded_file.seek(0)
            s3_client.put_object(
                Bucket=S3_BRONZE_BUCKET,
                Key=f"{job_id}/{uploaded_file.name}", # Use job_id as a prefix for organization
                Body=uploaded_file,
                Metadata=metadata
            )
            st.success(f"Job {job_id} started successfully!")
            st.info("Redirecting to the monitoring page...")
            
            st.session_state.job_id = job_id
            st.session_state.page = 'monitoring'
            st.rerun()
        except Exception as e:
            st.error("Failed to upload file to S3. Check your local AWS credentials and permissions.")
            st.error(f"Details: {e}")

# --- Page Router ---
if st.session_state.page == 'upload':
    render_upload_page()
elif st.session_state.page == 'monitoring':
    render_monitoring_page()
else:
    render_upload_page()