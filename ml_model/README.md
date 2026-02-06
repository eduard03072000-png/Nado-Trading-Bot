# ML Модуль для предсказания трендов

## Описание
Модуль машинного обучения для предсказания направления движения цены на основе исторических данных.

## Компоненты

### TrendPredictor
Основной класс для предсказания направления тренда.
- Использует технические индикаторы (RSI, MACD, MA)
- Может работать как с обученной моделью, так и с простым анализом
- Возвращает направление ("up", "down", "sideways") и уверенность (0-1)

### ModelTrainer
Класс для обучения Random Forest модели.
- Готовит данные из исторических цен
- Обучает классификатор на 3 класса (рост/падение/боковик)
- Выводит метрики точности

### HistoricalDataManager
Управление историческими данными.
- Сохранение/загрузка истории цен
- Генерация тестовых данных

## Использование

### Обучение модели
```bash
python ml_model/train_model.py
```

### В боте
```python
from ml import TrendPredictor

predictor = TrendPredictor(model_path="ml_model/trained_model.pkl")
direction, confidence = predictor.predict(price_history)

if direction == "up" and confidence > 0.7:
    # Открываем LONG
    pass
```

## Требования
- numpy
- scikit-learn
- pandas
