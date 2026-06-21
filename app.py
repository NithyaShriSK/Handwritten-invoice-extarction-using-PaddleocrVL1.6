import streamlit as st
import json
import tempfile
from PIL import Image

from ocr_engine import run_ocr_pipeline


# =============================
# PAGE CONFIG
# =============================

st.set_page_config(
    page_title="AI Invoice OCR",
    page_icon="📄",
    layout="wide"
)


# =============================
# STYLE
# =============================

st.markdown(
"""
<style>

.main{
background:#f5f7fb;
}

h1{
color:#1f4e79;
}

.stButton button{
background:#1f77b4;
color:white;
border-radius:10px;
height:45px;
font-size:18px;
}

</style>
""",
unsafe_allow_html=True
)



# =============================
# HEADER
# =============================

st.title("📄 AI Invoice OCR System")

st.write(
"""
PaddleOCR-VL 1.6 + LLaMA3 Invoice Extraction
"""
)



# =============================
# UPLOAD IMAGE
# =============================

uploaded_file = st.file_uploader(
    "Upload Invoice",
    type=[
        "png",
        "jpg",
        "jpeg"
    ]
)



if uploaded_file:


    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".png"
    )


    temp_file.write(
        uploaded_file.getbuffer()
    )

    temp_file.close()


    image_path = temp_file.name



    col1, col2 = st.columns(2)



    with col1:

        st.subheader(
            "Invoice Preview"
        )


        img = Image.open(
            image_path
        )


        st.image(
            img,
            use_container_width=True
        )



    with col2:

        st.subheader(
            "OCR Engine"
        )


        if st.button(
            "🚀 Extract Invoice"
        ):


            with st.spinner(
                "Running PaddleOCR-VL + LLaMA3..."
            ):


                try:

                    result = run_ocr_pipeline(
                        image_path
                    )


                    st.session_state.data = result


                    st.success(
                        "Extraction Completed"
                    )


                except Exception as e:

                    st.error(
                        f"OCR Error : {e}"
                    )




# =============================
# RESULT EDITOR
# =============================


if "data" in st.session_state:


    data = st.session_state.data


    st.divider()


    st.header(
        "✏ Edit Extracted Data"
    )



    col1, col2 = st.columns(2)



    # =============================
    # LEFT COLUMN
    # =============================


    with col1:


        data["company_name"] = st.text_input(
            "Company Name",
            value=data.get(
                "company_name",
                ""
            )
        )


        data["company_gst_no"] = st.text_input(
            "Company GST",
            value=data.get(
                "company_gst_no",
                ""
            )
        )


        data["invoice_number"] = st.text_input(
            "Invoice Number",
            value=data.get(
                "invoice_number",
                ""
            )
        )


        data["invoice_date"] = st.text_input(
            "Invoice Date",
            value=data.get(
                "invoice_date",
                ""
            )
        )


        data["buyer_name"] = st.text_input(
            "Buyer Name",
            value=data.get(
                "buyer_name",
                ""
            )
        )


        data["buyer_gst_no"] = st.text_input(
            "Buyer GST",
            value=data.get(
                "buyer_gst_no",
                ""
            )
        )



    # =============================
    # RIGHT COLUMN
    # =============================


    with col2:


        # Total Amount

        try:
            total_val = float(
                data.get(
                    "total_amount",
                    0
                )
            )

        except:

            total_val = 0.0


        data["total_amount"] = st.number_input(
            "Total Amount",
            value=total_val
        )



        # CGST

        try:
            cgst_val = float(
                data.get(
                    "cgst_amount",
                    0
                )
            )

        except:

            cgst_val = 0.0


        data["cgst_amount"] = st.number_input(
            "CGST Amount",
            value=cgst_val
        )



        # SGST

        try:
            sgst_val = float(
                data.get(
                    "sgst_amount",
                    0
                )
            )

        except:

            sgst_val = 0.0


        data["sgst_amount"] = st.number_input(
            "SGST Amount",
            value=sgst_val
        )



        # IGST

        try:
            igst_val = float(
                data.get(
                    "igst_amount",
                    0
                )
            )

        except:

            igst_val = 0.0


        data["igst_amount"] = st.number_input(
            "IGST Amount",
            value=igst_val
        )



    # =============================
    # PRODUCTS TABLE
    # =============================


    st.subheader(
        "Products"
    )


    products = data.get(
        "products_list",
        []
    )


    if not isinstance(products, list):

        products = []



    data["products_list"] = st.data_editor(
        products,
        num_rows="dynamic"
    )



    st.session_state.data = data



    # =============================
    # DOWNLOAD JSON
    # =============================


    st.divider()


    final_json = json.dumps(
        data,
        indent=2,
        ensure_ascii=False
    )



    st.download_button(

        label="⬇ Download Final JSON",

        data=final_json,

        file_name="invoice_data.json",

        mime="application/json"

    )



    # =============================
    # DISPLAY JSON
    # =============================


    with st.expander(
        "View JSON"
    ):

        st.json(data)