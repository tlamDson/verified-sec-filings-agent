"""Show a runs.csv value the way its unit asks. No rounding beyond display."""

from sec_agent.runs import RunRow


def show_value(row: RunRow) -> str:
    value = row.value
    match row.unit:
        case "fraction":
            return f"{value * 100:.1f}%"
        case "p_value":
            return f"p = {value:.2g}"
        case "difference":
            return f"{value:+.3f}"
        case "kappa":
            return f"{value:.2f}"
        case "ms":
            return f"{value:.0f} ms"
        case _:
            return f"{value:g} {row.unit}"


def show_interval(row: RunRow) -> str:
    if row.ci_low is None or row.ci_high is None:
        return ""
    low = row.model_copy(update={"value": row.ci_low})
    high = row.model_copy(update={"value": row.ci_high})
    return f"{show_value(low)} to {show_value(high)}"
