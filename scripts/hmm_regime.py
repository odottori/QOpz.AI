from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# HMM for continuous observations with diagonal Gaussian emissions.
# Pure-Python, deterministic (no external deps), designed for small/medium sequences.

EPS = 1e-12


def _logsumexp(vals: list[float]) -> float:
    m = max(vals)
    if m == -math.inf:
        return -math.inf
    s = sum(math.exp(v - m) for v in vals)
    return m + math.log(max(s, EPS))


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class HMMFitResult:
    converged: bool
    n_iter: int
    loglik: float
    transition: list[list[float]]
    means: list[list[float]]
    vars: list[list[float]]


class GaussianHMM:
    def __init__(self, n_states: int = 3, seed: int = 1337):
        if n_states < 2:
            raise ValueError("n_states must be >=2")
        self.n_states = n_states
        self.seed = seed
        self.pi: list[float] = [1.0 / n_states] * n_states
        self.A: list[list[float]] = [[1.0 / n_states] * n_states for _ in range(n_states)]
        self.means: list[list[float]] = []
        self.vars: list[list[float]] = []

    @staticmethod
    def _log_gauss_diag(x: list[float], mean: list[float], var: list[float]) -> float:
        # log N(x|mean,var_diag)
        ll = 0.0
        for j in range(len(x)):
            v = max(var[j], 1e-6)
            ll += -0.5 * (math.log(2.0 * math.pi * v) + ((x[j] - mean[j]) ** 2) / v)
        return ll

    def _init_params(self, X: list[list[float]]) -> None:
        # Deterministic init: partition sequence into K chunks and use chunk means/vars.
        T = len(X)
        d = len(X[0])
        self.means = []
        self.vars = []
        for k in range(self.n_states):
            a = int(k * T / self.n_states)
            b = int((k + 1) * T / self.n_states)
            chunk = X[a:b] if b > a else X
            mu = [sum(x[j] for x in chunk) / len(chunk) for j in range(d)]
            vv = []
            for j in range(d):
                v = sum((x[j] - mu[j]) ** 2 for x in chunk) / max(1, (len(chunk) - 1))
                vv.append(max(v, 1e-4))
            self.means.append(mu)
            self.vars.append(vv)

        # mild persistence
        self.pi = [1.0 / self.n_states] * self.n_states
        self.A = []
        for i in range(self.n_states):
            row = []
            for j in range(self.n_states):
                row.append(0.80 if i == j else 0.20 / (self.n_states - 1))
            self.A.append(row)

    def fit(self, X: list[list[float]], max_iter: int = 25, tol: float = 1e-4) -> HMMFitResult:
        if not X:
            raise ValueError("empty X")
        if len(X[0]) == 0:
            raise ValueError("empty feature vectors")

        self._init_params(X)
        K = self.n_states
        T = len(X)

        prev_ll = -math.inf
        converged = False
        n_iter = 0

        for it in range(1, max_iter + 1):
            n_iter = it

            # Precompute emission log-probs
            logB = [[0.0] * K for _ in range(T)]
            for t in range(T):
                for k in range(K):
                    logB[t][k] = self._log_gauss_diag(X[t], self.means[k], self.vars[k])

            # Forward with scaling in log-space
            log_alpha = [[-math.inf] * K for _ in range(T)]
            # init
            for k in range(K):
                log_alpha[0][k] = math.log(max(self.pi[k], EPS)) + logB[0][k]
            # recursion
            for t in range(1, T):
                for j in range(K):
                    log_alpha[t][j] = logB[t][j] + _logsumexp(
                        [log_alpha[t - 1][i] + math.log(max(self.A[i][j], EPS)) for i in range(K)]
                    )

            ll = _logsumexp(log_alpha[T - 1])
            if abs(ll - prev_ll) < tol:
                converged = True
                prev_ll = ll
                break
            prev_ll = ll

            # Backward
            log_beta = [[-math.inf] * K for _ in range(T)]
            for k in range(K):
                log_beta[T - 1][k] = 0.0
            for t in range(T - 2, -1, -1):
                for i in range(K):
                    log_beta[t][i] = _logsumexp(
                        [
                            math.log(max(self.A[i][j], EPS)) + logB[t + 1][j] + log_beta[t + 1][j]
                            for j in range(K)
                        ]
                    )

            # Gamma and Xi
            gamma = [[0.0] * K for _ in range(T)]
            xi = [[[0.0] * K for _ in range(K)] for _ in range(T - 1)]
            for t in range(T):
                denom = _logsumexp([log_alpha[t][k] + log_beta[t][k] for k in range(K)])
                for k in range(K):
                    gamma[t][k] = math.exp(log_alpha[t][k] + log_beta[t][k] - denom)

            for t in range(T - 1):
                denom = -math.inf
                tmp = [[0.0] * K for _ in range(K)]
                for i in range(K):
                    for j in range(K):
                        tmp[i][j] = (
                            log_alpha[t][i]
                            + math.log(max(self.A[i][j], EPS))
                            + logB[t + 1][j]
                            + log_beta[t + 1][j]
                        )
                        denom = _logsumexp([denom, tmp[i][j]])
                for i in range(K):
                    for j in range(K):
                        xi[t][i][j] = math.exp(tmp[i][j] - denom)

            # M-step: pi
            s = sum(gamma[0])
            self.pi = [g / max(s, EPS) for g in gamma[0]]

            # A
            A_new = [[0.0] * K for _ in range(K)]
            for i in range(K):
                denom = sum(gamma[t][i] for t in range(T - 1))
                for j in range(K):
                    num = sum(xi[t][i][j] for t in range(T - 1))
                    A_new[i][j] = num / max(denom, EPS)
                # normalize row
                rs = sum(A_new[i])
                if rs <= 0:
                    A_new[i] = [1.0 / K] * K
                else:
                    A_new[i] = [v / rs for v in A_new[i]]
            self.A = A_new

            # means/vars
            d = len(X[0])
            means_new = [[0.0] * d for _ in range(K)]
            vars_new = [[0.0] * d for _ in range(K)]
            for k in range(K):
                w = sum(gamma[t][k] for t in range(T))
                if w <= EPS:
                    continue
                for j in range(d):
                    means_new[k][j] = sum(gamma[t][k] * X[t][j] for t in range(T)) / w
                for j in range(d):
                    vars_new[k][j] = sum(gamma[t][k] * ((X[t][j] - means_new[k][j]) ** 2) for t in range(T)) / w
                    vars_new[k][j] = max(vars_new[k][j], 1e-4)
            self.means = means_new
            self.vars = vars_new

        return HMMFitResult(
            converged=converged,
            n_iter=n_iter,
            loglik=prev_ll,
            transition=self.A,
            means=self.means,
            vars=self.vars,
        )

    def posterior_last(self, X: list[list[float]]) -> list[float]:
        """Posterior state probabilities for the last observation in X."""
        K = self.n_states
        T = len(X)
        logB = [[0.0] * K for _ in range(T)]
        for t in range(T):
            for k in range(K):
                logB[t][k] = self._log_gauss_diag(X[t], self.means[k], self.vars[k])

        log_alpha = [[-math.inf] * K for _ in range(T)]
        for k in range(K):
            log_alpha[0][k] = math.log(max(self.pi[k], EPS)) + logB[0][k]
        for t in range(1, T):
            for j in range(K):
                log_alpha[t][j] = logB[t][j] + _logsumexp(
                    [log_alpha[t - 1][i] + math.log(max(self.A[i][j], EPS)) for i in range(K)]
                )
        denom = _logsumexp(log_alpha[T - 1])
        post = [math.exp(log_alpha[T - 1][k] - denom) for k in range(K)]
        s = sum(post)
        return [p / max(s, EPS) for p in post]

    def viterbi(self, X: list[list[float]]) -> list[int]:
        K = self.n_states
        T = len(X)
        logB = [[0.0] * K for _ in range(T)]
        for t in range(T):
            for k in range(K):
                logB[t][k] = self._log_gauss_diag(X[t], self.means[k], self.vars[k])

        dp = [[-math.inf] * K for _ in range(T)]
        back = [[0] * K for _ in range(T)]
        for k in range(K):
            dp[0][k] = math.log(max(self.pi[k], EPS)) + logB[0][k]
            back[0][k] = 0

        for t in range(1, T):
            for j in range(K):
                best_i = 0
                best = -math.inf
                for i in range(K):
                    v = dp[t - 1][i] + math.log(max(self.A[i][j], EPS))
                    if v > best:
                        best = v
                        best_i = i
                dp[t][j] = best + logB[t][j]
                back[t][j] = best_i

        last = max(range(K), key=lambda k: dp[T - 1][k])
        path = [0] * T
        path[T - 1] = last
        for t in range(T - 2, -1, -1):
            path[t] = back[t + 1][path[t + 1]]
        return path


def load_hmm_csv(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split(",")
            r = dict(zip(header, parts))
            r["date"] = date.fromisoformat(r["date"])
            # required numeric columns
            for k in ("vix", "ret_1d"):
                r[k] = float(r[k])
            # optional
            if "shock_family" in r:
                r["shock_family"] = str(r["shock_family"])
            if "label" in r:
                r["label"] = str(r["label"])
            rows.append(r)
    return rows


def fit_hmm_rolling(rows: list[dict[str, Any]], window: int = 252, max_iter: int = 20, tol: float = 1e-2, stride: int = 1, max_points: int | None = None) -> dict[str, Any]:
    """Fit a 3-state HMM on a rolling window. Returns per-date p_shock + metadata."""
    if len(rows) < window + 5:
        raise ValueError(f"need at least {window+5} rows, got {len(rows)}")

    # features: ret_1d and vix (scaled)
    def feat(r: dict[str, Any]) -> list[float]:
        return [float(r["ret_1d"]), float(r["vix"]) / 50.0]

    K = 3
    out: list[dict[str, Any]] = []
    last_fit: HMMFitResult | None = None

    if stride < 1:
        raise ValueError("stride must be >=1")

    for t in range(window, len(rows), stride):
        if max_points is not None and len(out) >= max_points:
            break
        seq = [feat(r) for r in rows[t - window : t]]
        hmm = GaussianHMM(n_states=K)
        fit = hmm.fit(seq, max_iter=max_iter, tol=tol)
        post = hmm.posterior_last(seq)
        # map state -> regime by vix mean in the window (state with highest vix mean = SHOCK)
        vix_means = [m[1] for m in fit.means]  # scaled
        order = sorted(range(K), key=lambda k: vix_means[k])
        normal, caution, shock = order[0], order[1], order[2]
        p_shock = post[shock]
        out.append(
            {
                "date": rows[t - 1]["date"].isoformat(),
                "p_shock": float(p_shock),
                "shock_state": int(shock),
                "transition": fit.transition,
                "converged": bool(fit.converged),
                "n_iter": int(fit.n_iter),
                "vix_state_order": [int(normal), int(caution), int(shock)],
                "vix_means_scaled": [float(v) for v in vix_means],
            }
        )
        last_fit = fit

    # transition row sums sanity (use last fit)
    trans = last_fit.transition if last_fit else [[1/3]*3]*3
    row_sums = [sum(r) for r in trans]
    last_vix_means = None
    if out:
        last_vix_means = out[-1].get("vix_means_scaled")
    return {"window": window, "K": K, "rows": out, "transition": trans, "transition_row_sums": row_sums, "last_vix_means_scaled": last_vix_means}
