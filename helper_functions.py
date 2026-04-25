import pandas as pd
import numpy as np
from pathlib import Path

def read_growth_file(file_name, data_dir, description="file", header = None, rows = None):
    if file_name is None:
        print(f"Warning: No {description} provided. Skipping.")
        return None

    # Handle list of files (for liquid growth)
    if isinstance(file_name, list):
        dfs = []
        for i, f in enumerate(file_name):
            file_path = data_dir / f

            if file_path.exists():
                h = header[i] if header else 59
                r = rows[i] if rows else 401

                df = pd.read_excel(file_path,
                                       usecols = "B:CU",
                                       header = h,
                                       nrows= r)
                
                plate_id = Path(f).stem
                df['plate'] = plate_id

                dfs.append(df)
            else:
                print(f"Warning: {description} not found at {file_path.resolve()}")
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        else:
            return None

    else:
        file_path = data_dir / file_name
        if file_path.exists():
            return pd.read_csv(file_path)
        else:
            print(f"Warning: {description} not found at {file_path.resolve()}")
            return None

def read_solid_growth(file_name, data_dir, description="file"):
    if file_name is None:
        print(f"Warning: No {description} provided. Skipping.")
        return None
    
    if isinstance(file_name, list):
        dfs = []
        for i, f in enumerate(file_name):
            file_path = data_dir / f
            if file_path.exists():
                df = pd.read_excel(file_path)
                dfs.append(df)
            else:
                print(f"Warning: {description} not found at {file_path.resolve()}")

        return dfs if dfs else None

    file_path = data_dir / file_name
    if file_path.exists():
        return pd.read_excel(file_path)
    else:
        print(f"Warning: {description} not found at {file_path.resolve()}")
        return None



def clean_reshape_grid_df(
        df,
        layout,
        object = False,
        plate_nr = None
):
    
    df = df.rename(columns ={'Plate Name' : "plate", 'Well ID' : 'well', 'Object ID': 'ID', 'Time Since Start (minutes)' : 'time'})

    
    df_clean = df.merge(layout, on = ['plate', 'well','ID'], how = 'inner')

    df_clean["media"] = df_clean["plate"].str.extract(r"^([^_]+)")
    df_clean["time"] = df_clean["time"]/60

    if plate_nr is not None:
        df_clean['plate_nr'] = plate_nr

    if object == False:
        df_clean.loc[:,'IO'] = (
            (df_clean['Object Color:Red'] +
             df_clean['Object Color:Green'] +
             df_clean['Object Color:Blue']).round(3))   
        
        df_clean.loc[:, 'IB'] = (
            (df_clean['Well color:Red']**(2.2) +
             df_clean['Well color:Green']**(2.2) +
             df_clean['Well color:Blue']**(2.2)).round(3))
        
        df_clean.loc[:, 'Intensity'] = (
            (df_clean['IO'] - df_clean['IB']).round(2))
        df_f = df_clean[['IBT #','time','media','Approximate area','Intensity','IB','IO','replicate','plate_nr']]
    else:
        df_clean.loc[:,'Intensity'] = (
            (df['Red'] +
             df['Green'] +
             df['Blue']).round(3))
        df_f = df_clean[['IBT #','time','media','Approximate area','Intensity','replicate', 'plate_nr']]

    return (df_f)

def clean_reshape_df_no_grid(
        df,
        layout,
        plate_nr = None
):
    
    df = df.rename(columns ={'Plate Name' : 'plate', 'Object ID' : 'ID', 'Time Since Start (minutes)': 'time'})
    df["media"] = df["plate"]
    df["time"] = df["time"]/60

    df.loc[:,'Intensity'] = (
        (df['Red'] +
        df['Green'] +
        df['Blue']).round(3)
    )
    
    df_clean = df.merge(layout, on = ['media', 'ID'], how = 'inner')

    if plate_nr is not None:
        df_clean['plate_nr'] = plate_nr

    df_clean = df_clean[['IBT #', 'time', 'media', 'Approximate area', 'Intensity','dilution','replicate','plate_nr']]
    return df_clean

def solid_summary(
        solid_data
):
    solid_sum = (
        solid_data
        .groupby(['plate_nr','IBT #', 'media', 'time'])
        .agg(
            n = ('Approximate area', 'count'),
            Area_mean=('Approximate area', 'mean'),
            Area_std=('Approximate area', 'std'),
            Intensity_mean=('Intensity', 'mean'),
            Intensity_std=('Intensity', 'std'),
        )
        .reset_index())
    
    return solid_sum
    

def clean_OD_df(
        df,
        layout
):
    df.rename({
        "T° Read 2:600": "Temperature",
    }, axis=1, inplace=True)

    df["Time"] = pd.to_timedelta(df["Time"].astype(str)).dt.total_seconds() / 3600
    
    long = df.melt(
        id_vars=["Time","plate"],
        var_name="well",
        value_name="od"
    )

    long = long[long["well"].str.match(r"^[A-H][0-9]{1,2}$")].copy()
    df = long.merge(
        layout,
        on=["plate","well"],
        how="left"
    )

    assert df["IBT #"].notna().all(), "Unmapped wells detected"
    assert df["od"].notna().all(), "Missing OD values"


    df["is_blank"] = df["IBT #"].str.lower() == "blank"
    blank_means = (
        df[df.is_blank]
        .groupby(["plate","Time", "media"])["od"]
        .mean()
        .reset_index()
        .rename(columns={"od": "blank_od"})
    )
    df = df.merge(blank_means, on=["plate","Time", "media"], how="left")
    print(df["blank_od"].isna().sum(), "missing blank_od values")
    df["od_corrected"] = df["od"] - df["blank_od"]
    df = df.sort_values(["Time","media","IBT #"])

    return (
        df[["Time", "od", "od_corrected", "IBT #", "media", "plate", "replicate"]])