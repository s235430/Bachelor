import pandas as pd
from pathlib import Path

def od_normalization(
        file_path,
        target_od,
        blank = 0.098,
        final_volume_uL = 910,
        threshold_uL = 30,
        dilution_factor = 100,
        out_csv = None
        ):
    
    """
    Read a plate OD file, apply optional pre-dilution factor, and calculate normalization volumes.
    
    Parameters
    ----------
    file_path : str or Path
        Path to CSV or Excel plate file.
    target_od : float
        Target OD for normalization.
    final_volume_uL : float, optional
        Volume to reach after normalization (default 600 uL).
    threshold_uL : float, optional
        Minimum removable volume (default 100 uL).
    dilution_factor : float, optional
        Pre-dilution factor if plate was diluted before reading (default 10).
    out_csv : str or Path, optional
        If provided, saves resulting dataframe as CSV.
    blank : float, required
        Background OD to subtract from all wells (default 0.098).
        
    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        ['well','OD','volume_ul','add_diluent_uL','theoretical_OD','status']
    """

    file_path = Path(file_path)
    
    if file_path.suffix == ".csv":
        df = pd.read_csv(file_path, header=0, index_col=0)
    else:
        df = pd.read_excel(file_path, header=0, index_col=0)

    # --- Convert to long format ---
    df = (
        df.stack()
          .rename("OD")
          .reset_index()
    )

    df.columns = ["row","col","OD"]
    df["well"] = df["row"] + df["col"].astype(str)
    df = df[["well", "OD"]]

    if blank is not None:
        df["OD"] = (df["OD"] - blank).clip(lower=0)
    
    # Remove empty wells
    df = df[df["OD"] > 0].copy()

    # --- columns ---
    df["volume_ul"] = 0.0
    df["add_diluent_uL"] = 0.0
    df["theoretical_OD"] = df["OD"]
    df["status"] = "no_change"
    df['OD'] = df['OD']*dilution_factor

    for i, row in df.iterrows():
        od = row["OD"]
        if od <= 0:
            df.at[i, "status"] = "invalid_OD"
            continue

        if od <= target_od:
            df.at[i, "status"] = "below_target"
            df.at[i, "theoretical_OD"] = od
            continue

        keep_fraction = target_od / od
        culture_volume = keep_fraction * final_volume_uL
        remove_volume = final_volume_uL - culture_volume

        if remove_volume < threshold_uL:
            df.at[i, "status"] = "below_threshold"
            df.at[i, "theoretical_OD"] = od
            continue

        
        df.at[i, "add_diluent_uL"] = remove_volume
        df.at[i, "theoretical_OD"] = target_od
        df.at[i, "status"] = "OK"

    # --- Save CSV if requested ---
    if out_csv:
        out_path = Path(out_csv)
        df["volume_ul"] = df["add_diluent_uL"].round()
        df[['well','volume_ul']].to_csv(out_path, index=False)

    return df[[
        "well",
        "OD",
        "volume_ul",
        "add_diluent_uL",
        "theoretical_OD",
        "status",
    ]]


def get_layout_reference(file_path, selected_cols):
    from pathlib import Path
    import pandas as pd

    file_path = Path(file_path)

    if file_path.suffix == ".csv":
        df = pd.read_csv(file_path, header=0, index_col=0)
    else:
        df = pd.read_excel(file_path, header=0, index_col=0)

    # --- Convert to long format ---
    df = df.stack().rename("IBT #").reset_index()
    df.columns = ["row", "col", "IBT #"]

    # --- Ensure consistent types ---
    df["col"] = pd.to_numeric(df["col"])
    selected_cols = [int(c) for c in selected_cols]

    # --- Filter ---
    filt = df[df["col"].isin(selected_cols)].copy()

    # --- Create deepwell columns ---
    filt["deepwell_col"] = 2 * filt["col"] - 1

    # --- Create well labels ---
    filt["well"] = filt["row"] + filt["col"].astype(str)
    filt["deepwell_well"] = filt["row"] + filt["deepwell_col"].astype(str)

    if filt.empty:
        raise ValueError("No rows match selected columns")

    return filt[["IBT #", "well", "row", "col", "deepwell_well", "deepwell_col"]].reset_index(drop=True)

def generate_randomized_mapping(
    df,
    media_list=("CRE", "LRE", "TY"),
    replicates=4,
    seed=None,
    out_ot_csv=None,
    out_data_csv=None
):
    """
    Generate randomized mapping using deepwell positions.

    - Uses deepwell_well as source
    - Expands replicates per media
    - Randomizes destination wells
    - Splits into multiple 96-well plates if needed
    """

    import string

    df = df.copy()

    # --- Use deepwell well ---
    ref_df = df[["IBT #", "deepwell_well"]].rename(
        columns={"deepwell_well": "from_well"}
    ).reset_index(drop=True)

    # --- Expand ---
    expanded_list = []
    for media in media_list:
        tmp = ref_df.copy()
        tmp = tmp.loc[tmp.index.repeat(replicates)].reset_index(drop=True)
        tmp["replicate"] = tmp.groupby(["IBT #", "from_well"]).cumcount() + 1
        tmp["media"] = media
        expanded_list.append(tmp)

    expanded = pd.concat(expanded_list, ignore_index=True)

    # --- Prepare layout ---
    rows = list(string.ascii_uppercase[:8])
    cols = list(range(1, 13))
    wells = [f"{r}{c}" for r in rows for c in cols]

    # --- Assign plate based on source column ---
    expanded["source_col"] = expanded["from_well"].str.extract(r"(\d+)").astype(int)
    expanded["plate"] = expanded["source_col"].apply(lambda x: f"plate_{x}")

    # --- Assign wells within each plate ---
    plates = []

    for plate_name, plate_df in expanded.groupby("plate"):
        plate_df = plate_df.sample(frac=1, random_state=seed).reset_index(drop=True)

        if len(plate_df) > 96:
            raise ValueError(f"{plate_name} has more than 96 samples!")

        plate_df["to_well"] = wells[:len(plate_df)]
        plates.append(plate_df)

    final_df = pd.concat(plates, ignore_index=True)

    # --- Save OT CSV ---
    if out_ot_csv:
        Path(out_ot_csv).parent.mkdir(parents=True, exist_ok=True)
        (final_df[
            ["IBT #", "from_well", "to_well", "plate", "media", "replicate"]
        ].sort_values(["plate","media","IBT #", "from_well","replicate"])).to_csv(out_ot_csv, index=False)

    # --- Save data CSV ---
    if out_data_csv:
        Path(out_data_csv).parent.mkdir(parents=True, exist_ok=True)
        out_df = final_df.copy()

        out_df = out_df.rename(columns={"to_well": "well"})
        out_df = out_df[
            ["IBT #", "well", "media", "plate", "replicate"]
        ]

        out_df.to_csv(out_data_csv, index=False)

    return final_df.sort_values(["plate", "from_well"]).reset_index(drop=True)

def stamp_mapping_reference(
    df,
    selected_cols,
    out_data_csv=None
):
    """
    Generate stamping layout based on selected deepwell source columns.
    Assumes:
    - df already contains only relevant rows
    - df has columns: 'IBT #', 'deepwell_well', 'deepwell_col'

    Mapping rule:
    - selected_cols[0] → dest cols 1–4
    - selected_cols[1] → dest cols 6–9
    - etc (block of 4 + 1 spacer)
    """
    df = df.copy()

    out_rows = []

    for i, col in enumerate(selected_cols):

        # block pattern: 4 replicates + 1 spacer
        start_col = 1 + i * 5
        dest_cols = [start_col + j for j in range(4)]

        col_df = df[df["deepwell_col"] == col]

        for _, row in col_df.iterrows():
            src_well = row["deepwell_well"]
            ibt = row["IBT #"]

            row_letter = src_well[0]

            for rep, dest_col in enumerate(dest_cols, start=1):
                dest_well = f"{row_letter}{dest_col}"

                out_rows.append({
                    "IBT #": ibt,
                    "from_well": src_well,
                    "well": dest_well,
                    "replicate": rep,
                    "deepwell_col": col
                })

    out_df = pd.DataFrame(out_rows)

    # --- save ---
    if out_data_csv:
        Path(out_data_csv).parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(out_data_csv, index=False)

    return out_df.sort_values(
        ["deepwell_col", "from_well", "replicate"]
    ).reset_index(drop=True)