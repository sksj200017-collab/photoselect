#!/usr/bin/env python3
"""
PhotoSelect 核心引擎 v2
功能：
- 照片分析（dHash / 清晰度 / 亮度 / EXIF 拍摄时间）
- 严格去重模式：dHash 相似分组
- 同主体筛选模式：ORB 特征匹配 + RANSAC（构图不同但主体相同）
- 缩略图缓存
"""

import os
import re
import sys
import time
import hashlib
import shutil
import datetime
from collections import defaultdict, OrderedDict

from PIL import Image, ImageFilter, ImageStat, ExifTags

# HEIC/HEIF/AVIF 支持（iPhone/现代手机照片）——模块加载时全局注册，
# 让所有 PIL.Image.open 都能读（缩略图/EXIF/人脸/模糊检测全流程）
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp',
              '.heic', '.heif', '.avif', '.gif', '.jfif', '.jpe'}
RAW_EXTS = {'.nef', '.cr2', '.cr3', '.arw', '.dng', '.raf', '.rw2', '.orf',
            '.pef', '.srw', '.x3f', '.erf'}
THUMB_EDGE = 256
VIEW_THUMB_EDGE = 512
DEFAULT_THRESHOLD = 7
MIN_SIZE = 10 * 1024      # 忽略小于 10KB 的文件（网络小图也要处理）
TRASH_DIR_NAME = "待删除"

# 文件类型过滤
FILTER_JPG = "jpg"     # 仅 JPG/JPEG
FILTER_RAW = "raw"     # 仅 RAW
FILTER_ALL = "all"     # 全部

MODE_STRICT = "strict"      # 严格去重：dHash 相似
MODE_SUBJECT = "subject"    # 同主体筛选：人脸识别 + ORB 特征匹配

# ORB 同主体参数
ORB_MAX_FEATURES = 800
ORB_MIN_SHARED_BUCKET = 12      # 倒排索引粗筛：共享特征桶数下限
ORB_MIN_MATCHES = 25            # BFMatcher 匹配数下限
ORB_MIN_INLIERS = 12            # RANSAC 内点数下限
ORB_INLIER_RATIO = 0.25         # 内点比例下限

# 人脸识别参数（同主体模式）
def _model_path(name):
    """定位模型文件：源码运行用脚本目录，打包后用 _MEIPASS"""
    for base in (os.path.dirname(os.path.abspath(__file__)),
                 getattr(sys, '_MEIPASS', '')):
        p = os.path.join(base, "assets", "models", name)
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "assets", "models", name)

FACE_DET_MODEL = _model_path("face_detection_yunet_2023mar.onnx")
FACE_REC_MODEL = _model_path("mobilefacenet.onnx")
FACE_SCORE_THRESHOLD = 0.3      # 人脸检测置信度（低阈值以免漏掉主体）
FACE_SIM_THRESHOLD = 0.42       # 人脸余弦相似度阈值（> 判定同一人）
FACE_BIG_SIZE = 150             # 大脸判定：宽高都 > 此值才算特写人脸
FACE_MAX_FACES = 3              # 每张照片最多取几张脸参与比对


# ── EXIF 拍摄时间 ─────────────────────────────────────────────────
# ── RAW 文件支持（NEF 等，通过 rawpy 提取内嵌 JPEG 预览） ────────
def is_raw_path(path):
    """判断是否为 RAW 文件（PIL 打不开，需 rawpy）"""
    return os.path.splitext(path)[1].lower() in RAW_EXTS


def load_raw_thumb(path, max_edge=THUMB_EDGE):
    """用 rawpy 读取 RAW 文件：优先提取内嵌 JPEG 预览（快），
    失败则尝试 postprocess 解压。返回 PIL Image 或 None。"""
    try:
        import rawpy
        import io
        raw = rawpy.imread(path)
        try:
            # 方式1：提取内嵌 JPEG 预览（不触发 unpack，兼容 D6 等新机型）
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                img = Image.open(io.BytesIO(thumb.data))
            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                img = Image.frombytes('RGB', (thumb.width, thumb.height),
                                      thumb.data)
            else:
                img = None
            if img is not None:
                img = img.convert('RGB')
                if max(img.size) > max_edge:
                    img.thumbnail((max_edge, max_edge), Image.LANCZOS)
                return img
        except Exception:
            pass
        try:
            # 方式2：postprocess 解压（老机型）
            rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                                  output_bps=8)
            img = Image.fromarray(rgb)
            if max(img.size) > max_edge:
                img.thumbnail((max_edge, max_edge), Image.LANCZOS)
            return img
        except Exception:
            pass
    except Exception:
        pass
    finally:
        try:
            raw.close()
        except Exception:
            pass
    return None


def read_taken_time(path):
    """读取 EXIF DateTimeOriginal，失败回退文件修改时间"""
    try:
        img = Image.open(path)
        exif = img.getexif()
        dt = None
        for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            if tag in exif:
                raw = str(exif[tag]).strip()
                try:
                    dt = datetime.datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                    break
                except ValueError:
                    continue
        img.close()
        if dt:
            return dt
    except Exception:
        pass
    # RAW 文件：尝试从内嵌 JPEG 读 EXIF
    if is_raw_path(path):
        try:
            import rawpy
            import io
            raw = rawpy.imread(path)
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                    exif = img.getexif()
                    for tag in (36867, 36868, 306):
                        if tag in exif:
                            try:
                                dt = datetime.datetime.strptime(
                                    str(exif[tag]).strip(), "%Y:%m:%d %H:%M:%S")
                                return dt
                            except ValueError:
                                continue
            except Exception:
                pass
            finally:
                raw.close()
        except Exception:
            pass
    # 回退：文件修改时间
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return datetime.datetime.min


def dsc_number(path):
    """从文件名提取 DSC 序号，如 DSC_1829.JPG -> 1829"""
    m = re.search(r'(\d+)', os.path.basename(path))
    return int(m.group(1)) if m else 0


# ── 缩略图加载 ────────────────────────────────────────────────────
def load_thumb(path, max_edge=THUMB_EDGE):
    # RAW 文件用 rawpy 提取内嵌预览
    if is_raw_path(path):
        img = load_raw_thumb(path, max_edge)
        if img is not None:
            return img.convert('L')
    try:
        img = Image.open(path)
        try:
            img.draft('L', (max_edge, max_edge))
        except Exception:
            pass
        img = img.convert('L')
        w, h = img.size
        if max(w, h) > max_edge:
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        return img
    except Exception:
        # PIL 失败 → 尝试 rawpy
        img = load_raw_thumb(path, max_edge)
        if img is not None:
            return img.convert('L')
        raise


def load_view_thumb(path, max_edge=VIEW_THUMB_EDGE):
    # RAW 文件用 rawpy 提取内嵌预览
    if is_raw_path(path):
        img = load_raw_thumb(path, max_edge)
        if img is not None:
            return img.convert('RGB')
    try:
        img = Image.open(path)
        try:
            img.draft('RGB', (max_edge, max_edge))
        except Exception:
            pass
        img = img.convert('RGB')
        w, h = img.size
        if max(w, h) > max_edge:
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        return img
    except Exception:
        # PIL 失败 → 尝试 rawpy
        img = load_raw_thumb(path, max_edge)
        if img is not None:
            return img.convert('RGB')
        raise


def dhash(img, hash_size=8):
    """感知哈希：numpy 向量化实现（与旧版逐像素实现完全等价，快 10-50 倍）"""
    import numpy as np
    img = img.resize((hash_size + 1, hash_size), Image.LANCZOS)
    a = np.asarray(img, dtype=np.uint8)
    diff = (a[:, :-1] > a[:, 1:]).astype(np.uint8)   # 行优先 0/1
    packed = np.packbits(diff, bitorder='big')
    return int.from_bytes(packed.tobytes(), 'big')


def sharpness_of(img):
    lap = img.filter(ImageFilter.Kernel((3, 3),
        [-1, -1, -1, -1, 8, -1, -1, -1, -1], scale=1, offset=0))
    return ImageStat.Stat(lap).stddev[0]


# ── 模糊检测（Laplacian 方差 + 分区域 + 人脸区域优先） ──────────
_BLUR_THRESHOLD_DEFAULT = 900   # 默认模糊阈值（FFT 高频比×1500）

def laplacian_variance(img_gray):
    """计算灰度图的 Laplacian 方差（越高越清晰）。
    输入 PIL Image，返回 float。
    """
    lap = img_gray.filter(ImageFilter.Kernel((3, 3),
        [-1, -1, -1, -1, 8, -1, -1, -1, -1], scale=1, offset=0))
    return ImageStat.Stat(lap).var[0]


def _load_image_for_blur(path):
    """加载图片用于模糊检测：灰度缩略图 ~800px"""
    from PIL import Image as PILImage
    try:
        if is_raw_path(path):
            img = load_raw_thumb(path, 800)
            if img is not None:
                return img.convert('L')
            return None
        # HEIC/HEIF 支持（iPhone 照片）
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.heic', '.heif'):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except Exception:
                pass
        img = PILImage.open(path)
        try:
            img.draft('RGB', (800, 800))
        except Exception:
            pass
        img = img.convert('RGB')
        w, h = img.size
        if max(w, h) > 800:
            img.thumbnail((800, 800), PILImage.LANCZOS)
        return img.convert('L')
    except Exception:
        return None


def _face_region_blur(path, img_gray):
    """检测人脸区域，返回人脸区域的 Laplacian 方差最大值。
    无脸返回 None。"""
    if not _load_face_models():
        return None
    import cv2
    import numpy as np
    from PIL import Image as PILImage
    try:
        # 读彩色图做人脸检测
        if is_raw_path(path):
            pil_img = load_raw_thumb(path, 800)
        else:
            pil_img = PILImage.open(path).convert('RGB')
        if pil_img is None:
            return None
        color = np.array(pil_img)
        color = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
        h, w = color.shape[:2]
        with _face_lock:
            _face_det.setInputSize((w, h))
            _, faces = _face_det.detect(color)
        if faces is None or len(faces) == 0:
            return None
        # 对检测到的每张脸，裁剪并计算 Laplacian
        best_score = 0.0
        for face in faces:
            x, y, fw, fh = map(int, face[:4])
            x = max(0, x); y = max(0, y)
            fw = min(fw, w - x); fh = min(fh, h - y)
            if fw < 20 or fh < 20:
                continue
            face_crop = img_gray.crop((x, y, x + fw, y + fh))
            score = laplacian_variance(face_crop)
            if score > best_score:
                best_score = score
        return best_score if best_score > 0 else None
    except Exception:
        return None


def compute_blur_score(path, threshold=_BLUR_THRESHOLD_DEFAULT):
    """计算照片模糊度评分（数字越高 = 越清晰）。
    使用 FFT 频域分析——清晰照片高频分量多，模糊照片能量集中在低频。
    返回 (score: float, is_blurry: bool, method: str)
    """
    img_gray = _load_image_for_blur(path)
    if img_gray is None:
        return 999.0, False, "failed"

    import numpy as np
    arr = np.array(img_gray, dtype=np.float64)
    f = np.fft.fft2(arr)
    fshift = np.fft.fftshift(f)
    mag = np.abs(fshift)
    h, w = mag.shape
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    radius = min(h, w) * 0.12
    hi_mask = dist > radius
    hi_energy = float(np.sum(mag[hi_mask]))
    total_energy = float(np.sum(mag))
    if total_energy == 0:
        return 999.0, False, "fft"
    fft_ratio = hi_energy / total_energy
    # 映射到 0-1000 的直观范围（brighter→sharper）
    score = min(fft_ratio * 1500.0, 999.0)
    return score, score < threshold, "fft"


def mark_blurry_photos(photos, threshold=None):
    """标记所有照片的模糊度：设置 blur_score 和 is_blurry。
    多线程并行（FFT 用 numpy 可释放 GIL，大文件夹提速明显）。"""
    if threshold is None:
        threshold = _BLUR_THRESHOLD_DEFAULT
    import concurrent.futures as cf

    def _one(p):
        score, is_blur, method = compute_blur_score(p.path, threshold)
        p.blur_score = score
        p.is_blurry = is_blur
        return p, is_blur

    blurry = []
    if len(photos) < 8:
        for p in photos:
            pp, is_blur = _one(p)
            if is_blur:
                blurry.append(pp)
        return blurry
    n_workers = min(8, max(2, os.cpu_count() or 2))
    with cf.ThreadPoolExecutor(max_workers=n_workers) as pool:
        for pp, is_blur in pool.map(_one, photos, chunksize=4):
            if is_blur:
                blurry.append(pp)
    return blurry


def build_jpg_raw_pairs(result):
    """JPG+RAW 配对（仅全部照片模式调用）：
    完全同名的 JPG 和 RAW（如 DSC_6180.JPG + DSC_6180.NEF）合并为一对，
    - 只显示 JPG（display_name 标记为 xxx.JPG/NEF）
    - RAW 从 singles/groups/blurry_photos 中隐藏（不单独展示）
    - 移动/导出时 JPG 和 RAW 一起动（靠返回的双向映射）
    返回双向映射 {path: pair_path}。
    """
    pairs = {}
    by_stem = {}
    for path, p in result.photos.items():
        stem, ext = os.path.splitext(p.name)
        by_stem.setdefault(stem.lower(), []).append(p)

    for plist in by_stem.values():
        jpgs = [p for p in plist if not is_raw_path(p.path)]
        raws = [p for p in plist if is_raw_path(p.path)]
        if not jpgs or not raws:
            continue
        jp, rp = jpgs[0], raws[0]
        j_ext = os.path.splitext(jp.name)[1].lstrip('.').upper()
        r_ext = os.path.splitext(rp.name)[1].lstrip('.').upper()
        jp.display_name = f"{os.path.splitext(jp.name)[0]}.{j_ext}/{r_ext}"
        pairs[jp.path] = rp.path
        pairs[rp.path] = jp.path
        # 隐藏 RAW：不再单独出现在 singles / groups / blurry
        if rp in result.singles:
            result.singles.remove(rp)
        for g in result.groups:
            if rp in g.photos:
                g.photos.remove(rp)
        blurry = getattr(result, 'blurry_photos', [])
        if rp in blurry:
            blurry.remove(rp)
    return pairs


def count_jpg_raw_pairs(folder):
    """统计文件夹里同名 JPG/RAW 的对数（分析前的醒目提示用）"""
    stems = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for f in names:
        full = os.path.join(folder, f)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(f)
        low = ext.lower()
        if low in ('.jpg', '.jpeg'):
            kind = 'jpg'
        elif low in ('.nef', '.cr2', '.cr3', '.arw', '.dng', '.raf',
                     '.rw2', '.orf', '.pef', '.srw', '.x3f', '.erf'):
            kind = 'raw'
        else:
            continue
        stems.setdefault(stem.lower(), set()).add(kind)
    return sum(1 for s in stems.values() if len(s) == 2)


# ── ORB 特征（同主体模式） ────────────────────────────────────────
_orb_cache = {}   # path -> (keypoints, descriptors)

def np_img(pil_img):
    """PIL Image -> numpy array"""
    import numpy as np
    return np.array(pil_img)


def verify_same_subject(kp1, des1, kp2, des2):
    """ORB 特征匹配 + RANSAC 验证，返回 (是否同主体, 内点数, 匹配数)"""
    if des1 is None or des2 is None or len(des1) < 10 or len(des2) < 10:
        return (False, 0, 0)
    import cv2
    import numpy as np
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(des1, des2, k=2)
    good = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < 0.75 * n.distance:
                good.append(m)
        elif len(pair) == 1:
            good.append(pair[0])
    if len(good) < ORB_MIN_MATCHES:
        return (False, 0, len(good))
    # RANSAC 单应性验证
    try:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None or mask is None:
            return (False, 0, len(good))
        inliers = int(mask.sum())
        ratio = inliers / len(good) if good else 0
        ok = (inliers >= ORB_MIN_INLIERS and ratio >= ORB_INLIER_RATIO)
        return (ok, inliers, len(good))
    except Exception:
        return (False, 0, len(good))


# ── 人脸识别（同主体模式 · 离线 AI） ──────────────────────────────
_face_det = None
_face_rec = None
_face_cache = {}   # path -> (bbox, embedding) or None
_face_lock = __import__('threading').Lock()   # OpenCV 模型非线程安全，加锁

def _load_face_models():
    """延迟加载 YuNet 检测器 + SFace 识别器"""
    global _face_det, _face_rec
    if _face_rec is not None:
        return True
    import cv2
    if not (os.path.exists(FACE_DET_MODEL) and os.path.exists(FACE_REC_MODEL)):
        return False
    _face_det = cv2.FaceDetectorYN.create(
        FACE_DET_MODEL, '', (320, 320),
        score_threshold=FACE_SCORE_THRESHOLD)
    _face_rec = cv2.FaceRecognizerSF.create(FACE_REC_MODEL, '')
    return True


def face_embedding(path):
    """返回前 N 大脸 [(bbox, embedding), ...]；无脸返回 []。带缓存。"""
    if path in _face_cache:
        return _face_cache[path]
    result = []
    try:
        if not _load_face_models():
            _face_cache[path] = result
            return result
        import cv2
        import numpy as np
        # 用 PIL 读图（支持中文/特殊字符路径），RAW 用 rawpy，再转 numpy
        from PIL import Image as PILImage
        if is_raw_path(path):
            pil_img = load_raw_thumb(path, 800)
        else:
            pil_img = PILImage.open(path).convert('RGB')
        if pil_img is None:
            _face_cache[path] = result
            return result
        img = np.array(pil_img)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]
        with _face_lock:
            _face_det.setInputSize((w, h))
            _, faces = _face_det.detect(img)
        if faces is not None and len(faces) > 0:
            # 按面积降序取前 FACE_MAX_FACES
            order = sorted(range(len(faces)),
                           key=lambda i: faces[i][2] * faces[i][3],
                           reverse=True)
            for i in order[:FACE_MAX_FACES]:
                try:
                    with _face_lock:
                        aligned = _face_rec.alignCrop(img, faces[i])
                        emb = _face_rec.feature(aligned)
                    result.append((faces[i], emb))
                except Exception:
                    continue
    except Exception:
        result = []
    _face_cache[path] = result
    return result


def same_person(path1, path2):
    """判断两张照片主体是否为同一人（人脸识别）。
    返回 (is_same, sim, n1, n2, big1, big2)
    - 两张都有大脸 → 只看人脸相似度
    - 否则 → 返回 None 表示"无法用人脸判断"，交给 ORB
    """
    faces1 = face_embedding(path1)
    faces2 = face_embedding(path2)
    if not faces1 or not faces2:
        return None
    import cv2
    # 任意一对脸相似度超过阈值 → 同人
    best_sim = -1.0
    best_pair = None
    for b1, e1 in faces1:
        for b2, e2 in faces2:
            with _face_lock:
                s = float(_face_rec.match(e1, e2, cv2.FaceRecognizerSF_FR_COSINE))
            if s > best_sim:
                best_sim = s
                best_pair = (b1, b2)
    if best_pair is None:
        return None
    b1, b2 = best_pair
    big1 = b1[2] > FACE_BIG_SIZE and b1[3] > FACE_BIG_SIZE
    big2 = b2[2] > FACE_BIG_SIZE and b2[3] > FACE_BIG_SIZE
    if big1 and big2:
        # 两张都是特写人脸 → 只信人脸（换人时构图相同也不合并）
        return (best_sim >= FACE_SIM_THRESHOLD, best_sim,
                len(faces1), len(faces2), True, True)
    if best_sim >= FACE_SIM_THRESHOLD:
        # 相似度足够高 → 同人（即使脸大小不一）
        return (True, best_sim, len(faces1), len(faces2), big1, big2)
    # 脸小或相似度低 → 无法仅凭人脸判定，交给 ORB
    return None


class PhotoInfo:
    __slots__ = ('path', 'name', 'dsc', 'hash', 'sharpness',
                 'brightness', 'size', 'width', 'height', 'taken',
                 'blur_score', 'is_blurry', 'display_name')

    def __init__(self, path, h, sharpness, brightness, size, w, hgt,
                 blur_score=None, is_blurry=False):
        self.path = path
        self.name = os.path.basename(path)
        self.dsc = dsc_number(path)
        self.hash = h
        self.sharpness = sharpness
        self.brightness = brightness
        self.size = size
        self.width = w
        self.height = hgt
        self.taken = read_taken_time(path)
        self.blur_score = blur_score
        self.is_blurry = is_blurry
        self.display_name = None   # JPG+RAW 配对时显示 "xxx.JPG/NEF"


class Group:
    __slots__ = ('photos', 'recommended_keep', 'user_keep', 'confirmed',
                 'kept_paths', 'pending_kept_paths')

    def __init__(self, photos):
        self.photos = photos
        self.recommended_keep = None
        self.user_keep = None
        self.confirmed = False
        self.kept_paths = None         # 确认时用户保留的 path 集合
        self.pending_kept_paths = None # 未确认时用户当前选择（跨面板保留）
        self._set_recommendation()

    def _set_recommendation(self):
        # 推荐保留：拍摄时间最新的（后拍优先）
        self.recommended_keep = max(self.photos, key=lambda p: p.taken)

    def recalc(self):
        """手动分组后重新计算推荐"""
        self._set_recommendation()
        self.user_keep = None

    def remove_photos(self, paths):
        """从组中移除指定路径的照片，返回被移除的 PhotoInfo 列表"""
        removed = [p for p in self.photos if p.path in paths]
        self.photos = [p for p in self.photos if p.path not in paths]
        if self.photos:
            self.recalc()
        return removed

    def visible_photos(self):
        """组内可见（未被删除）的照片：
        已确认的组 → 只显示 kept_paths 里的；
        未确认的组 → 全部显示"""
        if self.confirmed and self.kept_paths is not None:
            return [p for p in self.photos if p.path in self.kept_paths]
        return list(self.photos)

    @property
    def user_kept(self):
        return self.user_keep if self.user_keep is not None else self.recommended_keep

    @property
    def to_delete(self):
        kept = self.user_kept
        return [p for p in self.photos if p is not kept]


class AnalysisResult:
    def __init__(self, folder, threshold, mode):
        self.folder = folder
        self.threshold = threshold
        self.mode = mode
        self.photos = {}
        self.groups = []
        self.singles = []
        self.analysis_time = 0.0
        self.blurry_photos = []    # is_blurry=True 的照片列表
        self.file_filter = FILTER_ALL
        self.failed_count = 0      # 读取失败（损坏/不支持）的照片数
        self.failed_paths = []     # 读取失败明细 [(path, 原因)]，便于诊断


class Analyzer:
    def __init__(self, threshold=DEFAULT_THRESHOLD, mode=MODE_STRICT,
                 file_filter=FILTER_ALL, progress_cb=None):
        self.threshold = threshold
        self.mode = mode
        self.file_filter = file_filter
        self.progress_cb = progress_cb or (lambda cur, total, msg: None)

    def _ext_ok(self, ext):
        """根据文件类型过滤判断扩展名是否入选"""
        if self.file_filter == FILTER_JPG:
            return ext in {'.jpg', '.jpeg'}
        if self.file_filter == FILTER_RAW:
            return ext in RAW_EXTS
        return ext in IMAGE_EXTS or ext in RAW_EXTS

    def collect_files(self, folder):
        files = []
        for f in sorted(os.listdir(folder)):
            ext = os.path.splitext(f)[1].lower()
            if self._ext_ok(ext):
                p = os.path.join(folder, f)
                try:
                    if os.path.getsize(p) >= MIN_SIZE:
                        files.append(p)
                except OSError:
                    pass
        return files

    def analyze(self, folder, enable_blur=False, blur_threshold=None):
        t0 = time.time()
        files = self.collect_files(folder)
        total = len(files)
        self.progress_cb(0, total, "扫描照片...")
        result = AnalysisResult(folder, self.threshold, self.mode)
        result.file_filter = self.file_filter

        # 多线程并行特征提取（每张独立，结果与串行完全一致）
        import concurrent.futures as cf
        done = 0

        def extract(path):
            try:
                img = load_thumb(path)
                h = dhash(img)
                s = sharpness_of(img)
                b = ImageStat.Stat(img).mean[0]
                w, hgt = img.size
                return path, PhotoInfo(path, h, s, b,
                                       os.path.getsize(path), w, hgt)
            except Exception as e:
                result.failed_paths.append((path, repr(e)[:150]))
                return path, None

        n_workers = min(8, max(2, os.cpu_count() or 2))
        with cf.ThreadPoolExecutor(max_workers=n_workers) as pool:
            for path, pinfo in pool.map(extract, files):
                if pinfo is not None:
                    result.photos[path] = pinfo
                else:
                    result.failed_count += 1
                done += 1
                if done % 25 == 0 or done == total:
                    self.progress_cb(done, total,
                                     f"正在分析照片特征 ({done}/{total})...")

        # 模糊检测（在分组之前，不影响分组逻辑）
        if enable_blur:
            self.progress_cb(total, total, "正在识别模糊照片...")
            result.blurry_photos = mark_blurry_photos(
                list(result.photos.values()), blur_threshold)

        if self.mode == MODE_STRICT:
            self.progress_cb(total, total, "正在分组相似照片...")
            self._group_strict(result)
        else:
            self.progress_cb(total, total, "正在匹配同主体照片（特征提取）...")
            self._group_subject(result)

        # 统一按拍摄时间排序：组内照片、独张照片（第 1 点）
        for g in result.groups:
            g.photos.sort(key=lambda p: p.taken)
        result.singles.sort(key=lambda p: p.taken)
        result.groups.sort(key=lambda g: g.photos[0].taken
                           if g.photos else datetime.datetime.min)

        result.analysis_time = time.time() - t0
        return result

    # ── 严格去重分组 ────────────────────────────────────────────
    def _group_strict(self, result):
        paths = list(result.photos.keys())
        assigned = set()
        groups = []
        for i, p1 in enumerate(paths):
            if p1 in assigned:
                continue
            h1 = result.photos[p1].hash
            grp = [result.photos[p1]]
            assigned.add(p1)
            for p2 in paths[i + 1:]:
                if p2 in assigned:
                    continue
                if (h1 ^ result.photos[p2].hash).bit_count() <= self.threshold:
                    grp.append(result.photos[p2])
                    assigned.add(p2)
            if len(grp) > 1:
                groups.append(Group(grp))
            else:
                result.singles.append(grp[0])
        for g in groups:
            g.photos.sort(key=lambda p: p.taken)
        result.groups = groups

    # ── 同主体分组（ORB） ───────────────────────────────────────
    def _group_subject(self, result):
        import cv2
        import numpy as np

        paths = list(result.photos.keys())
        n = len(paths)

        # 1) 提取全部特征（带进度）
        features = {}
        for i, p in enumerate(paths, 1):
            features[p] = self._orb_features(p)
            if i % 20 == 0 or i == n:
                self.progress_cb(i, n, f"提取特征 ({i}/{n})...")

        # 2) 倒排索引粗筛候选对
        self.progress_cb(n, n, "构建特征索引...")
        bucket = defaultdict(list)   # 描述子前4字节 -> [path...]
        for p, (kp, des) in features.items():
            if des is None:
                continue
            seen = set()
            for d in des:
                key = d[:4].tobytes().hex()
                bucket[key].append(p)

        # 候选对：共享桶数 >= 阈值
        self.progress_cb(n, n, "筛选候选对...")
        shared_count = defaultdict(int)
        for key, plist in bucket.items():
            plist = list(set(plist))
            if len(plist) < 2:
                continue
            for a in range(len(plist)):
                for b in range(a + 1, len(plist)):
                    shared_count[(plist[a], plist[b])] += 1

        candidates = [(a, b) for (a, b), c in shared_count.items()
                      if c >= ORB_MIN_SHARED_BUCKET]
        total_cand = len(candidates)
        self.progress_cb(0, max(total_cand, 1), "验证候选对...")

        # 3a) 预提取所有人脸嵌入（每张只算一次，并行；避免候选对重复计算）
        import concurrent.futures as cf
        n_workers = min(6, max(2, os.cpu_count() or 2))
        uniq_paths = sorted({p for pair in candidates for p in pair})
        pre_done = 0
        with cf.ThreadPoolExecutor(max_workers=n_workers) as pool:
            for p in pool.map(face_embedding, uniq_paths, chunksize=4):
                pre_done += 1
                if pre_done % 10 == 0 or pre_done == len(uniq_paths):
                    self.progress_cb(
                        pre_done, max(len(uniq_paths), 1),
                        f"人脸特征 ({pre_done}/{len(uniq_paths)})...")

        # 3b) 验证候选对（人脸识别优先，ORB 兜底）——多线程并行（每对独立）
        def verify_pair(pair):
            a, b = pair
            fp = same_person(a, b)
            if fp is not None:
                if fp[0]:
                    return (a, b)
                elif fp[4] and fp[5]:
                    return None  # 明确不同人，跳过
                else:
                    kp1, des1 = features[a]
                    kp2, des2 = features[b]
                    ok, _, _ = verify_same_subject(kp1, des1, kp2, des2)
                    return (a, b) if ok else None
            else:
                kp1, des1 = features[a]
                kp2, des2 = features[b]
                ok, _, _ = verify_same_subject(kp1, des1, kp2, des2)
                return (a, b) if ok else None

        edges = []
        done = 0
        with cf.ThreadPoolExecutor(max_workers=n_workers) as pool:
            for result_pair in pool.map(verify_pair, candidates, chunksize=8):
                if result_pair is not None:
                    edges.append(result_pair)
                done += 1
                if done % 10 == 0 or done == total_cand:
                    self.progress_cb(done, max(total_cand, 1),
                                     f"验证候选对 ({done}/{total_cand})...")

        # 4) 并查集合并连通分量
        parent = {p: p for p in paths}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for a, b in edges:
            union(a, b)

        comps = defaultdict(list)
        for p in paths:
            comps[find(p)].append(p)

        groups = []
        singles = []
        for comp in comps.values():
            if len(comp) > 1:
                grp = Group([result.photos[p] for p in comp])
                grp.photos.sort(key=lambda p: p.taken)
                groups.append(grp)
            else:
                singles.append(result.photos[comp[0]])
        result.groups = groups
        result.singles = singles

    def _orb_features(self, path):
        """提取 ORB (关键点, 描述子)，带缓存"""
        if path in _orb_cache:
            return _orb_cache[path]
        try:
            img = load_view_thumb(path, 512)
            import cv2
            import numpy as np
            arr = np.array(img.convert('RGB'))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            orb = cv2.ORB_create(nfeatures=ORB_MAX_FEATURES)
            kp, des = orb.detectAndCompute(gray, None)
            _orb_cache[path] = (kp, des)
            return (kp, des)
        except Exception:
            _orb_cache[path] = (None, None)
            return (None, None)


class ThumbnailCache:
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = os.path.join(
                os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                'photoselect_cache')
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        # 内存 LRU 缓存（避免反复磁盘解码；按总字节限制防内存膨胀）
        self._mem = OrderedDict()          # (path, edge) -> PIL Image
        self._mem_bytes = 0
        self._mem_limit = 200 * 1024 * 1024   # 200MB 上限
        self._auto_cleanup()

    def _auto_cleanup(self, max_age_days=30, trigger_files=5000):
        """缓存目录文件过多时清理超期缓存（避免磁盘无限膨胀）"""
        try:
            files = [os.path.join(self.cache_dir, f)
                     for f in os.listdir(self.cache_dir)]
            if len(files) < trigger_files:
                return
            now = time.time()
            removed = 0
            for fp in files:
                try:
                    if now - os.path.getmtime(fp) > max_age_days * 86400:
                        os.remove(fp)
                        removed += 1
                except OSError:
                    pass
        except Exception:
            pass

    def _cache_path(self, path, edge):
        sig = hashlib.md5((path + f"_{edge}").encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{sig}.jpg")

    def _store_mem(self, key, img):
        """写入内存 LRU，超限时淘汰最久未用的"""
        self._mem[key] = img
        self._mem.move_to_end(key)
        self._mem_bytes += img.size[0] * img.size[1] * 3
        while self._mem_bytes > self._mem_limit and len(self._mem) > 1:
            _, old = self._mem.popitem(last=False)
            self._mem_bytes -= old.size[0] * old.size[1] * 3

    def get(self, path, edge=VIEW_THUMB_EDGE):
        key = (path, edge)
        # 1) 内存 LRU 命中
        if key in self._mem:
            img = self._mem.pop(key)
            self._mem[key] = img
            return img
        cp = self._cache_path(path, edge)
        # 2) 磁盘缓存命中
        if os.path.exists(cp):
            try:
                img = Image.open(cp).convert('RGB')
                self._store_mem(key, img)
                return img
            except Exception:
                pass
        # 3) 重新生成并落盘
        try:
            img = load_view_thumb(path, edge)
            img.save(cp, 'JPEG', quality=85)
            self._store_mem(key, img)
            return img
        except Exception:
            return None

    def clear(self):
        self._mem.clear()
        self._mem_bytes = 0
        for f in os.listdir(self.cache_dir):
            try:
                os.remove(os.path.join(self.cache_dir, f))
            except OSError:
                pass


# ── 文件操作 ──────────────────────────────────────────────────────
def move_to_trash(paths, folder):
    trash = os.path.join(folder, TRASH_DIR_NAME)
    os.makedirs(trash, exist_ok=True)
    moved = 0
    for p in paths:
        try:
            name = os.path.basename(p)
            base, ext = os.path.splitext(name)
            dest = os.path.join(trash, name)
            n = 1
            while os.path.exists(dest):   # 重名则递增 _dupN，避免覆盖丢失
                dest = os.path.join(trash, f"{base}_dup{n}{ext}")
                n += 1
            shutil.move(p, dest)
            moved += 1
        except OSError:
            pass
    return moved


def restore_from_trash(paths, folder):
    """撤销：把照片从 folder/待删除/ 移回 folder/，返回成功数"""
    trash = os.path.join(folder, TRASH_DIR_NAME)
    if not os.path.isdir(trash):
        return 0
    restored = 0
    for p in paths:
        try:
            name = os.path.basename(p)
            src = os.path.join(trash, name)
            if not os.path.exists(src):
                # 找最小的 _dupN 后缀
                base, ext = os.path.splitext(name)
                found = None
                for n in range(1, 1000):
                    cand = os.path.join(trash, f"{base}_dup{n}{ext}")
                    if os.path.exists(cand):
                        found = cand
                        break
                if found is None:
                    continue
                src = found
            dest = os.path.join(folder, name)
            shutil.move(src, dest)
            restored += 1
        except OSError:
            pass
    return restored


def copy_kept(paths, dest_folder, move=False):
    os.makedirs(dest_folder, exist_ok=True)
    ok, skipped = 0, 0
    for p in paths:
        try:
            name = os.path.basename(p)
            dest = os.path.join(dest_folder, name)
            if os.path.exists(dest):
                skipped += 1
                continue
            if move:
                shutil.move(p, dest)
            else:
                shutil.copy2(p, dest)
            ok += 1
        except OSError:
            pass
    return ok, skipped


# ── 测试入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    thr = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD
    mode = sys.argv[3] if len(sys.argv) > 3 else MODE_STRICT

    def cb(cur, total, msg):
        print(f"[{cur}/{total}] {msg}")

    a = Analyzer(threshold=thr, mode=mode, progress_cb=cb)
    res = a.analyze(folder)
    print(f"\n分析完成：{len(res.photos)} 张，{len(res.groups)} 组，"
          f"{len(res.singles)} 独张，耗时 {res.analysis_time:.1f}s")
    for i, g in enumerate(res.groups[:8], 1):
        names = [p.name for p in g.photos]
        print(f"  组{i}: {names}  → 推荐 {g.recommended_keep.name} "
              f"({g.recommended_keep.taken:%H:%M:%S})")
