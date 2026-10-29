"""데이터셋 검사 도구. 데이터셋 등록(validate_dataset.py)과 학습 스크립트가 같은 규칙을 씁니다.

검사 결과는 (stats, errors, warnings) 로 돌려주며, 첫 오류에서 멈추지 않고 최대
MAX_MESSAGES 개까지 모아 한 번에 보여 줍니다.
"""
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

import yaml

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
JUNK_DIRS = {"__MACOSX"}
MAX_MESSAGES = 100


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []
        self.n_errors = 0

    def error(self, msg):
        self.n_errors += 1
        if len(self.errors) < MAX_MESSAGES:
            self.errors.append(msg)

    def warn(self, msg):
        if len(self.warnings) < MAX_MESSAGES:
            self.warnings.append(msg)

    def summary(self):
        return {"errors": self.errors, "error_count": self.n_errors, "warnings": self.warnings}


# ---------------------------------------------------------------- 업로드 정리
def _zip_name(info: zipfile.ZipInfo) -> str:
    """UTF-8 표시가 없는 zip(윈도우 한글 압축 등)의 파일 이름을 cp949 로 다시 읽습니다."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def extract_zip(zip_path: Path, dest: Path):
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = _zip_name(info).replace("\\", "/")
            if info.is_dir() or name.endswith("/"):
                continue
            target = (dest / name).resolve()
            if not target.is_relative_to(dest):
                raise ValueError(f"압축 파일에 잘못된 경로가 있습니다: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)


def normalize_upload(root: Path) -> Path:
    """zip 하나만 올렸으면 풀고, 운영체제가 만든 군더더기 파일을 지우고,
    최상위에 폴더 하나만 있으면 그 안을 데이터셋 루트로 봅니다."""
    entries = [p for p in root.iterdir()]
    if len(entries) == 1 and entries[0].is_file() and entries[0].suffix.lower() == ".zip":
        zip_path = entries[0]
        extract_zip(zip_path, root)
        zip_path.unlink()

    for p in sorted(root.rglob("*"), reverse=True):
        if p.is_dir() and p.name in JUNK_DIRS:
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file() and (p.name in JUNK_NAMES or p.name.startswith("._")):
            p.unlink()

    while True:
        entries = [p for p in root.iterdir()]
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        else:
            return root


# ---------------------------------------------------------------- 공통 검사
def _check_image(path: Path, rep: Report, rel: str):
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
        if w < 1 or h < 1:
            rep.error(f"{rel}: 이미지 크기가 0 입니다")
    except Exception as e:
        rep.error(f"{rel}: 이미지를 열 수 없습니다 ({type(e).__name__})")


def check_split_leakage(manifest_files: dict, split_of, rep: Report):
    """내용이 똑같은 파일이 서로 다른 분할에 있으면 경고합니다 (검증/테스트 누수)."""
    by_hash = defaultdict(set)
    for rel, meta in manifest_files.items():
        split = split_of(rel)
        if split:
            by_hash[meta["sha256"] if isinstance(meta, dict) else meta].add((split, rel))
    n = 0
    for items in by_hash.values():
        splits = {s for s, _ in items}
        if len(splits) > 1:
            n += 1
            if n <= 10:
                rep.warn("같은 이미지가 여러 분할에 있습니다: " + ", ".join(sorted(r for _, r in items)))
    if n > 10:
        rep.warn(f"... 같은 이미지가 여러 분할에 있는 경우가 모두 {n}건입니다")


# ---------------------------------------------------------------- 검출 (YOLO)
def detection_names(root: Path) -> dict:
    for cand in ("dataset.yaml", "data.yaml"):
        if (root / cand).is_file():
            loaded = yaml.safe_load((root / cand).read_text(encoding="utf-8")) or {}
            raw = loaded.get("names")
            if raw:
                return dict(enumerate(raw)) if isinstance(raw, list) else {int(k): str(v) for k, v in raw.items()}
    return {0: "number_group"}


def validate_detection(root: Path, check_images: bool = True):
    """images/{train,val[,test]} 와 labels/{같은 분할}/<이미지 이름>.txt (YOLO 형식)."""
    rep = Report()
    names = detection_names(root)
    nc = len(names)
    counts = {}
    for split in ("train", "val", "test"):
        img_dir = root / "images" / split
        if not img_dir.is_dir():
            if split == "test":
                rep.warn("Test 분할(images/test)이 없습니다. 학습 후 Test 평가를 건너뜁니다.")
            else:
                rep.error(f"필수 폴더가 없습니다: images/{split}")
            continue
        images = sorted(p for p in img_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
        others = [p for p in img_dir.rglob("*") if p.is_file() and p.suffix.lower() not in IMAGE_EXTS]
        for p in others[:5]:
            rep.warn(f"이미지가 아닌 파일은 무시됩니다: {p.relative_to(root).as_posix()}")
        if not images:
            rep.error(f"이미지가 없습니다: images/{split}")
            continue
        boxes, per_class, empty = 0, defaultdict(int), 0
        label_dir = root / "labels" / split
        used_labels = set()
        for img in images:
            rel_img = img.relative_to(root).as_posix()
            if check_images:
                _check_image(img, rep, rel_img)
            label = label_dir / img.relative_to(img_dir).with_suffix(".txt")
            if not label.is_file():
                rep.error(f"라벨 파일이 없습니다: {label.relative_to(root).as_posix()}")
                continue
            used_labels.add(label.resolve())
            lines = [l for l in label.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
            if not lines:
                empty += 1
            for n, line in enumerate(lines, 1):
                parts = line.split()
                ok = len(parts) == 5
                if ok:
                    try:
                        cls = int(parts[0])
                        vals = [float(v) for v in parts[1:]]
                        ok = 0 <= cls < nc and all(0.0 <= v <= 1.0 for v in vals) and vals[2] > 0 and vals[3] > 0
                    except ValueError:
                        ok = False
                if not ok:
                    rep.error(f"라벨 형식 오류: {label.relative_to(root).as_posix()}:{n}: {line.strip()!r}")
                    continue
                boxes += 1
                per_class[names[cls]] += 1
        if label_dir.is_dir():
            orphans = [p for p in label_dir.rglob("*.txt") if p.resolve() not in used_labels]
            if orphans:
                rep.warn(f"labels/{split} 에 짝이 되는 이미지가 없는 라벨이 {len(orphans)}개 있습니다 (무시됨)")
        if empty:
            rep.warn(f"{split}: 객체가 없는(빈 라벨) 이미지 {empty}장")
        counts[split] = {"images": len(images), "boxes": boxes, "boxes_per_class": dict(per_class)}
    return {"task": "detection", "names": names, "counts": counts}, rep


def detection_split(rel: str):
    parts = rel.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "images" else None


# ---------------------------------------------------------------- 인식 (PP-OCR)
def read_rec_list(path: Path):
    return [l for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]


def validate_recognition(root: Path, charset=None, check_images: bool = True, max_text_length=None):
    """{train,val[,test]}_list.txt, 각 줄 '<이미지 상대경로>\\t<정답>'."""
    rep = Report()
    root = root.resolve()
    counts, lengths, unknown = {}, defaultdict(int), set()
    seen = {}
    for split in ("train", "val", "test"):
        src = root / f"{split}_list.txt"
        if not src.is_file():
            if split == "test":
                rep.warn("test_list.txt 가 없습니다. 학습 후 Test 평가를 건너뜁니다.")
            else:
                rep.error(f"필수 목록 파일이 없습니다: {split}_list.txt")
            continue
        lines = read_rec_list(src)
        if not lines:
            rep.error(f"목록이 비어 있습니다: {split}_list.txt")
            continue
        for n, line in enumerate(lines, 1):
            where = f"{split}_list.txt:{n}"
            if "\t" not in line:
                rep.error(f"{where}: 탭으로 구분된 '경로<TAB>정답' 형식이 아닙니다")
                continue
            name, text = line.split("\t", 1)
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                rep.error(f"{where}: 이미지가 없습니다: {name}")
                continue
            if not text:
                rep.error(f"{where}: 정답이 비어 있습니다")
                continue
            if name in seen and seen[name] != split:
                rep.warn(f"같은 이미지가 {seen[name]} 와 {split} 목록에 모두 있습니다: {name}")
            seen[name] = split
            if check_images:
                _check_image(path, rep, name)
            if charset is not None:
                unknown.update(c for c in text if c not in charset and c != " ")
            lengths[len(text)] += 1
            if max_text_length and len(text) > max_text_length:
                rep.warn(f"{where}: 정답 길이 {len(text)} 가 최대 길이 {max_text_length} 보다 깁니다 (학습에서 제외될 수 있음)")
        counts[split] = len(lines)
    if unknown:
        rep.error(f"문자 사전에 없는 문자가 정답에 있습니다: {''.join(sorted(unknown))}")
    return {"task": "recognition", "counts": counts, "text_lengths": dict(sorted(lengths.items()))}, rep


def recognition_split_map(root: Path):
    """이미지 상대경로 -> 분할. 누수 검사용."""
    out = {}
    for split in ("train", "val", "test"):
        p = root / f"{split}_list.txt"
        if p.is_file():
            for line in read_rec_list(p):
                if "\t" in line:
                    out[line.split("\t", 1)[0]] = split
    return out


# ---------------------------------------------------------------- E2E 평가 (검출 + 인식)
# 형식
#   labels.txt        '<이미지 상대경로>\t<패널>\t<슬롯 1~6>\t<정답>'  (UTF-8, BOM 허용)
#   images/...        패널 이미지. roi_config.json 이 있으면 전체 프레임 이미지
#   roi_config.json   (선택) {"image_width", "image_height", "panels": {"panel_1": [x1, y1, x2, y2], ...}}
# 정답이 없는 슬롯(육안 판독 불가 등)은 줄을 빼면 채점에서 제외됩니다.
E2E_SLOTS = 6


def load_roi_config(root: Path):
    p = root / "roi_config.json"
    if not p.is_file():
        return None
    import json

    cfg = json.loads(p.read_text(encoding="utf-8-sig"))
    panels = cfg.get("panels")
    if not isinstance(panels, dict) or not panels:
        raise ValueError("roi_config.json 에 panels 가 없습니다")
    out = {}
    for name, box in panels.items():
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int) for v in box)):
            raise ValueError(f"roi_config.json: {name} 좌표는 정수 [x1, y1, x2, y2] 여야 합니다")
        x1, y1, x2, y2 = box
        if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0:
            raise ValueError(f"roi_config.json: {name} 좌표가 올바르지 않습니다: {box}")
        out[name] = tuple(box)
    return {"image_width": cfg.get("image_width"), "image_height": cfg.get("image_height"), "panels": out}


def read_e2e_labels(root: Path, rep: Report = None):
    """labels.txt -> {(이미지, 패널): {슬롯: 정답}}. 형식 오류는 rep 에 모읍니다."""
    rep = rep or Report()
    labels = defaultdict(dict)
    src = root / "labels.txt"
    if not src.is_file():
        rep.error("필수 파일이 없습니다: labels.txt")
        return labels, rep
    for n, line in enumerate(read_rec_list(src), 1):
        parts = line.split("\t")
        if len(parts) != 4:
            rep.error(f"labels.txt:{n}: '이미지<TAB>패널<TAB>슬롯<TAB>정답' 4개 항목이 아닙니다")
            continue
        image, panel, slot, text = (p.strip() for p in parts)
        if not slot.isdigit() or not 1 <= int(slot) <= E2E_SLOTS:
            rep.error(f"labels.txt:{n}: 슬롯은 1~{E2E_SLOTS} 사이 숫자여야 합니다: {slot!r}")
            continue
        if not image or not panel or not text:
            rep.error(f"labels.txt:{n}: 빈 항목이 있습니다")
            continue
        key = (image, panel)
        if int(slot) in labels[key]:
            rep.error(f"labels.txt:{n}: 같은 이미지·패널·슬롯이 중복됩니다: {image} {panel} {slot}")
            continue
        labels[key][int(slot)] = text
    return labels, rep


def e2e_panels(root: Path, roi=None):
    """평가할 패널 목록 [(이미지 상대경로, 패널 이름)].

    패널 모드: images/ 아래 이미지 하나가 패널 하나 (패널 이름은 labels.txt 값, 없으면 파일 이름)
    프레임 모드: 이미지마다 roi_config.json 의 모든 패널
    """
    images = sorted(p.relative_to(root).as_posix() for p in (root / "images").rglob("*")
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if roi:
        return [(img, name) for img in images for name in roi["panels"]]
    return images


def validate_e2e(root: Path, charset=None, check_images: bool = True):
    rep = Report()
    root = root.resolve()
    try:
        roi = load_roi_config(root)
    except Exception as e:
        rep.error(str(e))
        roi = None
    if not (root / "images").is_dir():
        rep.error("필수 폴더가 없습니다: images")
        return {"task": "e2e"}, rep
    labels, rep = read_e2e_labels(root, rep)
    images = e2e_panels(root)  # 이미지 목록
    if not images:
        rep.error("images 폴더에 이미지가 없습니다")
    image_set = set(images)

    panel_of_image = {}
    unknown = set()
    for (image, panel), slots in labels.items():
        if image not in image_set:
            rep.error(f"labels.txt 의 이미지가 없습니다: {image}")
            continue
        if roi:
            if panel not in roi["panels"]:
                rep.error(f"roi_config.json 에 없는 패널입니다: {image} {panel}")
        else:
            prev = panel_of_image.setdefault(image, panel)
            if prev != panel:
                rep.error(f"패널 모드에서 이미지 하나는 패널 하나입니다: {image} ({prev}, {panel})")
        if charset is not None:
            for text in slots.values():
                unknown.update(c for c in text if c not in charset and c != " ")
    if unknown:
        rep.error(f"문자 사전에 없는 문자가 정답에 있습니다: {''.join(sorted(unknown))}")

    labeled_images = {img for img, _ in labels}
    unlabeled = [img for img in images if img not in labeled_images]
    if unlabeled:
        rep.warn(f"정답이 없는 이미지 {len(unlabeled)}장은 검출 개수만 집계합니다 (예: {unlabeled[0]})")

    if check_images or roi:
        from PIL import Image

        for img in images:
            path = root / img
            if check_images:
                _check_image(path, rep, img)
            if roi:
                try:
                    with Image.open(path) as im:
                        w, h = im.size
                except Exception:
                    continue
                outside = [n for n, (x1, y1, x2, y2) in roi["panels"].items() if x2 > w or y2 > h]
                if outside:
                    rep.error(f"{img}: ROI 가 이미지({w}x{h}) 밖으로 나갑니다: {', '.join(outside)}")
                elif roi.get("image_width") and (w, h) != (roi["image_width"], roi["image_height"]):
                    rep.warn(f"{img}: 이미지 크기 {w}x{h} 가 roi_config.json 의 "
                             f"{roi['image_width']}x{roi['image_height']} 와 다릅니다")

    n_slots = sum(len(s) for s in labels.values())
    stats = {
        "task": "e2e",
        "mode": "frame" if roi else "panel",
        "counts": {
            "images": len(images),
            "panels": len(images) * len(roi["panels"]) if roi else len(images),
            "labeled_panels": len(labels),
            "labeled_slots": n_slots,
        },
    }
    if roi:
        stats["roi_panels"] = sorted(roi["panels"])
    return stats, rep


# ---------------------------------------------------------------- 운영 파이프라인과 같은 슬롯 규칙
def sort_boxes_2x3(boxes):
    """박스 6개를 슬롯 순서로 정렬합니다 (고객 운영 코드 model_detection.sort_boxes_2x3 와 같은 규칙).

    중심 x 로 정렬해 2개씩 한 열로 묶고, 열 안에서는 중심 y 로 정렬합니다.
        1열  2열  3열
    1행  1    3    5
    2행  2    4    6
    boxes: [x1, y1, x2, y2, conf, cls] 리스트
    """
    if len(boxes) != E2E_SLOTS:
        raise ValueError(f"박스가 정확히 {E2E_SLOTS}개여야 합니다: {len(boxes)}")
    by_x = sorted(boxes, key=lambda b: (b[0] + b[2]) / 2)
    out = []
    for i in range(0, E2E_SLOTS, 2):
        out.extend(sorted(by_x[i:i + 2], key=lambda b: (b[1] + b[3]) / 2))
    return out


def crop_box(image, box, padding=0):
    """운영 코드와 같은 방식으로 자릅니다: x1/y1 은 내림, x2/y2 는 반올림, 여백 후 이미지 안으로 제한."""
    h, w = image.shape[:2]
    x1 = max(0, int(box[0]) - padding)
    y1 = max(0, int(box[1]) - padding)
    x2 = min(w, int(round(box[2])) + padding)
    y2 = min(h, int(round(box[3])) + padding)
    if x2 <= x1 or y2 <= y1:
        return None, (x1, y1, x2, y2)
    return image[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]
