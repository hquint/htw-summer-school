# Power Markets - Trading and Hedging a Retail Electricity Portfolio

## Instructor Questions and Suggested Answers

Instructor-only draft

## How to use these notes

The questions below can be used during or after the team presentations. The suggested answers identify the main ideas to listen for; students may use different wording or reach a different recommendation if it is supported by correct analysis.

## Core presentation questions

### 1. What information was known when the hedge was designed?

The portfolio assumptions, Berlin standard load profiles, historical 2019-2022 price shape, and futures snapshot were available on the assumed hedge date of 29 September 2023. The realised 2024 Day-Ahead prices, actual customer load, and reBAP were known only during or after delivery and must not influence the ex-ante hedge.

### 2. Why did you exclude the illiquid products?

A hedge must be executable. A quoted price is not sufficient if there is little market activity and the desired volume cannot be traded without a large price impact. Students should use `market_activity` to establish a defensible rule. In this dataset, the deliberately illiquid later monthly products have values from 1 to 10, while the intended tradable products are above 100.

### 3. Why did you avoid overlapping annual, quarterly, and monthly coverage?

CAL, Quarter, and Month products are alternative ways to cover the same delivery periods. Combining them at full portfolio volume would count the exposure more than once. Overlapping products could be used in a more sophisticated joint optimization, but their net delivery and purpose would need to be modelled explicitly.

### 4. Is the HPFC a forecast?

No. It is a contract-consistent valuation curve that distributes the average futures prices across time using a historical shape. It reproduces the Base and Peak futures values but does not predict weather, outages, renewable generation, or price shocks during 2024.

### 5. Why constrain the hedge by value rather than annual volume?

One MWh at a high-price hour is economically different from one MWh at a low-price hour. Value neutrality makes the forecast portfolio and hedge equal when measured with the HPFC and prevents the optimization from creating a systematic value bias merely to improve the physical shape fit.

### 6. How can the hedge be value-neutral but not volume-neutral?

The optimizer can slightly overhedge lower-value hours and underhedge higher-value hours, or the reverse, while preserving the same total HPFC value. Standard Base and Peak blocks cannot reproduce every quarter-hour of the customer profile, so equal value does not imply equal annual MWh.

### 7. Why is imbalance settlement the same for all strategies?

All three strategies use the same customer forecast as their Day-Ahead schedule. They therefore have the same actual-minus-forecast deviation and face the same reBAP. The futures hedge changes the price exposure of the forecast volume; it does not change the physical forecast error.

### 8. Which strategy reduced cost volatility most effectively?

In the locked backtest, `COARSE_CAL` has the lowest standard deviation of monthly procurement prices: approximately EUR 2.43/MWh, compared with EUR 18.56/MWh for `GRANULAR` and EUR 20.15/MWh for `UNHEDGED`. The annual CAL hedge fixes a similar price level across the whole year, whereas the granular hedge retains differences between monthly and quarterly forward prices.

The granular hedge nevertheless has the better physical shape fit and slightly higher forecast-shaping coverage. Students should recognize this trade-off rather than assume that greater product granularity improves every risk measure.

### 9. Would you recommend a hedge if it produced a small realised loss?

Potentially, yes. A hedge can be successful if it reduces exposure to adverse prices and keeps costs within the company's risk tolerance, even when the realised spot market makes the unhedged alternative cheaper in hindsight. The realised difference can be understood as the ex-post cost of protection.

### 10. Which modelling simplification matters most?

There is no single required answer. Strong answers explain the mechanism. Examples include contract lots and transaction costs affecting executability, forecast updates and intraday trading reducing imbalance, or collateral and liquidity requirements changing the company's ability to maintain futures positions.

## Additional diagnostic questions

### 11. Where does the implied Off-Peak formula come from?

The Base price is the interval-weighted average of Peak and Off-Peak prices:

```text
P_base * N_all
    = P_peak * N_peak + P_off * N_off
```

Rearranging gives the Off-Peak formula used in the project.

### 12. Why should the two procurement-cost representations agree?

Buying the forecast residual at Day-Ahead after paying the fixed futures price is algebraically equivalent to buying the full forecast load Day-Ahead and subtracting the long futures payoff. A difference between the two calculations normally indicates inconsistent delivery hours, MW-to-MWh conversion, or payoff signs.

### 13. Does the futures hedge remove customer volume risk?

No. The hedge is designed against the forecast load. Actual-minus-forecast consumption remains exposed to reBAP. Intraday reforecasting and trading could reduce this exposure, but those steps are outside the simplified model.

### 14. Why can a negative Day-Ahead residual be valid?

The value-neutral futures combination may physically overhedge some intervals. The company then sells the excess forecast position Day-Ahead. A negative residual is not automatically an error; it should be interpreted together with the value-neutrality and non-negativity constraints.

### 15. What should happen during an extreme positive Day-Ahead price shock?

The unhedged strategy remains exposed for the complete forecast load. A hedged strategy is exposed only through its residual shape, so its event-period cost should react much less. Neither hedge removes imbalance risk, and overhedged intervals may produce gains when excess energy is sold at the higher price.

### 16. What should students consider when pricing the customer product?

They should begin with an ex-ante view of procurement cost and decide which additional costs and risks the offered price must cover. Strong answers distinguish expected cost from realised backtest cost, explain how residual risk is treated, and identify information that the project does not supply. There is no single required pricing formula.

## Numerical checkpoints for the locked case

These values are instructor checks and should not be distributed with the student brief:

| Check | Expected result |
| --- | ---: |
| Forecast portfolio energy | 43,000 MWh |
| Actual portfolio energy | 43,138 MWh |
| Portfolio normalized absolute forecast error | 1.97% |
| Imbalance settlement, all strategies | EUR 30,503.84 |
| Imbalance premium versus Day-Ahead | EUR 13,589.24 |
| Unhedged final average price | EUR 81.997/MWh |
| Coarse final average price | EUR 80.705/MWh |
| Granular final average price | EUR 80.718/MWh |
| Coarse saving versus unhedged | EUR 55,737 |
| Granular saving versus unhedged | EUR 55,197 |
| Coarse monthly-price standard deviation | EUR 2.43/MWh |
| Granular monthly-price standard deviation | EUR 18.56/MWh |
| Unhedged monthly-price standard deviation | EUR 20.15/MWh |
| Coarse forecast-shaping coverage | 70.3% |
| Granular forecast-shaping coverage | 72.1% |

Small differences caused by display rounding are acceptable.
