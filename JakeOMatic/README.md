# JakeOmatic: how the calculations work

JakeOmatic 4.0 summarizes lake and stream fish surveys. This page explains every statistic it reports. All of the code is in [`jakeomatic.py`](jakeomatic.py), and the function names below refer to it.

Live page: https://chrisbuerginrogers.github.io/Kevin/JakeOMatic/

## Fish records

Each row of the fish table is one record: species code, **count**, length (mm), weight (g), pass number (stream surveys), and optional status, mark and tag ID.

- **Count.** A row stands for *count* fish (normally 1). Every total, percentage, CPUE, mean and length-frequency bar is weighted by it. A row with count 5 and length 200 mm counts as five 200 mm fish.
- **Missing values.** A length or weight of 0 means "not measured". Those fish still count toward catch totals and CPUE, but not toward length or weight summaries.
- **Lengths in cm** are converted to mm when entered.

## Species table (LUT)

Each species has a standard-weight equation and five length categories (mm):

```math
\log_{10} W_s = a \cdot \log_{10} L + b
```

where *L* is total length in mm, *W<sub>s</sub>* is in grams, *a* is the **slope** and *b* the **intercept**. A slope of 0 means the species has no equation, so Wr isn't calculated for it. A stock length of 0 means PSD and RSD-P aren't calculated.

| Code | Species | Slope *a* | Intercept *b* | Stock | Quality | Preferred | Memorable | Trophy |
|---|---|---|---|---|---|---|---|---|
| LOC | Brown trout | 2.96 | −4.867 | 150 | 230 | 300 | 380 | 460 |
| RBT | Rainbow trout | 2.99 | −4.898 | 250 | 400 | 500 | 650 | 800 |
| SRN, CRN, GBN, RGN | Cutthroat trout | 3.086 | −5.192 | 200 | 350 | 450 | 600 | 750 |
| BRK | Brook trout | 3.103 | −5.186 | 200 | 330 | — | — | — |
| MWF | Mountain whitefish | 3.036 | −5.086 | — | — | — | — | — |
| MAC | Lake trout | 3.264 | −5.681 | 300 | 500 | 650 | 800 | 1000 |
| RCS | River carpsucker | 2.992 | −4.839 | 180 | 280 | 360 | 460 | 560 |
| WHS | White sucker | 2.94 | −4.755 | 150 | 250 | 330 | 410 | 510 |

Other species in the list (grayling, splake, kokanee, Arctic char and most suckers) have no default values. You can edit the table, or add species, on the **Species LUT** tab. Your changes are saved in your browser.

## Weights and condition

**Relative weight** (`relative_weight`) compares a fish's weight to the standard weight for its length:

```math
W_r = 100 \times \frac{W}{W_s}
```

**Mean Wr** is the count-weighted mean of Wr over fish that have a length, a weight, and a species equation.

*Example.* A 300 mm brown trout weighing 300 g: W<sub>s</sub> = 10<sup>2.96 × log₁₀(300) − 4.867</sup> = 291.9 g, so Wr = 100 × 300 / 291.9 = **102.8**.

**Estimate Weights** (`estimate_weights`) fills each missing weight with W<sub>s</sub> for the fish's length (rounded to 0.1 g), so those fish have Wr = 100. Use it only when you need biomass, because it pulls mean Wr toward 100.

**Mean length and weight** are count-weighted means over measured fish. Lake summaries show them in inches (mm ÷ 25.4) and pounds (g ÷ 453.59237).

## Lake survey (`lake_stats`, `level2_lake`)

### Catch per unit effort

You enter effort as hours of electrofishing (E), gill net (G) and trap net (T).

```math
\text{CPUE}_\text{gear} = \frac{\text{number of fish of the species}}{\text{hours of that gear}}
```

**CPUE ≥S** uses only fish at or above stock length. Records aren't tagged by gear, so each gear's CPUE divides the same catch by that gear's hours. Enter hours only for the gear you actually used. A gear with 0 hours shows no CPUE.

### Size structure (`size_structure`)

Proportional and relative stock density, as percentages of stock-length fish:

```math
\text{PSD} = 100 \times \frac{\text{fish} \ge \text{quality length}}{\text{fish} \ge \text{stock length}}
\qquad
\text{RSD-P} = 100 \times \frac{\text{fish} \ge \text{preferred length}}{\text{fish} \ge \text{stock length}}
```

*Example.* 40 rainbow trout of 250 mm or more, of which 18 are 400 mm or more and 5 are 500 mm or more: PSD = 100 × 18/40 = **45**, RSD-P = 100 × 5/40 = **12.5**.

### Level II table

One row per species, in the order species first appear in the fish table:

| Column | Calculation |
|---|---|
| # Caught | Number of fish of the species |
| % Catch | 100 × species fish ÷ all fish in the survey |
| Mean Ln, Ln Range | Mean, minimum and maximum length, in inches |
| Mean Wt, Wt Range | Mean, minimum and maximum weight, in pounds |
| E / G / T CPUE | Fish per hour for each gear |
| PSD, RSD-P, Mean Wr | As above |

The length-frequency table counts fish in 3 cm bins from 0 to 96 cm, plus a final bin for fish over 96 cm. Each bin includes its lower edge and excludes its upper edge (a 30.0 cm fish goes in 30–33).

## Stream survey (`stream_stats`, `level2_stream`)

### Size filter

Stream statistics use only fish whose length is within the **min** and **max** cut (mm, inclusive). A max of 0 means no upper limit. The filter applies to every stream statistic, chart and Level II column.

### Station size (`station`)

You enter the station length and mean width in feet.

```math
\text{area (ha)} = \frac{\text{length (ft)} \times \text{width (ft)} \times 0.09290304}{10{,}000}
\qquad
\text{length (km)} = \text{length (ft)} \times 0.0003048
```

### Two-pass removal estimate (`two_pass_removal`)

With *C*<sub>1</sub> fish caught on the first pass and *C*<sub>2</sub> on the second, the Seber & Le Cren (1967) estimate is:

```math
\hat{N} = \frac{C_1^2}{C_1 - C_2}
\qquad
\hat{p} = \frac{C_1 - C_2}{C_1}
\qquad
\operatorname{Var}(\hat{N}) = \frac{C_1^2\, C_2^2\, (C_1 + C_2)}{(C_1 - C_2)^4}
```

where *p̂* is the capture probability. The 95% confidence interval is N̂ ± 1.96 √Var(N̂). The lower limit is never set below *C*<sub>1</sub> + *C*<sub>2</sub>, the number of fish actually caught.

There's no estimate if the first pass caught no fish, or if the second pass caught as many as the first (*C*<sub>2</sub> ≥ *C*<sub>1</sub>), because the catch didn't go down.

### Density and biomass (`_stream_species`)

```math
\text{fish/ha} = \frac{\hat{N}}{\text{area}}
\qquad
\text{fish/km} = \frac{\hat{N}}{\text{length}}
\qquad
\text{kg/ha} = \frac{\hat{N} \times \bar{W}}{1000 \times \text{area}}
\qquad
\text{kg/km} = \frac{\hat{N} \times \bar{W}}{1000 \times \text{length}}
```

where *W̄* is the mean weight (g) of the weighed fish of that species within the size cut. Each ± value is the 95% half-width of N̂ put through the same formula. That interval reflects uncertainty in N̂ only, not in mean weight.

### Level II table

The stream Level II table reports the same quantities in English units:

| Column | Calculation |
|---|---|
| 1st Pass, 2nd Pass | *C*<sub>1</sub>, *C*<sub>2</sub> |
| Capture P | *p̂* |
| Pop Est, 95% CI | N̂ and its ± half-width |
| #/Mile | N̂ ÷ (km × 0.621371192) |
| #/Acre | N̂ ÷ (ha × 2.4710538) |
| Lb/Acre | N̂ × *W̄* ÷ 453.59237 ÷ acres |
| Mean Wr | As above |

The length-frequency table uses 2 cm bins from 0 to 60 cm, plus a final bin for fish over 60 cm.

### Worked example

A 600 ft × 18 ft station (0.1003 ha, 0.1829 km). Brown trout: 100 on the first pass, 40 on the second, mean weight 250 g.

| Quantity | Value |
|---|---|
| N̂ | 100² / (100 − 40) = **166.7** |
| *p̂* | 60 / 100 = **0.60** |
| SE | √(100² × 40² × 140 / 60⁴) = 13.1 |
| 95% CI | ± 25.8, so 140.9 to 192.4 |
| Fish/ha | 166.7 / 0.1003 = **1,661** |
| Fish/km | 166.7 / 0.1829 = **911** |
| kg/ha | 166.7 × 250 / 1000 / 0.1003 = **415** |

## Chapman-Petersen mark-recapture (`chapman_petersen`)

*M* fish are marked on the first visit. On the second, *C* fish are caught, and *R* of them are marked recaptures. Chapman's modified Petersen estimate, with Seber's (1970) variance:

```math
\hat{N} = \frac{(M+1)(C+1)}{R+1} - 1
\qquad
\operatorname{Var}(\hat{N}) = \frac{(M+1)(C+1)(M-R)(C-R)}{(R+1)^2 (R+2)}
```

The 95% confidence interval is N̂ ± 1.96 √Var(N̂). The lower limit is never set below *M* + *C* − *R*, the number of different fish handled. The calculator also shows the unmodified Petersen estimate, *MC*/*R*, and the recapture rate *R*/*C*.

*Example.* *M* = 50, *C* = 60, *R* = 15: N̂ = 51 × 61 / 16 − 1 = **193.4**, 95% CI ± 65.8 (127.7 to 259.2). The Petersen estimate is 50 × 60 / 15 = 200.

## Charts

- **Length frequency** (`length_frequency`): counts of measured fish of the selected species in bins of the chosen width (mm), from 0 to the largest fish.
- **Wr plot** (`wr_points`): Wr against length for each fish of the selected species that has a length, a weight and a species equation.

Stream charts use only fish inside the size cut.

## Checking the numbers yourself

`jakeomatic.py` has no browser code, so you can run it with plain Python:

```bash
cd JakeOMatic
python3 -c "
import jakeomatic as j
print(j.two_pass_removal(100, 40))
print(j.chapman_petersen(50, 60, 15))
lut = j.default_lut()
print(j.relative_weight(300, 300, j.lookup(lut, 'LOC')))
"
```

## Changes from JakeOmatic 3.0

Version 4.0 uses the Count field everywhere, uses the Seber & Le Cren variance for removal estimates (the 3.0 formula underestimated it), bases stream densities and biomass on the population estimate, and applies the size filter to all stream statistics. See the [main README](../README.md#jakeomatic) for the full list.

## References

- Seber, G. A. F., and E. D. Le Cren. 1967. Estimating population parameters from catches large relative to the population. *Journal of Animal Ecology* 36:631–643.
- Seber, G. A. F. 1970. The effects of trap response on tag recapture estimates. *Biometrics* 26:13–22.
- Standard-weight equations and length categories: Bister et al. 2000 (*North American Journal of Fisheries Management* 20:570–574), Hyatt & Hubert 2001 (*NAJFM* 21:253–254) and Muoneke & Pope 1999 (*NAJFM* 19:878–879), as cited in the code.
