/**
 * NRRD 파일 파서.
 *
 * 3D Slicer에서 내보낸 볼륨/세그멘테이션 로딩용.
 * 기존 nrrd.js의 ES 모듈 + TypeScript 버전.
 */

import pako from 'pako';

/** NRRD 헤더 정보 */
export interface NRRDHeader {
  dimension: number;
  sizes: number[];
  type: string;
  encoding: string;
  spacing: number[];
  spaceDirections: (number[] | null)[] | null;
  spaceOrigin: number[];
}

/** NRRD 파싱 결과 */
export interface NRRDData {
  header: NRRDHeader;
  data: ArrayLike<number>;
}

type TypedArrayConstructor =
  | typeof Uint8Array
  | typeof Int8Array
  | typeof Uint16Array
  | typeof Int16Array
  | typeof Uint32Array
  | typeof Int32Array
  | typeof Float32Array
  | typeof Float64Array;

/** NRRD 타입 → TypedArray 매핑 */
const TYPE_MAP: Record<string, string> = {
  uchar: 'uint8',
  'unsigned char': 'uint8',
  uint8: 'uint8',
  uint8_t: 'uint8',
  char: 'int8',
  'signed char': 'int8',
  int8: 'int8',
  int8_t: 'int8',
  ushort: 'uint16',
  'unsigned short': 'uint16',
  uint16: 'uint16',
  uint16_t: 'uint16',
  short: 'int16',
  'signed short': 'int16',
  int16: 'int16',
  int16_t: 'int16',
  uint: 'uint32',
  'unsigned int': 'uint32',
  uint32: 'uint32',
  uint32_t: 'uint32',
  int: 'int32',
  'signed int': 'int32',
  int32: 'int32',
  int32_t: 'int32',
  float: 'float32',
  double: 'float64',
};

export class NRRDLoader {
  /** NRRD 파일 파싱 */
  static parse(buffer: ArrayBuffer): NRRDData {
    const bytes = new Uint8Array(buffer);

    // 헤더와 데이터 분리
    const { header, dataOffset } = this._parseHeader(bytes);

    // 데이터 추출
    const rawData = buffer.slice(dataOffset);

    // 디코딩
    let decodedData: ArrayBuffer;
    if (header.encoding === 'gzip') {
      decodedData = this._decodeGzip(rawData);
    } else if (header.encoding === 'raw') {
      decodedData = rawData;
    } else {
      throw new Error(`지원하지 않는 인코딩: ${header.encoding}`);
    }

    // 타입에 맞는 배열로 변환
    const typedData = this._toTypedArray(decodedData, header.type);

    console.log('NRRD 로딩 완료:', {
      sizes: header.sizes,
      type: header.type,
      encoding: header.encoding,
      spacing: header.spacing,
      dataLength: typedData.length,
    });

    return { header, data: typedData };
  }

  /** 헤더 파싱 */
  private static _parseHeader(bytes: Uint8Array): { header: NRRDHeader; dataOffset: number } {
    let headerEnd = 0;
    let prevNewline = false;

    for (let i = 0; i < bytes.length - 1; i++) {
      if (bytes[i] === 10) {
        // \n
        if (prevNewline) {
          headerEnd = i + 1;
          break;
        }
        prevNewline = true;
      } else if (bytes[i] !== 13) {
        // \r가 아니면
        prevNewline = false;
      }
    }

    const headerText = new TextDecoder().decode(bytes.slice(0, headerEnd));
    const header = this._parseHeaderText(headerText);

    return { header, dataOffset: headerEnd };
  }

  /** 헤더 텍스트 파싱 */
  private static _parseHeaderText(text: string): NRRDHeader {
    const header: NRRDHeader = {
      dimension: 3,
      sizes: [1, 1, 1],
      type: 'uint8',
      encoding: 'raw',
      spacing: [1, 1, 1],
      spaceDirections: null,
      spaceOrigin: [0, 0, 0],
    };

    const lines = text.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;

      const colonIdx = trimmed.indexOf(':');
      if (colonIdx === -1) continue;

      const key = trimmed.slice(0, colonIdx).trim().toLowerCase();
      const value = trimmed.slice(colonIdx + 1).trim();

      switch (key) {
        case 'dimension':
          header.dimension = parseInt(value);
          break;
        case 'sizes':
          header.sizes = value.split(/\s+/).map(Number);
          break;
        case 'type':
          header.type = TYPE_MAP[value.toLowerCase()] || 'uint8';
          break;
        case 'encoding':
          header.encoding = value.toLowerCase();
          break;
        case 'spacings':
        case 'spacing':
          header.spacing = value.split(/\s+/).map(Number);
          break;
        case 'space directions':
          header.spaceDirections = this._parseSpaceDirections(value);
          if (header.spaceDirections) {
            header.spacing = header.spaceDirections.map((dir) => {
              if (!dir) return 1;
              return Math.sqrt(dir[0] * dir[0] + dir[1] * dir[1] + dir[2] * dir[2]);
            });
          }
          break;
        case 'space origin': {
          const match = value.match(/\(([-\d.e+]+),([-\d.e+]+),([-\d.e+]+)\)/);
          if (match) {
            header.spaceOrigin = [parseFloat(match[1]), parseFloat(match[2]), parseFloat(match[3])];
          }
          break;
        }
      }
    }

    return header;
  }

  /** space directions 파싱 */
  private static _parseSpaceDirections(value: string): (number[] | null)[] | null {
    const dirs: (number[] | null)[] = [];
    const regex = /\(([-\d.e+]+),([-\d.e+]+),([-\d.e+]+)\)|none/g;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(value)) !== null) {
      if (match[0] === 'none') {
        dirs.push(null);
      } else {
        dirs.push([parseFloat(match[1]), parseFloat(match[2]), parseFloat(match[3])]);
      }
    }

    return dirs.length > 0 ? dirs : null;
  }

  /** Gzip 디코딩 */
  private static _decodeGzip(buffer: ArrayBuffer): ArrayBuffer {
    try {
      const decompressed = pako.inflate(new Uint8Array(buffer));
      return decompressed.buffer;
    } catch (e) {
      throw new Error(`Gzip 디코딩 실패: ${(e as Error).message}`);
    }
  }

  /** 타입에 맞는 TypedArray로 변환 */
  private static _toTypedArray(buffer: ArrayBuffer, type: string): ArrayLike<number> {
    const constructors: Record<string, TypedArrayConstructor> = {
      uint8: Uint8Array,
      int8: Int8Array,
      uint16: Uint16Array,
      int16: Int16Array,
      uint32: Uint32Array,
      int32: Int32Array,
      float32: Float32Array,
      float64: Float64Array,
    };
    const Ctor = constructors[type] || Uint8Array;
    return new Ctor(buffer);
  }
}
