"""手势识别核心模块：MediaPipe HandLandmarker + 规则式手势分类。

抽取自 gesture-effects 项目的 legacy-python/gesture.py（MIT 风格注释保留），
作为 camera-mcp-server 的可复用视觉模块。核心思想不变：
  21 个手部关键点 → 每个手指用「指尖到手腕 / 参考关节到手腕」距离比判伸弯
  → 组合成手势规则。全部可解释、可调参、无需训练。

支持手势: open_palm(张手) / fist(拳头) / thumbs_up(竖拇指) / peace(剪刀手)
         / ok / heart(比心) / one(比1)
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# ---------------------------------------------------------------------------
# MediaPipe 21 关键点索引（标准）
#   0  手腕 WRIST
#   1-4  拇指 (4=指尖)
#   5-8  食指 (8=指尖)
#   9-12 中指 (12=指尖)
#   13-16 无名指 (16=指尖)
#   17-20 小指 (20=指尖)
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_TIP, THUMB_IP, THUMB_MCP = 4, 3, 2
INDEX_TIP, INDEX_MCP, INDEX_PIP = 8, 5, 6
MIDDLE_TIP, MIDDLE_MCP = 12, 9
RING_TIP, RING_MCP = 16, 13
PINKY_TIP, PINKY_MCP = 20, 17
PALM = 9  # 掌心近似点（中指根）

# 手指： (指尖, 参考点)。参考点 = 该手指伸直与否的参照关节
# 食指/中指/无名指/小指用 MCP（指尖到手腕 vs 指根到手腕）
# 拇指用 IP 关节（拇指 MCP 离手腕太近，弯曲时距离比不敏感）
FINGERS = {
    "thumb": (THUMB_TIP, THUMB_IP),
    "index": (INDEX_TIP, INDEX_MCP),
    "middle": (MIDDLE_TIP, MIDDLE_MCP),
    "ring": (RING_TIP, RING_MCP),
    "pinky": (PINKY_TIP, PINKY_MCP),
}

# 手指伸直判定：指尖到手腕距离 / 参考点到手腕距离
EXTEND_RATIO = 1.35   # 比值高于此视为伸直
BEND_RATIO = 1.15     # 比值低于此视为弯曲，之间为模糊态

# 拇指专用阈值（参照点不同，分布更密集）
THUMB_EXTEND_RATIO = 1.30
THUMB_BEND_RATIO = 1.15

# 比心 / OK：拇指尖与食指尖距离（按手尺寸归一化）
PINCH_DIST = 0.38

# 手势列表
GESTURES = ("open_palm", "fist", "thumbs_up", "peace", "ok", "heart", "one")


@dataclass
class Hand:
    """一只手的状态。"""

    landmarks: List[tuple] = field(default_factory=list)  # 21 个 (x, y) 像素坐标
    norm_landmarks: List[tuple] = field(default_factory=list)  # 21 个归一化 (x, y)
    handedness: str = "Unknown"      # Left / Right（图像视角）
    score: float = 0.0
    gesture: str = "none"            # 当前识别出的手势
    palm_center: tuple = (0.0, 0.0)  # 掌心（像素坐标）
    hand_size: float = 0.0           # 手尺寸（像素）：手腕到中指根距离
    finger_states: dict = field(default_factory=dict)  # 各手指伸直状态

    def tip(self, idx: int) -> tuple:
        """返回某关键点的像素坐标。"""
        return self.landmarks[idx]

    def to_dict(self) -> dict:
        """序列化为 JSON 友好的 dict（MCP 工具返回值用）。"""
        return {
            "gesture": self.gesture,
            "handedness": self.handedness,
            "confidence": round(self.score, 4),
            "hand_size": round(self.hand_size, 1),
            "palm_center": [round(v, 1) for v in self.palm_center],
            "finger_states": self.finger_states,
            "landmarks": [[round(x, 1), round(y, 1)] for x, y in self.landmarks],
        }


def resolve_model_path(explicit: Optional[str] = None) -> str:
    """按优先级找 hand_landmarker.task 模型：
    1. 显式传入
    2. 环境变量 CAMERA_MCP_HAND_MODEL
    3. 项目根 models/ 目录（本文件上溯两级）
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("CAMERA_MCP_HAND_MODEL")
    if env:
        candidates.append(env)
    # camera_mcp/gestures.py -> 项目根
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(project_root, "models", "hand_landmarker.task"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        "找不到 hand_landmarker.task 模型。请用 scripts/download_models.py 下载，"
        "或设置环境变量 CAMERA_MCP_HAND_MODEL 指向模型路径。"
    )


class GestureDetector:
    """封装 MediaPipe HandLandmarker + 规则式手势分类。"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        num_hands: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        model_path = resolve_model_path(model_path)
        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._detector = vision.HandLandmarker.create_from_options(options)

    # ------------------------------------------------------------------
    # 检测
    # ------------------------------------------------------------------
    def detect(self, frame_bgr: np.ndarray) -> List[Hand]:
        """输入 BGR 帧，返回检测到的手列表（含手势分类结果）。"""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_image)

        h, w = frame_bgr.shape[:2]
        hands: List[Hand] = []
        for i, lm_list in enumerate(result.hand_landmarks):
            hand = Hand()
            for lm in lm_list:
                hand.norm_landmarks.append((lm.x, lm.y))
                hand.landmarks.append((int(lm.x * w), int(lm.y * h)))
            if result.handedness and i < len(result.handedness) and result.handedness[i]:
                hand.handedness = result.handedness[i][0].category_name
                hand.score = result.handedness[i][0].score
            hand.hand_size = self._dist(hand.landmarks[WRIST], hand.landmarks[MIDDLE_MCP])
            hand.palm_center = hand.landmarks[PALM]
            hand.finger_states = self._finger_states(hand)
            hand.gesture = self.classify(hand)
            hands.append(hand)
        return hands

    def close(self):
        self._detector.close()

    # ------------------------------------------------------------------
    # 几何工具
    # ------------------------------------------------------------------
    @staticmethod
    def _dist(a: tuple, b: tuple) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _finger_states(self, hand: Hand) -> dict:
        """判断每个手指伸直/弯曲/模糊。用 指尖-手腕距离 / 参考点-手腕距离。"""
        states = {}
        wrist = hand.landmarks[WRIST]
        for name, (tip_i, ref_i) in FINGERS.items():
            d_tip = self._dist(hand.landmarks[tip_i], wrist)
            d_ref = self._dist(hand.landmarks[ref_i], wrist)
            ratio = d_tip / max(d_ref, 1e-6)
            if name == "thumb":
                ext, bend = THUMB_EXTEND_RATIO, THUMB_BEND_RATIO
            else:
                ext, bend = EXTEND_RATIO, BEND_RATIO
            if ratio > ext:
                states[name] = "extended"
            elif ratio < bend:
                states[name] = "bent"
            else:
                states[name] = "mid"
        return states

    # ------------------------------------------------------------------
    # 手势分类（规则式）
    # ------------------------------------------------------------------
    def classify(self, hand: Hand) -> str:
        s = hand.finger_states
        fingers = ["index", "middle", "ring", "pinky"]
        extended = [f for f in fingers if s[f] == "extended"]
        bent = [f for f in fingers if s[f] == "bent"]
        n_ext = len(extended)
        n_bent = len(bent)
        thumb_ext = s["thumb"] == "extended"

        # 拇指尖与食指尖是否相触（比心 / OK 共用）
        pinch = self._dist(hand.landmarks[THUMB_TIP], hand.landmarks[INDEX_TIP]) \
            < PINCH_DIST * max(hand.hand_size, 1e-6)

        # 张开手掌：五指全伸
        if thumb_ext and n_ext == 4:
            return "open_palm"

        # 食指比一：仅食指伸直，中/无/小指弯曲（拇指状态随意，避免和竖拇指混淆）
        # 注意：必须放在 thumbs_up 之前，否则拇指伸直时会被竖拇指规则抢先
        if (s["index"] == "extended" and s["middle"] == "bent"
                and s["ring"] == "bent" and s["pinky"] == "bent"):
            return "one"

        # 拳头：五指全曲（要求拇指严格弯曲，比心时拇指半立不算拳头）
        if s["thumb"] == "bent" and n_bent == 4:
            return "fist"

        # 比心：拇指+食指相触成心形，其余三指弯曲
        if pinch and n_bent >= 2 and n_ext <= 1:
            return "heart"

        # OK：拇指+食指成环，其余手指伸直
        if pinch and n_ext >= 2:
            return "ok"

        # 剪刀手：食指+中指伸直，无名指+小指弯曲
        if (s["index"] == "extended" and s["middle"] == "extended"
                and s["ring"] == "bent" and s["pinky"] == "bent"):
            return "peace"

        # 竖大拇指：拇指伸直，其余四指弯曲
        if thumb_ext and n_bent >= 3:
            return "thumbs_up"

        return "none"


# 进程级单例：模型加载很贵（数百 ms），摄像头场景不要每帧重建
_detector: Optional[GestureDetector] = None


def get_detector(**kwargs) -> GestureDetector:
    """获取全局共享的 GestureDetector 实例。"""
    global _detector
    if _detector is None:
        _detector = GestureDetector(**kwargs)
    return _detector


def reset_detector():
    """销毁全局单例（改模型路径 / 换参数时用）。"""
    global _detector
    if _detector is not None:
        _detector.close()
        _detector = None
