#!/usr/bin/env python3
"""v3: 多脸匹配策略 —— 取每张照片所有检测到的人脸，
两组之间如果有任一对脸相似度高 → 判定同主体"""
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

def all_face_embeddings(path, thresh=0.3, max_faces=5):
    """返回 [(bbox, embedding), ...] 取面积最大的前 max_faces 张"""
    img = cv2.imread(path)
    if img is None:
        return []
    h, w = img.shape[:2]
    det = get_detector(w, h, thresh)
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return []
    # 按面积降序取前 max_faces
    order = sorted(range(len(faces)), key=lambda i: faces[i][2]*faces[i][3], reverse=True)
    rec = get_rec()
    embs = []
    for i in order[:max_faces]:
        try:
            aligned = rec.alignCrop(img, faces[i])
            emb = rec.feature(aligned)
            embs.append((faces[i], emb))
        except Exception:
            continue
    return embs

def best_pair_similarity(embs1, embs2):
    """两组脸之间的最大配对相似度"""
    if not embs1 or not embs2:
        return None
    rec = get_rec()
    best = -1.0
    for _, e1 in embs1:
        for _, e2 in embs2:
            s = float(rec.match(e1, e2, cv2.FaceRecognizerSF_FR_COSINE))
            if s > best:
                best = s
    return best

def main():
    pairs = [
        ('DSC_2983.JPG', 'DSC_2986.JPG', '同场景连拍 应高'),
        ('DSC_2983.JPG', 'DSC_2994.JPG', '换人 应低'),
        ('DSC_2983.JPG', 'DSC_3025.JPG', '换人 应低'),
        ('DSC_2994.JPG', 'DSC_3025.JPG', '同人B 应高'),
        ('DSC_3209.JPG', 'DSC_3210.JPG', '组4内 应高'),
        ('DSC_3209.JPG', 'DSC_4924.JPG', '组4/组5 应高'),
        ('DSC_4924.JPG', 'DSC_4925.JPG', '组5内 应高'),
        ('DSC_3196.JPG', 'DSC_3200.JPG', '组2/组3 ?'),
        ('DSC_5094.JPG', 'DSC_5098.JPG', '组6内 应高'),
    ]
    print("=" * 80)
    for a, b, note in pairs:
        ea = all_face_embeddings(os.path.join(FOLDER, a))
        eb = all_face_embeddings(os.path.join(FOLDER, b))
        s = best_pair_similarity(ea, eb)
        s_str = f"{s:.3f}" if s is not None else "无脸"
        print(f"{a} vs {b} [{note}]: {s_str} ({len(ea)}脸 vs {len(eb)}脸)")
    print("=" * 80)

if __name__ == "__main__":
    main()
