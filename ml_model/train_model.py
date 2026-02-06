"""
Скрипт для обучения ML модели
Запуск: python train_model.py
"""
import sys
from pathlib import Path

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ml import ModelTrainer, HistoricalDataManager
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Основная функция обучения"""
    
    print("=" * 60)
    print("🎓 ОБУЧЕНИЕ ML МОДЕЛИ ДЛЯ ПРЕДСКАЗАНИЯ ТРЕНДОВ")
    print("=" * 60)
    
    # Инициализация
    data_manager = HistoricalDataManager()
    trainer = ModelTrainer()
    
    symbol = "BTC-USDT"
    
    # Проверяем наличие данных
    prices = data_manager.load_prices(symbol)
    
    if len(prices) < 100:
        print(f"\n⚠️ Недостаточно исторических данных ({len(prices)} цен)")
        print("📊 Генерируем тестовые данные...")
        prices = data_manager.generate_sample_data(symbol, count=2000)
    
    print(f"\n📊 Загружено цен: {len(prices)}")
    print(f"💰 Диапазон: {min(prices):.2f} - {max(prices):.2f}")
    
    # Обучение
    print("\n🎓 Начинаем обучение...")
    metrics = trainer.train(prices, test_size=0.2)
    
    if metrics:
        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТЫ ОБУЧЕНИЯ")
        print("=" * 60)
        print(f"✅ Обучено примеров: {metrics['samples_trained']}")
        print(f"📈 Точность на обучении: {metrics['train_accuracy']:.2%}")
        print(f"📈 Точность на тесте: {metrics['test_accuracy']:.2%}")
        
        # Детальный отчет
        report = metrics['classification_report']
        print("\n📋 Детальная статистика:")
        for label in ['Down', 'Sideways', 'Up']:
            if label in report:
                stats = report[label]
                print(f"  {label:10} - Precision: {stats['precision']:.2%}, "
                      f"Recall: {stats['recall']:.2%}, "
                      f"F1: {stats['f1-score']:.2%}")
        
        # Сохранение модели
        model_path = "ml_model/trained_model.pkl"
        Path("ml_model").mkdir(exist_ok=True)
        
        import pickle
        with open(model_path, 'wb') as f:
            pickle.dump(trainer.get_model(), f)
        
        print(f"\n✅ Модель сохранена: {model_path}")
        
    else:
        print("\n❌ Обучение не удалось")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
