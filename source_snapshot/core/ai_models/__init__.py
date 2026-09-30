# [DORMANT - V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
AI Models Module
Provides machine-learning-driven biological design features.
"""

from .base_model import BaseAIModel

try:
    from .promoter_predictor import PromoterStrengthPredictor
except Exception:
    PromoterStrengthPredictor = None  # type: ignore

try:
    from .grna_designer import gRNADesigner
except Exception:
    gRNADesigner = None  # type: ignore

try:
    from .deep_codon import DeepCodonOptimizer
except Exception:
    DeepCodonOptimizer = None  # type: ignore

try:
    from .crispr_ai_enhanced import (
        CRISPREfficiencyPredictor,
        get_predictor as get_crispr_predictor,
        predict_grna,
        predict_offtarget,
    )
except Exception:
    CRISPREfficiencyPredictor = None  # type: ignore

try:
    from .metabolic_optimizer import (
        MetabolicOptimizer,
        get_optimizer,
        optimize_pathway,
        list_supported_metabolites,
    )
except Exception:
    MetabolicOptimizer = None  # type: ignore

__all__ = [
    'BaseAIModel',
    'PromoterStrengthPredictor',
    'gRNADesigner',
    'DeepCodonOptimizer',
    'CRISPREfficiencyPredictor',
    'MetabolicOptimizer',
]

__version__ = '1.2.0'
