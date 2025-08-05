import streamlit as st
import fitz  # PyMuPDF
import re

st.set_page_config(page_title="Stacy's Fertilizer Calculator", page_icon="🌱", layout="centered")
st.title("Stacy's Fertilizer Calculator with Fertilizer Dropdowns")

st.markdown("""
<div style='color: #fa4616; font-weight: bold; font-size: 20px;'>Welcome!</div>
<div style='font-size:16px;'>Upload a soil test PDF. Select fertilizer products to see application needs.</div>
<br>
""", unsafe_allow_html=True)

pdf_file = st.file_uploader("Upload your soil test report (PDF)", type=["pdf"])

if pdf_file:
    st.success(f"File uploaded: {pdf_file.name}")
    try:
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        all_text = ""
        for page in doc:
            all_text += page.get_text() + "\n"
        all_text = all_text.replace("\n", " ")
        st.text_area("Extracted PDF Text", all_text, height=300)

        st.markdown("<div style='color:#fa4616;'>Parsing nutrient values...</div>", unsafe_allow_html=True)

        unit_match = re.search(r"per (\d+\s*sq\.*\s*ft)", all_text.lower())
        if unit_match:
            raw_unit = unit_match.group(1).replace(" ", "").replace("sq.ft", "sq ft").strip()
            unit = raw_unit
        else:
            unit = "acre"

        n_match_home = re.search(r"Nitrogen\(N\):\s*(\d+\.?\d*) lbs per .*?", all_text)
        n_match_farm = re.search(r"Apply (\d+\.?\d*) lbs of Nitrogen per Acre", all_text)
        n = float(n_match_home.group(1)) if n_match_home else (float(n_match_farm.group(1)) if n_match_farm else 0)

        p_match = re.search(r"Phosphorus\(P2O5\):\s*(\d+\.?\d*) lbs per .*?", all_text)
        k_match = re.search(r"Potassium\(K2O\):\s*(\d+\.?\d*) lbs per .*?", all_text)
        mg_match = re.search(r"Magnesium\(Mg\):\s*(\d+\.?\d*) lbs per .*?", all_text)
        lime_match = re.search(r"Lime:\s*(\d+\.?\d*) lbs per .*?", all_text)

        p = float(p_match.group(1)) if p_match else 0
        k = float(k_match.group(1)) if k_match else 0
        mg = float(mg_match.group(1)) if mg_match else 0
        lime = float(lime_match.group(1)) if lime_match else 0

        st.markdown(f"<div style='color:#0021a5;'>Lime: {lime} lbs per {unit}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:#0021a5;'>Nitrogen: {n} lbs per {unit}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:#0021a5;'>Phosphorus: {p} lbs per {unit}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:#0021a5;'>Potassium: {k} lbs per {unit}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:#0021a5;'>Magnesium: {mg} lbs per {unit}</div>", unsafe_allow_html=True)

        st.markdown("<hr><div style='color:#fa4616;'>Select Fertilizer Products:</div>", unsafe_allow_html=True)
        fertilizer_options = {
    "10-10-10": (10, 10, 10, 0),
    "16-4-8": (16, 4, 8, 0),
    "Ammonium Nitrate (34-0-0)": (34, 0, 0, 0),
    "Ammonium Sulfate (21-0-0)": (21, 0, 0, 0),
    "Triple Superphosphate (0-46-0)": (0, 46, 0, 0),
    "Muriate of Potash (0-0-60)": (0, 0, 60, 0),
    "Epsom Salt (10% Mg)": (0, 0, 0, 10)
}
        selected_ferts = st.multiselect("Select fertilizers available", list(fertilizer_options.keys()), default=["10-10-10"])

        st.markdown("<div style='color:#fa4616;'>Fertilizer Recommendations:</div>", unsafe_allow_html=True)
        for fert in selected_ferts:
            comp = fertilizer_options[fert]
            if fert == "Epsom Salt (10% Mg)" and mg > 0:
                epsom_needed = round(mg / 10 * 100, 2)
                st.markdown(f"<div style='color:#0021a5; font-weight:bold;'>Epsom Salt: {epsom_needed} lbs per {unit}</div>", unsafe_allow_html=True)
            elif fert != "Epsom Salt (10% Mg)":
                n_pct, p_pct, k_pct = comp[0], comp[1], comp[2]
                needed = max(
                    n / (n_pct / 100) if n_pct > 0 else 0,
                    p / (p_pct / 100) if p_pct > 0 else 0,
                    k / (k_pct / 100) if k_pct > 0 else 0
                )
                needed = round(needed, 2)
                if needed > 0:
                    st.markdown(f"<div style='color:#0021a5; font-weight:bold;'>{fert}: {needed} lbs per {unit}</div>", unsafe_allow_html=True)

        if lime > 0:
            st.markdown(f"<div style='color:#0021a5;'>Apply {lime} lbs per {unit} of lime</div>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Error during PDF processing: {e}")
else:
    st.info("Please upload a PDF to continue.")