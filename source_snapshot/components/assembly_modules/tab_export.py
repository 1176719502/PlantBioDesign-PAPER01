"""
components/assembly_modules/tab_export.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sequence Export tab — FASTA, GenBank, plain text.
"""
import io
import streamlit as st
from components.assembly_modules.assembly_utils import validate_sequence
from core.activity_log import log_build_activity
from core.session_keys import SK

try:
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord
    from Bio.SeqFeature import SeqFeature, FeatureLocation
    from Bio import SeqIO
    _BIO_OK = True
except ImportError:
    _BIO_OK = False


def _default_export_name() -> str:
    for key in (
        'active_sequence_name',
        'handoff_name',
        'construct_name',
        SK.ACTIVE_NAME,
        SK.PROJECT_NAME,
    ):
        value = str(st.session_state.get(key, '') or '').strip()
        if value and value != 'Untitled Project':
            return value
    return 'assembly_product'


def render() -> None:
    st.markdown("#### Sequence Export Preview")
    st.caption(
        "Downloads from this page are workspace/reference artifacts only. They do not indicate "
        "Expression Wizard Step 6 readiness, final delivery approval, or experimental readiness certification."
    )

    export_seq = st.session_state.get(SK.ACTIVE_SEQ,
                 st.session_state.get(SK.ASSEMBLY_RESULT, ''))
    method = st.session_state.get(SK.ASSEMBLY_METHOD, 'Manual')

    if not export_seq:
        st.info("Enter or assemble a sequence in another tab before exporting a workspace artifact.")
        return

    is_valid, val_msg = validate_sequence(export_seq)
    if not is_valid:
        st.error(f"Sequence is invalid: {val_msg}")
        return

    default_name = _default_export_name()
    if 'exp_name' not in st.session_state or st.session_state.get('exp_name') == 'assembly_product':
        st.session_state['exp_name'] = default_name
    ename = st.text_input("Sequence Name", key="exp_name")
    fmt   = st.selectbox("Export Format",
                          ["FASTA", "GenBank (GBK)", "Plain Text"], key="exp_fmt")
    feats = st.session_state.get(SK.FEATURES, [])

    if st.button("Prepare Workspace Export", type="primary",
                 use_container_width=True, key="btn_exp"):
        try:
            ext = {"FASTA": "fasta", "GenBank (GBK)": "gbk", "Plain Text": "txt"}.get(fmt, "txt")
            buf = io.StringIO()

            if _BIO_OK:
                rec = SeqRecord(Seq(export_seq), id=ename, name=ename,
                                description=f"Assembled by Universal BioDesign ({method})")
                for ff in feats:
                    start = int(ff.get('Start', 0))
                    end   = int(ff.get('End', 0))
                    if ff.get('Name') and end > start:
                        rec.features.append(SeqFeature(
                            FeatureLocation(start, end, strand=1),
                            type='gene',
                            qualifiers={'label': [ff.get('Name', '')]},
                        ))
                if fmt == 'FASTA':
                    SeqIO.write(rec, buf, 'fasta')
                elif fmt == 'GenBank (GBK)':
                    SeqIO.write(rec, buf, 'genbank')
                else:
                    buf.write(str(rec.seq))
            else:
                # Fallback without biopython
                if fmt == 'FASTA':
                    buf.write(f"\u003e{ename}\n")
                    seq = export_seq
                    for i in range(0, len(seq), 60):
                        buf.write(seq[i:i+60] + '\n')
                else:
                    buf.write(export_seq)

            st.markdown("##### Preview summary")
            st.download_button(
                label=f"Download {ename}.{ext}",
                data=buf.getvalue(),
                file_name=f"{ename}.{ext}",
                mime="text/plain",
                key="btn_dl_exp",
            )
            st.success(f"Preview generated — documentation artifact preview ready to download: {ename}.{ext} ({len(export_seq):,} bp)")
            st.markdown("##### Export review notes")
            st.caption("This documentation artifact does not bypass Expression Wizard Step 6 export review rules.")
            st.markdown("##### Documentation artifact")
            st.caption("Documentation artifact available for this computational preview only.")
            log_build_activity(f"Sequence exported: {ename}", f"{fmt} · {len(export_seq)} bp")
        except Exception as ex:
            st.error(f"Export failed: {ex}")
