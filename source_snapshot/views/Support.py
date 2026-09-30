"""
views/Support.py
~~~~~~~~~~~~~~~~
About & Support page — Reference docs, terminology, legal notices.
"""
import streamlit as st


def render() -> None:
    st.markdown("""
    <style>
    .sup-section {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 18px;
    }
    .sup-section h3 {
        font-size: 1rem;
        font-weight: 600;
        color: #111827;
        margin-bottom: 10px;
    }
    .sup-label {
        display: block;
        font-size: .72rem;
        font-weight: 700;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: .7px;
        margin-bottom: 14px;
        border-bottom: 1px solid #e5e7eb;
        padding-bottom: 6px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
        <h1 style="margin:0;font-size:1.45rem;font-weight:600">帮助与支持</h1>
    </div>
    <div style="font-size:.82rem;color:#6b7280;border-bottom:1px solid #e5e7eb;
                padding-bottom:.85rem;margin-bottom:1.4rem">
        使用说明 &nbsp;|&nbsp; 常用术语 &nbsp;|
        &nbsp; 参考资源 &nbsp;|&nbsp; 科研使用提示
    </div>
    """, unsafe_allow_html=True)

    col_l, col_r = st.columns([1, 1], gap="large")

    # ── Left column ──────────────────────────────────────────────────────────
    with col_l:

        # Platform info
        with st.container(border=True):
            st.markdown('<span class="sup-label">平台</span>', unsafe_allow_html=True)
            st.markdown("""
**BioDesign Studio** v5.5

当前版本聚焦单基因表达设计的基础流程，
支持基因输入、宿主选择、构建设定与基础导出。
页面中涉及的分析与查看功能仅作为当前版本的辅助能力说明。
            """)
            st.markdown("""
| 模块 | 当前用途 |
|---|---|
| 表达向导 | 单基因表达设计主流程 |
| 组装与克隆 | PCR 设计、克隆仿真与导出支持 |
| 序列工具 | 序列查看、注释与基础分析 |
| 蛋白结构分析 | 蛋白质理化参数计算与 3D 结构查看 |
| 元件库 | 基因、质粒、引物与宿主记录管理 |
            """)

        # Terminology
        with st.container(border=True):
            st.markdown('<span class="sup-label">关键术语</span>', unsafe_allow_html=True)
            st.markdown("""
- **DBTL** — Design-Build-Test-Learn engineering cycle
- **Golden Gate** — Type IIS restriction enzyme (e.g. BsaI/BsmBI) multi-fragment seamless assembly
- **Gibson Assembly** — In vitro homologous recombination, requires 15–40 bp overlaps
- **CRISPR** — Clustered Regularly Interspaced Short Palindromic Repeats; gRNA-guided genome editing
- **gRNA** — Guide RNA; 20 nt spacer sequence directing Cas9/Cas12a to a target site
- **PAM** — Protospacer Adjacent Motif (e.g. NGG for SpCas9, TTTV for Cas12a)
- **CAI** — Codon Adaptation Index; measures codon usage optimality for a host organism
- **MCS** — Multiple Cloning Site; polylinker region carrying clustered restriction sites
- **RBS** — Ribosome Binding Site (prokaryotic; e.g. Shine-Dalgarno: AGGAGG)
- **Kozak** — Eukaryotic translation initiation context (GCCACCATG)
- **BGC** — Biosynthetic Gene Cluster; co-localised genes encoding a secondary metabolite pathway
- **pI** — Isoelectric point; pH at which net protein charge is zero
- **GRAVY** — Grand Average of Hydropathicity; positive = hydrophobic, negative = hydrophilic
- **Tm** — Melting temperature of a DNA duplex or primer
- **TPSA** — Topological Polar Surface Area; used in drug-likeness (Lipinski Ro5) assessment
            """)

    # ── Right column ─────────────────────────────────────────────────────────
    with col_r:

        # Databases & External Resources
        with st.container(border=True):
            st.markdown('<span class="sup-label">数据库 &amp; 外部资源</span>',
                        unsafe_allow_html=True)
            st.markdown("""
**Sequence & Parts**
- [iGEM Parts Registry](https://parts.igem.org) — Standard biological parts
- [Addgene](https://www.addgene.org) — Plasmids & vectors repository
- [NCBI](https://www.ncbi.nlm.nih.gov) — Sequences, literature & BLAST
- [UniProt](https://www.uniprot.org) — Protein sequences & functional annotation

**Structure**
- [RCSB PDB](https://www.rcsb.org) — 3D protein structures
- [AlphaFold DB](https://alphafold.ebi.ac.uk) — AI-predicted protein structures

**Tools referenced by this platform**
- [Primer3](https://primer3.ut.ee) — PCR primer design
            """)

        # Protocol references
        with st.container(border=True):
            st.markdown('<span class="sup-label">协议参考</span>',
                        unsafe_allow_html=True)
            st.markdown("""
- 单基因表达设计流程说明 → **表达向导**
- PCR 设计、克隆仿真与导出 → **组装与克隆**
- 蛋白质理化参数与 3D 结构查看 → **蛋白结构分析**
- 基因、质粒、引物与宿主记录管理 → **元件库**
            """)

        # Legal & Compliance
        with st.container(border=True):
            st.markdown('<span class="sup-label">法律 &amp; 合规</span>',
                        unsafe_allow_html=True)

            st.markdown("**1. 模型与组件说明**")
            st.markdown("""
本软件当前页面可能使用第三方模型或可视化组件，
具体能力以当前版本中实际提供的功能为准。
            """)

            st.markdown("**2. 数据隐私**")
            st.success(
                "本地页面优先处理当前工作数据；如页面涉及外部数据库或结构资源，"
                "将按模块功能直接访问对应公开资源。"
            )

            st.markdown("**3. 仅限科研用途**")
            st.warning(
                "预测结果仅供科研辅助参考，"
                "严禁直接用于临床诊疗。"
            )

    st.markdown("""
    <div style="border-top:1px solid #e5e7eb;margin-top:1.2rem;padding-top:.9rem;
                font-size:.75rem;color:#9ca3af;text-align:center">
        © 2026 BioDesign Inc. &nbsp;·&nbsp; BioDesign Studio v5.5
        &nbsp;·&nbsp; 帮助与支持
    </div>
    """, unsafe_allow_html=True)
