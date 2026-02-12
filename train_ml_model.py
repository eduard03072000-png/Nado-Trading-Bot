"""
ML Model Training Script
Обучает модель предсказания направления тренда
"""
import asyncio
import numpy as np
import pickle
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import logging

from historical_data_provider import HistoricalDataProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def prepare_features(candles, lookback=20):
    """
    Подготовить features для ML из свечей
    
    Args:
        candles: List[Dict] - исторические свечи
        lookback: int - количество периодов назад
    
    Returns:
        X: features array
        y: labels array (1=UP, 0=DOWN, -1=SIDEWAYS)
    """
    X = []
    y = []
    
    for i in range(lookback, len(candles) - 1):
        window = candles[i-lookback:i]
        
        # Извлекаем цены
        closes = np.array([c['close'] for c in window])
        volumes = np.array([c['volume'] for c in window])
        highs = np.array([c['high'] for c in window])
        lows = np.array([c['low'] for c in window])
        
        # Feature engineering
        features = []
        
        # 1. Price returns
        returns = np.diff(closes) / closes[:-1]
        features.extend([
            np.mean(returns),
            np.std(returns),
            np.max(returns),
            np.min(returns)
        ])
        
        # 2. Moving averages
        ma_5 = np.mean(closes[-5:])
        ma_10 = np.mean(closes[-10:])
        ma_20 = np.mean(closes)
        current_price = closes[-1]
        
        features.extend([
            (current_price - ma_5) / ma_5,
            (current_price - ma_10) / ma_10,
            (current_price - ma_20) / ma_20,
            (ma_5 - ma_10) / ma_10,
            (ma_10 - ma_20) / ma_20
        ])
        
        # 3. RSI (simplified)
        gains = returns[returns > 0]
        losses = -returns[returns < 0]
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        features.append(rsi / 100)  # Normalize
        
        # 4. Volatility
        volatility = np.std(returns)
        features.append(volatility)
        
        # 5. Volume indicators
        avg_volume = np.mean(volumes)
        current_volume = volumes[-1]
        features.extend([
            (current_volume - avg_volume) / avg_volume,
            np.std(volumes) / avg_volume
        ])
        
        # 6. Price range
        avg_range = np.mean(highs - lows)
        current_range = highs[-1] - lows[-1]
        features.append((current_range - avg_range) / avg_range)
        
        X.append(features)
        
        # Label: следующая свеча вверх/вниз/боком
        next_close = candles[i+1]['close']
        current_close = candles[i]['close']
        change = (next_close - current_close) / current_close
        
        if change > 0.005:  # >0.5% - UP
            y.append(1)
        elif change < -0.005:  # <-0.5% - DOWN
            y.append(0)
        else:  # Sideways
            y.append(-1)
    
    return np.array(X), np.array(y)


async def train_model():
    """Обучить ML модель"""
    logger.info("=== ML MODEL TRAINING ===")
    
    async with HistoricalDataProvider() as provider:
        all_X = []
        all_y = []
        
        # Загружаем данные для всех продуктов
        products = {
            2: "BTC",
            4: "ETH",
            8: "SOL"
        }
        
        for product_id, name in products.items():
            logger.info(f"\n[{name}] Loading data...")
            
            # Получаем 30 дней данных (больше = лучше)
            candles = await provider.get_historical_klines(
                product_id=product_id,
                interval="1h",
                days=30
            )
            
            if not candles:
                logger.error(f"[{name}] No data!")
                continue
            
            # Подготавливаем features
            X, y = prepare_features(candles, lookback=24)
            
            logger.info(f"[{name}] Features: {X.shape}, Labels: {len(y)}")
            logger.info(f"[{name}] UP: {sum(y==1)}, DOWN: {sum(y==0)}, SIDEWAYS: {sum(y==-1)}")
            
            all_X.append(X)
            all_y.append(y)
        
        # Объединяем все данные
        X_combined = np.vstack(all_X)
        y_combined = np.concatenate(all_y)
        
        logger.info(f"\n=== COMBINED DATASET ===")
        logger.info(f"Total samples: {len(X_combined)}")
        logger.info(f"UP: {sum(y_combined==1)} ({sum(y_combined==1)/len(y_combined)*100:.1f}%)")
        logger.info(f"DOWN: {sum(y_combined==0)} ({sum(y_combined==0)/len(y_combined)*100:.1f}%)")
        logger.info(f"SIDEWAYS: {sum(y_combined==-1)} ({sum(y_combined==-1)/len(y_combined)*100:.1f}%)")
        
        # Убираем SIDEWAYS для упрощения (бинарная классификация)
        mask = y_combined != -1
        X_filtered = X_combined[mask]
        y_filtered = y_combined[mask]
        
        logger.info(f"\nFiltered dataset (UP/DOWN only): {len(X_filtered)} samples")
        
        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X_filtered, y_filtered,
            test_size=0.2,
            random_state=42
        )
        
        logger.info(f"\n=== TRAINING ===")
        logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")
        
        # Обучаем Random Forest
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        
        model.fit(X_train, y_train)
        
        # Оценка
        train_pred = model.predict(X_train)
        test_pred = model.predict(X_test)
        
        train_acc = accuracy_score(y_train, train_pred)
        test_acc = accuracy_score(y_test, test_pred)
        
        logger.info(f"\n=== RESULTS ===")
        logger.info(f"Train Accuracy: {train_acc:.2%}")
        logger.info(f"Test Accuracy: {test_acc:.2%}")
        logger.info(f"\nClassification Report:")
        print(classification_report(y_test, test_pred, target_names=['DOWN', 'UP']))
        
        # Важность features
        feature_importance = model.feature_importances_
        logger.info(f"\nTop 5 Important Features:")
        top_indices = np.argsort(feature_importance)[-5:][::-1]
        for idx in top_indices:
            logger.info(f"  Feature {idx}: {feature_importance[idx]:.4f}")
        
        # Сохраняем модель
        model_path = Path("ml_model_trained.pkl")
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        
        logger.info(f"\n[OK] Model saved to {model_path}")
        logger.info(f"[OK] Test Accuracy: {test_acc:.2%}")
        
        return model, test_acc


if __name__ == "__main__":
    asyncio.run(train_model())
