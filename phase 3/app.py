
from pathlib import Path
from io import BytesIO
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "framingham_cleaned.csv"
MODEL_FILE = BASE_DIR / "logistic_model.pkl"

FEATURES = [
    "male", "age", "education", "currentSmoker", "cigsPerDay",
    "BPMeds", "prevalentStroke", "prevalentHyp", "diabetes",
    "totChol", "sysBP", "diaBP", "BMI", "heartRate", "glucose"
]

st.set_page_config(
    page_title="Heart Disease Risk Predictor",
    page_icon="+",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------- UI --------------------
st.markdown("""
<style>
.stApp {
    background: #f7f9fc;
}
.block-container {
    max-width: 1180px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

/* Hero */
.hero {
    padding: 2rem 2.2rem;
    border-radius: 18px;
    background: linear-gradient(135deg, #102a43 0%, #1f4e79 100%);
    color: white;
    margin-bottom: 1.4rem;
    box-shadow: 0 12px 32px rgba(16,42,67,.16);
}
.hero h1 {
    margin: 0 0 .45rem 0;
    font-size: 2.05rem;
    line-height: 1.2;
    font-weight: 750;
}
.hero p {
    margin: 0;
    color: #dce9f5;
    font-size: 1rem;
}
.medical-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    margin-right: 9px;
    border-radius: 9px;
    background: rgba(255,255,255,.16);
    border: 1px solid rgba(255,255,255,.28);
    color: #fff;
    font-size: 1.4rem;
    font-weight: 800;
    vertical-align: 2px;
}

/* Section */
.section-title {
    color: #102a43 !important;
    font-size: 1.1rem;
    font-weight: 750;
    margin: .6rem 0 1rem;
    padding-bottom: .55rem;
    border-bottom: 2px solid #d9e2ec;
}

/* Labels: explicit, high contrast */
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] * {
    opacity: 1 !important;
}
[data-testid="stWidgetLabel"] p {
    color: #243b53 !important;
    font-weight: 650 !important;
    font-size: .88rem !important;
}

/* Number inputs: DON'T override Streamlit's internal buttons/layout */
[data-testid="stNumberInput"] {
    margin-bottom: .35rem;
}
[data-testid="stNumberInput"] input {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
[data-testid="stNumberInput"] button {
    color: #ffffff !important;
    opacity: 1 !important;
}
[data-testid="stNumberInput"] button svg {
    color: #ffffff !important;
    fill: #ffffff !important;
}

/* Select inputs */
[data-baseweb="select"] > div {
    border-radius: 10px !important;
    min-height: 42px;
}
[data-baseweb="select"] div {
    color: #ffffff !important;
}
[data-baseweb="select"] svg {
    color: #ffffff !important;
}

/* Prediction button */
.stButton > button {
    border-radius: 10px !important;
    min-height: 3.05rem !important;
    font-weight: 700 !important;
    font-size: .98rem !important;
}

/* Results */
.result-card {
    padding: 1.4rem;
    border-radius: 16px;
    background: #ffffff;
    border: 1px solid #d9e2ec;
    box-shadow: 0 8px 24px rgba(16,42,67,.07);
    text-align: center;
    min-height: 130px;
}
.risk-number {
    font-size: 2.8rem;
    font-weight: 800;
    color: #102a43;
    margin: .2rem 0;
}
.small-note {
    color: #627d98;
    font-size: .88rem;
}
.stDownloadButton > button {
    border-radius: 10px !important;
    min-height: 2.8rem !important;
    font-weight: 650 !important;
}
.footer {
    margin-top: 2rem;
    padding: 1rem 1.2rem;
    border-radius: 12px;
    background: #edf3f8;
    color: #52677a;
    font-size: .82rem;
    border: 1px solid #d9e2ec;
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_model():
    if MODEL_FILE.exists():
        return joblib.load(MODEL_FILE), "Loaded saved model"

    if not DATA_FILE.exists():
        raise FileNotFoundError("framingham_cleaned.csv was not found beside app.py.")

    df = pd.read_csv(DATA_FILE)
    X, y = df[FEATURES], df["TenYearCHD"]

    from sklearn.model_selection import train_test_split, GridSearchCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    X_train, _, y_train, _ = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("logreg", LogisticRegression(solver="liblinear", max_iter=1000))
    ])

    grid = GridSearchCV(
        pipe,
        {
            "logreg__C": [0.01, 0.1, 1, 10],
            "logreg__penalty": ["l1", "l2"],
        },
        cv=5,
        scoring="roc_auc",
        n_jobs=-1,
    )
    grid.fit(X_train, y_train)
    joblib.dump(grid.best_estimator_, MODEL_FILE)
    return grid.best_estimator_, "Trained and saved a new model"


def make_suggestions(values, probability):
    suggestions = []

    if values["currentSmoker"]:
        suggestions.append("Smoking: consider a structured smoking-cessation plan and discuss available support with a healthcare professional.")
    if values["sysBP"] >= 130 or values["diaBP"] >= 80:
        suggestions.append("Blood pressure: the entered values may warrant monitoring and discussion with a healthcare professional.")
    if values["totChol"] >= 200:
        suggestions.append("Cholesterol: consider discussing your lipid profile and heart-health goals with a healthcare professional.")
    if values["BMI"] >= 25:
        suggestions.append("Weight/activity: regular physical activity and balanced nutrition can support cardiovascular health.")
    if values["glucose"] >= 100 or values["diabetes"]:
        suggestions.append("Glucose/diabetes: consider regular monitoring and follow-up with a healthcare professional.")
    if values["BPMeds"] or values["prevalentHyp"]:
        suggestions.append("Blood-pressure history: continue prescribed treatment as directed and keep routine follow-up appointments.")

    if not suggestions:
        suggestions.append("Continue heart-healthy habits such as regular physical activity, balanced nutrition, avoiding tobacco, adequate sleep, and routine health check-ups.")

    if probability >= 0.20:
        suggestions.append("Because the model estimates a higher probability, consider sharing this report with a healthcare professional for proper clinical assessment.")
    else:
        suggestions.append("A lower model probability does not rule out heart disease. Continue routine preventive care and discuss personal risk factors with a healthcare professional.")

    return suggestions


def build_pdf(values, probability, prediction, suggestions):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=16*mm, leftMargin=16*mm,
        topMargin=15*mm, bottomMargin=15*mm
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=20, leading=24, textColor=colors.HexColor("#102a43"),
        spaceAfter=8
    )
    subtitle = ParagraphStyle(
        "SubtitleCustom", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=9, textColor=colors.HexColor("#627d98"), spaceAfter=18
    )
    heading = ParagraphStyle(
        "HeadingCustom", parent=styles["Heading2"],
        fontSize=13, leading=16, textColor=colors.HexColor("#102a43"),
        spaceBefore=10, spaceAfter=8
    )
    body = ParagraphStyle(
        "BodyCustom", parent=styles["BodyText"], fontSize=9.5,
        leading=14, spaceAfter=6
    )

    story = [
        Paragraph("Heart Disease Risk Prediction Report", title),
        Paragraph(
            f"Generated on {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
            subtitle
        ),
        Paragraph("Prediction Summary", heading),
    ]

    risk_text = f"{probability * 100:.1f}%"
    class_text = "Higher predicted risk (Class 1)" if prediction else "Lower predicted risk (Class 0)"

    summary = [
        ["Estimated 10-year CHD probability", risk_text],
        ["Model classification", class_text],
    ]
    table = Table(summary, colWidths=[95*mm, 75*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#edf3f8")),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#102a43")),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#d9e2ec")),
        ("PADDING", (0,0), (-1,-1), 9),
    ]))
    story += [table, Spacer(1, 8*mm)]

    labels = {
        "male": "Sex", "age": "Age", "education": "Education code",
        "currentSmoker": "Current smoker", "cigsPerDay": "Cigarettes/day",
        "BPMeds": "BP medication", "prevalentStroke": "Previous stroke",
        "prevalentHyp": "Hypertension", "diabetes": "Diabetes",
        "totChol": "Total cholesterol (mg/dL)", "sysBP": "Systolic BP (mmHg)",
        "diaBP": "Diastolic BP (mmHg)", "BMI": "BMI",
        "heartRate": "Heart rate (bpm)", "glucose": "Glucose (mg/dL)"
    }
    display = dict(values)
    display["male"] = "Male" if values["male"] else "Female"
    for key in ["currentSmoker", "BPMeds", "prevalentStroke", "prevalentHyp", "diabetes"]:
        display[key] = "Yes" if values[key] else "No"

    story.append(Paragraph("Entered Information", heading))
    rows = [["Measure", "Value"]] + [[labels[k], str(display[k])] for k in FEATURES]
    input_table = Table(rows, colWidths=[95*mm, 75*mm], repeatRows=1)
    input_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#102a43")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#d9e2ec")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story += [input_table, Spacer(1, 5*mm)]

    story.append(Paragraph("Practical Suggestions", heading))
    for suggestion in suggestions:
        story.append(Paragraph("• " + suggestion, body))

    story.append(Paragraph("Important Disclaimer", heading))
    story.append(Paragraph(
        "This report is generated by an academic machine-learning model using the Framingham "
        "dataset. It is not a clinical diagnosis and does not replace a qualified healthcare professional.",
        body
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


try:
    model, model_status = get_model()
except Exception as exc:
    st.error(f"Unable to load the model: {exc}")
    st.stop()

st.markdown("""
<div class="hero">
    <h1><span class="medical-icon">+</span> Heart Disease Risk Predictor</h1>
    <p>Machine-learning based 10-year CHD risk estimation using the Framingham dataset.</p>
</div>
""", unsafe_allow_html=True)

st.caption(f"Model status: {model_status}")

st.markdown('<div class="section-title">Patient Information</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)

with c1:
    age = st.number_input("Age (years)", min_value=18, max_value=100, value=50, step=1, key="age_input")
    sex_label = st.selectbox("Sex", ["Female", "Male"], key="sex_input")
    male = 1 if sex_label == "Male" else 0
    education = st.selectbox("Education level", [1, 2, 3, 4], index=1, key="education_input")
    smoker_label = st.selectbox("Current smoker", ["No", "Yes"], key="smoker_input")
    current_smoker = 1 if smoker_label == "Yes" else 0
    cigs_per_day = st.number_input("Cigarettes per day", min_value=0.0, max_value=100.0, value=0.0, step=1.0, key="cigs_input")

with c2:
    bpmeds_label = st.selectbox("Blood-pressure medication", ["No", "Yes"], key="bpmeds_input")
    bpmeds = 1 if bpmeds_label == "Yes" else 0
    stroke_label = st.selectbox("Previous stroke", ["No", "Yes"], key="stroke_input")
    stroke = 1 if stroke_label == "Yes" else 0
    hyp_label = st.selectbox("Hypertension", ["No", "Yes"], key="hyp_input")
    hyp = 1 if hyp_label == "Yes" else 0
    diabetes_label = st.selectbox("Diabetes", ["No", "Yes"], key="diabetes_input")
    diabetes = 1 if diabetes_label == "Yes" else 0
    tot_chol = st.number_input("Total cholesterol (mg/dL)", min_value=80.0, max_value=600.0, value=200.0, step=1.0, key="chol_input")

with c3:
    sys_bp = st.number_input("Systolic BP (mmHg)", min_value=70.0, max_value=300.0, value=120.0, step=1.0, key="sysbp_input")
    dia_bp = st.number_input("Diastolic BP (mmHg)", min_value=40.0, max_value=200.0, value=80.0, step=1.0, key="diabp_input")
    bmi = st.number_input("BMI", min_value=10.0, max_value=70.0, value=25.0, step=0.1, key="bmi_input")
    heart_rate = st.number_input("Heart rate (bpm)", min_value=30.0, max_value=220.0, value=75.0, step=1.0, key="hr_input")
    glucose = st.number_input("Glucose (mg/dL)", min_value=40.0, max_value=500.0, value=80.0, step=1.0, key="glucose_input")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

predict = st.button("Predict 10-Year CHD Risk", type="primary", use_container_width=True)

if predict:
    values = {
        "male": male, "age": age, "education": education,
        "currentSmoker": current_smoker, "cigsPerDay": cigs_per_day,
        "BPMeds": bpmeds, "prevalentStroke": stroke,
        "prevalentHyp": hyp, "diabetes": diabetes,
        "totChol": tot_chol, "sysBP": sys_bp, "diaBP": dia_bp,
        "BMI": bmi, "heartRate": heart_rate, "glucose": glucose
    }

    input_data = pd.DataFrame([values], columns=FEATURES)
    probability = float(model.predict_proba(input_data)[0, 1])
    prediction = int(model.predict(input_data)[0])
    suggestions = make_suggestions(values, probability)

    st.markdown("### Prediction Result")
    r1, r2 = st.columns(2)

    with r1:
        st.markdown(
            f'<div class="result-card"><div class="small-note">'
            f'Estimated 10-year CHD probability</div>'
            f'<div class="risk-number">{probability*100:.1f}%</div></div>',
            unsafe_allow_html=True
        )

    with r2:
        label = "Higher predicted risk" if prediction else "Lower predicted risk"
        st.markdown(
            f'<div class="result-card"><div class="small-note">Model class</div>'
            f'<div class="risk-number" style="font-size:2rem;">{label}</div>'
            f'<div class="small-note">Class {prediction}</div></div>',
            unsafe_allow_html=True
        )

    st.progress(min(max(probability, 0.0), 1.0))

    if prediction:
        st.warning("The model classified this input as class 1. This is a machine-learning estimate, not a medical diagnosis.")
    else:
        st.success("The model classified this input as class 0. This is a machine-learning estimate, not a medical diagnosis.")

    st.markdown("### Practical Suggestions")
    for item in suggestions:
        st.write("• " + item)

    pdf_bytes = build_pdf(values, probability, prediction, suggestions)
    st.download_button(
        "Download Personalised Risk Report (PDF)",
        data=pdf_bytes,
        file_name="heart_disease_risk_report.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

    with st.expander("View values sent to the model"):
        st.dataframe(input_data, use_container_width=True)

with st.expander("About this project"):
    st.write(
        "This app uses the project's Phase 3 Logistic Regression model with "
        "StandardScaler and the same 15 input features. The target variable is TenYearCHD."
    )

st.markdown("""
<div class="footer">
<b>Academic project disclaimer:</b> This application is for educational and demonstration
purposes only. It is not a clinical diagnostic tool.
</div>
""", unsafe_allow_html=True)
