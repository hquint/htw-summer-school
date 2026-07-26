# Power Markets - Trading and Hedging a Retail Electricity Portfolio

## Main Project Brief

HTW Summer School Project  
Dr. Helio Quintanilha Jr.  
Sourcing and Hedging Specialist  
Ostrom GmbH  
helio@ostrom.de

## Variable glossary

The notation below is used throughout the project. Unless stated otherwise, interval energy volumes refer to one quarter-hour.

| Symbol(s) | Meaning | Unit |
| --------- | ------- | ---- |
| *p*, *t*, *τ*, *j*, *b* | customer profile, delivery interval, summation interval, futures product, and non-overlapping optimization block | index |
| *E_p*, *n_p*, *e_p* | annual portfolio energy for profile *p*, customer count, and annual energy per customer | MWh, count, MWh |
| *s_p,t*, *L_p,t*, *L_t* | normalized load-profile value, forecast load for profile *p*, and total forecast load | profile unit, MWh, MWh |
| *P_base*, *P_peak*, *P_off*, *P_slice* | Base, Peak, implied Off-Peak, and applicable slice price | EUR/MWh |
| *N_all*, *N_peak*, *N_off* | number of all, Peak, and Off-Peak quarter-hours in a delivery period | intervals |
| *s_t*, *mean_slice(s)*, *HPFC_t* | historical price-shape factor, its mean within a slice, and the hourly price forward curve value | factor, factor, EUR/MWh |
| *Δt*, *x_j*, *D_j,t*, *H_t* | interval duration, futures position, delivery indicator, and hedge energy | hours, MW, 0 or 1, MWh |
| *R_t^DA*, *P_t^DA* | residual forecast volume settled Day-Ahead and realised Day-Ahead price | MWh, EUR/MWh |
| *A_t*, *I_t*, *P_t^imb* | actual load, imbalance volume, and realised imbalance price | MWh, MWh, EUR/MWh |
| *C_futures*, *C_forecast* | fixed futures cost and total cost of procuring the forecast position | EUR |
| *C_residual^DA*, *C_imb*, *C_final* | Day-Ahead residual cost, imbalance settlement, and final procurement cost | EUR |
| *Π_futures*, *Premium_imb*, *Saving* | financial futures payoff, imbalance premium, and saving relative to the unhedged benchmark | EUR |

## 1. The management decision

You have completed your first review of the customer and market data. Your manager now asks you to recommend a procurement strategy for the company's 2024 customer portfolio using the futures products available on 29 September 2023.

The recommendation should protect the company against adverse wholesale-price movements while keeping the hedge reasonably close to the shape of the expected customer load. It should be evaluated as a risk-management decision, not as a speculative trade.

Standard Base and Peak futures can fix the price of broad delivery blocks, but the customer load is neither flat nor perfectly known. The company therefore faces:

- **shape risk**, because the futures do not exactly match the forecast load; and
- **volume risk**, because actual customer consumption can differ from the forecast.

The procurement process is represented in three stages:

```text
Futures hedge
    covers part of the forecast load at agreed futures prices

Day-Ahead shaping
    buys or sells the forecast volume not matched by the futures

Imbalance settlement
    settles actual consumption minus the Day-Ahead schedule
```

Your work should show how the cost and risk change as each stage is added.

## 2. Strategies to evaluate

Compare three strategies:


| Strategy     | Futures universe                                                                            |
| ------------ | ------------------------------------------------------------------------------------------- |
| `UNHEDGED`   | No futures                                                                                  |
| `COARSE_CAL` | Eligible annual Base and Peak products                                                      |
| `GRANULAR`   | The finest non-overlapping combination of eligible Month and Quarter Base and Peak products |


Selecting the futures is part of the task. Use the `market_activity` criterion developed in your data briefing, justify which products are tradable, and demonstrate that each hedge covers 2024 without overlapping delivery periods.

Futures positions are continuous MW and must be non-negative. Transaction costs, bid-ask spreads, and integer contract lots are not modelled.

## 3. Stage 1 - Forecast the customer portfolio

**Inputs:** the customer table in the Data Description and `slp_profiles.csv`

Construct the quarter-hourly forecast load of each customer group and the total portfolio.

For profile p, let E_p be annual portfolio energy, n_p the number of customers, and e_p annual consumption per customer:

```text
annual_portfolio_energy[p]
    = customer_count[p] * annual_mwh_per_customer[p]
```

Let s_p,t denote the supplied normalized profile value at quarter-hour t. Scale the corresponding standard load profile:

```text
forecast_load[p,t]
    = annual_portfolio_energy[p]
      * normalized_profile[p,t]
      / sum(normalized_profile[p])
```

Then calculate:

```text
total_forecast_load[t]
    = sum over profiles of forecast_load[p,t]
```

Reconcile the resulting annual energy with the customer table and distinguish correctly between quarter-hourly MWh and average MW.

Explain how the customer mix affects the daily and seasonal load shape and the potential use of Base and Peak futures.

## 4. Stage 2 - Construct the HPFC

**Inputs:** `futures_prices.csv` and `shape_factors.csv`

Your manager needs an hourly valuation of the portfolio, but the futures market provides only average prices for broad delivery blocks. Construct a simplified Hourly Price Forward Curve (HPFC), represented on the project's quarter-hourly grid, using the eligible non-overlapping products selected for the granular strategy.

### 4.1 Infer the Off-Peak price

For each selected delivery period, the Base future gives the average price across all intervals, while the Peak future gives the average across only the Peak intervals. To shape Peak and Off-Peak hours separately without changing the quoted Base value, the prices must satisfy:

```text
P_base * N_all
    = P_peak * N_peak + P_off * N_off
```

Rearranging this identity gives the implied Off-Peak price:

```text
P_off
    = (P_base * N_all - P_peak * N_peak)
      / N_off
```

where `N_all`, `N_peak`, and `N_off` are the numbers of all, Peak, and Off-Peak quarter-hours in the applicable delivery period.

### 4.2 Apply the historical price shape

Within Peak and Off-Peak separately, write s_t for the supplied historical shape factor and rescale it:

```text
HPFC[t]
    = P_slice
      * historical_shape_factor[t]
      / mean(historical_shape_factor within the slice)
```

`P_slice` is either the quoted Peak price or the implied Off-Peak price.

### 4.3 Reconcile the curve

For every calibration period, verify that:

- the mean HPFC across Peak intervals equals the quoted Peak future; and
- the mean HPFC across all intervals equals the quoted Base future.

Use eligible products that were not used to build the HPFC as independent reconciliation checks. This tests whether the curve is also consistent with coarser or overlapping market information. Small differences caused by quotes rounded to cents are acceptable.

Conclude this stage by explaining why a contract-consistent HPFC is useful for valuation but is not a forecast of realised Day-Ahead prices.

## 5. Stage 3 - Optimize the futures hedge

**Inputs:** the forecast portfolio, completed HPFC, and `futures_prices.csv`

Let x_j be the MW position in futures product j. Construct the energy represented by the hedge in every quarter-hour:

```text
hedge_energy[t]
    = 0.25 * sum over products j
      of position_mw[j] * delivery_indicator[j,t]
```

A Base product delivers in every interval of its delivery period. A Peak product delivers only in the defined Peak intervals.

### 5.1 Economic constraint - value neutrality

Within each non-overlapping optimization period b, require:

```text
sum over t in b of hedge_energy[t] * HPFC[t]
    =
sum over t in b of forecast_load[t] * HPFC[t]
```

Apply the constraint to each non-overlapping delivery block in the selected strategy. The coarse hedge therefore has one annual value constraint, while the granular hedge has one constraint for each selected Month or Quarter block.

### 5.2 Minimize the shape mismatch

Among the positions satisfying value neutrality, solve:

```text
minimize
    sum over t of
    (forecast_load[t] - hedge_energy[t])^2
```

subject to:

```text
position_mw[j] >= 0
```



### 5.3 Check the hedge

For each strategy, report:

- futures positions in MW;
- hedge notional energy in MWh;
- hedge and forecast values under the HPFC;
- value-neutrality error;
- residual-load RMSE; and
- absolute residual Day-Ahead volume.

Explain why value neutrality does not necessarily produce volume neutrality, and assess which price and shape risks remain after optimization.

## 6. Stage 4 - Shape the forecast position Day-Ahead

**Input:** `day_ahead_prices.csv`

The futures are financial contracts and do not change the physical customer schedule. The company schedules its forecast load Day-Ahead, while the part not covered economically by the futures remains exposed to the Day-Ahead price:

```text
day_ahead_residual[t]
    = forecast_load[t] - hedge_energy[t]
```

Calculate the cost of the forecast position:

```text
forecast procurement cost
    = fixed futures cost
      + sum(day_ahead_residual[t] * day_ahead_price[t])
```

Validate the result through the equivalent financial representation:

```text
forecast procurement cost
    = full forecast load purchased Day-Ahead
      - financial futures payoff
```

For `UNHEDGED`, `hedge_energy[t]` is zero and the complete forecast load remains exposed to Day-Ahead prices.

Reconcile the two cost representations. Interpret both signs of `day_ahead_residual`: what action is required when it is positive, and how should a negative value be handled?

## 7. Stage 5 - Settle the volume deviation

**Inputs:** `actual_portfolio_load.csv` and `imbalance_prices.csv`

During delivery, actual consumption differs from the Day-Ahead schedule. Calculate:

```text
imbalance_volume[t]
    = actual_load[t] - forecast_load[t]
```

The imbalance settlement is:

```text
imbalance settlement
    = sum(imbalance_volume[t] * imbalance_price[t])
```

Final procurement cost becomes:

```text
final procurement cost
    = fixed futures cost
      + Day-Ahead residual cost
      + imbalance settlement
```

Also isolate the price consequence of being imbalanced:

```text
imbalance premium
    = sum(
        imbalance_volume[t]
        * (imbalance_price[t] - day_ahead_price[t])
      )
```

Interpret positive and negative `imbalance_volume` and the corresponding settlement cashflow. The Day-Ahead schedule is the same forecast portfolio under all three strategies; show what this implies for imbalance settlement and explain which risk the futures hedge does not remove.

## 8. Stage 6 - Advise management

Compare the strategies using at least:


| Measure                                              | Purpose                       |
| ---------------------------------------------------- | ----------------------------- |
| Final annual procurement cost                        | Total economic outcome        |
| Final average price in EUR/MWh of actual load        | Comparable unit cost          |
| Saving versus unhedged                               | Procurement P&L benchmark     |
| Monthly average procurement-price standard deviation | Descriptive cost stability    |
| Monthly price range                                  | Exposure to seasonal extremes |
| Absolute residual Day-Ahead volume                   | Remaining spot exposure       |
| Residual-load RMSE                                   | Hedge shape quality           |
| Imbalance settlement and premium                     | Cost of forecast error        |


Define procurement P&L relative to the unhedged benchmark:

```text
saving versus unhedged
    = unhedged final cost - strategy final cost
```

A positive value indicates a lower realised procurement cost. It is a backtest result, not evidence that the hedge was designed as a speculative profit strategy.

Recommend one strategy to management. Support the recommendation with both cost and risk evidence; the strategy with the lowest realised annual cost is not automatically the best hedge.

## 9. Stage 7 - Interpret a severe price event

Identify a relevant high-price day or interval in the 2024 Day-Ahead data. 

Use the selected event and the results already produced to show the Day-Ahead price, customer load, hedge, and residual exposure. Compare how the three strategies were exposed and explain how the event affected procurement cost.

This is primarily an interpretation exercise, not a new optimization or simulation task. A simple sensitivity showing what would happen if the high prices were larger or lasted longer may be used to support the discussion, but it is not required.

Conclude the event analysis by answering: **If the company had not hedged, how could an extreme spot-price event affect its liquidity and ability to continue serving customers? Which risks would remain even with the hedge?**

Avoid assuming that one expensive day automatically causes bankruptcy. Base the conclusion on the size and duration of the exposure and the protection provided by each strategy.

## 10. Optional extensions



### Price the customer product

Your manager now asks what fixed energy price the company should offer its customers. Develop a transparent pricing approach using only information that would have been available when the offer was made.

Decide which cost and risk components should enter the price, state any additional assumptions or information you require, and explain how the selected hedge affects the result. Clearly separate an ex-ante price from conclusions that rely on realised 2024 data.

### Test another hedge design

As a separate extension, you may:

- construct a `QUARTER_ONLY` hedge using Q1-Q4 Base and Peak;
- propose another non-overlapping product set; or
- add one realistic trading constraint and discuss its effect.



## 11. Deliverables and evidence

Each team must submit:

1. a reproducible notebook, script, or workbook; and
2. a 10-15 minute presentation communicating the method, evidence, and management recommendation.

The analysis and presentation must include:

- an HPFC reconciliation table;
- a futures-position table;
- a final cost-and-risk comparison table;
- the customer portfolio shape and composition;
- the HPFC shape and contract-reconciliation evidence;
- the forecast load, hedge shape, and residual exposure;
- a monthly procurement cost or price comparison; and
- the selected severe-price-event analysis.

Teams are free to choose the presentation structure, number of slides, chart types, and any additional evidence.

## 12. Assessment guidance


| Area                                           | Weight |
| ---------------------------------------------- | ------ |
| Data preparation and portfolio validation      | 20%    |
| HPFC and hedge-optimization correctness        | 25%    |
| Day-Ahead and imbalance accounting             | 20%    |
| Economic interpretation and risk understanding | 20%    |
| Communication and independent insight          | 15%    |


Strong submissions will reproduce the required accounting and optimization correctly, identify limitations without losing sight of the simplified model, and make a clear commercial recommendation supported by evidence.

## 13. Assumptions and limitations

Return to the assumptions identified in your initial data briefing. Select at least three and explain how they could affect the hedge, the procurement result, or the management recommendation. Where possible, describe the likely direction of the effect.
