/**
 * HEX8 요소 기하 유틸리티
 *
 * - HEX8_FACES: 6개 면의 로컬 노드 인덱스 (외향 법선 기준 반시계)
 * - extractSurfaceTriangles: 내부 공유 면 제거, 외부 면만 삼각형으로 변환
 */

/**
 * HEX8 요소 면 정의 (6면, 각 4노드)
 * 외향 법선 기준 반시계 방향
 */
export const HEX8_FACES: number[][] = [
  [0, 3, 2, 1], // 하부 (z-)
  [4, 5, 6, 7], // 상부 (z+)
  [0, 1, 5, 4], // 전면 (y-)
  [2, 3, 7, 6], // 후면 (y+)
  [0, 4, 7, 3], // 좌측 (x-)
  [1, 2, 6, 5], // 우측 (x+)
];

/**
 * HEX8 요소에서 표면 삼각형 추출
 *
 * 내부 면(2개 요소가 공유)은 제외하고, 외부 면만 삼각형으로 변환한다.
 *
 * @param elements 요소별 글로벌 노드 인덱스 배열 (n_elem × 8)
 * @returns 삼각형 배열 — 각 삼각형은 [nodeIdx0, nodeIdx1, nodeIdx2]
 */
export function extractSurfaceTriangles(elements: number[][]): number[][] {
  // 면 → 등장 횟수 매핑 (정렬된 노드 키)
  const faceCount = new Map<string, { nodes: number[]; count: number }>();

  for (const elem of elements) {
    for (const faceLocalNodes of HEX8_FACES) {
      const globalNodes = faceLocalNodes.map(li => elem[li]);
      // 정렬된 키로 공유 면 감지
      const key = [...globalNodes].sort((a, b) => a - b).join(',');
      const existing = faceCount.get(key);
      if (existing) {
        existing.count++;
      } else {
        faceCount.set(key, { nodes: globalNodes, count: 1 });
      }
    }
  }

  // count === 1 인 면만 외부 표면 → 쿼드 → 삼각형 2개
  const triangles: number[][] = [];
  for (const { nodes, count } of faceCount.values()) {
    if (count === 1) {
      const [n0, n1, n2, n3] = nodes;
      triangles.push([n0, n1, n2]);
      triangles.push([n0, n2, n3]);
    }
  }

  return triangles;
}
