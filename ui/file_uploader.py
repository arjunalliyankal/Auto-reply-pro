import os
import json
import streamlit as st
from ingestion.loader import load_document
from ingestion.image_extractor import extract_images_from_pdf   # NEW
from rag.vector_store import build_index
from ingestion.supported_formats import SUPPORTED_FORMATS


def render_file_uploader() -> bool:
    """
    Renders the business knowledge base upload panel.

    Returns:
        True if a new index was just built, False otherwise.
    """
    st.markdown("##  Business Knowledge Base")
    st.caption(
        "Upload your business documents. Supported formats: "
        + ", ".join(f"`{ext}`" for ext in SUPPORTED_FORMATS)
    )

    uploaded_files = st.file_uploader(
        "Upload your business documents",
        accept_multiple_files=True,
        type=[ext.lstrip(".") for ext in SUPPORTED_FORMATS],
        key="kb_uploader",
        label_visibility="collapsed",
    )

    built = False
    if uploaded_files:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"📄 {len(uploaded_files)} file(s) ready to process")
        with col2:
            if st.button("🔄 Build Knowledge Base", width="stretch"):
                os.makedirs("data/uploads", exist_ok=True)
                all_docs       = []
                all_image_meta = []   # NEW
                progress = st.progress(0, text="Processing documents…")
                for i, f in enumerate(uploaded_files):
                    path = f"data/uploads/{f.name}"
                    with open(path, "wb") as out:
                        out.write(f.getbuffer())
                    try:
                        docs = load_document(path)
                        all_docs.extend(docs)
                    except Exception as e:
                        st.warning(f"⚠️ Could not load `{f.name}`: {e}")

                    # NEW: extract images if it's a PDF
                    if f.name.lower().endswith(".pdf"):
                        try:
                            images = extract_images_from_pdf(path)
                            all_image_meta.extend(images)
                        except Exception as e:
                            st.warning(f"⚠️ Could not extract images from `{f.name}`: {e}")

                    progress.progress(
                        (i + 1) / len(uploaded_files),
                        text=f"Processing {f.name}…",
                    )
                if all_docs:
                    with st.spinner("Building FAISS text index…"):
                        build_index(all_docs)
                        
                    # PRESERVE MANUAL UPLOADS
                    if os.path.exists("data/image_metadata.json"):
                        with open("data/image_metadata.json", "r", encoding="utf-8") as f:
                            try:
                                old_meta = json.load(f)
                                manual_items = [m for m in old_meta if m.get("source_file") == "Manual Upload"]
                                all_image_meta.extend(manual_items)
                            except json.JSONDecodeError:
                                pass

                    with open("data/image_metadata.json", "w", encoding="utf-8") as f:
                        json.dump(all_image_meta, f, indent=2)
                    st.success(
                        f"✅ Knowledge base built: {len(uploaded_files)} file(s), "
                        f"{len(all_docs)} text chunk(s), "
                        f"{len(all_image_meta)} image(s) indexed for visual replies."
                    )
                    built = True
                else:
                    st.error("❌ No documents could be loaded. Please check your files.")
                progress.empty()

    return built
