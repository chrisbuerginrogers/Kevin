# StockDB: how it works

StockDB looks up western fish stocking records from 1952 to 1999. It's a search tool, so the only calculation is the fish total. This page explains how the data is read, how searches match, and how the total is worked out. All of the code is in the `<script>` block of [`index.html`](index.html).

Live page: https://chrisbuerginrogers.github.io/Kevin/StockDB/

## The data

[`WestStock52-99mod.txt`](WestStock52-99mod.txt) is a tab-separated file with one stocking event per row: 56,083 rows covering 2,308 water codes. The first line holds the column names:

`CODE  NAME  SPECIES  NUMFISH  INSIZE  SIZE  YEAR  UNIT  MAJ_DRAIN  COUNTY  AWM_AREA  AREABIO`

The page uses three of these:

| Column | Used for |
|---|---|
| `CODE` | The 5-digit water code |
| `NAME` | The water name |
| `NUMFISH` | Number of fish stocked, summed for the total |

The other columns are shown in the results table as they appear in the file.

**When the page loads it:**

1. Splits the file into lines (any line ending) and each line on tabs. Blank rows are skipped.
2. Converts `YEAR` from two digits to four: a value below 100 has 1900 added (`53` becomes `1953`). Values already four digits long are kept.
3. Builds a list of waters, one per distinct code and name pair (2,315 in all), with the number of rows for each.

## Searching

**By name.** As you type, the suggestion list shows up to 60 waters whose names contain the text (ignoring case), in this order:

1. names that **start** with the text
2. names with a **word** that starts with the text (after a space, `#`, `(`, `-` or `/`)
3. names that contain the text anywhere else

Within each group, waters are in alphabetical order. Each suggestion shows its code and number of rows.

- **Choosing a suggestion** shows the rows with that exact code and name.
- **Pressing Enter** without choosing shows every row whose name contains the text, across all waters.

**By code.** Once you've typed all 5 digits, the page shows every row with that code. If the code has one name, it fills the name box.

## The total

The status line shows the number of rows found and the total number of fish:

```
total fish = sum of NUMFISH over the rows shown
```

Blank or non-numeric `NUMFISH` values count as 0.

## Data cleanup

Each water code normally has one name. Abbreviations, typos and word-order variants were merged into a single name per code (for example LIME CR, LIME CREEK and LIME CRK became LIME CREEK). Seven codes deliberately keep two names because the code itself looks miscoded. They're listed in the [main README](../README.md#stockdb), and the original names are in the git history.
