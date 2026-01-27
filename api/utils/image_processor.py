# utils/image_processor.py
import numpy as np
from PIL import Image, ImageDraw

def preprocess_image(input_img: Image.Image, target_size=(640, 640)):
    """이미지를 모델 입력 규격에 맞게 변환"""
    # RGB 변환 및 리사이즈
    img = input_img.convert("RGB").resize(target_size)
    img_array = np.array(img).transpose(2, 0, 1) # (H,W,C) -> (C,H,W)
    # 정규화 및 배치 차원 추가
    img_array = np.expand_dims(img_array, axis=0).astype(np.float32) / 255.0
    return img_array

def draw_boxes(image: Image.Image, predictions: list, target_size=640):
    """이미지 위에 탐지된 박스 그리기"""
    draw = ImageDraw.Draw(image)
    orig_w, orig_h = image.size
    
    # 스케일 비율 계산
    x_scale = orig_w / target_size
    y_scale = orig_h / target_size

    for det in predictions:
        box = det['box'] # [x1, y1, x2, y2]
        # 좌표 복원
        x1, y1 = box[0] * x_scale, box[1] * y_scale
        x2, y2 = box[2] * x_scale, box[3] * y_scale
        
        # 박스와 라벨 그리기
        draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
        label = f"ID:{det['class_id']} ({det['confidence']:.2f})"
        draw.text((x1, y1 - 10), label, fill="red")
    
    return image