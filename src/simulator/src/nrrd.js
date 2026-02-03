/**
 * NRRD 파일 파서
 * 3D Slicer에서 내보낸 볼륨/세그멘테이션 로딩용
 */

class NRRDLoader {
    /**
     * NRRD 파일 파싱
     * @param {ArrayBuffer} buffer - 파일 데이터
     * @returns {Object} { header, data }
     */
    static parse(buffer) {
        const bytes = new Uint8Array(buffer);

        // 헤더와 데이터 분리
        const { header, dataOffset } = this._parseHeader(bytes);

        // 데이터 추출
        const rawData = buffer.slice(dataOffset);

        // 디코딩
        let decodedData;
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
            dataLength: typedData.length
        });

        return { header, data: typedData };
    }

    /**
     * 헤더 파싱
     */
    static _parseHeader(bytes) {
        // 헤더는 텍스트, 빈 줄로 데이터와 분리
        let headerEnd = 0;
        let prevNewline = false;

        for (let i = 0; i < bytes.length - 1; i++) {
            // \n\n 또는 \r\n\r\n 찾기
            if (bytes[i] === 10) {  // \n
                if (prevNewline) {
                    headerEnd = i + 1;
                    break;
                }
                prevNewline = true;
            } else if (bytes[i] !== 13) {  // \r가 아니면
                prevNewline = false;
            }
        }

        const headerText = new TextDecoder().decode(bytes.slice(0, headerEnd));
        const header = this._parseHeaderText(headerText);

        return { header, dataOffset: headerEnd };
    }

    /**
     * 헤더 텍스트 파싱
     */
    static _parseHeaderText(text) {
        const header = {
            dimension: 3,
            sizes: [1, 1, 1],
            type: 'uint8',
            encoding: 'raw',
            spacing: [1, 1, 1],
            spaceDirections: null,
            spaceOrigin: [0, 0, 0]
        };

        const lines = text.split('\n');

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;

            // key: value 형식
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
                    header.type = this._normalizeType(value);
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
                        // space directions에서 spacing 추출
                        header.spacing = header.spaceDirections.map(dir => {
                            if (!dir) return 1;
                            return Math.sqrt(dir[0]*dir[0] + dir[1]*dir[1] + dir[2]*dir[2]);
                        });
                    }
                    break;

                case 'space origin':
                    const match = value.match(/\(([-\d.e+]+),([-\d.e+]+),([-\d.e+]+)\)/);
                    if (match) {
                        header.spaceOrigin = [
                            parseFloat(match[1]),
                            parseFloat(match[2]),
                            parseFloat(match[3])
                        ];
                    }
                    break;
            }
        }

        return header;
    }

    /**
     * space directions 파싱
     * 예: (1,0,0) (0,1,0) (0,0,1) 또는 none (1,0,0) ...
     */
    static _parseSpaceDirections(value) {
        const dirs = [];
        const regex = /\(([-\d.e+]+),([-\d.e+]+),([-\d.e+]+)\)|none/g;
        let match;

        while ((match = regex.exec(value)) !== null) {
            if (match[0] === 'none') {
                dirs.push(null);
            } else {
                dirs.push([
                    parseFloat(match[1]),
                    parseFloat(match[2]),
                    parseFloat(match[3])
                ]);
            }
        }

        return dirs.length > 0 ? dirs : null;
    }

    /**
     * 타입 정규화
     */
    static _normalizeType(type) {
        const typeMap = {
            'uchar': 'uint8',
            'unsigned char': 'uint8',
            'uint8': 'uint8',
            'uint8_t': 'uint8',
            'char': 'int8',
            'signed char': 'int8',
            'int8': 'int8',
            'int8_t': 'int8',
            'ushort': 'uint16',
            'unsigned short': 'uint16',
            'uint16': 'uint16',
            'uint16_t': 'uint16',
            'short': 'int16',
            'signed short': 'int16',
            'int16': 'int16',
            'int16_t': 'int16',
            'uint': 'uint32',
            'unsigned int': 'uint32',
            'uint32': 'uint32',
            'uint32_t': 'uint32',
            'int': 'int32',
            'signed int': 'int32',
            'int32': 'int32',
            'int32_t': 'int32',
            'float': 'float32',
            'double': 'float64'
        };

        return typeMap[type.toLowerCase()] || 'uint8';
    }

    /**
     * Gzip 디코딩 (pako 라이브러리 사용)
     */
    static _decodeGzip(buffer) {
        if (typeof pako === 'undefined') {
            throw new Error('Gzip 디코딩을 위해 pako 라이브러리가 필요합니다');
        }

        try {
            const decompressed = pako.inflate(new Uint8Array(buffer));
            return decompressed.buffer;
        } catch (e) {
            throw new Error(`Gzip 디코딩 실패: ${e.message}`);
        }
    }

    /**
     * 타입에 맞는 TypedArray로 변환
     */
    static _toTypedArray(buffer, type) {
        switch (type) {
            case 'uint8':
                return new Uint8Array(buffer);
            case 'int8':
                return new Int8Array(buffer);
            case 'uint16':
                return new Uint16Array(buffer);
            case 'int16':
                return new Int16Array(buffer);
            case 'uint32':
                return new Uint32Array(buffer);
            case 'int32':
                return new Int32Array(buffer);
            case 'float32':
                return new Float32Array(buffer);
            case 'float64':
                return new Float64Array(buffer);
            default:
                return new Uint8Array(buffer);
        }
    }
}

// 전역으로 내보내기
window.NRRDLoader = NRRDLoader;
