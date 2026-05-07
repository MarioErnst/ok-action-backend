def extract_errors_for_dim(analysis: dict, dim: str | None) -> list:
    """
    Extracts the error list from a single dimension's analysis result.

    Returns the 'err' or 'det' list for the given dim, or an empty list
    if dim is None or the dimension is not present in the analysis.
    """
    if not dim:
        return []
    dim_data = analysis.get("dims", {}).get(dim, {})
    return dim_data.get("err") or dim_data.get("det") or []
