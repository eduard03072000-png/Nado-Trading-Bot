"""
Автоматическая интеграция улучшений в telegram_trading_bot.py
Запустите этот скрипт для применения изменений
"""

import re
import os

def apply_improvements():
    """Применить улучшения к telegram_trading_bot.py"""
    
    # Получаем директорию скрипта
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    bot_file = os.path.join(script_dir, "telegram_trading_bot.py")
    improved_file = os.path.join(script_dir, "improved_positions.py")
    
    # Читаем файлы
    with open(bot_file, 'r', encoding='utf-8') as f:
        bot_content = f.read()
    
    with open(improved_file, 'r', encoding='utf-8') as f:
        improved_content = f.read()
    
    print("🔧 Применяем улучшения...")
    
    # 1. Добавляем новые states
    print("1️⃣ Добавление новых conversation states...")
    old_states = (
        "WAITING_TPSL_PRODUCT = 15  # Separate state for calculator\n"
        "WAITING_SUBACCOUNT_ID = 16  # For linked signer setup"
    )
    
    new_states = (
        "WAITING_TPSL_PRODUCT = 15  # Separate state for calculator\n"
        "WAITING_SUBACCOUNT_ID = 16  # For linked signer setup\n"
        "WAITING_TP_MODE, WAITING_TP_PRICE, WAITING_TP_PERCENT = range(17, 20)  # For TP setup"
    )
    
    if old_states in bot_content and new_states not in bot_content:
        bot_content = bot_content.replace(old_states, new_states)
        print("   ✅ States добавлены")
    else:
        print("   ⚠️ States уже добавлены или не найдены")
    
    # 2. Заменяем функцию show_positions
    print("2️⃣ Замена функции show_positions...")
    
    # Находим старую функцию
    pattern = r'async def show_positions\(.*?\):\s*""".*?""".*?(?=\n\nasync def |\nclass |\ndef main\(|\Z)'
    
    if re.search(pattern, bot_content, re.DOTALL):
        # Извлекаем новую функцию из improved_positions.py
        new_func_pattern = r'async def show_positions_improved\(.*?\):(.*?)(?=\n\n# ===|\Z)'
        new_func_match = re.search(new_func_pattern, improved_content, re.DOTALL)
        
        if new_func_match:
            new_function = "async def show_positions" + new_func_match.group(0)[len("async def show_positions_improved"):]
            bot_content = re.sub(pattern, new_function, bot_content, count=1, flags=re.DOTALL)
            print("   ✅ show_positions заменена")
        else:
            print("   ❌ Не удалось найти новую функцию")
    else:
        print("   ⚠️ show_positions не найдена")
    
    # 3. Добавляем новые функции перед главной функцией
    print("3️⃣ Добавление новых функций...")
    
    # Извлекаем новые функции из improved_positions
    new_functions = [
        'async def set_tp_menu',
        'async def tp_mode_selected',
        'async def handle_tp_price',
        'async def handle_tp_percent',
        'async def confirm_tp_order'
    ]
    
    functions_to_add = []
    for func_name in new_functions:
        pattern = f'{func_name}\\(.*?\\):(.*?)(?=\\n\\nasync def |\\n\\n# ===|\\Z)'
        match = re.search(pattern, improved_content, re.DOTALL)
        if match:
            functions_to_add.append(match.group(0))
    
    if functions_to_add:
        # Находим место перед def main()
        main_pattern = r'(def main\(\):)'
        insertion_point = f"\n\n# ============ УСТАНОВКА TP ============\n\n{''.join(['\\n\\n' + f for f in functions_to_add])}\n\n\n{main_pattern}"
        
        if 'async def set_tp_menu' not in bot_content:
            bot_content = re.sub(main_pattern, insertion_point, bot_content)
            print(f"   ✅ Добавлено {len(functions_to_add)} функций")
        else:
            print("   ⚠️ Функции уже добавлены")
    else:
        print("   ❌ Не удалось извлечь новые функции")
    
    # 4. Добавляем TP handler в main()
    print("4️⃣ Добавление TP handler...")
    
    # Находим место после tpsl_handler
    tpsl_handler_pattern = r'(# Обработчик TP/SL Calculatorа\s+tpsl_handler = ConversationHandler\(.*?per_message=False\s+\))'
    
    tp_handler_code = '''
    
    # TP Setup Handler
    tp_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_tp_menu, pattern=r'^set_tp_\\d+$')
        ],
        states={
            WAITING_TP_MODE: [
                CallbackQueryHandler(tp_mode_selected, pattern=r'^tp_mode_(price|percent)$')
            ],
            WAITING_TP_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tp_price)
            ],
            WAITING_TP_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tp_percent)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(show_positions, pattern='^positions$')
        ],
        per_message=False
    )'''
    
    if 'tp_handler = ConversationHandler' not in bot_content:
        bot_content = re.sub(
            tpsl_handler_pattern,
            r'\1' + tp_handler_code,
            bot_content,
            flags=re.DOTALL
        )
        print("   ✅ TP handler добавлен")
    else:
        print("   ⚠️ TP handler уже добавлен")
    
    # 5. Регистрируем tp_handler
    print("5️⃣ Регистрация tp_handler...")
    
    add_handler_pattern = r'(application\.add_handler\(tpsl_handler\))'
    
    if 'application.add_handler(tp_handler)' not in bot_content:
        bot_content = re.sub(
            add_handler_pattern,
            r'\1\n    application.add_handler(tp_handler)',
            bot_content
        )
        print("   ✅ tp_handler зарегистрирован")
    else:
        print("   ⚠️ tp_handler уже зарегистрирован")
    
    # 6. Добавляем callback handler для confirm_tp
    print("6️⃣ Добавление callback handler для confirm_tp...")
    
    close_pattern = r'(application\.add_handler\(CallbackQueryHandler\(close_position, pattern=r\'\^close_\\d\+\$\'\)\))'
    
    if 'CallbackQueryHandler(confirm_tp_order' not in bot_content:
        bot_content = re.sub(
            close_pattern,
            r'\1\n    application.add_handler(CallbackQueryHandler(confirm_tp_order, pattern=r\'^confirm_tp_\'))',
            bot_content
        )
        print("   ✅ Callback handler добавлен")
    else:
        print("   ⚠️ Callback handler уже добавлен")
    
    # Сохраняем измененный файл
    backup_file = "telegram_trading_bot_backup.py"
    print(f"\n💾 Создание резервной копии: {backup_file}")
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        with open(bot_file, 'r', encoding='utf-8') as orig:
            f.write(orig.read())
    
    print(f"💾 Сохранение изменений в {bot_file}")
    with open(bot_file, 'w', encoding='utf-8') as f:
        f.write(bot_content)
    
    print("\n✅ Интеграция завершена!")
    print(f"\n📋 Резервная копия сохранена: {backup_file}")
    print(f"📋 Улучшенный файл: {bot_file}")
    print("\n🚀 Теперь можно запустить бота и протестировать новые возможности!")

if __name__ == "__main__":
    try:
        apply_improvements()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
