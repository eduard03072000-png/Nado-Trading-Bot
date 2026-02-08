"""
Patch telegram_trading_bot.py to use per-user dashboards.
Adds `dashboard = ensure_dashboard(update.effective_user.id)` to each handler that uses dashboard.
"""
import re

with open(r'C:\Project\Trading_bot\telegram_trading_bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern: find async def handlers that reference `dashboard.` but don't already have `ensure_dashboard`
# We need to add: dashboard = ensure_dashboard(update.effective_user.id)
# After the first line of each function body

lines = content.split('\n')
result = []
i = 0
patched_count = 0

while i < len(lines):
    line = lines[i]
    result.append(line)
    
    # Detect async def handler(update, context) pattern
    match = re.match(r'^async def \w+\(update.*context.*\):', line)
    if match:
        func_name = re.search(r'async def (\w+)', line).group(1)
        
        # Look ahead to see if this function uses `dashboard.` or `dashboard,`
        # and doesn't already have ensure_dashboard
        lookahead = '\n'.join(lines[i+1:min(i+100, len(lines))])
        
        # Find end of function (next function def or end of file)
        func_end = len(lines)
        for j in range(i+1, min(i+200, len(lines))):
            if re.match(r'^(async )?def \w+', lines[j]) or re.match(r'^class \w+', lines[j]):
                func_end = j
                break
        
        func_body = '\n'.join(lines[i+1:func_end])
        
        uses_dashboard = 'dashboard.' in func_body or 'dashboard,' in func_body
        already_patched = 'ensure_dashboard' in func_body
        
        # Skip start and handle_subaccount_input (they handle dashboard differently)
        skip_funcs = ['start', 'handle_subaccount_input', 'main', 'cancel']
        
        if uses_dashboard and not already_patched and func_name not in skip_funcs:
            # Find the docstring or first code line after the def
            j = i + 1
            # Skip docstring
            if j < len(lines) and '"""' in lines[j]:
                result.append(lines[j])
                j += 1
                # Multi-line docstring
                if lines[j-1].count('"""') < 2:
                    while j < len(lines) and '"""' not in lines[j]:
                        result.append(lines[j])
                        j += 1
                    if j < len(lines):
                        result.append(lines[j])
                        j += 1
                i = j
                # Now insert our line
                # Detect indentation from the next code line
                indent = '    '
                result.append(f'{indent}dashboard = ensure_dashboard(update.effective_user.id)')
                patched_count += 1
                print(f"  Patched: {func_name}")
                continue
            else:
                # No docstring, insert right after def
                i = j
                indent = '    '
                result.append(f'{indent}dashboard = ensure_dashboard(update.effective_user.id)')
                patched_count += 1
                print(f"  Patched: {func_name}")
                continue
    
    i += 1

print(f"\nTotal patched: {patched_count} functions")

with open(r'C:\Project\Trading_bot\telegram_trading_bot.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(result))

print("Done!")
