import streamlit as st
import fitz  # PyMuPDF
import re
import urllib.parse

st.title("Soil Test Fertilizer Calculator")

uploaded_file = st.file_uploader("Upload Soil Test PDF", type="pdf")

# ---------------- helpers ----------------
def clean_num(x):
    try:
        return float(x)
    except:
        return 0.0

def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")

def extract_num_after_label(block: str, label_regex: str) -> float:
    pats = [
        rf"{label_regex}[^:\n]*:\s*([0-9.]+)\s*l(?:b|bs)\b",
        rf"{label_regex}.*?([0-9.]+)\s*l(?:b|bs)\b",
    ]
    for p in pats:
        m = re.search(p, block, flags=re.IGNORECASE)
        if m:
            return clean_num(m.group(1))
    return 0.0

# ---------- Unit detection (explicit text first, crop fallback) ----------
def detect_unit(text: str, crop_name: str):
    """
    Returns (unit_string, source_string)
    Explicit text beats crop heuristic.
    """
    t = (text or "").lower()

    def has(pat: str) -> bool:
        return re.search(pat, t, flags=re.IGNORECASE) is not None

    # Accept "sq ft", "sq. ft.", "sq.ft", "sqft"
    if has(r"per\s+1[, ]?000\s*(?:sq\.?\s*ft\.?|sqft)"):
        return "per 1,000 sq ft", "detected from report text"
    if has(r"per\s+100\s*(?:sq\.?\s*ft\.?|sqft)"):
        return "per 100 sq ft", "detected from report text"
    if has(r"per\s+acre"):
        return "per acre", "detected from report text"

    cl = (crop_name or "").lower()
    if any(w in cl for w in ["vegetable garden", "vegetable", "garden"]):
        return "per 100 sq ft", "based on crop type"
    if any(w in cl for w in ["lawn", "turf", "st. augustine", "zoysia"]):
        return "per 1,000 sq ft", "based on crop type"
    if any(w in cl for w in ["bahia", "bahiagrass", "pasture", "hay", "silage", "perennial grass", "bermudagrass", "forage", "producer"]):
        return "per acre", "based on crop type"

    return "per acre", "default"

# ---------- Lime detection ----------
def _normalize_unit_token(u: str) -> str | None:
    if not u: 
        return None
    u = u.lower()
    if "acre" in u or u.strip() in ("ac",):
        return "per acre"
    if "1,000" in u or "1000" in u:
        return "per 1,000 sq ft"
    if "100" in u:
        return "per 100 sq ft"
    if "sq" in u and "ft" in u:  # generic sq ft without quantity -> leave None
        return None
    return None

def extract_lime(block: str, default_unit: str):
    """
    Returns tuple: (lime_value_float, unit_string, found_anything_bool, explicit_bool, no_lime_bool)
    - explicit_bool means unit was captured from the text itself.
    - no_lime_bool means text explicitly said no lime needed.
    """
    t = block

    # Explicit "no lime" phrases
    if re.search(r"\b(no\s+lime\s+(?:needed|required|recommended)|lime\s+not\s+required)\b", t, re.IGNORECASE):
        return 0.0, default_unit, True, False, True

    # Patterns with captured unit
    pats_with_unit = [
        r"Lime(?:\s*(?:Requirement|Req\.?)\s*)?[^:\n]*:\s*([0-9.]+)\s*l(?:b|bs)\s*(?:of\s+lime\s*)?(?:per|/)\s*([A-Za-z0-9 ,._]+)",
        r"Apply\s*([0-9.]+)\s*l(?:b|bs)\s*(?:of\s+)?(?:agricultural\s+)?lime\s*(?:per|/)\s*([A-Za-z0-9 ,._]+)",
    ]
    for p in pats_with_unit:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            val = clean_num(m.group(1))
            raw_u = (m.group(2) or "").strip()
            unit = _normalize_unit_token(raw_u) or default_unit
            return val, unit, True, True, False

    # Numeric lime with no explicit unit -> use default unit
    pats_no_unit = [
        r"Lime(?:\s*(?:Requirement|Req\.?)\s*)?[^:\n]*:\s*([0-9.]+)\s*l(?:b|bs)\b",
        r"Apply\s*([0-9.]+)\s*l(?:b|bs)\s*(?:of\s+)?(?:agricultural\s+)?lime\b",
    ]
    for p in pats_no_unit:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            val = clean_num(m.group(1))
            return val, default_unit, True, False, False

    # Nothing found
    return 0.0, default_unit, False, False, False

# ---------- Generic extractors (non-Bahia) ----------
def extract_generic_nutrient(text: str, label: str) -> float:
    patterns = [
        rf"{label}\s*\([^)]*\)\s*:\s*([0-9.]+)\s*l(?:b|bs)\b",
        rf"{label}[^:\n]*:\s*([0-9.]+)\s*l(?:b|bs)\b",
        rf"{label}.*?\s([0-9.]+)\s*l(?:b|bs)\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
    return 0.0

# ---------- Bahia-specific bits (parsing only; UI stays the same) ----------
def extract_bahia_n(block: str) -> float:
    pats = [
        r"Nitrogen\s*\(\s*N\s*\)\s*:\s*Apply\s*([0-9.]+)\s*l(?:b|bs)\s+of\s+Nitrogen\s+per\s+Acre",
        r"Nitrogen\s*\(\s*N\s*\)\s*:\s*([0-9.]+)\s*l(?:b|bs)\s+per\s+acre",
        r"(?:Apply\s*)?([0-9.]+)\s*l(?:b|bs)\s*(?:of\s*)?(?:Nitrogen|N)\b.*per\s+acre",
    ]
    for p in pats:
        m = re.search(p, block, flags=re.IGNORECASE)
        if m:
            return clean_num(m.group(1))
    return extract_num_after_label(block, r"Nitrogen\s*\(\s*N\s*\)")

def extract_p_bahia(block: str) -> float:
    if re.search(r"no\s+P\s+recommendation", block, re.IGNORECASE):
        return 0.0
    pats = [
        r"Phosphorus\s*\(\s*P(?:2O5|₂O₅)\s*\)\s*:\s*([0-9.]+)\s*l(?:b|bs)\b",
        r"(?:P2O5|P₂O₅)[^:\n]*:\s*([0-9.]+)\s*l(?:b|bs)\b",
    ]
    for p in pats:
        m = re.search(p, block, flags=re.IGNORECASE)
        if m:
            return clean_num(m.group(1))
    return 0.0

def extract_mg(block: str) -> float:
    return extract_num_after_label(block, r"Magnesium\s*\(\s*Mg\s*\)")

# ---------- Robust sample splitter (avoids false multiples) ----------
def _find_crop(text: str) -> str:
    m = re.search(r"Crop:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    return m.group(1).strip() if m else "Unknown"

def split_samples(pdf_text: str):
    """
    Split by 'Client Identification ... Lab Number ...' or
    'Sample Number ... Lab Number ...'. Fallback = whole doc.
    """
    pat = re.compile(
        r"(Client Identification:.*?Lab Number:\s*\S+)|(Sample Number:.*?Lab Number:\s*\S+)",
        flags=re.IGNORECASE | re.DOTALL
    )
    matches = list(pat.finditer(pdf_text))
    if not matches:
        return [{"label": "Sample", "crop": _find_crop(pdf_text), "text": pdf_text}]

    blocks = []
    for i, m in enumerate(matches):
        s = m.start()
        e = matches[i+1].start() if i+1 < len(matches) else len(pdf_text)
        block = pdf_text[s:e]
        label = None
        m1 = re.search(r"Client Identification:\s*(.+?)\s+Set Number:\s*([A-Z0-9-]+)\s+Lab Number:\s*([A-Z0-9-]+)", block, re.IGNORECASE)
        if m1:
            label = f"{m1.group(1).strip()} | Set {m1.group(2)} | Lab {m1.group(3)}"
        else:
            m2 = re.search(r"Sample Number:\s*([0-9-]+).*?Lab Number:\s*([A-Z0-9-]+)", block, re.IGNORECASE | re.DOTALL)
            if m2:
                label = f"Sample {m2.group(1)} | Lab {m2.group(2)}"
        blocks.append({"label": label or f"Sample {i+1}", "crop": _find_crop(block), "text": block})
    return blocks

# ---------------- main ----------------
if uploaded_file:
    pdf_text = ""
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            pdf_text += page.get_text()

    samples = split_samples(pdf_text)

    # Dropdown only if >1
    if len(samples) > 1:
        choice = st.selectbox("Select sample in this PDF:", [s["label"] for s in samples])
        sample = next(s for s in samples if s["label"] == choice)
    else:
        sample = samples[0]

    block = sample["text"]
    crop_name = sample["crop"]
    unit, unit_src = detect_unit(block, crop_name)

    # Parse nutrients (Bahia gets special N; everything else generic)
    bahia = "bahia" in crop_name.lower()
    if bahia:
        n_rec = extract_bahia_n(block) or 80.0  # safety net
        p_rec = extract_p_bahia(block)
        k_rec = extract_generic_nutrient(block, "Potassium")  # numeric if present
        mg_rec = extract_mg(block)
    else:
        n_rec  = extract_generic_nutrient(block, "Nitrogen")
        p_rec  = extract_generic_nutrient(block, "Phosphorus")
        k_rec  = extract_generic_nutrient(block, "Potassium")
        mg_rec = extract_generic_nutrient(block, "Magnesium")

    # Old override for hay/silage/perennial grass
    nitrogen_override_note = None
    crop_lower = crop_name.lower()
    if any(term in crop_lower for term in ["hay", "silage", "perennial grass"]):
        if n_rec == 0.0:
            n_rec = 80.0
            nitrogen_override_note = "Standard N recommendation for hay; not based on soil test."

    # ----------- Display (old style) -----------
    st.subheader(f"Crop: {crop_name}")
    st.caption(f"Units shown {unit} — {unit_src}")

    if n_rec > 0: st.write(f"**Nitrogen (N):** {fmt(n_rec)} lbs {unit}")
    if nitrogen_override_note: st.caption(nitrogen_override_note)
    if p_rec > 0: st.write(f"**Phosphorus (P₂O₅):** {fmt(p_rec)} lbs {unit}")
    if k_rec > 0: st.write(f"**Potassium (K₂O):** {fmt(k_rec)} lbs {unit}")
    if mg_rec > 0: st.write(f"**Magnesium (Mg):** {fmt(mg_rec)} lbs {unit}")
    if all(v == 0 for v in [n_rec, p_rec, k_rec, mg_rec]):
        st.info("No nutrient additions recommended in the parsed report.")

    # ----------- Lime section -----------
    lime_val, lime_unit_used, lime_found, lime_explicit, lime_none = extract_lime(block, unit)
    st.markdown("---")
    st.subheader("Lime Recommendation")
    if lime_none or (lime_found and lime_val == 0):
        st.markdown("<span style='color:#1E88E5; font-weight:600;'>No lime needed.</span>", unsafe_allow_html=True)
    elif lime_found and lime_val > 0:
        st.markdown(
            f"<span style='color:#2E7D32; font-weight:700;'>Lime needed: {fmt(lime_val)} lbs {lime_unit_used}</span>",
            unsafe_allow_html=True
        )
    else:
        st.caption("No lime info found in this sample.")

    st.markdown("---")

    # ----------- Fertilizer Product Suggestions (old style) -----------
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
        return round(target / (pct / 100.0), 2)

    lbs_needed = {
        "N": calc_lbs_needed(n_rec, n_pct),
        "P": calc_lbs_needed(p_rec, p_pct),
        "K": calc_lbs_needed(k_rec, k_pct),
        "Mg": calc_lbs_needed(mg_rec, mg_pct),
    }

    st.write("### Fertilizer Application Recommendation:")
    any_line = False
    for nutrient, lbs in lbs_needed.items():
        if lbs > 0:
            any_line = True
            st.markdown(
                f"<span style='color:blue; font-size:20px; font-weight:bold;'>Apply {lbs} lbs of {selected_fert} {unit} for {nutrient}.</span>",
                unsafe_allow_html=True
            )
        elif fertilizers[selected_fert][{'N':0,'P':1,'K':2,'Mg':3}[nutrient]] > 0:
            # old inline note if product contains a nutrient that isn't needed
            st.write(f"No {nutrient} needed. {selected_fert} provides {nutrient}.")

    # Old-style summary: single rate that satisfies the largest requirement
    max_lbs = max(lbs_needed.values()) if any_line else 0.0
    if max_lbs > 0:
        st.markdown(
            f"<span style='color:orange; font-size:20px; font-weight:bold;'>Summary: "
            f"Apply {max_lbs} lbs of {selected_fert} {unit} to satisfy this soil report.</span>",
            unsafe_allow_html=True
        )

    st.success("Calculation Complete.")

    # ---------- Help me find this fertilizer (button that actually opens) ----------
    if selected_fert:
        query = urllib.parse.quote(
            selected_fert + " fertilizer site:amazon.com OR site:tractorsupply.com OR site:lowes.com OR site:homedepot.com"
        )
        url = f"https://www.google.com/search?q={query}"

        # Streamlit >= 1.32: link_button exists
        if hasattr(st, "link_button"):
            st.link_button("🔍 Help me find this fertilizer", url)
        else:
            # Fallback for older Streamlit
            from streamlit.components.v1 import html
            if st.button("🔍 Help me find this fertilizer"):
                html(f"<script>window.open('{url}', '_blank');</script>", height=0)
