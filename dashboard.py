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

import subprocess
import sys
import shutil
import tempfile
import zipfile

import streamlit as st

from cardiodev_guard.scanner import run_scan
from cardiodev_guard.report import to_json, to_markdown
from cardiodev_guard.findings import Severity, AuditDomain, ScanReport
from cardiodev_guard.auditors.qa_audit import register_qa_analyzers

# ---------------------------------------------------------------------------
# One-time QA analyzer registration
# ---------------------------------------------------------------------------
_QA_ANALYZERS_REGISTERED: bool = False
if not _QA_ANALYZERS_REGISTERED:
    register_qa_analyzers()
    _QA_ANALYZERS_REGISTERED = True

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CardioDev-Guard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Theme palettes
# ---------------------------------------------------------------------------
_DARK = {
    "bg":          "#0B0D0F",
    "surface":     "#111417",
    "surface2":    "#171B20",
    "surface3":    "#1E2329",
    "border":      "rgba(255,255,255,.09)",
    "border2":     "rgba(255,255,255,.06)",
    "text":        "#F2F1ED",
    "muted":       "#8B929D",
    "muted2":      "#555C68",
    "accent":      "#9A8CFF",
    "accent_dim":  "#7468cc",
    "accent_bg":   "rgba(154,140,255,.10)",
    "accent_brd":  "rgba(154,140,255,.25)",
    "block_bg":    "rgba(220,80,70,.12)",
    "block_brd":   "rgba(220,80,70,.35)",
    "block_text":  "#E87060",
    "warn_bg":     "rgba(200,140,40,.10)",
    "warn_brd":    "rgba(200,140,40,.30)",
    "warn_text":   "#D4A030",
    "pass_bg":     "rgba(70,170,110,.10)",
    "pass_brd":    "rgba(70,170,110,.28)",
    "pass_text":   "#5BB880",
    "scan_bg":     "rgba(255,255,255,.04)",
    "code_bg":     "rgba(255,255,255,.06)",
    "bar_track":   "rgba(255,255,255,.07)",
    "block_bar":   "#C04040",
    "warn_bar":    "#B08020",
    "pass_bar":    "#3A9060",
    "empty_bar":   "rgba(255,255,255,.08)",
    "empty_cnt":   "#444C58",
    "sb_bg":       "#0D0F12",
    "sb_border":   "rgba(255,255,255,.07)",
    "sb_text":     "#8B929D",
    "sb_active_bg":"rgba(154,140,255,.14)",
    "sb_active_c": "#9A8CFF",
    "footer_c":    "#2E3440",
    "input_bg":    "#171B20",
    "input_brd":   "rgba(255,255,255,.12)",
}
_LIGHT = {
    "bg":          "#F7F6F3",
    "surface":     "#FFFFFF",
    "surface2":    "#F0EEE9",
    "surface3":    "#E8E6E1",
    "border":      "rgba(0,0,0,.09)",
    "border2":     "rgba(0,0,0,.06)",
    "text":        "#1A1C20",
    "muted":       "#6B7280",
    "muted2":      "#A0A8B4",
    "accent":      "#6B5CE7",
    "accent_dim":  "#8878ee",
    "accent_bg":   "rgba(107,92,231,.08)",
    "accent_brd":  "rgba(107,92,231,.22)",
    "block_bg":    "#FDF2F2",
    "block_brd":   "#E8A8A8",
    "block_text":  "#C0392B",
    "warn_bg":     "#FDF7E6",
    "warn_brd":    "#E8D080",
    "warn_text":   "#8A5C00",
    "pass_bg":     "#EEF8F2",
    "pass_brd":    "#A8D5B8",
    "pass_text":   "#2E7D52",
    "scan_bg":     "rgba(0,0,0,.03)",
    "code_bg":     "rgba(0,0,0,.04)",
    "bar_track":   "#E8E6E1",
    "block_bar":   "#C0392B",
    "warn_bar":    "#C9A032",
    "pass_bar":    "#5AAB7B",
    "empty_bar":   "#D8D5D0",
    "empty_cnt":   "#C0BDCA",
    "sb_bg":       "#FFFFFF",
    "sb_border":   "rgba(0,0,0,.08)",
    "sb_text":     "#6B7280",
    "sb_active_bg":"rgba(107,92,231,.09)",
    "sb_active_c": "#6B5CE7",
    "footer_c":    "#C8C5D4",
    "input_bg":    "#FFFFFF",
    "input_brd":   "rgba(0,0,0,.14)",
}


def _css(t: dict) -> str:
    """Return the full CSS block for the given theme palette dict `t`."""
    return f"""
<style>
/* ── Reset & Base ──────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {{
    background: {t["bg"]} !important;
    color: {t["text"]} !important;
    font-family: -apple-system,"Segoe UI",system-ui,sans-serif;
}}
.stApp {{ background: {t["bg"]} !important; }}
.block-container {{
    max-width: 1200px;
    padding-top: 1.2rem;
    padding-bottom: 3.5rem;
    padding-left: 2rem;
    padding-right: 2rem;
}}
/* Streamlit element overrides */
.stMarkdown p, .stMarkdown li, .stMarkdown h1,
.stMarkdown h2, .stMarkdown h3, .stMarkdown code {{
    color: {t["text"]} !important;
}}
.stTextInput > div > div > input {{
    background: {t["input_bg"]} !important;
    border: 1px solid {t["input_brd"]} !important;
    color: {t["text"]} !important;
    border-radius: 8px !important;
    font-size: .88rem !important;
}}
.stTextInput > div > div > input::placeholder {{ color: {t["muted2"]} !important; }}
.stTextInput label {{ color: {t["muted"]} !important; }}
/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
    background: transparent !important;
    border-bottom: 1px solid {t["border"]} !important;
    gap: 0 !important;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent !important;
    color: {t["muted"]} !important;
    font-size: .82rem !important;
    font-weight: 600 !important;
    padding: .4rem .9rem !important;
    border-bottom: 2px solid transparent !important;
}}
.stTabs [aria-selected="true"] {{
    color: {t["accent"]} !important;
    border-bottom-color: {t["accent"]} !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
    background: transparent !important;
    padding-top: .8rem !important;
}}
/* Expander */
.streamlit-expanderHeader {{
    background: {t["surface2"]} !important;
    color: {t["muted"]} !important;
    border: 1px solid {t["border"]} !important;
    border-radius: 8px !important;
    font-size: .82rem !important;
}}
/* Code blocks */
.stCodeBlock pre, code {{
    background: {t["code_bg"]} !important;
    color: {t["muted"]} !important;
    border: 1px solid {t["border2"]} !important;
    border-radius: 6px !important;
}}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: {t["sb_bg"]} !important;
    border-right: 1px solid {t["sb_border"]} !important;
}}
[data-testid="stSidebar"] .stMarkdown {{ padding: 0 !important; }}
[data-testid="stSidebar"] .stButton > button {{
    width: 100% !important;
    text-align: left !important;
    padding: .38rem .95rem !important;
    background: transparent !important;
    border: none !important;
    border-radius: 7px !important;
    font-size: .87rem !important;
    font-weight: 500 !important;
    color: {t["sb_text"]} !important;
    min-height: 2rem !important;
    margin: .03rem .35rem !important;
    box-shadow: none !important;
    letter-spacing: 0 !important;
    transition: background .12s, color .12s !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: {t["sb_active_bg"]} !important;
    color: {t["sb_active_c"]} !important;
}}
.sb-nav-active > div > button,
.sb-nav-active > div > div > button {{
    background: {t["sb_active_bg"]} !important;
    color: {t["sb_active_c"]} !important;
    font-weight: 700 !important;
}}
/* Theme toggle buttons in sidebar */
[data-testid="stSidebar"] .theme-toggle-wrap .stButton > button {{
    font-size: .75rem !important;
    font-weight: 600 !important;
    padding: .22rem .6rem !important;
    min-height: 1.5rem !important;
    border-radius: 5px !important;
    margin: .05rem !important;
}}
.sb-logo-row {{
    display: flex;
    align-items: center;
    gap: .55rem;
    padding: 1.1rem 1rem .3rem;
}}
.sb-product {{
    font-size: .97rem;
    font-weight: 800;
    color: {t["text"]};
    letter-spacing: -.01em;
}}
.sb-brand-sub {{
    font-size: .63rem;
    font-weight: 600;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: {t["accent"]};
    padding: 0 1rem .7rem;
    display: block;
}}
.sb-divider {{
    height: 1px;
    background: {t["border"]};
    margin: .1rem .8rem .45rem;
}}
.sb-section-label {{
    font-size: .6rem;
    font-weight: 700;
    letter-spacing: .13em;
    text-transform: uppercase;
    color: {t["muted2"]};
    padding: .55rem 1rem .2rem;
    display: block;
}}
.sb-footer {{
    font-size: .68rem;
    color: {t["muted2"]};
    padding: .65rem 1rem;
    line-height: 1.55;
    border-top: 1px solid {t["border"]};
    margin-top: .4rem;
}}

/* ── Scan controls ─────────────────────────────────────────────────────── */
/* Main area buttons (non-sidebar) */
.main .stButton > button {{
    border-radius: 8px !important;
    min-height: 2.4rem !important;
    font-weight: 700 !important;
    font-size: .87rem !important;
    letter-spacing: .01em !important;
}}
.stDownloadButton > button {{
    border-radius: 8px !important;
    min-height: 2.3rem !important;
    font-weight: 600 !important;
}}

/* ── Hero ──────────────────────────────────────────────────────────────── */
.hero-wrap {{
    padding: 2rem 0 1.5rem;
    border-bottom: 1px solid {t["border"]};
    margin-bottom: 1.6rem;
}}
.hero-eyebrow {{
    font-size: .63rem;
    font-weight: 700;
    letter-spacing: .17em;
    text-transform: uppercase;
    color: {t["accent"]};
    margin-bottom: .5rem;
    display: flex;
    align-items: center;
    gap: .4rem;
}}
.hero-title-row {{
    display: flex;
    align-items: center;
    gap: .7rem;
    margin-bottom: .45rem;
}}
.hero-title {{
    font-size: 2.1rem;
    font-weight: 900;
    color: {t["text"]};
    letter-spacing: -.04em;
    line-height: 1.0;
    margin: 0;
}}
.hero-sub-line {{
    font-size: .9rem;
    color: {t["muted"]};
    margin: 0 0 .5rem 0;
    line-height: 1.5;
}}
.hero-annotation-wrap {{
    display: flex;
    align-items: center;
    gap: .5rem;
    margin-top: .4rem;
}}
.hero-annotation {{
    font-size: .76rem;
    color: {t["muted2"]};
    font-style: italic;
}}

/* ── Workflow nav line ─────────────────────────────────────────────────── */
.workflow-nav {{
    display: flex;
    align-items: center;
    gap: 0;
    padding: .65rem 0;
    border-bottom: 1px solid {t["border"]};
    margin-bottom: 1.4rem;
    flex-wrap: wrap;
    gap: .1rem;
}}
.wf-item {{
    display: flex;
    align-items: center;
    gap: .3rem;
    padding: .2rem .5rem;
}}
.wf-num {{
    font-size: .62rem;
    font-weight: 800;
    letter-spacing: .06em;
    color: {t["muted2"]};
}}
.wf-label {{
    font-size: .75rem;
    font-weight: 600;
    color: {t["muted"]};
    letter-spacing: .03em;
}}
.wf-item.done .wf-num {{ color: {t["pass_text"]}; }}
.wf-item.done .wf-label {{ color: {t["pass_text"]}; }}
.wf-item.active .wf-num {{ color: {t["accent"]}; }}
.wf-item.active .wf-label {{ color: {t["accent"]}; }}
.wf-sep {{
    color: {t["muted2"]};
    font-size: .65rem;
    padding: 0 .15rem;
    opacity: .5;
}}

/* ── Target project area ───────────────────────────────────────────────── */
.target-section {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
    padding: 1.1rem 1.3rem 1rem;
    margin-bottom: 1.1rem;
}}
.target-label {{
    font-size: .6rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: {t["muted2"]};
    margin-bottom: .5rem;
}}
.target-hint {{
    font-size: .73rem;
    color: {t["muted2"]};
    margin-top: .45rem;
    line-height: 1.5;
}}
.target-active {{
    font-size: .77rem;
    color: {t["muted"]};
    margin-top: .3rem;
    padding: .28rem .5rem;
    background: {t["scan_bg"]};
    border-radius: 5px;
    display: inline-block;
    border: 1px solid {t["border2"]};
}}
.target-active b {{ color: {t["text"]}; }}
.target-active code {{
    font-size: .72rem;
    color: {t["muted"]};
    background: transparent !important;
    border: none !important;
}}
.target-error {{
    font-size: .78rem;
    color: {t["block_text"]};
    margin-top: .3rem;
}}

/* ── Vertical flow diagram ─────────────────────────────────────────────── */
.vflow-wrap {{
    padding: .5rem .4rem;
}}

/* ── Scan meta pill ────────────────────────────────────────────────────── */
.scan-meta {{
    font-size: .72rem;
    color: {t["muted2"]};
    margin-bottom: .65rem;
    padding: .32rem .6rem;
    background: {t["scan_bg"]};
    border-radius: 5px;
    display: inline-block;
    border: 1px solid {t["border2"]};
}}
.scan-meta b {{ color: {t["muted"]}; }}
.scan-meta code {{
    font-size: .68rem;
    color: {t["muted2"]};
    background: transparent !important;
    border: none !important;
}}

/* ── Release readiness panel ───────────────────────────────────────────── */
.readiness-panel {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
}}
.readiness-label {{
    font-size: .6rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: {t["muted2"]};
    margin-bottom: .5rem;
}}
.readiness-verdict {{
    font-size: 1.35rem;
    font-weight: 900;
    letter-spacing: -.02em;
    margin: 0 0 .7rem;
    line-height: 1;
}}
.readiness-verdict.ready  {{ color: {t["pass_text"]}; }}
.readiness-verdict.blocked {{ color: {t["block_text"]}; }}
.readiness-verdict.pending {{ color: {t["muted"]}; }}

/* metric table */
.metric-table {{
    width: 100%;
    border-collapse: collapse;
}}
.metric-table tr {{
    border-bottom: 1px solid {t["border2"]};
}}
.metric-table tr:last-child {{ border-bottom: none; }}
.metric-table td {{
    padding: .3rem 0;
    font-size: .82rem;
}}
.metric-table .mt-label {{
    color: {t["muted"]};
    font-weight: 500;
}}
.metric-table .mt-val {{
    text-align: right;
    font-weight: 800;
    font-size: .95rem;
    letter-spacing: -.01em;
}}
.mt-blocker {{ color: {t["block_text"]}; }}
.mt-warning {{ color: {t["warn_text"]}; }}
.mt-pass    {{ color: {t["pass_text"]}; }}
.mt-total   {{ color: {t["accent"]}; }}

/* release banner strip */
.banner-ready {{
    padding: .55rem 1rem;
    border-radius: 7px;
    background: {t["pass_bg"]};
    border: 1px solid {t["pass_brd"]};
    color: {t["pass_text"]};
    font-weight: 700;
    font-size: .88rem;
    margin-bottom: .7rem;
}}
.banner-blocked {{
    padding: .55rem 1rem;
    border-radius: 7px;
    background: {t["block_bg"]};
    border: 1px solid {t["block_brd"]};
    color: {t["block_text"]};
    font-weight: 700;
    font-size: .88rem;
    margin-bottom: .7rem;
}}
.banner-pending {{
    padding: .55rem 1rem;
    border-radius: 7px;
    background: {t["scan_bg"]};
    border: 1px solid {t["border"]};
    color: {t["muted"]};
    font-weight: 600;
    font-size: .86rem;
    margin-bottom: .7rem;
}}

/* ── Quality overview panel ────────────────────────────────────────────── */
.quality-panel {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
}}
.panel-label {{
    font-size: .6rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: {t["muted2"]};
    margin-bottom: .7rem;
}}

/* quality bars */
.quality-row {{
    display: flex;
    align-items: center;
    gap: .5rem;
    margin-bottom: .44rem;
}}
.quality-name {{
    font-size: .74rem;
    color: {t["muted"]};
    font-weight: 500;
    width: 145px;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.quality-bar-bg {{
    flex: 1;
    height: 6px;
    background: {t["bar_track"]};
    border-radius: 3px;
    overflow: hidden;
    min-width: 36px;
}}
.quality-bar-fill {{
    height: 100%;
    border-radius: 3px;
    min-width: 3px;
}}
.quality-bar-fill.ok    {{ background: {t["pass_bar"]}; }}
.quality-bar-fill.warn  {{ background: {t["warn_bar"]}; }}
.quality-bar-fill.block {{ background: {t["block_bar"]}; }}
.quality-bar-fill.empty {{ background: transparent; min-width: 0; width: 0 !important; }}
.quality-count {{
    font-size: .68rem;
    font-weight: 700;
    min-width: 40px;
    text-align: right;
    flex-shrink: 0;
    white-space: nowrap;
}}
.quality-count.ok    {{ color: {t["pass_text"]}; }}
.quality-count.warn  {{ color: {t["warn_text"]}; }}
.quality-count.block {{ color: {t["block_text"]}; }}
.quality-count.empty {{ color: {t["empty_cnt"]}; }}

/* ── Top findings (audit log style) ───────────────────────────────────── */
.top-findings-wrap {{
    display: flex;
    gap: .65rem;
    margin: .6rem 0 .85rem;
    flex-wrap: wrap;
}}
.top-finding {{
    flex: 1;
    min-width: 185px;
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
    padding: .75rem .9rem;
    border-left: 3px solid {t["border"]};
}}
.top-finding.blocker {{ border-left-color: {t["block_text"]}; }}
.top-finding.warning {{ border-left-color: {t["warn_text"]}; }}
.top-finding.pass    {{ border-left-color: {t["pass_text"]}; }}
.tf-sev-row {{
    display: flex;
    align-items: center;
    gap: .35rem;
    margin-bottom: .3rem;
}}
.tf-severity {{
    font-size: .58rem;
    font-weight: 800;
    letter-spacing: .12em;
    text-transform: uppercase;
}}
.tf-severity.blocker {{ color: {t["block_text"]}; }}
.tf-severity.warning {{ color: {t["warn_text"]}; }}
.tf-severity.pass    {{ color: {t["pass_text"]}; }}
.tf-title {{
    font-size: .81rem;
    font-weight: 700;
    color: {t["text"]};
    margin-bottom: .28rem;
    line-height: 1.35;
}}
.tf-evidence {{
    font-size: .72rem;
    color: {t["muted"]};
    line-height: 1.4;
    margin-bottom: .4rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}}
.tf-link {{
    font-size: .7rem;
    font-weight: 700;
    color: {t["accent"]};
    text-decoration: none;
}}

/* ── Finding card ──────────────────────────────────────────────────────── */
.finding-card {{
    padding: .78rem 1rem;
    border-radius: 9px;
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-left: 3px solid {t["border"]};
    margin-bottom: .55rem;
}}
.finding-card.blocker {{ border-left-color: {t["block_text"]}; }}
.finding-card.warning {{ border-left-color: {t["warn_text"]}; }}
.finding-card.pass    {{ border-left-color: {t["pass_text"]}; }}

.finding-title {{
    font-weight: 700;
    font-size: .88rem;
    color: {t["text"]};
    margin-bottom: .35rem;
    line-height: 1.4;
}}
.finding-badge {{
    display: inline-block;
    padding: .1rem .42rem;
    border-radius: 4px;
    font-size: .61rem;
    font-weight: 800;
    margin-right: .35rem;
    vertical-align: middle;
    letter-spacing: .06em;
    text-transform: uppercase;
}}
.badge-blocker {{
    background: {t["block_bg"]};
    color: {t["block_text"]};
    border: 1px solid {t["block_brd"]};
}}
.badge-warning {{
    background: {t["warn_bg"]};
    color: {t["warn_text"]};
    border: 1px solid {t["warn_brd"]};
}}
.badge-pass {{
    background: {t["pass_bg"]};
    color: {t["pass_text"]};
    border: 1px solid {t["pass_brd"]};
}}
.badge-cat {{
    background: {t["scan_bg"]};
    color: {t["muted2"]};
    border: 1px solid {t["border2"]};
}}
.finding-field-label {{
    font-size: .65rem;
    font-weight: 700;
    color: {t["muted2"]};
    text-transform: uppercase;
    letter-spacing: .09em;
    margin-top: .45rem;
}}
.finding-field-value {{
    font-size: .8rem;
    color: {t["muted"]};
    margin-top: .08rem;
    line-height: 1.5;
}}

/* ── Domain header ─────────────────────────────────────────────────────── */
.domain-header {{
    font-size: .9rem;
    font-weight: 800;
    color: {t["text"]};
    margin: .25rem 0 .65rem;
    padding-bottom: .3rem;
    border-bottom: 1px solid {t["border"]};
    letter-spacing: -.01em;
}}
.domain-ready   {{ color: {t["pass_text"]}; font-size: .72rem; font-weight: 700; }}
.domain-blocked {{ color: {t["block_text"]}; font-size: .72rem; font-weight: 700; }}

/* ── Section label ─────────────────────────────────────────────────────── */
.section-label {{
    font-size: .6rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: {t["muted2"]};
    margin: 1rem 0 .45rem;
    display: block;
}}

/* ── Docs cards ────────────────────────────────────────────────────────── */
.docs-card {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    margin-bottom: .7rem;
}}
.docs-card h3 {{
    font-size: .9rem;
    font-weight: 800;
    color: {t["text"]};
    margin: 0 0 .45rem 0;
}}
.docs-card p, .docs-card li {{
    font-size: .82rem;
    color: {t["muted"]};
    line-height: 1.6;
}}
.docs-card code {{
    font-size: .76rem;
    background: {t["code_bg"]} !important;
    padding: .1rem .32rem;
    border-radius: 4px;
    color: {t["accent"]} !important;
    border: none !important;
}}

/* ── Empty state ───────────────────────────────────────────────────────── */
.empty-state {{
    padding: 1.5rem 1.7rem;
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
    margin-top: .5rem;
}}
.empty-state-title {{
    font-size: 1rem;
    font-weight: 800;
    color: {t["text"]};
    margin-bottom: .25rem;
}}
.empty-state-sub {{
    font-size: .83rem;
    color: {t["muted"]};
    line-height: 1.55;
}}

/* ── Export label ──────────────────────────────────────────────────────── */
.export-label {{
    font-size: .6rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: {t["muted2"]};
    margin: .8rem 0 .4rem;
    display: block;
}}

/* ── Page footer ───────────────────────────────────────────────────────── */
.page-footer {{
    margin-top: 2.5rem;
    padding-top: .8rem;
    border-top: 1px solid {t["border"]};
    color: {t["footer_c"]};
    font-size: .69rem;
    text-align: center;
    line-height: 1.6;
}}
</style>
"""


# ---------------------------------------------------------------------------
# SVG logo — shield with a subtle pulse line inside
# ---------------------------------------------------------------------------
def _logo_svg(size: int = 24, accent: str = "#9A8CFF", stroke: str = "#F2F1ED") -> str:
    """Inline SVG shield-with-pulse logo. accent=guard color, stroke=shield body."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 32 32" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle;flex-shrink:0;">'
        f'<path d="M16 2 L28 7 L28 17 C28 23.5 22 28.5 16 30 C10 28.5 4 23.5 4 17 L4 7 Z" '
        f'fill="none" stroke="{accent}" stroke-width="1.8" stroke-linejoin="round"/>'
        f'<polyline points="8,17 11,13 14,19 17,11 20,17 24,17" '
        f'fill="none" stroke="{accent}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".9"/>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Hero annotation SVG curved arrow
# ---------------------------------------------------------------------------
def _curved_arrow_svg(t: dict) -> str:
    """Small SVG curved arrow for hero annotation."""
    return (
        f'<svg width="36" height="20" viewBox="0 0 36 20" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle;opacity:.55;">'
        f'<defs>'
        f'<marker id="ca" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">'
        f'<path d="M0,0.5 L5,3 L0,5.5 L1.2,3 Z" fill="{t["muted2"]}"/>'
        f'</marker>'
        f'</defs>'
        f'<path d="M2,16 Q18,2 34,10" fill="none" stroke="{t["muted2"]}" '
        f'stroke-width="1.3" marker-end="url(#ca)" stroke-dasharray="2,1.5"/>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Vertical flow SVG (PROJECT → AUDIT → QUALITY → RELEASE)
# ---------------------------------------------------------------------------
def _vertical_flow_svg(t: dict) -> str:
    """Vertical pipeline SVG for the right column beside Target Project."""
    ac = t["accent"]
    mt = t["muted2"]
    bg = t["surface2"]
    bd = t["border"]
    tx = t["muted"]
    return f"""
<div class="vflow-wrap">
<svg viewBox="0 0 110 260" xmlns="http://www.w3.org/2000/svg"
     style="width:110px;display:block;margin:0 auto;overflow:visible;">
  <defs>
    <marker id="vfa" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 L1.5,3 Z" fill="{mt}"/>
    </marker>
  </defs>
  <!-- NODE 1 -->
  <rect x="15" y="5" width="80" height="30" rx="6"
        fill="{bg}" stroke="{bd}" stroke-width="1"/>
  <text x="55" y="18" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="8" font-weight="700" fill="{tx}">PROJECT</text>
  <text x="55" y="28" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="6.5" fill="{mt}">.py · .ipynb · .csv</text>
  <!-- CONNECTOR 1→2 -->
  <line x1="55" y1="35" x2="55" y2="63"
        stroke="{mt}" stroke-width="1.3" marker-end="url(#vfa)"/>
  <!-- ANNOTATION right of connector -->
  <text x="65" y="52" font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="6.5" font-style="italic" fill="{mt}" opacity=".7">any ML project</text>
  <!-- NODE 2 -->
  <rect x="15" y="65" width="80" height="30" rx="6"
        fill="{t['accent_bg']}" stroke="{t['accent_brd']}" stroke-width="1.2"/>
  <text x="55" y="78" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="8" font-weight="700" fill="{ac}">ML AUDIT</text>
  <text x="55" y="88" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="6.5" fill="{ac}" opacity=".8">Scan · Analyze</text>
  <!-- CONNECTOR 2→3 -->
  <line x1="55" y1="95" x2="55" y2="123"
        stroke="{mt}" stroke-width="1.3" marker-end="url(#vfa)"/>
  <!-- ANNOTATION left of connector -->
  <text x="5" y="113" font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="6.5" font-style="italic" fill="{mt}" opacity=".7">what can</text>
  <text x="5" y="121" font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="6.5" font-style="italic" fill="{mt}" opacity=".7">break?</text>
  <!-- NODE 3 -->
  <rect x="15" y="125" width="80" height="30" rx="6"
        fill="{bg}" stroke="{bd}" stroke-width="1"/>
  <text x="55" y="141" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="8" font-weight="700" fill="{tx}">QUALITY CHECKS</text>
  <!-- CONNECTOR 3→4 -->
  <line x1="55" y1="155" x2="55" y2="183"
        stroke="{mt}" stroke-width="1.3" marker-end="url(#vfa)"/>
  <text x="65" y="171" font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="6.5" font-style="italic" fill="{mt}" opacity=".7">ready to ship?</text>
  <!-- NODE 4 -->
  <rect x="15" y="185" width="80" height="30" rx="6"
        fill="{bg}" stroke="{bd}" stroke-width="1"/>
  <text x="55" y="198" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="8" font-weight="700" fill="{tx}">RELEASE</text>
  <text x="55" y="209" text-anchor="middle"
        font-family="-apple-system,Segoe UI,system-ui,sans-serif"
        font-size="7" fill="{mt}">READINESS</text>
</svg>
</div>
"""


# ---------------------------------------------------------------------------
# Helpers — audit logic UNCHANGED
# ---------------------------------------------------------------------------

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
    css = _SEVERITY_CSS[f.severity]
    badge_css = _BADGE_CSS[f.severity]

    def row(label, value):
        safe = value.replace("\n", "<br>")
        return (
            f'<div class="finding-field-label">{label}</div>'
            f'<div class="finding-field-value">{safe}</div>'
        )

    cat_html = (
        f'<span class="finding-badge badge-cat">{f.category}</span>'
        if f.category else ""
    )

    return f"""
<div class="finding-card {css}">
  <div class="finding-title">
    <span class="finding-badge {badge_css}">{f.severity.value}</span>
    {cat_html}
    {f.title}
  </div>
  {row("Evidence", f.evidence)}
  {row("Why it matters", f.explanation)}
  {row("Suggested fix", f.suggested_fix)}
  {row("Validation method", f.validation_method)}
</div>
"""


def _render_summary_table(report: ScanReport) -> None:
    """Typography-based metric table instead of four giant cards."""
    n_b = len(report.blockers)
    n_w = len(report.warnings)
    n_p = len(report.passes)
    n_t = n_b + n_w + n_p
    st.markdown(f"""
<table class="metric-table">
  <tr><td class="mt-label">Blockers</td><td class="mt-val mt-blocker">{n_b}</td></tr>
  <tr><td class="mt-label">Warnings</td><td class="mt-val mt-warning">{n_w}</td></tr>
  <tr><td class="mt-label">Passed</td><td class="mt-val mt-pass">{n_p}</td></tr>
  <tr><td class="mt-label">Total</td><td class="mt-val mt-total">{n_t}</td></tr>
</table>
""", unsafe_allow_html=True)


def _render_release_banner(report: ScanReport) -> None:
    total = len(report.all_findings)
    if total == 0:
        st.markdown(
            '<div class="banner-pending">&#9203;&nbsp; Awaiting audit results</div>',
            unsafe_allow_html=True,
        )
    elif report.release_ready:
        st.markdown(
            f'<div class="banner-ready">&#10003;&nbsp; {report.release_status_label}'
            f' &mdash; no blockers</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="banner-blocked">&#10007;&nbsp; {report.release_status_label}'
            f' &mdash; {len(report.blockers)} blocker(s) must be resolved</div>',
            unsafe_allow_html=True,
        )


def _render_domain_tab(result) -> None:
    icon = _DOMAIN_ICON.get(result.domain, "📋")

    if not result.findings:
        st.markdown(
            f'<div class="domain-header">{icon} {result.domain.value} Audit'
            f'<span style="color:var(--muted2,#555C68);font-size:.71rem;font-weight:400;">'
            f' &mdash; awaiting results</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="padding:.8rem 1rem;border-radius:8px;'
            f'border:1px dashed rgba(128,128,128,.3);font-size:.82rem;">'
            f'<b>{result.domain.value} audit pending.</b><br>'
            f'<span style="font-size:.74rem;">'
            f'Call <code>cardiodev_guard.auditors.{result.domain.value.lower()}'
            f'_audit.inject_results(audit_result)</code> before scanning.</span></div>',
            unsafe_allow_html=True,
        )
        return

    status_css = "domain-ready" if result.is_ready else "domain-blocked"
    status_label = "Ready" if result.is_ready else f"{len(result.blockers)} blocker(s)"
    st.markdown(
        f'<div class="domain-header">{icon} {result.domain.value} Audit &nbsp;'
        f'<span class="{status_css}">&mdash; {status_label}</span></div>',
        unsafe_allow_html=True,
    )

    ordered = (
        sorted([f for f in result.findings if f.severity == Severity.BLOCKER], key=lambda x: x.title)
        + sorted([f for f in result.findings if f.severity == Severity.WARNING], key=lambda x: x.title)
        + sorted([f for f in result.findings if f.severity == Severity.PASS], key=lambda x: x.title)
    )
    for f in ordered:
        st.markdown(_finding_card_html(f), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Quality Overview — count-based bars, dynamically mapped (logic UNCHANGED)
# ---------------------------------------------------------------------------

_QUALITY_DIMS = [
    "Data Quality",
    "Model Quality",
    "Code & Structure",
    "Reproducibility",
    "Testing",
    "Security & Compliance",
    "Documentation",
]

_CAT_FRAGMENTS: list[tuple[str, str]] = [
    ("data_quality",      "Data Quality"),
    ("data",              "Data Quality"),
    ("model_performance", "Model Quality"),
    ("model",             "Model Quality"),
    ("reproducib",        "Reproducibility"),
    ("repro",             "Reproducibility"),
    ("test_coverage",     "Testing"),
    ("test",              "Testing"),
    ("security",          "Security & Compliance"),
    ("compliance",        "Security & Compliance"),
    ("documentation",     "Documentation"),
    ("doc",               "Documentation"),
    ("code_quality",      "Code & Structure"),
    ("code",              "Code & Structure"),
    ("structure",         "Code & Structure"),
    ("dependency",        "Code & Structure"),
    ("analyzer_failure",  "Code & Structure"),
]

_DOMAIN_DIM_FALLBACK: dict[AuditDomain, str] = {
    AuditDomain.ML:      "Model Quality",
    AuditDomain.QA:      "Data Quality",
    AuditDomain.RELEASE: "Code & Structure",
}


def _map_finding_to_dim(f) -> str:
    key = (f.category or "").lower().strip()
    for fragment, dim in _CAT_FRAGMENTS:
        if fragment in key:
            return dim
    return _DOMAIN_DIM_FALLBACK.get(f.domain, "Code & Structure")


def _quality_bar_html(name: str, n_block: int, n_warn: int, n_pass: int, max_total: int) -> str:
    total = n_block + n_warn + n_pass

    if total == 0:
        return (
            f'<div class="quality-row">'
            f'<div class="quality-name">{name}</div>'
            f'<div class="quality-bar-bg"><div class="quality-bar-fill empty"></div></div>'
            f'<div class="quality-count empty">0</div>'
            f'</div>'
        )

    bar_pct = max(int(total / max(max_total, 1) * 100), 4)

    if n_block > 0:
        bar_cls = cnt_cls = "block"
        cnt = f"{total} ({n_block}&#9747;)" if (n_warn > 0 or n_pass > 0) else f"{n_block}&#9747;"
    elif n_warn > 0:
        bar_cls = cnt_cls = "warn"
        cnt = f"{total} ({n_warn}&#9888;)" if n_pass > 0 else f"{n_warn}&#9888;"
    else:
        bar_cls = cnt_cls = "ok"
        cnt = f"{total}&#10003;"

    return (
        f'<div class="quality-row">'
        f'<div class="quality-name">{name}</div>'
        f'<div class="quality-bar-bg">'
        f'<div class="quality-bar-fill {bar_cls}" style="width:{bar_pct}%;"></div>'
        f'</div>'
        f'<div class="quality-count {cnt_cls}">{cnt}</div>'
        f'</div>'
    )


def _render_quality_overview(report: ScanReport) -> None:
    """Render quality overview bars derived from actual finding data. Logic UNCHANGED."""
    bucket: dict[str, dict[str, int]] = {
        d: {"block": 0, "warn": 0, "pass": 0} for d in _QUALITY_DIMS
    }
    for f in report.all_findings:
        dim = _map_finding_to_dim(f)
        if dim not in bucket:
            dim = "Code & Structure"
        if f.severity == Severity.BLOCKER:
            bucket[dim]["block"] += 1
        elif f.severity == Severity.WARNING:
            bucket[dim]["warn"] += 1
        else:
            bucket[dim]["pass"] += 1

    max_total = max(
        (b["block"] + b["warn"] + b["pass"] for b in bucket.values()),
        default=1,
    )

    html_parts = [
        _quality_bar_html(dim, bucket[dim]["block"], bucket[dim]["warn"], bucket[dim]["pass"], max_total)
        for dim in _QUALITY_DIMS
    ]

    st.markdown(
        '<div class="panel-label">Quality Overview</div>' + "".join(html_parts),
        unsafe_allow_html=True,
    )


def _render_top_findings(report: ScanReport) -> None:
    """Show top 3 findings as audit-log style cards."""
    all_ordered = (
        sorted(report.blockers, key=lambda x: x.title)
        + sorted(report.warnings, key=lambda x: x.title)
        + sorted(report.passes, key=lambda x: x.title)
    )
    top = all_ordered[:3]
    if not top:
        return

    cards = []
    for f in top:
        css = _SEVERITY_CSS[f.severity]
        sev = f.severity.value.upper()
        cat = f.category.upper() if f.category else ""
        ev = f.evidence[:110].replace("\n", " ")
        cards.append(
            f'<div class="top-finding {css}">'
            f'<div class="tf-sev-row">'
            f'<span class="tf-severity {css}">{sev}</span>'
            + (f'<span style="font-size:.58rem;color:var(--muted2,#555);font-weight:600;letter-spacing:.06em;">{cat}</span>' if cat else "")
            + f'</div>'
            f'<div class="tf-title">{f.title}</div>'
            f'<div class="tf-evidence">{ev}</div>'
            f'<span class="tf-link">Details &#8595;</span>'
            f'</div>'
        )

    st.markdown(
        '<span class="section-label">Top Findings</span>'
        '<div class="top-findings-wrap">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Docs view
# ---------------------------------------------------------------------------

def _render_docs() -> None:
    st.markdown("""
<div class="docs-card">
  <h3>CardioDev-Guard &mdash; Quick Reference</h3>
  <p>CardioDev-Guard is a generic ML project quality and release-readiness audit tool.
  It scans any local ML project and produces structured findings across three audit domains.</p>
</div>
<div class="docs-card">
  <h3>Workflow</h3>
  <ol>
    <li><b>Scan</b> &mdash; Select a local ML project directory and click <em>Run Scan</em>.</li>
    <li><b>Analyze</b> &mdash; The tool runs all registered analyzers.</li>
    <li><b>Report</b> &mdash; Findings with evidence, fixes, and downloads.</li>
    <li><b>Re-check</b> &mdash; Re-run after applying fixes to verify improvement.</li>
  </ol>
</div>
<div class="docs-card">
  <h3>Audit Domains</h3>
  <ul>
    <li><b>ML</b> &mdash; Core ML pipeline checks via core bridge.</li>
    <li><b>QA</b> &mdash; Missing values, duplicates, class imbalance, model metrics, leakage.</li>
    <li><b>Release</b> &mdash; Aggregated readiness verdict.</li>
  </ul>
</div>
<div class="docs-card">
  <h3>Severity Levels</h3>
  <ul>
    <li><b>BLOCKER</b> &mdash; Must be resolved before release (HIGH or CRITICAL).</li>
    <li><b>WARNING</b> &mdash; Should be reviewed (MEDIUM or LOW).</li>
    <li><b>PASS</b> &mdash; Check passed (INFO).</li>
  </ul>
</div>
<div class="docs-card">
  <h3>Supported Project Types</h3>
  <p>Any local directory containing ML project files:<br>
  <code>.py</code>&nbsp; <code>.ipynb</code>&nbsp; <code>.csv</code>&nbsp;
  <code>.pkl</code>&nbsp; <code>.parquet</code></p>
</div>
<div class="docs-card">
  <h3>CLI Usage</h3>
  <p><code>streamlit run dashboard.py</code></p>
  <p>Default target: the CardioDev-Guard repository itself (demo mode).</p>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Project target helpers
# ---------------------------------------------------------------------------
_REPO_ROOT: Path = Path(__file__).resolve().parent
_DEFAULT_TARGET: str = str(
    _REPO_ROOT / "phase 3"
    if (_REPO_ROOT / "phase 3").is_dir()
    else _REPO_ROOT
)


def _resolve_target(raw: str) -> tuple[Path | None, str]:
    p = Path(raw.strip())
    if not p.exists():
        return None, f"Path does not exist: `{p}`"
    if not p.is_dir():
        return None, f"Path is not a directory: `{p}`"
    return p.resolve(), ""


def _extract_uploaded_project(zip_bytes: bytes, filename: str) -> tuple[Path | None, str]:
    """Safely extract an uploaded ML project ZIP into a temporary directory."""
    if not filename.lower().endswith(".zip"):
        return None, "Please upload a .zip ML project."

    temp_root = Path(tempfile.mkdtemp(prefix="cardiodev_guard_"))

    try:
        zip_path = temp_root / "project.zip"
        zip_path.write_bytes(zip_bytes)

        with zipfile.ZipFile(zip_path) as zf:
            members = [m for m in zf.infolist() if not m.filename.startswith("__MACOSX/")]
            if not members:
                raise ValueError("The ZIP is empty.")

            # Prevent ZIP path traversal (e.g. ../../some_file).
            for member in members:
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("Invalid ZIP: unsafe file path detected.")

            zf.extractall(temp_root / "project")

        project_dir = temp_root / "project"
        children = [p for p in project_dir.iterdir() if p.name != "__MACOSX"]
        directories = [p for p in children if p.is_dir()]
        files = [p for p in children if p.is_file()]

        # Handle both: project.zip/files... and project.zip/project/files...
        if len(directories) == 1 and not files:
            project_root = directories[0]
        else:
            project_root = project_dir

        # The ZIP itself is no longer needed after extraction.
        zip_path.unlink(missing_ok=True)
        return project_root.resolve(), ""

    except zipfile.BadZipFile:
        shutil.rmtree(temp_root, ignore_errors=True)
        return None, "The uploaded file is not a valid ZIP."
    except Exception as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        return None, f"Could not extract project: {exc}"


def _cleanup_uploaded_project() -> None:
    """Remove the previous temporary uploaded-project directory."""
    old_root = st.session_state.pop("uploaded_project_temp", None)
    if old_root:
        shutil.rmtree(old_root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
def _footer() -> None:
    st.markdown(
        '<div class="page-footer">'
        'CardioDev-Guard &nbsp;&middot;&nbsp; ML Project Quality Audit &nbsp;&middot;&nbsp;'
        ' Academic project &nbsp;&middot;&nbsp; Does not modify any ML model files'
        '</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

def main() -> None:

    # ── Session-state defaults ─────────────────────────────────────────────
    if "view" not in st.session_state:
        st.session_state["view"] = "dashboard"
    if "theme" not in st.session_state:
        st.session_state["theme"] = "dark"

    theme_key = st.session_state["theme"]
    t = _DARK if theme_key == "dark" else _LIGHT

    # Inject theme-specific CSS
    st.markdown(_css(t), unsafe_allow_html=True)

    scan_done = "last_report" in st.session_state
    view = st.session_state.get("view", "dashboard")

    # ── Sidebar ────────────────────────────────────────────────────────────
    with st.sidebar:
        logo_svg = _logo_svg(size=22, accent=t["accent"], stroke=t["text"])
        st.markdown(
            f'<div class="sb-logo-row">'
            f'{logo_svg}'
            f'<span class="sb-product">CardioDev-Guard</span>'
            f'</div>'
            f'<span class="sb-brand-sub">ML Quality Audit</span>'
            f'<div class="sb-divider"></div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<span class="sb-section-label">Navigation</span>',
            unsafe_allow_html=True,
        )

        # Nav buttons
        _nav_items = [
            ("dashboard", "Dashboard"),
            ("scan",      "Scan"),
            ("findings",  "Findings"),
            ("report",    "Report"),
            ("recheck",   "Re-check"),
            ("docs",      "Docs"),
        ]
        for view_key, label in _nav_items:
            is_active = view == view_key
            if is_active:
                st.markdown('<div class="sb-nav-active">', unsafe_allow_html=True)
            if st.button(label, key=f"nav_{view_key}"):
                st.session_state["view"] = view_key
                st.rerun()
            if is_active:
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            '<div class="sb-divider" style="margin-top:.45rem;"></div>'
            '<span class="sb-section-label">Audit Domains</span>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:.79rem;color:{t["muted"]};line-height:1.9;'
            f'padding:.05rem 1rem .35rem;">'
            f'ML Artifact checks<br>'
            f'QA / Test checks<br>'
            f'Release gate</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="sb-footer">'
            f'Developer &amp; CI/CD audit tool.<br>'
            f'Does not modify any ML model files.'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Hero ───────────────────────────────────────────────────────────────
    logo_hero = _logo_svg(size=28, accent=t["accent"], stroke=t["text"])
    arrow_svg = _curved_arrow_svg(t)

    st.markdown(f"""
<div class="hero-wrap">
  <div class="hero-eyebrow">
    {logo_hero}
    <span>ML Project Quality Audit</span>
  </div>
  <div class="hero-title-row">
    <h1 class="hero-title">CardioDev-Guard</h1>
  </div>
  <p class="hero-sub-line">From notebooks to production-ready ML.</p>
  <div class="hero-annotation-wrap">
    {arrow_svg}
    <span class="hero-annotation">find what can break before release</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Workflow nav line ──────────────────────────────────────────────────
    step_defs = [("01", "SCAN"), ("02", "ANALYZE"), ("03", "REPORT"), ("04", "RE-CHECK")]
    wf_html = '<div class="workflow-nav">'
    for i, (num, name) in enumerate(step_defs):
        cls = "done" if (scan_done and i < 3) else ("active" if (not scan_done and i == 0) else "")
        if i > 0:
            wf_html += '<span class="wf-sep">&#8594;</span>'
        wf_html += (
            f'<div class="wf-item {cls}">'
            f'<span class="wf-num">{num}</span>'
            f'<span class="wf-label">{name}</span>'
            f'</div>'
        )
    wf_html += "</div>"
    st.markdown(wf_html, unsafe_allow_html=True)

    # ── DOCS view ──────────────────────────────────────────────────────────
    if view == "docs":
        _render_docs()
        _footer()
        return

    # ── Target project section + vertical flow diagram ─────────────────────
    col_target, col_flow = st.columns([3, 1], gap="medium")

    with col_target:
        st.markdown(
            f'<div class="target-label" style="padding-top:.35rem;">TARGET PROJECT</div>',
            unsafe_allow_html=True,
        )

        input_mode = st.radio(
            "Project source",
            ["Upload ZIP", "Local Folder"],
            horizontal=True,
            label_visibility="collapsed",
            key="project_input_mode",
        )

        target_path = None
        path_error = ""

        if input_mode == "Upload ZIP":
            uploaded_project = st.file_uploader(
                "Upload ML project ZIP",
                type=["zip"],
                key="uploaded_project",
                help="ZIP your ML project folder and upload it here. The project is scanned in a temporary folder and is not executed.",
            )

            if uploaded_project is not None:
                st.session_state["uploaded_project_bytes"] = uploaded_project.getvalue()
                st.session_state["uploaded_project_name"] = uploaded_project.name

            if st.session_state.get("uploaded_project_bytes"):
                upload_name = st.session_state.get("uploaded_project_name", "project.zip")
                st.markdown(
                    f'<div class="target-active"><b>Uploaded:</b> <code>{upload_name}</code></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="target-hint">Upload an updated ZIP again before Re-check after fixing your project locally.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="target-hint">Cloud users can upload any ML project as a ZIP. '
                    'Works with .py, .ipynb, .csv, .pkl and .parquet projects.</div>',
                    unsafe_allow_html=True,
                )

        else:
            hdr_col, browse_col = st.columns([5, 1])
            with hdr_col:
                st.caption("Local folder mode — works when running CardioDev-Guard on your own machine.")
            with browse_col:
                if sys.platform == "darwin":
                    if st.button("Browse", key="browse_folder", use_container_width=True):
                        try:
                            result = subprocess.run(
                                [
                                    "osascript",
                                    "-e",
                                    'POSIX path of (choose folder with prompt "Select ML Project Folder")',
                                ],
                                capture_output=True,
                                text=True,
                            )
                            if result.returncode == 0:
                                selected = result.stdout.strip()
                                if selected:
                                    st.session_state["target_project_path"] = selected.rstrip("/")
                                    st.rerun()
                        except OSError:
                            st.warning(
                                "Folder browsing is unavailable here. "
                                "Enter the project path manually."
                            )
                else:
                    st.caption("Browse is available locally on macOS; online users should use Upload ZIP.")

            target_path_raw: str = st.text_input(
                "Local ML project folder path",
                value=st.session_state.get("target_project_path", _DEFAULT_TARGET),
                key="target_project_path",
                placeholder="/Users/you/my-ml-project",
                label_visibility="collapsed",
                help="Absolute path to any local ML project directory.",
            )

            target_path, path_error = _resolve_target(target_path_raw)
            if target_path is None:
                st.markdown(
                    f'<div class="target-error">&#9888; {path_error}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        btn_col, recheck_col = st.columns([1, 1])
        with btn_col:
            run_button = st.button(
                "Run Scan" if not scan_done else "Run Scan Again",
                type="primary",
                use_container_width=True,
            )
        with recheck_col:
            recheck_button = st.button(
                "Re-check",
                type="secondary",
                use_container_width=True,
                disabled=not scan_done,
                help="Re-run the scan to verify fixes. For an uploaded project, upload the updated ZIP first.",
            )

    with col_flow:
        st.markdown(_vertical_flow_svg(t), unsafe_allow_html=True)

    # ── Execute scan ───────────────────────────────────────────────────────
    if run_button or recheck_button:
        target = None
        err = ""
        temp_target = None

        if input_mode == "Upload ZIP":
            zip_bytes = st.session_state.get("uploaded_project_bytes")
            zip_name = st.session_state.get("uploaded_project_name", "project.zip")
            if not zip_bytes:
                err = "Upload an ML project ZIP before running the scan."
            else:
                # Clean the previous extracted copy before creating a new one.
                _cleanup_uploaded_project()
                target, err = _extract_uploaded_project(zip_bytes, zip_name)
                temp_target = target
                if target is not None:
                    st.session_state["uploaded_project_temp"] = str(target.parent.parent)
        else:
            target, err = _resolve_target(
                st.session_state.get("target_project_path", _DEFAULT_TARGET)
            )

        if target is None:
            st.error(err)
            return

        label = "Re-checking project..." if recheck_button else "Scanning project..."
        try:
            with st.spinner(label):
                report = run_scan(target)
        finally:
            # Keep the extracted ZIP during the Streamlit session so Re-check/report
            # can still reference the scan result; the next scan cleans it up.
            pass

        st.session_state["last_report"] = report
        st.session_state["scan_count"] = st.session_state.get("scan_count", 0) + 1
        if not recheck_button:
            st.session_state["view"] = "dashboard"
        st.rerun()

    # ── SCAN view ──────────────────────────────────────────────────────────
    if view == "scan":
        if not scan_done:
            st.markdown(
                '<div class="empty-state">'
                '<div class="empty-state-title">Ready when you are.</div>'
                '<div class="empty-state-sub">Enter the path above and click <b>Run Scan</b>.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            _render_release_banner(st.session_state["last_report"])
        _footer()
        return

    # ── RECHECK view ───────────────────────────────────────────────────────
    if view == "recheck":
        if not scan_done:
            st.info("Run a scan first, then use Re-check to verify your fixes.")
        else:
            report: ScanReport = st.session_state["last_report"]
            sc = st.session_state.get("scan_count", 1)
            sn = Path(report.project_path).name or report.project_path
            st.markdown(
                f'<div class="scan-meta">Target: <b>{sn}</b> &middot; Scan #{sc}</div>',
                unsafe_allow_html=True,
            )
            _render_release_banner(report)
            _render_summary_table(report)
        _footer()
        return

    # ── No report yet ──────────────────────────────────────────────────────
    if not scan_done:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-state-title">Ready when you are.</div>'
            '<div class="empty-state-sub">'
            'Select a local ML project above and run the audit.<br>'
            '<span style="font-size:.76rem;opacity:.6;">'
            'Scan &rarr; Analyze &rarr; Report &rarr; Re-check'
            '</span></div></div>',
            unsafe_allow_html=True,
        )
        _footer()
        return

    # ── Report exists ──────────────────────────────────────────────────────
    report: ScanReport = st.session_state["last_report"]
    scan_count = st.session_state.get("scan_count", 1)
    scanned_name = Path(report.project_path).name or report.project_path

    st.markdown(
        f'<div class="scan-meta">'
        f'Target: <b>{scanned_name}</b>'
        f'&nbsp;&middot;&nbsp;<code>{report.project_path}</code>'
        f'&nbsp;&middot;&nbsp;{report.scan_timestamp}'
        f'&nbsp;&middot;&nbsp;Scan #{scan_count}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── FINDINGS view ──────────────────────────────────────────────────────
    if view == "findings":
        st.markdown('<span class="section-label">Findings by Domain</span>', unsafe_allow_html=True)
        domain_names = [
            f'{_DOMAIN_ICON.get(r.domain, "📋")} {r.domain.value}'
            for r in report.audit_results
        ]
        if domain_names:
            tabs = st.tabs(domain_names + ["All Findings"])
            for i, result in enumerate(report.audit_results):
                with tabs[i]:
                    _render_domain_tab(result)
            with tabs[-1]:
                st.markdown('<div class="domain-header">All Findings</div>', unsafe_allow_html=True)
                all_ordered = (
                    sorted(report.blockers, key=lambda x: (x.domain.value, x.title))
                    + sorted(report.warnings, key=lambda x: (x.domain.value, x.title))
                    + sorted(report.passes, key=lambda x: (x.domain.value, x.title))
                )
                for f in all_ordered:
                    di = _DOMAIN_ICON.get(f.domain, "📋")
                    st.markdown(
                        f'<div style="font-size:.66rem;color:{t["muted2"]};margin-bottom:.1rem;">'
                        f'{di} {f.domain.value}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(_finding_card_html(f), unsafe_allow_html=True)
        _footer()
        return

    # ── REPORT view ────────────────────────────────────────────────────────
    if view == "report":
        _render_release_banner(report)
        _render_summary_table(report)
        st.markdown('<span class="export-label">Export Report</span>', unsafe_allow_html=True)
        ec1, ec2 = st.columns(2)
        with ec1:
            md_report = to_markdown(report)
            st.download_button(
                label="Download Markdown",
                data=md_report.encode("utf-8"),
                file_name=f"cardiodev_guard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with ec2:
            json_report = to_json(report)
            st.download_button(
                label="Download JSON",
                data=json_report.encode("utf-8"),
                file_name=f"cardiodev_guard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )
        with st.expander("Preview JSON Report"):
            st.code(json_report, language="json")
        _footer()
        return

    # ── DASHBOARD view (default) ───────────────────────────────────────────

    # 2-column: Release Readiness | Quality Overview
    left_col, right_col = st.columns([1, 1], gap="medium")

    with left_col:
        total_f = len(report.all_findings)
        if total_f == 0:
            v_cls, v_txt = "pending", "PENDING"
        elif report.release_ready:
            v_cls, v_txt = "ready", "READY"
        else:
            v_cls, v_txt = "blocked", "NOT READY"

        st.markdown(
            f'<div class="readiness-panel">'
            f'<div class="readiness-label">Release Readiness</div>'
            f'<div class="readiness-verdict {v_cls}">{v_txt}</div>',
            unsafe_allow_html=True,
        )
        _render_summary_table(report)
        st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
       _render_quality_overview(report)

    # Status banner
    _render_release_banner(report)

    # Top findings
    _render_top_findings(report)

    # Detailed findings
    st.markdown('<span class="section-label">Findings by Domain</span>', unsafe_allow_html=True)
    domain_names = [
        f'{_DOMAIN_ICON.get(r.domain, "📋")} {r.domain.value}'
        for r in report.audit_results
    ]
    if domain_names:
        tabs = st.tabs(domain_names + ["All Findings"])
        for i, result in enumerate(report.audit_results):
            with tabs[i]:
                _render_domain_tab(result)
        with tabs[-1]:
            st.markdown('<div class="domain-header">All Findings</div>', unsafe_allow_html=True)
            all_ordered = (
                sorted(report.blockers, key=lambda x: (x.domain.value, x.title))
                + sorted(report.warnings, key=lambda x: (x.domain.value, x.title))
                + sorted(report.passes, key=lambda x: (x.domain.value, x.title))
            )
            for f in all_ordered:
                di = _DOMAIN_ICON.get(f.domain, "📋")
                st.markdown(
                    f'<div style="font-size:.66rem;color:{t["muted2"]};margin-bottom:.1rem;">'
                    f'{di} {f.domain.value}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(_finding_card_html(f), unsafe_allow_html=True)

    # Export
    st.markdown('<span class="export-label">Export Report</span>', unsafe_allow_html=True)
    ec1, ec2 = st.columns(2)
    with ec1:
        md_report = to_markdown(report)
        st.download_button(
            label="Download Markdown",
            data=md_report.encode("utf-8"),
            file_name=f"cardiodev_guard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with ec2:
        json_report = to_json(report)
        st.download_button(
            label="Download JSON",
            data=json_report.encode("utf-8"),
            file_name=f"cardiodev_guard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )
    with st.expander("Preview JSON Report"):
        st.code(json_report, language="json")

    _footer()


if __name__ == "__main__":
    main()
