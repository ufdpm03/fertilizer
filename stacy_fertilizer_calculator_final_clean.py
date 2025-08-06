import streamlit as st
import fitz  # PyMuPDF
import re

st.title("Soil Test Fertilizer Calculator")

uploaded_file = st.file_uploader("Upload Soil Test PDF", type="pdf")

if uploaded_file:
    pdf_text = ""
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            pdf_text += page.get_text()

    # Extract crop name
    crop_match = re.search(r"Crop:\s*(.+?)\n", pdf_text)
    crop_name = crop_match.group(1).strip() if crop_match else "Unknown"

    # Determine unit based on crop type
    crop_lower = crop_name.lower()
    if any(term in crop_lower for term in ["lawn", "turf"]):
        unit = "per 1,000 sq ft"
    elif "vegetable" in crop_lower:
        unit = "per 100 sq ft"
    else:
        unit = "per acre"

    # Improved nutrient extraction with multiple patterns
    def extract_nutrient(nutrient, text):
        patterns = [
            fr"{nutrient}\(.*?\):\s*([0-9.]+)\s*lbs",  # pattern 1
            fr"{nutrient}.*?:\s*([0-9.]+)\s*lbs",       # pattern 2
            fr"{nutrient}.*?\s+([0-9.]+)\s+lbs",        # pattern 3
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return 0.0

    n_rec = extract_nutrient("Nitrogen", pdf_text)
    p_rec = extract_nutrient("Phosphorus", pdf_text)
    k_rec = extract_nutrient("Potassium", pdf_text)
    mg_rec = extract_nutrient("Magnesium", pdf_text)

    # Auto override for hay or silage nitrogen recommendation
    nitrogen_override_note = None
    if any(term in crop_lower for term in ["hay", "silage", "perennial grass"]):
        if n_rec == 0.0:
            n_rec = 80.0
            nitrogen_override_note = "Standard N recommendation for hay; not based on soil test."

    st.subheader("Crop: " + crop_name)

    st.write(f"**Nitrogen (N):** {n_rec} lbs {unit}")
    if nitrogen_override_note:
        st.caption(nitrogen_override_note)

    st.write(f"**Phosphorus (P₂O₅):** {p_rec} lbs {unit}")
    st.write(f"**Potassium (K₂O):** {k_rec} lbs {unit}")
    st.write(f"**Magnesium (Mg):** {mg_rec} lbs {unit}")

    st.markdown("---")

    st.subheader("Fertilizer Product Suggestions")
    fertilizers = {
        "16-4-8": (16, 4, 8, 0),
        "8-8-8": (8, 8, 8, 0),
        "10-10-10": (10, 10, 10, 0),
        "Ammonium Nitrate (34-0-0)": (34, 0, 0, 0),
        "Ammonium Sulfate (21-0-0)": (21, 0, 0, 0),
        "Triple Superphosphate (0-45-0)": (0, 45, 0, 0),
        "Muriate of Potash (0-0-60)": (0, 0, 60, 0),
        "K-Mag (0-0-22-11Mg)": (0, 0, 22, 11),
        "Epsom Salt (0-0-0-10Mg)": (0, 0, 0, 10),
    }

    selected_fert = st.selectbox("Select a Fertilizer Product:", list(fertilizers.keys()))

    n_pct, p_pct, k_pct, mg_pct = fertilizers[selected_fert]

    def calc_lbs_needed(target, pct):
        if pct == 0 or target == 0:
            return 0.0
        return round(target / (pct / 100), 2)

    lbs_needed = {
        "N": calc_lbs_needed(n_rec, n_pct),
        "P": calc_lbs_needed(p_rec, p_pct),
        "K": calc_lbs_needed(k_rec, k_pct),
        "Mg": calc_lbs_needed(mg_rec, mg_pct),
    }

    pct_dict = {"N": n_pct, "P": p_pct, "K": k_pct, "Mg": mg_pct}

    st.write("### Fertilizer Application Recommendation:")
    for nutrient, lbs in lbs_needed.items():
        if lbs > 0:
            st.markdown(f"<span style='color:blue; font-size:20px; font-weight:bold;'>Apply {lbs} lbs of {selected_fert} {unit} for {nutrient}.</span>", unsafe_allow_html=True)
        elif pct_dict[nutrient] > 0:
            st.write(f"No {nutrient} needed. {selected_fert} provides {nutrient}.")

    st.success("Calculation Complete.")
