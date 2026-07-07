"""pytest 配置：确保根目录在 sys.path。"""
import os
import sys

# 把项目根加入 import path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
