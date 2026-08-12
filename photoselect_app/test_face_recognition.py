#!/usr/bin/env python3
"""验证 SFace 人脸识别在同主体分组中的效果。
关键问题：
1. DSC_2983 vs DSC_2994（用户说换人了）应该相似度低
2. DSC_3209 vs DSC_4924（用户说同一人不同构图）应该相似度高
3. 组内连续照片应高相似
"""
import cv2
import numpy as np
import os

DET_MODEL = r"E:\photoselect\photoselect_app\assets\models\face_detection_yunet_2023mar.onnx"
REC_MODEL = r"E:\photoselect\photoselect_app\assets\models\mobilefacenet.onnx"
FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"

_det_cache = {}
_rec = None

def get_detector(w, h):
    key = (w, h)
    if key not in _det_cache:
        d = cv2.FaceDetectorYN.create(DET_MODEL, '', (w, h), score_threshold=0.6)
        d.setInputSize((w, h))
        _det_cache[key] = d
    return _det_cache[key]

def get_rec():
    global _rec
    if _rec is None:
        _rec = cv2.FaceRecognizerSF.create(REC_MODEL, '')
    return _rec

def get_embeddings(path):
    """返回 [(bbox, embedding), ...]"""
    img = cv2.imread(path)
    if img is None:
        return []
    h, w = img.shape[:2]
    det = get_detector(w, h)
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return []
    rec = get_rec()
    embs = []
    for f in faces:
        try:
            aligned = rec.alignCrop(img, f)
            emb = rec.feature(aligned)
            embs.append((f, emb))
        except Exception:
            continue
    return embs

def best_similarity(embs1, embs2):
    """两组 embedding 之间的最大余弦相似度"""
    if not embs1 or not embs2:
        return None
    rec = get_rec()
    best = -1.0
    for _, e1 in embs1:
        for _, e2 in embs2:
            s = float(rec.match(e1, e2, cv2.FaceRecognizerSF_FR_COSINE))
            best = max(best, s)
    return best

def main():
    pairs = [
        # (A, B, 期望, 说明)
        ('DSC_2983.JPG', 'DSC_2986.JPG', 'high', '同场景连续拍'),
        ('DSC_2983.JPG', 'DSC_2994.JPG', 'low',  '用户说换人了'),
        ('DSC_2983.JPG', 'DSC_3025.JPG', '?',    '用户说2994起换人，3025应该也是另一人'),
        ('DSC_2994.JPG', 'DSC_3025.JPG', 'high', '同组17张里，2994-3025同一人'),
        ('DSC_3209.JPG', 'DSC_3210.JPG', 'high', '组4内部'),
        ('DSC_3209.JPG', 'DSC_4924.JPG', 'high', '用户说组4/组5同一人不同构图'),
        ('DSC_4924.JPG', 'DSC_4925.JPG', 'high', '组5内部'),
        ('DSC_3196.JPG', 'DSC_3200.JPG', '?',    '组2/组3'),
        ('DSC_5094.JPG', 'DSC_5098.JPG', '?',    '组6内部'),
    ]
    print("=" * 70)
    for a, b, expect, note in pairs:
        pa = os.path.join(FOLDER, a)
        pb = os.path.join(FOLDER, b)
        ea = get_embeddings(pa)
        eb = get_embeddings(pb)
        s = best_similarity(ea, eb)
        s_str = f"{s:.3f}" if s is not None else "无脸"
        face_note = f"({len(ea)}脸 vs {len(eb)}脸)"
        print(f"{a} vs {b} [{expect}][{note}]: {s_str} {face_note}")

    print("=" * 70)
    print("SFace 余弦相似度经验值：>0.3 通常同一人；<0.2 通常不同人")

if __name__ == "__main__":
    main()
