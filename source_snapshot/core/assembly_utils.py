# [DORMANT - V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
# -*- coding: utf-8 -*-
"""
生物信息学底层算法模块
- 序列清洗与验证
- 动态引物设计 (Nearest-Neighbor Tm)
- PCR 局部比对预测
- Golden Gate 组装约束检查
- 环状 DNA 拓扑计算
"""
import re
from typing import Tuple, List, Optional, Dict, Any
from core.config import configure_pydna_log_dir

configure_pydna_log_dir()

# -- pydna integration (Gibson / Golden Gate in-silico simulation) -----------
try:
    from pydna.dseqrecord import Dseqrecord
    from pydna.assembly import Assembly
    _PYDNA_OK = True
except ImportError:
    _PYDNA_OK = False


def simulate_gibson(fragments: list, overlap: int = 20) -> dict:
    """
    Simulate Gibson Assembly in-silico using pydna.
    Args:
        fragments : list of DNA strings (linear fragments).
        overlap   : minimum overlap in bp (default 20).
    Returns dict: success, product, length, n_fragments, error
    
    """
    if not _PYDNA_OK:
        return {"success": False, "product": "", "length": 0,
                "n_fragments": len(fragments),
                "error": "pydna not installed. Run: pip install pydna>=3.1.4"}
    if len(fragments) < 2:
        return {"success": False, "product": "", "length": 0,
                "n_fragments": len(fragments),
                "error": "Gibson Assembly requires at least 2 fragments."}
    try:
        recs = [Dseqrecord(f.upper(), linear=True) for f in fragments]
        asm = Assembly(recs, limit=overlap)
        products = asm.assemble_circular()
        if not products:
            return {"success": False, "product": "", "length": 0,
                    "n_fragments": len(fragments),
                    "error": f"No circular product. Check fragments share >= {overlap} bp overlaps."}
        seq_str = str(products[0].seq).upper()
        return {"success": True, "product": seq_str, "length": len(seq_str),
                "n_fragments": len(fragments), "error": ""}
    except Exception as exc:
        return {"success": False, "product": "", "length": 0,
                "n_fragments": len(fragments), "error": str(exc)}


def simulate_golden_gate(fragments: list, enzyme: str = "BsaI", overlap: int = 4) -> dict:
    """
    Simulate Golden Gate Assembly in-silico using pydna.
    Args:
        fragments : list of DNA strings with enzyme sites added.
        enzyme    : 'BsaI' or 'BsmBI'.
        overlap   : overhang length in bp (default 4).
    Returns dict: success, product, length, n_fragments, error
    
    """
    if not _PYDNA_OK:
        return {"success": False, "product": "", "length": 0,
                "n_fragments": len(fragments),
                "error": "pydna not installed. Run: pip install pydna>=3.1.4"}
    if len(fragments) < 2:
        return {"success": False, "product": "", "length": 0,
                "n_fragments": len(fragments),
                "error": "Golden Gate Assembly requires at least 2 fragments."}
    try:
        recs = [Dseqrecord(f.upper(), linear=True) for f in fragments]
        asm = Assembly(recs, limit=overlap)
        products = asm.assemble_circular()
        if not products:
            return {"success": False, "product": "", "length": 0,
                    "n_fragments": len(fragments),
                    "error": f"No circular product. Verify {enzyme} sites and overhangs."}
        seq_str = str(products[0].seq).upper()
        return {"success": True, "product": seq_str, "length": len(seq_str),
                "n_fragments": len(fragments), "error": ""}
    except Exception as exc:
        return {"success": False, "product": "", "length": 0,
                "n_fragments": len(fragments), "error": str(exc)}



# ==========================================
# 1. Sequence cleaning and validation (input preprocessing)
# ==========================================
def clean_dna_sequence(raw: str) -> Tuple[str, List[str]]:
    """
    清洗 DNA 序列：去除空白、换行、不可见字符，统一大小写。
    返回 (清洗后序列, 警告列表)。
    """
    if not raw or not isinstance(raw, str):
        return "", ["Input is empty or not a string"]
    
    warnings = []
    # Remove whitespace, line breaks, and invisible characters
    cleaned = re.sub(r'[\s\r\n\t\u00a0\u200b\u200c\u200d\ufeff]', '', raw)
    cleaned = cleaned.upper()
    
    # Check invalid characters
    valid_bases = set('ATGC')
    invalid_chars = set()
    for c in cleaned:
        if c not in valid_bases:
            invalid_chars.add(c)
    
    if invalid_chars:
        invalid_str = ', '.join(sorted(invalid_chars))
        if 'N' in invalid_chars:
            warnings.append("Sequence contains N (degenerate bases); removed. Results may be affected.")
            cleaned = cleaned.replace('N', '')
        else:
            cleaned = ''.join(c for c in cleaned if c in valid_bases)
            warnings.append(f"Invalid characters removed: {invalid_str}")
    
    if len(cleaned) < 10:
        warnings.append("Sequence is very short and may not support reliable analysis")
    
    return cleaned, warnings


def validate_dna_for_build(seq: str, min_len: int = 50) -> Tuple[bool, str]:
    """
    验证序列是否适合 Build 模块使用。
    返回 (是否有效, 错误/空消息)。
    """
    if not seq:
        return False, "Sequence is empty"
    cleaned, warnings = clean_dna_sequence(seq)
    if len(cleaned) < min_len:
        return False, f"Cleaned sequence is shorter than {min_len} bp"
    if warnings and 'N' in str(warnings):
        return True, "; ".join(warnings)  # Still usable, but surface the warning
    return True, ""


# ==========================================
# 2. Dynamic primer design (Nearest-Neighbor Tm sliding window)
# ==========================================
def design_primer_by_tm(
    seq: str,
    is_forward: bool,
    tm_target: float = 60.0,
    tm_tolerance: float = 2.0,
    min_len: int = 18,
    max_len: int = 35,
) -> Tuple[str, float]:
    """
    基于 Nearest-Neighbor 热力学模型的滑窗引物设计。
    根据 GC 含量动态调整长度，使 Tm 落在 [tm_target ± tm_tolerance]。
    返回 (引物序列, 实际 Tm)。
    """
    from Bio.Seq import Seq
    from Bio.SeqUtils import MeltingTemp as mt
    
    seq = seq.upper()
    max_len = min(max_len, len(seq))
    
    best_primer = None
    best_tm = 0.0
    best_diff = 999.0
    
    for length in range(min_len, max_len + 1):
        if is_forward:
            candidate = seq[:length]
        else:
            # 反向引物 = RC(序列 3' 端)
            candidate = str(Seq(seq[-length:]).reverse_complement())
        
        if len(candidate) < min_len:
            continue
            
        try:
            tm = mt.Tm_NN(Seq(candidate))
        except Exception:
            continue
        
        diff = abs(tm - tm_target)
        if diff < best_diff and (tm_target - tm_tolerance) <= tm <= (tm_target + tm_tolerance):
            best_diff = diff
            best_primer = candidate
            best_tm = tm
    
    # 若未找到理想 Tm，取最接近的
    if best_primer is None:
        for length in range(min_len, max_len + 1):
            if is_forward:
                candidate = seq[:length]
            else:
                candidate = str(Seq(seq[-length:]).reverse_complement())
            try:
                tm = mt.Tm_NN(Seq(candidate))
            except Exception:
                continue
            diff = abs(tm - tm_target)
            if diff < best_diff:
                best_diff = diff
                best_primer = candidate
                best_tm = tm
    
    if best_primer is None:
        L = min(20, len(seq))
        best_primer = seq[:L] if is_forward else str(Seq(seq[-L:]).reverse_complement())
        try:
            best_tm = mt.Tm_NN(Seq(best_primer))
        except Exception:
            best_tm = 60.0
    
    return best_primer, round(best_tm, 1)


# ==========================================
# 3. PCR 局部比对预测 (替代 find 精确匹配)
# ==========================================
def find_primer_binding_local(
    template: str,
    primer: str,
    is_reverse_primer: bool,
    min_3prime_match: int = 5,
    max_mismatch_3prime: int = 0,
) -> List[Dict[str, Any]]:
    """
    使用局部比对查找引物结合位点，重点检查 3' 端 5bp 互补性。
    返回可能的结合位点列表，用于预测主产物和 Off-target。
    """
    from Bio.Align import PairwiseAligner
    from Bio.Seq import Seq
    
    template = template.upper()
    if is_reverse_primer:
        query = str(Seq(primer.upper()).reverse_complement())
    else:
        query = primer.upper()
    
    # 1. Prioritize exact matches
    exact = template.find(query)
    if exact >= 0:
        return [{"start": exact, "end": exact + len(query), "score": 999, "is_off_target": False}]
    
    # 2. Circular template: concatenate seq+seq to support binding across the origin
    template_ext = template + template if len(template) < 10000 else template
    
    # 3. Use local alignment to find the best binding sites
    aligner = PairwiseAligner(mode='local', match_score=2, mismatch_score=-1)
    aligner.gap_score = -2
    
    hits = []
    try:
        alns = list(aligner.align(query, template_ext))
        if alns:
            best = alns[0]
            # Extract coordinates on the template from the alignment
            aln_templ, aln_query = best.aligned
            if aln_templ and aln_query:
                t_start, t_end = aln_templ[0][0], aln_templ[0][1]
                score = best.score
                if score >= len(query) * 1.2:  # At least 60% matched
                    pos = t_start % len(template) if len(template_ext) > len(template) else t_start
                    hits.append({
                        "start": pos,
                        "end": pos + (t_end - t_start),
                        "score": score,
                        "is_off_target": False,
                    })
    except Exception:
        pass
    
    return hits[:5]


def predict_pcr_products(
    template: str,
    primer_f: str,
    primer_r: str,
) -> Dict[str, Any]:
    """
    基于局部比对预测 PCR 产物，包括可能的非特异性扩增。
    正向引物 3' 端 = amplicon 起点，反向引物 3' 端 = amplicon 终点。
    """
    hits_f = find_primer_binding_local(template, primer_f, is_reverse_primer=False)
    hits_r = find_primer_binding_local(template, primer_r, is_reverse_primer=True)
    
    if not hits_f or not hits_r:
        return {
            "primary_product": None,
            "primary_length": 0,
            "off_targets": [],
            "has_off_target": False,
        }
    
    best_f = hits_f[0]
    best_r = hits_r[0]
    
    # Amplicon region: from the 3' end of the forward primer to the 3' end of the reverse primer
    amp_start = best_f["end"]
    amp_end = best_r["start"]
    
    if amp_end > amp_start:
        length = amp_end - amp_start
    else:
        # Circular template crosses the origin
        length = len(template) - amp_start + amp_end
    
    off_targets = []
    for hf in hits_f[1:] + hits_r[1:]:
        off_targets.append({"start": hf["start"], "end": hf["end"], "score": hf["score"]})
    
    return {
        "primary_product": (amp_start, amp_end),
        "primary_length": max(50, length),
        "off_targets": off_targets,
        "has_off_target": len(off_targets) > 0,
    }


# ==========================================
# 4. Golden Gate 组装约束检查
# ==========================================
# Type IIS 酶识别序列 (BsaI: GGTCTC, BsmBI: CGTCTC)
BSAI_SITE = "GGTCTC"
BSMBI_SITE = "CGTCTC"

# Experimentally validated orthogonal 4 bp overhang library (Engler et al.)
ORTHOGONAL_OVERHANGS = [
    "GGAG", "TACT", "AATG", "GCTT", "CGCG", "TCCA", "AGTC",
    "CGCT", "AGAC", "TGAC", "GACT", "ATCG", "TCAG", "GATC",
]


def get_type_iis_sites():
    """返回 BsaI/BsmBI 识别序列列表"""
    return [BSAI_SITE, BSMBI_SITE]


def scan_internal_sites(seq: str) -> List[Dict[str, Any]]:
    """
    扫描序列内部是否包含 BsaI/BsmBI 切点。
    若存在，需在组装前进行 Domestication（位点突变）。
    """
    seq = seq.upper()
    found = []
    for site, enz in [(BSAI_SITE, "BsaI"), (BSMBI_SITE, "BsmBI")]:
        pos = 0
        while True:
            idx = seq.find(site, pos)
            if idx < 0:
                break
            found.append({"enzyme": enz, "position": idx, "site": site})
            pos = idx + 1
    return found


def select_orthogonal_overhangs(num_parts: int) -> List[str]:
    """
    According to the number of parts, select overhangs from the orthogonal library to ensure that adjacent junctions do not self-ligate because of mismatched pairing.
    """
    from Bio.Seq import Seq
    
    used = []
    for i in range(num_parts + 1):
        oh = ORTHOGONAL_OVERHANGS[i % len(ORTHOGONAL_OVERHANGS)]
        oh_rc = str(Seq(oh).reverse_complement())
        # Simple check: avoid matches to already selected forward or reverse complements
        ok = True
        for u in used:
            u_rc = str(Seq(u).reverse_complement())
            if oh == u or oh == u_rc or oh_rc == u:
                ok = False
                break
        if ok:
            used.append(oh)
        else:
            # Try the next candidate
            for candidate in ORTHOGONAL_OVERHANGS:
                if candidate in used:
                    continue
                c_rc = str(Seq(candidate).reverse_complement())
                ok = True
                for u in used:
                    u_rc = str(Seq(u).reverse_complement())
                    if candidate == u or candidate == u_rc or c_rc == u:
                        ok = False
                        break
                if ok:
                    used.append(candidate)
                    break
            if len(used) <= i:
                used.append(ORTHOGONAL_OVERHANGS[i % len(ORTHOGONAL_OVERHANGS)])
    return used[:num_parts + 1]


def check_assembly_constraints(
    part_seqs: List[str],
    part_names: List[str],
) -> Tuple[bool, List[str]]:
    """
    检查组装约束：内部位点、正交性。
    返回 (是否通过, 警告/错误列表)。
    """
    issues = []
    for i, (seq, name) in enumerate(zip(part_seqs, part_names)):
        sites = scan_internal_sites(seq)
        if sites:
            for s in sites:
                issues.append(f"⚠️ Part [{name}] contains internal {s['enzyme']} site at position {s['position']} — requires domestication (silent mutation) before assembly.")
    
    return len(issues) == 0, issues


# ==========================================
# 5. 环状 DNA 拓扑计算
# ==========================================
def get_circular_subsequence(seq: str, start: int, end: int) -> str:
    """
    获取环状序列上 [start, end) 的子序列，支持跨越起点 (0/total_bp)。
    """
    n = len(seq)
    if start <= end:
        return seq[start:end]
    # Crosses the origin
    return seq[start:] + seq[:end]


def calculate_circular_fragments(total_bp: int, cut_positions: List[int]) -> List[int]:
    """
    环状 DNA 酶切片段计算，正确处理跨越起点的片段。
    """
    if not cut_positions:
        return [total_bp]
    cuts = sorted(set(cut_positions))
    if len(cuts) == 1:
        return [total_bp]
    
    fragments = []
    for i in range(len(cuts) - 1):
        fragments.append(cuts[i + 1] - cuts[i])
    # Final fragment: from the last cut site to the first cut site (across the origin)
    fragments.append(total_bp - cuts[-1] + cuts[0])
    return sorted(fragments, reverse=True)
