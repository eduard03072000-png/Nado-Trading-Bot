"""
Класс для обучения ML модели на исторических данных
"""
import numpy as np
from typing import List, Tuple
from decimal import Decimal
import logging
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Класс для обучения модели предсказания трендов
    """
    
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        self.trained = False
    
    def prepare_training_data(
        self,
        price_history: List[Decimal],
        lookback: int = 20,
        prediction_horizon: int = 5
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Подготовить данные для обучения
        
        Args:
            price_history: История цен
            lookback: Сколько периодов использовать для признаков
            prediction_horizon: На сколько периодов вперед предсказывать
        
        Returns:
            (X, y) - признаки и метки классов
        """
        prices = np.array([float(p) for p in price_history])
        
        X = []
        y = []
        
        # Генерируем обучающие примеры
        for i in range(lookback, len(prices) - prediction_horizon):
            # Признаки: последние lookback цен
            window = prices[i-lookback:i]
            
            # Вычисляем признаки
            features = self._extract_features(window)
            
            # Метка класса: направление движения через prediction_horizon
            future_price = prices[i + prediction_horizon]
            current_price = prices[i]
            
            price_change = (future_price - current_price) / current_price
            
            # Классификация: 0 = down, 1 = sideways, 2 = up
            if price_change > 0.005:  # +0.5%
                label = 2  # up
            elif price_change < -0.005:  # -0.5%
                label = 0  # down
            else:
                label = 1  # sideways
            
            X.append(features)
            y.append(label)
        
        return np.array(X), np.array(y)
    
    def _extract_features(self, window: np.ndarray) -> List[float]:
        """Извлечь признаки из окна цен"""
        features = []
        
        # 1. Процентные изменения
        returns = np.diff(window) / window[:-1]
        features.extend([
            np.mean(returns),
            np.std(returns),
            np.min(returns),
            np.max(returns)
        ])
        
        # 2. Скользящие средние
        ma_5 = np.mean(window[-5:]) if len(window) >= 5 else window[-1]
        ma_10 = np.mean(window[-10:]) if len(window) >= 10 else window[-1]
        
        features.extend([
            (window[-1] - ma_5) / ma_5,
            (window[-1] - ma_10) / ma_10,
            (ma_5 - ma_10) / ma_10 if ma_10 != 0 else 0
        ])
        
        # 3. Моментум
        if len(window) >= 5:
            momentum = (window[-1] - window[-5]) / window[-5]
        else:
            momentum = 0
        features.append(momentum)
        
        # 4. Относительная позиция в диапазоне
        price_range = np.max(window) - np.min(window)
        if price_range > 0:
            relative_position = (window[-1] - np.min(window)) / price_range
        else:
            relative_position = 0.5
        features.append(relative_position)
        
        return features
    
    def train(
        self,
        price_history: List[Decimal],
        test_size: float = 0.2
    ) -> dict:
        """
        Обучить модель на исторических данных
        
        Args:
            price_history: История цен
            test_size: Доля данных для тестирования
        
        Returns:
            Словарь с метриками
        """
        logger.info("🎓 Начинаем обучение модели...")
        
        # Подготовка данных
        X, y = self.prepare_training_data(price_history)
        
        if len(X) == 0:
            logger.error("❌ Недостаточно данных для обучения")
            return {}
        
        logger.info(f"📊 Подготовлено примеров: {len(X)}")
        logger.info(f"📊 Распределение классов: {np.bincount(y)}")
        
        # Разделение на train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        
        # Обучение
        self.model.fit(X_train, y_train)
        self.trained = True
        
        # Оценка
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)
        
        # Предсказания
        y_pred = self.model.predict(X_test)
        
        logger.info(f"✅ Обучение завершено!")
        logger.info(f"📈 Точность на train: {train_score:.2%}")
        logger.info(f"📈 Точность на test: {test_score:.2%}")
        
        # Детальный отчет
        report = classification_report(
            y_test, y_pred,
            target_names=['Down', 'Sideways', 'Up'],
            output_dict=True
        )
        
        return {
            'train_accuracy': train_score,
            'test_accuracy': test_score,
            'classification_report': report,
            'samples_trained': len(X_train)
        }
    
    def predict(self, features: np.ndarray) -> Tuple[str, float]:
        """
        Предсказать направление по признакам
        
        Returns:
            (направление, уверенность)
        """
        if not self.trained:
            return "sideways", 0.5
        
        # Предсказание
        prediction = self.model.predict([features])[0]
        probabilities = self.model.predict_proba([features])[0]
        
        # Преобразование в читаемый вид
        direction_map = {0: "down", 1: "sideways", 2: "up"}
        direction = direction_map[prediction]
        confidence = probabilities[prediction]
        
        return direction, confidence
    
    def get_model(self):
        """Получить обученную модель"""
        return self.model if self.trained else None
