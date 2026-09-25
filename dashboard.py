"""
CardioDev-Guard — Developer Dashboard
========================================
Streamlit developer dashboard implementing the full
Scan → Analyze → Report → Re-check workflow.

Run:
    streamlit run dashboard.py
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

import streamlit as st

from cardiodev_guard.scanner import run_scan
from cardiodev_guard.report import to_json, to_markdown
from cardiodev_guard.findings import Severity, AuditDomain, ScanReport

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CardioDev-Guard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS — clean, minimal, demo-friendly
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Base ─────────────────────────────────────────────────── */
.stApp { background: #f5f7fa; }
.block-container { max-width: 1200px; padding-top: 1.6rem; padding-bottom: 3rem; }

/* ── Header ──────────────────────────────────────────────── */
.guard-header {
    padding: 1.6rem 2rem;
    border-radius: 14px;
    background: #0f172a;
    color: white;
    margin-bottom: 1.4rem;
}
.guard-header h1 { margin: 0 0 .3rem 0; font-size: 1.85rem; font-weight: 800; }
.guard-header p  { margin: 0; color: #94a3b8; font-size: .95rem; }

/* ── Status banner ───────────────────────────────────────── */
.status-ready {
    padding: .9rem 1.4rem; border-radius: 10px;
    background: #f0fdf4; border: 1.5px solid #86efac;
    color: #15803d; font-weight: 700; font-size: 1.05rem;
}
.status-blocked {
    padding: .9rem 1.4rem; border-radius: 10px;
    background: #fff1f2; border: 1.5px solid #fca5a5;
    color: #b91c1c; font-weight: 700; font-size: 1.05rem;
}

/* ── Metric cards ─────────────────────────────────────────── */
.metric-row { display: flex; gap: 1rem; margin: 1rem 0; }
.metric-card {
    flex: 1; padding: 1rem 1.2rem; border-radius: 12px;
    background: #ffffff; border: 1px solid #e2e8f0;
    text-align: center;
}
.metric-number { font-size: 2.2rem; font-weight: 800; margin: .1rem 0; }
.metric-label  { font-size: .82rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }
.num-blocker { color: #dc2626; }
.num-warning { color: #d97706; }
.num-pass    { color: #16a34a; }

/* ── Finding card ─────────────────────────────────────────── */
.finding-card {
    padding: 1rem 1.2rem;
    border-radius: 10px;
    background: #ffffff;
    border-left: 4px solid #e2e8f0;
    margin-bottom: .8rem;
    border: 1px solid #e2e8f0;
}
.finding-card.blocker { border-left-color: #dc2626; }
.finding-card.warning { border-left-color: #d97706; }
.finding-card.pass    { border-left-color: #16a34a; }

.finding-title { font-weight: 700; font-size: .97rem; color: #0f172a; margin-bottom: .4rem; }
.finding-badge {
    display: inline-block; padding: .15rem .55rem;
    border-radius: 999px; font-size: .72rem; font-weight: 700;
    margin-right: .5rem; vertical-align: middle;
}
.badge-blocker { background: #fee2e2; color: #b91c1c; }
.badge-warning { background: #fef3c7; color: #92400e; }
.badge-pass    { background: #dcfce7; color: #15803d; }

.finding-field-label { font-size: .75rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: .05em; margin-top: .55rem; }
.finding-field-value { font-size: .88rem; color: #1e293b; margin-top: .1rem; }

/* ── Domain tabs ──────────────────────────────────────────── */
.domain-header {
    font-size: 1.05rem; font-weight: 750;
    color: #0f172a; margin: .4rem 0 .8rem;
    padding-bottom: .4rem; border-bottom: 2px solid #e2e8f0;
}
.domain-ready   { color: #16a34a; font-size: .8rem; font-weight: 600; }
.domain-blocked { color: #dc2626; font-size: .8rem; font-weight: 600; }

/* ── Scan button ──────────────────────────────────────────── */
.stButton > button {
    border-radius: 9px !important;
    min-height: 2.8rem !important;
    font-weight: 700 !important;
    font-size: .97rem !important;
}
.stDownloadButton > button {
    border-radius: 9px !important;
    min-height: 2.6rem !important;
    font-weight: 600 !important;
}

/* ── Section title ────────────────────────────────────────── */
.section-title {
    font-size: 1rem; font-weight: 750; color: #0f172a;
    border-bottom: 2px solid #e2e8f0; padding-bottom: .4rem;
    margin: .8rem 0 .9rem;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_ICON = {
    Severity.BLOCKER: "🔴",
    Severity.WARNING: "🟡",
    Severity.PASS: "🟢",
}

_SEVERITY_CSS = {
    Severity.BLOCKER: "blocker",
    Severity.WARNING: "warning",
    Severity.PASS: "pass",
}

_BADGE_CSS = {
    Severity.BLOCKER: "badge-blocker",
    Severity.WARNING: "badge-warning",
    Severity.PASS: "badge-pass",
}

_DOMAIN_ICON = {
    AuditDomain.ML: "🤖",
    AuditDomain.QA: "🧪",
    AuditDomain.RELEASE: "🚀",
}


def _finding_card_html(f) -> str:
    icon = _SEVERITY_ICON[f.severity]
    css = _SEVERITY_CSS[f.severity]
    badge_css = _BADGE_CSS[f.severity]

    def row(label, value):
        safe_value = value.replace("\n", "<br>")
        return (
            f'<div class="finding-field-label">{label}</div>'
            f'<div class="finding-field-value">{safe_value}</div>'
        )

    category_html = (
        f'<span class="finding-badge" style="background:#f1f5f9;color:#475569;">'
        f'{f.category}</span>'
        if f.category else ""
    )

    return f"""
<div class="finding-card {css}">
    <div class="finding-title">
        <span class="finding-badge {badge_css}">{icon} {f.severity.value}</span>
        {category_html}
        {f.title}
    </div>
    {row("Evidence", f.evidence)}
    {row("Why it matters", f.explanation)}
    {row("Suggested fix", f.suggested_fix)}
    {row("Validation method", f.validation_method)}
</div>
"""


def _render_summary_cards(report: ScanReport) -> None:
    n_blockers = len(report.blockers)
    n_warnings = len(report.warnings)
    n_passes = len(report.passes)

    st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-number num-blocker">{n_blockers}</div>
        <div class="metric-label">🔴 Blockers</div>
    </div>
    <div class="metric-card">
        <div class="metric-number num-warning">{n_warnings}</div>
        <div class="metric-label">🟡 Warnings</div>
    </div>
    <div class="metric-card">
        <div class="metric-number num-pass">{n_passes}</div>
        <div class="metric-label">🟢 Passed</div>
    </div>
    <div class="metric-card">
        <div class="metric-number" style="color:#3b82f6;">{n_blockers + n_warnings + n_passes}</div>
        <div class="metric-label">📋 Total findings</div>
    </div>
</div>
""", unsafe_allow_html=True)


def _render_release_banner(report: ScanReport) -> None:
    total = len(report.all_findings)

    if total == 0:
        # All adapters returned empty — no team has injected results yet.
        st.markdown(
            '<div style="padding:.9rem 1.4rem;border-radius:10px;'
            'background:#f8fafc;border:1.5px solid #e2e8f0;'
            'color:#64748b;font-weight:600;font-size:1rem;">'
            '⏳ &nbsp;Awaiting audit results — no findings received yet</div>',
            unsafe_allow_html=True,
        )
    elif report.release_ready:
        st.markdown(
            f'<div class="status-ready">✅ &nbsp;{report.release_status_label}'
            f'&nbsp;— no blockers detected</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="status-blocked">🚫 &nbsp;{report.release_status_label}'
            f'&nbsp;— {len(report.blockers)} blocker(s) must be resolved</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)


def _render_domain_tab(result) -> None:
    icon = _DOMAIN_ICON.get(result.domain, "📋")

    if not result.findings:
        # Adapter returned an empty result — team has not injected findings yet.
        st.markdown(
            f'<div class="domain-header">{icon} {result.domain.value} Audit &nbsp;'
            f'<span style="color:#94a3b8;font-size:.8rem;">— awaiting results</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
<div style="padding:1.2rem 1.4rem;border-radius:10px;background:#f8fafc;
            border:1.5px dashed #cbd5e1;color:#64748b;font-size:.9rem;">
    ⏳ &nbsp;<b>{result.domain.value} audit results pending.</b><br>
    The {result.domain.value} team's module has not injected findings yet.<br>
    <span style="font-size:.8rem;">
        Call <code>cardiodev_guard.auditors.{result.domain.value.lower()}_audit.inject_results(audit_result)</code>
        before running the scan.
    </span>
</div>
""",
            unsafe_allow_html=True,
        )
        return

    status_css = "domain-ready" if result.is_ready else "domain-blocked"
    status_label = "✅ Ready" if result.is_ready else f"🚫 {len(result.blockers)} blocker(s)"

    st.markdown(
        f'<div class="domain-header">{icon} {result.domain.value} Audit &nbsp;'
        f'<span class="{status_css}">— {status_label}</span></div>',
        unsafe_allow_html=True,
    )

    # Ordering: BLOCKERs first, then WARNINGs, then PASSes
    ordered = (
        sorted([f for f in result.findings if f.severity == Severity.BLOCKER], key=lambda x: x.title)
        + sorted([f for f in result.findings if f.severity == Severity.WARNING], key=lambda x: x.title)
        + sorted([f for f in result.findings if f.severity == Severity.PASS], key=lambda x: x.title)
    )

    for f in ordered:
        st.markdown(_finding_card_html(f), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

def main() -> None:
    # ── Header ────────────────────────────────────────────────────────────
    st.markdown("""
<div class="guard-header">
    <h1>🛡️ CardioDev-Guard</h1>
    <p>ML Project Quality Audit Dashboard &nbsp;·&nbsp; Scan → Analyze → Report → Re-check</p>
</div>
""", unsafe_allow_html=True)

    # ── Sidebar: scan target ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Scan Configuration")
        default_path = str(Path(__file__).resolve().parent)
        project_path = st.text_input(
            "Project path",
            value=default_path,
            help="Absolute path to the CardioDev-Guard project root.",
        )
        st.markdown("---")
        st.markdown("**Audit domains**")
        st.markdown("🤖 ML Artifact checks  \n🧪 QA / Test checks  \n🚀 Release gate checks")
        st.markdown("---")
        st.caption(
            "This dashboard is for developers and CI/CD pipelines.  \n"
            "It does **not** modify any ML model files."
        )

    # ── Workflow step indicator ────────────────────────────────────────────
    col_steps = st.columns(4)
    step_style_active = "background:#0f172a;color:white;padding:.35rem .9rem;border-radius:20px;font-size:.82rem;font-weight:700;"
    step_style_done   = "background:#dcfce7;color:#15803d;padding:.35rem .9rem;border-radius:20px;font-size:.82rem;font-weight:700;"
    step_style_idle   = "background:#f1f5f9;color:#64748b;padding:.35rem .9rem;border-radius:20px;font-size:.82rem;"

    scan_done = "last_report" in st.session_state

    with col_steps[0]:
        st.markdown(f'<span style="{step_style_active if not scan_done else step_style_done}">1 · Scan</span>', unsafe_allow_html=True)
    with col_steps[1]:
        st.markdown(f'<span style="{step_style_done if scan_done else step_style_idle}">2 · Analyze</span>', unsafe_allow_html=True)
    with col_steps[2]:
        st.markdown(f'<span style="{step_style_done if scan_done else step_style_idle}">3 · Report</span>', unsafe_allow_html=True)
    with col_steps[3]:
        st.markdown(f'<span style="{step_style_done if scan_done else step_style_idle}">4 · Re-check</span>', unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Scan controls ──────────────────────────────────────────────────────
    btn_col, recheck_col, _ = st.columns([2, 2, 4])

    with btn_col:
        run_button = st.button(
            "▶ Run Scan" if not scan_done else "▶ Run Scan Again",
            type="primary",
            use_container_width=True,
        )

    with recheck_col:
        recheck_button = st.button(
            "🔄 Re-check",
            type="secondary",
            use_container_width=True,
            disabled=not scan_done,
            help="Re-run the scan to verify fixes. Enabled after the first scan.",
        )

    # ── Execute scan ───────────────────────────────────────────────────────
    if run_button or recheck_button:
        target = Path(project_path)
        if not target.exists():
            st.error(f"Path does not exist: `{project_path}`")
            return

        label = "Re-checking project..." if recheck_button else "Scanning project..."
        with st.spinner(label):
            report = run_scan(target)

        st.session_state["last_report"] = report
        st.session_state["scan_count"] = st.session_state.get("scan_count", 0) + 1

        # Rerun so the step indicators refresh
        st.rerun()

    # ── Render report ──────────────────────────────────────────────────────
    if "last_report" in st.session_state:
        report: ScanReport = st.session_state["last_report"]
        scan_count = st.session_state.get("scan_count", 1)

        # Scan metadata
        st.markdown(
            f'<div style="font-size:.82rem;color:#64748b;margin-bottom:.6rem;">'
            f'📅 Last scanned: <b>{report.scan_timestamp}</b> &nbsp;·&nbsp; '
            f'Scan #{scan_count} &nbsp;·&nbsp; '
            f'Path: <code>{report.project_path}</code>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Release status banner ──────────────────────────────────────────
        _render_release_banner(report)

        # ── Summary metrics ────────────────────────────────────────────────
        st.markdown('<div class="section-title">📊 Summary</div>', unsafe_allow_html=True)
        _render_summary_cards(report)

        # ── Per-domain findings ────────────────────────────────────────────
        st.markdown('<div class="section-title">🔍 Findings by Domain</div>', unsafe_allow_html=True)

        domain_names = [
            f'{_DOMAIN_ICON.get(r.domain, "📋")} {r.domain.value}'
            for r in report.audit_results
        ]

        if domain_names:
            tabs = st.tabs(domain_names + ["📋 All Findings"])

            for i, result in enumerate(report.audit_results):
                with tabs[i]:
                    _render_domain_tab(result)

            # All findings tab
            with tabs[-1]:
                st.markdown('<div class="domain-header">📋 All Findings</div>', unsafe_allow_html=True)
                all_ordered = (
                    sorted(report.blockers, key=lambda x: (x.domain.value, x.title))
                    + sorted(report.warnings, key=lambda x: (x.domain.value, x.title))
                    + sorted(report.passes, key=lambda x: (x.domain.value, x.title))
                )
                for f in all_ordered:
                    domain_icon = _DOMAIN_ICON.get(f.domain, "📋")
                    st.markdown(
                        f'<div style="font-size:.75rem;color:#64748b;margin-bottom:.2rem;">'
                        f'{domain_icon} {f.domain.value}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(_finding_card_html(f), unsafe_allow_html=True)

        # ── Export section ─────────────────────────────────────────────────
        st.markdown('<div class="section-title">📥 Export Report</div>', unsafe_allow_html=True)

        export_col1, export_col2 = st.columns(2)

        with export_col1:
            md_report = to_markdown(report)
            st.download_button(
                label="⬇ Download Markdown Report",
                data=md_report.encode("utf-8"),
                file_name=f"cardiodev_guard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        with export_col2:
            json_report = to_json(report)
            st.download_button(
                label="⬇ Download JSON Report",
                data=json_report.encode("utf-8"),
                file_name=f"cardiodev_guard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )

        with st.expander("👁 Preview JSON Report"):
            st.code(json_report, language="json")

    else:
        # ── Empty state ────────────────────────────────────────────────────
        st.markdown("""
<div style="text-align:center;padding:3rem 2rem;background:#ffffff;
            border-radius:14px;border:1.5px dashed #cbd5e1;margin-top:1rem;">
    <div style="font-size:3rem;margin-bottom:.8rem;">🛡️</div>
    <div style="font-size:1.1rem;font-weight:700;color:#0f172a;margin-bottom:.4rem;">
        Ready to audit your project
    </div>
    <div style="color:#64748b;font-size:.9rem;">
        Click <b>▶ Run Scan</b> to start the Scan → Analyze → Report workflow.
    </div>
</div>
""", unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────
    st.markdown("""
<div style="margin-top:2.5rem;padding:1rem 1.4rem;border-radius:10px;
            background:#f8fafc;border:1px solid #e2e8f0;
            color:#94a3b8;font-size:.8rem;text-align:center;">
    CardioDev-Guard · Developer Audit Dashboard · Academic project ·
    Does not modify any ML model files
</div>
""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
