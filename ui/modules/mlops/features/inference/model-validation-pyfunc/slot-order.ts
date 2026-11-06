/** [x1, y1, x2, y2, conf, cls] */
export type Box = number[];

export const PANEL_SLOTS = 6;

/**
 * 박스 6개를 슬롯 순서로 정렬합니다 (training/dataset_tools.py sort_boxes_2x3 와 같은 규칙).
 * 중심 x 로 정렬해 2개씩 한 열로 묶고, 열 안에서는 중심 y 로 정렬합니다.
 *      1열 2열 3열
 * 1행   1   3   5
 * 2행   2   4   6
 */
export function sortBoxes2x3(boxes: Box[]): Box[] {
  if (boxes.length !== PANEL_SLOTS) {
    throw new Error(`박스가 정확히 ${PANEL_SLOTS}개여야 합니다: ${boxes.length}`);
  }
  const cx = (b: Box) => (b[0] + b[2]) / 2;
  const cy = (b: Box) => (b[1] + b[3]) / 2;
  const byX = [...boxes].sort((a, b) => cx(a) - cx(b));
  const out: Box[] = [];
  for (let i = 0; i < PANEL_SLOTS; i += 2) {
    out.push(...byX.slice(i, i + 2).sort((a, b) => cy(a) - cy(b)));
  }
  return out;
}
