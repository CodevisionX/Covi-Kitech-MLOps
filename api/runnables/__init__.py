# runnables/__init__.py
from .yolo_runnable import YoloRunnable
from .cnn_runnable import CnnRunnable

# 외부에서 'from runnables import *'를 할 때 노출될 클래스 정의
__all__ = ["YoloRunnable", "CnnRunnable"]