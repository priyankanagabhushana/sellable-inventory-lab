"""Shared presentation helpers for the Streamlit learning product."""
from __future__ import annotations

import html

import streamlit as st


NAVY = "#16283A"
TEAL = "#177267"
ORANGE = "#D96F3D"
CREAM = "#F6F1E7"
INK = "#17212B"
MUTED = "#5B6670"
LINE = "#DDD5C7"
GREEN = "#2F7D63"
RED = "#B7523F"
GOLD = "#B58A42"


def apply_theme() -> None:
    """Apply a compact, accessible visual system across every page."""
    st.markdown(
        f"""
        <style>
        :root {{
          --sellable-navy: {NAVY};
          --sellable-teal: {TEAL};
          --sellable-orange: {ORANGE};
          --sellable-cream: {CREAM};
          --sellable-ink: {INK};
          --sellable-muted: {MUTED};
          --sellable-line: {LINE};
        }}
        .stApp {{
          background:
            radial-gradient(circle at 90% 0%, rgba(23,114,103,.08), transparent 28rem),
            linear-gradient(180deg, #fbf8f2 0%, #f6f1e7 100%);
          color: var(--sellable-ink);
        }}
        [data-testid="stSidebar"] {{
          background: #efe7d8;
          border-right: 1px solid var(--sellable-line);
        }}
        [data-testid="stHeader"] {{ background: rgba(251,248,242,.84); }}
        .block-container {{ max-width: 1180px; padding-top: 2.3rem; padding-bottom: 4rem; }}
        h1, h2, h3 {{ color: var(--sellable-navy); letter-spacing: -.025em; }}
        h1 {{ max-width: 900px; }}
        p, li {{ line-height: 1.62; }}
        [data-testid="stMetric"] {{
          background: rgba(255,255,255,.72);
          border: 1px solid var(--sellable-line);
          border-radius: 16px;
          padding: 1rem 1.1rem;
          box-shadow: 0 8px 30px rgba(22,40,58,.04);
        }}
        [data-testid="stMetricLabel"] {{ color: var(--sellable-muted); }}
        [data-testid="stMetricValue"] {{ color: var(--sellable-navy); }}
        [data-testid="stExpander"] {{
          border: 1px solid var(--sellable-line);
          border-radius: 14px;
          background: rgba(255,255,255,.58);
        }}
        [data-testid="stDataFrame"] {{
          border: 1px solid var(--sellable-line);
          border-radius: 14px;
          overflow: hidden;
        }}
        .sellable-hero {{
          position: relative;
          overflow: hidden;
          padding: 2.2rem 2.35rem;
          margin: .2rem 0 1.8rem;
          background: linear-gradient(135deg, {NAVY} 0%, #214558 58%, {TEAL} 100%);
          color: #fff;
          border-radius: 24px;
          box-shadow: 0 20px 60px rgba(22,40,58,.17);
        }}
        .sellable-hero::after {{
          content: "";
          position: absolute;
          width: 260px;
          height: 260px;
          right: -90px;
          top: -115px;
          border: 42px solid rgba(255,255,255,.08);
          border-radius: 50%;
        }}
        .sellable-kicker {{
          position: relative;
          z-index: 1;
          font-size: .76rem;
          font-weight: 750;
          letter-spacing: .13em;
          text-transform: uppercase;
          color: #bde3dc;
          margin-bottom: .7rem;
        }}
        .sellable-hero h1 {{
          position: relative;
          z-index: 1;
          color: #fff;
          margin: 0;
          max-width: 760px;
          font-size: clamp(2rem, 5vw, 3.25rem);
          line-height: 1.05;
        }}
        .sellable-hero p {{
          position: relative;
          z-index: 1;
          color: #e9f0f2;
          max-width: 800px;
          margin: 1rem 0 1.2rem;
          font-size: 1.04rem;
        }}
        .sellable-badges {{ position: relative; z-index: 1; display:flex; flex-wrap:wrap; gap:.55rem; }}
        .sellable-badge {{
          display:inline-flex;
          align-items:center;
          gap:.4rem;
          padding:.34rem .7rem;
          border-radius:999px;
          background:rgba(255,255,255,.12);
          border:1px solid rgba(255,255,255,.2);
          color:#fff;
          font-size:.78rem;
          font-weight:650;
        }}
        .sellable-step {{
          display:grid;
          grid-template-columns: 54px minmax(0,1fr);
          gap:1rem;
          align-items:start;
          margin:2.25rem 0 1rem;
        }}
        .sellable-step-number {{
          width:46px;
          height:46px;
          display:grid;
          place-items:center;
          border-radius:14px;
          background:{TEAL};
          color:#fff;
          font-weight:800;
          box-shadow:0 8px 18px rgba(23,114,103,.18);
        }}
        .sellable-step h2 {{ margin:.05rem 0 .2rem; }}
        .sellable-step p {{ margin:0; color:{MUTED}; }}
        .sellable-callout {{
          padding:1rem 1.1rem;
          margin:.55rem 0 1rem;
          border-radius:14px;
          background:rgba(255,255,255,.72);
          border:1px solid {LINE};
          border-left:5px solid {TEAL};
          box-shadow:0 8px 24px rgba(22,40,58,.035);
        }}
        .sellable-callout.orange {{ border-left-color:{ORANGE}; }}
        .sellable-callout.gold {{ border-left-color:{GOLD}; }}
        .sellable-callout.red {{ border-left-color:{RED}; }}
        .sellable-callout strong {{ display:block; color:{NAVY}; margin-bottom:.2rem; }}
        .sellable-callout span {{ color:{MUTED}; line-height:1.55; }}
        .sellable-pipeline {{
          display:grid;
          grid-template-columns:repeat(4,minmax(0,1fr));
          gap:.7rem;
          margin:1rem 0 1.35rem;
        }}
        .sellable-pipe-node {{
          position:relative;
          min-height:92px;
          padding:.9rem;
          border-radius:16px;
          border:1px solid {LINE};
          background:rgba(255,255,255,.72);
        }}
        .sellable-pipe-node b {{ display:block; color:{NAVY}; margin-bottom:.3rem; }}
        .sellable-pipe-node small {{ color:{MUTED}; line-height:1.35; }}
        .sellable-pipe-node:not(:last-child)::after {{
          content:"→";
          position:absolute;
          right:-.66rem;
          top:35%;
          width:1.3rem;
          height:1.3rem;
          border-radius:50%;
          background:{CREAM};
          color:{ORANGE};
          display:grid;
          place-items:center;
          font-weight:800;
          z-index:2;
        }}
        .sellable-flow {{
          display:flex;
          flex-wrap:wrap;
          align-items:center;
          gap:.48rem;
          padding:1rem 0;
        }}
        .sellable-flow-item {{
          padding:.7rem .85rem;
          border-radius:12px;
          background:#fff;
          border:1px solid {LINE};
          color:{NAVY};
          font-weight:650;
        }}
        .sellable-flow-arrow {{ color:{ORANGE}; font-weight:900; }}
        .sellable-tree {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.7rem; margin:1rem 0; }}
        .sellable-tree-node {{
          min-height:115px;
          padding:.85rem;
          border-radius:14px;
          background:rgba(255,255,255,.76);
          border:1px solid {LINE};
        }}
        .sellable-tree-node b {{ color:{NAVY}; display:block; margin-bottom:.35rem; }}
        .sellable-tree-node span {{ color:{MUTED}; font-size:.88rem; line-height:1.45; }}
        .sellable-footer {{ color:{MUTED}; font-size:.82rem; margin-top:2.5rem; padding-top:1rem; border-top:1px solid {LINE}; }}
        @media (max-width: 760px) {{
          .block-container {{ padding-top:1rem; }}
          .sellable-hero {{ padding:1.55rem 1.25rem; border-radius:18px; }}
          .sellable-pipeline, .sellable-tree {{ grid-template-columns:1fr; }}
          .sellable-pipe-node:not(:last-child)::after {{ display:none; }}
          .sellable-step {{ grid-template-columns:42px minmax(0,1fr); gap:.75rem; }}
          .sellable-step-number {{ width:38px; height:38px; border-radius:11px; }}
        }}
        .sellable-hero {{ padding:1.1rem 1.35rem; margin:0 0 1rem; border-radius:18px; box-shadow:none; }}
        .sellable-hero h1 {{ font-size:clamp(1.65rem,3vw,2.1rem); line-height:1.15; padding:0; }}
        .sellable-hero p {{ margin:.45rem 0; font-size:.97rem; }}
        .sellable-kicker {{ font-size:.67rem; margin-bottom:.4rem; }}
        .sellable-step {{ margin:1.4rem 0 .6rem; }}
        .lab-card {{ background:#fffdf8; border:1px solid {LINE}; border-radius:16px; padding:1rem 1.15rem; margin:.55rem 0; }}
        .lab-card h3 {{ margin:.1rem 0 .35rem; padding:0; font-size:1.1rem; }}
        .lab-caption {{ font-size:.85rem; color:{MUTED}; margin:.4rem 0; }}
        .lab-strip {{ display:flex; height:64px; overflow:hidden; border-radius:12px; margin:1rem 0 .6rem; border:1px solid {LINE}; }}
        .lab-strip span {{ display:flex; align-items:center; justify-content:center; font-weight:700; min-width:0; }}
        .lab-legend {{ display:flex; flex-wrap:wrap; gap:1rem; font-size:.9rem; }}
        .lab-chip {{ display:inline-block; border:1px solid {LINE}; border-radius:9px; padding:.4rem .7rem; background:#fff; margin:.25rem; }}
        .lab-path {{ display:flex; flex-direction:column; align-items:center; gap:.2rem; }}
        .lab-decision {{ text-align:center; width:min(100%,480px); background:white; border:2px solid {TEAL}; padding:.7rem; border-radius:12px; }}
        .lab-path small {{ color:{MUTED}; }}
        .lab-answer {{ color:{TEAL}; font-weight:700; padding:.2rem; }}
        @media(max-width:760px) {{
          .block-container {{ padding-top:3.5rem; }}
          .sellable-hero {{ padding:1rem; }}
          .sellable-hero h1 {{ font-size:1.65rem; }}
          .sellable-badges {{ gap:.3rem; }}
          .sellable-hero .sellable-badges {{ display:none; }}
          .sellable-hero p {{ font-size:.9rem; margin:.4rem 0 0; }}
          .lab-strip {{ height:52px; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, kicker: str, badges: list[str]) -> None:
    pills = "".join(f'<span class="sellable-badge">{html.escape(item)}</span>' for item in badges)
    st.markdown(
        f"""
        <section class="sellable-hero">
          <div class="sellable-kicker">{html.escape(kicker)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(subtitle)}</p>
          <div class="sellable-badges">{pills}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def step(number: int, title: str, summary: str) -> None:
    st.markdown(
        f"""
        <div class="sellable-step">
          <div class="sellable-step-number">{number}</div>
          <div><h2>{html.escape(title)}</h2><p>{html.escape(summary)}</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def callout(title: str, body: str, tone: str = "teal") -> None:
    tone_class = tone if tone in {"orange", "gold", "red"} else ""
    st.markdown(
        f'<div class="sellable-callout {tone_class}"><strong>{html.escape(title)}</strong>'
        f'<span>{html.escape(body)}</span></div>',
        unsafe_allow_html=True,
    )


def pipeline(items: list[tuple[str, str]]) -> None:
    blocks = "".join(
        f'<div class="sellable-pipe-node"><b>{html.escape(title)}</b>'
        f'<small>{html.escape(body)}</small></div>'
        for title, body in items
    )
    st.markdown(f'<div class="sellable-pipeline">{blocks}</div>', unsafe_allow_html=True)


def flow(items: list[str]) -> None:
    nodes: list[str] = []
    for index, item in enumerate(items):
        if index:
            nodes.append('<span class="sellable-flow-arrow">→</span>')
        nodes.append(f'<span class="sellable-flow-item">{html.escape(item)}</span>')
    st.markdown(f'<div class="sellable-flow">{"".join(nodes)}</div>', unsafe_allow_html=True)


def knowledge_check(question: str, answer: str) -> None:
    with st.expander(f"Check yourself · {question}", expanded=False):
        st.success(answer)


def footer() -> None:
    st.markdown(
        '<div class="sellable-footer">Independent educational project · Commercial data and results are simulated · Fixed seeds make the examples reproducible</div>',
        unsafe_allow_html=True,
    )
