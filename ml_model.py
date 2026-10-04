#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
User‑Behaviour Analysis with Machine Learning
============================================

Author   : Your Name
Created  : 2026‑10‑04
Version  : 1.0

Usage
-----
    python user_behaviour_ml.py --data path/to/user_log.csv \
                                --target churn \
                                --model random_forest \
                                --output results/

Description
-----------
The script expects a CSV file with **raw activity logs**.  
Typical columns (you can adapt the code to your schema):

    user_id          : identifier of the user (string / int)
    timestamp        : datetime of the event (ISO‑8601 or epoch)
    action_type      : categorical name of the performed action
    duration_seconds : numeric – how long the action lasted
    device           : categorical – e.g. 'mobile', 'desktop'
    ... (any other raw columns)

The script will:

1.  Aggregate events per user → one row per user.
2.  Engineer features such as:
        - total number of sessions
        - average session length
        - frequency of each action_type
        - device usage ratios
3.  Encode categorical features (One‑Hot).
4.  Train a classifier (default = RandomForest) to predict the column given by ``--target``.
5.  Print / plot evaluation metrics.
6.  (Optional) Run K‑Means clustering on the engineered features and visualise the clusters.

"""

# ----------------------------------------------------------------------
# Imports
# ----------------------------------------------------------------------
import argparse
import os
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix,
                             classification_report, roc_auc_score,
                             roc_curve)
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.cluster import KMeans

warnings.filterwarnings("ignore")   # silence harmless warnings


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """Parse command‑line arguments."""
    parser = argparse.ArgumentParser(
        description="Machine‑Learning pipeline for user‑behaviour analysis."
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to the CSV file containing raw user activity logs.",
    )
    parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Name of the column to predict (e.g., 'churn', 'high_value').",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="random_forest",
        choices=["random_forest", "gradient_boosting"],
        help="Which classifier to train.",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Proportion of data used for the test set.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Folder where plots & reports will be saved.",
    )
    parser.add_argument(
        "--cluster",
        action="store_true",
        help="If set, run K‑Means clustering on the engineered features.",
    )
    return parser.parse_args()


def load_data(csv_path: str) -> pd.DataFrame:
    """Read CSV and parse timestamps."""
    df = pd.read_csv(csv_path)
    # Try to parse a column named 'timestamp' (common name)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        raise KeyError("Column 'timestamp' not found in the dataset.")
    return df


def aggregate_user_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert raw event logs into one row per user with aggregated statistics.
    """
    # ------------------------------------------------------------------
    # 1️⃣ Basic per‑user aggregates
    # ------------------------------------------------------------------
    agg_funcs = {
        "timestamp": ["min", "max", "nunique"],          # first, last, distinct days
        "duration_seconds": ["sum", "mean", "std"],     # total, avg, std of duration
    }

    # If there are additional numeric columns, add them automatically
    numeric_cols = df.select_dtypes(include=["int64", "float64"]).columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in ["user_id", "duration_seconds"]]
    for col in numeric_cols:
        agg_funcs[col] = ["mean", "std"]

    user_base = df.groupby("user_id").agg(agg_funcs)
    user_base.columns = ["_".join(col).strip() for col in user_base.columns.values]
    user_base = user_base.reset_index()

    # ------------------------------------------------------------------
    # 2️⃣ Action‑type frequencies (one‑hot like)
    # ------------------------------------------------------------------
    action_counts = (
        df.groupby(["user_id", "action_type"])
        .size()
        .unstack(fill_value=0)
        .add_prefix("action_")
        .reset_index()
    )

    # ------------------------------------------------------------------
    # 3️⃣ Device usage ratios
    # ------------------------------------------------------------------
    device_counts = (
        df.groupby(["user_id", "device"])
        .size()
        .unstack(fill_value=0)
        .add_prefix("device_")
        .reset_index()
    )
    # Convert to ratios (percentage of sessions per device)
    device_ratio = device_counts.copy()
    device_cols = [c for c in device_ratio.columns if c.startswith("device_")]
    device_ratio[device_cols] = device_ratio[device_cols].div(
        device_ratio[device_cols].sum(axis=1), axis=0
    )

    # ------------------------------------------------------------------
    # 4️⃣ Merge everything together
    # ------------------------------------------------------------------
    user_df = (
        user_base.merge(action_counts, on="user_id", how="left")
        .merge(device_ratio, on="user_id", how="left")
    )
    # Fill NaNs that appear after merges (e.g., users with no actions of a certain type)
    user_df = user_df.fillna(0)

    # ------------------------------------------------------------------
    # 5️⃣ Derive extra features
    # ------------------------------------------------------------------
    # Session length = last_timestamp - first_timestamp (in seconds)
    user_df["session_length_seconds"] = (
        (user_df["timestamp_max"] - user_df["timestamp_min"]).dt.total_seconds()
    )
    # Average sessions per day
    user_df["sessions_per_day"] = user_df["timestamp_nunique"] / (
        user_df["session_length_seconds"] / (24 * 3600) + 1e-6
    )
    return user_df


def prepare_features(
    df: pd.DataFrame, target_col: str, random_state: int = 42
) -> tuple:
    """
    Split data, build a preprocessing pipeline and return train/test sets.
    Returns:
        X_train, X_test, y_train, y_test, preprocessing_pipeline
    """
    if target_col not in df.columns:
        raise KeyError(f"Target column '{target_col}' not found in the dataframe.")

    X = df.drop(columns=[target_col, "user_id"])
    y = df[target_col]

    # Identify column types
    categorical_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    numeric_cols = X.select_dtypes(include=["int64", "float64"]).columns.tolist()

    # Pre‑processing: One‑Hot for categoricals, StandardScaler for numerics
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
        ]
    )

    # Train‑test split (stratified if classification)
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=args.test_size,
        random_state=random_state,
        stratify=y if len(np.unique(y)) > 2 else None,
    )

    return X_train, X_test, y_train, y_test, preprocessor


def build_classifier(model_name: str, random_state: int = 42) -> Pipeline:
    """Create a scikit‑learn Pipeline with the chosen classifier."""
    if model_name == "random_forest":
        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=None,
            min_samples_split=2,
            random_state=random_state,
            n_jobs=-1,
        )
    elif model_name == "gradient_boosting":
        clf = GradientBoostingClassifier(
            n_estimators=200,
            learning_rate=0.1,
            max_depth=3,
            random_state=random_state,
        )
    else:
        raise ValueError(f"Unsupported model '{model_name}'")

    # The pipeline will first apply the preprocessor defined earlier
    pipeline = Pipeline(steps=[("preprocess", None), ("clf", clf)])
    return pipeline


def train_and_evaluate(
    pipeline: Pipeline,
    X_train,
    X_test,
    y_train,
    y_test,
    output_dir: Path,
    model_name: str,
) -> None:
    """Fit the model, compute metrics, and save plots."""
    # Insert the preprocessor into the pipeline (it was set to None earlier)
    pipeline.steps[0] = ("preprocess", preprocessor)

    # Fit
    pipeline.fit(X_train, y_train)

    # Predict
    y_pred = pipeline.predict(X_test)
    y_proba = (
        pipeline.predict_proba(X_test)[:, 1]
        if hasattr(pipeline.named_steps["clf"], "predict_proba")
        else None
    )

    # ------------------- Metrics -------------------
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred)

    print("\n=== Classification Report ===")
    print(classification_report(y_test, y_pred))

    # Save report as CSV
    pd.DataFrame(report).transpose().to_csv(output_dir / "classification_report.csv")

    # ------------------- Confusion Matrix -------------------
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False)
    plt.title(f"{model_name} – Confusion Matrix")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.tight_layout()
    plt.savefig(output_dir / "confusion_matrix.png")
    plt.close()

    # ------------------- ROC Curve (if probability available) -------------------
    if y_proba is not None:
        auc = roc_auc_score(y_test, y_proba)
        fpr, tpr, _ = roc_curve(y_test, y_proba)

        plt.figure(figsize=(6, 5))
        plt.plot(fpr, tpr, label=f"AUC = {auc:.3f}")
        plt.plot([0, 1], [0, 1], "k--")
        plt.xlabel("False Positive Rate")
        plt.ylabel("True Positive Rate")
        plt.title(f"{model_name} – ROC Curve")
        plt.legend(loc="lower right")
        plt.tight_layout()
        plt.savefig(output_dir / "roc_curve.png")
        plt.close()
        print(f"ROC‑AUC: {auc:.4f}")

    # ------------------- Feature Importance (for tree‑based models) -------------------
    if hasattr(pipeline.named_steps["clf"], "feature_importances_"):
        # Get