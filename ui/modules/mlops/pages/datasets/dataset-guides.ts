import { DatasetTask } from '../../services/apis/models/dataset.model';

/** 등록 전에 화면에서 바로 확인하는 필수 경로 (서버 검사가 최종 기준) */
export interface RequiredPath { path: string; kind: 'dir' | 'file'; }

export interface DatasetGuide {
  /** 이 종류로 학습·평가하는 모델 */
  usedBy: string;
  summary: string;
  /** 선택할 폴더의 구조 (트리 그림) */
  tree: string;
  /** 파일 안 내용 예시 */
  examples: { title: string; body: string }[];
  rules: string[];
  required: RequiredPath[];
}

export const DATASET_GUIDES: Record<DatasetTask, DatasetGuide> = {
  detection: {
    usedBy: 'YOLO26 · YOLOv8 학습',
    summary: '패널 이미지와 숫자 영역 박스 라벨(YOLO 형식)을 준비합니다. train, val은 필수이고 test가 있으면 최종 평가에 사용합니다.',
    tree:
`panel-det/            ← 이 폴더를 선택
├─ data.yaml          (선택) 클래스 이름
├─ images/
│  ├─ train/          *.png, *.jpg
│  ├─ val/
│  └─ test/           (선택)
└─ labels/
   ├─ train/          이미지와 같은 이름의 .txt
   ├─ val/
   └─ test/           (선택)`,
    examples: [
      { title: 'labels/train/0001.txt (한 줄에 박스 1개)', body: '0 0.512 0.334 0.120 0.080\n0 0.705 0.334 0.118 0.081' },
      { title: 'data.yaml (선택)', body: 'names: [number_group]' },
    ],
    rules: [
      '라벨 한 줄은 "클래스 중심x 중심y 너비 높이" 순서이며, 좌표는 이미지 크기에 대한 0~1 사이 비율입니다.',
      '라벨 파일 이름은 이미지 이름과 같아야 합니다 (0001.png ↔ 0001.txt).',
      '박스가 없는 이미지는 내용이 빈 .txt 파일을 둡니다.',
    ],
    required: [
      { path: 'images/train', kind: 'dir' }, { path: 'images/val', kind: 'dir' },
      { path: 'labels/train', kind: 'dir' }, { path: 'labels/val', kind: 'dir' },
    ],
  },
  recognition: {
    usedBy: 'PP-OCRv6 학습',
    summary: '잘라낸 숫자 이미지와 정답 목록을 준비합니다. 목록 파일의 한 줄이 이미지 1장입니다.',
    tree:
`panel-rec/            ← 이 폴더를 선택
├─ train_list.txt
├─ val_list.txt
├─ test_list.txt      (선택)
└─ images/            (폴더 이름·구조는 자유)
   ├─ 000001.png
   └─ ...`,
    examples: [
      { title: 'train_list.txt (이미지 경로, 탭, 정답)', body: 'images/000001.png\t1948\nimages/000002.png\t75' },
    ],
    rules: [
      '경로와 정답 사이는 탭(Tab) 1칸으로 구분합니다. 경로는 선택한 폴더 기준의 상대경로로 적습니다.',
      '파일은 UTF-8로 저장합니다(BOM 허용). 정답에는 인식 사전에 있는 글자만 사용할 수 있습니다.',
      '같은 이미지가 train과 val에 함께 있으면 경고를 표시합니다.',
    ],
    required: [{ path: 'train_list.txt', kind: 'file' }, { path: 'val_list.txt', kind: 'file' }],
  },
  e2e: {
    usedBy: 'E2E 평가\n(검출 + 인식)',
    summary: '패널(또는 전체 프레임) 이미지와 슬롯별 정답을 준비합니다. 학습에는 쓰지 않고 E2E 평가에만 사용합니다.',
    tree:
`e2e-panel/            ← 이 폴더를 선택
├─ labels.txt
├─ roi_config.json    (선택) 있으면 전체 프레임 모드
└─ images/
   └─ frame_000001_panel_1.png`,
    examples: [
      { title: 'labels.txt (이미지, 패널, 슬롯 1~6, 정답을 탭으로 구분)', body: 'images/frame_000001_panel_1.png\tpanel_1\t1\t1948\nimages/frame_000001_panel_1.png\tpanel_1\t3\t75' },
      { title: 'roi_config.json (선택, 프레임 모드)', body: '{"panels": {"panel_1": [x1, y1, x2, y2], ...}}' },
    ],
    rules: [
      '패널 모드: 이미지 1장이 패널 1개입니다.',
      '프레임 모드: roi_config.json의 픽셀 좌표로 패널을 잘라 평가합니다. 현장 운영 코드와 같은 방식입니다.',
      '평가 데이터는 학습에 사용한 데이터와 겹치지 않게 준비합니다.',
    ],
    required: [{ path: 'labels.txt', kind: 'file' }],
  },
  timeseries: {
    usedBy: '1D-CNN 학습',
    summary: '센서 시계열 구간(윈도)과 정답을 numpy 배열 파일(.npy)로 준비합니다. 분류와 회귀를 모두 지원합니다.',
    tree:
`sensor-ts/            ← 이 폴더를 선택
├─ meta.json          (선택)
├─ train/
│  ├─ X.npy
│  └─ y.npy
├─ val/
│  ├─ X.npy
│  └─ y.npy
└─ test/              (선택)
   ├─ X.npy
   └─ y.npy`,
    examples: [
      { title: '배열 모양', body: 'X.npy  (샘플 수, 윈도 길이, 채널 수)     예: (6000, 20, 52)\ny.npy  분류: (샘플 수,) 정수 라벨\n       회귀: (샘플 수,) 또는 (샘플 수, 출력 수) 실수' },
      { title: 'meta.json (선택)', body: '{"problem": "classification", "class_names": ["정상", "고장A", "고장B"]}' },
    ],
    rules: [
      'train, val, test의 윈도 길이와 채널 수가 같아야 합니다. NaN과 무한대 값은 사용할 수 없습니다.',
      'meta.json이 없으면 y가 정수 1열일 때 분류, 그 외에는 회귀로 판단합니다.',
      '파이썬에서는 np.save("train/X.npy", X)로 저장합니다.',
    ],
    required: [
      { path: 'train/X.npy', kind: 'file' }, { path: 'train/y.npy', kind: 'file' },
      { path: 'val/X.npy', kind: 'file' }, { path: 'val/y.npy', kind: 'file' },
    ],
  },
};
