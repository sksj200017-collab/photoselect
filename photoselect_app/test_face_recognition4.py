#!/usr/bin/env python3
"""v4: 混合评分 —— 主脸相似度 + ORB 全图匹配 综合判断
设计：
- 人脸相似度（主脸 embedding 余弦）
- ORB 匹配（同主体模式原算法）
- 综合：任一强信号即可合并，但换人时人脸信号覆盖 ORB
"""
import cv2
import numpy as np
import os

DET_MODEL = r"E:\photoselect\photoselect_app\assets\models\face_detection_yunet_2023mar.onnx"
REC_MODEL = r"E:\photoselect\photoselect_app\assets\models\mobilefacenet.onnx"
FOLDER = r"C:\Users\nfd\Desktop\testPhotoSelect"

_det_cache = {}
_rec = None
_orb_cache = {}

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

def main_face_embedding(path, thresh=0.4):
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    det = get_detector(w, h, thresh)
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    areas = [f[2] * f[3] for f in faces]
    best = faces[int(np.argmax(areas))]
    rec = get_rec()
    try:
        aligned = rec.alignCrop(img, best)
        emb = rec.feature(aligned)
        return (best, emb)
    except Exception:
        return None

def face_sim(e1, e2):
    if e1 is None or e2 is None:
        return None
    rec = get_rec()
    return float(rec.match(e1[1], e2[1], cv2.FaceRecognizerSF_FR_COSINE))

def orb_sim(path1, path2):
    """ORB 特征匹配比率（0-1），同主体模式原算法"""
    try:
        kp1, d1 = _orb(path1)
        kp2, d2 = _orb(path2)
        if d1 is None or d2 is None or len(d1) < 10 or len(d2) < 10:
            return 0.0
        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(d1, d2, k=2)
        good = []
        for pair in matches:
            if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
                good.append(pair[0])
        if len(good) < 15:
            return 0.0
        src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None or mask is None:
            return 0.0
        inliers = int(mask.sum())
        ratio = inliers / len(good)
        return ratio if inliers >= 12 else 0.0
    except Exception:
        return 0.0

def _orb(path):
    if path in _orb_cache:
        return _orb_cache[path]
    try:
        from PIL import Image
        img = Image.open(path).convert('RGB')
        img.thumbnail((512, 512))
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        orb = cv2.ORB_create(nfeatures=800)
        kp, des = orb.detectAndCompute(gray, None)
        _orb_cache[path] = (kp, des)
        return (kp, des)
    except Exception:
        _orb_cache[path] = (None, None)
        return (None, None)

def main():
    pairs = [
        ('DSC_2983.JPG', 'DSC_2986.JPG', '同场景连拍'),
        ('DSC_2983.JPG', 'DSC_2994.JPG', '换人!'),
        ('DSC_2983.JPG', 'DSC_3025.JPG', '换人!'),
        ('DSC_2994.JPG', 'DSC_3025.JPG', '同人B?'),
        ('DSC_3209.JPG', 'DSC_3210.JPG', '组4内'),
        ('DSC_3209.JPG', 'DSC_4924.JPG', '组4/组5 同人?'),
        ('DSC_4924.JPG', 'DSC_4925.JPG', '组5内'),
        ('DSC_3196.JPG', 'DSC_3200.JPG', '组2/组3'),
        ('DSC_5094.JPG', 'DSC_5098.JPG', '组6内'),
    ]
    print("=" * 95)
    print(f"{'对比':<38}{'人脸':>7}{'ORB':>7}{'综合':>7}  说明")
    print("-" * 95)
    for a, b, note in pairs:
        pa, pb = os.path.join(FOLDER, a), os.path.join(FOLDER, b)
        ea, eb = main_face_embedding(pa), main_face_embedding(pb)
        fs = face_sim(ea, eb)
        os_ = orb_sim(pa, pb)
        # 综合规则：
        # 两张都有大脸(>100x100)时 → 主要看人脸（换人时构图相同也不合并）
        # 否则 → 看 ORB
        fa = ea[0] if ea else None
        fb = eb[0] if eb else None
        big_face_a = fa is not None and fa[2] > 150 and fa[3] > 150
        big_face_b = fb is not None and fb[2] > 150 and fb[3] > 150
        if fs is None:
            verdict = "ORB:" + ("✓" if os_ > 0.3 else "✗")
        elif big_face_a and big_face_b:
            verdict = "人脸:" + ("✓" if fs > 0.4 else "✗")
        else:
            verdict = "混合:" + ("✓" if (fs and fs > 0.4) or os_ > 0.3 else "✗")
        fs_str = f"{fs:.2f}" if fs is not None else "无脸"
        print(f"{a} vs {b} [{note}]  {fs_str:>7}{os_:>7.2f}  {verdict}")
    print("=" * 95)

if __name__ == "__main__":
    main()
