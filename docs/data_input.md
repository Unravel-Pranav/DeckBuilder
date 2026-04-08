Below are **CSV versions for all chart / graph data** from your file so you can directly load them into your system.

(Source data extracted from your uploaded script: )

---

# CSV Data for All Chart Types

## 1. Bar Chart – Leasing Volume by Market

```csv
Market,Volume_MSF
Chicago,42
Dallas,38
Atlanta,31
Phoenix,28
Denver,22
```

---

## 2. Line Chart – Vacancy Rate Trend

```csv
Quarter,Vacancy_Rate
2023 Q1,4.2
2023 Q2,4.5
2023 Q3,4.8
2023 Q4,5.1
2024 Q1,5.3
2024 Q2,5.0
2024 Q3,4.7
```

---

## 3. Line Chart Multi Axis – Asking vs Effective Rent

```csv
Quarter,Asking_Rent,Effective_Rent
2024 Q1,12.10,10.80
2024 Q2,12.50,11.20
2024 Q3,12.80,11.50
2024 Q4,13.20,11.90
2025 Q1,13.10,12.00
```

---

## 4. Area Chart – Monthly Absorption

```csv
Month,Absorption_SF
Jan,120000
Feb,145000
Mar,132000
Apr,158000
May,167000
Jun,149000
```

---

## 5. Area Multi Axis – Availability by Class

```csv
Quarter,Class_A,Class_B,Class_C
2024 Q1,320,210,90
2024 Q2,340,225,85
2024 Q3,360,230,100
2024 Q4,375,245,95
2025 Q1,390,260,105
```

---

## 6. Horizontal Bar – Rent Growth by Region

```csv
Region,Rent_Growth_Pct
Northeast,5.2
Mid-Atlantic,4.4
Midwest,3.8
South,6.1
Mountain West,5.0
Pacific,4.9
```

---

## 7. Stacked Bar – Direct vs Sublease

```csv
Market,Direct_SF,Sublease_SF
North,820000,140000
South,610000,210000
East,705000,95000
West,890000,260000
Central,540000,120000
```

---

## 8. Pie Chart – Inventory by Class

```csv
Segment,Share
Class A,42
Class B,33
Class C,18
Unclassified,7
```

---

## 9. Donut Chart – Leasing by Tenant Type

```csv
Tenant_Type,Pct
Logistics / 3PL,48
Light Mfg,27
R&D / Lab,14
Other,11
```

---

## 10. Single Column Stacked – Allocation by Risk

```csv
Component,Value
Core / Core+,48
Value-Add,28
Opportunistic,14
Development,10
```

---

# Combo Charts CSV

## 11. Combo Single Bar + Line

```csv
City,Leasing_Vol,Cap_Rate
Chicago,118,5.4
Dallas,96,5.8
Atlanta,104,5.6
Phoenix,88,6.1
Denver,72,6.3
```

---

## 12. Combo Double Bar + Line

```csv
Year,New_Supply,Net_Absorption,Vacancy
2022,42,38,5.1
2023,55,44,5.4
2024,48,41,5.7
2025E,40,45,5.3
```

---

## 13. Combo Stacked Bar + Line

```csv
Quarter,Direct,Sublease,Rent_Index
2024 Q1,320,90,100
2024 Q2,340,110,102
2024 Q3,360,95,105
2024 Q4,375,125,108
```

---

## 14. Combo Area + Bar

```csv
Month,Pipeline_MSF,Deliveries_MSF
Jan,72,58
Feb,88,64
Mar,91,70
Apr,85,90
```

---

# Tables CSV

## Generic Table

```csv
Metric,High,Low,Avg
Asking Rent ($/SF),15.50,8.25,11.20
Sale Price ($/SF),210,145,178
Cap Rate (%),6.5,4.8,5.4
NOI Growth (%),4.2,1.8,3.1
```

---

## Market Stats Table

```csv
Submarket,Inventory_SF,Vacancy,Net_Absorption,Under_Construction
O'Hare,120450000,4.2%,245000,1200000
I-88 Corridor,85200000,5.1%,-12000,450000
South Suburbs,92100000,6.8%,115000,0
Central City,45000000,3.5%,45000,85000
Lake County,38700000,7.2%,-8500,0
```

---

## Market Stats Sub Table

```csv
Item,Chicago,Dallas,New York,Phoenix
Leasing Activity,1.2M SF,0.9M SF,0.5M SF,0.7M SF
Net Absorption,450K SF,120K SF,-50K SF,280K SF
Deliveries,800K SF,1.5M SF,200K SF,950K SF
Under Construction,2.1M SF,3.0M SF,0.8M SF,1.2M SF
```

---

## Industrial Figures Table

```csv
Market,Total_SF,Available_SF,Availability_Rate
Hub Alpha,10000000,500000,5.0%
Hub Beta,15000000,1200000,8.0%
Hub Gamma,8500000,340000,4.0%
```

---

# If you are building a system, remember this structure:

| Chart Type | X Column | Y Columns       |
| ---------- | -------- | --------------- |
| Bar        | Market   | Volume          |
| Line       | Time     | Value           |
| Multi Line | Time     | Multiple Values |
| Stacked    | Category | Multiple Values |
| Pie        | Category | Share           |
| Combo      | Category | Bars + Line     |

---

If you want, next I can give **JSON schema for each chart type** (very important for your PPT engine).




I checked your file. It already contains **sample data for all map/chart/graph/table types** inside `CHART_DATA` and `TABLE_DATA`. I’ll extract and organize it so you can directly use it.
(Reference file: )

---

# All Chart / Graph Data Types (From Your File)

## 1. Bar Chart

```json
[
  {"Market": "Chicago", "Volume_MSF": 42},
  {"Market": "Dallas", "Volume_MSF": 38},
  {"Market": "Atlanta", "Volume_MSF": 31},
  {"Market": "Phoenix", "Volume_MSF": 28},
  {"Market": "Denver", "Volume_MSF": 22}
]
```

---

## 2. Line Chart – Single Axis

```json
[
  {"Quarter": "2023 Q1", "Vacancy_Rate": 4.2},
  {"Quarter": "2023 Q2", "Vacancy_Rate": 4.5},
  {"Quarter": "2023 Q3", "Vacancy_Rate": 4.8},
  {"Quarter": "2023 Q4", "Vacancy_Rate": 5.1},
  {"Quarter": "2024 Q1", "Vacancy_Rate": 5.3},
  {"Quarter": "2024 Q2", "Vacancy_Rate": 5.0},
  {"Quarter": "2024 Q3", "Vacancy_Rate": 4.7}
]
```

---

## 3. Line Chart – Multi Axis

```json
[
  {"Quarter": "2024 Q1", "Asking_Rent": 12.10, "Effective_Rent": 10.80},
  {"Quarter": "2024 Q2", "Asking_Rent": 12.50, "Effective_Rent": 11.20},
  {"Quarter": "2024 Q3", "Asking_Rent": 12.80, "Effective_Rent": 11.50},
  {"Quarter": "2024 Q4", "Asking_Rent": 13.20, "Effective_Rent": 11.90},
  {"Quarter": "2025 Q1", "Asking_Rent": 13.10, "Effective_Rent": 12.00}
]
```

---

## 4. Area Chart – Single Axis

```json
[
  {"Month": "Jan", "Absorption_SF": 120000},
  {"Month": "Feb", "Absorption_SF": 145000},
  {"Month": "Mar", "Absorption_SF": 132000},
  {"Month": "Apr", "Absorption_SF": 158000},
  {"Month": "May", "Absorption_SF": 167000},
  {"Month": "Jun", "Absorption_SF": 149000}
]
```

---

## 5. Area Chart – Multi Axis

```json
[
  {"Quarter": "2024 Q1", "Class_A": 320, "Class_B": 210, "Class_C": 90},
  {"Quarter": "2024 Q2", "Class_A": 340, "Class_B": 225, "Class_C": 85},
  {"Quarter": "2024 Q3", "Class_A": 360, "Class_B": 230, "Class_C": 100},
  {"Quarter": "2024 Q4", "Class_A": 375, "Class_B": 245, "Class_C": 95},
  {"Quarter": "2025 Q1", "Class_A": 390, "Class_B": 260, "Class_C": 105}
]
```

---

## 6. Horizontal Bar Chart

```json
[
  {"Region": "Northeast", "Rent_Growth_Pct": 5.2},
  {"Region": "Mid-Atlantic", "Rent_Growth_Pct": 4.4},
  {"Region": "Midwest", "Rent_Growth_Pct": 3.8},
  {"Region": "South", "Rent_Growth_Pct": 6.1},
  {"Region": "Mountain West", "Rent_Growth_Pct": 5.0},
  {"Region": "Pacific", "Rent_Growth_Pct": 4.9}
]
```

---

## 7. Stacked Bar Chart

```json
[
  {"Market": "North", "Direct_SF": 820000, "Sublease_SF": 140000},
  {"Market": "South", "Direct_SF": 610000, "Sublease_SF": 210000},
  {"Market": "East", "Direct_SF": 705000, "Sublease_SF": 95000},
  {"Market": "West", "Direct_SF": 890000, "Sublease_SF": 260000},
  {"Market": "Central", "Direct_SF": 540000, "Sublease_SF": 120000}
]
```

---

## 8. Pie Chart

```json
[
  {"Segment": "Class A", "Share": 42},
  {"Segment": "Class B", "Share": 33},
  {"Segment": "Class C", "Share": 18},
  {"Segment": "Unclassified", "Share": 7}
]
```

---

## 9. Donut Chart

```json
[
  {"Tenant_Type": "Logistics / 3PL", "Pct": 48},
  {"Tenant_Type": "Light Mfg", "Pct": 27},
  {"Tenant_Type": "R&D / Lab", "Pct": 14},
  {"Tenant_Type": "Other", "Pct": 11}
]
```

---

## 10. Single Column Stacked

```json
[
  {"Component": "Core / Core+", "Value": 48},
  {"Component": "Value-Add", "Value": 28},
  {"Component": "Opportunistic", "Value": 14},
  {"Component": "Development", "Value": 10}
]
```

---

# Combo Charts

## 11. Combo – Single Bar + Line

```json
[
  {"City": "Chicago", "Leasing_Vol": 118, "Cap_Rate": 5.4},
  {"City": "Dallas", "Leasing_Vol": 96, "Cap_Rate": 5.8},
  {"City": "Atlanta", "Leasing_Vol": 104, "Cap_Rate": 5.6},
  {"City": "Phoenix", "Leasing_Vol": 88, "Cap_Rate": 6.1},
  {"City": "Denver", "Leasing_Vol": 72, "Cap_Rate": 6.3}
]
```

---

## 12. Combo – Double Bar + Line

```json
[
  {"Year": "2022", "New_Supply": 42, "Net_Absorption": 38, "Vacancy": 5.1},
  {"Year": "2023", "New_Supply": 55, "Net_Absorption": 44, "Vacancy": 5.4},
  {"Year": "2024", "New_Supply": 48, "Net_Absorption": 41, "Vacancy": 5.7},
  {"Year": "2025E", "New_Supply": 40, "Net_Absorption": 45, "Vacancy": 5.3}
]
```

---

## 13. Combo – Stacked Bar + Line

```json
[
  {"Quarter": "2024 Q1", "Direct": 320, "Sublease": 90, "Rent_Index": 100},
  {"Quarter": "2024 Q2", "Direct": 340, "Sublease": 110, "Rent_Index": 102},
  {"Quarter": "2024 Q3", "Direct": 360, "Sublease": 95, "Rent_Index": 105},
  {"Quarter": "2024 Q4", "Direct": 375, "Sublease": 125, "Rent_Index": 108}
]
```

---

## 14. Combo – Area + Bar

```json
[
  {"Month": "Jan", "Pipeline_MSF": 72, "Deliveries_MSF": 58},
  {"Month": "Feb", "Pipeline_MSF": 88, "Deliveries_MSF": 64},
  {"Month": "Mar", "Pipeline_MSF": 91, "Deliveries_MSF": 70},
  {"Month": "Apr", "Pipeline_MSF": 85, "Deliveries_MSF": 90}
]
```

---

# Table Data Types

## Generic Table

```json
[
  {"Metric": "Asking Rent ($/SF)", "High": "15.50", "Low": "8.25", "Avg": "11.20"},
  {"Metric": "Sale Price ($/SF)", "High": "210", "Low": "145", "Avg": "178"},
  {"Metric": "Cap Rate (%)", "High": "6.5", "Low": "4.8", "Avg": "5.4"}
]
```

## Market Stats Table

## Market Stats Sub Table

## Industrial Figures

## Large Table

(These are also defined in TABLE_DATA in the file.)

---

# Summary – All Chart Types Supported

Your system supports:

1. Bar Chart
2. Line Single Axis
3. Line Multi Axis
4. Area Single Axis
5. Area Multi Axis
6. Horizontal Bar
7. Stacked Bar
8. Pie
9. Donut
10. Single Column Stacked
11. Combo Single Bar + Line
12. Combo Double Bar + Line
13. Combo Stacked Bar + Line
14. Combo Area + Bar

**Total = 14 chart types**

---

# If you want I can next give you:

* JSON template for each chart
* CSV for each chart
* Map data format
* Axis config format
* Full frontend JSON example

Just tell me.
