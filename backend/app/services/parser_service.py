from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from ..models import AccountClass, TranslationPolicy
from .common import to_decimal


def _normalize_col(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {_normalize_col(col): col for col in columns}
    for candidate in candidates:
        key = _normalize_col(candidate)
        if key in normalized:
            return normalized[key]
    return None


def read_file_to_df(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(file_path)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("File has no usable rows")
    return df


def parse_trial_balance(file_path: Path, local_currency: str) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    df = read_file_to_df(file_path)
    cols = [str(c).strip() for c in df.columns]

    account_code_col = _pick_column(cols, ["Account Code", "Code", "Account", "GL Code", "Account Number"])
    account_name_col = _pick_column(cols, ["Account Name", "Name", "Description", "Account Description"])
    debit_col = _pick_column(cols, ["Debit", "Dr", "Period Debit", "Debits"])
    credit_col = _pick_column(cols, ["Credit", "Cr", "Period Credit", "Credits"])
    amount_col = _pick_column(cols, ["Balance", "Amount", "Net", "Closing Balance", "YTD"])
    counterparty_col = _pick_column(cols, ["Counterparty", "Intercompany", "Contact", "Trading Partner"])
    ic_flag_col = _pick_column(cols, ["Is Intercompany", "IC", "Intercompany Flag"])

    if not account_code_col:
        raise ValueError("Cannot identify account code column in source file")
    if not (amount_col or (debit_col and credit_col)):
        raise ValueError("File must contain either amount column or both debit and credit columns")

    records: list[dict[str, Any]] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for idx, row in df.iterrows():
        account_code_raw = row.get(account_code_col)
        if pd.isna(account_code_raw):
            continue

        account_code = str(account_code_raw).strip()
        if not account_code:
            continue

        debit = to_decimal(row.get(debit_col)) if debit_col else Decimal("0")
        credit = to_decimal(row.get(credit_col)) if credit_col else Decimal("0")
        if amount_col:
            amount = to_decimal(row.get(amount_col))
        else:
            amount = debit - credit

        total_debit += max(debit, Decimal("0"))
        total_credit += max(credit, Decimal("0"))

        account_name = None
        if account_name_col is not None and pd.notna(row.get(account_name_col)):
            account_name = str(row.get(account_name_col)).strip()

        counterparty = None
        if counterparty_col is not None and pd.notna(row.get(counterparty_col)):
            counterparty = str(row.get(counterparty_col)).strip()

        is_ic = False
        if ic_flag_col is not None and pd.notna(row.get(ic_flag_col)):
            text = str(row.get(ic_flag_col)).strip().lower()
            is_ic = text in {"1", "true", "yes", "y"}
        if counterparty:
            is_ic = True

        records.append(
            {
                "account_code": account_code,
                "account_name": account_name,
                "local_currency": local_currency,
                "period_amount": amount,
                "debit": debit if debit_col else None,
                "credit": credit if credit_col else None,
                "counterparty": counterparty,
                "is_intercompany": is_ic,
                "source_row_number": int(idx) + 2,
            }
        )

    if debit_col and credit_col:
        imbalance = total_debit - total_credit
    else:
        total_amount = sum((item["period_amount"] for item in records), start=Decimal("0"))
        positive = sum((max(item["period_amount"], Decimal("0")) for item in records), start=Decimal("0"))
        negative = sum((-min(item["period_amount"], Decimal("0")) for item in records), start=Decimal("0"))
        total_debit = positive
        total_credit = negative
        imbalance = total_amount

    stats = {
        "row_count": Decimal(str(len(records))),
        "total_debit": total_debit,
        "total_credit": total_credit,
        "imbalance": imbalance,
    }
    return records, stats


def parse_mapping(file_path: Path) -> list[dict[str, Any]]:
    df = read_file_to_df(file_path)
    cols = [str(c).strip() for c in df.columns]

    entity_col = _pick_column(cols, ["Entity", "Entity Name", "Entity ID"])
    local_code_col = _pick_column(cols, ["Local Account Code", "Account Code", "Local Code", "Code"])
    local_name_col = _pick_column(cols, ["Local Account Name", "Local Name", "Account Name", "Description"])
    group_code_col = _pick_column(cols, ["Group Account Code", "Group Code", "Reporting Code"])
    group_name_col = _pick_column(cols, ["Group Account Name", "Group Name", "Reporting Name"])
    class_col = _pick_column(cols, ["Account Class", "Type", "Class"])
    policy_col = _pick_column(cols, ["Translation Policy", "FX Policy", "Rate Type"])
    hist_date_col = _pick_column(cols, ["Historical Rate Date", "Hist Date", "Rate Date"])
    intercompany_col = _pick_column(cols, ["Is Intercompany", "Intercompany", "IC"])

    missing = []
    if not local_code_col:
        missing.append("local account code")
    if not group_code_col:
        missing.append("group account code")
    if not class_col:
        missing.append("account class")
    if not policy_col:
        missing.append("translation policy")

    if missing:
        raise ValueError(f"Mapping file missing required columns: {', '.join(missing)}")

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        local_code = str(row.get(local_code_col)).strip() if pd.notna(row.get(local_code_col)) else ""
        group_code = str(row.get(group_code_col)).strip() if pd.notna(row.get(group_code_col)) else ""
        if not local_code or not group_code:
            continue

        account_class = str(row.get(class_col)).strip().upper()
        if account_class not in {item.value for item in AccountClass}:
            raise ValueError(f"Invalid account class '{account_class}' for local account {local_code}")

        policy = str(row.get(policy_col)).strip().upper()
        if policy not in {item.value for item in TranslationPolicy}:
            raise ValueError(f"Invalid translation policy '{policy}' for local account {local_code}")

        hist_date: date | None = None
        if hist_date_col and pd.notna(row.get(hist_date_col)):
            hist_date = pd.to_datetime(row.get(hist_date_col)).date()

        entity_ref = None
        if entity_col and pd.notna(row.get(entity_col)):
            entity_ref = str(row.get(entity_col)).strip()

        local_name = str(row.get(local_name_col)).strip() if local_name_col and pd.notna(row.get(local_name_col)) else None
        group_name = str(row.get(group_name_col)).strip() if group_name_col and pd.notna(row.get(group_name_col)) else None

        is_ic = False
        if intercompany_col and pd.notna(row.get(intercompany_col)):
            val = str(row.get(intercompany_col)).strip().lower()
            is_ic = val in {"1", "true", "yes", "y"}

        records.append(
            {
                "entity_ref": entity_ref,
                "local_account_code": local_code,
                "local_account_name": local_name,
                "group_account_code": group_code,
                "group_account_name": group_name,
                "account_class": account_class,
                "translation_policy": policy,
                "historical_rate_date": hist_date,
                "is_intercompany": is_ic,
            }
        )

    if not records:
        raise ValueError("No mapping rows found")

    return records
