# Ground truth: planted effects in the project 3 generator

Rendered from `data_gen/plants.toml` and `data/planted_entities.json` by the generator. The analysis never reads either; they are used only by the final found-vs-planted cross-check.

Window: 2025-01-01 for 365 days; 80000 customers; 8 nodes; 420 SKUs.

1. **Checkout funnel drop-off.** From day 229 (2025-08-18) android users move to app version 5.4 over 14 days; on that version payment success falls from 93% to 72%. Failed payments end the session without an order. Other platforms and steps are unchanged. Expected signature: the payment-attempt to order step drops for android 5.4 only, from that date.
2. **Retention drivers.** Monthly churn hazard 0.17 multiplied by acquisition channel (referral x0.6, organic x0.85, paid_search x1.0, paid_social x1.5, partner x1.2) and by x1.8 when the first order had a problem (missing item or late, 10% of first orders). Expected signature: referral retains best and paid social worst; customers with a bad first order retain markedly worse.
3. **Basket affinities.** 6 SKU pairs where the partner joins 45% of baskets containing the anchor: S005 -> S082, S374 -> S391, S365 -> S410, S372 -> S262, S390 -> S114, S158 -> S217. Expected signature: these pairs top the lift ranking among frequent pairs.
4. **Perishable overstock and wastage.** At N02, N06, the 7 fastest bakery / ready_meals SKUs are replenished to 1.8x their shelf life (others: up to 2 days or half the shelf life). Node-SKUs: N02/S081, N02/S093, N02/S129, N02/S130, N02/S139, N02/S149, N02/S150, N06/S081, N06/S093, N06/S129, N06/S130, N06/S136, N06/S139, N06/S149. Expected signature: days of cover above shelf life, top waste cost; recommendation to reduce depth.
5. **High-margin, under-ranged SKUs.** 6 `premium_deli` SKUs (S399, S400, S401, S402, S403, S404) carry a 52% margin and are ranged only at N01, N05, where they sell like top-15% SKUs. Expected signature: low network velocity (C class) but strong per-ranged-node velocity and margin; recommendation to add them at other nodes.

## Generator assumptions that are not planted
- Signups grow linearly through the year; channel, platform and home node drawn independently.
- Order rate while active is gamma-distributed (mean about 0.95 orders per 30 days); the first order happens at signup.
- Baskets: 1 + Poisson(4.8) lines, 55% from a personal repertoire of 12 favourite SKUs, the rest by popularity within the home node's range.
- Non-buying sessions (1.4 per intended order) stop at visit, browse, cart or checkout.
- Daily order-up-to replenishment; perishables age in FIFO buckets and are written off after their shelf life; ambient goods hold 4 days of cover.
