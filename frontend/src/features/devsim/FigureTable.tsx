/**
 * 곡선에서 뽑은 지표 표.
 *
 * 곡선만 겹쳐 놓으면 "다르다"는 것만 보이고 얼마나 다른지는 안 보인다. 문턱전압
 * 0.1V 차이와 온전류 두 배 차이는 눈으로 구분되지 않는다.
 *
 * 낼 수 없는 값은 빈칸으로 둔다. 억지로 채우면 그게 측정값인 줄 알고 읽게 된다.
 */
import type { Figures } from './figures'

export interface FigureRow {
  label: string
  figures: Figures
}

function engineering(value: number | null, unit: string): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${value.toExponential(2)} ${unit}`
}

function volts(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(3)} V`
}

function ratio(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  const decades = Math.log10(value)
  return `10^${decades.toFixed(1)}`
}

function swing(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(0)} mV/dec`
}

const COLUMNS: {
  key: string
  head: string
  title: string
  render: (figures: Figures) => string
}[] = [
  {
    key: 'ion',
    head: 'I_on',
    title: '곡선에서 가장 큰 전류',
    render: (f) => engineering(f.iOn, 'A/µm'),
  },
  {
    key: 'ioff',
    head: 'I_off',
    title: '0 이 아닌 가장 작은 전류',
    render: (f) => engineering(f.iOff, 'A/µm'),
  },
  {
    key: 'onoff',
    head: 'on/off',
    title: 'I_on / I_off',
    render: (f) => ratio(f.onOff),
  },
  {
    key: 'vth',
    head: 'V_th',
    title: '최대 gm 접선을 가로축까지 늘려 얻은 값 (전달 특성에서만 뜻이 있다)',
    render: (f) => volts(f.vth),
  },
  {
    key: 'ss',
    head: 'SS',
    title: '문턱 아래 기울기',
    render: (f) => swing(f.ss),
  },
  {
    key: 'gm',
    head: 'gm_max',
    title: '최대 상호컨덕턴스 dI/dV',
    render: (f) => engineering(f.gmMax, 'S/µm'),
  },
  {
    key: 'ron',
    head: 'R_on',
    title: '원점 부근 기울기의 역수 (출력 특성에서만 뜻이 있다)',
    render: (f) => engineering(f.ron, 'Ω·µm'),
  },
]

export function FigureTable({ rows }: { rows: FigureRow[] }) {
  if (rows.length === 0) return null
  return (
    <div className="figure-table">
      <table>
        <thead>
          <tr>
            <th scope="col">곡선</th>
            {COLUMNS.map((column) => (
              <th scope="col" key={column.key} title={column.title}>
                {column.head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {COLUMNS.map((column) => (
                <td key={column.key}>{column.render(row.figures)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
