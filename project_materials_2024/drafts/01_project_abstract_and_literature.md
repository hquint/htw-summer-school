# Power Markets - Trading and Hedging a Retail Electricity Portfolio

HTW Summer School Project  
Dr. Helio Quintanilha Jr.  
Sourcing and Hedging Specialist  
Ostrom GmbH  
helio@ostrom.de

## Abstract

In this project, participants will take the role of an energy portfolio analyst working for a retail electricity supplier. Starting from a set of futures prices and historical load and market information, participants will construct a simplified Hourly Price Forward Curve (HPFC) representing the market value of future electricity across the hours of 2024. They will then analyse the consumption profile of a mixed portfolio of residential, commercial, and agricultural customers and investigate how electricity demand varies across hours, days, and seasons.

Using only standard Base and Peak futures products, participants will design and optimize a hedging strategy for the customer portfolio. They will compare a coarse annual hedge with a more granular hedge based on non-overlapping monthly and quarterly products.

Finally, participants will assess the economic impact of their strategy using realised 2024 Day-Ahead and imbalance prices. They will calculate the resulting procurement costs and profit-and-loss (P&L), compare the hedged strategies with an unhedged benchmark, and evaluate both realised cost and cost stability.

## Project activities

Participants will:

- construct and analyse a portfolio based on Berlin standard load profiles;
- build and validate an HPFC from Base and Peak futures and historical price shapes;
- formulate a value-neutral hedge optimization using liquid futures products;
- distinguish between futures hedging, Day-Ahead shaping, and imbalance settlement; and
- present a commercial recommendation supported by cost and risk analysis.



## Selected literature and market references

[European Energy Exchange (EEX), *German Power Markets*.](https://www.eex.com/en/markets/power/german-power-markets)

[Fleten, S.-E. and Lemming, J. (2003), *Constructing forward price curves in electricity markets*, *Energy Economics*, 25(5), 409-424.](https://doi.org/10.1016/S0140-9883%2803%2900039-2)

[Oum, Y., Oren, S. S. and Deng, S. (2006), *Hedging quantity risks with standard power options in a competitive wholesale electricity market*, *Naval Research Logistics*, 53(7), 697-712.](https://oren.ieor.berkeley.edu/pubs/nrl_yumi_revision%20%2824%29.pdf)

[Bundesnetzagentur, *SMARD electricity-market data*.](https://www.smard.de/en/all-about-our-data-download-section-210130)

[German transmission system operators, *reBAP imbalance price*.](https://www.netztransparenz.de/de-de/Regelenergie/Ausgleichsenergiepreis/reBAP)

[Stromnetz Berlin, *Standard load profiles*.](https://www.stromnetz.berlin/en/grid-users/standard-load-profiles)

## Prerequisites

Participants should be comfortable working with tabular data, plotting time series, and interpreting basic optimization results. The project can be completed in Python, R, Excel, or another suitable analytical environment. Previous experience with electricity trading is helpful but not required.

**Disclaimer:** This project is a simplified educational exercise. The supplied case includes constructed scenario assumptions and does not represent an executable historical trading strategy or financial, trading, or risk-management advice.
