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
