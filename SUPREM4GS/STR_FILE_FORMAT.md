# SUPREM4GS `.str` Structure File Format

`examples/exam1/boron.in` 실행 결과(`boron.str`)를 분석하고, `postmini`(공식 후처리 툴)의
`Line` 명령으로 실제 값을 대조해 검증한 내용. 검증 방법: `chmod +x postmini` 후
`Read` → `SUPREM4` → 파일명으로 구조 로드, `Line` 메뉴에서 각 quantity(1~7)를 파일로
export해서 raw `.str`의 `n` 라인 컬럼 값과 1:1 대조.

## 전체 라인 타입

| prefix | 예시 | 의미 |
|---|---|---|
| `v` | `v SUPREM-IV.GS B.9305` | 버전 헤더 |
| `D` | `D 1 2 2` | 차원 정보 (1D 모드 등) |
| `c` | `c 1 0  0` | 노드 좌표. `c <node_id 1-based> <x> <y(1D는 0)>` |
| `r` | `r 1   3` | 영역-물질 매핑. `r <region_id> <material_id>` |
| `t` | `t 1 1 2 1 42 2 -1 -1` | 요소(element) 연결성. `t <elem_id> <region_id> <node...> -1 -1` |
| `M` | `M 0 1.373000e+03` | 온도 기록 (K). 예: 1.373e3K = 1100°C (`diffuse temp=1100`) |
| `s` | `s 6   5 23 0 1 12 14` | 이 구조에서 추적하는 species/solution-variable 개수 및 내부 코드 |
| `n` | `n 0   3   5.86e18 ...` | **노드별 물성 데이터.** 아래 상세 참조 |
| `I` | `I 6   1 1 0 0 0 0` | 인터페이스/경계 레코드 |

## `n` 라인 상세 (핵심 - 검증 완료)

```
n <node_id (0-based)> <material_id> <col1> <col2> <col3> <col4> <col5> <col6>
```

- **node_id는 0-based.** `c` 라인의 노드 번호는 1-based이므로 `n 41 ...` → `c 42`(예:
  x=2.0, exam1 기준 마지막 노드)에 대응. 오프셋 -1 로 변환 필요.
- **material_id**: `r` 라인에서 정의된 region-material 매핑과 일치.
  exam1 기준 `0`=ambient(노출 표면 바깥, 별도 region 없이 암묵적), `1`=oxide, `3`=silicon.
  경계 노드(oxide/ambient 계면, oxide/silicon 계면 등)는 인접한 material마다 한 줄씩
  중복으로 나타남 (내부 벌크 노드는 한 줄만 존재).

### 컬럼 매핑 (단일 도펀트=boron 예제로 검증됨)

| 컬럼 | 항목 | 단위/비고 |
|---|---|---|
| col1 | Chem. Boron Concentration | cm⁻³ (화학적/total 농도) |
| col2 | Active Boron Concentration | cm⁻³ (전기적 활성 농도 — depth profile 플롯엔 보통 이 값) |
| col3 | Vacancies | cm⁻³ |
| col4 | Interstitials | cm⁻³ |
| col5 | Interstitial Traps | fraction |
| col6 | Potential | V |

- **Net doping**은 파일에 별도 저장되지 않음. `-Active Concentration`으로 파생 계산
  (boron 단일 도펀트라 acceptor라서 음수 부호).
- `postmini`의 `Line` 메뉴 quantity 목록(1~7: Chem Boron, Active Boron, Vacancies,
  Interstitials, Interstitial Traps, Potential, Net doping)과 대조해 col1~col6가
  1~6번 quantity와 정확히 일치함을 확인.

### 다중 도펀트 / 2D 케이스 검증 결과 (`examples/mosfet/CMOS.in`)

> `CMOS.in` 은 2026-08-21 에 `examples/mosfet/nmos.in` 으로 대체됐다. 아래 검증은
> 그 파일로 한 것이고, 결론(컬럼 규칙)은 파일과 무관하게 유효하다. 당시 산출물은
> `backend/tests/fixtures/` 의 `2d_cmos_source.str` 로 남아 있으며 지금도 시험이
> 그것을 쓴다.

`CMOS.in`(2D, boron+phosphorus+arsenic 3종 도펀트, silicon/oxide/poly 3개 물질)을
실행해서 나온 `source.str`(소스/드레인 arsenic implant 이후 최종 구조)로 재검증함.
결과: **컬럼 개수·순서는 도펀트 구성에 따라 달라지지만, 항상 `s` 라인이 선언한
species 개수 = `n` 라인의 값 개수 = `postmini` `Line` 메뉴에 뜨는 quantity 개수/순서와
1:1로 일치**한다는 일반 규칙을 확인함.

`source.str`의 `s` 라인: `s 14   5 23 8 9 19 0 1 12 14 24 3 21 2 20` (14개 species) →
`n` 라인도 값이 14개. `postmini` `Line` 메뉴도 14개 quantity를 보여줌:

```
n <node_id(0-based)> <material_id> <col1> ... <col14>

col1  = Chem. Boron Concentration
col2  = Active Boron Concentration
col3  = X velocity              (이동 경계 계산용, 저장된 구조에선 보통 0)
col4  = Y velocity              (위와 동일)
col5  = Delta Interface Area    (위와 동일)
col6  = Vacancies
col7  = Interstitials
col8  = Interstitial Traps
col9  = Potential
col10 = Net doping              (※ 아래 주의 참고 — 이 예제에서는 항상 0으로 나옴,
                                    domain 전역에서 ActiveBoron이 1e16 수준으로
                                    non-zero인데도 raw column과 postmini 추출값
                                    모두 0. 전기 시뮬레이션을 안 켠 순수 공정 시뮬레이션
                                    에서는 이 슬롯이 채워지지 않는 것으로 보임.
                                    → 파서에서는 이 컬럼을 신뢰하지 말고
                                    Net = (Active P + Active As + ...) - Active B
                                    식으로 직접 계산할 것)
col11 = Chem. Phosphorous Concentration
col12 = Active Phosphorous Concentration
col13 = Chem. Arsenic Concentration
col14 = Active Arsenic Concentration
```

검증 방법: `x=0` 수직 cut에서 `postmini`가 뽑아준 `.B_CHEM/.B/.VACANCIES/...` 각
파일 값을 같은 좌표의 raw `n` 라인 각 컬럼과 直접 대조 (byte-exact 일치, oxide
영역의 sentinel 값 `[Xvel,Yvel,DeltaArea,Vacancies,Interstitials,ITraps,Potential]
= [0,0,0,1.0,1.0,0.5,0]` 패턴도 정확히 일치). col1~col9, col11~col14는 다수
depth 지점에서 확인 완료. col10(Net doping)만 예외적으로 이 예제에서 유효한
값을 못 얻음.

**material_id도 이번엔 4개** (`r 1 3`=silicon, `r 2 1`=oxide, `r 3 4`=poly,
`r 4 1`=oxide 두번째 region). 같은 oxide 가 region 2 와 4 로 나뉘어 있다는 점에
주목 — region_id 로 물질을 판단하면 안 되고 `r` 라인의 material_id 를 봐야 한다.
material_id→이름 자체는 고정 열거형이며 아래 "Material ID 매핑" 섹션에 확정해 뒀다.

## ★ 메시 구조 (`D` / `c` / `t` 라인) — 바이너리 역어셈블로 확정

앞선 판에서 "`t` 라인 필드 의미 미검증"으로 남겨뒀던 부분을 확정했다. 추론이 아니라
`suprem` 바이너리(unstripped ELF)의 `.str` 리더/라이터를 직접 역어셈블한 결과다:
`ig2_read`(0x42dc90), `ig2_write`(0x42e8d0), `mk_ele`, `mk_nd`, `alloc_tri`, `ChosenBC`.

### `D` 라인 = `D <mode> <nvrt> <nedg>`

`ig2_write` 가 전역변수 mode / nvrt / nedg 를 그대로 출력한다.

```
D 1 2 2   →  1D, 요소당 정점 2개, 이웃 2개
D 2 3 3   →  2D, 요소당 정점 3개, 이웃 3개
```

**이 값이 `t` 라인의 필드 배치를 결정한다.** 필드 수 = `2 + nvrt + nedg + 2`
(1D는 8개, 2D는 10개). 하드코딩하지 말고 `D` 라인을 읽어서 쓸 것.

### `t` 라인 = `t <elem_id> <region_id> <정점 nvrt개> <이웃 nedg개> <미확정 2개>`

| 위치 | 내용 | 비고 |
|---|---|---|
| 1 | elem_id | 1-based, 항상 순차 |
| 2 | region_id | 1-based, `r` 라인의 키 |
| 3 ~ 2+nvrt | **정점** | **1-based 좌표(`c`) 인덱스** |
| 다음 nedg개 | **이웃** | 1 이상이면 1-based elem_id, 음수면 경계 조건 |
| 마지막 2개 | 미확정 | 모든 예제에서 `-1 -1`. 해석하지 말고 그대로 보존 |

**이웃 배치 규칙: `neighbors[i]` 는 정점 `i` 의 맞은편 변을 공유하는 요소다.**
(source.str 의 이웃 참조 7686개 전부에서 위반 0건, 비대칭 링크 0건으로 확인.
"변 `(v[i], v[i+1])`" 가설은 7686개 전부에서 실패했다.)

디코딩 규칙: `값 >= 1` → 요소 인덱스 `값-1` / `값 <= 0` → 경계 sentinel.

### 경계 조건 sentinel

`ChosenBC()` 가 `"/reflect"`, `"/backside"`, `"/exposed"` 문자열 테이블에서 i번째
일치 항목에 대해 `-1024 + i` 를 반환한다.

```
-1024 = reflect    (반사 경계. alloc_tri 의 "이웃 없음" 초기값이기도 함)
-1023 = backside   (웨이퍼 뒷면)
-1022 = exposed    (노출 표면 / ambient)
-1025 = undefined  (매칭 실패. 예제 파일에는 등장하지 않음)
```

기하로도 정확히 맞아떨어진다. substrate.str(4µm × 3µm 사각형)에서
`-1024` 는 x=0 과 x=4 의 양 옆면 합계 **6.0000µm**, `-1023` 은 y=3.0 바닥
**4.0000µm**, `-1022` 는 y=0.0 표면 **4.0000µm**.

### `c` 라인의 마지막 `0` 은 데이터가 아니다

`ig2_write` 가 `fwrite("  0\n", 1, 4, fp)` 로 찍는 **하드코딩된 리터럴**이다
(0x42ea1d). flag 로 오해하고 파싱하지 말 것. 실제 내용은 `c <id> <x> [<y>]` 뿐.

### 정정: `n` 라인 첫 필드는 노드 일련번호가 아니다

리더가 `mk_nd(필드1, 필드2)` 를 호출하고 `mk_nd` 는 1번 인자를 `nd->pt` 에 넣는다.
즉 **0-based 좌표(point) 인덱스**다. 숫자상으로는 이전 판의 "-1 오프셋" 설명과
같은 결과지만, 이렇게 이해해야 계면 점이 왜 여러 줄로 나오는지가 자연스럽다:
같은 점에 대해 인접 물질마다 레코드가 하나씩 있는 것이다.
`(point, material)` 조합은 16개 파일 전부에서 유일하다.

### ★ 계면에서는 반드시 물질을 지정해 값을 조회할 것

계면 점은 물질에 따라 값이 **다르다.** source.str 의 (x=2.0, y=0.0419063) 지점:

```
chem_boron   oxide 쪽   1.030547e+17
             silicon 쪽 2.067090e+16      ← 5배 차이
```

컨투어를 그릴 때 그리는 요소의 물질로 조회하지 않으면 계면에서 값이 튄다.
(source.str 기준 계면 점이 174개 있다.)

### 검증 결과 요약

- 이웃 참조 7686개: 맞은편 정점 규칙 위반 0, 비대칭 링크 0
- 경계 변 165개 = 음수 이웃 슬롯 165개 (두 집합이 완전히 동일)
- substrate.str 총면적 **12.000000000 µm²** = 4µm × 3µm 도메인과 정확히 일치
- 바운딩 박스 내 무작위 4000점이 **전부 정확히 삼각형 1개**에만 속함 (빈틈/중복 없음)
- 16개 파일 전 요소의 부호 면적이 양수 (정점 순서 일관)
- poly gate region: x=[1.7500, 2.2500], 면적 **0.20000 µm²** = CMOS.in 의
  0.5µm × 0.4µm 게이트와 일치
- postmini `Line` 추출값과 교차검증: y=0.4 컷에서 69/69 지점 재현, 최대 상대오차 4.9e-6

### 남은 미확정

`t` 라인 마지막 2개 필드의 **의미**는 확정하지 못했다. 확인된 것: `alloc_tri` 가
둘 다 -1 로 초기화하고, `ig2_read` 가 이 필드를 쓰는 유일한 곳이며, `ig2_write` 는
±1 보정 없이 그대로 출력한다. 다만 두 번째 필드는 죽은 값이 아니다 —
`build_edg`, `build_reg`, `geom`, `contour`, `fill_grid`, `do_1d`, `draw_vornoi`,
`DetectLoop` 이 모두 -1 인지 아닌지를 플래그로 검사한다. **렌더링 목적으로는 둘 다
무시하고 다시 쓸 때 `-1 -1` 로 되돌리면 된다.**

또한 2D 검증 표본이 mosfet 계열(공정 15단계) + 1D exam1 에 한정된다. gaas 계열은
미확인.

### 검증 방법론 요약 (다음 예제에도 재사용)

새 예제(`.in`) 결과를 파싱할 때마다:
1. `chmod +x postmini` (최초 1회) → `Read` → `SUPREM4` → 대상 `.str` 파일명
2. `Line` → 메뉴에 뜨는 quantity 이름/개수 확인 (도펀트 구성에 따라 달라짐)
3. 각 quantity를 같은 cut 좌표(`V`/`H`, 좌표값)로 하나씩 export
4. raw `n` 라인의 해당 좌표 값과 컬럼별로 byte-exact 대조해서 순서 확정
5. 결과를 이 문서에 추가 (도펀트 조합별로 컬럼 순서가 다를 수 있으므로 절대
   일반화해서 하드코딩하지 말 것 — 매번 `s` 라인 species 개수와 `Line` 메뉴
   개수가 일치하는지부터 확인)

## ★ `s` 라인 species 코드 사전 (컬럼 매핑의 정답)

**컬럼 순서는 파일마다 다르다. 위치로 추측하지 말고 반드시 `s` 라인의 코드로 매핑할 것.**

`s <개수> <코드1> <코드2> ...` 형식이며, **코드의 나열 순서가 곧 `n` 라인 값의 순서**다.
3개 파일을 교차 대조해 아래 사전을 확정했다:

| 코드 | quantity | 비고 |
|---|---|---|
| 0 | Vacancies | |
| 1 | Interstitials | |
| 2 | Chem. Arsenic | |
| 3 | Chem. Phosphorus | |
| 4 | Chem. Antimony | |
| 5 | Chem. Boron | |
| 8 | X velocity | 2D 전용 |
| 9 | Y velocity | 2D 전용 |
| 12 | Interstitial Traps | |
| 14 | Potential | |
| 19 | Delta Interface Area | 2D 전용 |
| 20 | Active Arsenic | |
| 21 | Active Phosphorus | |
| 22 | Active Antimony | |
| 23 | Active Boron | |
| 24 | Net Doping | 2D 파일에서만 등장, 값은 신뢰 불가(아래 참조) |

### 근거가 된 3개 파일

```
exam1/boron.str        s 6    5 23 0 1 12 14
                              └B┘ └공통 4종┘

mosfet/source.str      s 14   5 23 8 9 19 0 1 12 14 24 3 21 2 20
                              └B┘ └2D전용┘ └공통┘ NET └P┘ └As┘

(검증용 자작 1D)       s 10   5 23 3 21 4 22 0 1 12 14
                              └B┘ └P┘ └Sb┘ └공통 4종┘
```

세 파일에서 **같은 코드는 항상 같은 quantity**였고, **나열 순서는 파일마다 달랐다**
(mosfet은 공통 4종 뒤에 P/As가 붙지만, 자작 파일은 도펀트가 전부 앞에 옴).
따라서 위치 기반 하드코딩은 반드시 깨진다.

### 도펀트 코드 규칙

chem 코드는 `data/sup4gs.imp`의 element id와 일치하고(2=arsenic, 3=phosphorus,
4=antimony, 5=boron), **active = chem + 18** 이다. antimony(4→22)는 이 규칙으로
먼저 예측한 뒤 실제 실행으로 맞는 것을 확인했다.

미확인 도펀트(beryllium=31, carbon=45, gallium 등)도 같은 규칙이면 각각 49, 63이
되겠지만 **이건 아직 검증 안 됨**. 파서는 위 표에 없는 코드를 만나면 조용히 넘기지
말고 경고를 내도록 할 것.

### 파서가 지켜야 할 불변식

1. `s` 라인의 개수 필드 == 코드 개수 == 각 `n` 라인의 값 개수. 어긋나면 즉시 에러.
2. 컬럼 접근은 코드→인덱스 조회로만. 위치 상수 금지.
3. 표에 없는 코드는 경고 후 `unknown_<코드>` 로 보존 (버리지 말 것).
4. **Net Doping(코드 24)의 값은 쓰지 말 것.** mosfet 파일에서 실제 도핑이
   1e16 수준인데도 raw 값과 postmini 추출값이 모두 0이었다. 전기 시뮬레이션을
   돌리지 않은 순수 공정 결과에서는 채워지지 않는 것으로 보인다.
   Net = Σ(active donor) − Σ(active acceptor) 로 직접 계산할 것.
   (donor: arsenic·phosphorus·antimony / acceptor: boron — `data/modelrc`에
   `antimony donor`, `boron acceptor` 식으로 정의돼 있음)

## Material ID 매핑 (확정)

> 정정: 이 문서의 이전 판에는 "매 파일마다 `r` 라인을 파싱해서 material_id→이름
> 매핑을 만들어야 한다"고 적혀 있었으나 **틀렸다.** `r` 라인은
> `r <region_id> <material_id>` 뿐이고 물질 **이름이 들어있지 않다.**
> 변하는 것은 region_id→material_id 배정이고, material_id→이름은 고정 열거형이다.

CMOS.in 의 공정 단계별 `.str` 을 순서대로 대조해 확정했다. 각 단계에서 물질이
하나씩 추가될 때 새 id 가 정확히 그 시점에 등장한다:

| 단계 | `r` 라인 | 새로 등장한 id |
|---|---|---|
| substrate.str | `r 1 3` | **3 = silicon** |
| oxidation.str | `r 1 3`, `r 2 1` | **1 = oxide** |
| nitride.str | `r 1 3`, `r 2 1`, `r 3 2` | **2 = nitride** |
| nitride_remove.str | `r 1 3`, `r 2 1` | (nitride 제거 → region 소멸, 일관성 확인) |
| poly_gate.str | `r 1 3`, `r 2 1`, `r 3 4` | **4 = poly** |
| ild.str | `r 1 3`, `r 2 1`, `r 3 4`, `r 4 1`, `r 5 1` | (oxide 가 여러 region 으로) |

```
0 = ambient   (r 라인엔 없고 n 라인에만 등장. 노출 표면 바깥의 가스)
1 = oxide
2 = nitride
3 = silicon
4 = poly
```

**하드코딩해도 되는 것**: material_id → 이름 (위 표. 시뮬레이터 고정 열거형)
**하드코딩하면 안 되는 것**: region_id → 물질. 같은 oxide 가 파일마다 region 2, 4,
5 로 흩어지므로 반드시 `r` 라인을 읽어야 한다.

gaas 계열(exam10~17)의 material_id 는 미확인. 표에 없는 id 는 `unknown_<id>` 로
보존하고 경고를 낼 것.

### 주의: sup4gs.imp 는 완전히 다른 번호 체계

`data/sup4gs.imp` 헤더의 material id 테이블은 implant 통계 파일 전용이며
**`.str` 의 material_id 와 다르다**. 혼동해서 갖다 쓰면 안 된다:

```
sup4gs.imp material id: 3=silicon, 5=oxide, 4=polysilicon, 2=nitride, 6=aluminum, 8=gaas
                                    ^^^^^^^ .str 에서는 oxide=1, nitride=2, poly=4
sup4gs.imp element  id: 5=boron, 3=phosphorus, 2=arsenic, 4=antimony, 6=BF2, 31=beryllium, ...
                        └─ 이쪽 element id 는 .str 의 chem species 코드와 일치함 ─┘
```

## 실행 예시 (재현용)

```bash
cd TCAD/SUPREM4GS
./suprem4gs <<'EOF'
cd examples/exam1
source boron.in
quit
EOF
```

`postmini`로 quantity별 raw export해서 검증하려면:

```bash
chmod +x postmini   # 기본 권한이 -rw-r--r-- 라 실행권한 없음
./postmini
# Read -> SUPREM4 -> examples/exam1/boron.str
# Line -> 1 (Chem. Boron Concentration) -> boron.B_CHEM 생성
```
