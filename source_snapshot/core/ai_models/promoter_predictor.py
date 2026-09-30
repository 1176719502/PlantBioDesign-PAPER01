# [DORMANT - V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
启动子强度预测器
使用机器学习预测启动子的表达强度
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from Bio.Seq import Seq
try:
    from Bio.SeqUtils import gc_fraction as GC
except ImportError:
    try:
        from Bio.SeqUtils import GC
    except ImportError:
        # 手动实现 GC 计算
        def GC(seq):
            seq = str(seq).upper()
            gc_count = seq.count('G') + seq.count('C')
            return (gc_count / len(seq) * 100) if len(seq) > 0 else 0
import logging

from .base_model import BaseAIModel

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False
    logger.warning("scikit-learn 未安装，启动子预测功能将受限")


class PromoterStrengthPredictor(BaseAIModel):
    """
    启动子强度预测器
    
    基于序列特征预测启动子的相对表达强度（0-100）
    """
    
    def __init__(self, model_type: str = 'gradient_boosting'):
        """
        初始化预测器
        
        Args:
            model_type: 模型类型 ('gradient_boosting' 或 'random_forest')
        """
        super().__init__(model_name=f"promoter_strength_{model_type}")
        
        self.model_type = model_type
        self.scaler = StandardScaler()
        
        if _SKLEARN_OK:
            if model_type == 'gradient_boosting':
                self.model = GradientBoostingRegressor(
                    n_estimators=200,
                    learning_rate=0.1,
                    max_depth=5,
                    random_state=42
                )
            else:
                self.model = RandomForestRegressor(
                    n_estimators=200,
                    max_depth=10,
                    random_state=42
                )
        else:
            self.model = None
    
    def extract_features(self, sequence: str) -> np.ndarray:
        """
        从启动子序列提取特征
        
        特征包括：
        1. GC 含量
        2. 序列长度
        3. TATA box 相似度
        4. CAAT box 相似度
        5. 二核苷酸频率（16 维）
        6. 三核苷酸频率（64 维）
        7. 位置特异性特征
        
        Args:
            sequence: 启动子序列
        
        Returns:
            特征向量
        """
        seq = sequence.upper()
        features = []
        
        # 1. 基本特征
        features.append(GC(seq))  # GC 含量
        features.append(len(seq))  # 序列长度
        features.append(seq.count('A') / len(seq))  # A 含量
        features.append(seq.count('T') / len(seq))  # T 含量
        features.append(seq.count('G') / len(seq))  # G 含量
        features.append(seq.count('C') / len(seq))  # C 含量
        
        # 2. TATA box 特征（TATAAA 在 -30 到 -25 位置）
        tata_motif = 'TATAAA'
        tata_score = self._find_motif_score(seq, tata_motif)
        features.append(tata_score)
        
        # 3. CAAT box 特征（CCAAT 在 -80 到 -70 位置）
        caat_motif = 'CCAAT'
        caat_score = self._find_motif_score(seq, caat_motif)
        features.append(caat_score)
        
        # 4. GC box 特征（GGGCGG）
        gc_box_motif = 'GGGCGG'
        gc_box_score = self._find_motif_score(seq, gc_box_motif)
        features.append(gc_box_score)
        
        # 5. 二核苷酸频率（16 维）
        dinuc_freq = self._calculate_dinucleotide_frequency(seq)
        features.extend(dinuc_freq)
        
        # 6. 三核苷酸频率（前 20 个最常见的）
        trinuc_freq = self._calculate_trinucleotide_frequency(seq, top_k=20)
        features.extend(trinuc_freq)
        
        # 7. 位置特异性特征（分段 GC 含量）
        segment_gc = self._calculate_segment_gc(seq, n_segments=5)
        features.extend(segment_gc)
        
        # 8. 重复序列特征
        features.append(self._calculate_repeat_score(seq))
        
        # 9. 熵（序列复杂度）
        features.append(self._calculate_entropy(seq))
        
        return np.array(features)
    
    def _find_motif_score(self, sequence: str, motif: str) -> float:
        """
        计算 motif 匹配分数（允许错配）
        
        Returns:
            0-1 之间的分数
        """
        if len(sequence) < len(motif):
            return 0.0
        
        max_score = 0.0
        for i in range(len(sequence) - len(motif) + 1):
            subseq = sequence[i:i+len(motif)]
            matches = sum(1 for a, b in zip(subseq, motif) if a == b)
            score = matches / len(motif)
            max_score = max(max_score, score)
        
        return max_score
    
    def _calculate_dinucleotide_frequency(self, sequence: str) -> List[float]:
        """计算二核苷酸频率"""
        dinucleotides = ['AA', 'AT', 'AG', 'AC',
                         'TA', 'TT', 'TG', 'TC',
                         'GA', 'GT', 'GG', 'GC',
                         'CA', 'CT', 'CG', 'CC']
        
        counts = {dn: 0 for dn in dinucleotides}
        total = len(sequence) - 1
        
        if total <= 0:
            return [0.0] * 16
        
        for i in range(total):
            dinuc = sequence[i:i+2]
            if dinuc in counts:
                counts[dinuc] += 1
        
        return [counts[dn] / total for dn in dinucleotides]
    
    def _calculate_trinucleotide_frequency(self, sequence: str, top_k: int = 20) -> List[float]:
        """计算三核苷酸频率（只返回前 top_k 个）"""
        trinucleotides = ['AAA', 'AAT', 'AAG', 'AAC', 'ATA', 'ATT', 'ATG', 'ATC',
                          'AGA', 'AGT', 'AGG', 'AGC', 'ACA', 'ACT', 'ACG', 'ACC',
                          'TAA', 'TAT', 'TAG', 'TAC']  # 前 20 个
        
        counts = {tn: 0 for tn in trinucleotides}
        total = len(sequence) - 2
        
        if total <= 0:
            return [0.0] * top_k
        
        for i in range(total):
            trinuc = sequence[i:i+3]
            if trinuc in counts:
                counts[trinuc] += 1
        
        return [counts[tn] / total for tn in trinucleotides]
    
    def _calculate_segment_gc(self, sequence: str, n_segments: int = 5) -> List[float]:
        """计算分段 GC 含量"""
        segment_length = len(sequence) // n_segments
        gc_values = []
        
        for i in range(n_segments):
            start = i * segment_length
            end = start + segment_length if i < n_segments - 1 else len(sequence)
            segment = sequence[start:end]
            if len(segment) > 0:
                gc_values.append(GC(segment))
            else:
                gc_values.append(0.0)
        
        return gc_values
    
    def _calculate_repeat_score(self, sequence: str) -> float:
        """计算重复序列得分"""
        if len(sequence) < 4:
            return 0.0
        
        repeats = 0
        for length in [2, 3, 4]:
            for i in range(len(sequence) - length * 2 + 1):
                motif = sequence[i:i+length]
                if sequence[i+length:i+length*2] == motif:
                    repeats += 1
        
        return repeats / len(sequence)
    
    def _calculate_entropy(self, sequence: str) -> float:
        """计算序列熵（复杂度）"""
        if len(sequence) == 0:
            return 0.0
        
        counts = {'A': 0, 'T': 0, 'G': 0, 'C': 0}
        for base in sequence:
            if base in counts:
                counts[base] += 1
        
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / len(sequence)
                entropy -= p * np.log2(p)
        
        return entropy
    
    def train(self, X, y, test_size: float = 0.2, **kwargs):
        """
        训练模型
        
        Args:
            X: 特征矩阵或序列列表
            y: 强度标签（0-100）
            test_size: 测试集比例
        """
        if not _SKLEARN_OK:
            raise ImportError("需要安装 scikit-learn: pip install scikit-learn")
        
        # 如果输入是序列，提取特征
        if isinstance(X[0], str):
            logger.info("从序列提取特征...")
            X = np.array([self.extract_features(seq) for seq in X])
        
        # 分割数据
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        
        # 标准化
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # 训练
        logger.info(f"训练 {self.model_type} 模型...")
        self.model.fit(X_train_scaled, y_train)
        self.is_trained = True
        
        # 评估
        train_score = self.model.score(X_train_scaled, y_train)
        test_score = self.model.score(X_test_scaled, y_test)
        
        logger.info(f"训练集 R²: {train_score:.4f}")
        logger.info(f"测试集 R²: {test_score:.4f}")
        
        # 保存模型
        self.save_model()
        
        return {
            'train_r2': train_score,
            'test_r2': test_score
        }
    
    def predict(self, X) -> np.ndarray:
        """
        预测启动子强度
        
        Args:
            X: 特征矩阵或序列（字符串）
        
        Returns:
            预测强度（0-100）
        """
        # 如果输入是单个序列
        if isinstance(X, str):
            # 如果模型未训练，使用规则驱动预测
            if not self.is_trained:
                return self._rule_based_prediction(X)
            
            features = self.extract_features(X)
            features_scaled = self.scaler.transform([features])
            prediction = self.model.predict(features_scaled)[0]
            return np.clip(prediction, 0, 100)
        
        # 如果输入是序列列表
        if isinstance(X[0], str):
            # 如果模型未训练，使用规则驱动预测
            if not self.is_trained:
                return np.array([self._rule_based_prediction(seq) for seq in X])
            
            X = np.array([self.extract_features(seq) for seq in X])
        
        # 如果模型未训练，返回默认值
        if not self.is_trained:
            return np.array([50.0] * len(X))
        
        X_scaled = self.scaler.transform(X)
        predictions = self.model.predict(X_scaled)
        return np.clip(predictions, 0, 100)
    
    def _rule_based_prediction(self, sequence: str) -> float:
        """
        基于规则的启动子强度预测（当模型未训练时使用）
        
        Args:
            sequence: 启动子序列
        
        Returns:
            预测强度（0-100）
        """
        score = 50.0  # 基础分数
        
        # GC 含量影响（最优 40-60%）
        gc_content = GC(sequence)
        if 40 <= gc_content <= 60:
            score += 10
        elif gc_content < 30 or gc_content > 70:
            score -= 10
        
        # TATA box 存在性
        if 'TATAAA' in sequence or 'TATAAT' in sequence:
            score += 15
        
        # CAAT box 存在性
        if 'CCAAT' in sequence:
            score += 10
        
        # GC box 存在性
        if 'GGGCGG' in sequence or 'GGGGCG' in sequence:
            score += 10
        
        # 序列长度影响
        if 100 <= len(sequence) <= 500:
            score += 5
        elif len(sequence) < 50:
            score -= 10
        
        return np.clip(score, 0, 100)
    
    def _calculate_metrics(self, y_true, y_pred) -> Dict:
        """计算回归指标"""
        if not _SKLEARN_OK:
            return {}
        
        return {
            'mse': mean_squared_error(y_true, y_pred),
            'rmse': np.sqrt(mean_squared_error(y_true, y_pred)),
            'mae': mean_absolute_error(y_true, y_pred),
            'r2': r2_score(y_true, y_pred)
        }
    
    def predict_with_confidence(self, sequence: str) -> Tuple[float, str]:
        """
        预测启动子强度并返回置信度描述
        
        Args:
            sequence: 启动子序列
        
        Returns:
            (预测强度, 置信度描述)
        """
        strength = self.predict(sequence)
        
        # 根据强度分类
        if strength >= 80:
            category = "强启动子 (Strong)"
        elif strength >= 60:
            category = "中强启动子 (Medium-Strong)"
        elif strength >= 40:
            category = "中等启动子 (Medium)"
        elif strength >= 20:
            category = "弱启动子 (Weak)"
        else:
            category = "极弱启动子 (Very Weak)"
        
        return strength, category
    
    def get_feature_importance(self) -> Optional[pd.DataFrame]:
        """
        获取特征重要性
        
        Returns:
            特征重要性 DataFrame
        """
        if not self.is_trained or not hasattr(self.model, 'feature_importances_'):
            return None
        
        feature_names = [
            'GC_content', 'Length', 'A_content', 'T_content', 'G_content', 'C_content',
            'TATA_score', 'CAAT_score', 'GC_box_score'
        ]
        feature_names += [f'Dinuc_{i}' for i in range(16)]
        feature_names += [f'Trinuc_{i}' for i in range(20)]
        feature_names += [f'Segment_GC_{i}' for i in range(5)]
        feature_names += ['Repeat_score', 'Entropy']
        
        importance_df = pd.DataFrame({
            'Feature': feature_names,
            'Importance': self.model.feature_importances_
        }).sort_values('Importance', ascending=False)
        
        return importance_df


# ═══════════════════════════════════════════════════════════════════
#  训练数据生成器（用于演示和初始化）
# ═══════════════════════════════════════════════════════════════════

def generate_training_data() -> Tuple[List[str], List[float]]:
    """
    生成训练数据（基于已知启动子）
    
    Returns:
        (序列列表, 强度列表)
    """
    # 已知启动子数据（来自文献和 iGEM）
    known_promoters = [
        # 强启动子
        ("TTGACAATTAATCATCGGCTCGTATAATGTGTGGAATTGTGAGCGGATAACAATTTCACACAGGAAACAGACCATG", 95),  # T7
        ("GGCTGCAGGTCGACGGATCCCCGGAATTCGATATCAAGCTTATCGATACCGTCGACCTCGAGGGGGGGCCCGGTACCCAATTCGCCCTATAGTGAGTCGTATTACAATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCTGGCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGCGAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGGCGCTTTGCCTGGTTTCCGGCACCAGAAGCGGTGCCGGAAAGCTGGCTGGAGTGCGATCTTCCTGAGGCCGATACTGTCGTCGTCCCCTCAAACTGGCAGATGCACGGTTACGATGCGCCCATCTACACCAACGTGACCTATCCCATTACGGTCAATCCGCCGTTTGTTCCCACGGAGAATCCGACGGGTTGTTACTCGCTCACATTTAATGTTGATGAAAGCTGGCTACAGGAAGGCCAGACGCGAATTATTTTTGATGGCGTTCCTATTGGTTAAAAAATGAGCTGATTTAACAAAAATTTAATGCGAATTTTAACAAAATATTAACGTTTACAATTTAAATATTTGCTTATACAATCTTCCTGTTTTTGGGGCTTTTCTGATTATCAACCGGGGTACATATGATTGACATGCTAGTTTTACGATTACCGTTCATCGATTCTCTTGTTTGCTCCAGACTCTCAGGCAATGACCTGATAGCCTTTGTAGATCTCTCAAAAATAGCTACCCTCTCCGGCATTAATTTATCAGCTAGAACGGTTGAATATCATATTGATGGTGATTTGACTGTCTCCGGCCTTTCTCACCCTTTTGAATCTTTACCTACACATTACTCAGGCATTGCATTTAAAATATATGAGGGTTCTAAAAATTTTTATCCTTGCGTTGAAATAAAGGCTTCTCCCGCAAAAGTATTACAGGGTCATAATGTTTTTGGTACAACCGATTTAGCTTTATGCTCTGAGGCTTTATTGCTTAATTTTGCTAATTCTTTGCCTTGCCTGTATGATTTATTGGATGTT", 90),  # 35S
        
        # 中强启动子
        ("AAGCTTGCATGCCTGCAGGTCGACTCTAGAGGATCCCCGGGTACCGAGCTCGAATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCTGGCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGCGAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGG", 65),  # ZmUbi
        
        # 中等启动子
        ("TCCCTATCAGTGATAGAGATTGACATCCCTATCAGTGATAGAGATACTGAGCAC", 50),  # Minimal CMV
        
        # 弱启动子
        ("TTGACGGCTAGCTCAGTCCTAGGTATAATGCTAGC", 25),  # Weak synthetic
        ("ATGCTAGCTAGCTAGCTAGCTAGCTAGCTAGC", 15),  # Very weak
    ]
    
    sequences = [seq for seq, _ in known_promoters]
    strengths = [strength for _, strength in known_promoters]
    
    return sequences, strengths


if __name__ == "__main__":
    # 测试代码
    print("=" * 60)
    print("启动子强度预测器测试")
    print("=" * 60)
    
    # 创建预测器
    predictor = PromoterStrengthPredictor()
    
    # 测试序列
    test_seq = "TTGACAATTAATCATCGGCTCGTATAATGTGTGGAATTGTGAGCGGATAACAATTTCACACAGGAAACAGACCATG"
    
    # 提取特征
    features = predictor.extract_features(test_seq)
    print(f"\n特征维度: {len(features)}")
    
    # 预测（规则驱动）
    strength, category = predictor.predict_with_confidence(test_seq)
    print(f"\n预测强度: {strength:.2f}")
    print(f"分类: {category}")
    
    print("\n" + "=" * 60)
