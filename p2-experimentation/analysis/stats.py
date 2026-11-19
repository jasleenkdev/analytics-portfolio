"""Statistical building blocks for the experiment and pilot readouts. Pure functions, unit-tested."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import NormalIndPower


def srm_test(n_control: int, n_treatment: int, expected_share: float = 0.5) -> float:
    """Chi-square goodness-of-fit p-value for the observed split against the designed split."""
    total = n_control + n_treatment
    return float(stats.chisquare([n_control, n_treatment], [total * (1 - expected_share), total * expected_share]).pvalue)


def welch_from_stats(m1, v1, n1, m0, v0, n0, alpha=0.05) -> dict:
    """Difference in means (treatment - control) with a Welch t confidence interval."""
    se = np.sqrt(v1 / n1 + v0 / n0)
    dof = se ** 4 / ((v1 / n1) ** 2 / (n1 - 1) + (v0 / n0) ** 2 / (n0 - 1))
    diff = m1 - m0
    t = diff / se
    half = stats.t.ppf(1 - alpha / 2, dof) * se
    return {"control_mean": m0, "treatment_mean": m1, "diff": diff, "se": se, "ci_low": diff - half,
            "ci_high": diff + half, "p_value": float(2 * stats.t.sf(abs(t), dof)),
            "rel_diff": diff / m0 if m0 else np.nan, "rel_ci_low": (diff - half) / m0 if m0 else np.nan,
            "rel_ci_high": (diff + half) / m0 if m0 else np.nan, "n_control": int(n0), "n_treatment": int(n1)}


def welch(y_t: np.ndarray, y_c: np.ndarray, alpha=0.05) -> dict:
    return welch_from_stats(np.mean(y_t), np.var(y_t, ddof=1), len(y_t), np.mean(y_c), np.var(y_c, ddof=1), len(y_c), alpha)


def cuped(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float, float]:
    """CUPED-adjusted outcome y - theta (x - mean x), theta pooled across arms; returns (y_adj, theta, variance reduction)."""
    theta = np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1)
    y_adj = y - theta * (x - x.mean())
    return y_adj, float(theta), float(1 - np.var(y_adj, ddof=1) / np.var(y, ddof=1))


def delta_ratio(mean_x, mean_y, var_x, var_y, cov_xy, n) -> tuple[float, float]:
    """Ratio of means and its delta-method variance (per-user numerator x and denominator y)."""
    r = mean_x / mean_y
    var = (var_x / mean_y ** 2 - 2 * mean_x * cov_xy / mean_y ** 3 + mean_x ** 2 * var_y / mean_y ** 4) / n
    return float(r), float(var)


def ratio_diff(t: dict, c: dict, alpha=0.05) -> dict:
    r1, v1 = delta_ratio(t["mean_x"], t["mean_y"], t["var_x"], t["var_y"], t["cov_xy"], t["n"])
    r0, v0 = delta_ratio(c["mean_x"], c["mean_y"], c["var_x"], c["var_y"], c["cov_xy"], c["n"])
    se = np.sqrt(v1 + v0)
    z = stats.norm.ppf(1 - alpha / 2)
    diff = r1 - r0
    return {"control_mean": r0, "treatment_mean": r1, "diff": diff, "se": se, "ci_low": diff - z * se,
            "ci_high": diff + z * se, "p_value": float(2 * stats.norm.sf(abs(diff / se))),
            "rel_diff": diff / r0, "rel_ci_low": (diff - z * se) / r0, "rel_ci_high": (diff + z * se) / r0,
            "n_control": int(c["n"]), "n_treatment": int(t["n"])}


def mde(sd: float, n_per_arm: float, alpha=0.05, power=0.8) -> float:
    """Minimum detectable absolute difference in means for a two-sided test with equal arms."""
    effect = NormalIndPower().solve_power(nobs1=n_per_arm, alpha=alpha, power=power, ratio=1.0)
    return float(effect * sd)


def n_for_effect(sd: float, abs_effect: float, alpha=0.05, power=0.8) -> float:
    return float(NormalIndPower().solve_power(effect_size=abs_effect / sd, alpha=alpha, power=power, ratio=1.0))


def holm(p_values: list[float], alpha=0.05, method="holm") -> tuple[np.ndarray, np.ndarray]:
    reject, p_adj, _, _ = multipletests(p_values, alpha=alpha, method=method)
    return reject, p_adj


def interaction_test(df: pd.DataFrame, y: str, dimension: str) -> float:
    """p-value of the joint test that the treatment effect is equal across levels of `dimension`."""
    model = smf.ols(f"{y} ~ C(variant) * C({dimension})", data=df).fit(cov_type="HC1")
    terms = [n for n in model.params.index if ":" in n]
    if not terms:
        return float("nan")
    r = np.zeros((len(terms), len(model.params)))
    for i, name in enumerate(terms):
        r[i, list(model.params.index).index(name)] = 1
    return float(model.wald_test(r, scalar=True).pvalue)


def did(panel: pd.DataFrame, metric: str, alpha=0.05) -> dict:
    """Two-way fixed-effects difference-in-differences with node-clustered standard errors."""
    d = panel.assign(treated_post=(panel.treated & panel.post).astype(float))
    res = smf.ols(f"{metric} ~ treated_post + C(node_id) + C(ops_date)", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.node_id)[0]})
    est, se = res.params["treated_post"], res.bse["treated_post"]
    lo, hi = res.conf_int(alpha).loc["treated_post"]
    base = d.loc[d.treated & ~d.post, metric].mean()
    return {"metric": metric, "estimate": float(est), "se": float(se), "ci_low": float(lo), "ci_high": float(hi),
            "p_value": float(res.pvalues["treated_post"]), "treated_baseline": float(base),
            "rel_estimate": float(est / base), "n_obs": int(res.nobs), "n_clusters": int(d.node_id.nunique())}


def event_study(panel: pd.DataFrame, metric: str, ref_week: int = -1) -> tuple[pd.DataFrame, float]:
    """Week-by-week treated-vs-control coefficients (relative to ref_week) and the joint pre-trend p-value."""
    d = panel.copy()
    weeks = sorted(w for w in d.rel_week.unique() if w != ref_week)
    names = {w: f"ev_{'m' if w < 0 else 'p'}{abs(w)}" for w in weeks}
    for w, name in names.items():
        d[name] = (d.treated & (d.rel_week == w)).astype(float)
    res = smf.ols(f"{metric} ~ {' + '.join(names.values())} + C(node_id) + C(ops_date)", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.node_id)[0]})
    ci = res.conf_int()
    coefs = pd.DataFrame([{"rel_week": w, "estimate": res.params[n], "ci_low": ci.loc[n, 0], "ci_high": ci.loc[n, 1]}
                          for w, n in names.items()] + [{"rel_week": ref_week, "estimate": 0.0, "ci_low": 0.0, "ci_high": 0.0}])
    pre = [n for w, n in names.items() if w < ref_week]
    r = np.zeros((len(pre), len(res.params)))
    for i, name in enumerate(pre):
        r[i, list(res.params.index).index(name)] = 1
    # F version with cluster degrees of freedom: the chi-square Wald over-rejects with ~24 clusters
    return coefs.sort_values("rel_week", ignore_index=True), float(res.wald_test(r, use_f=True, scalar=True).pvalue)


def pre_trend_slope(panel: pd.DataFrame, metric: str) -> dict:
    """Pre-period only: does the treated-minus-control gap drift linearly over time?"""
    pre = panel[~panel.post].assign(trend=lambda d: d.treated.astype(float) * d.rel_day)
    res = smf.ols(f"{metric} ~ trend + C(node_id) + C(ops_date)", data=pre).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(pre.node_id)[0]})
    return {"slope_per_day": float(res.params["trend"]), "p_value": float(res.pvalues["trend"])}


def placebo(panel: pd.DataFrame, metric: str, offset_days: int) -> dict:
    """DiD on pre-period data only, pretending treatment started offset_days before the real start."""
    pre = panel[~panel.post].copy()
    pre["post"] = pre.rel_day >= -offset_days
    return did(pre, metric)
