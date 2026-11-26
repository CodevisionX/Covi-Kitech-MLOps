/** 브라우저에서 .npy(숫자 배열)를 읽습니다. 정답 y.npy 채점용이라 숫자 자료형만 지원합니다. */
export interface NpyArray { shape: number[]; data: Float64Array; }

export function parseNpy(buf: ArrayBuffer): NpyArray {
  const bytes = new Uint8Array(buf);
  if (bytes[0] !== 0x93 || String.fromCharCode(...bytes.slice(1, 6)) !== 'NUMPY') {
    throw new Error('.npy 파일이 아닙니다');
  }
  const major = bytes[6];
  const view = new DataView(buf);
  const headerLen = major >= 2 ? view.getUint32(8, true) : view.getUint16(8, true);
  const offset = (major >= 2 ? 12 : 10) + headerLen;
  const header = new TextDecoder('latin1').decode(bytes.slice(major >= 2 ? 12 : 10, offset));
  const descr = /'descr':\s*'([^']+)'/.exec(header)?.[1] || '';
  if (/'fortran_order':\s*True/.test(header)) throw new Error('fortran_order 배열은 지원하지 않습니다');
  const shape = (/'shape':\s*\(([^)]*)\)/.exec(header)?.[1] || '').split(',').map(s => s.trim()).filter(Boolean).map(Number);
  const n = shape.reduce((a, b) => a * b, 1);
  if (descr[0] === '>') throw new Error('빅엔디언 배열은 지원하지 않습니다');
  const kind = descr.slice(1);
  const ctor: Record<string, any> = {
    f8: Float64Array, f4: Float32Array, i8: BigInt64Array, i4: Int32Array, i2: Int16Array, i1: Int8Array,
    u8: BigUint64Array, u4: Uint32Array, u2: Uint16Array, u1: Uint8Array, b1: Uint8Array,
  };
  const T = ctor[kind];
  if (!T) throw new Error(`지원하지 않는 자료형입니다: ${descr}`);
  const raw = new T(buf.slice(offset, offset + n * T.BYTES_PER_ELEMENT));
  return { shape, data: Float64Array.from(raw as ArrayLike<number | bigint>, v => Number(v)) };
}
