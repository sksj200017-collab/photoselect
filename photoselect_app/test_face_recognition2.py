#!/usr/bin/env python3
"""v2: 只用主体人脸（最大脸）做匹配 + 降低检测阈值"""
import cv2
import numpy as np
import os

DET_MODEL = r"E:\photoselect\photoselect_app\assets\models\face_detection_yunet_2023mar.onnx"
REC_MODEL = r"E:\photoselect\photoselect_app\assets\models\mobilefacenet.onnx"
FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"

_det_cache = {}
_rec = None

def get_detector(w, h, thresh):
    key = (w, h, thresh)
    if key not in _det_cache:
        d = cv2.FaceDetectorYN.create(DET_MODEL, '', (w, h), score_threshold=thresh)
        d.setInputSize((w, h))
        _det_cache[key] = d
    return _det_cache[key]

def get_rec():
    global _rec
    if _rec is None:
        _rec = cv2.FaceRecognizerSF.create(REC_MODEL, '')
    return _rec

def main_face_embedding(path, thresh=0.3):
    """返回 (bbox, embedding) 只取最大人脸；无脸返回 None"""
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    det = get_detector(w, h, thresh)
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    # 取面积最大的人脸
    areas = [f[2] * f[3] for f in faces]
    best = faces[int(np.argmax(areas))]
    rec = get_rec()
    try:
        aligned = rec.alignCrop(img, best)
        emb = rec.feature(aligned)
        return (best, emb)
    except Exception:
        return None

def similarity(e1, e2):
    if e1 is None or e2 is None:
        return None
    rec = get_rec()
    return float(rec.match(e1[1], e2[1], cv2.FaceRecognizerSF_FR_COSINE))

def main():
    pairs = [
        ('DSC_2983.JPG', 'DSC_2986.JPG', '同场景连拍 应高'),
        ('DSC_2983.JPG', 'DSC_2994.JPG', '换人 应低'),
        ('DSC_2983.JPG', 'DSC_3025.JPG', '换人 应低'),
        ('DSC_2994.JPG', 'DSC_3025.JPG', '同人 应高'),
        ('DSC_3209.JPG', 'DSC_3210.JPG', '组4内 应高'),
        ('DSC_3209.JPG', 'DSC_4924.JPG', '组4/组5 应高'),
        ('DSC_4924.JPG', 'DSC_4925.JPG', '组5内 应高'),
        ('DSC_3196.JPG', 'DSC_3200.JPG', '组2/组3 ?'),
        ('DSC_5094.JPG', 'DSC_5098.JPG', '组6内 应高'),
    ]
    print("=" * 78)
    for a, b, note in pairs:
        ea = main_face_embedding(os.path.join(FOLDER, a))
        eb = main_face_embedding(os.path.join(FOLDER, b))
        s = similarity(ea, eb)
        s_str = f"{s:.3f}" if s is not None else "无脸"
        fa = f"{ea[0][2]:.0f}x{ea[0][3]:.0f}" if ea else "-"
        fb = f"{eb[0][2]:.0f}x{eb[0][3]:.0f}" if eb else "-"
        print(f"{a} vs {b} [{note}]: {s_str} (主脸 {fa} vs {fb})")
    print("=" * 78)

if __name__ == "__main__":
    main()
