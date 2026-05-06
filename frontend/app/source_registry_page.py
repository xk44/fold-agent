"""Source registry page helpers for FoldAgent dashboard.

Renders the Paul Conyngham / Rosie links, AlphaFold resources,
bioinformatics tools, and agent framework references.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_source_registry_markdown() -> str | None:
    candidates = [
        Path(__file__).resolve().parents[2] / "docs" / "source_registry.md",
        Path.cwd() / "docs" / "source_registry.md",
    ]
    for p in candidates:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


SOURCE_CATEGORIES = [
    {
        "title": "Paul Conyngham / Rosie",
        "description": "Direct links to Paul's public work on using AI for his dog's cancer treatment.",
        "icon": "🐕",
        "links": [
            {"label": "Paul X profile", "url": "https://x.com/paul_conyngham"},
            {"label": "Paul GitHub", "url": "https://github.com/PaulConyngham"},
            {
                "label": "Rosie repo",
                "url": "https://github.com/PaulConyngham/AutologousCancerVaccineWithQuantumParticles",
            },
        ],
        "warning": "Paul's GitHub repo is an autologous tumor-lysate protocol, not the exact mRNA neoantigen Rosie pipeline.",
    },
    {
        "title": "AlphaFold / Protein Structure",
        "description": "Structure prediction backends supported by FoldAgent.",
        "icon": "🧬",
        "links": [
            {"label": "AlphaFold 2", "url": "https://github.com/google-deepmind/alphafold"},
            {"label": "AlphaFold 3", "url": "https://github.com/google-deepmind/alphafold3"},
            {"label": "AlphaFold Server", "url": "https://alphafoldserver.com/"},
            {"label": "ColabFold", "url": "https://github.com/sokrypton/ColabFold"},
            {"label": "LocalColabFold", "url": "https://github.com/YoshitakaMo/localcolabfold"},
        ],
    },
    {
        "title": "Bioinformatics Tools",
        "description": "Pipeline tools wrapped by FoldAgent adapters.",
        "icon": "🔬",
        "links": [
            {"label": "BWA/BWA-MEM2", "url": "https://github.com/bwa-mem2/bwa-mem2"},
            {
                "label": "GATK Mutect2",
                "url": "https://gatk.broadinstitute.org/hc/en-us/articles/360037593851-Mutect2",
            },
            {"label": "Ensembl VEP", "url": "https://www.ensembl.org/vep"},
            {"label": "pVACtools", "url": "https://pvactools.readthedocs.io/"},
            {
                "label": "NetMHCpan",
                "url": "https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/",
            },
        ],
    },
    {
        "title": "Agent Frameworks",
        "description": "Agent skill formats supported by FoldAgent.",
        "icon": "🤖",
        "links": [
            {"label": "Claude Code Skills", "url": "https://code.claude.com/docs/en/skills"},
            {"label": "OpenClaw", "url": "https://github.com/openclaw/openclaw"},
            {"label": "Hermes Agent", "url": "https://github.com/NousResearch/hermes-agent"},
        ],
    },
    {
        "title": "News / Reporting",
        "description": "Media coverage of the Paul Conyngham / Rosie story.",
        "icon": "📰",
        "links": [
            {
                "label": "UNSW Article",
                "url": "https://news.unsw.edu.au/en/meet-the-man-who-designed-a-cancer-vaccine-for-his-dog",
            },
            {
                "label": "The Scientist",
                "url": "https://www.the-scientist.com/chatgpt-and-alphafold-help-design-personalized-vaccine-for-dog-with-cancer-74227",
            },
            {
                "label": "Fortune",
                "url": "https://fortune.com/2026/03/15/australian-tech-entrepreneur-ai-cancer-vaccine-dog-rosie-unsw-mrna/",
            },
        ],
    },
]


def render_source_registry(st: Any) -> None:
    st.header("Source Registry")
    st.caption(
        "Curated links to the people, tools, and research that inspired FoldAgent. "
        "This project does not provide medical advice or treatment instructions."
    )

    for cat in SOURCE_CATEGORIES:
        with st.expander(f"{cat['icon']} {cat['title']}", expanded=False):
            st.write(cat["description"])
            if cat.get("warning"):
                st.warning(cat["warning"])
            for link in cat["links"]:
                st.markdown(f"- [{link['label']}]({link['url']})")

    md = load_source_registry_markdown()
    if md:
        with st.expander("Full Source Registry (docs/source_registry.md)"):
            st.markdown(md)
