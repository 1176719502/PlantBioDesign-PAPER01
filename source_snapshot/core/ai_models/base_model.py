# [DORMANT - V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
AI 模型基类
所有 AI 模型的抽象基类，提供统一接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import pickle
import os
import logging

logger = logging.getLogger(__name__)


class BaseAIModel(ABC):
    """AI 模型基类"""
    
    def __init__(self, model_name: str, model_dir: str = "data/ai_models"):
        """
        初始化模型
        
        Args:
            model_name: 模型名称
            model_dir: 模型保存目录
        """
        self.model_name = model_name
        self.model_dir = model_dir
        self.model = None
        self.is_trained = False
        
        # 确保模型目录存在
        os.makedirs(model_dir, exist_ok=True)
        
        # 尝试加载已训练的模型
        self._try_load_model()
    
    @abstractmethod
    def train(self, X, y, **kwargs):
        """
        训练模型
        
        Args:
            X: 特征数据
            y: 标签数据
            **kwargs: 其他训练参数
        """
        pass
    
    @abstractmethod
    def predict(self, X) -> Any:
        """
        预测
        
        Args:
            X: 输入特征
        
        Returns:
            预测结果
        """
        pass
    
    @abstractmethod
    def extract_features(self, input_data: Any) -> Any:
        """
        从原始输入提取特征
        
        Args:
            input_data: 原始输入数据
        
        Returns:
            特征向量
        """
        pass
    
    def save_model(self, filepath: Optional[str] = None):
        """
        保存模型到文件
        
        Args:
            filepath: 保存路径（默认使用 model_dir/model_name.pkl）
        """
        if filepath is None:
            filepath = os.path.join(self.model_dir, f"{self.model_name}.pkl")
        
        try:
            save_data = {
                'model': self.model,
                'is_trained': self.is_trained,
                'metadata': self.get_metadata()
            }
            # Save scaler if it exists
            if hasattr(self, 'scaler'):
                save_data['scaler'] = self.scaler
            
            with open(filepath, 'wb') as f:
                pickle.dump(save_data, f)
            logger.info(f"模型已保存到: {filepath}")
        except Exception as e:
            logger.error(f"保存模型失败: {e}")
    
    def load_model(self, filepath: Optional[str] = None):
        """
        从文件加载模型
        
        Args:
            filepath: 模型文件路径
        """
        if filepath is None:
            filepath = os.path.join(self.model_dir, f"{self.model_name}.pkl")
        
        if not os.path.exists(filepath):
            logger.warning(f"模型文件不存在: {filepath}")
            return False
        
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.model = data.get('model')
                self.is_trained = data.get('is_trained', False)
                # Load scaler if it exists
                if 'scaler' in data and hasattr(self, 'scaler'):
                    self.scaler = data['scaler']
            logger.info(f"模型已加载: {filepath}")
            return True
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            self.is_trained = False
            return False
    
    def _try_load_model(self):
        """尝试加载已保存的模型"""
        self.load_model()
    
    def get_metadata(self) -> Dict:
        """
        获取模型元数据
        
        Returns:
            元数据字典
        """
        return {
            'model_name': self.model_name,
            'is_trained': self.is_trained
        }
    
    def evaluate(self, X_test, y_test) -> Dict:
        """
        评估模型性能
        
        Args:
            X_test: 测试特征
            y_test: 测试标签
        
        Returns:
            评估指标字典
        """
        if not self.is_trained:
            raise ValueError("模型尚未训练")
        
        predictions = self.predict(X_test)
        return self._calculate_metrics(y_test, predictions)
    
    @abstractmethod
    def _calculate_metrics(self, y_true, y_pred) -> Dict:
        """
        计算评估指标
        
        Args:
            y_true: 真实标签
            y_pred: 预测标签
        
        Returns:
            指标字典
        """
        pass
