"""NPZ 결과 파일을 JSON으로 변환.

FEA 결과를 웹 시각화에서 사용할 수 있도록 변환합니다.

사용법:
    python convert_npz.py <input.npz> [output.json]
"""

import json
import numpy as np
import sys
from pathlib import Path


def convert_npz_to_json(input_path: str, output_path: str = None):
    """NPZ 파일을 JSON으로 변환.

    Args:
        input_path: 입력 NPZ 파일 경로
        output_path: 출력 JSON 파일 경로 (None이면 입력 파일명.json)
    """
    input_path = Path(input_path)

    if not input_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {input_path}")
        return

    if output_path is None:
        output_path = input_path.with_suffix('.json')
    else:
        output_path = Path(output_path)

    print(f"로드 중: {input_path}")
    data = np.load(input_path)

    # NPZ 키 확인
    print(f"키: {list(data.keys())}")

    # JSON 변환 (numpy 배열을 리스트로)
    json_data = {}

    for key in data.keys():
        arr = data[key]
        print(f"  {key}: shape={arr.shape}, dtype={arr.dtype}")

        # numpy 배열을 Python 리스트로 변환
        json_data[key] = arr.tolist()

    # JSON 저장
    print(f"저장 중: {output_path}")
    with open(output_path, 'w') as f:
        json.dump(json_data, f)

    # 파일 크기
    size_kb = output_path.stat().st_size / 1024
    print(f"완료: {size_kb:.1f} KB")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n사용 가능한 NPZ 파일:")

        # 현재 디렉토리와 상위 디렉토리에서 npz 파일 검색
        for pattern in ['*.npz', '../*.npz', '../../*.npz', '../../../*.npz']:
            for f in Path('.').glob(pattern):
                print(f"  {f}")
        return

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    convert_npz_to_json(input_path, output_path)


if __name__ == '__main__':
    main()
