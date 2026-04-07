"""pytest 配置：将 src 加入 Python 路径"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
