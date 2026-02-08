"""
NADO DEX Trading Dashboard
Комплексный инструмент для управления торговлей
"""
import sys
import os
import json
import time

# Исправление кодировки для Windows
if os.name == 'nt':  # Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import PlaceMarketOrderParams
from nado_protocol.utils.execute import MarketOrderParams
from nado_protocol.utils import SubaccountParams, subaccount_to_hex
from decimal import ROUND_DOWN
import config
from decimal import Decimal
import time
from datetime import datetime
