"""Statistical Excel functions for the pycel formula engine (pycel does not ship them)."""
from scipy import stats


def norm_s_inv(p):
    return float(stats.norm.ppf(p))


def norm_s_dist(x, cumulative=True):
    return float(stats.norm.cdf(x) if cumulative else stats.norm.pdf(x))


def chisq_dist_rt(x, df):
    return float(stats.chi2.sf(x, df))
