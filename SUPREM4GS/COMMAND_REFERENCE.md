# SUPREM-IV.GS 커맨드 레퍼런스

매뉴얼(320쪽 PDF)과 `data/suprem.key` 를 합쳐 만든 목록이다.
`tools/docs/build_reference.py` 가 생성하므로 직접 고치지 말 것.

분류는 매뉴얼의 "Commands" 장(p.51)이 나눈 것을 그대로 따랐다.

## 목차

- **데이터 입출력** — 격자와 재질을 정의하고, 구조를 파일로 주고받는다.
  - [`mode`](#mode) Set the dimensionality of the simulator.
  - [`line`](#line) Specify a mesh line location.
  - [`region`](#region) Specify a mesh region.
  - [`boundary`](#boundary) Specify a surface type.
  - [`initialize`](#initialize) Setup grid, background doping levels.
  - [`profile`](#profile) Read a one dimensional doping profile.
  - [`structure`](#structure) Read/write the mesh and solution information.
- **공정 시뮬레이션** — 실제 공정 단계. 이 커맨드들이 웨이퍼를 바꾼다.
  - [`deposit`](#deposit) Deposit a layer.
  - [`etch`](#etch) Etch a layer.
  - [`implant`](#implant) Perform ion implantation.
  - [`diffuse`](#diffuse) Run a time temperature step on the wafer and calculate oxidation and diffusion of impurities.
  - [`stress`](#stress) Calculate elastic stresses.
  - [`method`](#method) Select numerical methods and models for diffusion and oxidation.
- **결과 보기** — 계산이 끝난 구조에서 값을 꺼내 그리거나 출력한다.
  - [`select`](#select) Select the plot variable for the post-processing routines.
  - [`plot.1d`](#plot1d) Plot a one dimensional cross section.
  - [`plot.2d`](#plot2d) Plot a two dimensional xy picture.
  - [`contour`](#contour) Plot contours in the selected variable on a two-dimensional plot.
  - [`print.1d`](#print1d) Print values along a one dimensional cross section.
  - [`label`](#label) Put labels on a plot.
  - [`option`](#option) option – Set options.
- **기타** — 출력·계산·대기 같은 보조 기능.
  - [`cpulog`](#cpulog) Log the cpu usage summary to a file.
  - [`echo`](#echo) A string printer and desk calculator.
  - [`printf`](#printf) A string printer and desk calculator.
  - [`pause`](#pause) Wait and execute command.
- **셸 내장** — 인터프리터가 직접 처리한다. suprem.key 에 정의되어 있지 않다.
  - [`define`](#define) Define strings for command line substitution.
  - [`undef`](#undef) Undefine previously defined macros.
  - [`set`](#set) Set various shell parameters.
  - [`unset`](#unset) Unset various shell parameters.
  - [`for`](#for) Command looping facility.
  - [`source`](#source) Execute commands from the specified file.
  - [`help`](#help) Online quick info facility.
  - [`man`](#man) Online help facility for SUPREM-IV.
- **물성 계수** — 확산·편석·클러스터링 계수를 바꾼다. 기본값은 data/modelrc 에 있고 사람이 읽을 수 있는 형식이다.
  - [`antimony`](#antimony) Set the coefficients of antimony kinetics.
  - [`arsenic`](#arsenic) Set the coefficients of arsenic kinetics.
  - [`beryllium`](#beryllium) Set the coefficients of beryllium kinetics.
  - [`boron`](#boron) Set the coefficients of boron kinetics.
  - [`carbon`](#carbon) Set the coefficients of carbon kinetics.
  - [`generic`](#generic) Set the coefficients for a generic impurity’s kinetics.
  - [`germanium`](#germanium) Set the coefficients of germanium kinetics.
  - [`interstitial`](#interstitial) Set coefficients of interstitial kinetics.
  - [`isilicon`](#isilicon) Set the coefficients of silicon impurity kinetics.
  - [`magnesium`](#magnesium) Set the coefficients of magnesium kinetics.
  - [`material`](#material) Set the coefficients of some materials.
  - [`oxide`](#oxide) Specify oxidation coefficients.
  - [`phosphorus`](#phosphorus) Set the coefficients of phosphorus kinetics.
  - [`selenium`](#selenium) Set the coefficients of selenium kinetics.
  - [`tin`](#tin) Set the coefficients of tin kinetics.
  - [`trap`](#trap) Set coefficients of interstitial traps.
  - [`vacancy`](#vacancy) Set coefficients of vacancy kinetics.
  - [`zinc`](#zinc) Set the coefficients of zinc kinetics.
- **문서 없음** — suprem.key 에는 있지만 매뉴얼에 설명이 없다. 받는 파라미터는 알 수 있어도 무엇을 하는 커맨드인지는 직접 확인해야 한다.
  - [`cesium`](#cesium) 
  - [`device`](#device) 
  - [`gold`](#gold) 

## 데이터 입출력

격자와 재질을 정의하고, 구조를 파일로 주고받는다.

### mode

Set the dimensionality of the simulator.

매뉴얼 87쪽

```
mode [ one.dim | two.dim ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `one.dim` | boolean | — | · `operation` 중 택1 |
| `two.dim` | boolean | — | · `operation` 중 택1 |
| `three.dim` | boolean | — | · `operation` 중 택1 |

### line

Specify a mesh line location.

매뉴얼 76쪽

```
line ( x | y | z ) location = <n> [spacing = <n>] [tag = <string>]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `x.direction` | boolean | f | · `direction` 중 택1 |
| `y.direction` | boolean | f | · `direction` 중 택1 |
| `z.direction` | boolean | f | · `direction` 중 택1 |
| `location` | float | 0.0 |  |
| `spacing` | float | -999.0 |  |
| `tag` | string | — | a name to call this line |

### region

Specify a mesh region.

매뉴얼 105쪽

```
region
     ( silicon | oxide | nitride | poly | gas | oxynitr | photores |
             aluminum | gaas )
     xlo = <string> ylo = <string> xhi = <string> yhi = <string>
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `xlo` | string | — | tag name |
| `xhi` | string | — | tag name |
| `ylo` | string | — | tag name |
| `yhi` | string | — | tag name |
| `silicon` | boolean | f | · `mater` 중 택1 |
| `oxide` | boolean | f | · `mater` 중 택1 |
| `oxynitride` | boolean | f | · `mater` 중 택1 |
| `nitride` | boolean | f | · `mater` 중 택1 |
| `poly` | boolean | f | · `mater` 중 택1 |
| `photoresist` | boolean | f | · `mater` 중 택1 |
| `aluminum` | boolean | f | · `mater` 중 택1 |
| `gaas` | boolean | f | · `mater` 중 택1 |

### boundary

Specify a surface type.

매뉴얼 48쪽

```
boundary
    ( reflecting | exposed | backside )
    xlo = <string> ylo = <string>
    xhi = <string> yhi = <string>
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `xlo` | string | — | tag name |
| `xhi` | string | — | tag name |
| `ylo` | string | — | tag name |
| `yhi` | string | — | tag name |
| `reflecting` | boolean | f | · `type` 중 택1 |
| `exposed` | boolean | f | · `type` 중 택1 |
| `backside` | boolean | f | · `type` 중 택1 |
| `code` | integer | -999 |  |

### initialize

Setup grid, background doping levels.

매뉴얼 71쪽

```
initialize
       [ infile=<string> ]
       [ ( antimony | arsenic | boron | phosphorus | gold |
               gallium | beryllium | magnesium | selenium |
               isilicon | tin | germanium | zinc | carbon | generic ) ]
       [ conc=<n> ]
       [ orientation=<n> ]
       [ line.data ] [ scale ] [ flip.y ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `infile` | string | — | structure file for read |
| `conc` | float | — | background concentration |
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `gold` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `orient` | integer | 100 | Substrate crystal orientation, default 100 |
| `p.ori` | integer | 110 | Orientation of mask edges. Don't change this. |
| `line.data` | boolean | f | list locations of mesh lines? |
| `interval.r` | float | 1.5 | maximum interval ratio |
| `scale` | float | 1.0 | scale factor for incoming meshes |
| `flip.y` | boolean | false | invert the mesh |

### profile

Read a one dimensional doping profile.

매뉴얼 103쪽

```
profile
      infile=<string>
      ( antimony | arsenic | boron | phosphorus | gallium |
             interstitial | vacancy | beryllium | carbon |
             germanium | selenium | isilicon | tin |
             magnesium | zinc | generic )
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `interstitia` (문서상 `interstitial`) | boolean | — | · `impurity` 중 택1 |
| `vacancy` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `infile` | string | — |  |
| `offset` | float | — | the amount of displacement added to the data |

### structure

Read/write the mesh and solution information.

매뉴얼 113쪽

```
structure
      [ (infile=<string> | outfile=<string>) ]
      [ pisces=<string> ] [ show ] [ backside.y=<n> ]
      [ mirror ] [ left ] [ right ]
      [ imagetool=<string> ]
              [ x.min=<n> | x.max=<n> | y.min=<n> | y.max=<n> |
              z.min=<n> | z.max=<n> | pixelx=<n> | pixely=<n> |
              nxfac=<n> | nyfac=<n> | mode=<n> ]
      [ simpl=<string> ] [ header=<string> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `infile` | string | — | filename of old mesh |
| `outfile` | string | — | filename for storage |
| `pisces` | string | — | filename for pisces output |
| `show` | boolean | f | plot the electrodes |
| `backside.y` | float | 0.0 | y-location of backside contact |
| `scale` | float | 1.0 |  |
| `flip.y` | boolean | false | invert the mesh |
| `mirror` | boolean | f | reflect the grid about an edge |
| `right` | boolean | — | · `rlswitch` 중 택1 |
| `left` | boolean | — | · `rlswitch` 중 택1 |
| `top` | boolean | — | · `tbswitch` 중 택1 |
| `bottom` | boolean | — | · `tbswitch` 중 택1 |
| `region` | integer | -1 |  |
| `reflect` | boolean | — | · `mat` 중 택1 |
| `backside` ⚠사용 불가 | boolean | — | · `mat` 중 택1 |
| `exposed` | boolean | — | · `mat` 중 택1 |
| `oxide` | boolean | — | · `mat` 중 택1 |
| `nitride` | boolean | — | · `mat` 중 택1 |
| `silicon` | boolean | — | · `mat` 중 택1 |
| `poly` | boolean | — | · `mat` 중 택1 |
| `oxynitride` | boolean | — | · `mat` 중 택1 |
| `aluminum` | boolean | — | · `mat` 중 택1 |
| `photoresist` | boolean | — | · `mat` 중 택1 |
| `imagetool` | string | — | filename for Imagetool output |
| `x.min` | float | -10000.0 | minimum x value for plots |
| `x.max` | float | 10000.0 | maximum x value for plots |
| `y.min` | float | -10000.0 | minimum y value for plots |
| `y.max` | float | 10000.0 | maximum y value for plots |
| `z.min` | float | -10000.0 | minimum z value for plotx |
| `z.max` | float | 10000.0 | maximum z value for plots |
| `pixelx` | integer | 400 | number of pixels in x-direction |
| `pixely` | integer | 200 | number of pixels in y-direction |
| `nxfac` | integer | 1 | interpolation factor in x-direction |
| `nyfac` | integer | 1 | interpolation factor in y-direction |
| `mode` | integer | 0 | special z-axis scaling mode |
| `mac` | boolean | f | output for a Macintosh-II |
| `clear` | boolean | f | clear counter |
| `count` | boolean | f | increment counter |
| `simpl` | string | — | filename for SIMPL-2 output |
| `header` | string | — | header file for SIMPL-2 |

## 공정 시뮬레이션

실제 공정 단계. 이 커맨드들이 웨이퍼를 바꾼다.

### deposit

Deposit a layer.

매뉴얼 54쪽

```
deposit
     ( silicon | oxide | oxynitr | nitride | poly | photores |
            alumin | gaas )
     thickness = <n> [ divisions = <n> ]
     [ none | arsenic | antimony | boron | phosphor |
            beryllium | magnesium | selenium | isilicon |
            tin | germanium | zinc | carbon | generic]
     [ conc=<n> ] [ space=<n> ]
     [ file=<string> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `photoresist` | boolean | — | · `material` 중 택1 |
| `aluminum` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `none` | boolean | — | · `impurity` 중 택1 |
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `concentrati` (문서상 `concentration`) | float | 1.0e10 | concentration of doping |
| `thick` | float | -999.0 | thickness of the new layer |
| `divisions` | integer | 1 | number of grid lines in this material |
| `space` | float | — | space between grid on outer edge of new material |
| `square` | boolean | — |  |
| `temperature` | float | 0.0 | temperature of deposition |
| `pressure` | float | 0.0 | pressure of deposition |
| `time` | float | 0.0 | time of deposition |
| `file` | string | — | filename of string to deposit |

### etch

Etch a layer.

매뉴얼 64쪽

```
etch
       [ silicon | oxide | oxynitr | nitride | poly | photores |
               alumin | gaas ]
       [ left | right | start | continue | done | dry | all ]
       [ x=<n> ] [ y=<n> ] [ thick=<n> ]
       [ p1.x=<n> ] [ p1.y=<n> ] [ p2.x=<n> ] [ p2.y=<n> ]
       [ file=<string> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `photoresist` | boolean | — | · `material` 중 택1 |
| `aluminum` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `spacing` | float | -999.0 |  |
| `left` | boolean | — | etch left of the p1,p2 line · `type_etch` 중 택1 |
| `right` | boolean | — | etch right of the p1,p2 line · `type_etch` 중 택1 |
| `start` | boolean | — | first of a series of coordinates · `type_etch` 중 택1 |
| `continue` | boolean | — | one of many of a series of coordinates · `type_etch` 중 택1 |
| `done` | boolean | — | last of a series of coordinates · `type_etch` 중 택1 |
| `dry` | boolean | — | straight down form the top · `type_etch` 중 택1 |
| `thick` | float | — | how far down from top · `type_etch` 중 택1 |
| `physical` | boolean | — | give a rate constant and time · `type_etch` 중 택1 |
| `r.silicon` | float | 0.0 | etch rate for silicon · `type_etch` 중 택1 |
| `r.oxide` | float | 0.0 | etch rate for oxide · `type_etch` 중 택1 |
| `r.oxynitrid` (문서상 `r.oxynitride`) | float | 0.0 | etch rate for oxynitride · `type_etch` 중 택1 |
| `r.nitride` | float | 0.0 | etch rate for nitride · `type_etch` 중 택1 |
| `r.poly` | float | 0.0 | etch rate for polysilicon · `type_etch` 중 택1 |
| `r.photoresi` (문서상 `r.photoresist`) | float | 0.0 | etch rate for photoresist · `type_etch` 중 택1 |
| `r.aluminum` | float | 0.0 | etch rate for aluminum · `type_etch` 중 택1 |
| `time` | float | — | etch time · `type_etch` 중 택1 |
| `all` | boolean | — | etch an entire material · `type_etch` 중 택1 |
| `x` | float | — | x value of a set of coords |
| `y` | float | — | y value of a set of coords |
| `p1.x` | float | 0 | x value in half a line |
| `p1.y` | float | 0 | y value in half a line |
| `p2.x` | float | 0 | x value in half a line |
| `p2.y` | float | 0 | y value in half a line |
| `file` | string | — | filename of string to etch |

### implant

Perform ion implantation.

매뉴얼 67쪽

```
implant
     ( antimony | arsenic | boron | bf2 | cesium | phosphorus |
           beryllium | magnesium | selenium | isilicon | tin |
           germanium | zinc | carbon | generic )
     [ gauss | pearson ]
     dose=<n> energy=<n>
     [ damage ] [ max.damage=<n> ]
     [ range=<n> ] [ std.dev=<n> ]
     [ gamma=<n> ] [ kurtosis=<n> ]
     [ angle=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dose` | float | — | per centimeter squared |
| `energy` | float | — | Kev |
| `silicon` | boolean | — | · `impurity` 중 택1 |
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `bf2` | boolean | — | · `impurity` 중 택1 |
| `cesium` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `damage` | boolean | false | Calculate damage profiles |
| `max.damage` | float | 1.0e22 | Maximum damage |
| `gauss` | boolean | — | · `model` 중 택1 |
| `pearson` | boolean | — | · `model` 중 택1 |
| `range` | float | — | Projected range in microns |
| `std.dev` | float | — | Standard Deviation |
| `gamma` | float | — |  |
| `kurtosis` | float | — |  |
| `angle` | float | 0.0 | Angle from vertical |

### diffuse

Run a time temperature step on the wafer and calculate oxidation and diffusion of impurities.

매뉴얼 57쪽

```
diffuse
      time=<n> temperature=<n>
      [ ( dryo2 | weto2 | nitrogen | ammonia | argon |
             antimony | arsenic | boron | phosphorus |
             beryllium | magnesium | selenium | isilicon |
             tin | germanium | zinc | carbon | generic ) ]
      [ gas.conc=<n> ] [ pressure=<n> ]
      [ gold.surf ] [ continue ]
      [ movie=<string> ] [ dump=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `temp` | float | — | degrees Kelvin |
| `time` | float | — | minutes |
| `ramp` | boolean | — |  |
| `start` | float | — | start temperature |
| `stop` | float | — | stop temperature |
| `dryo2` | boolean | false | · `ambient` 중 택1 |
| `weto2` | boolean | false | · `ambient` 중 택1 |
| `nitrogen` | boolean | false | · `ambient` 중 택1 |
| `ammonia` | boolean | false | · `ambient` 중 택1 |
| `argon` | boolean | false | · `ambient` 중 택1 |
| `antimony` | boolean | — | · `ambient` 중 택1 |
| `arsenic` | boolean | — | · `ambient` 중 택1 |
| `boron` | boolean | — | · `ambient` 중 택1 |
| `gallium` | boolean | — | · `ambient` 중 택1 |
| `phosphorus` | boolean | — | · `ambient` 중 택1 |
| `beryllium` | boolean | — | · `ambient` 중 택1 |
| `magnesium` | boolean | — | · `ambient` 중 택1 |
| `selenium` | boolean | — | · `ambient` 중 택1 |
| `isilicon` | boolean | — | · `ambient` 중 택1 |
| `tin` | boolean | — | · `ambient` 중 택1 |
| `germanium` | boolean | — | · `ambient` 중 택1 |
| `zinc` | boolean | — | · `ambient` 중 택1 |
| `carbon` | boolean | — | · `ambient` 중 택1 |
| `generic` | boolean | — | · `ambient` 중 택1 |
| `pressure` | float | 1.0 | partial pressure of active gas species (atm) |
| `solid.sol` | boolean | false |  |
| `gas.conc` | float | 1e13 | gas concentration for predep |
| `continue` | boolean | — |  |
| `dump` | integer | — | save structure every dump time steps |
| `gold.surf` | float | — |  |
| `movie` | string | — | string to be executed at all time steps |

### stress

Calculate elastic stresses.

매뉴얼 111쪽

```
stress [ temp1=<n> temp2=<n> ] [ nel=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `temp1` | float | — | Degrees Celsius |
| `temp2` | float | — | Degrees Celsius |
| `nel` | integer | — | nodes/element (6 or 7) |
| `ubc3` | string | — |  |
| `ubc4` | string | — |  |
| `ubc5` | string | — |  |
| `ubc6` | string | — |  |
| `ubc7` | string | — |  |
| `ubc8` | string | — |  |
| `ubc9` | string | — |  |
| `vbc3` | string | — |  |
| `vbc4` | string | — |  |
| `vbc5` | string | — |  |
| `vbc6` | string | — |  |
| `vbc7` | string | — |  |
| `vbc8` | string | — |  |
| `vbc9` | string | — |  |

### method

Select numerical methods and models for diffusion and oxidation.

매뉴얼 79쪽

```
method
     [ ( vacancies | interstitial | arsenic | phosphorus |
             antimony | boron | gallium | oxidant | velocity |
             traps | gold | psi | cesium | beryllium | magnesium |
             selenium | isilicon | tin | germanium | zinc | carbon |
             generic ) ]
     [ rel.error=<n> ] [ abs.error=<n> ]
     [ init.time=<n> ] [ ( trbdf | formula ) ]
     [ min.fill ] [ min.freq=<n> ]
     [ ( gauss | cg ) ] [ back=<n> ] [ blk.itlim=<n> ]
     [ ( time | error | newton ) ]
     [ ( diag | full.fac ) ]
     [ ( fermi | two.dim | steady | full.cpl ) ]
     [ ( erfc | erfg | erf1 | erf2 | vertical | compress | viscous ) ]
     [ grid.oxide=<n> ] [ skip.sil ]
     [ oxide.gdt=<n> ] [ redo.oxide=<n> ]
     [ oxide.early=<n> ] [ oxide.late=<n> ] [ oxide.rel=<n> ]
     [ gloop.emin=<n> ] [ gloop.emax=<n> ] [ gloop.imin=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `vacancies` | boolean | — | · `impurity` 중 택1 |
| `interstitia` (문서상 `interstitial`) | boolean | — | · `impurity` 중 택1 |
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `oxidant` | boolean | — | · `impurity` 중 택1 |
| `velocity` | boolean | — | · `impurity` 중 택1 |
| `traps` | boolean | — | · `impurity` 중 택1 |
| `gold` | boolean | — | · `impurity` 중 택1 |
| `psi` | boolean | — | · `impurity` 중 택1 |
| `cesium` | boolean | — | · `impurity` 중 택1 |
| `electron` | boolean | — | · `impurity` 중 택1 |
| `holes` | boolean | — | · `impurity` 중 택1 |
| `circuit` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `min.fill` | boolean | true | minimum degree reorder |
| `min.freq` | float | 1.25 | relative increase in l length before redoing |
| `gauss` | boolean | — | · `blkmeth` 중 택1 |
| `cg` | boolean | — | · `blkmeth` 중 택1 |
| `back` | integer | 1 | number of back vectors |
| `init.time` | float | 0.1 | seconds |
| `time` | boolean | — | when the time step dictates it · `factor` 중 택1 |
| `err` | boolean | — | when the error reduction indicates · `factor` 중 택1 |
| `newton` | boolean | — | every newton iteration · `factor` 중 택1 |
| `diag` | boolean | — | diagonal blocks · `precondition` 중 택1 |
| `knot` | boolean | — | knot blocks - not available · `precondition` 중 택1 |
| `full.fac` | boolean | — | full LU decomposition of everything · `precondition` 중 택1 |
| `trbdf` | boolean | — |  |
| `formula` | string | — | a formula giving dt as f(t) |
| `fermi` | boolean | — | defects are a function of fermi level only · `defectm` 중 택1 |
| `two.dim` | boolean | — | full 2D numerical solution · `defectm` 중 택1 |
| `steady` | boolean | — | full 2d steady state solution · `defectm` 중 택1 |
| `full.cpl` | boolean | — | full 2d with completer defect dopant pairing · `defectm` 중 택1 |
| `erfc` | boolean | — | · `oxidem` 중 택1 |
| `erf1` | boolean | — | · `oxidem` 중 택1 |
| `erf2` | boolean | — | · `oxidem` 중 택1 |
| `erfg` | boolean | — | · `oxidem` 중 택1 |
| `vertical` | boolean | — | · `oxidem` 중 택1 |
| `compress` | boolean | — | · `oxidem` 중 택1 |
| `viscous` | boolean | — | · `oxidem` 중 택1 |
| `grid.oxide` | float | 0.1 | oxide spacing to use in the field region, in microns |
| `redo.oxide` | float | 10 | percent change concentration before redoing flow |
| `oxide.gdt` | float | 0.25 | maximum time step relative to grid change |
| `oxide.rel` | float | 1.0e-6 | relative error bound for velocities |
| `oxide.early` | float | 0.5 | earliest node can be removed |
| `oxide.late` | float | 0.9 | latest node can be removed |
| `ox.obfix` | float | 2 | cos-squared of worst angle before hacking |
| `gloop.imax` | float | 170 | worst intrusion angle, degrees |
| `gloop.emin` | float | 130 | tolerable extrusion angle, degrees |
| `gloop.emax` | float | 170 | worst extrusion angle, degrees |
| `grid.grain` | float | 0.1 | oxide spacing to use in the field region, in microns |
| `grain.gdt` | float | 0.25 | maximum time step relative to grid change |
| `norm.style` | integer | 0 | 0=true normal / 1=boosted normal |
| `verbose` | boolean | true |  |
| `rel.error` | float | 1.0e-3 | relative error bound |
| `abs.error` | float | 1.0e10 | absolute error bound |
| `skip.sil` | boolean | t |  |
| `blk.itlim` | integer | 10 | Max iterations on blocks |

## 결과 보기

계산이 끝난 구조에서 값을 꺼내 그리거나 출력한다.

### select

Select the plot variable for the post-processing routines.

매뉴얼 107쪽

```
select
      [ z=<expr> ] [ label=<string> ] [ title=<string> ] [ temp=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `z` | string | — | vector expression |
| `title` | string | — | plot title |
| `label` | string | — | z axis label |
| `temp` | float | — | degrees Kelvin |

### plot.1d

Plot a one dimensional cross section.

매뉴얼 90쪽

```
plot.1d
      [ (x.value=<n> | y.value=<n>) ]
      [ exposed | backside | reflect | silicon | oxide |
             nitride | poly | oxynitride | aluminum |
             photoresist | gaas | gas ]
      [ /exposed | /backside | /reflect | /silicon | /oxide |
             /nitride | /poly | /oxynitride | /aluminum |
             /photoresist | /gaas | /gas ]
      [ boundary ] [ axis ] [ clear ]
      [ symb=<n> ]
      [ x.max=<n> ] [ x.min=<n> ] [ y.max=<n> ] [ y.min=<n> ]
      [ arclength ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `boundary` | boolean | — | draw material boundaries that are crossed |
| `clear` | boolean | true | clear the plot |
| `axis` | boolean | true | draw axes |
| `symb` | integer | — | place symbols on the data line |
| `line.type` | integer | 1 |  |
| `x.value` | float | — | draw a vertical line at this x · `direction` 중 택1 |
| `y.value` | float | — | draw a horizontal line at this y · `direction` 중 택1 |
| `x.min` | float | — | minimum value on the horizontal plot axis |
| `x.max` | float | — | maximum value on the horizontal plot axis |
| `y.min` | float | — | minimum value on the vertical plot axis |
| `y.max` | float | — | minimum value on the vertical plot axis |
| `notselected` | boolean | — | · `mat1` 중 택1 |
| `reflect` | boolean | — | · `mat1` 중 택1 |
| `backside` | boolean | — | · `mat1` 중 택1 |
| `exposed` | boolean | — | · `mat1` 중 택1 |
| `gas` | boolean | — | · `mat1` 중 택1 |
| `oxide` | boolean | — | · `mat1` 중 택1 |
| `nitride` | boolean | — | · `mat1` 중 택1 |
| `silicon` | boolean | — | · `mat1` 중 택1 |
| `poly` | boolean | — | · `mat1` 중 택1 |
| `oxynitride` | boolean | — | · `mat1` 중 택1 |
| `aluminum` | boolean | — | · `mat1` 중 택1 |
| `photoresist` | boolean | — | · `mat1` 중 택1 |
| `gaas` | boolean | — | · `mat1` 중 택1 |
| `/notselecte` (문서상 `/notselected`) | boolean | — | · `mat2` 중 택1 |
| `/reflect` | boolean | — | · `mat2` 중 택1 |
| `/backside` | boolean | — | · `mat2` 중 택1 |
| `/exposed` | boolean | — | · `mat2` 중 택1 |
| `/gas` | boolean | — | · `mat2` 중 택1 |
| `/oxide` | boolean | — | · `mat2` 중 택1 |
| `/nitride` | boolean | — | · `mat2` 중 택1 |
| `/silicon` | boolean | — | · `mat2` 중 택1 |
| `/poly` | boolean | — | · `mat2` 중 택1 |
| `/oxynitride` | boolean | — | · `mat2` 중 택1 |
| `/aluminum` | boolean | — | · `mat2` 중 택1 |
| `/photoresis` (문서상 `/photoresist`) | boolean | — | · `mat2` 중 택1 |
| `/gaas` | boolean | — | · `mat2` 중 택1 |
| `/code` | integer | — | boundaries that are none of the above |
| `arclength` | boolean | f | use arclength for interface x coordinate |

### plot.2d

Plot a two dimensional xy picture.

매뉴얼 94쪽

```
plot.2d
      [ x.max=<n> ] [ x.min=<n> ] [ y.min=<n> ] [ y.max=<n> ]
      [ clear ] [ fill ] [ boundary ] [ grid ] [ axis ]
      [ vornoi ] [ diamonds ]
      [ stress ] [ vmax=<n> ] [ vleng=<n> ]
      [ flow ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `x.min` | float | -1000.0 | minimum x value for plots |
| `x.max` | float | 1000.0 | maximum x value for plots |
| `y.min` | float | -1000.0 | minimum y value for plots |
| `y.max` | float | 1000.0 | maximum y value for plots |
| `normal` | boolean | — | · `newwin` 중 택1 |
| `zoom.in` | boolean | — | · `newwin` 중 택1 |
| `zoom.out` | boolean | — | · `newwin` 중 택1 |
| `pan` | boolean | — | · `newwin` 중 택1 |
| `line.grid` | integer | 1 | line type for grid lines |
| `line.bound` | integer | 2 | line type for boundary lines |
| `vornoi` | boolean | false | plot vornoi triangles |
| `diamonds` | boolean | false | plot diamonds |
| `stress` | boolean | false |  |
| `flow` | boolean | false |  |
| `vmax` | float | 0 |  |
| `vleng` | float | 0 |  |
| `line.com` | integer | 3 |  |
| `line.ten` | integer | 4 |  |
| `boundary` | boolean | — | material boundary |
| `grid` | boolean | — | draw the grid |
| `clear` | boolean | true | clear the screen |
| `axis` | boolean | true | draw an axis |
| `fill` | boolean | false | fill the screen with plot |

### contour

Plot contours in the selected variable on a two-dimensional plot.

매뉴얼 50쪽

```
contour
     [ line.type=<n> ] [ value=<n> ] [ symb=<n> ]
     [ print ] [ label ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `line.type` | integer | 1 | line type to draw in |
| `value` | float | — | value of isoconcentration line |
| `symb` | integer | — | symbol to put on line (0 == no symbol) |
| `print` | boolean | — |  |
| `label` | boolean | — |  |

### print.1d

Print values along a one dimensional cross section.

매뉴얼 98쪽

```
print.1d
      [ ( x.value=<n> | y.value=<n> ) ]
      [ silicon | oxide | nitride … ]
      [ /exposed | /backside | /reflect | /silicon | /oxide |
              /nitride … ]
      [ arclength ] [ layers ] [ x.min=<n> ] [ x.max=<n> ]
      [ format=<string> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `x.value` | float | — | draw a vertical line at this x · `direction` 중 택1 |
| `y.value` | float | — | draw a horizontal line at this y · `direction` 중 택1 |
| `layers` | boolean | — | integrate data and compile region thicknesses |
| `x.min` | float | — | minimum value on the horizontal plot axis |
| `x.max` | float | — | minimum value on the horizontal plot axis |
| `reflect` | boolean | — | · `mat1` 중 택1 |
| `backside` | boolean | — | · `mat1` 중 택1 |
| `exposed` | boolean | — | · `mat1` 중 택1 |
| `oxide` | boolean | — | · `mat1` 중 택1 |
| `nitride` | boolean | — | · `mat1` 중 택1 |
| `silicon` | boolean | — | · `mat1` 중 택1 |
| `poly` | boolean | — | · `mat1` 중 택1 |
| `oxynitride` | boolean | — | · `mat1` 중 택1 |
| `aluminum` | boolean | — | · `mat1` 중 택1 |
| `photoresist` | boolean | — | · `mat1` 중 택1 |
| `/reflect` | boolean | — | · `mat2` 중 택1 |
| `/backside` | boolean | — | · `mat2` 중 택1 |
| `/exposed` | boolean | — | · `mat2` 중 택1 |
| `/oxide` | boolean | — | · `mat2` 중 택1 |
| `/nitride` | boolean | — | · `mat2` 중 택1 |
| `/silicon` | boolean | — | · `mat2` 중 택1 |
| `/poly` | boolean | — | · `mat2` 중 택1 |
| `/oxynitride` | boolean | — | · `mat2` 중 택1 |
| `/aluminum` | boolean | — | · `mat2` 중 택1 |
| `/photoresis` (문서상 `/photoresist`) | boolean | — | · `mat2` 중 택1 |
| `format` | string | — | format for data values, default %-16e |
| `arclength` | boolean | f | use arclength for interface x coordinate |

### label

Put labels on a plot.

매뉴얼 74쪽

```
label
        [ x=<n> y=<n> ] [ label=<string> ] [ symb=<n> ]
        [ line.type=<n> ]
```

### option

option – Set options.

매뉴얼 88쪽

```
option [ quiet | normal | chat | barf ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `terminal` | string | — | terminal type |
| `plot.file` | string | — | where output is to go if not the terminal |
| `file.save` | string | — | file to copy plot to |
| `stop.save` | boolean | — | quit saving and close save file |
| `on.save` | boolean | — | restart saving after a pause |
| `off.save` | boolean | — | turn off saving for a while |
| `quiet` | boolean | — | · `verbose` 중 택1 |
| `normal` | boolean | — | · `verbose` 중 택1 |
| `chat` | boolean | — | · `verbose` 중 택1 |
| `barf` | boolean | — | · `verbose` 중 택1 |

## 기타

출력·계산·대기 같은 보조 기능.

### cpulog

Log the cpu usage summary to a file.

매뉴얼 52쪽

```
cpu [ log ] [ cpufile=<string> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `log` | boolean | true | cpu usage logging on/off |
| `cpufile` | string | — | file for cpu data |

### echo

A string printer and desk calculator.

매뉴얼 62쪽

```
echo [ string ]
```

### printf

A string printer and desk calculator.

매뉴얼 101쪽

```
print [ string ]
```

### pause

Wait and execute command.

매뉴얼 89쪽

```
pause
```

## 셸 내장

인터프리터가 직접 처리한다. suprem.key 에 정의되어 있지 않다.

### define

Define strings for command line substitution.

매뉴얼 29쪽

```
define [ macro_name macro_body ]
```

### undef

Undefine previously defined macros.

매뉴얼 39쪽

```
undef [ macro_name ]
```

### set

Set various shell parameters.

매뉴얼 36쪽

```
set [ ( echo | noexecute | prompt string ) ]
```

### unset

Unset various shell parameters.

매뉴얼 40쪽

```
unset [ ( echo | noexecute ) ]
```

### for

Command looping facility.

매뉴얼 31쪽

```
[ foreach | for ] name ( list )
      commands
end
```

### source

Execute commands from the specified file.

매뉴얼 38쪽

```
source filename
```

### help

Online quick info facility.

매뉴얼 33쪽

```
help [ command_name ]
```

### man

Online help facility for SUPREM-IV.

매뉴얼 34쪽

```
man [ command_name ]
```

## 물성 계수

확산·편석·클러스터링 계수를 바꾼다. 기본값은 data/modelrc 에 있고 사람이 읽을 수 있는 형식이다.

### antimony

Set the coefficients of antimony kinetics.

매뉴얼 121쪽

```
antimony
     ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
     [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dim.0=<n> ] [ Dim.E=<n> ]
     [ Fi = <n> ]
     [ implanted ] [ grown.in ]
     [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
     [ ( /silicon | /oxide | /oxynitr | /nitride | /gas |
             /poly | /gaas ) ]
     [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
     [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.214 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 3.65 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 15.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 4.08 | Activation energy for V- diffusivity - eV |
| `Fi` | float | 0.05 | Fractional Interstitialcy component |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### arsenic

Set the coefficients of arsenic kinetics.

매뉴얼 126쪽

```
arsenic
     ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
     [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dim.0=<n> ] [ Dim.E=<n> ]
     [ Fi = <n> ]
     [ implanted ] [ grown.in ]
     [ Ctn.0=<n> ] [ Ctn.E=<n> ]
     [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
     [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
             /gaas ) ]
     [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
     [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.214 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 3.65 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 15.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 4.08 | Activation energy for V- diffusivity - eV |
| `Fi` | float | 0.05 | Fractional Interstitialcy component |
| `Ctn.0` | float | -102.205 | log of pre exponential clustering coeff |
| `Ctn.E` | float | 0.33 | Activation energy of clustering |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### beryllium

Set the coefficients of beryllium kinetics.

매뉴얼 132쪽

```
beryllium
        ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
        [ Dix.0=<n> ] [ Dix.E=<n> ]
        [ Dip.0=<n> ] [ Dip.E=<n> ] [ Dipp.0=<n> ] [ Dipp.E=<n> ]
        [ Fi = <n> ]
        [ implanted ] [ grown.in ]
        [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
        [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
                /gaas ) ]
        [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
        [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dip.0` | float | 0.0 | Pre-exponential constant for V+ cm2/sec |
| `Dip.E` | float | 0.0 | Activation energy for V+ diffusivity - eV |
| `Dipp.0` | float | 0.0 | Pre-exponential constant for V++ cm2/sec |
| `Dipp.E` | float | 0.0 | Activation energy for V++ diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### boron

Set the coefficients of boron kinetics.

매뉴얼 138쪽

```
boron
       ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
       [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dip.0=<n> ] [ Dip.E=<n> ]
       [ Fi = <n> ]
       [ implanted ] [ grown.in ]
       [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
       [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
               /gaas ) ]
       [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
       [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.037 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 3.46 | Activation energy for Vo diffusivity - eV |
| `Dip.0` | float | 0.72 | Pre-exponential constant for V+ cm2/sec |
| `Dip.E` | float | 3.46 | Activation energy for V+ diffusivity - eV |
| `Fi` | float | 0.9 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### carbon

Set the coefficients of carbon kinetics.

매뉴얼 144쪽

```
carbon
       ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
       [ Dix.0=<n> ] [ Dix.E=<n> ]
       [ Dip.0=<n> ] [ Dip.E=<n> ] [ Dipp.0=<n> ] [ Dipp.E=<n> ]
       [ Fi = <n> ]
       [ implanted ] [ grown.in ]
       [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
       [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
               /gaas ) ]
       [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
       [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dip.0` | float | 0.0 | Pre-exponential constant for V+ cm2/sec |
| `Dip.E` | float | 0.0 | Activation energy for V+ diffusivity - eV |
| `Dipp.0` | float | 0.0 | Pre-exponential constant for V++ cm2/sec |
| `Dipp.E` | float | 0.0 | Activation energy for V++ diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### generic

Set the coefficients for a generic impurity’s kinetics.

매뉴얼 149쪽

```
generic
     ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
     [ Dix.0=<n> ] [ Dix.E=<n> ]
     [ Dim.0=<n> ] [ Dim.E=<n> ]
     [ Dimm.0=<n> ] [ Dimm.E=<n> ]
     [ Dimmm.0=<n> ] [ Dimmm.E=<n> ]
     [ Dip.0=<n> ] [ Dip.E=<n> ]
     [ Dipp.0=<n> ] [ Dipp.E=<n> ]
     [ Dippp.0=<n> ] [ Dippp.E=<n> ]
     [ Fi = <n> ]
     [ implanted ] [ grown.in ]
     [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
     [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly | gaas ) ]
     [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
     [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dip.0` | float | 0.0 | Pre-exponential constant for V+ cm2/sec |
| `Dip.E` | float | 0.0 | Activation energy for V+ diffusivity - eV |
| `Dipp.0` | float | 0.0 | Pre-exponential constant for V++ cm2/sec |
| `Dipp.E` | float | 0.0 | Activation energy for V++ diffusivity - eV |
| `Dippp.0` | float | 0.0 | Pre-exponential constant for V+++ cm2/sec |
| `Dippp.E` | float | 0.0 | Activation energy for V+++ diffusivity - eV |
| `Dim.0` | float | 0.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 0.0 | Activation energy for V- diffusivity - eV |
| `Dimm.0` | float | 0.0 | Pre-exponential constant for V-- cm2/sec |
| `Dimm.E` | float | 0.0 | Activation energy for V-- diffusivity - eV |
| `Dimmm.0` | float | 0.0 | Pre-exponential constant for V--- cm2/sec |
| `Dimmm.E` | float | 0.0 | Activation energy for V--- diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### germanium

Set the coefficients of germanium kinetics.

매뉴얼 155쪽

```
germanium
      ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
      [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dim.0=<n> ] [ Dim.E=<n> ]
      [ Dimm.0=<n> ] [ Dimm.E=<n> ] [ Fi = <n> ]
      [ implanted ] [ grown.in ]
      [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
      [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
              /gaas ) ]
      [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
      [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 0.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 0.0 | Activation energy for V- diffusivity - eV |
| `Dimm.0` | float | 0.0 | Pre-exponential constant for V-- cm2/sec |
| `Dimm.E` | float | 0.0 | Activation energy for V-- diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### interstitial

Set coefficients of interstitial kinetics.

매뉴얼 160쪽

```
interstitial
      ( silicon | oxide | poly | oxynitr | nitride | gas | gaas )
      [ D.0=<n> ] [ D.E=<n> ]
      [ Kr.0=<n> ] [ Kr.E=<n> ]
      [ Cstar.0=<n> ] [ Cstar.E=<n> ]
      [ ktrap.0=<n> ] [ ktrap.E=<n> ]
      [ neu.0=<n> ] [ neu.E=<n> ] [ neg.0=<n> ] [ neg.E=<n> ]
      [ dneg.0=<n> ] [ dneg.E=<n> ] [ tneg.0=<n> ] [ tneg.E=<n>]
      [ pos.0=<n> ] [ pos.E=<n> ] [ dpos.0=<n> ] [ dpos.E=<n> ]
      [ tpos.0=<n> ] [ tpos.E=<n> ]
      [ ( /silicon | /oxide | /poly | /oxynitr | /nitride | /gas |
              /gaas ) ]
      [ time.inj ] [ growth.inj ] [ recomb ] [ segregation ]
      [ Ksurf.0=<n> ] [ Ksurf.E=<n> ]
      [ Krat.0=<n> ] [ Krat.E=<n> ]
      [ Kpow.0=<n> ] [ Kpow.E=<n> ]
      [ vmole=<n> ] [ theta.0=<n> ] [ theta.E=<n> ]
      [ Gpow.0=<n> ] [ Gpow.E=<n> ]
      [ A.0=<n> ] [ A.E=<n> ] [ t0.0=<n> ] [ t0.E=<n> ]
      [ Tpow.0=<n> ] [ Tpow.E=<n> ]
      [ rec.str=<s> ] [ inj.str=<s> ]
      [ Seg.E=<n> ] [ Seg.0=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `aluminum` | boolean | — | · `material` 중 택1 |
| `photoresist` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `D.0` | float | 1e-9 | cm2 / sec diffusion preexponential |
| `D.E` | float | 0.0 | eV - diffusion activation energy |
| `Kr.0` | float | 2.5e-17 | cm3 / sec preexponential for I-V recombination |
| `Kr.E` | float | 0.0 | eV - activation energy for I-V recombination |
| `Cstar.0` | float | 1e13 | cm-3 equilibrium concentration preexponential |
| `Cstar.E` | float | 0.0 | eV - activation of equilibrium concentration |
| `ktrap.0` | float | — | cm3 / sec preexponential for trap constant |
| `ktrap.E` | float | 0.0 | eV - activation energy for trap lifetime |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `neu.0` | float | 1.0 |  |
| `neg.0` | float | 0.0 |  |
| `dneg.0` | float | 0.0 |  |
| `tneg.0` | float | 0.0 |  |
| `pos.0` | float | 0.0 |  |
| `dpos.0` | float | 0.0 |  |
| `tpos.0` | float | 0.0 |  |
| `neu.E` | float | 1.0 |  |
| `neg.E` | float | 0.0 |  |
| `dneg.E` | float | 0.0 |  |
| `tneg.E` | float | 0.0 |  |
| `pos.E` | float | 0.0 |  |
| `dpos.E` | float | 0.0 |  |
| `tpos.E` | float | 0.0 |  |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `time.inj` | boolean | — |  |
| `growth.inj` | boolean | — |  |
| `recomb` | boolean | — |  |
| `segregation` | boolean | — |  |
| `Ksurf.0` | float | 5.0e-6 | surface recombination velocity in cm/sec |
| `Ksurf.E` | float | 0.0 | surface recombination velocity activation |
| `Krat.0` | float | 0.0 | surface recombination velocity in cm/sec |
| `Krat.E` | float | 0.0 | surface recombination velocity activation |
| `Kpow.0` | float | 0.0 | power dependence of Ksurf on growth rate |
| `Kpow.E` | float | 0.0 | power dependence of Ksurf on growth rate |
| `vmole` | float | 5.0e22 | the atomic concentration of material being consumed |
| `theta.0` | float | 0.1 | fraction of atoms consumed injected preexponential |
| `theta.E` | float | 0.0 | fraction of atoms consumed injected activation |
| `Gpow.0` | float | 1.0 | power dependence of injection |
| `Gpow.E` | float | 0.0 | power dependence of injection |
| `A.0` | float | 1.0e10 | the preexponential injection constant |
| `A.E` | float | 0.0 | the activation injection constant |
| `t0.0` | float | 1.0 | preexponential time constant of injection |
| `t0.E` | float | 0.0 | activation time constant of injection |
| `Tpow.0` | float | 1.0 | preexponential power dependence |
| `Tpow.E` | float | 0.0 | activation power dependence |
| `rec.str` | string | — | formula for surface recombination |
| `inj.str` | string | — | formula for surface injection |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |

### isilicon

Set the coefficients of silicon impurity kinetics.

매뉴얼 199쪽

```
isilicon
        ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
        [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dim.0=<n> ] [ Dim.E=<n> ]
        [ Dimm.0=<n> ] [ Dimm.E=<n> ] [ Fi = <n> ]
        [ implanted ] [ grown.in ]
        [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
        [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
                /gaas ) ]
        [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
        [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 0.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 0.0 | Activation energy for V- diffusivity - eV |
| `Dimm.0` | float | 0.0 | Pre-exponential constant for V-- cm2/sec |
| `Dimm.E` | float | 0.0 | Activation energy for V-- diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### magnesium

Set the coefficients of magnesium kinetics.

매뉴얼 170쪽

```
magnesium
      ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
      [ Dix.0=<n> ] [ Dix.E=<n> ]
      [ Dip.0=<n> ] [ Dip.E=<n> ] [ Dipp.0=<n> ] [ Dipp.E=<n> ]
      [ Fi = <n> ]
      [ implanted ] [ grown.in ]
      [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
      [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
              /gaas ) ]
      [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
      [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dip.0` | float | 0.0 | Pre-exponential constant for V+ cm2/sec |
| `Dip.E` | float | 0.0 | Activation energy for V+ diffusivity - eV |
| `Dipp.0` | float | 0.0 | Pre-exponential constant for V++ cm2/sec |
| `Dipp.E` | float | 0.0 | Activation energy for V++ diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### material

Set the coefficients of some materials.

매뉴얼 176쪽

```
material
     ( silicon | oxide | poly | oxynitr | nitride | photores |
            aluminum )
     [ ( wet | dry ) ]
     [ Ni.0=<n> ] [ Ni.E=<n> ] [ Ni.Pow=<n> ]
     [ eps=<n> ]
     [ visc.0=<n> ] [ visc.E=<n> ] [ visc.x=<n> ]
     [ Young.m=<n> ] [ Poiss.r=<n> ]
     [ lcte=<string> ]
     [ intrin.sig=<n> ]
     [ act.a=<n> ] [ act.b=<n> ] [ ( n.type | p.type ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `silicon` | boolean | — | · `which` 중 택1 |
| `oxide` | boolean | — | · `which` 중 택1 |
| `oxynitride` | boolean | — | · `which` 중 택1 |
| `nitride` | boolean | — | · `which` 중 택1 |
| `poly` | boolean | — | · `which` 중 택1 |
| `photoresist` | boolean | — | · `which` 중 택1 |
| `aluminum` | boolean | — | · `which` 중 택1 |
| `gaas` | boolean | — | · `which` 중 택1 |
| `wet` | boolean | — | · `w2` 중 택1 |
| `dry` | boolean | — | · `w2` 중 택1 |
| `Ni.0` | float | 3.9e16 | Pre exponential of Ni |
| `Ni.E` | float | 0.605 | Activation Energy of Ni |
| `Ni.Pow` | float | 1.5 | Power of the temperature |
| `eps` | float | 13.1 | relative permittivity |
| `visc.0` | float | — | Viscosity prefactor g/(cm*s) |
| `visc.E` | float | — | Viscosity energy (electron volts) |
| `visc.x` | float | — | Artificial compressibility factor: 0-0.49999 |
| `Young.m` | float | — | Young's modulus(dynes/cm2) |
| `Poiss.r` | float | — | Poisson's ratio |
| `lcte` | string | — | linear coefficient of thermal expansion, /K |
| `intrin.sig` | float | — | intrinsic stress, dynes/cm2 |
| `p.type` | boolean | — | · `type` 중 택1 |
| `n.type` | boolean | — | · `type` 중 택1 |
| `act.a` | string | — | GaAs activation model parameter a |
| `act.b` | string | — | GaAs activation model parameter b |

### oxide

Specify oxidation coefficients.

매뉴얼 180쪽

```
oxide
        orientation= ( 111 | 110 | 100 )
        ( dry | wet )
        [ lin.l.0=<n> ] [ lin.l.e=<n> ] [ lin.h.0=<n> ] [ lin.h.e=<n> ]
        [ l.break=<n> ] [ l.pde=<n> ]
        [ par.l.0=<n> ] [ par.l.e=<n> ] [ par.h.0=<n> ] [ par.h.e=<n> ]
        [ p.break=<n> ] [ p.pdep=<n> ]
        [ ori.dep ] [ ori.fac=<n> ]
        [ thinox.0=<n> ] [ thinox.e=<n> ] [ thinox.l=<n> ]
        [ hcl.pc=<n> ] [ hclT=<string> ] [ hclP=<string> ]
        [ hcl.par=<string> ] [ hcl.lin=<string> ]
        [ baf.dep ] [ baf.ebk=<n> ] [ baf.pe=<n> ] [ baf.ppe=<n> ]
        [ baf.ne=<n> ] [ baf.nne=<n> ] [ baf.k0=<n> ] [ baf.ke=<n> ]
        [ stress.dep ] [ Vc=<n> ] [ Vr=<n> ] [ Vd=<n> ] [ Vt=<n> ]
        [ Dlim=<n> ]
        [ gamma=<n> ] [ alpha=<n> ]
        [ henry.coeff=<n> | theta=<n> ]
        [ ( silicon | oxide | nitride | poly | gaas | gas ) ]
        [ ( /silicon | /oxide | /nitride | /poly | /gaas | /gas ) ]
        [ diff.0=<n> ] [ diff.e=<n> ] [ seg.0=<n> ] [ seg.E=<n> ]
        [ trn.0=<n> ] [ trn.E=<n> ]
        [ initial=<n> ] [ spread=<n> | mask.edge=<n> ]
        [ erf.q=<n> ] [ erf.delta=<n> ] [ erf.lbb=<n> ] [ erf.h=<n> ]
        [ nit.thick=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `orient` | integer | 100 | relevant orientation for the coefficient specified (111/110/100) |
| `dry` | boolean | false |  |
| `wet` | boolean | false |  |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `l.break` | float | — | B/A breakpoint - degrees Celsius |
| `lin.l.0` | float | — | B/A prefactor at low T - microns/minute |
| `lin.l.e` | float | — | B/A energy    at low T - eV |
| `lin.h.0` | float | — | B/A prefactor at highT - microns/minute |
| `lin.h.e` | float | — | B/A energy    at highT - eV |
| `p.break` | float | — | B   breakpoint - degrees Celsius |
| `par.l.0` | float | — | B   prefactor at low T - microns/minute |
| `par.l.e` | float | — | B   energy    at low T - eV |
| `par.h.0` | float | — | B   prefactor at highT - microns/minute |
| `par.h.e` | float | — | B   energy    at highT - eV |
| `thinox.0` | float | — | thin oxide coeff prefactor - microns/minute |
| `thinox.e` | float | — | thin oxide coeff energy    - eV |
| `thinox.l` | float | — | thin oxide coeff decay length - microns |
| `l.pdep` | float | — | pressure power law dependence of B/A |
| `p.pdep` | float | — | pressure power law dependence of B |
| `hcl.pc` | float | — | % of hcl in the ambient |
| `hclT` | string | — | list of columns (temperatures) in hcl model |
| `hclP` | string | — | list of rows    (hcl %'s) in hcl model |
| `hcl.par` | string | — | row major array of parabolic dependences |
| `hcl.lin` | string | — | row major array of linear dependences |
| `baf.dep` | boolean | — | B/A dependent on Fermi level? |
| `baf.ebk` | float | — | B/A(Ef): dimensionless ratio of d(Eg/dT / k) |
| `baf.pe` | float | — | B/A(Ef):        positive vacancy activation energy(Ev) |
| `baf.ppe` | float | — | B/A(Ef): double positive vacancy activation energy(Ev) |
| `baf.ne` | float | — | B/A(Ef):        negative vacancy activation energy(Ev) |
| `baf.nne` | float | — | B/A(Ef): double negative vacancy activation energy(Ev) |
| `baf.k0` | float | — | B/A(Ef): enhancement ratio prefactor |
| `baf.ke` | float | — | B/A(Ef): enhancement ratio activation energy(Ev) |
| `alpha` | float | — | ratio of atomic volume in material 1 to material 2 |
| `henry.coef` | float | — | solubility of oxidant in oxide (/cm3/atm) |
| `theta` | float | — | conc of O atoms incorporated in material (/cm3) |
| `diff.0` | float | — | Oxidant diffusivity prefactor (cm2/s) |
| `diff.e` | float | — | Oxidant diffusivity activation energy (eV) |
| `seg.0` | float | — | segregation prefactor (cm2/s) |
| `seg.E` | float | — | segregation energy (eV) |
| `trn.0` | float | — | interface transfer prefactor (cm2/s) |
| `trn.E` | float | — | interface transfer energy (eV) |
| `stress.dep` | boolean | false | Stress dependent coefficients? |
| `ori.dep` | boolean | true | Use local orientation? |
| `ori.fac` | float | 1.0 | B/A relative to 111 |
| `Vc` | float | — | Volume coefficient of viscosity reduction (cubic angstroms) |
| `Vr` | float | — | Volume coefficient of B/A reduction (cubic angstroms) |
| `Vd` | float | — | Volume coefficient of B   reduction (cubic angstroms) |
| `Dlim` | float | — | Maximum D increase, default 1 |
| `Vt` | float | — | Volume coefficient of B/A reduction (cubic angstroms) |
| `gamma` | float | — | surface tension coefficient |
| `initial` | float | 0.002 | initial oxide thickness (not 0!) - mu |
| `spread` | float | 1.0 | ratio of lateral to vertical spread |
| `mask.edge` | float | -200 | oxide is to the right of mask.edge - mu |
| `nit.thick` | float | — | nitride thickness - mu |
| `erf.q` | float | — | q parameter for erf2 model - mu |
| `erf.delta` | float | — | delta paramter for erf2 model - mu |
| `erf.lbb` | string | — | Lbb model |
| `erf.h` | string | — | erf.h model |

### phosphorus

Set the coefficients of phosphorus kinetics.

매뉴얼 188쪽

```
phosphorus
       ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
       [ Dix.0=<n> ] [ Dix.E=<n> ]
       [ Dim.0=<n> ] [ Dim.E=<n> ]
       [ Dimm.0=<n> ] [ Dimm.E=<n> ]
       [ Dvx.0=<n> ] [ Dvx.E=<n> ]
       [ Dvm.0=<n> ] [ Dvm.E=<n> ]
       [ Dvmm.0=<n> ] [ Dvmm.E=<n> ]
       [ implanted ] [ grown.in ]
       [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
       [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
                /gaas ) ]
       [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
       [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 3.85 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 3.66 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 4.44 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 4.00 | Activation energy for V- diffusivity - eV |
| `Dimm.0` | float | 4.44 | Pre-exponential constant for V- cm2/sec |
| `Dimm.E` | float | 4.00 | Activation energy for V- diffusivity - eV |
| `Dvx.0` | float | 3.85 | Pre-exponential constant for Vo cm2/sec |
| `Dvx.E` | float | 3.66 | Activation energy for Vo diffusivity - eV |
| `Dvm.0` | float | 4.44 | Pre-exponential constant for V- cm2/sec |
| `Dvm.E` | float | 4.00 | Activation energy for V- diffusivity - eV |
| `Dvmm.0` | float | 4.44 | Pre-exponential constant for V- cm2/sec |
| `Dvmm.E` | float | 4.00 | Activation energy for V- diffusivity - eV |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### selenium

Set the coefficients of selenium kinetics.

매뉴얼 194쪽

```
selenium
        ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
        [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dim.0=<n> ] [ Dim.E=<n> ]
        [ Dimm.0=<n> ] [ Dimm.E=<n> ] [ Fi = <n> ]
        [ implanted ] [ grown.in ]
        [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
        [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
                /gaas ) ]
        [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
        [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 0.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 0.0 | Activation energy for V- diffusivity - eV |
| `Dimm.0` | float | 0.0 | Pre-exponential constant for V-- cm2/sec |
| `Dimm.E` | float | 0.0 | Activation energy for V-- diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### tin

Set the coefficients of tin kinetics.

매뉴얼 205쪽

```
tin
        ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
        [ Dix.0=<n> ] [ Dix.E=<n> ] [ Dim.0=<n> ] [ Dim.E=<n> ]
        [ Dimm.0=<n> ] [ Dimm.E=<n> ] [ Fi = <n> ]
        [ implanted ] [ grown.in ]
        [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
        [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
                /gaas ) ]
        [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
        [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dim.0` | float | 0.0 | Pre-exponential constant for V- cm2/sec |
| `Dim.E` | float | 0.0 | Activation energy for V- diffusivity - eV |
| `Dimm.0` | float | 0.0 | Pre-exponential constant for V-- cm2/sec |
| `Dimm.E` | float | 0.0 | Activation energy for V-- diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

### trap

Set coefficients of interstitial traps.

매뉴얼 210쪽

```
trap
       ( silicon | oxide | poly | oxynitr | nitride | gas |
              aluminum | photores )
       [ enable ]
       [ total=<n> ]
       [ frac.0=<n> ] [ frac.E=<n> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `aluminum` | boolean | — | · `material` 중 택1 |
| `photoresist` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `enable` | boolean | — |  |
| `total` | float | — | total trap concentration |
| `frac.0` | float | — | fraction at equilibrium filled |
| `frac.E` | float | — | fraction at equilibrium filled |

### vacancy

Set coefficients of vacancy kinetics.

매뉴얼 213쪽

```
vacancy
     ( silicon | oxide | poly | oxynitr | nitride | gaas | gas )
     [ D.0=<n> ] [ D.E=<n> ]
     [ Kr.0=<n> ] [ Kr.E=<n> ]
     [ Cstar.0=<n> ] [ Cstar.E=<n> ]
     [ ktrap.0=<n> ] [ ktrap.E=<n> ]
     [ neu.0=<n> ] [ neu.E=<n> ]
     [ neg.0=<n> ] [ neg.E=<n> ] [ dneg.0=<n> ] [ dneg.E=<n> ]
     [ tneg.0=<n> ] [ tneg.E=<n> ]
     [ pos.0=<n> ] [ pos.E=<n> ] [ dpos.0=<n> ] [ dpos.E=<n> ]
     [ tpos.0=<n> ] [ tpos.E=<n> ]
     [ ( /silicon | /oxide | /poly | /oxynitr | /nitride | /gaas |
             /gas ) ]
     [ time.inj ] [ growth.inj ] [ recomb ]
     [ Ksurf.0=<n> ] [ Ksurf.E=<n> ]
     [ Krat.0=<n> ] [ Krat.E=<n> ]
     [ Kpow.0=<n> ] [ Kpow.E=<n> ]
     [ vmole=<n> ] [ theta.0=<n> ] [ theta.E=<n> ]
     [ Gpow.0=<n> ] [ Gpow.E=<n> ]
     [ A.0=<n> ] [ A.E=<n> ] [ t0.0=<n> ] [ t0.E=<n> ]
     [ Tpow.0=<n> ] [ Tpow.E=<n> ]
     [ rec.str=<s> ] [ inj.str=<s> ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `aluminum` | boolean | — | · `material` 중 택1 |
| `photoresist` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `D.0` | float | 1e-9 | cm2 / sec diffusion preexponential |
| `D.E` | float | 0.0 | eV - diffusion activation energy |
| `Kr.0` | float | 2.5e-17 | cm3 / sec preexponential for I-V recombination |
| `Kr.E` | float | 0.0 | eV - activation energy for I-V recombination |
| `Cstar.0` | float | 1e13 | cm-3 equilibrium concentration preexponential |
| `Cstar.E` | float | 0.0 | eV - activation of equilibrium concentration |
| `ktrap.0` | float | — | cm3 / sec preexponential for trap constant |
| `ktrap.E` | float | 0.0 | eV - activation energy for trap lifetime |
| `boron` | boolean | — | · `impurity` 중 택1 |
| `gallium` | boolean | — | · `impurity` 중 택1 |
| `antimony` | boolean | — | · `impurity` 중 택1 |
| `arsenic` | boolean | — | · `impurity` 중 택1 |
| `phosphorus` | boolean | — | · `impurity` 중 택1 |
| `beryllium` | boolean | — | · `impurity` 중 택1 |
| `magnesium` | boolean | — | · `impurity` 중 택1 |
| `selenium` | boolean | — | · `impurity` 중 택1 |
| `isilicon` | boolean | — | · `impurity` 중 택1 |
| `tin` | boolean | — | · `impurity` 중 택1 |
| `germanium` | boolean | — | · `impurity` 중 택1 |
| `zinc` | boolean | — | · `impurity` 중 택1 |
| `carbon` | boolean | — | · `impurity` 중 택1 |
| `generic` | boolean | — | · `impurity` 중 택1 |
| `neu.0` | float | 1.0 |  |
| `neg.0` | float | 0.0 |  |
| `dneg.0` | float | 0.0 |  |
| `tneg.0` | float | 0.0 |  |
| `pos.0` | float | 0.0 |  |
| `dpos.0` | float | 0.0 |  |
| `tpos.0` | float | 0.0 |  |
| `neu.E` | float | 1.0 |  |
| `neg.E` | float | 0.0 |  |
| `dneg.E` | float | 0.0 |  |
| `tneg.E` | float | 0.0 |  |
| `pos.E` | float | 0.0 |  |
| `dpos.E` | float | 0.0 |  |
| `tpos.E` | float | 0.0 |  |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `time.inj` | boolean | — |  |
| `growth.inj` | boolean | — |  |
| `recomb` | boolean | — |  |
| `segregation` | boolean | — |  |
| `Ksurf.0` | float | 5.0e-6 | surface recombination velocity in cm/sec |
| `Ksurf.E` | float | 0.0 | surface recombination velocity activation |
| `Krat.0` | float | 0.0 | surface recombination velocity in cm/sec |
| `Krat.E` | float | 0.0 | surface recombination velocity activation |
| `Kpow.0` | float | 0.0 | power dependence of Ksurf on growth rate |
| `Kpow.E` | float | 0.0 | power dependence of Ksurf on growth rate |
| `vmole` | float | 5.0e22 | the atomic concentration of material being consumed |
| `theta.0` | float | 0.1 | fraction of atoms consumed injected preexponential |
| `theta.E` | float | 0.0 | fraction of atoms consumed injected activation |
| `Gpow.0` | float | 1.0 | power dependence of injection |
| `Gpow.E` | float | 0.0 | power dependence of injection |
| `A.0` | float | 1.0e10 | the preexponential injection constant |
| `A.E` | float | 0.0 | the activation injection constant |
| `t0.0` | float | 1.0 | preexponential time constant of injection |
| `t0.E` | float | 0.0 | activation time constant of injection |
| `Tpow.0` | float | 1.0 | preexponential power dependence |
| `Tpow.E` | float | 0.0 | activation power dependence |
| `rec.str` | string | — | formula for surface recombination |
| `inj.str` | string | — | formula for surface injection |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |

### zinc

Set the coefficients of zinc kinetics.

매뉴얼 221쪽

```
zinc
        ( silicon | oxide | oxynit | nitride | gas | poly | gaas )
        [ Dix.0=<n> ] [ Dix.E=<n> ]
        [ Dip.0=<n> ] [ Dip.E=<n> ] [ Dipp.0=<n> ] [ Dipp.E=<n> ]
        [ Fi = <n> ]
        [ implanted ] [ grown.in ]
        [ ss.clear ] [ ss.temp=<n> ] [ ss.conc=<n> ]
        [ ( /silicon | /oxide | /oxynitr | /nitride | /gas | /poly |
                /gaas ) ]
        [ Seg.0=<n> ] [ Seg.E=<n> ] [ Trn.0=<n> ] [ Trn.E=<n> ]
        [ ( donor | acceptor ) ]
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `donor` | boolean | — | · `model` 중 택1 |
| `acceptor` | boolean | — | · `model` 중 택1 |
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `Dix.0` | float | 0.0 | Pre-exponential constant for Vo cm2/sec |
| `Dix.E` | float | 0.0 | Activation energy for Vo diffusivity - eV |
| `Dip.0` | float | 0.0 | Pre-exponential constant for V+ cm2/sec |
| `Dip.E` | float | 0.0 | Activation energy for V+ diffusivity - eV |
| `Dipp.0` | float | 0.0 | Pre-exponential constant for V++ cm2/sec |
| `Dipp.E` | float | 0.0 | Activation energy for V++ diffusivity - eV |
| `Fi` | float | 0.0 | Fractional Interstitialcy |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `ss.clear` | boolean | false | reset the value list |
| `ss.temp` | float | — | temperature half of solid solubility pair |
| `ss.conc` | float | — | concentration half of solid solubility pair |

## 문서 없음

suprem.key 에는 있지만 매뉴얼에 설명이 없다. 받는 파라미터는 알 수 있어도 무엇을 하는 커맨드인지는 직접 확인해야 한다.

### cesium

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `D.0` | float | 0.037 | Pre-exponential constant for Vo cm2/sec |
| `D.E` | float | 3.46 | Activation energy for Vo diffusivity - eV |
| `mobile` | boolean | true | Mobile species? |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |
| `g.0` | float | 1.0 | Pre-exponential constant for detrapping cm/s |
| `g.E` | float | 0.0 | Activation energy for detrapping |

### device

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `init` | boolean | — |  |
| `electron` | boolean | — | solve for electrons |
| `qfn` | float | — | fixed electron quasifermi level |
| `holes` | boolean | — | solve for holes |
| `qfp` | float | — | fixed hole quasifermi level |
| `width` | float | — |  |
| `movie` | string | — |  |

### gold

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `implanted` | boolean | — |  |
| `grown.in` | boolean | — |  |
| `K.0` | float | 0.037 | Pre-exponential constant for Vo cm2/sec |
| `K.E` | float | 3.46 | Activation energy for Vo diffusivity - eV |
| `silicon` | boolean | — | · `material` 중 택1 |
| `oxide` | boolean | — | · `material` 중 택1 |
| `oxynitride` | boolean | — | · `material` 중 택1 |
| `nitride` | boolean | — | · `material` 중 택1 |
| `poly` | boolean | — | · `material` 중 택1 |
| `gas` | boolean | — | · `material` 중 택1 |
| `gaas` | boolean | — | · `material` 중 택1 |
| `/silicon` | boolean | — | · `mater` 중 택1 |
| `/oxide` | boolean | — | · `mater` 중 택1 |
| `/oxynitride` | boolean | — | · `mater` 중 택1 |
| `/nitride` | boolean | — | · `mater` 중 택1 |
| `/poly` | boolean | — | · `mater` 중 택1 |
| `/gas` | boolean | — | · `mater` 중 택1 |
| `/gaas` | boolean | — | · `mater` 중 택1 |
| `Seg.0` | float | 1.0 | Pre-exponential constant for Segregation |
| `Seg.E` | float | 0.0 | Activation energy for Segregation |
| `Trn.0` | float | 1.0 | Pre-exponential constant for transport cm/s |
| `Trn.E` | float | 0.0 | Activation energy for transport |

