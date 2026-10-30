/** RFC 4180 CSV 파싱 (따옴표, 줄바꿈 포함 필드, BOM, CRLF 처리). 첫 줄은 헤더. */
export function parseCsv(text: string): Record<string, string>[] {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else quoted = false;
      } else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); field = '';
      rows.push(row); row = [];
    } else field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  const data = rows.filter(r => !(r.length === 1 && r[0] === ''));
  if (!data.length) return [];
  const header = data[0];
  return data.slice(1).map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ''])));
}
