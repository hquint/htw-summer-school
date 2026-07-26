# Power Markets - Trading and Hedging a Retail Electricity Portfolio

## Data Description

HTW Summer School Project  
Dr. Helio Quintanilha Jr.  
Sourcing and Hedging Specialist  
Ostrom GmbH  
helio@ostrom.de

You have joined the power-trading team of a retail electricity supplier. Before the team decides how to hedge its 2024 customer portfolio, your manager asks you to understand the customer book and the available market data.

## 1. The data on your desk

The following files have been provided by your team:


| File                        | What it contains                                               | Main fields                                   |
| --------------------------- | -------------------------------------------------------------- | --------------------------------------------- |
| `slp_profiles.csv`          | Berlin HB, GB, and LB standard load profiles                   | normalized kWh by quarter-hour                |
| `futures_prices.csv`        | 2024 Base and Peak futures snapshot dated 29 September 2023    | delivery period, price, market activity       |
| `shape_factors.csv`         | Historical price shape derived from 2019-2022 Day-Ahead prices | month, hour, weekday, Peak flag, shape factor |
| `day_ahead_prices.csv`      | Realised 2024 German/Luxembourg Day-Ahead prices               | EUR/MWh                                       |
| `actual_portfolio_load.csv` | Realised 2024 consumption of the three customer groups         | MWh by quarter-hour                           |
| `imbalance_prices.csv`      | Realised 2024 German reBAP                                     | EUR/MWh                                       |
| `data_dictionary.csv`       | Field definitions and data origin                              | file, field, description                      |
| `sources.csv`               | Public sources used in the project                             | dataset, publisher, URL                       |


Note: The futures snapshot and actual customer load were constructed for this scenario. The load profiles and realised market prices come from public sources, while the historical shape factors are derived from public Day-Ahead data.

### Reading the time series

- `timestamp_utc` is the common time key.
- `timestamp_local` shows Europe/Berlin time and should be used to interpret daily and weekly patterns.
- The load, shape-factor, actual-load, and imbalance series contain 35,136 quarter-hours.
- Day-Ahead prices are hourly values repeated over the corresponding four quarter-hours.
- Energy volumes are measured in MWh and futures positions will later be measured in MW.
- Prices are measured in EUR/MWh.
- For the project, Peak means Monday-Friday from 08:00 to 20:00 local time.

The timestamp columns already represent the spring and autumn clock changes. Note anything unusual you observe, but no additional daylight-saving adjustment is required for this initial analysis.

## 2. Your customer portfolio

Your company supplies the following customers:


| Profile | Customer type      | Customers | Annual consumption per customer |
| ------- | ------------------ | --------- | ------------------------------- |
| HB      | Household          | 10,000    | 3.5 MWh                         |
| GB      | General commercial | 200       | 30.0 MWh                        |
| LB      | Agriculture        | 20        | 100.0 MWh                       |


Stromnetz Berlin provides a standardized quarter-hourly load profile for each customer type. These profiles describe how annual consumption is distributed over time. As part of your analysis, you will inspect their units and annual totals and determine how to scale them to the customer portfolio above.

## 3. Your manager's briefing

Before the team begins the HPFC construction and hedge optimization, prepare a short data briefing containing four exhibits. Each exhibit should combine a clear visual with a concise economic interpretation.

### Exhibit 1 - Customer portfolio

**Inputs:** the customer table in Section 2 and `slp_profiles.csv`

**Hint:** First calculate the annual MWh required for each customer group and compare it with the annual sum of the corresponding normalized SLP. Use this relationship to find one scaling factor for all quarter-hours of that profile.

Show:

- annual energy and percentage share by customer group;
- average daily HB, GB, and LB shapes; and
- a comparison of weekday and weekend consumption.

Explain how you scaled the standard profiles, show that the annual portfolio energy reconciles with the customer assumptions, and describe how the customer mix influences the supplier's total load shape.

### Exhibit 2 - Futures market

**File:** `futures_prices.csv`

The file contains Year, Quarter, and Month products. Base covers every hour of its delivery period; Peak covers only the defined weekday Peak hours. `market_activity` is a simplified indicator of tradability. Consider how this information should influence which products may be included in a hedge.

Plot Base and Peak prices by delivery period together with `market_activity`.

Identify:

- a suitable `market_activity` criterion and explain your choice;
- the products that appear usable;
- the products that appear illiquid;
- the non-overlapping ways of covering 2024 with CAL, Q1-Q4, or M01-M03 followed by Q2-Q4; and
- any visible seasonal pattern in the futures prices.

Conclude which products the trading desk could use for a coarse and a more granular hedge. Explain why overlapping annual, quarterly, and monthly full-volume positions would not be an appropriate comparison.

### Exhibit 3 - Historical price shape

**File:** `shape_factors.csv`

The `historical_shape_factor` describes how prices varied by month, hour, and weekday in 2019-2022. It has an annual average close to one and is a relative shape rather than a price. Produce a month-hour heatmap, using a suitable aggregation if weekday and weekend patterns need to be shown separately.

Interpret:

- what values above and below one mean;
- the hours and seasons with high and low factors;
- the relationship between the shape and the Peak definition;
- differences between weekdays and weekends; and
- how a relative shape factor could help transform block futures into an hourly curve.

Conclude what information the historical shape adds to the average futures quotes.

### Exhibit 4 - Realised market prices

**Files:** `day_ahead_prices.csv` and `imbalance_prices.csv`

Compare the 2024 Day-Ahead and reBAP prices using a time-series plot and a distributional view such as a box plot, histogram, or quantile table.

Identify:

- extreme positive and negative prices;
- periods of elevated volatility;
- whether reBAP appears more variable than Day-Ahead; and
- one market episode that deserves further investigation in the main project.



### Close the briefing

End with short answers to three questions:

1. Which information was available when the hedge was designed on 29 September 2023, and which became known only during delivery?
2. What data checks did you perform before trusting the analysis?
3. If the strategy were executed for a real retail portfolio, what important information or market features would still be missing?

For the final question, identify at least three assumptions or simplifications and explain how each could affect the analysis.

## 4. Sources and use

The source organisations and links are provided in `sources.csv`. The principal sources are Stromnetz Berlin for the standard load profiles, Bundesnetzagentur SMARD for Day-Ahead prices, and Netztransparenz for reBAP.
