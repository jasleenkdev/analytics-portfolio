# Memo: retention, range and waste, full year

**To:** Category and growth teams  **From:** Analytics  **Data:** simulated (seeded generator, not real company data)

**Bottom line.** 76,479 customers placed a first order this year; 67.0% ordered again within 90 days. Retention is driven by acquisition channel and, above all, by whether the first order goes right. A payment fault in android app 5.4 has been costing orders since 2025-08-18. On the range side, a handful of high-margin SKUs are badly under-ranged and perishable overstock at a few node-categories accounts for a large share of waste.

### 1. Protect the first order
Customers whose first order had a problem are 7.4 points less likely to come back within 90 days (95% CI 6.1 to 8.6), the largest single driver in the model. Channel matters too: paid_social customers repeat 5.7 points less than organic, referral customers 2.1 points more.
**Action:** route first orders to the most reliable pick and dispatch slots and issue an automatic credit when a first order goes wrong (test it as an experiment); weight acquisition budget by 90-day repeat, not by first-order cost alone.

### 2. Fix payments on android 5.4
Payment success on that version is 71.7% against 93.0% for every other platform and version (all other funnel steps are normal). The platform's success rate went from 92.8% before the release to 71.6% once adopted. That is about 14,963 lost orders, roughly 534,631 in basket value, plus weaker retention for the customers affected.
**Action:** escalate to the app team as a release regression; until fixed, offer a fallback payment method in that version.

### 3. Give the under-ranged premium SKUs more space
6 `premium_deli` SKUs with about 52% margin are ranged at only 2 nodes, so they look mid-table at network level (class B), yet where ranged they sell faster than the median SKU. Across all 86 add recommendations, the expected gain is 141,646 to 220,398 a year in gross margin (low end assumes 30% cannibalisation and the weakest node's result).
**Action:** range them at the remaining nodes in a staged roll-out and measure against untouched nodes.

### 4. Cut depth where perishables outlive their shelf life
Perishable waste cost 284,290 (10.2% of units received). 107 node-SKUs carry more days of cover than their shelf life while selling at least 1 unit a day; they wasted 106,027, led by ready_meals at N02. Cutting cover to 50% of shelf life saves an estimated 53,013 to 95,424 a year.
**Action:** lower order-up-to levels for these node-SKUs (the workbook lists the recommended stock per node-SKU) and review weekly waste.

### Also worth acting on
- **Champions** are 20% of customers but 42% of margin; **at-risk** customers (good history, not seen recently) hold 25% of margin and are the win-back target.
- 6 product pairs are bought together far more than chance (lift 5.8 to 28.2): place them together and use them for bundles. The drop list (299 slow, low-margin, class C node-SKUs) frees space for the adds above at a small margin cost.

**Caveats.** Impact ranges rest on stated substitution and cannibalisation assumptions (config), not on a measured ranging test; retention effects are associations from a model and should be confirmed by experiment before large spend.

## Appendix: recommendations by node (annual, currency units)
Drop columns are the net annual margin change after waste avoided (negative = margin given up).

| node_id | add_skus | add_low | add_high | reduce_skus | waste_saved_low | waste_saved_high | drop_skus | drop_net_low | drop_net_high |
|---|---|---|---|---|---|---|---|---|---|
| N01 | 8 | 10,214 | 16,882 | 14 | 3,093 | 5,568 | 37 | -515 | 893 |
| N02 | 12 | 26,707 | 41,325 | 22 | 23,188 | 41,738 | 38 | -1,479 | 220 |
| N03 | 14 | 16,067 | 25,219 | 12 | 2,270 | 4,087 | 37 | -222 | 923 |
| N04 | 12 | 20,434 | 31,274 | 7 | 1,428 | 2,571 | 38 | -1,392 | 252 |
| N05 | 6 | 3,808 | 6,980 | 9 | 1,798 | 3,236 | 37 | -392 | 728 |
| N06 | 11 | 23,225 | 35,717 | 18 | 16,152 | 29,074 | 37 | -1,147 | 197 |
| N07 | 14 | 26,608 | 40,802 | 14 | 2,694 | 4,850 | 37 | -3,018 | -940 |
| N08 | 9 | 14,584 | 22,198 | 11 | 2,389 | 4,301 | 38 | -611 | 666 |
