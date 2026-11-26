# UI 디자인 기준

KITECH 공정 모델을 학습·평가·배포하는 연구소 내부 도구입니다. 측정 장비 소프트웨어처럼 조용하고 정확한 화면을 지향합니다. 장식보다 데이터가 먼저 보여야 합니다.

## 토큰

값은 `src/styles/_tokens.scss` 한곳에서 관리합니다. 화면 SCSS에는 색 코드와 글자 크기 숫자를 쓰지 않습니다.

| 분류 | 토큰 | 값 |
|---|---|---|
| 주 색 | `--main-primary-color` | `#002387` |
| 선택 배경 | `--main-primary-light` | `#e9edf6` |
| 페이지 배경 | `--bg-body` | `#f4f5f7` |
| 표면 | `--bg-card` | `#ffffff` |
| 테두리 | `--border-color` | `#dfe3e8` |
| 본문 글자 | `--text-main` | `#1a2130` |
| 보조 글자 | `--text-muted` | `#566072` |

상태 색은 `--success`, `--warning`, `--error`, `--info`, `--neutral`이며, 각각 글자색 `-color`와 배경색 `-bg`가 짝입니다.

## 글자

글꼴은 Pretendard 하나를 씁니다. 코드와 해시만 `--font-mono`를 씁니다.

| 역할 | 토큰 | 크기 |
|---|---|---|
| 페이지 제목 | `--text-page` | 22px / 700 |
| 섹션 제목 | `--text-section` | 16px / 600 |
| 본문·표·입력 | `--text-body` | 14px |
| 라벨·표 헤더 | `--text-label` | 13px |
| 보조·배지 | `--text-meta` | 13px |
| 큰 수치 | `--text-metric` | 24px / 600 |

**13px 미만은 쓰지 않습니다.** 차트 축과 범례도 13px입니다.

## 모양

- 반경은 `--radius-sm` 4px(배지), `--radius-md` 6px(버튼·입력), `--radius-lg` 8px(카드·다이얼로그) 세 단계입니다.
- 카드는 1px 테두리만 씁니다. 그림자는 다이얼로그와 메뉴에만 씁니다.
- 전환은 150ms 색 변화만 씁니다. 떠오르는 hover와 등장 애니메이션은 쓰지 않습니다.

## 쓰지 않는 것

- 그라데이션 버튼과 배경 (스켈레톤 shimmer 제외)
- 카드 왼쪽·위쪽의 굵은 색 띠
- 알약 모양 버튼과 탭
- 제목 옆 장식 아이콘
- 채움 색 위험 버튼. 중지·삭제는 빨강 외곽선 버튼으로 구분합니다.

## 공용 요소

| 요소 | 위치 |
|---|---|
| 페이지 머리말 `app-page-header` | `modules/shared/ui/page-header` |
| 경로 표시 `app-breadcrumb` | `modules/shared/ui/breadcrumb` |
| 상대 시간 `relativeTime` | `modules/shared/utils/format.ts` |
| 차트 색과 기본값 | `modules/shared/utils/chart-theme.ts` |
| 상태 배지 `.status-badge[data-status]` | `src/styles/_status.scss` |
| 전역 패턴 `.filter-tab` `.drop-zone` `.info-item` `.inline-tag` `.count-badge` | `src/styles/_patterns.scss` |

마크업 구조까지 반복되면 컴포넌트로, 스타일만 반복되면 전역 클래스로 묶습니다.

## 폴더

기능 화면은 `modules/mlops/features/{datasets,training,evaluation,inference,common}`에 둡니다. `.gitignore`의 `datasets/` 규칙 때문에 `features/datasets/` 안에는 `datasets/`라는 이름의 폴더를 만들지 않습니다.
