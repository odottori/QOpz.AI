from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

CLASSES = ("NORMAL", "CAUTION", "SHOCK")


@dataclass(frozen=True)
class RegimePrediction:
    asof: date
    label: str
    proba: dict[str, float]


def _softmax(logits: list[float]) -> list[float]:
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps) or 1.0
    return [e / s for e in exps]


def _logit(p: float) -> float:
    p = min(1.0 - 1e-9, max(1e-9, p))
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _year(d: date) -> int:
    return d.year


def parse_date_iso(s: str) -> date:
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid date format {s!r} — expected YYYY-MM-DD") from exc


def load_dataset_csv(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split(",")
            r = dict(zip(header, parts))
            r["date"] = parse_date_iso(r["date"])
            for k in ("vix", "vix3m", "ret_5d"):
                r[k] = float(r[k])
            r["label"] = str(r["label"])
            rows.append(r)
    return rows


def split_by_year(rows: list[dict[str, Any]], train_years: Iterable[int], oos_year: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_set = [r for r in rows if _year(r["date"]) in set(train_years)]
    oos_set = [r for r in rows if _year(r["date"]) == oos_year]
    return train_set, oos_set


def featurize(rows: list[dict[str, Any]], features: list[str]) -> list[list[float]]:
    X: list[list[float]] = []
    for r in rows:
        X.append([float(r[f]) for f in features])
    return X


def labels(rows: list[dict[str, Any]]) -> list[str]:
    return [str(r["label"]) for r in rows]


def train_gaussian_nb(X: list[list[float]], y: list[str], features: list[str]) -> dict[str, Any]:
    """Pure-Python Gaussian Naive Bayes, deterministic, no external deps."""
    # group by class
    idx = {c: [] for c in CLASSES}
    for i, lab in enumerate(y):
        if lab not in idx:
            raise ValueError(f"unknown class: {lab}")
        idx[lab].append(i)

    n = len(y)
    priors: dict[str, float] = {}
    means: dict[str, list[float]] = {}
    vars_: dict[str, list[float]] = {}

    for c in CLASSES:
        ids = idx[c]
        priors[c] = len(ids) / n if n else 1.0 / len(CLASSES)
        # means/vars per feature
        m: list[float] = []
        v: list[float] = []
        for j in range(len(features)):
            vals = [X[i][j] for i in ids] or [0.0]
            mu = sum(vals) / len(vals)
            m.append(mu)
            vv = sum((x - mu) ** 2 for x in vals) / max(1, (len(vals) - 1))
            v.append(max(vv, 1e-6))
        means[c] = m
        vars_[c] = v

    return {
        "type": "gaussian_nb",
        "features": features,
        "priors": priors,
        "means": means,
        "vars": vars_,
        "platt": None,
    }


def predict_proba(model: dict[str, Any], X: list[list[float]]) -> list[dict[str, float]]:
    features = model["features"]
    priors = model["priors"]
    means = model["means"]
    vars_ = model["vars"]

    out: list[dict[str, float]] = []
    for row in X:
        logits: list[float] = []
        for c in CLASSES:
            lp = math.log(max(priors.get(c, 1e-9), 1e-9))
            # gaussian likelihood
            for j in range(len(features)):
                mu = float(means[c][j])
                var = float(vars_[c][j])
                x = float(row[j])
                lp += -0.5 * math.log(2 * math.pi * var) - ((x - mu) ** 2) / (2 * var)
            logits.append(lp)
        probs = _softmax(logits)

        # optional platt scaling
        platt = model.get("platt")
        if isinstance(platt, dict):
            scaled: list[float] = []
            for k, c in enumerate(CLASSES):
                a = float(platt[c]["a"])
                b = float(platt[c]["b"])
                x = _logit(probs[k])
                scaled.append(_sigmoid(a * x + b))
            s = sum(scaled) or 1.0
            probs = [p / s for p in scaled]

        out.append({c: probs[i] for i, c in enumerate(CLASSES)})
    return out


def predict(model: dict[str, Any], X: list[list[float]]) -> list[str]:
    probs = predict_proba(model, X)
    return [max(p.items(), key=lambda kv: kv[1])[0] for p in probs]


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    ok = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    return ok / len(y_true)


def confusion_matrix(y_true: list[str], y_pred: list[str]) -> dict[str, dict[str, int]]:
    m = {a: {b: 0 for b in CLASSES} for a in CLASSES}
    for t, p in zip(y_true, y_pred):
        if t in m and p in m[t]:
            m[t][p] += 1
    return m


def brier_score(y_true: list[str], proba: list[dict[str, float]]) -> float:
    """Multiclass Brier: mean over samples of sum_k (p_k - y_k)^2."""
    if not y_true:
        return 1.0
    total = 0.0
    for yt, pr in zip(y_true, proba):
        for c in CLASSES:
            yk = 1.0 if yt == c else 0.0
            pk = float(pr.get(c, 0.0))
            total += (pk - yk) ** 2
    return total / (len(y_true) * len(CLASSES))


def fit_platt_scaling(model: dict[str, Any], X_cal: list[list[float]], y_cal: list[str], iters: int = 250, lr: float = 0.05) -> dict[str, Any]:
    """One-vs-rest Platt scaling on top of raw probabilities. Pure Python GD."""
    raw = predict_proba({**model, "platt": None}, X_cal)
    # initialise
    platt: dict[str, dict[str, float]] = {c: {"a": 1.0, "b": 0.0} for c in CLASSES}

    for c in CLASSES:
        a = 1.0
        b = 0.0
        # x = logit(p_c)
        xs = [_logit(float(r[c])) for r in raw]
        ys = [1.0 if y == c else 0.0 for y in y_cal]
        for _ in range(iters):
            da = 0.0
            db = 0.0
            n = 0
            for x, y in zip(xs, ys):
                z = a * x + b
                p = _sigmoid(z)
                da += (p - y) * x
                db += (p - y)
                n += 1
            if n:
                a -= lr * (da / n)
                b -= lr * (db / n)
        platt[c] = {"a": float(a), "b": float(b)}

    model2 = dict(model)
    model2["platt"] = platt
    return model2


def fisher_feature_importance(X: list[list[float]], y: list[str], features: list[str]) -> list[tuple[str, float]]:
    """Deterministic importance score; 'SHAP-like' for our offline pipeline."""
    # overall mean per feature
    n = len(y)
    if n == 0:
        return [(f, 0.0) for f in features]

    overall = [sum(row[j] for row in X) / n for j in range(len(features))]

    scores: list[tuple[str, float]] = []
    for j, f in enumerate(features):
        # between-class variance / within-class variance
        between = 0.0
        within = 0.0
        for c in CLASSES:
            idx = [i for i, yy in enumerate(y) if yy == c]
            if not idx:
                continue
            mu_c = sum(X[i][j] for i in idx) / len(idx)
            between += len(idx) * (mu_c - overall[j]) ** 2
            within += sum((X[i][j] - mu_c) ** 2 for i in idx)
        score = between / (within + 1e-9)
        scores.append((f, float(score)))
    scores.sort(key=lambda kv: kv[1], reverse=True)
    return scores


def save_model(model: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")


def load_model(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))
